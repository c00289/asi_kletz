"""SqlRepository: generic, schema-driven CRUD for one entity on an SQL storage."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..errors import CommandError
from ..schema import SYSTEM_FIELDS, EntitySchema, FieldType, coerce
from ..storage.base import Storage
from ..storage.sqlite import now_iso, quote


class SqlRepository:
    def __init__(self, schema: EntitySchema, storage: Storage) -> None:
        self.schema = schema
        self.storage = storage
        self.table = quote(schema.table)

    # -- encoding -------------------------------------------------------
    def _encode(self, name: str, value: Any) -> Any:
        if name in SYSTEM_FIELDS:
            return value
        spec = self.schema.field(name)
        if spec.type is FieldType.BOOL:
            return 1 if value else 0
        return value

    def _decode(self, row: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(row)
        for spec in self.schema.fields:
            if spec.type is FieldType.BOOL and spec.name in out:
                out[spec.name] = bool(out[spec.name])
        return out

    def _check_columns(self, names: Iterable[str]) -> None:
        bad = [n for n in names if not self.schema.has(n)]
        if bad:
            raise CommandError(f"{self.schema.name} has no field(s): {', '.join(bad)}")

    def _order_clause(self, order_by: str | Sequence[str] | None) -> str:
        if not order_by:
            keys: Sequence[str] = self.schema.order_by
        elif isinstance(order_by, str):
            keys = [k.strip() for k in order_by.split(",") if k.strip()]
        else:
            keys = list(order_by)
        parts = []
        for key in keys:
            desc = key.startswith("-")
            name = key.lstrip("-+")
            self._check_columns([name])
            parts.append(f"{quote(name)} {'DESC' if desc else 'ASC'} NULLS LAST")
        return " ORDER BY " + ", ".join(parts) if parts else ""

    def _where(self, filters: Mapping[str, Any] | None) -> tuple[str, list[Any]]:
        if not filters:
            return "", []
        self._check_columns(filters)
        clauses, params = [], []
        for name, value in filters.items():
            if name in SYSTEM_FIELDS:
                clean = int(value) if name == "id" else value
            else:
                clean, _ = coerce(self.schema.field(name), value)
            if clean is None:
                clauses.append(f"{quote(name)} IS NULL")
            else:
                clauses.append(f"{quote(name)} = ?")
                params.append(self._encode(name, clean))
        return " WHERE " + " AND ".join(clauses), params

    # -- reads ----------------------------------------------------------
    def get(self, row_id: int) -> dict[str, Any] | None:
        row = self.storage.fetchone(f"SELECT * FROM {self.table} WHERE id = ?", (int(row_id),))
        return self._decode(row) if row else None

    def list(
        self,
        filters: Mapping[str, Any] | None = None,
        order_by: str | Sequence[str] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        where, params = self._where(filters)
        sql = f"SELECT * FROM {self.table}{where}{self._order_clause(order_by)}"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset or 0)}"
        return [self._decode(r) for r in self.storage.fetchall(sql, params)]

    def count(self, filters: Mapping[str, Any] | None = None) -> int:
        where, params = self._where(filters)
        row = self.storage.fetchone(f"SELECT COUNT(*) AS n FROM {self.table}{where}", params)
        return int(row["n"]) if row else 0

    def exists(self, row_id: int) -> bool:
        return self.storage.fetchone(f"SELECT 1 AS x FROM {self.table} WHERE id = ?", (int(row_id),)) is not None

    # -- writes ---------------------------------------------------------
    def create(self, data: Mapping[str, Any], row_id: int | None = None) -> dict[str, Any]:
        self._check_columns(data)
        ts = now_iso()
        values = {name: self._encode(name, v) for name, v in data.items() if name not in SYSTEM_FIELDS}
        values["created_at"] = ts
        values["updated_at"] = ts
        if row_id is not None:
            values["id"] = int(row_id)
        cols = ", ".join(quote(c) for c in values)
        marks = ", ".join("?" for _ in values)
        cur = self.storage.execute(f"INSERT INTO {self.table} ({cols}) VALUES ({marks})", list(values.values()))
        new_id = row_id if row_id is not None else cur.lastrowid
        return self.get(int(new_id))  # type: ignore[return-value]

    def update(self, row_id: int, data: Mapping[str, Any]) -> dict[str, Any] | None:
        self._check_columns(data)
        values = {name: self._encode(name, v) for name, v in data.items() if name not in SYSTEM_FIELDS}
        if not values:
            return self.get(row_id)
        values["updated_at"] = now_iso()
        assignments = ", ".join(f"{quote(c)} = ?" for c in values)
        cur = self.storage.execute(
            f"UPDATE {self.table} SET {assignments} WHERE id = ?", [*values.values(), int(row_id)]
        )
        if cur.rowcount == 0:
            return None
        return self.get(row_id)

    def delete(self, row_id: int) -> bool:
        cur = self.storage.execute(f"DELETE FROM {self.table} WHERE id = ?", (int(row_id),))
        return cur.rowcount > 0

    def delete_all(self) -> int:
        cur = self.storage.execute(f"DELETE FROM {self.table}")
        return cur.rowcount

    def bulk_insert(self, rows: Sequence[Mapping[str, Any]], keep_ids: bool = False) -> list[int]:
        ids: list[int] = []
        with self.storage.transaction():
            for row in rows:
                row_id = row.get("id") if keep_ids else None
                created = self.create({k: v for k, v in row.items() if k not in SYSTEM_FIELDS}, row_id)
                ids.append(created["id"])
        return ids
