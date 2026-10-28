"""The ``tracker`` verb: the Weekly Activity Tracker in and out of the database.

``tracker import <file>`` reads the engineer's text once; ``tracker build history|week`` writes the
text back as a view (``<out>/tracker_history.txt``, ``<out>/tracker_week.txt``); ``tracker add
<text>`` appends a line to a section of the current week. Nothing of the Safety Plan changes.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command

OUT_HELP = "build: output folder (default: $ASI_KLETZ_OUT, `out` in kletz.toml, or out/ next to the database)"


@register_command
class TrackerCommand(Command):
    verb = "tracker"
    help = (
        "The Weekly Activity Tracker: import <file> reads the text into sprints, items and weeks; "
        "build history|week writes it back out; add <text> appends a line to the current week."
    )
    arguments = (
        Argument("action", "import | build | add", required=True, choices=("import", "build", "add")),
        Argument("what", "import: the tracker text file; build: history | week; add: the line to append"),
        Argument("mode", "import: replace | merge (default: replace into an empty tracker, else merge)",
                 flag=True, choices=("replace", "merge")),
        Argument("out", OUT_HELP, flag=True, type="path"),
        Argument("jira", "build: refresh the active sprint's Jira lines through `jira live` first",
                 flag=True, type="bool"),
        Argument("as-of", "build / add: the date to build for or add to (YYYY-MM-DD, default today)", flag=True),
        Argument("section", "add: Outcomes | Issues | Note (default Outcomes)", flag=True,
                 choices=("Outcomes", "Issues", "Note")),
        Argument("week", "add: the week's start date (default: the week of --as-of)", flag=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        tracker = ctx.brain.tracker
        action, what = args["action"], args.get("what")
        if action == "import":
            if not what:
                return Result.failure("tracker import needs the path of the tracker text file")
            data = tracker.import_file(what, args.get("mode"), ctx.actor)
            return Result.success(data, data.pop("warnings"))
        if action == "build":
            if what not in ("history", "week"):
                return Result.failure("tracker build needs `history` or `week`")
            data = tracker.build(what, args.get("out"), args.get("as_of"), bool(args.get("jira")), ctx.actor)
            return Result.success(data, data.pop("warnings"))
        if not what:
            return Result.failure("tracker add needs the text to append")
        row = tracker.add_line(what, args.get("section") or "Outcomes", args.get("week"), args.get("as_of"), ctx.actor)
        return Result.success(row)
