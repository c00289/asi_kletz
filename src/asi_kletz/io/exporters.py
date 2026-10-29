"""Exporters: the workbook and the JSON dump are *views* regenerated from the database.

Since 0.9.0 both carry the hidden ``uid`` of every row: the JSON dump as any key, the workbook as the
last column of every sheet, headed ``uid`` and hidden, so the sheet reads as before and still round-trips.
"""

from __future__ import annotations

import abc
import datetime as dt
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..errors import NotFound
from ..schema import EntitySchema, FieldType
from ..schema.fields import json_text
from ..version import SCHEMA_VERSION, __version__

if TYPE_CHECKING:
    from ..brain import Brain


def _timestamp() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


class Exporter(abc.ABC):
    format: ClassVar[str] = ""
    suffix: ClassVar[str] = ""

    @abc.abstractmethod
    def export(self, brain: Brain, out: str | Path | None, entity: str | None = None) -> dict[str, Any]:
        """Write the view. Returns a summary with ``path``, ``entities`` (counts) and ``warnings``."""


class ExporterFactory:
    _exporters: dict[str, type[Exporter]] = {}

    @classmethod
    def register(cls, exporter: type[Exporter]) -> type[Exporter]:
        cls._exporters[exporter.format] = exporter
        return exporter

    @classmethod
    def create(cls, fmt: str) -> Exporter:
        try:
            return cls._exporters[fmt]()
        except KeyError:
            raise NotFound(f"unknown export format {fmt!r}; known: {', '.join(cls._exporters)}") from None

    @classmethod
    def formats(cls) -> list[str]:
        return list(cls._exporters)


def _schemas(brain: Brain, entity: str | None) -> list[EntitySchema]:
    return [brain.registry.get(entity)] if entity else list(brain.registry)


def _save_with_fallback(save: Callable[[Path], None], out: Path, suffix: str) -> tuple[Path, str | None]:
    """Save to ``out``; if it is locked (open in Excel), save to a timestamped sibling instead."""
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        save(out)
        return out, None
    except PermissionError:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        alt = out.with_name(f"{out.stem}_{stamp}{suffix}")
        save(alt)
        return alt, f"{out.name} is locked (open in another program); wrote {alt.name} instead"


@ExporterFactory.register
class JsonExporter(Exporter):
    format = "json"
    suffix = ".json"

    def payload(self, brain: Brain, entity: str | None = None) -> dict[str, Any]:
        base = {"schema_version": SCHEMA_VERSION, "app_version": __version__, "exported_at": _timestamp()}
        if entity:
            schema = brain.registry.get(entity)
            return {**base, "entity": schema.name, "rows": brain.service(schema.name).list()}
        return {**base, "entities": {s.name: brain.service(s.name).list() for s in brain.registry}}

    def export(self, brain: Brain, out: str | Path | None, entity: str | None = None) -> dict[str, Any]:
        payload = self.payload(brain, entity)
        target = Path(out) if out else Path(f"{payload.get('entity', 'asi_kletz')}.json")

        def save(path: Path) -> None:
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        path, warning = _save_with_fallback(save, target, self.suffix)
        if entity:
            counts = {payload["entity"]: len(payload["rows"])}
        else:
            counts = {name: len(rows) for name, rows in payload["entities"].items()}
        return {"format": self.format, "path": str(path), "entities": counts, "warnings": [warning] if warning else []}


@ExporterFactory.register
class ExcelExporter(Exporter):
    format = "excel"
    suffix = ".xlsx"
    HEADER_FILL = "FFD9E1F2"

    def export(self, brain: Brain, out: str | Path | None, entity: str | None = None) -> dict[str, Any]:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation

        wb = Workbook()
        wb.remove(wb.active)
        counts: dict[str, int] = {}
        for schema in _schemas(brain, entity):
            ws = wb.create_sheet(schema.sheet[:31])
            rows = brain.service(schema.name).list()
            counts[schema.name] = len(rows)
            widths: list[int] = []
            for col, spec in enumerate(schema.fields, start=1):
                cell = ws.cell(row=1, column=col, value=spec.header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor=self.HEADER_FILL)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                widths.append(len(spec.header))
            for r, row in enumerate(rows, start=2):
                for col, spec in enumerate(schema.fields, start=1):
                    value = row.get(spec.name)
                    if value is None:
                        continue
                    cell = ws.cell(row=r, column=col)
                    if spec.type is FieldType.BOOL:
                        cell.value = 1 if value else 0
                    elif spec.type is FieldType.DATE:
                        cell.value = dt.date.fromisoformat(value)
                        cell.number_format = "yyyy-mm-dd"
                    elif spec.type is FieldType.URL:
                        cell.value = value
                        cell.hyperlink = value
                        cell.style = "Hyperlink"
                    elif spec.type is FieldType.JSON:  # the people of a role: JSON text, read back by the import
                        cell.value = value if isinstance(value, str) else json_text(value)
                    else:
                        cell.value = value
                        if spec.type is FieldType.MULTILINE:
                            cell.alignment = Alignment(wrap_text=True, vertical="top")
                    widths[col - 1] = max(widths[col - 1], min(len(str(value)), 60))
            for col, spec in enumerate(schema.fields, start=1):
                base = spec.width or widths[col - 1]
                if spec.type is FieldType.BOOL:
                    base = min(base, 14)
                ws.column_dimensions[get_column_letter(col)].width = max(6, min(base + 2, 62))
                if spec.hidden:  # the uid: present in the data, hidden on the sheet, so it reads as before
                    ws.column_dimensions[get_column_letter(col)].hidden = True
                if spec.lookup:
                    values = brain.lookups.get(spec.lookup, ())
                    formula = '"' + ",".join(values) + '"'
                    if values and len(formula) <= 255 and not any("," in v or '"' in v for v in values):
                        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=False)
                        ws.add_data_validation(dv)
                        letter = get_column_letter(col)
                        dv.add(f"{letter}2:{letter}{max(len(rows) + 200, 500)}")
            ws.freeze_panes = "A2"
            if rows:
                ws.auto_filter.ref = ws.dimensions
        target = Path(out) if out else Path(brain.workbook_path)
        path, warning = _save_with_fallback(wb.save, target, self.suffix)
        return {"format": self.format, "path": str(path), "entities": counts, "warnings": [warning] if warning else []}
