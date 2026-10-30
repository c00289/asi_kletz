"""The ``hara`` verb: the ISO 19014 risk assessment, parametrised (0.28.0).

``hara list | get <ref> | builders | new <builder> [--name --slug --system --from <xlsx> --vehicle <letter>
--generation 1|2 --analysis <slug>] | recompute <ref> | summary <ref> | check <ref> | validate <ref> | export
<ref> [--out <dir>] [--format xlsx|md]... [--all] | delete <ref> [--cascade]``. A HARA is named by its id, its
uid or its slug. The parts (vehicles, functions, use cases, failure modes, assumptions, ratings, assessments,
approvals) are rows of their own entities, so the generic ``create`` / ``update`` / ``delete`` work on them
and the rules hold there too; ``mplr`` is calculated and only ``recompute`` writes it. Every verb answers a
JSON ``Result``, every change is audited and published as ``hara.changed``; an export is audited as
``hara.export`` and published as ``hara.exported``.
"""

from __future__ import annotations

from typing import Any

from ..errors import CommandError
from ..hara.hara_factory import DEFAULT_FORMATS, FORMATS
from .base import Argument, Command, Context, Result
from .factory import register_command

ACTIONS = ("list", "get", "builders", "new", "recompute", "summary", "check", "validate", "export", "delete")


@register_command
class HaraCommand(Command):
    verb = "hara"
    help = (
        "HARA (ISO 19014): list, get <ref>, builders, new <builder> [--name --from --vehicle --generation --analysis], "
        "recompute <ref>, summary <ref>, check <ref>, validate <ref>, export <ref> [--out] [--format ...] [--all], "
        "delete <ref> [--cascade]."
    )
    arguments = (
        Argument("action", " | ".join(ACTIONS), required=True, choices=ACTIONS),
        Argument("target", "The HARA (id, uid or slug); for `new` the builder"),
        Argument("name", "Name of the new HARA (new)", flag=True),
        Argument("slug", "Slug of the new HARA (default: from the name)", flag=True),
        Argument("system", "The system under analysis (new)", flag=True),
        Argument("from", "The workbook (from_workbook) or the HARA to clone (clone)", flag=True, type="path"),
        Argument("vehicle", "The annex letter the MPLr is read for (G), or `cumulative`", flag=True),
        Argument(
            "generation", "1: the named assessment sheets (default); 2: the hidden HARA-n twins", flag=True, type="int"
        ),
        Argument("analysis", "Slug of an STPA analysis already holding step 1 (from_workbook)", flag=True),
        Argument("out", "Folder for the export (default: <out>/hara)", flag=True, type="path"),
        Argument(
            "format",
            f"Export format, repeatable (default: {', '.join(DEFAULT_FORMATS)})",
            flag=True,
            multiple=True,
            choices=FORMATS,
        ),
        Argument("all", "Export every format", flag=True, type="bool", default=False),
        Argument(
            "cascade",
            "For `delete`: take the parts along (and a workbook-read STPA analysis whose step 3 never began)",
            flag=True,
            type="bool",
            default=False,
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        action = args["action"]
        brain = ctx.brain
        service = brain.hara
        factory = brain.hara_factory
        target = args.get("target")
        if action == "list":
            return Result.success([service.summary(r) for r in brain.service("hara").list()])
        if action == "builders":
            return Result.success({"builders": factory.catalog()})
        if action == "new":
            if not target:
                return Result.failure(f"hara new needs a builder: {', '.join(factory.builders())}")
            row, warnings = factory.create(
                target,
                ctx.actor,
                name=args.get("name"),
                slug=args.get("slug"),
                system=args.get("system"),
                path=args.get("from"),
                vehicle=args.get("vehicle"),
                generation=args.get("generation"),
                analysis=args.get("analysis"),
            )
            return Result.success(row, warnings)
        if not target:
            return Result.failure(f"hara {action} needs a HARA: its id, uid or slug")
        if action == "get":
            row = service.resolve(target)
            return Result.success({**service.summary(row), "parts": service.parts(row["slug"])})
        if action == "delete":
            return Result.success(service.delete(target, bool(args.get("cascade")), ctx.actor))
        if action == "recompute":
            return Result.success(service.recompute(target, ctx.actor))
        if action == "summary":
            return Result.success(service.hazard_summary(target))
        if action == "check":
            report = service.check(target)
            warnings = [
                f"{context}: {c['differ']} of {c['rows']} rows differ from the workbook"
                for context, c in report["contexts"].items()
                if c["differ"]
            ]
            return Result.success(report, warnings)
        if action == "validate":
            report = service.validate(target)
            return Result(
                ok=report["ok"], data=report, errors=list(report["errors"]), warnings=list(report["warnings"])
            )
        if action == "export":
            data = factory.export(target, args.get("out"), _formats(args), actor=ctx.actor)
            return Result.success(data, list(data["issues"]))
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
