"""The ``plan`` verb: the Safety Plan's points, the sprint and deadline calculated from them, the standards an
export fills, and since 0.20.0 the work product URLs (``plan urls --placeholder <url>``; since 0.22.0 also
``--audit`` and ``--replace <old-url> <new-url>``, Phase A of the Confluence integration plan).

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
        "the parameters filled (the weight the schedule used; the sprint's end; the Jira ticket's status; a "
        "role's people inline, Name (email), alphabetical; the work product's first URL and all of them); "
        "parameters --row <id> prints that value set without building, with the people per role and the roles "
        "still legacy or empty; tickets lists every work product with its Jira key and the ones still without "
        "one; urls --placeholder <url> puts that URL on every work product that has none (idempotent; --check "
        "names the rows and writes nothing); urls --audit [--rows <id>...] reads every work product's URLs by "
        "kind (confluence, jira, sharepoint, placeholder, other) and lists the findings, writing nothing: a "
        "placeholder still present, no Confluence page where the work product location names Confluence, a "
        "Jira URL that disagrees with the row's Jira key; urls --replace <old-url> <new-url> puts the new URL "
        "where the old one stands on every row that carries it, one audited step (--check names the rows and "
        "writes nothing; a row that already carries the new URL is left alone with a warning)."
    )
    arguments = (
        Argument("action", "schedule | weights | export | parameters | tickets | urls", required=True,
                 choices=("schedule", "weights", "export", "parameters", "tickets", "urls")),
        Argument("what", "weights: load"),
        Argument("file", "weights load: the JSON list of {id, order, deliverable, points[, uid]}", type="path"),
        Argument("row", "export / parameters: the Safety Plan row (id or uid)", flag=True, type="ref"),
        Argument("out", "export: the output folder (default: $ASI_KLETZ_OUT, `out` in kletz.toml, or out/ next to "
                 "the database)", flag=True, type="path"),
        Argument("standard", "export / parameters: one standard's folder (default: every standard the row has)",
                 flag=True),
        Argument("placeholder", "urls: the URL every row with no work product URL gets", flag=True),
        Argument("audit", "urls: the findings on the work product URLs, by kind; nothing is written",
                 flag=True, type="bool"),
        Argument("rows", "urls --audit: only these Safety Plan rows (id or uid; repeatable)", flag=True, type="ref",
                 multiple=True),
        Argument("replace", "urls: the old URL and the new one; every row carrying the old gets the new in its place",
                 flag=True, nargs=2),
        Argument("check", "urls: a dry run; the rows that would be filled or changed are named and nothing is "
                 "written", flag=True, type="bool"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.schedule
        if args["action"] == "tickets":
            return Result.success(tickets(ctx.brain))
        if args["action"] == "urls":
            return urls(ctx, args)
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


def urls(ctx: Context, args: dict[str, Any]) -> Result:
    """``plan urls``: ``--audit`` (the findings, a list; ``ok`` even with findings, they are data), ``--replace
    <old> <new>`` (the rows changed, the refusals as warnings) or ``--placeholder <url>`` (0.20.0)."""
    work_products = ctx.brain.work_products
    check = bool(args.get("check"))
    if args.get("audit"):
        rows = args.get("rows")
        if rows is not None and not isinstance(rows, (list, tuple)):
            rows = [rows]
        return Result.success(work_products.audit(list(rows) if rows else None))
    replace = args.get("replace")
    if replace is not None:
        pair = [str(p) for p in replace] if isinstance(replace, (list, tuple)) else [str(replace)]
        if len(pair) != 2:
            return Result.failure("plan urls --replace needs two URLs: the old and the new")
        data = work_products.replace(pair[0], pair[1], actor=ctx.actor, check=check)
        return Result.success(data, data.pop("warnings"))
    if (args.get("placeholder") or "").strip():
        return Result.success(work_products.fill_placeholder(args["placeholder"], actor=ctx.actor, check=check))
    return Result.failure("plan urls needs --placeholder <url>, --audit or --replace <old-url> <new-url>")


def tickets(brain: Any) -> dict[str, Any]:
    """Every work product with its Jira key, in plan order, and the orders of the ones still without one
    (the owner, 2026-10-29: "every work product needs to be linked to some Jira ticket")."""
    from ..generate import plan_queries as pq

    rows = []
    for row in pq.all_rows(brain):
        key = (row.get("jira_key") or "").strip().upper() or None
        rows.append({
            "id": row["id"], "order": row.get("order"), "deliverable": pq.one_line(row.get("deliverable") or "", 70),
            "status": row.get("status"), "jira_key": key, "missing": key is None,
        })
    missing = [r["order"] if r["order"] is not None else r["id"] for r in rows if r["missing"]]
    return {"rows": rows, "count": len(rows), "with_ticket": len(rows) - len(missing), "missing": missing}
