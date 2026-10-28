"""The ``sprint`` verb: the agile rules on top of the generic CRUD of ``sprint`` and ``sprint_item``.

``board`` reads; ``start``, ``close``, ``point`` and ``carry`` write through the entity services, so
the audit log and the event bus see them. Capacity is a warning, never a refusal.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class SprintCommand(Command):
    verb = "sprint"
    help = (
        "Sprints of the Weekly Activity Tracker: board [n] shows points and days; start opens one; "
        "close [n] counts Done and carries the rest; point --item --points; carry --item [--to]."
    )
    arguments = (
        Argument("action", "board | start | close | point | carry", required=True,
                 choices=("board", "start", "close", "point", "carry")),
        Argument("number", "board / close / start: the sprint number (default: the active sprint)", type="int"),
        Argument("item", "point / carry: the sprint item id", flag=True, type="int"),
        Argument("points", "point: 1 to the sprint's capacity; 0 clears", flag=True, type="int"),
        Argument("to", "carry: the sprint to carry the item into (default: the next one)", flag=True, type="int"),
        Argument("phase", "start: the lifecycle phase, by number or full value", flag=True),
        Argument("start", "start: first day (YYYY-MM-DD, default: --as-of)", flag=True),
        Argument("end", "start: last day (default: start + sprint_days)", flag=True),
        Argument("capacity", "start: points (default: sprint_capacity in kletz.toml, else 10)", flag=True, type="int"),
        Argument("goal", "start: the sprint goal", flag=True),
        Argument("label", "start: the printed label (default SPRINT <n>)", flag=True),
        Argument("as-of", "board: today; close: the close date; start: the default first day", flag=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        sprints = ctx.brain.sprints
        action = args["action"]
        if action == "board":
            return Result.success(_board(sprints.board(args.get("number"), args.get("as_of"))))
        if action == "start":
            row, warnings = sprints.start(
                phase=args.get("phase"), start=args.get("start"), end=args.get("end"), capacity=args.get("capacity"),
                goal=args.get("goal"), label=args.get("label"), number=args.get("number"), as_of=args.get("as_of"),
                actor=ctx.actor,
            )
            return Result.success(row, warnings)
        if action == "close":
            data = sprints.close(args.get("number"), args.get("as_of"), ctx.actor)
            return Result.success(data, data.pop("warnings"))
        if args.get("item") is None:
            return Result.failure(f"sprint {action} needs --item <id>")
        if action == "point":
            if args.get("points") is None:
                return Result.failure("sprint point needs --points <n> (0 clears)")
            points = int(args["points"]) or None
            row, warnings = sprints.point(int(args["item"]), points, ctx.actor)
            return Result.success(row, warnings)
        return Result.success(sprints.carry(int(args["item"]), args.get("to"), ctx.actor))


def _board(data: dict[str, Any]) -> dict[str, Any]:
    """The board with its warnings folded in as data too (the Result carries them as warnings as well)."""
    return data
