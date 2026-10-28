"""The ``gui`` verb: open the desktop window on the current Brain."""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class GuiCommand(Command):
    verb = "gui"
    help = "Open the desktop window (blocks until it is closed)."
    arguments = (
        Argument(
            "theme",
            "Theme key for this launch only (see `asi-kletz theme`): a palette such as pink-noir or plain; "
            "also $ASI_KLETZ_THEME. Default: the latched preference, else cyan-neon",
            flag=True,
        ),
        Argument(
            "no-server",
            "Open the window without the local automation server for this launch (no session file); "
            "also ASI_KLETZ_AUTOMATION=off",
            flag=True,
            type="bool",
            default=False,
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..gui.app import launch
        from ..gui.theme import ThemeFactory

        launch(ctx.brain, theme=ThemeFactory.resolve(args.get("theme")), server=not args.get("no_server"))
        counts = {s.name: ctx.brain.service(s.name).count() for s in ctx.brain.registry}
        return Result.success({"closed": True, "entities": counts})
