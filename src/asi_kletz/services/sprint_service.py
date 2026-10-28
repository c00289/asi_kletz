"""SprintService: the agile rules. A sprint is ten points; the tool sums, warns, closes and carries.

Every write goes through the entity services, so the audit log and the event bus see it like any
other change. ``close`` publishes ``sprint.closed`` with the numbers the dashboard shows.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..generate import plan_queries as pq
from ..generate import sprint_queries as q

if TYPE_CHECKING:
    from ..brain import Brain

_LABEL_NUMBER = re.compile(r"^(?P<word>.*?)(?P<n>\d+)\s*$")


class SprintService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- reads -------------------------------------------------------------------------
    def board(self, number: int | None = None, as_of: Any = None) -> dict[str, Any]:
        sprint = q.sprint_by_number(self.brain, number)
        return q.board(self.brain, sprint, q.as_of_date(as_of))

    # -- writes --------------------------------------------------------------------------
    def start(
        self, *, phase: str | None = None, start: Any = None, end: Any = None, capacity: int | None = None,
        goal: str | None = None, label: str | None = None, number: int | None = None, as_of: Any = None,
        actor: str = "python",
    ) -> tuple[dict[str, Any], list[str]]:
        """Open a sprint as Active: the Planned sprint ``number`` (or the next Planned one), else a new one."""
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
            last = q.parse_date(end, "end") if end else first + dt.timedelta(days=self.brain.sprint_days)
            data["end"] = last.isoformat()
        if capacity is not None:
            data["capacity"] = int(capacity)
        if goal is not None:
            data["goal"] = goal
        if label:
            data["label"] = label
        if planned:
            row, warnings = self._activate(planned[0], data, actor)
        else:
            next_number = (max((s["number"] for s in rows), default=0) + 1)
            data.setdefault("number", next_number)
            data.setdefault("capacity", self.brain.sprint_capacity)
            data.setdefault("label", f"SPRINT {next_number}")
            if "lifecycle_phase" not in data and rows:
                data["lifecycle_phase"] = rows[-1].get("lifecycle_phase")
            row, warnings = service.create(data, actor)
        self.brain.events.publish("sprint.started", number=row["number"], actor=actor)
        return row, warnings

    def close(self, number: int | None = None, as_of: Any = None, actor: str = "python") -> dict[str, Any]:
        """Close the active sprint: Done stays, the rest is carried into the next sprint (opened now), Jira freezes."""
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
        capacity = int(sprint.get("capacity") or self.brain.sprint_capacity)
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

    # -- helpers ----------------------------------------------------------------------
    def _activate(self, planned: dict[str, Any], data: dict[str, Any], actor: str) -> tuple[dict[str, Any], list[str]]:
        """Update a Planned sprint with ``data`` (status Active among it), filling the capacity and label it lacks."""
        if not planned.get("capacity"):
            data.setdefault("capacity", self.brain.sprint_capacity)
        if not planned.get("label"):
            data.setdefault("label", f"SPRINT {planned['number']}")
        return self.brain.service(q.SPRINT).update(planned["id"], data, actor)

    def _next_sprint(self, sprint: dict[str, Any], day: dt.date | None, actor: str) -> dict[str, Any]:
        """The lowest-numbered sprint after ``sprint``; created (Active) when there is none, following on in time."""
        later = [s for s in q.sprints(self.brain) if s["number"] > sprint["number"]]
        if later:
            if day is not None and later[0].get("status") == "Planned":
                first = q.parse_date(sprint["end"]) if sprint.get("end") else day
                data = {"status": "Active"}
                if not later[0].get("start"):
                    data["start"] = first.isoformat()
                    data["end"] = (first + dt.timedelta(days=self.brain.sprint_days)).isoformat()
                later[0], _ = self._activate(later[0], data, actor)
            return later[0]
        start = q.parse_date(sprint["end"]) if sprint.get("end") else (day or dt.date.today())
        length = self.brain.sprint_days
        if sprint.get("start") and sprint.get("end"):
            length = (q.parse_date(sprint["end"]) - q.parse_date(sprint["start"])).days or length
        number = sprint["number"] + 1
        found = _LABEL_NUMBER.match(sprint.get("label") or "")
        label = f"{found['word']}{int(found['n']) + 1}" if found else f"SPRINT {number}"
        row, _ = self.brain.service(q.SPRINT).create({
            "number": number, "label": label, "lifecycle_phase": sprint.get("lifecycle_phase"),
            "start": start.isoformat(), "end": (start + dt.timedelta(days=length)).isoformat(),
            "capacity": sprint.get("capacity") or self.brain.sprint_capacity, "status": "Active",
        }, actor)
        return row
