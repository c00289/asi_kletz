"""HolidayService: the holidays the sprint planner skips, loaded from a JSON list by date and name.

``load`` reads ``[{"date", "name", "status"[, "note"]}, ...]`` (or ``{"holidays": [...]}``) and upserts: a
row matching on date and name is updated with the fields the file carries (``unchanged`` when nothing
differs), a missing one is created. The whole file is validated first; a bad row stops the load before
anything is written. Writes go through the entity service, so the audit log and the event bus see them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, ValidationError
from ..generate import sprint_queries as q

if TYPE_CHECKING:
    from ..brain import Brain

FIELDS = ("date", "name", "status", "note")


class HolidayService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    def load(self, path: str | Path, actor: str = "python") -> dict[str, Any]:
        file = Path(path)
        if not file.is_file():
            raise CommandError(f"no such file: {file}")
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CommandError(f"{file.name} is not JSON: {exc}") from None
        if isinstance(payload, dict) and isinstance(payload.get("holidays"), list):
            payload = payload["holidays"]
        if not isinstance(payload, list):
            raise CommandError(f"{file.name} must hold a JSON list of holidays (date, name, status)")
        service = self.brain.service(q.HOLIDAY)
        rows: list[dict[str, Any]] = []
        for index, raw in enumerate(payload, start=1):
            if not isinstance(raw, dict):
                raise CommandError(f"{file.name}: holiday {index} is not an object")
            data = {k: raw.get(k) for k in FIELDS if k in raw}
            try:
                clean, _ = service.schema.coerce_row(data, self.brain.lookups, partial=True)
            except ValidationError as exc:
                raise CommandError(f"{file.name}: holiday {index}: {'; '.join(exc.errors)}") from None
            if not clean.get("date") or not clean.get("name"):
                raise CommandError(f"{file.name}: holiday {index} needs a date and a name")
            rows.append(clean)
        existing = {(r["date"], r["name"]): r for r in service.list()}
        counts = {"inserted": 0, "updated": 0, "unchanged": 0}
        with self.brain.storage.transaction():
            for clean in rows:
                current = existing.get((clean["date"], clean["name"]))
                if current is None:
                    created, _ = service.create(clean, actor)
                    existing[(clean["date"], clean["name"])] = created
                    counts["inserted"] += 1
                    continue
                delta = {k: v for k, v in clean.items() if current.get(k) != v}
                if delta:
                    service.update(current["id"], delta, actor)
                    counts["updated"] += 1
                else:
                    counts["unchanged"] += 1
        return {"path": str(file), "rows": len(rows), **counts, "holidays": service.count()}
