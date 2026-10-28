"""RepositoryFactory: entity name -> repository bound to the active storage backend."""

from __future__ import annotations

from ..errors import NotFound
from ..schema import EntitySchema, SchemaRegistry
from ..storage.base import Storage
from .sql_repo import SqlRepository


class RepositoryFactory:
    _implementations: dict[str, type] = {"sqlite": SqlRepository}

    def __init__(self, storage: Storage, registry: SchemaRegistry) -> None:
        self.storage = storage
        self.registry = registry
        self._cache: dict[str, SqlRepository] = {}

    @classmethod
    def register(cls, backend: str, implementation: type) -> None:
        cls._implementations[backend] = implementation

    def for_entity(self, entity: str | EntitySchema) -> SqlRepository:
        schema = entity if isinstance(entity, EntitySchema) else self.registry.get(entity)
        if schema.name not in self._cache:
            try:
                impl = self._implementations[self.storage.backend]
            except KeyError:
                raise NotFound(f"no repository implementation for backend {self.storage.backend!r}") from None
            self._cache[schema.name] = impl(schema, self.storage)
        return self._cache[schema.name]
