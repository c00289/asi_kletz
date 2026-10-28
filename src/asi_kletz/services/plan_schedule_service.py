"""PlanScheduleService: the calculated ``sprint`` and ``deadline`` of every Safety Plan row, kept current.

``recompute`` runs the pure scheduler (``generate/plan_schedule.py``) over the rows, the sprint chain and the
sprint items and writes the two calculated fields where they changed, through the repository (no guard, no
hook), audited once as ``schedule``. It runs after every change that can move the answer: the ``after`` hook
of the plan, sprint and sprint-item services, the deferred block around ``sprint close``, ``sprint plan`` and
``holiday load``, and once on open. ``guard`` keeps the calculated fields and the panel's defaults out of a
create or an update; ``load_weights`` sets the defaults from the panel's record.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, ValidationError
from ..generate import plan_queries as pq
from ..generate import sprint_queries as q
from ..generate.plan_schedule import SOURCE_DEFAULT, SOURCE_FLOOR, SOURCE_POINTS, schedule, weight_of
from ..schema import UID, normalise_uid
from ..schema.definitions import CALCULATED_RULE, DEFAULTS_RULE

if TYPE_CHECKING:
    from ..brain import Brain

PLAN = pq.PLAN_ENTITY
CALCULATED = ("sprint", "deadline")


class PlanScheduleService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self._running = False
        self._deferred = 0
        self._pending = False

    # -- the rule on the rows -------------------------------------------------------------
    def guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> None:
        """Before a create or an update of a plan row: the calculated fields and the panel's default are not
        written by hand; ``points`` is a positive integer or empty.

        A create's ``clean`` carries every field (``coerce_row`` fills the absent ones with ``None``), so a
        create is refused only for a value; an update's ``clean`` carries the fields given, so any presence.
        """
        given = (lambda name: clean.get(name) is not None) if current is None else (lambda name: name in clean)
        if any(given(name) for name in CALCULATED):
            raise ValidationError(PLAN, [CALCULATED_RULE])
        if given("default_points"):
            raise ValidationError(PLAN, [DEFAULTS_RULE])
        if clean.get("points") is not None and int(clean["points"]) < 1:
            raise ValidationError(PLAN, [f"points must be a positive integer, not {clean['points']}"])

    # -- when to recompute ------------------------------------------------------------------
    def on_change(self, action: str, row_id: int | None = None) -> None:
        """The ``after`` hook of the plan, sprint and sprint-item services."""
        if self._running:
            return
        if self._deferred:
            self._pending = True
            return
        self.recompute()

    @contextmanager
    def deferred(self) -> Iterator[None]:
        """Hold the hook for a run of writes (a close, a plan, a load) and recompute once at the end."""
        self._deferred += 1
        try:
            yield
        finally:
            self._deferred -= 1
            if self._deferred == 0 and self._pending:
                self._pending = False
                self.recompute()

    # -- the recompute ------------------------------------------------------------------------
    def recompute(self, actor: str = "system") -> dict[str, Any]:
        """Write ``sprint`` and ``deadline`` on the rows where they changed; audited once; ``plan.scheduled``."""
        if self._running:
            return {"changed": 0, "rows": 0, "warnings": [], "unscheduled": []}
        self._running = True
        try:
            rows = pq.all_rows(self.brain)
            result = schedule(rows, q.sprints(self.brain), self.brain.service(q.ITEM).list(), self.brain.default_points)
            repo = self.brain.service(PLAN).repo
            changed = 0
            with self.brain.storage.transaction():
                for row in rows:
                    if row["id"] not in result.assignments:
                        continue
                    number, deadline = result.assignments[row["id"]]
                    if (row.get("sprint"), row.get("deadline")) != (number, deadline):
                        repo.update(row["id"], {"sprint": number, "deadline": deadline})
                        changed += 1
                if changed:
                    self.brain.storage.audit(
                        actor, "schedule", PLAN, None, {"count": changed, "warnings": list(result.warnings)}
                    )
            if changed:
                self.brain.events.publish(
                    "plan.scheduled", changed=changed, warnings=len(result.warnings), actor=actor
                )
            unscheduled = [rid for rid, (number, _) in result.assignments.items() if number is None]
            return {
                "changed": changed, "rows": len(rows), "warnings": list(result.warnings), "unscheduled": unscheduled,
            }
        finally:
            self._running = False

    def table(self) -> list[dict[str, Any]]:
        """One line per deliverable in plan order: the points, the weight and its source, the sprint, the deadline."""
        rows = pq.all_rows(self.brain)
        result = schedule(rows, q.sprints(self.brain), self.brain.service(q.ITEM).list(), self.brain.default_points)
        out = []
        for row in rows:
            weight, source = weight_of(row, self.brain.default_points)
            source = result.sources.get(row["id"], source)
            if source not in (SOURCE_POINTS, SOURCE_DEFAULT, SOURCE_FLOOR):
                weight = 0
            out.append({
                "id": row["id"], "order": row.get("order"),
                "deliverable": pq.one_line(row.get("deliverable") or "", 60),
                "points": row.get("points"), "default_points": row.get("default_points"), "weight": weight,
                "source": source, "sprint": row.get("sprint"), "deadline": row.get("deadline"),
                "status": row.get("status"),
            })
        return out

    # -- the panel's defaults ------------------------------------------------------------------
    def load_weights(self, path: str | Path, actor: str = "python") -> dict[str, Any]:
        """Set ``default_points`` from a JSON list of ``{id, order, deliverable, points[, uid]}``: a row is
        matched by uid when the file has one, else by id; written through the repository, audited once."""
        file = Path(path)
        if not file.is_file():
            raise CommandError(f"no such file: {file}")
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CommandError(f"{file.name} is not JSON: {exc}") from None
        if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            payload = payload["rows"]
        if not isinstance(payload, list):
            raise CommandError(f"{file.name} must hold a JSON list of {{id, order, deliverable, points}}")
        service = self.brain.service(PLAN)
        by_id = {r["id"]: r for r in service.list()}
        by_uid = {r[UID]: r for r in by_id.values() if r.get(UID)}
        counts = {"set": 0, "unchanged": 0}
        unmatched: list[str] = []
        with self.brain.storage.transaction():
            for index, raw in enumerate(payload, start=1):
                if not isinstance(raw, dict) or raw.get("points") in (None, ""):
                    raise CommandError(f"{file.name}: row {index} needs points")
                try:
                    points = int(raw["points"])
                except (TypeError, ValueError):
                    raise CommandError(f"{file.name}: row {index}: {raw['points']!r} is not an integer") from None
                if points < 1:
                    raise CommandError(f"{file.name}: row {index}: points must be a positive integer")
                row = None
                uid = normalise_uid(raw["uid"]) if raw.get("uid") else None
                if uid:
                    row = by_uid.get(uid)
                elif raw.get("id") is not None:
                    row = by_id.get(int(raw["id"]))
                if row is None:
                    unmatched.append(str(raw.get("uid") or raw.get("id") or f"row {index}"))
                    continue
                if row.get("default_points") == points:
                    counts["unchanged"] += 1
                    continue
                service.repo.update(row["id"], {"default_points": points})
                counts["set"] += 1
            if counts["set"]:
                self.brain.storage.audit(actor, "weights", PLAN, None, {**counts, "unmatched": len(unmatched)})
        schedule_result = self.recompute(actor)
        return {
            "path": str(file), "rows": len(payload), **counts, "unmatched": unmatched,
            "scheduled": schedule_result["changed"], "warnings": schedule_result["warnings"],
        }
