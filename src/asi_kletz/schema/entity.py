"""EntitySchema: one declaration per table, from which everything else is derived."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..errors import ValidationError
from .fields import FieldSpec, FieldType, coerce

SYSTEM_FIELDS: tuple[str, ...] = ("id", "created_at", "updated_at")


@dataclass(frozen=True)
class EntitySchema:
    """Declares an entity: its names, its fields, and how it is ordered."""

    name: str
    table: str
    label: str
    sheet: str
    fields: tuple[FieldSpec, ...]
    order_by: tuple[str, ...] = ("id",)
    description: str = ""
    _by_name: dict[str, FieldSpec] = field(default_factory=dict, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ValueError(f"entity name {self.name!r} must be a Python identifier")
        fields = tuple(self.fields)
        object.__setattr__(self, "fields", fields)
        seen: dict[str, FieldSpec] = {}
        for spec in fields:
            if spec.name in SYSTEM_FIELDS:
                raise ValueError(f"{self.name}: field {spec.name!r} clashes with a system field")
            if spec.name in seen:
                raise ValueError(f"{self.name}: duplicate field {spec.name!r}")
            seen[spec.name] = spec
        object.__setattr__(self, "_by_name", seen)
        for key in self.order_by:
            if key.lstrip("-") not in seen and key.lstrip("-") not in SYSTEM_FIELDS:
                raise ValueError(f"{self.name}: order_by references unknown field {key!r}")

    # -- introspection -------------------------------------------------
    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.fields)

    @property
    def all_columns(self) -> tuple[str, ...]:
        return ("id", *self.field_names, "created_at", "updated_at")

    def field(self, name: str) -> FieldSpec:
        try:
            return self._by_name[name]
        except KeyError:
            raise KeyError(f"{self.name} has no field {name!r}") from None

    def has(self, name: str) -> bool:
        return name in self._by_name or name in SYSTEM_FIELDS

    def groups(self) -> dict[str, list[FieldSpec]]:
        out: dict[str, list[FieldSpec]] = {}
        for spec in self.fields:
            out.setdefault(spec.group or "", []).append(spec)
        return out

    def blank(self) -> dict[str, Any]:
        return {spec.name: spec.default for spec in self.fields}

    # -- validation -----------------------------------------------------
    def coerce_row(
        self,
        data: Mapping[str, Any],
        lookups: Mapping[str, Sequence[str]] | None = None,
        *,
        partial: bool = False,
    ) -> tuple[dict[str, Any], list[str]]:
        """Validate and normalise one row. Returns ``(clean, warnings)``.

        With ``partial=True`` only the supplied fields are checked (for updates).
        Raises ``ValidationError`` listing every problem at once.
        """
        errors: list[str] = []
        warnings: list[str] = []
        clean: dict[str, Any] = {}
        unknown = sorted(set(data) - set(self.field_names) - set(SYSTEM_FIELDS))
        if unknown:
            errors.append(f"unknown field(s): {', '.join(unknown)}")
        for spec in self.fields:
            if partial and spec.name not in data:
                continue
            try:
                value, warning = coerce(spec, data.get(spec.name), lookups)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            clean[spec.name] = value
            if warning:
                warnings.append(warning)
        if errors:
            raise ValidationError(self.name, errors)
        return clean, warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "table": self.table,
            "label": self.label,
            "sheet": self.sheet,
            "description": self.description,
            "order_by": list(self.order_by),
            "fields": [spec.to_dict() for spec in self.fields],
        }


def slugify(text: str) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in text.lower()).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug


def flag_fields(group: str, prefix: str, headers: Iterable[str]) -> list[FieldSpec]:
    """Build a run of boolean columns from their Excel headers (Safety Plan matrix)."""
    return [
        FieldSpec(f"{prefix}_{slugify(header)}", FieldType.BOOL, label=header, group=group)
        for header in headers
    ]
