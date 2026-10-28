"""ModelFactory: build a dataclass for an entity from its schema, on demand."""

from __future__ import annotations

from dataclasses import asdict, field, make_dataclass
from typing import Any

from ..schema import EntitySchema, SchemaRegistry


def _to_dict(self) -> dict[str, Any]:
    return asdict(self)


def _from_dict(cls, data: dict[str, Any]):
    known = cls.__dataclass_fields__
    return cls(**{k: v for k, v in data.items() if k in known})


class ModelFactory:
    """Produces (and caches) one dataclass type per entity."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self.registry = registry
        self._cache: dict[str, type] = {}

    def build(self, entity: str | EntitySchema) -> type:
        schema = entity if isinstance(entity, EntitySchema) else self.registry.get(entity)
        if schema.name in self._cache:
            return self._cache[schema.name]
        fields: list[tuple[str, Any, Any]] = [("id", int | None, field(default=None))]
        for spec in schema.fields:
            fields.append((spec.name, spec.py_type | None, field(default=spec.default)))
        fields.append(("created_at", str | None, field(default=None)))
        fields.append(("updated_at", str | None, field(default=None)))
        class_name = "".join(part.capitalize() for part in schema.name.split("_"))
        cls = make_dataclass(
            class_name,
            fields,
            kw_only=True,
            namespace={
                "__schema__": schema,
                "to_dict": _to_dict,
                "from_dict": classmethod(_from_dict),
                "__module__": __name__,
            },
        )
        self._cache[schema.name] = cls
        return cls

    def instance(self, entity: str, data: dict[str, Any]):
        return self.build(entity).from_dict(data)
