"""The ``people`` verb: the Outlook address book, searched for a name (0.20.0).

The owner, 2026-10-29: "use the outlook method please". ``people lookup <text>`` asks Outlook desktop on
this machine (``services/outlook_service.py``, COM through PowerShell) for the entries whose name contains
``text`` and answers with the matches, name and email each, as ``Name <email>`` lines ready for a role
parameter. Nothing is stored; nothing runs without this call; a machine without Outlook answers with one
clear error line.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class PeopleCommand(Command):
    verb = "people"
    help = (
        "The people of the Outlook address book on this machine: lookup <text> searches it for a name (part of "
        "one is enough) through Outlook's COM automation and lists the matches, name and email each, as "
        "`Name <email>` lines ready for a role parameter; nothing is stored, nothing runs without this call."
    )
    arguments = (
        Argument("action", "lookup", required=True, choices=("lookup",)),
        Argument("text", "lookup: part of a name (two characters at least)"),
        Argument("limit", "lookup: matches at most (default 30)", flag=True, type="int"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..services import outlook_service

        if not (args.get("text") or "").strip():
            return Result.failure("people lookup needs <text>, part of a name")
        limit = args.get("limit") or outlook_service.LIMIT
        return Result.success(outlook_service.lookup(args["text"], limit=int(limit)))
