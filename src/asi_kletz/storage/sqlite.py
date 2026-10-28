"""SQLite backend: one file, no server, tables generated from the schema registry."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ..errors import StorageError
from ..schema import UID, FieldType, SchemaRegistry, new_uid
from ..version import __version__
from .base import Storage


def quote(identifier: str) -> str:
    """Quote an SQL identifier (field names such as ``order`` and ``end`` are keywords)."""
    return '"' + identifier.replace('"', '""') + '"'


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


class SQLiteStorage(Storage):
    backend = "sqlite"

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        try:
            self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open database {self.path!r}: {exc}") from exc
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._depth = 0

    # -- transactions ---------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._depth == 0:
            self.conn.execute("BEGIN")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("ROLLBACK")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self.conn.execute("COMMIT")

    # -- raw access -----------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        try:
            return self.conn.execute(sql, tuple(params))
        except sqlite3.Error as exc:
            raise StorageError(f"{exc} (sql: {sql.strip()[:120]})") from exc

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None:
        try:
            self.conn.executemany(sql, [tuple(r) for r in rows])
        except sqlite3.Error as exc:
            raise StorageError(f"{exc} (sql: {sql.strip()[:120]})") from exc

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        try:
            rows = self.conn.execute(sql, tuple(params)).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"{exc} (sql: {sql.strip()[:120]})") from exc
        return [dict(r) for r in rows]

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self.fetchall(sql + " LIMIT 1", params)
        return rows[0] if rows else None

    # -- schema ---------------------------------------------------------
    def ensure_schema(self, registry: SchemaRegistry) -> dict[str, Any]:
        created: list[str] = []
        altered: dict[str, list[str]] = {}
        with self.transaction():
            self.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version INTEGER PRIMARY KEY AUTOINCREMENT,"
                " fingerprint TEXT NOT NULL, applied_at TEXT NOT NULL, app_version TEXT)"
            )
            self.execute(
                "CREATE TABLE IF NOT EXISTS audit_log ("
                " id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,"
                " action TEXT NOT NULL, entity TEXT, entity_id INTEGER, payload TEXT)"
            )
            existing_tables = {
                r["name"] for r in self.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for schema in registry:
                cols = [f"{quote('id')} INTEGER PRIMARY KEY AUTOINCREMENT"]
                for spec in schema.fields:
                    cols.append(self._column_ddl(spec.name, spec.type))
                cols.append(f"{quote('created_at')} TEXT NOT NULL")
                cols.append(f"{quote('updated_at')} TEXT NOT NULL")
                if schema.table not in existing_tables:
                    self.execute(f"CREATE TABLE {quote(schema.table)} ({', '.join(cols)})")
                    created.append(schema.table)
                    continue
                present = {
                    r["name"] for r in self.fetchall(f"PRAGMA table_info({quote(schema.table)})")
                }
                for spec in schema.fields:
                    if spec.name not in present:
                        self.execute(
                            f"ALTER TABLE {quote(schema.table)} ADD COLUMN "
                            + self._column_ddl(spec.name, spec.type)
                        )
                        altered.setdefault(schema.table, []).append(spec.name)
            for schema in registry:  # the uid is unique per table; the index comes once the column exists
                if schema.has(UID):
                    self.execute(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {quote(f'ix_{schema.table}_uid')}"
                        f" ON {quote(schema.table)} ({quote(UID)})"
                    )
            fingerprint = registry.fingerprint()
            last = self.fetchone("SELECT fingerprint FROM schema_migrations ORDER BY version DESC")
            if last is None or last["fingerprint"] != fingerprint:
                self.execute(
                    "INSERT INTO schema_migrations (fingerprint, applied_at, app_version)"
                    " VALUES (?, ?, ?)",
                    (fingerprint, now_iso(), __version__),
                )
        return {"created": created, "altered": altered, "fingerprint": fingerprint}

    def stamp_uids(self, registry: SchemaRegistry) -> dict[str, int]:
        """Every row without a ``uid`` gets a fresh one: one ``UPDATE ... WHERE id = ?`` per row, all in one
        transaction, audited once per table that had rows to stamp (``stamp_uids``, with the count).

        A 0.8.x database therefore opens as 0.9.0 with every row identified and nothing else changed:
        ``updated_at`` is left alone, the row was not edited. A stamped database stamps nothing and
        leaves no audit entry behind.
        """
        counts: dict[str, int] = {}
        with self.transaction():
            for schema in registry:
                if not schema.has(UID):
                    continue
                table, column = quote(schema.table), quote(UID)
                rows = self.fetchall(f"SELECT id FROM {table} WHERE {column} IS NULL OR {column} = '' ORDER BY id")
                for row in rows:
                    self.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (new_uid(), row["id"]))
                counts[schema.name] = len(rows)
                if rows:
                    self.audit("system", "stamp_uids", schema.name, None, {"count": len(rows)})
        return counts

    @staticmethod
    def _column_ddl(name: str, kind: FieldType) -> str:
        if kind is FieldType.BOOL:
            return f"{quote(name)} INTEGER NOT NULL DEFAULT 0"
        if kind is FieldType.INT:
            return f"{quote(name)} INTEGER"
        return f"{quote(name)} TEXT"

    # -- audit ----------------------------------------------------------
    def audit(
        self,
        actor: str,
        action: str,
        entity: str | None = None,
        entity_id: int | None = None,
        payload: Any = None,
    ) -> None:
        text = None if payload is None else json.dumps(payload, ensure_ascii=False, default=str)
        self.execute(
            "INSERT INTO audit_log (ts, actor, action, entity, entity_id, payload)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (now_iso(), actor, action, entity, entity_id, text),
        )

    def audit_tail(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.fetchall(
            "SELECT id, ts, actor, action, entity, entity_id, payload FROM audit_log"
            " ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        for row in rows:
            if row.get("payload"):
                try:
                    row["payload"] = json.loads(row["payload"])
                except ValueError:
                    pass
        return rows

    def describe(self) -> dict[str, Any]:
        last = self.fetchone(
            "SELECT version, fingerprint, applied_at, app_version FROM schema_migrations"
            " ORDER BY version DESC"
        )
        return {
            "backend": self.backend,
            "path": self.path,
            "sqlite_version": sqlite3.sqlite_version,
            "schema_migration": last,
        }

    def close(self) -> None:
        self.conn.close()
