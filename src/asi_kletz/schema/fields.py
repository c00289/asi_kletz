"""Field types and the one coercion routine every layer shares.

A ``FieldSpec`` describes one column of an entity: its name, type, Excel header,
and (for enums) which lookup list constrains it. ``coerce`` turns whatever a
caller handed in (CLI string, JSON value, Excel cell) into the canonical Python
value stored in the database, or raises ``ValueError`` with a message that names
the field.
"""

from __future__ import annotations

import datetime as dt
import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_EXCEL_EPOCH = dt.date(1899, 12, 30)
_TRUE = {"1", "true", "yes", "y", "x", "on", "t"}
_FALSE = {"0", "false", "no", "n", "off", "f", ""}
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%b-%Y")


class FieldType(enum.StrEnum):
    TEXT = "text"
    MULTILINE = "multiline"
    INT = "int"
    BOOL = "bool"
    DATE = "date"
    URL = "url"
    ENUM = "enum"


SQL_TYPES: dict[FieldType, str] = {
    FieldType.TEXT: "TEXT",
    FieldType.MULTILINE: "TEXT",
    FieldType.INT: "INTEGER",
    FieldType.BOOL: "INTEGER",
    FieldType.DATE: "TEXT",
    FieldType.URL: "TEXT",
    FieldType.ENUM: "TEXT",
}

PY_TYPES: dict[FieldType, type] = {
    FieldType.TEXT: str,
    FieldType.MULTILINE: str,
    FieldType.INT: int,
    FieldType.BOOL: bool,
    FieldType.DATE: str,
    FieldType.URL: str,
    FieldType.ENUM: str,
}


@dataclass(frozen=True)
class FieldSpec:
    """One column of an entity."""

    name: str
    type: FieldType = FieldType.TEXT
    label: str | None = None
    required: bool = False
    lookup: str | None = None
    group: str | None = None
    width: int | None = None
    help: str = ""

    def __post_init__(self) -> None:
        if not self.name.isidentifier() or self.name.startswith("_"):
            raise ValueError(f"field name {self.name!r} must be a public Python identifier")
        if self.type is FieldType.ENUM and not self.lookup:
            raise ValueError(f"enum field {self.name!r} needs a lookup name")

    @property
    def header(self) -> str:
        """Column header used in Excel and in human-facing listings."""
        return self.label if self.label is not None else self.name.replace("_", " ")

    @property
    def sql_type(self) -> str:
        return SQL_TYPES[self.type]

    @property
    def py_type(self) -> type:
        return PY_TYPES[self.type]

    @property
    def is_flag(self) -> bool:
        return self.type is FieldType.BOOL

    @property
    def default(self) -> Any:
        return False if self.is_flag else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": str(self.type),
            "header": self.header,
            "required": self.required,
            "lookup": self.lookup,
            "group": self.group,
            "help": self.help,
        }


def excel_serial_to_date(serial: float) -> dt.date:
    """Convert an Excel 1900-system day serial (for example 46314) to a date."""
    return _EXCEL_EPOCH + dt.timedelta(days=int(serial))


def date_to_excel_serial(value: dt.date) -> int:
    return (value - _EXCEL_EPOCH).days


def normalize_text(value: str) -> str:
    """Replace non-breaking spaces and strip the ends. Internal newlines are kept."""
    return value.replace("\xa0", " ").strip()


def coerce(
    spec: FieldSpec,
    value: Any,
    lookups: Mapping[str, Sequence[str]] | None = None,
) -> tuple[Any, str | None]:
    """Return ``(clean_value, warning_or_None)``; raise ``ValueError`` if uncoercible."""
    if isinstance(value, str):
        value = normalize_text(value)
    if value is None or value == "":
        if spec.is_flag:
            return False, None
        if spec.required:
            raise ValueError(f"{spec.name}: a value is required")
        return None, None

    kind = spec.type
    if kind is FieldType.INT:
        if isinstance(value, bool):
            return int(value), None
        if isinstance(value, (int, float)):
            if float(value) != int(value):
                raise ValueError(f"{spec.name}: {value!r} is not a whole number")
            return int(value), None
        try:
            return int(str(value).strip()), None
        except ValueError:
            raise ValueError(f"{spec.name}: {value!r} is not an integer") from None

    if kind is FieldType.BOOL:
        if isinstance(value, (bool, int, float)):
            return bool(value), None
        text = str(value).strip().lower()
        if text in _TRUE:
            return True, None
        if text in _FALSE:
            return False, None
        raise ValueError(f"{spec.name}: {value!r} is not a yes/no value")

    if kind is FieldType.DATE:
        if isinstance(value, dt.datetime):
            return value.date().isoformat(), None
        if isinstance(value, dt.date):
            return value.isoformat(), None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return excel_serial_to_date(value).isoformat(), None
        text = str(value).strip()
        for fmt in _DATE_FORMATS:
            try:
                return dt.datetime.strptime(text, fmt).date().isoformat(), None
            except ValueError:
                continue
        if text.isdigit() and 4 < len(text) < 7:
            return excel_serial_to_date(int(text)).isoformat(), None
        raise ValueError(f"{spec.name}: {value!r} is not a date (use YYYY-MM-DD)")

    text = value if isinstance(value, str) else str(value)
    if kind is not FieldType.MULTILINE:
        text = " ".join(text.split())
    if kind is FieldType.ENUM and lookups is not None and spec.lookup:
        allowed = lookups.get(spec.lookup, ())
        if allowed and text not in allowed:
            return text, f"{spec.name}: {text!r} is not in lookup {spec.lookup!r}"
    return text, None
