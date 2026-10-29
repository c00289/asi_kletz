"""EntityService: validated CRUD for one entity, with audit log and events."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from ..automation.events import EventBus
from ..errors import CommandError, NotFound, ValidationError
from ..repositories.sql_repo import SqlRepository
from ..schema import UID, EntitySchema, LookupRegistry, new_uid, normalise_uid
from ..storage.base import Storage

LOAD_MODES = ("replace", "merge", "append")
UID_IMMUTABLE = "uid is immutable"


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
        # an entity's own rule, run after coercion and before the write: ``guard(current_row_or_None, clean)``
        # may fill ``clean`` or raise ``ValidationError`` (the sprint's capacity rule; ``Brain.service`` sets it)
        self.guard: Callable[[dict[str, Any] | None, dict[str, Any]], None] | None = None
        # a hook run once after a committed create, update, delete or load: ``after(action, row_id)`` (the
        # plan's recompute; ``Brain.service`` sets it on the plan, sprint and sprint-item services)
        self.after: Callable[[str, int | None], None] | None = None

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

    def get(self, ref: int | str) -> dict[str, Any]:
        row = self.repo.get(self.resolve(ref))
        if row is None:
            raise NotFound(f"{self.schema.name} {ref} not found")
        return row

    def get_by_uid(self, uid: str) -> dict[str, Any]:
        """The row carrying ``uid``; ``NotFound`` when no row does (or the value is not a uid)."""
        clean = normalise_uid(uid)
        row = self.repo.get_by_uid(clean) if clean else None
        if row is None:
            raise NotFound(f"{self.schema.name} with uid {uid!r} not found")
        return row

    def resolve(self, ref: int | str) -> int:
        """The id behind a ``ref``: an integer (or a string of digits) is an id; a uid is looked up
        (``NotFound`` when no row carries it); anything else is a ``CommandError``.
        """
        if isinstance(ref, bool):
            raise CommandError(f"{ref!r} is neither an id nor a uid")
        if isinstance(ref, int):
            return ref
        text = str(ref).strip()
        if text.isdigit():
            return int(text)
        if normalise_uid(text) is not None:
            return int(self.get_by_uid(text)["id"])
        raise CommandError(f"{text!r} is neither an id nor a uid")

    # -- writes ---------------------------------------------------------
    def create(self, data: Mapping[str, Any], actor: str = "python") -> tuple[dict[str, Any], list[str]]:
        clean, warnings = self.schema.coerce_row(data, self.lookups)
        if self.guard is not None:
            self.guard(None, clean)
        if self.schema.has(UID) and not clean.get(UID):  # assigned once, here; a uid handed in is kept
            clean[UID] = new_uid()
        with self.storage.transaction():
            row = self.repo.create(clean)
            self.storage.audit(actor, "create", self.schema.name, row["id"], clean)
        self.events.publish("entity.created", entity=self.schema.name, id=row["id"], actor=actor, row=row)
        if self.after is not None:
            self.after("create", row["id"])
        return row, warnings

    def update(
        self, ref: int | str, data: Mapping[str, Any], actor: str = "python"
    ) -> tuple[dict[str, Any], list[str]]:
        row_id = self.resolve(ref)
        clean, warnings = self.schema.coerce_row(data, self.lookups, partial=True)
        if self.guard is not None:
            current = self.repo.get(row_id)
            if current is None:
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.guard(current, clean)
        with self.storage.transaction():
            if UID in clean:
                clean = self._check_uid(row_id, clean)
            row = self.repo.update(row_id, clean)
            if row is None:
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.storage.audit(actor, "update", self.schema.name, row_id, clean)
        self.events.publish("entity.updated", entity=self.schema.name, id=row_id, actor=actor, row=row)
        if self.after is not None:
            self.after("update", row_id)
        return row, warnings

    def _check_uid(self, row_id: int, clean: dict[str, Any]) -> dict[str, Any]:
        """A ``uid`` in an update is immutable: the stored value is a no-op, another one a ``ValidationError``;
        an empty one (a form or a file that does not carry it) leaves the stored value alone."""
        current = self.repo.get(row_id)
        if current is None:
            raise NotFound(f"{self.schema.name} {row_id} not found")
        clean = dict(clean)
        if clean[UID] in (None, "") or clean[UID] == current.get(UID):
            del clean[UID]
        else:
            raise ValidationError(self.schema.name, [UID_IMMUTABLE])
        return clean

    def delete(self, ref: int | str, actor: str = "python") -> int:
        """Delete the row behind ``ref``; returns its id."""
        row_id = self.resolve(ref)
        with self.storage.transaction():
            if not self.repo.delete(row_id):
                raise NotFound(f"{self.schema.name} {row_id} not found")
            self.storage.audit(actor, "delete", self.schema.name, row_id)
        self.events.publish("entity.deleted", entity=self.schema.name, id=row_id, actor=actor)
        if self.after is not None:
            self.after("delete", row_id)
        return row_id

    def load_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        mode: str = "merge",
        actor: str = "import",
    ) -> dict[str, Any]:
        """Bulk load. ``replace`` wipes first; ``merge`` upserts by id; ``append`` inserts fresh ids.

        The uid comes first (section 3.1 of docs/hidden-identity-plan.md): a row whose ``uid`` exists in
        the table updates that row, whatever its ``id`` in the file, in every mode; otherwise a row whose
        ``id`` exists updates by id (merge only, as before; the file's uid, when it has one, replaces the
        stored one, which is how a sibling's cached rows take this tool's uids); otherwise the row is
        inserted keeping the file's uid when present (every mode) and the file's id in merge mode. A row
        without a uid (a 0.8.x file) keeps the stored uid on an update and gets a fresh one on an insert.
        A calculated field (the plan's ``sprint`` and ``deadline``, 0.11.0) is never taken from the file on a
        row that is not Done: the tool recomputes it after the load (the ``after`` hook) and the importer
        warns once, through ``calculated_warning``, when the file's values differed; a Done row keeps the
        file's values, they are history.
        Rows are validated one by one; a bad row is reported and skipped, never fatal.
        """
        if mode not in LOAD_MODES:
            raise CommandError(f"mode must be one of {', '.join(LOAD_MODES)}, not {mode!r}")
        summary: dict[str, Any] = {
            "entity": self.schema.name, "mode": mode,
            "inserted": 0, "updated": 0, "deleted": 0, "skipped": 0,
            "warnings": [], "errors": [],
        }
        has_uid = self.schema.has(UID)
        calculated = self.schema.calculated_fields  # the file's values are ignored: the tool computes them
        carried: list[tuple[int, dict[str, Any]]] = []  # (row id, the file's calculated values) to warn about
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
                if calculated and clean.get("status") == "Done":
                    ignored = {}  # the past keeps what the file says (a free-text deadline is history)
                else:
                    ignored = {s.name: clean.pop(s.name) for s in calculated if clean.get(s.name) not in (None, "")}
                    for spec in calculated:
                        clean.pop(spec.name, None)
                row_id = raw.get("id")
                uid = clean.get(UID) if has_uid else None
                by_uid = self.repo.get_by_uid(uid) if uid else None
                if by_uid is not None:
                    self.repo.update(int(by_uid["id"]), clean)
                    summary["updated"] += 1
                    written = int(by_uid["id"])
                elif mode == "merge" and row_id is not None and self.repo.exists(int(row_id)):
                    if has_uid and not uid:
                        del clean[UID]  # the file does not carry it: the stored uid stays
                    self.repo.update(int(row_id), clean)
                    summary["updated"] += 1
                    written = int(row_id)
                else:
                    keep = int(row_id) if (mode == "merge" and row_id is not None) else None
                    if has_uid and not uid:
                        clean[UID] = new_uid()
                    written = int(self.repo.create(clean, keep)["id"])
                    summary["inserted"] += 1
                if ignored:
                    carried.append((written, ignored))
            summary["ignored"] = carried  # the importer compares them once every entity is loaded and recomputed
            self.storage.audit(
                actor, f"load:{mode}", self.schema.name, None,
                {k: summary[k] for k in ("inserted", "updated", "deleted", "skipped")},
            )
        self.events.publish("entity.loaded", entity=self.schema.name, actor=actor, summary=summary)
        if self.after is not None:
            self.after("load", None)
        return summary

    def calculated_warning(self, summary: dict[str, Any]) -> str | None:
        """After the load and its recompute: one line when rows carried a calculated value that differs from
        the stored (calculated) one, or ``None``."""
        differing = 0
        for written, ignored in summary.get("ignored", ()):
            row = self.repo.get(written) or {}
            if any(str(row.get(k) or "") != str(v) for k, v in ignored.items()):
                differing += 1
        if not differing:
            return None
        words = [s.name.replace("_", " ") for s in self.schema.calculated_fields]
        names = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]
        return (
            f"{differing} row(s) carried a {names} that differs from the calculated value; "
            "the file's values were ignored"
        )
