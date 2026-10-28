"""EntityService: validated CRUD for one entity, with audit log and events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..automation.events import EventBus
from ..errors import CommandError, NotFound
from ..repositories.sql_repo import SqlRepository
from ..schema import EntitySchema, LookupRegistry
from ..storage.base import Storage

LOAD_MODES = ("replace", "merge", "append")


class EntityService:
    def __init__(
        self,
        schema: EntitySchema,
        repository: SqlRepository,
        storage: Storage,
        lookups: LookupRegistry,
        events: EventBus,
    ) -> None:
        self.schema = schema
        self.repo = repository
        self.storage = storage
        self.lookups = lookups
        self.events = events

    # -- reads ----------------------------------------------------------
    def list(
        self,
        filters: Mapping[str, Any] | None = None,
        order_by: str | Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.repo.list(filters, order_by, limit, offset)

    def count(self, filters: Mapping[str, Any] | None = None) -> int:
        return self.repo.count(filters)

    def get(self, row_id: int) -> dict[str, Any]:
        row = self.repo.get(row_id)
        if row is None:
            raise NotFound(f"{self.schema.name} {row_id} not found")
        return row

    # -- writes ---------------------------------------------------------
    def create(self, data: Mapping[str, Any], actor: str = "python") -> tuple[dict[str, Any], list[str]]:
        clean, warnings = self.schema.coerce_row(data, self.lookups)
        with self.storage.transaction():
            row = self.repo.create(clean)
            self.storage.audit(actor, "create", self.schema.name, row["id"], clean)
        self.events.publish("entity.created", entity=self.schema.name, id=row["id"], actor=actor, row=row)
        return row, warnings

    def update(
        self, row_id: int, data: Mapping[str, Any], actor: str = "python"
    ) -> tuple[dict[str, Any], list[str]]:
        clean, warnings = self.schema.coerce_row(data, self.lookups, partial=True)
        with self.storage.transaction():
            row = self.repo.update(row_id, clean)
            if row is None:
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.storage.audit(actor, "update", self.schema.name, row_id, clean)
        self.events.publish("entity.updated", entity=self.schema.name, id=row_id, actor=actor, row=row)
        return row, warnings

    def delete(self, row_id: int, actor: str = "python") -> None:
        with self.storage.transaction():
            if not self.repo.delete(row_id):
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.storage.audit(actor, "delete", self.schema.name, row_id)
        self.events.publish("entity.deleted", entity=self.schema.name, id=row_id, actor=actor)

    def load_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        mode: str = "merge",
        actor: str = "import",
    ) -> dict[str, Any]:
        """Bulk load. ``replace`` wipes first; ``merge`` upserts by id; ``append`` inserts fresh ids.

        Rows are validated one by one; a bad row is reported and skipped, never fatal.
        """
        if mode not in LOAD_MODES:
            raise CommandError(f"mode must be one of {', '.join(LOAD_MODES)}, not {mode!r}")
        summary: dict[str, Any] = {
            "entity": self.schema.name, "mode": mode,
            "inserted": 0, "updated": 0, "deleted": 0, "skipped": 0,
            "warnings": [], "errors": [],
        }
        with self.storage.transaction():
            if mode == "replace":
                summary["deleted"] = self.repo.delete_all()
            for index, raw in enumerate(rows, start=1):
                try:
                    clean, warnings = self.schema.coerce_row(
                        {k: v for k, v in raw.items() if k != "id"}, self.lookups
                    )
                except Exception as exc:  # ValidationError or anything odd in a row
                    summary["errors"].append(f"row {index}: {exc}")
                    summary["skipped"] += 1
                    continue
                summary["warnings"].extend(f"row {index}: {w}" for w in warnings)
                row_id = raw.get("id")
                if mode == "merge" and row_id is not None and self.repo.exists(int(row_id)):
                    self.repo.update(int(row_id), clean)
                    summary["updated"] += 1
                else:
                    keep = int(row_id) if (mode == "merge" and row_id is not None) else None
                    self.repo.create(clean, keep)
                    summary["inserted"] += 1
            self.storage.audit(
                actor, f"load:{mode}", self.schema.name, None,
                {k: summary[k] for k in ("inserted", "updated", "deleted", "skipped")},
            )
        self.events.publish("entity.loaded", entity=self.schema.name, actor=actor, summary=summary)
        return summary
