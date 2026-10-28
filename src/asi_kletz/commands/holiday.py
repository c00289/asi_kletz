"""The ``holiday`` verb: the holidays the sprint planner skips.

``holiday load <file>`` upserts a JSON list of ``{"date", "name", "status"[, "note"]}`` by date and name
(``data/us-holidays-2026-2029.json`` is the seed). Everything else on holidays is the generic CRUD:
``list holiday``, ``create holiday --set date=... --set name=...``, ``update holiday <ref> --set status=confirmed``.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class HolidayCommand(Command):
    verb = "holiday"
    help = (
        "Holidays the sprint planner skips (a sprint spans 10 business days; weekends and holidays do not "
        "count): load <file> upserts a JSON list of {date, name, status[, note]} by date and name."
    )
    arguments = (
        Argument("action", "load", required=True, choices=("load",)),
        Argument("file", "load: the JSON file (a list of holidays, or {\"holidays\": [...]})", type="path"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        if not args.get("file"):
            return Result.failure("holiday load needs the path of the JSON file")
        return Result.success(ctx.brain.holidays.load(args["file"], ctx.actor))
