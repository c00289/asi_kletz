"""SprintService: the agile rules. A sprint is eight points and fourteen calendar days, Tuesday to Monday; the
tool sums, warns, closes, carries, plans the chain ahead and aligns an older chain onto the cadence.

The owner's law (2026-10-29, ``schema/definitions.py:SPRINT_RULE``): "what we know as sprint 3 is actually sprint
31, renumber appropriately, and then ensure that sprints always go Tuesday to Tuesday; this supersedes anything I
said before; I also included a picture from systems engineering that is law for our sprints." The picture: Sprint
31 is 2026-10-27 to 2026-11-09 and every sprint after it follows 14 days later. So a sprint starts on a Tuesday and
ends on the Monday 13 days later (``SPRINT_LENGTH``), the next starts the next day, and a holiday is a day off
inside it, never a reason to move it. Capacity is 8 points per sprint, fixed (``SPRINT_CAPACITY``, the rule of
2026-10-28 that stands): ``guard`` enforces both on every create and update of a sprint that starts on or after
the anchor (an older Closed sprint is history), ``enforce_capacity`` the capacity on every open.

``align`` is the migration for a database written under the old rule (10 business days, holidays stretching the
dates): it renumbers the chain so the sprint starting on the anchor date carries the anchor number, re-dates
every sprint that is not Closed onto the cadence, carries every reference and recomputes the plan's schedule.

Every write goes through the entity services, so the audit log and the event bus see it like any other
change. ``close`` publishes ``sprint.closed`` with the numbers the dashboard shows; ``plan`` publishes
``sprint.planned``; ``align`` publishes ``sprint.aligned``.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, ValidationError
from ..generate import plan_queries as pq
from ..generate import sprint_queries as q
from ..schema import normalise_uid
from ..schema.definitions import (
    CADENCE_RULE,
    CADENCE_START,
    CAPACITY_RULE,
    SPRINT_CAPACITY,
    SPRINT_LENGTH,
    SPRINT_WEEKDAY,
)
from ..tracker.business_days import holidays_within

if TYPE_CHECKING:
    from ..brain import Brain

_LABEL_NUMBER = re.compile(r"^(?P<word>.*?)(?P<n>\d+)\s*$")
HOLIDAYS_GOAL = "Holidays: "  # the goal the planner writes when a sprint contains holidays; never a human's
PLAN_YEARS = 3
ONE_DAY = dt.timedelta(days=1)
REFERENCES = (  # (entity, column): what points at a sprint by number, carried by ``align``
    (q.ITEM, "sprint"), (q.ITEM, "carried_from"), (q.WEEK, "sprint"), (pq.PLAN_ENTITY, "sprint"),
)


def sprint_end(start: dt.date) -> dt.date:
    """The last day of a sprint that starts on ``start``: the Monday 13 days later."""
    return start + dt.timedelta(days=SPRINT_LENGTH - 1)


def cadence_start(number: int, anchor_number: int, anchor_start: dt.date) -> dt.date:
    """The first day of sprint ``number`` on the cadence that has sprint ``anchor_number`` start on ``anchor_start``."""
    return anchor_start + dt.timedelta(days=SPRINT_LENGTH * (int(number) - int(anchor_number)))


def holidays_goal(start: dt.date, end: dt.date, holidays: dict[dt.date, str]) -> str | None:
    """``Holidays: <name> (<m/d>), ...`` for the holidays inside ``[start, end]``, or ``None`` when there are none.
    Days off inside the sprint, named so the board knows; they never move its dates."""
    within = holidays_within(start, end, holidays)
    if not within:
        return None
    return HOLIDAYS_GOAL + ", ".join(f"{holidays[day]} ({day.month}/{day.day})" for day in within)


class SprintService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- the rules on the row ------------------------------------------------------------------
    def guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> None:
        """The check the ``sprint`` entity service runs before a create (``current`` is None) or an update.

        Capacity: a sprint that is not Closed has 8: a create without one gets it, a create or an update with
        another value is refused with the rule's text. A Closed sprint's capacity is history and may be edited.
        Cadence: a sprint that starts on or after the anchor (2026-10-27) starts on a Tuesday and ends on the
        Monday 13 days later (an end left empty is filled), and starts the day after the previous sprint on the
        cadence ends, 14 days more per number between them; otherwise it is refused with the law's text. Dates
        are checked when they are written: an older sprint keeps its history until someone edits its dates, and
        ``sprint align`` is the way to move a whole chain.
        """
        status = clean.get("status", (current or {}).get("status"))
        if status != "Closed":
            if current is None and clean.get("capacity") is None:
                clean["capacity"] = SPRINT_CAPACITY
            if "capacity" in clean and clean["capacity"] not in (None, SPRINT_CAPACITY):
                raise ValidationError(q.SPRINT, [CAPACITY_RULE])
        self._guard_dates(current, clean)

    def _guard_dates(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> None:
        if current is not None and "start" not in clean and "end" not in clean:
            return
        row = {**(current or {}), **clean}
        if not row.get("start"):
            return  # an undated Planned sprint: the planner or ``sprint start`` dates it
        start = q.parse_date(row["start"], "start")
        if start < CADENCE_START:
            return  # history: the sprints before the picture keep their dates
        if start.weekday() != SPRINT_WEEKDAY:
            raise ValidationError(q.SPRINT, [
                f"start {start.isoformat()} is a {start.strftime('%A')}, not a Tuesday: {CADENCE_RULE}"
            ])
        wanted = sprint_end(start)
        if clean.get("end") in (None, "") and ("end" in clean or current is None or "start" in clean):
            clean["end"] = wanted.isoformat()
        elif row.get("end"):
            end = q.parse_date(row["end"], "end")
            if end != wanted:
                raise ValidationError(q.SPRINT, [
                    f"end {end.isoformat()} is not the Monday 13 days after {start.isoformat()} "
                    f"({wanted.isoformat()}): {CADENCE_RULE}"
                ])
        number = row.get("number")
        if number is None:
            return
        own = (current or {}).get("id")
        previous = [
            s for s in q.sprints(self.brain)
            if s["id"] != own and int(s["number"]) < int(number) and s.get("start") and s.get("end")
            and q.parse_date(s["start"]) >= CADENCE_START
        ]
        if not previous:
            return
        before = previous[-1]
        between = int(number) - int(before["number"]) - 1  # numbers and dates lock together: 14 days a sprint
        expected = q.parse_date(before["end"]) + ONE_DAY + dt.timedelta(days=SPRINT_LENGTH * between)
        if expected != start:
            after = f"after sprint {before['number']} ends ({before['end']})"
            why = f"the day {after}" if not between else f"{between} sprint(s) of {SPRINT_LENGTH} days {after}"
            raise ValidationError(q.SPRINT, [
                f"sprint {number} starts {start.isoformat()}, not {expected.isoformat()}, {why}: {CADENCE_RULE}"
            ])

    def enforce_capacity(self, actor: str = "system") -> int:
        """On open: every sprint that is not Closed and whose capacity is not 8 gets 8, in one transaction,
        audited once (``enforce_capacity``, the count and the ids) when anything changed. Returns the count."""
        service = self.brain.service(q.SPRINT)
        rows = [
            r for r in service.list()
            if r.get("status") != "Closed" and r.get("capacity") != SPRINT_CAPACITY
        ]
        if not rows:
            return 0
        with self.brain.storage.transaction():
            for row in rows:
                service.repo.update(row["id"], {"capacity": SPRINT_CAPACITY})
            self.brain.storage.audit(
                actor, "enforce_capacity", q.SPRINT, None,
                {"count": len(rows), "ids": [r["id"] for r in rows], "capacity": SPRINT_CAPACITY},
            )
        return len(rows)

    # -- an item and its plan row (0.13.0) ---------------------------------------------------------
    def link_item(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> list[str] | None:
        """The guard of ``sprint_item``: ``plan_row`` and ``plan_uid`` name the same Safety Plan row. Given
        ``plan_row``, ``plan_uid`` follows; given ``plan_uid``, ``plan_row`` is resolved from it; the uid wins
        when both are given and disagree, with a warning. An unknown uid or id is refused."""
        return self._link(clean, loading=False)

    def link_loaded(self, clean: dict[str, Any]) -> list[str] | None:
        """The load hook of ``sprint_item``: a file's ``plan_uid`` is kept and ``plan_row`` re-resolved from
        it, silently (a stale id in the file is the very case the uid is for), so a tracker dump survives a
        plan re-import that renumbered the rows; an unknown uid leaves ``plan_row`` empty, with a warning,
        rather than a stale number."""
        return self._link(clean, loading=True)

    def _link(self, clean: dict[str, Any], *, loading: bool) -> list[str] | None:
        plan = self.brain.service(pq.PLAN_ENTITY).repo
        warnings: list[str] = []
        given_uid = clean.get("plan_uid") not in (None, "")
        given_row = clean.get("plan_row") is not None
        if given_uid:
            uid = normalise_uid(clean["plan_uid"])
            if uid is None:
                raise ValidationError(q.ITEM, [f"plan_uid: {clean['plan_uid']!r} is not a uid"])
            row = plan.get_by_uid(uid)
            if row is None:
                if not loading:
                    raise ValidationError(q.ITEM, [f"plan_uid {uid} names no Safety Plan row"])
                warnings.append(f"plan_uid {uid} names no Safety Plan row; plan_row left empty")
                clean["plan_uid"], clean["plan_row"] = uid, None
            else:
                if given_row and int(clean["plan_row"]) != int(row["id"]) and not loading:
                    # by hand the two disagreeing is worth a word; on a load a stale id is the very case the uid is for
                    warnings.append(
                        f"plan_row {clean['plan_row']} and plan_uid {uid} disagree; the uid wins: plan_row {row['id']}"
                    )
                clean["plan_uid"], clean["plan_row"] = uid, int(row["id"])
        elif given_row:
            row = plan.get(int(clean["plan_row"]))
            if row is None:
                if not loading:
                    raise ValidationError(q.ITEM, [f"plan_row {clean['plan_row']} names no Safety Plan row"])
                warnings.append(f"plan_row {clean['plan_row']} names no Safety Plan row")
            else:
                clean["plan_uid"] = row.get("uid")
        elif "plan_row" in clean or "plan_uid" in clean:  # cleared on purpose: both go
            clean["plan_row"] = clean["plan_uid"] = None
        return warnings or None

    def fill_plan_uids(self, actor: str = "system") -> int:
        """On open: every item with a ``plan_row`` and no ``plan_uid`` gets the row's uid (an item written
        before 0.13.0), through the repository, audited once with the count. Returns the count."""
        items = self.brain.service(q.ITEM)
        plan = self.brain.service(pq.PLAN_ENTITY).repo
        filled: list[int] = []
        with self.brain.storage.transaction():
            for item in items.list():
                if item.get("plan_row") is None or item.get("plan_uid"):
                    continue
                row = plan.get(int(item["plan_row"]))
                if row is None or not row.get("uid"):
                    continue
                items.repo.update(item["id"], {"plan_uid": row["uid"]})
                filled.append(item["id"])
            if filled:
                self.brain.storage.audit(actor, "link_plan_uids", q.ITEM, None, {"count": len(filled), "ids": filled})
        return len(filled)

    # -- reads -------------------------------------------------------------------------
    def board(self, number: int | None = None, as_of: Any = None) -> dict[str, Any]:
        sprint = q.sprint_by_number(self.brain, number)
        return q.board(self.brain, sprint, q.as_of_date(as_of))

    # -- writes --------------------------------------------------------------------------
    def start(
        self, *, phase: str | None = None, start: Any = None, end: Any = None, goal: str | None = None,
        label: str | None = None, number: int | None = None, as_of: Any = None, actor: str = "python",
    ) -> tuple[dict[str, Any], list[str]]:
        """Open a sprint as Active: the Planned sprint ``number`` (or the next Planned one), else a new one.

        The first day is ``--start``, else the day after the previous sprint on the cadence ends, else
        ``--as-of``, else today; it must be a Tuesday (the guard refuses anything else) and the last day is the
        Monday 13 days later (an ``--end`` that says otherwise is refused). Capacity is the rule, 8.
        """
        active = q.active_sprint(self.brain)
        if active is not None:
            raise CommandError(f"sprint {active['number']} is active; close it first")
        service = self.brain.service(q.SPRINT)
        rows = q.sprints(self.brain)
        planned = [s for s in rows if s.get("status") == "Planned" and (number is None or s["number"] == number)]
        if number is not None and not planned:
            raise CommandError(f"no planned sprint number {number}")
        data: dict[str, Any] = {"status": "Active"}
        if phase:
            data["lifecycle_phase"] = pq.resolve_phase(self.brain, str(phase))
        target = planned[0]["number"] if planned else (max((s["number"] for s in rows), default=0) + 1)
        if start or not planned or not planned[0].get("start"):
            if start:
                first = q.parse_date(start, "start")
            else:
                first = self._follow_on(rows, target) or q.as_of_date(as_of)
            data["start"] = first.isoformat()
            last = q.parse_date(end, "end") if end else sprint_end(first)
            data["end"] = last.isoformat()
        if goal is not None:
            data["goal"] = goal
        if label:
            data["label"] = label
        if planned:
            row, warnings = self._activate(planned[0], data, actor)
        else:
            data.setdefault("number", target)
            data.setdefault("capacity", SPRINT_CAPACITY)
            data.setdefault("label", f"SPRINT {target}")
            if "lifecycle_phase" not in data and rows:
                data["lifecycle_phase"] = rows[-1].get("lifecycle_phase")
            row, warnings = service.create(data, actor)
        self.brain.events.publish("sprint.started", number=row["number"], actor=actor)
        return row, warnings

    def close(self, number: int | None = None, as_of: Any = None, actor: str = "python") -> dict[str, Any]:
        """Close the active sprint: Done stays, the rest is carried into the next sprint (opened now), Jira freezes."""
        with self.brain.schedule.deferred():  # the plan's deadlines move once, after the close
            return self._close(number, as_of, actor)

    def _close(self, number: int | None, as_of: Any, actor: str) -> dict[str, Any]:
        sprint = q.sprint_by_number(self.brain, number)
        if sprint.get("status") != "Active":
            raise CommandError(f"sprint {sprint['number']} is {sprint.get('status') or 'unset'}, not Active")
        day = q.as_of_date(as_of)
        items = q.items(self.brain, sprint["number"])
        carried = [r for r in items if r.get("status") not in ("Done", "Carried")]
        warnings: list[str] = []
        missing = [r for r in carried if not r.get("points")]
        if missing:
            warnings.append("carried without points: " + "; ".join(pq.one_line(r["title"], 60) for r in missing))
        self.brain.tracker.freeze_jira(sprint["number"], day, actor)
        target = self._next_sprint(sprint, day, actor)
        item_service = self.brain.service(q.ITEM)
        for row in carried:
            copy = {
                k: row.get(k) for k in ("kind", "title", "plan_row", "jira_key", "issue_type", "heading", "points",
                                        "target", "note", "jira_line", "order")
            }
            copy.update({"sprint": target["number"], "status": "To Do", "carried_from": sprint["number"]})
            item_service.create(copy, actor)
            item_service.update(row["id"], {"status": "Carried"}, actor)
        closed, _ = self.brain.service(q.SPRINT).update(
            sprint["id"], {"status": "Closed", "closed_on": day.isoformat()}, actor
        )
        summary = {
            "sprint": closed, "done": q.done(items), "carried": len(carried),
            "next": target["number"], "velocity": q.velocity(self.brain), "warnings": warnings,
        }
        self.brain.events.publish(
            "sprint.closed", number=closed["number"], done=summary["done"], carried=summary["carried"],
            next=summary["next"], velocity=summary["velocity"], actor=actor,
        )
        return summary

    def point(self, item_id: int, points: int | None, actor: str = "python") -> tuple[dict[str, Any], list[str]]:
        """Set (or with ``None`` clear) the points of an item; over-commitment is a warning, never a refusal."""
        service = self.brain.service(q.ITEM)
        row = service.get(int(item_id))
        sprint = q.sprint_by_number(self.brain, row["sprint"])
        capacity = q.capacity_of(sprint)
        if points is not None and not 1 <= int(points) <= capacity:
            raise CommandError(f"points must be between 1 and the sprint's capacity ({capacity}), not {points}")
        updated, warnings = service.update(row["id"], {"points": points}, actor)
        warnings.extend(q.board(self.brain, sprint)["warnings"])
        return updated, warnings

    def carry(self, item_id: int, to: int | None = None, actor: str = "python") -> dict[str, Any]:
        """Move one open item into sprint ``to`` (default the next one) now, leaving a Carried trace behind."""
        service = self.brain.service(q.ITEM)
        row = service.get(int(item_id))
        if row.get("status") in ("Done", "Carried"):
            raise CommandError(f"item {row['id']} is {row['status']}; only an open item is carried")
        source = q.sprint_by_number(self.brain, row["sprint"])
        target = q.sprint_by_number(self.brain, to) if to is not None else self._next_sprint(source, None, actor)
        copy = {
            k: row.get(k) for k in ("kind", "title", "plan_row", "jira_key", "issue_type", "heading", "points",
                                    "target", "note", "jira_line", "order")
        }
        copy.update({"sprint": target["number"], "status": "To Do", "carried_from": source["number"]})
        created, _ = service.create(copy, actor)
        service.update(row["id"], {"status": "Carried"}, actor)
        return created

    # -- the planner -------------------------------------------------------------------------
    def plan(
        self, *, until: Any = None, years: int | None = None, replan: bool = False, actor: str = "python",
    ) -> dict[str, Any]:
        """Extend the sprint chain to a horizon with empty Planned sprints, fourteen days each, Tuesday to Monday.

        The next sprint starts the day after the highest-numbered sprint's end and ends 13 days later;
        ``SPRINT <n>``, no lifecycle phase, capacity 8, Planned, the goal naming the holidays it contains (days
        off; they never move a sprint). Sprints are added while their start is on or before the horizon
        (``until``, else ``years`` years after the last end), so the last one may end after it; ``years``
        counts from the end of the last sprint that has started (Active or Closed), so a second run with the
        same horizon adds nothing. An existing sprint is never touched: a run adds what is missing up to the
        horizon. With ``replan`` the Planned sprints after the active one (after the last Closed one when none
        is active) are put back on the cadence first, each starting the day after the previous one ends;
        Active and Closed sprints are never touched, and a goal is rewritten only when it is empty or a
        ``Holidays:`` line the planner wrote.
        """
        with self.brain.schedule.deferred():  # the plan's deadlines move once, after the chain is planned
            return self._plan(until=until, years=years, replan=replan, actor=actor)

    def _plan(self, *, until: Any, years: int | None, replan: bool, actor: str) -> dict[str, Any]:
        span = PLAN_YEARS if years is None else int(years)
        if until is None and span < 1:
            raise CommandError(f"years must be 1 or more, not {span}")
        holidays = q.holiday_dates(self.brain)
        service = self.brain.service(q.SPRINT)
        rows = q.sprints(self.brain)
        if not rows:
            raise CommandError("no sprint to continue from; run `sprint start` first")
        touched: list[dict[str, Any]] = []
        replanned = 0
        span_start: dt.date | None = None  # the planned span: the holidays in it are the ones named
        with self.brain.storage.transaction():
            if replan:
                anchors = [r for r in rows if r.get("status") != "Planned"]
                anchor = anchors[-1] if anchors else None
                previous_end = q.parse_date(anchor["end"]) if anchor and anchor.get("end") else None
                span_start = previous_end
                after = anchor["number"] if anchor else None
                planned = [r for r in rows if r.get("status") == "Planned" and (after is None or r["number"] > after)]
                for row in planned:
                    if previous_end is not None:
                        start = previous_end + ONE_DAY
                    elif row.get("start"):
                        start = q.parse_date(row["start"])
                    else:
                        start = dt.date.today()
                    end = sprint_end(start)
                    delta: dict[str, Any] = {}
                    if row.get("start") != start.isoformat():
                        delta["start"] = start.isoformat()
                    if row.get("end") != end.isoformat():
                        delta["end"] = end.isoformat()
                    goal = row.get("goal") or ""
                    if not goal or goal.startswith(HOLIDAYS_GOAL):
                        wanted = holidays_goal(start, end, holidays)
                        if (wanted or None) != (goal or None):
                            delta["goal"] = wanted
                    if span_start is None:
                        span_start = start
                    if delta:
                        row, _ = service.update(row["id"], delta, actor)
                        replanned += 1
                        touched.append(row)
                    previous_end = end
                rows = q.sprints(self.brain)
            last = rows[-1]
            if not last.get("end"):
                raise CommandError(f"sprint {last['number']} has no end date; set it before planning")
            last_end = q.parse_date(last["end"])
            started = [r for r in rows if r.get("status") != "Planned" and r.get("end")]
            anchor_end = (
                q.parse_date(started[-1]["end"]) if started else q.parse_date(rows[0].get("start") or last["end"])
            )
            horizon = q.parse_date(until, "until") if until is not None else _years_after(anchor_end, span)
            if span_start is None:
                span_start = last_end
            number = int(last["number"])
            start = last_end + ONE_DAY
            added = 0
            while start <= horizon:
                number += 1
                end = sprint_end(start)
                goal = holidays_goal(start, end, holidays)
                row, _ = service.create({
                    "number": number, "label": f"SPRINT {number}", "start": start.isoformat(),
                    "end": end.isoformat(), "capacity": SPRINT_CAPACITY, "status": "Planned", "goal": goal,
                }, actor)
                touched.append(row)
                added += 1
                last = row
                start = end + ONE_DAY
        chain_end = q.parse_date(last["end"]) if last.get("end") else last_end
        inside = holidays_within(span_start + ONE_DAY, chain_end, holidays) if span_start else []
        summary = {
            "added": added, "replanned": replanned,
            "first": _brief(touched[0]) if touched else None, "last": _brief(last),
            "until": horizon.isoformat(), "length_days": SPRINT_LENGTH, "capacity": SPRINT_CAPACITY,
            "holidays": [f"{holidays[day]} ({day.isoformat()})" for day in inside],
        }
        self.brain.events.publish(
            "sprint.planned", added=added, replanned=replanned, until=summary["until"], actor=actor
        )
        return summary

    # -- the alignment (0.18.0) -------------------------------------------------------------------
    def align(self, number: int, start: Any, *, check: bool = False, actor: str = "python") -> dict[str, Any]:
        """Put an existing chain on the law: the sprint that starts on ``start`` (a Tuesday) becomes sprint
        ``number`` and every other sprint shifts by the same offset; ``SPRINT n`` labels follow; every sprint that
        is not Closed is re-dated onto the cadence (``number`` on ``start``, 14 days per step, before and after);
        every reference follows (``sprint_item.sprint`` and ``carried_from``, ``week.sprint``, the plan rows'
        ``sprint``); then the plan's schedule is recomputed. One transaction, one audit entry (``align``), one
        event (``sprint.aligned``); nothing is written and nothing is audited when the chain is already aligned,
        so a second run changes nothing. With ``check`` the mapping is computed and returned, nothing written.
        Refused when the date is not a Tuesday, when no sprint (or more than one) starts on it, when two sprints
        share a number, or when the shift would take a number below 1.
        """
        anchor_start = q.parse_date(start, "start")
        if anchor_start.weekday() != SPRINT_WEEKDAY:
            raise CommandError(
                f"{anchor_start.isoformat()} is a {anchor_start.strftime('%A')}, not a Tuesday: {CADENCE_RULE}"
            )
        rows = q.sprints(self.brain)
        if not rows:
            raise CommandError("no sprint to align; run `sprint start` first")
        numbers = [int(r["number"]) for r in rows]
        duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
        if duplicates:
            raise CommandError(
                "two sprints share a number: " + ", ".join(str(n) for n in duplicates) + "; fix that first"
            )
        anchors = [r for r in rows if r.get("start") and q.parse_date(r["start"]) == anchor_start]
        if not anchors:
            raise CommandError(f"no sprint starts on {anchor_start.isoformat()}")
        if len(anchors) > 1:
            raise CommandError(
                f"{len(anchors)} sprints start on {anchor_start.isoformat()}: "
                + ", ".join(str(r["number"]) for r in anchors)
            )
        offset = int(number) - int(anchors[0]["number"])
        lowest = min(numbers) + offset
        if lowest < 1:
            raise CommandError(f"sprint {min(numbers)} would become sprint {lowest}; numbers start at 1")
        mapping: list[dict[str, Any]] = []
        changes: dict[int, dict[str, Any]] = {}
        for row in rows:
            old, new = int(row["number"]), int(row["number"]) + offset
            delta: dict[str, Any] = {}
            if new != old:
                delta["number"] = new
            label = row.get("label") or ""
            found = _LABEL_NUMBER.match(label)
            new_label = f"{found['word']}{new}" if found and int(found["n"]) == old else (label or f"SPRINT {new}")
            if new_label != label:
                delta["label"] = new_label
            if row.get("status") != "Closed":
                first = cadence_start(new, int(number), anchor_start)
                last = sprint_end(first)
                if row.get("start") != first.isoformat():
                    delta["start"] = first.isoformat()
                if row.get("end") != last.isoformat():
                    delta["end"] = last.isoformat()
            if delta:
                changes[row["id"]] = delta
            after = {**row, **delta}
            mapping.append({
                "id": row["id"], "from": old, "to": new, "status": row.get("status"),
                "label": (label, after.get("label")), "start": (row.get("start"), after.get("start")),
                "end": (row.get("end"), after.get("end")),
                "changed": sorted(k for k in delta if k != "label"),
            })
        references = {f"{entity}.{column}": 0 for entity, column in REFERENCES}
        pointers: list[tuple[str, int, dict[str, Any]]] = []
        if offset:
            for entity, column in REFERENCES:
                for row in self.brain.service(entity).list():
                    if row.get(column) is not None:
                        pointers.append((entity, row["id"], {column: int(row[column]) + offset}))
                        references[f"{entity}.{column}"] += 1
        summary: dict[str, Any] = {
            "check": check, "number": int(number), "start": anchor_start.isoformat(), "offset": offset,
            "anchor": {"id": anchors[0]["id"], "from": int(anchors[0]["number"]), "to": int(number)},
            "sprints": len(rows), "renumbered": sum(1 for m in mapping if m["from"] != m["to"]),
            "redated": sum(1 for m in mapping if "start" in m["changed"] or "end" in m["changed"]),
            "references": references, "mapping": mapping, "scheduled": 0,
        }
        if check or not (changes or pointers):
            return summary
        with self.brain.storage.transaction():
            sprint_repo = self.brain.service(q.SPRINT).repo
            for row_id, delta in changes.items():
                sprint_repo.update(row_id, delta)
            for entity, row_id, delta in pointers:
                self.brain.service(entity).repo.update(row_id, delta)
            self.brain.storage.audit(actor, "align", q.SPRINT, None, {
                "number": int(number), "start": anchor_start.isoformat(), "offset": offset,
                "renumbered": summary["renumbered"], "redated": summary["redated"], "references": references,
                "mapping": {str(m["from"]): m["to"] for m in mapping},
            })
        summary["scheduled"] = self.brain.schedule.recompute(actor)["changed"]
        self.brain.events.publish(
            "sprint.aligned", number=int(number), start=anchor_start.isoformat(), offset=offset,
            renumbered=summary["renumbered"], redated=summary["redated"], actor=actor,
        )
        return summary

    # -- helpers ----------------------------------------------------------------------
    def _follow_on(self, rows: list[dict[str, Any]], number: int) -> dt.date | None:
        """The day after the end of the highest-numbered dated sprint below ``number``, or ``None``."""
        before = [r for r in rows if int(r["number"]) < int(number) and r.get("end")]
        return q.parse_date(before[-1]["end"]) + ONE_DAY if before else None

    def _activate(self, planned: dict[str, Any], data: dict[str, Any], actor: str) -> tuple[dict[str, Any], list[str]]:
        """Update a Planned sprint with ``data`` (status Active among it), filling the capacity and label it lacks."""
        if not planned.get("capacity"):
            data.setdefault("capacity", SPRINT_CAPACITY)
        if not planned.get("label"):
            data.setdefault("label", f"SPRINT {planned['number']}")
        return self.brain.service(q.SPRINT).update(planned["id"], data, actor)

    def _next_sprint(self, sprint: dict[str, Any], day: dt.date | None, actor: str) -> dict[str, Any]:
        """The lowest-numbered sprint after ``sprint``; created (Active) when there is none, following on in time:
        it starts the day after ``sprint``'s end and runs 14 days, Tuesday to Monday."""
        later = [s for s in q.sprints(self.brain) if s["number"] > sprint["number"]]
        if later:
            if day is not None and later[0].get("status") == "Planned":
                data = {"status": "Active"}
                if not later[0].get("start"):
                    first = q.parse_date(sprint["end"]) + ONE_DAY if sprint.get("end") else day
                    data["start"] = first.isoformat()
                    data["end"] = sprint_end(first).isoformat()
                later[0], _ = self._activate(later[0], data, actor)
            return later[0]
        start = q.parse_date(sprint["end"]) + ONE_DAY if sprint.get("end") else (day or dt.date.today())
        number = sprint["number"] + 1
        found = _LABEL_NUMBER.match(sprint.get("label") or "")
        label = f"{found['word']}{int(found['n']) + 1}" if found else f"SPRINT {number}"
        row, _ = self.brain.service(q.SPRINT).create({
            "number": number, "label": label, "lifecycle_phase": sprint.get("lifecycle_phase"),
            "start": start.isoformat(), "end": sprint_end(start).isoformat(),
            "capacity": SPRINT_CAPACITY, "status": "Active",
        }, actor)
        return row


def _years_after(day: dt.date, years: int) -> dt.date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:  # 29 February
        return day + dt.timedelta(days=365 * years)


def _brief(row: dict[str, Any]) -> dict[str, Any]:
    return {"number": row["number"], "start": row.get("start"), "end": row.get("end")}
