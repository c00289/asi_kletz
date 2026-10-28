"""Abstract storage interface. A backend knows tables, transactions, and auditing."""

from __future__ import annotations

import abc
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, ClassVar

from ..schema import SchemaRegistry


class Storage(abc.ABC):
    backend: ClassVar[str] = "abstract"

    @abc.abstractmethod
    def ensure_schema(self, registry: SchemaRegistry) -> dict[str, Any]:
        """Create or migrate tables for every entity. Returns a summary."""

    @abc.abstractmethod
    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Nestable transaction: commits when the outermost block exits cleanly."""

    @abc.abstractmethod
    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any: ...

    @abc.abstractmethod
    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> None: ...

    @abc.abstractmethod
    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None: ...

    @abc.abstractmethod
    def audit(
        self,
        actor: str,
        action: str,
        entity: str | None = None,
        entity_id: int | None = None,
        payload: Any = None,
    ) -> None: ...

    @abc.abstractmethod
    def audit_tail(self, limit: int = 20) -> list[dict[str, Any]]: ...

    @abc.abstractmethod
    def describe(self) -> dict[str, Any]: ...

    @abc.abstractmethod
    def close(self) -> None: ...
