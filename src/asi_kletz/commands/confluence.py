"""The ``confluence`` verb: Confluence through asi_hopper, read only (0.23.0, Phase B of the Confluence
integration plan).

``confluence search <text>`` finds pages by title in one space; ``confluence page <id-or-url>`` reads one
record (``--body`` for the Markdown); ``confluence link <row> <id-or-url>`` appends the page's canonical URL to
a Safety Plan row's work product URLs through the ordinary update path (the guard, the audit and the event
apply); ``confluence evidence`` writes a Hopper page bundle of every linked page into the Kletz evidence folder,
audited once; ``confluence check`` reports whether every linked page is still there, its version and whether
it moved since the last bundle. Nothing writes to Confluence. A rejected Atlassian session surfaces as the one
line the Jira verbs show (``run `asi-hopper auth login```); the reads publish nothing (a read is not a change
to the plan) and the evidence publishes ``plan.confluence_evidence``.
"""

from __future__ import annotations

from typing import Any

from ..services.confluence_service import DEFAULT_SPACE, SEARCH_LIMIT
from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class ConfluenceCommand(Command):
    verb = "confluence"
    help = (
        "Confluence through asi_hopper, read only: search <text> [--space KEY] [--limit n] finds the pages of one "
        "space whose title contains the text (newest change first; no Rovo); page <id-or-url> [--body] reads one "
        "page's record, the Markdown body only with --body; link <row> <id-or-url> [--first] appends the page's "
        "canonical URL to the row's work product URLs (first with --first) through the ordinary update path, "
        "refusing a page already on the row; evidence [--rows ...] [--comments] [--out DIR] [--name NAME] writes "
        "a Hopper page bundle of every Confluence page the rows point at into the evidence folder, audited once; "
        "check [--rows ...] reports every linked page's title, version and whether it moved since the last bundle."
    )
    arguments = (
        Argument("action", "search | page | link | evidence | check", required=True,
                 choices=("search", "page", "link", "evidence", "check")),
        Argument("target", "search: part of a page title; page: a page id or URL; link: the Safety Plan row (id "
                 "or uid)"),
        Argument("page", "link: the page id or URL to put on the row"),
        Argument("space", f"search: the space key (default: [confluence] space in kletz.toml, else {DEFAULT_SPACE})",
                 flag=True),
        Argument("limit", f"search: hits at most (default {SEARCH_LIMIT})", flag=True, type="int"),
        Argument("body", "page: include the Markdown body", flag=True, type="bool"),
        Argument("first", "link: put the page first, as the link", flag=True, type="bool"),
        Argument("rows", "evidence / check: only these Safety Plan rows (id or uid; repeatable)", flag=True,
                 type="ref", multiple=True),
        Argument("comments", "evidence: include every page's comments in the bundle", flag=True, type="bool"),
        Argument("out", "evidence: the folder the bundle goes under (default: evidence_dir in kletz.toml, else "
                 "evidence/ beside the database)", flag=True, type="path"),
        Argument("name", "evidence: the bundle folder's own name (default: safety-plan-work-products-<date>)",
                 flag=True),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        service = ctx.brain.confluence
        action = args["action"]
        if action == "search":
            return Result.success(service.search(args.get("target"), args.get("space"), args.get("limit")))
        if action == "page":
            if not (args.get("target") or "").strip():
                return Result.failure("confluence page needs <id-or-url>")
            return Result.success(service.page(args["target"], body=bool(args.get("body"))))
        if action == "link":
            if not (args.get("target") or "").strip() or not (args.get("page") or "").strip():
                return Result.failure("confluence link needs <row> <id-or-url>")
            data = service.link(args["target"], args["page"], first=bool(args.get("first")), actor=ctx.actor)
            return Result.success(data, data.pop("warnings"))
        rows = args.get("rows")
        if rows is not None and not isinstance(rows, (list, tuple)):
            rows = [rows]
        rows = list(rows) if rows else None
        if action == "evidence":
            data = service.evidence(rows, comments=bool(args.get("comments")), out=args.get("out"),
                                    name=args.get("name"), actor=ctx.actor)
            return Result.success(data, data.pop("warnings"))
        data = service.check(rows)
        return Result.success(data, data.pop("warnings"))
