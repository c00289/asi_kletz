"""Schema layer: entity declarations, field types, lookups, and the registry."""

from .entity import SYSTEM_FIELDS, EntitySchema, flag_fields, slugify
from .fields import FieldSpec, FieldType, coerce, date_to_excel_serial, excel_serial_to_date
from .lookups import LookupRegistry, default_lookups
from .registry import SchemaRegistry, default_registry, register_entity

__all__ = [
    "SYSTEM_FIELDS",
    "EntitySchema",
    "FieldSpec",
    "FieldType",
    "LookupRegistry",
    "SchemaRegistry",
    "coerce",
    "date_to_excel_serial",
    "default_lookups",
    "default_registry",
    "excel_serial_to_date",
    "flag_fields",
    "register_entity",
    "slugify",
]
