"""StorageFactory: backend name -> Storage instance."""

from __future__ import annotations

from typing import Any

from ..errors import NotFound
from .base import Storage
from .sqlite import SQLiteStorage


class StorageFactory:
    _backends: dict[str, type[Storage]] = {}

    @classmethod
    def register(cls, backend: type[Storage]) -> type[Storage]:
        cls._backends[backend.backend] = backend
        return backend

    @classmethod
    def create(cls, name: str = "sqlite", **options: Any) -> Storage:
        try:
            backend = cls._backends[name]
        except KeyError:
            raise NotFound(f"unknown storage backend {name!r}; known: {', '.join(cls._backends)}") from None
        return backend(**options)

    @classmethod
    def backends(cls) -> list[str]:
        return list(cls._backends)


StorageFactory.register(SQLiteStorage)
