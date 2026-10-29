"""The ``cs`` verb: control structures (docs/control-structure-plan.md, section 6).

``cs list | get <id> | builders | new <builder> [--name --system --slug --from <file>] |
duplicate <id> --name | delete <id> [--cascade] | validate <id> | import <drawio-or-folder> |
export <id> --out <dir> [--format drawio|png|svg]... [--all] [--no-ocr]``. A structure is named by
its id, its uid or its slug. The parts (controllers, algorithms, process-model entries, edges,
signals, notes) are rows of their own entities, so the generic ``create`` / ``update`` /
``delete`` work on them and the rules hold there too (``delete --cascade`` on a controller or an
edge). Every verb answers a JSON ``Result``, every change is audited and published as
``cs.changed``; an export is audited as ``cs.export`` and published as ``cs.exported`` with the
files written and the OCR verdict.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import CommandError
from ..stpa.factory import DEFAULT_FORMATS, FORMATS
from .base import Argument, Command, Context, Result
from .factory import register_command

ACTIONS = ("list", "get", "builders", "new", "duplicate", "delete", "validate", "import", "export")


@register_command
class CsCommand(Command):
    verb = "cs"
    help = (
        "Control structures: list, get <id>, builders, new <builder>, duplicate <id> --name, delete <id> "
        "[--cascade], validate <id>, import <drawio-or-folder>, export <id> --out <dir> [--format ...] [--all] "
        "[--no-ocr]."
    )
    arguments = (
        Argument("action", " | ".join(ACTIONS), required=True, choices=ACTIONS),
        Argument("target", "The structure (id, uid or slug); for `new` the builder; for `import` the file or folder"),
        Argument("name", "Name of the new structure (new, duplicate)", flag=True),
        Argument("slug", "Slug of the new structure (default: from the name)", flag=True),
        Argument("system", "The system the structure controls (new)", flag=True),
        Argument("from", "The file, folder or structure a builder reads (from_drawio, from_datasets, clone)",
                 flag=True, type="path"),
        Argument("out", "Output folder for `export` (default: control_structures/ under the out folder)",
                 flag=True, type="path"),
        Argument("format", f"Export format, repeatable (default: {', '.join(DEFAULT_FORMATS)})",
                 flag=True, multiple=True, choices=FORMATS),
        Argument("all", "Export every format", flag=True, type="bool", default=False),
        Argument("no-ocr", "Skip the OCR gate on the PNG", flag=True, type="bool", default=False),
        Argument("cascade", "For `delete`: take the parts along; without it a structure with parts is refused",
                 flag=True, type="bool", default=False),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        action = args["action"]
        brain = ctx.brain
        service = brain.control_structures
        target = args.get("target")
        if action == "list":
            rows = brain.service("control_structure").list()
            return Result.success([service.summary(r) for r in rows])
        if action == "builders":
            return Result.success({"builders": brain.factory.catalog()})
        if action == "new":
            if not target:
                return Result.failure(f"cs new needs a builder: {', '.join(brain.factory.builders())}")
            row, warnings = brain.factory.create(
                target, ctx.actor, name=args.get("name"), slug=args.get("slug"), system=args.get("system"),
                path=args.get("from"),
            )
            return Result.success(row, warnings)
        if action == "import":
            if not target:
                return Result.failure("cs import needs a .drawio file or a datasets folder")
            path = Path(target)
            builder = "from_datasets" if path.is_dir() else "from_drawio"
            row, warnings = brain.factory.create(
                builder, ctx.actor, name=args.get("name"), slug=args.get("slug"), system=args.get("system"),
                path=str(path),
            )
            return Result.success(row, warnings)
        if not target:
            return Result.failure(f"cs {action} needs a structure: its id, uid or slug")
        if action == "get":
            row = service.resolve(target)
            return Result.success({**service.summary(row), "parts": service.parts(row["slug"])})
        if action == "duplicate":
            if not args.get("name"):
                return Result.failure("cs duplicate needs --name")
            row, warnings = service.duplicate(target, args["name"], args.get("slug"), ctx.actor)
            return Result.success(row, warnings)
        if action == "delete":
            return Result.success(service.delete(target, bool(args.get("cascade")), ctx.actor))
        if action == "validate":
            report = service.validate(target)
            return Result(
                ok=report["ok"], data=report, errors=list(report["errors"]), warnings=list(report["warnings"]),
            )
        if action == "export":
            formats = _formats(args)
            data = brain.factory.export(
                target, args.get("out"), formats, ocr=not args.get("no_ocr"), actor=ctx.actor,
            )
            warnings = [i["message"] for i in data["issues"]]
            return Result.success(data, warnings)
        raise CommandError(f"unknown action {action!r}")


def _formats(args: dict[str, Any]) -> tuple[str, ...]:
    if args.get("all"):
        return FORMATS
    given = args.get("format")
    if not given:
        return DEFAULT_FORMATS
    if isinstance(given, str):
        given = [given]
    return tuple(dict.fromkeys(str(f).strip().lower() for f in given if str(f).strip()))
