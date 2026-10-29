"""SprintService: the agile rules. A sprint is eight points and ten business days; the tool sums, warns,
closes, carries and plans the chain ahead.

The owner's rule (2026-10-28, ``docs/sprint-planner-plan.md``): a sprint spans 10 business days (Monday to
Friday count; weekends and holidays do not, so a sprint that contains a holiday ends one calendar day later
per holiday; dates move as holidays become real, the cadence does not); capacity is 8 points per sprint,
company policy (8 productive days of the 10; holidays never reduce points); sprints are consecutive with no
gaps, numbered across the programme (SPRINT n). And: "every single sprint except the one in the past is 8
points; set this as a global value that is fixed." So ``SPRINT_CAPACITY`` is enforced here: ``guard`` on
every create and update of a sprint, ``enforce_capacity`` on every open; a Closed sprint is the past and
keeps its stored capacity as history.

Every write goes through the entity services, so the audit log and the event bus see it like any other
change. ``close`` publishes ``sprint.closed`` with the numbers the dashboard shows; ``plan`` publishes
``sprint.planned``.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, ValidationError
from ..generate import plan_queries as pq
from ..generate import sprint_queries as q
from ..schema import normalise_uid
from ..schema.definitions import CAPACITY_RULE, SPRINT_CAPACITY
from ..tracker.business_days import add_business_days, holidays_within, next_business_day

if TYPE_CHECKING:
    from ..brain import Brain

_LABEL_NUMBER = re.compile(r"^(?P<word>.*?)(?P<n>\d+)\s*$")
HOLIDAYS_GOAL = "Holidays: "  # the goal the planner writes when a sprint contains holidays; never a human's
PLAN_YEARS = 3


def holidays_goal(start: dt.date, end: dt.date, holidays: dict[dt.date, str]) -> str | None:
    """``Holidays: <name> (<m/d>), ...`` for the holidays inside ``[start, end]``, or ``None`` when there are none."""
    within = holidays_within(start, end, holidays)
    if not within:
        return None
    return HOLIDAYS_GOAL + ", ".join(f"{holidays[day]} ({day.month}/{day.day})" for day in within)


class SprintService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- the capacity rule -----------------------------------------------------------------
    def guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> None:
        """The check the ``sprint`` entity service runs before a create (``current`` is None) or an update.

        A sprint that is not Closed has capacity 8: a create without one gets it, a create or an update with
        another value is refused with the rule's text. A Closed sprint's capacity is history and may be edited.
        """
        status = clean.get("status", (current or {}).get("status"))
        if status == "Closed":
            return
        if current is None and clean.get("capacity") is None:
            clean["capacity"] = SPRINT_CAPACITY
        if "capacity" in clean and clean["capacity"] not in (None, SPRINT_CAPACITY):
            raise ValidationError(q.SPRINT, [CAPACITY_RULE])

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

        The first day is ``--start``, else ``--as-of``, else today, kept as given; the default last day is
        the sprint's ``sprint_days``th business day over the holiday table. Capacity is the rule, 8.
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
        first = q.parse_date(start, "start") if start else (q.as_of_date(as_of))
        if start or not planned or not planned[0].get("start"):
            data["start"] = first.isoformat()
            last = q.parse_date(end, "end") if end else self._end_of(first)
            data["end"] = last.isoformat()
        if goal is not None:
            data["goal"] = goal
        if label:
            data["label"] = label
        if planned:
            row, warnings = self._activate(planned[0], data, actor)
        else:
            next_number = (max((s["number"] for s in rows), default=0) + 1)
            data.setdefault("number", next_number)
            data.setdefault("capacity", SPRINT_CAPACITY)
            data.setdefault("label", f"SPRINT {next_number}")
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
        self, *, until: Any = None, years: int | None = None, days: int | None = None, replan: bool = False,
        actor: str = "python",
    ) -> dict[str, Any]:
        """Extend the sprint chain to a horizon with empty Planned sprints, ten business days each.

        The next sprint starts on the first business day after the highest-numbered sprint's end and ends on
        its ``days``th business day (holidays skipped, so the calendar span grows); ``SPRINT <n>``, no
        lifecycle phase, capacity 8, Planned, the goal naming the holidays it contains. Sprints are added while
        their start is on or before the horizon (``until``, else ``years`` years after the last end), so the
        last one may end after it; ``years`` counts from the end of the last sprint that has started (Active
        or Closed), so a second run with the same horizon adds nothing. An existing sprint is never touched:
        a run adds what is missing up to the horizon. With ``replan`` the Planned sprints after the
        active one (after the last Closed one when none is active) get their dates recomputed first from the
        holiday table as it is now; Active and Closed sprints are never touched, and a goal is rewritten only
        when it is empty or a ``Holidays:`` line the planner wrote.
        """
        with self.brain.schedule.deferred():  # the plan's deadlines move once, after the chain is planned
            return self._plan(until=until, years=years, days=days, replan=replan, actor=actor)

    def _plan(
        self, *, until: Any, years: int | None, days: int | None, replan: bool, actor: str
    ) -> dict[str, Any]:
        length = int(self.brain.sprint_days if days is None else days)
        if length < 1:
            raise CommandError(f"days must be 1 or more, not {length}")
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
        span_start: dt.date | None = None  # the planned span: the holidays in it are the ones honoured
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
                        start = next_business_day(previous_end, holidays)
                    elif row.get("start"):
                        start = add_business_days(q.parse_date(row["start"]), 0, holidays)
                    else:
                        start = add_business_days(dt.date.today(), 0, holidays)
                    end = add_business_days(start, length - 1, holidays)
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
            start = next_business_day(last_end, holidays)
            added = 0
            while start <= horizon:
                number += 1
                end = add_business_days(start, length - 1, holidays)
                goal = holidays_goal(start, end, holidays)
                row, _ = service.create({
                    "number": number, "label": f"SPRINT {number}", "start": start.isoformat(),
                    "end": end.isoformat(), "capacity": SPRINT_CAPACITY, "status": "Planned", "goal": goal,
                }, actor)
                touched.append(row)
                added += 1
                last = row
                start = next_business_day(end, holidays)
        chain_end = q.parse_date(last["end"]) if last.get("end") else last_end
        honoured = holidays_within(span_start + dt.timedelta(days=1), chain_end, holidays) if span_start else []
        summary = {
            "added": added, "replanned": replanned,
            "first": _brief(touched[0]) if touched else None, "last": _brief(last),
            "until": horizon.isoformat(), "days": length, "capacity": SPRINT_CAPACITY,
            "holidays": [f"{holidays[day]} ({day.isoformat()})" for day in honoured],
        }
        self.brain.events.publish(
            "sprint.planned", added=added, replanned=replanned, until=summary["until"], actor=actor
        )
        return summary

    # -- helpers ----------------------------------------------------------------------
    def _end_of(self, first: dt.date) -> dt.date:
        """The last day of a sprint that starts on ``first``: its ``sprint_days``th business day."""
        return add_business_days(first, max(1, self.brain.sprint_days) - 1, q.holiday_dates(self.brain))

    def _activate(self, planned: dict[str, Any], data: dict[str, Any], actor: str) -> tuple[dict[str, Any], list[str]]:
        """Update a Planned sprint with ``data`` (status Active among it), filling the capacity and label it lacks."""
        if not planned.get("capacity"):
            data.setdefault("capacity", SPRINT_CAPACITY)
        if not planned.get("label"):
            data.setdefault("label", f"SPRINT {planned['number']}")
        return self.brain.service(q.SPRINT).update(planned["id"], data, actor)

    def _next_sprint(self, sprint: dict[str, Any], day: dt.date | None, actor: str) -> dict[str, Any]:
        """The lowest-numbered sprint after ``sprint``; created (Active) when there is none, following on in time:
        it starts on the first business day after ``sprint``'s end and runs ``sprint_days`` business days."""
        later = [s for s in q.sprints(self.brain) if s["number"] > sprint["number"]]
        holidays = q.holiday_dates(self.brain)
        if later:
            if day is not None and later[0].get("status") == "Planned":
                data = {"status": "Active"}
                if not later[0].get("start"):
                    first = next_business_day(q.parse_date(sprint["end"]), holidays) if sprint.get("end") else day
                    data["start"] = first.isoformat()
                    data["end"] = self._end_of(first).isoformat()
                later[0], _ = self._activate(later[0], data, actor)
            return later[0]
        if sprint.get("end"):
            start = next_business_day(q.parse_date(sprint["end"]), holidays)
        else:
            start = add_business_days(day or dt.date.today(), 0, holidays)
        number = sprint["number"] + 1
        found = _LABEL_NUMBER.match(sprint.get("label") or "")
        label = f"{found['word']}{int(found['n']) + 1}" if found else f"SPRINT {number}"
        row, _ = self.brain.service(q.SPRINT).create({
            "number": number, "label": label, "lifecycle_phase": sprint.get("lifecycle_phase"),
            "start": start.isoformat(), "end": self._end_of(start).isoformat(),
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
