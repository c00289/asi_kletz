"""The ``theme`` verb: list the palette catalog, or latch a theme so it survives restarts.

Everything the window's theme picker does, this command does: validate the key, write the
preference, publish ``theme.changed`` so a window open in this process repaints. ``--theme``
on the window and ``$ASI_KLETZ_THEME`` are one-off views and never write the preference; only
this verb does, whether called from the CLI, from Python, or by the picker.
"""

from __future__ import annotations

from typing import Any

from ..errors import NotFound
from ..prefs import prefs_path, read_prefs, write_prefs
from .base import Argument, Command, Context, Result
from .factory import register_command


def describe_themes() -> dict[str, Any]:
    """The catalog, the latched key, the key this process resolves to, and where the preference lives."""
    from ..gui.theme import ThemeFactory

    return {
        "theme": ThemeFactory.resolve(),
        "latched": read_prefs().get("theme"),
        "default": ThemeFactory.default_key(),
        "prefs": str(prefs_path()),
        "themes": [
            {
                "key": entry.key, "title": entry.title, "family": entry.family, "tone": entry.tone,
                "primary": entry.palette.primary, "accent": entry.palette.accent,
            }
            for entry in ThemeFactory.entries()
        ],
    }


@register_command
class ThemeCommand(Command):
    verb = "theme"
    help = "Latch the window theme by key (survives restarts), or list the catalog when no key is given."
    arguments = (
        Argument("key", "Theme key such as pink-noir or plain; omit to list the catalog"),
        Argument("list", "List the catalog (the same as giving no key)", flag=True, type="bool", default=False),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..gui.theme import ThemeFactory

        key = args.get("key")
        if key:
            try:
                theme = ThemeFactory.create(key)
            except NotFound as exc:
                return Result.failure(str(exc))
            write_prefs(theme=theme.key)
            ctx.brain.events.publish("theme.changed", theme=theme.key, actor=ctx.actor)
        return Result.success(describe_themes())
