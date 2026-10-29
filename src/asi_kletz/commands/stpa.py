"""The ``stpa`` verb: STPA analyses read from Confluence (asi_hopper/docs/confluence-integration-plan.md, 7.2).

``stpa list | get <id> | builders | new <builder> [--name --system --slug --from <bundle> --page <id>
--out <dir>] | refresh <id> [--from <bundle>] [--apply] | validate <id> | link <id> --structure <slug>
[--apply] | export <id> [--out <dir>] [--format xlsx|md|docx|pdf|svg|png]... [--all] | delete <id>
[--cascade]``. An analysis is named by its id, its uid or its slug. The parts (losses, hazards,
UCAs, scenarios, constraints) are rows of their own entities, so the generic ``create`` / ``update``
/ ``delete`` work on them and the rules hold there too. Every verb answers a JSON ``Result``, every
change is audited and published as ``stpa.changed``; an export is audited as ``stpa.export`` and
published as ``stpa.exported``. ``refresh`` without ``--apply`` is a report (new, changed and
retired objects by code); with it the report is applied and every Kletz-side field is kept.
"""

from __future__ import annotations

from typing import Any

from ..errors import CommandError
from ..stpa.stpa_factory import DEFAULT_FORMATS, FORMATS
from .base import Argument, Command, Context, Result
from .factory import register_command

ACTIONS = ("list", "get", "builders", "new", "refresh", "validate", "link", "export", "delete")


@register_command
class StpaCommand(Command):
    verb = "stpa"
    help = (
        "STPA analyses: list, get <id>, builders, new <builder> [--name --system --from --page --out], refresh <id> "
        "[--from <bundle>] [--apply], validate <id>, link <id> --structure <slug> [--apply], export <id> --out <dir> "
        "[--format ...] [--all], delete <id> [--cascade]."
    )
    arguments = (
        Argument("action", " | ".join(ACTIONS), required=True, choices=ACTIONS),
        Argument("target", "The analysis (id, uid or slug); for `new` the builder"),
        Argument("name", "Name of the new analysis (new)", flag=True),
        Argument("slug", "Slug of the new analysis (default: from the name)", flag=True),
        Argument("system", "The system under analysis (new)", flag=True),
        Argument(
            "from", "The bundle folder (from_bundle, refresh) or the analysis to clone (clone)", flag=True, type="path"
        ),
        Argument(
            "page", "The Confluence page id (from_confluence; from_bundle when the bundle holds several)", flag=True
        ),
        Argument(
            "out",
            "Folder for the evidence bundle (from_confluence) or the export (default: evidence/, stpa/)",
            flag=True,
            type="path",
        ),
        Argument(
            "format",
            f"Export format, repeatable (default: {', '.join(DEFAULT_FORMATS)})",
            flag=True,
            multiple=True,
            choices=FORMATS,
        ),
        Argument("all", "Export every format", flag=True, type="bool", default=False),
        Argument(
            "apply", "For `refresh` and `link`: write what the report proposes", flag=True, type="bool", default=False
        ),
        Argument("structure", "For `link`: the control structure's slug", flag=True),
        Argument(
            "cascade",
            "For `delete`: take the parts along; without it an analysis with parts is refused",
            flag=True,
            type="bool",
            default=False,
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        action = args["action"]
        brain = ctx.brain
        service = brain.stpa
        factory = brain.stpa_factory
        target = args.get("target")
        if action == "list":
            rows = brain.service("stpa_analysis").list()
            return Result.success([service.summary(r) for r in rows])
        if action == "builders":
            return Result.success({"builders": factory.catalog()})
        if action == "new":
            if not target:
                return Result.failure(f"stpa new needs a builder: {', '.join(factory.builders())}")
            row, warnings = factory.create(
                target,
                ctx.actor,
                name=args.get("name"),
                slug=args.get("slug"),
                system=args.get("system"),
                path=args.get("from"),
                page=args.get("page"),
                out=args.get("out"),
            )
            return Result.success(row, warnings)
        if not target:
            return Result.failure(f"stpa {action} needs an analysis: its id, uid or slug")
        if action == "get":
            row = service.resolve(target)
            return Result.success({**service.summary(row), "parts": service.parts(row["slug"])})
        if action == "delete":
            return Result.success(service.delete(target, bool(args.get("cascade")), ctx.actor))
        if action == "validate":
            report = service.validate(target)
            return Result(
                ok=report["ok"],
                data=report,
                errors=list(report["errors"]),
                warnings=list(report["warnings"]),
            )
        if action == "refresh":
            dataset = factory.reread(target, args.get("from"))
            if args.get("apply"):
                report = service.apply_refresh(target, dataset, ctx.actor)
            else:
                report = {**service.compare(target, dataset), "applied": False}
            return Result.success(report, list(report.get("warnings") or []))
        if action == "link":
            report = service.link_structure(
                target, args.get("structure"), apply=bool(args.get("apply")), actor=ctx.actor
            )
            warnings = [
                f"{u['code']}: {u['status']} match for {u['controller']!r} / {u['control_action']!r}"
                for u in report["ucas"]
                if u["status"] != "exact"
            ]
            return Result.success(report, warnings)
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
