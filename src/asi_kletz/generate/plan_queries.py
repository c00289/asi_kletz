"""Read-side helpers over the Safety Plan that diagrams, documents and the dashboard share.

Every number shown in the window and every number printed in a report comes from here, so
the two cannot drift. Nothing in this module writes.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..schema import EntitySchema, FieldSpec

if TYPE_CHECKING:
    from ..brain import Brain

PLAN_ENTITY = "safety_plan_row"
CLOSED_STATUSES = ("Done", "Out-of-Scope")
FLAG_GROUPS = ("location", "reference", "author", "verification", "reviewer")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y", "%d %B %Y")
_DATE_TOKEN = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{4}|\d{4}/\d{2}/\d{2}|\d{1,2}[- ][A-Za-z]{3,9}[- ]\d{4}"
)


# -- rows -------------------------------------------------------------------
def all_rows(brain: Brain) -> list[dict[str, Any]]:
    """Every deliverable, in plan order (``order`` then ``id``)."""
    return brain.service(PLAN_ENTITY).list(order_by=("order", "id"))


def statuses(brain: Brain) -> list[str]:
    return list(brain.lookups.get("plan_status", ()))


def phases(brain: Brain, rows: Iterable[dict[str, Any]] | None = None) -> list[str]:
    """The lifecycle phases in lookup order, then any value a row uses that is not in the lookup."""
    known = list(brain.lookups.get("lifecycle_phase", ()))
    if rows is None:
        return known
    unknown = sorted({r["lifecycle_phase"] for r in rows if r.get("lifecycle_phase") not in (None, *known)})
    return [*known, *unknown]


def pdp_phases(brain: Brain) -> list[str]:
    return list(brain.lookups.get("pdp_phase", ()))


def phase_number(phase: str) -> str:
    """``"3. Functional Safety Concept (FSC)"`` -> ``"3"``; a phase without a number comes back whole."""
    match = re.match(r"\s*(\d+)\s*\.", phase or "")
    return match.group(1) if match else (phase or "").strip()


def phase_title(phase: str) -> str:
    """``"3. Functional Safety Concept (FSC)"`` -> ``"Functional Safety Concept (FSC)"``."""
    return re.sub(r"^\s*\d+\s*\.\s*", "", phase or "").strip()


def resolve_phase(brain: Brain, value: str) -> str:
    """Accept a lifecycle phase by its full lookup value or by its leading number."""
    text = (value or "").strip()
    known = phases(brain)
    if text in known:
        return text
    number = text.rstrip(".").strip()
    for phase in known:
        if phase_number(phase) == number:
            return phase
    raise CommandError(f"unknown phase {value!r}; known: {', '.join(known)}")


def rows_by_phase(brain: Brain, rows: Iterable[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    """Phase -> its rows in plan order. Every phase of the lookup is a key, even when empty."""
    rows = all_rows(brain) if rows is None else list(rows)
    grouped: dict[str, list[dict[str, Any]]] = {phase: [] for phase in phases(brain, rows)}
    for row in rows:
        grouped.setdefault(row.get("lifecycle_phase") or "", []).append(row)
    return grouped


def rows_by_pdp_phase(brain: Brain, rows: Iterable[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    rows = all_rows(brain) if rows is None else list(rows)
    grouped: dict[str, list[dict[str, Any]]] = {phase: [] for phase in pdp_phases(brain)}
    for row in rows:
        grouped.setdefault(str(row.get("pdp_phase") or ""), []).append(row)
    return grouped


# -- counts -----------------------------------------------------------------
def counts_by_status(brain: Brain, rows: Iterable[dict[str, Any]] | None = None) -> dict[str, int]:
    """``{status: count}`` for every status of the lookup, plus ``total``."""
    rows = all_rows(brain) if rows is None else list(rows)
    counts = {status: 0 for status in statuses(brain)}
    for row in rows:
        status = row.get("status") or ""
        counts[status] = counts.get(status, 0) + 1
    counts["total"] = len(rows)
    return counts


def counts_by_phase(brain: Brain, rows: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One record per phase: ``lifecycle_phase``, ``deliverables``, ``done`` and a count per status."""
    rows = all_rows(brain) if rows is None else list(rows)
    out = []
    for phase, phase_rows in rows_by_phase(brain, rows).items():
        record: dict[str, Any] = {
            "lifecycle_phase": phase,
            "deliverables": len(phase_rows),
            "done": sum(1 for r in phase_rows if r.get("status") == "Done"),
        }
        for status in statuses(brain):
            record[status] = sum(1 for r in phase_rows if r.get("status") == status)
        out.append(record)
    return out


def open_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deliverables that are neither Done nor Out-of-Scope."""
    return [r for r in rows if r.get("status") not in CLOSED_STATUSES]


def blocked(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if r.get("status") == "Blocked"]


# -- deadlines ----------------------------------------------------------------
def parse_deadline(text: Any) -> dt.date | None:
    """Best-effort date from the free-text deadline column: ISO, ``dd/mm/yyyy`` and a few others."""
    if text is None:
        return None
    if isinstance(text, dt.datetime):
        return text.date()
    if isinstance(text, dt.date):
        return text
    raw = str(text).strip()
    candidates = [raw, *(m.group(0) for m in _DATE_TOKEN.finditer(raw))]
    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return dt.datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def due_within(
    rows: Iterable[dict[str, Any]], days: int = 30, today: dt.date | None = None
) -> tuple[list[tuple[dict[str, Any], dt.date]], list[dict[str, Any]]]:
    """Open rows whose deadline parses and falls within ``days`` (overdue included), and those with no date."""
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=days)
    due: list[tuple[dict[str, Any], dt.date]] = []
    undated: list[dict[str, Any]] = []
    for row in open_rows(rows):
        when = parse_deadline(row.get("deadline"))
        if when is None:
            undated.append(row)
        elif when <= horizon:
            due.append((row, when))
    due.sort(key=lambda item: (item[1], item[0].get("order") or 0))
    return due, undated


# -- flags ------------------------------------------------------------------
def _default_schema() -> EntitySchema:
    from ..schema.definitions import SAFETY_PLAN_ROW

    return SAFETY_PLAN_ROW


def group_flags(group: str, schema: EntitySchema | None = None) -> list[FieldSpec]:
    """The boolean fields of a flag group, in declaration order."""
    schema = schema or _default_schema()
    return [spec for spec in schema.groups().get(group, []) if spec.is_flag]


def set_flags(row: dict[str, Any], group: str, schema: EntitySchema | None = None) -> list[str]:
    """Labels of the flags of ``group`` that are set on ``row`` (``["DMS", "JAMA"]`` for location)."""
    return [spec.header for spec in group_flags(group, schema) if row.get(spec.name)]


def summarise(labels: Iterable[str], limit: int = 3) -> str:
    """``a, b, c +2``: the first ``limit`` labels and how many more there are (for node labels)."""
    labels = [str(label) for label in labels if label]
    if len(labels) <= limit:
        return ", ".join(labels)
    return ", ".join(labels[:limit]) + f" +{len(labels) - limit}"


def describe(row: dict[str, Any], text_field: str | None, group: str, schema: EntitySchema | None = None) -> str:
    """Free text of ``text_field`` plus the set flags of ``group``, joined for a table cell."""
    parts: list[str] = []
    if text_field and row.get(text_field):
        parts.append(one_line(row[text_field]))
    parts.extend(flag for flag in set_flags(row, group, schema) if flag not in parts)
    return "; ".join(parts)


def one_line(text: Any, limit: int = 0) -> str:
    """Collapse whitespace and newlines; optionally truncate with an ellipsis."""
    flat = " ".join(str(text or "").split())
    if limit and len(flat) > limit:
        return flat[: limit - 1].rstrip() + "…"
    return flat
