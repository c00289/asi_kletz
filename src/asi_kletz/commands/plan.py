"""The ``plan`` verb: the Safety Plan's points, and the sprint and deadline calculated from them.

``plan schedule`` recomputes now and prints the table (order, deliverable, points, the weight and its
source, sprint, deadline, status, warnings); ``plan weights load <file>`` sets ``default_points`` from the
estimation panel's record (``data/deliverable-points.json``), matching rows by uid when the file has one,
else by id. The sprint rule (owner, 2026-10-28): a sprint spans 10 business days (weekends and holidays
excluded, so holidays stretch dates); capacity is 8 points per sprint, company policy, a fixed global; only a
Closed sprint keeps another number as history; sprints are consecutive, numbered across the programme.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class PlanCommand(Command):
    verb = "plan"
    help = (
        "The Safety Plan's points: schedule recomputes every row's sprint (where its last point lands, 8 points "
        "a sprint, committed items first) and deadline (that sprint's end) and prints the table; "
        "weights load <file> sets each row's default points from the estimation panel's record; "
        "export --row <id> [--out <dir>] [--standard <folder>] builds the row's standards with asi_gutenberg, "
        "the parameters filled (the chosen points, never the default; the sprint's end; the Jira ticket's "
        "status); parameters --row <id> prints that value set without building."
    )
    arguments = (
        Argument("action", "schedule | weights | export | parameters", required=True,
                 choices=("schedule", "weights", "export", "parameters")),
        Argument("what", "weights: load"),
        Argument("file", "weights load: the JSON list of {id, order, deliverable, points[, uid]}", type="path"),
        Argument("row", "export / parameters: the Safety Plan row (id or uid)", flag=True, type="ref"),
        Argument("out", "export: the output folder (default: $ASI_KLETZ_OUT, `out` in kletz.toml, or out/ next to "
                 "the database)", flag=True, type="path"),
        Argument("standard", "export / parameters: one standard's folder (default: every standard the row has)",
                 flag=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.schedule
        if args["action"] in ("export", "parameters"):
            if args.get("row") is None:
                return Result.failure(f"plan {args['action']} needs --row <id>")
            row_id = ctx.brain.service("safety_plan_row").resolve(args["row"])
            if args["action"] == "parameters":
                data = ctx.brain.standards.value_set(row_id, args.get("standard"))
                return Result.success(data, data.pop("warnings"))
            data = ctx.brain.standards.export(row_id, args.get("out"), args.get("standard"), ctx.actor)
            return Result.success(data, data.pop("warnings"))
        if args["action"] == "schedule":
            data = service.recompute(ctx.actor)
            table = service.table()
            return Result.success(
                {"changed": data["changed"], "rows": table, "warnings": data["warnings"],
                 "unscheduled": data["unscheduled"]},
                data["warnings"],
            )
        if args.get("what") != "load":
            return Result.failure("plan weights needs `load <file>`")
        if not args.get("file"):
            return Result.failure("plan weights load needs the path of the JSON file")
        data = service.load_weights(args["file"], ctx.actor)
        return Result.success(data, data.pop("warnings"))
