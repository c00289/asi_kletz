"""The ``standards`` verb: the parametrised standards a Safety Plan row can be exported into.

``standards list`` reads the standards directory (``standards_dir`` in kletz.toml, default
``../asi_standards``): one entry per folder holding a Gutenberg Markdown source of the same name, with its
title and its parameters (the document-level names a person supplies, the count of row-level names Kletz
supplies). ``standards for --row <id>`` says which of them a plan row has, by its QMS reference flags. The
export itself is ``plan export --row <id>``.
"""

from __future__ import annotations

from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class StandardsCommand(Command):
    verb = "standards"
    help = (
        "The parametrised standards (asi_standards): list reads the standards directory; for --row <id> names "
        "the standards a Safety Plan row has, by its QMS reference flags."
    )
    arguments = (
        Argument("action", "list | for", required=True, choices=("list", "for")),
        Argument("row", "for: the Safety Plan row (id or uid)", flag=True, type="ref"),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.standards
        if args["action"] == "list":
            return Result.success(
                {"standards_dir": str(service.root()), "standards": [s.to_dict() for s in service.list()]}
            )
        if args.get("row") is None:
            return Result.failure("standards for needs --row <id>")
        row = ctx.brain.service("safety_plan_row").get(args["row"])
        return Result.success({
            "row": row["id"], "order": row.get("order"), "standards_dir": str(service.root()),
            "standards": [s.to_dict() for s in service.for_row(row)],
        })
