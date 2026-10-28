"""Built-in transfer commands: dump/load JSON, export/import Excel, run scripts."""

from __future__ import annotations

from typing import Any

from ..io import ExporterFactory, ImporterFactory
from ..services.entity_service import LOAD_MODES
from .base import Argument, Command, Context, Result
from .factory import register_command

MODE = Argument(
    "mode", "replace: wipe then insert; merge: upsert by id; append: new ids",
    flag=True, choices=LOAD_MODES, default="merge",
)


def _load_result(summary: dict[str, Any]) -> Result:
    return Result(
        ok=not summary.get("errors"),
        data=summary,
        errors=list(summary.get("errors", [])),
        warnings=list(summary.get("warnings", [])),
    )


@register_command
class DumpCommand(Command):
    verb = "dump"
    help = "Write the database to JSON (one entity, or all in one envelope)."
    arguments = (
        Argument("entity", "Only this entity", flag=True),
        Argument("out", "Output file (default: kletz.json or <entity>.json)", flag=True, type="path"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        summary = ctx.brain.transfer.dump(args.get("out"), args.get("entity"))
        return Result.success(summary, summary.pop("warnings", []))


@register_command
class LoadCommand(Command):
    verb = "load"
    help = "Load a JSON dump back into the database."
    arguments = (Argument("path", "JSON file written by `dump`", required=True, type="path"), MODE)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return _load_result(ctx.brain.transfer.load(args["path"], args["mode"], ctx.actor))


@register_command
class ExportCommand(Command):
    verb = "export"
    help = "Export to a view format (excel regenerates the workbook; json equals dump)."
    arguments = (
        Argument("format", "Export format", required=True, choices=tuple(ExporterFactory.formats())),
        Argument("out", "Output file", flag=True, type="path"),
        Argument("entity", "Only this entity", flag=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        summary = ctx.brain.transfer.export(args["format"], args.get("out"), args.get("entity"))
        return Result.success(summary, summary.pop("warnings", []))


@register_command
class ImportCommand(Command):
    verb = "import"
    help = "Import from a file (excel seeds the database from the workbook)."
    arguments = (
        Argument("format", "Import format", required=True, choices=tuple(ImporterFactory.formats())),
        Argument("path", "File to import", required=True, type="path"),
        MODE,
        Argument("entity", "Only these entities (repeatable)", flag=True, multiple=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        entities = args.get("entity")
        if isinstance(entities, str):
            entities = [entities]
        return _load_result(
            ctx.brain.transfer.import_(args["format"], args["path"], args["mode"], entities, ctx.actor)
        )


@register_command
class RunCommand(Command):
    verb = "run"
    help = 'Replay a .jsonl script of commands ({"verb": ..., "args": {...}} per line).'
    arguments = (
        Argument("path", "Script file", required=True, type="path"),
        Argument("stop-on-error", "Stop at the first failing step", flag=True, type="bool", default=False),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..automation.script_runner import run_script

        results = run_script(ctx.brain, args["path"], ctx.actor, bool(args.get("stop_on_error")))
        failed = [i for i, r in enumerate(results, start=1) if not r.ok]
        return Result(
            ok=not failed,
            data={"steps": len(results), "failed": failed, "results": [r.to_dict() for r in results]},
            errors=[f"step {i}: {'; '.join(results[i - 1].errors)}" for i in failed],
        )
