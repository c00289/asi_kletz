"""TransferService: dump/load JSON and export/import Excel through the io factories."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..io import ExporterFactory, ImporterFactory

if TYPE_CHECKING:
    from ..brain import Brain


class TransferService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    def export(self, fmt: str, out: str | Path | None = None, entity: str | None = None) -> dict[str, Any]:
        return ExporterFactory.create(fmt).export(self.brain, out, entity)

    def import_(
        self,
        fmt: str,
        path: str | Path,
        mode: str = "merge",
        entities: list[str] | None = None,
        actor: str = "import",
    ) -> dict[str, Any]:
        return ImporterFactory.create(fmt).import_(self.brain, path, mode, entities, actor)

    def dump(self, out: str | Path | None = None, entity: str | None = None) -> dict[str, Any]:
        return self.export("json", out, entity)

    def load(self, path: str | Path, mode: str = "merge", actor: str = "import") -> dict[str, Any]:
        return self.import_("json", path, mode, None, actor)

    def payload(self, entity: str | None = None) -> dict[str, Any]:
        """In-memory JSON dump (no file), for AI agents and tests."""
        from ..io.exporters import JsonExporter

        return JsonExporter().payload(self.brain, entity)
