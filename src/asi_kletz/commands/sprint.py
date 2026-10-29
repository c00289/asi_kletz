"""The ``sprint`` verb: the agile rules on top of the generic CRUD of ``sprint`` and ``sprint_item``.

``board`` reads; ``start``, ``close``, ``point``, ``carry``, ``plan`` and ``align`` write through the entity
services, so the audit log and the event bus see them. Over-commitment is a warning, never a refusal; the
capacity (8, fixed) and the cadence (14 days, Tuesday to Monday, the owner's law of 2026-10-29) are the rules
and a sprint cannot be created or edited around them.
"""

from __future__ import annotations

from typing import Any

from ..schema.definitions import CADENCE_NUMBER, CADENCE_START, SPRINT_CAPACITY, SPRINT_RULE
from .base import Argument, Command, Context, Result
from .factory import register_command

RULE = SPRINT_RULE  # the owner's sprint law, 2026-10-29, verbatim; it lives in schema/definitions.py


@register_command
class SprintCommand(Command):
    verb = "sprint"
    help = (
        "Sprints of the Weekly Activity Tracker: board [n] shows points and days; start opens one; "
        "close [n] counts Done and carries the rest; point --item --points; carry --item [--to]; "
        "plan extends the chain with empty Planned sprints to a horizon (--until, else --years 3), "
        "--replan puts the planned dates back on the cadence; align <n> --start <Tuesday> renumbers and "
        "re-dates an existing chain onto the law (--check prints the mapping and changes nothing). The law: " + RULE
    )
    arguments = (
        Argument("action", "board | start | close | point | carry | plan | align", required=True,
                 choices=("board", "start", "close", "point", "carry", "plan", "align")),
        Argument("number", "board / close / start: the sprint number (default: the active sprint); "
                 f"align: the number the sprint starting on --start gets (the picture: {CADENCE_NUMBER})", type="int"),
        Argument("item", "point / carry: the sprint item id", flag=True, type="int"),
        Argument("points", f"point: 1 to the sprint's capacity ({SPRINT_CAPACITY}); 0 clears", flag=True, type="int"),
        Argument("to", "carry: the sprint to carry the item into (default: the next one)", flag=True, type="int"),
        Argument("phase", "start: the lifecycle phase, by number or full value", flag=True),
        Argument("start", "start: first day, a Tuesday (YYYY-MM-DD; default: the day after the previous sprint "
                 f"ends, else --as-of); align: the Tuesday the anchor sprint starts on ({CADENCE_START.isoformat()})",
                 flag=True),
        Argument("end", "start: last day (default and only value: the Monday 13 days after the first)", flag=True),
        Argument("goal", "start: the sprint goal", flag=True),
        Argument("label", "start: the printed label (default SPRINT <n>)", flag=True),
        Argument("as-of", "board: today; close: the close date; start: the default first day", flag=True),
        Argument("until", "plan: the horizon (YYYY-MM-DD); sprints are added while they start on or before it",
                 flag=True),
        Argument("years", "plan: the horizon as years after the last sprint's end (default 3) without --until",
                 flag=True, type="int"),
        Argument("replan", "plan: put every Planned sprint after the active one back on the cadence first",
                 flag=True, type="bool"),
        Argument("check", "align: a dry run; the mapping is reported and nothing is written", flag=True, type="bool"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        sprints = ctx.brain.sprints
        action = args["action"]
        if action == "board":
            return Result.success(sprints.board(args.get("number"), args.get("as_of")))
        if action == "start":
            row, warnings = sprints.start(
                phase=args.get("phase"), start=args.get("start"), end=args.get("end"), goal=args.get("goal"),
                label=args.get("label"), number=args.get("number"), as_of=args.get("as_of"), actor=ctx.actor,
            )
            return Result.success(row, warnings)
        if action == "close":
            data = sprints.close(args.get("number"), args.get("as_of"), ctx.actor)
            return Result.success(data, data.pop("warnings"))
        if action == "plan":
            return Result.success(sprints.plan(
                until=args.get("until"), years=args.get("years"), replan=bool(args.get("replan")), actor=ctx.actor,
            ))
        if action == "align":
            if args.get("number") is None or not args.get("start"):
                return Result.failure("sprint align needs the number and --start <YYYY-MM-DD>, a Tuesday")
            return Result.success(sprints.align(
                int(args["number"]), args["start"], check=bool(args.get("check")), actor=ctx.actor,
            ))
        if args.get("item") is None:
            return Result.failure(f"sprint {action} needs --item <id>")
        if action == "point":
            if args.get("points") is None:
                return Result.failure("sprint point needs --points <n> (0 clears)")
            points = int(args["points"]) or None
            row, warnings = sprints.point(int(args["item"]), points, ctx.actor)
            return Result.success(row, warnings)
        return Result.success(sprints.carry(int(args["item"]), args.get("to"), ctx.actor))
