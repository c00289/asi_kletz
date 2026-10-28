"""SchemaRegistry: the catalogue of entities every factory reads from."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator

from ..errors import NotFound
from .entity import EntitySchema


class SchemaRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, EntitySchema] = {}
        self._aliases: dict[str, str] = {}

    def register(self, schema: EntitySchema) -> EntitySchema:
        if schema.name in self._schemas:
            raise ValueError(f"entity {schema.name!r} already registered")
        self._schemas[schema.name] = schema
        for alias in (schema.name, schema.table, schema.label, schema.sheet):
            self._aliases.setdefault(alias.casefold(), schema.name)
        return schema

    def get(self, key: str) -> EntitySchema:
        """Resolve by entity name, table, label, or sheet name (case-insensitive)."""
        name = self._aliases.get(str(key).casefold())
        if name is None:
            raise NotFound(f"unknown entity {key!r}; known entities: {', '.join(self.names())}")
        return self._schemas[name]

    def names(self) -> list[str]:
        return list(self._schemas)

    def __iter__(self) -> Iterator[EntitySchema]:
        return iter(self._schemas.values())

    def __len__(self) -> int:
        return len(self._schemas)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key.casefold() in self._aliases

    def fingerprint(self) -> str:
        payload = json.dumps([s.to_dict() for s in self], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {"entities": [s.to_dict() for s in self], "fingerprint": self.fingerprint()}


default_registry = SchemaRegistry()


def register_entity(schema: EntitySchema, registry: SchemaRegistry | None = None) -> EntitySchema:
    """Register an entity. New tables are added by calling this, not by editing core code."""
    return (registry or default_registry).register(schema)
