"""The ``jira`` verb: Jira through asi_hopper, read only.

``jira live`` fetches a JQL for the JIRA Live Data window and publishes ``jira.live``;
``jira comments <key>`` fetches one issue's comment history for its comments view and publishes
nothing (a lookup changes nothing a front end holds). Neither writes the database or the audit
log: the audit log records changes to the Safety Plan, and a read is not one.
"""

from __future__ import annotations

from typing import Any

from ..services.jira_service import LIVE_JQL, LIVE_LIMIT
from .base import Argument, Command, Context, Result
from .factory import register_command


@register_command
class JiraCommand(Command):
    verb = "jira"
    help = (
        "Jira through asi_hopper, read only: live <jql> fetch for the JIRA Live Data window, "
        "comments <key> for its comments view, login to sign in to Atlassian in the browser (clears the stored "
        "session first)."
    )
    arguments = (
        Argument("action", "live | comments | login", required=True, choices=("live", "comments", "login")),
        Argument("key", "Issue key for `comments`, e.g. HWL-2572"),
        Argument("jql", f"JQL for `live` (default: jira_live_jql in kletz.toml, else: {LIVE_JQL})", flag=True),
        Argument("limit", "For `live`: most issues to fetch (default 2000)", flag=True, type="int", default=LIVE_LIMIT),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        if args["action"] == "comments":
            return Result.success(ctx.brain.jira.comments(args.get("key")))
        if args["action"] == "login":
            return Result.success(ctx.brain.jira.login())
        limit = args.get("limit")
        limit = LIVE_LIMIT if limit is None else int(limit)  # 0 is a value, not an absence
        data = ctx.brain.jira.live(args.get("jql"), limit)
        ctx.brain.events.publish(
            "jira.live", jql=data["jql"], count=data["count"], truncated=data["truncated"],
            fetched_at=data["fetched_at"], actor=ctx.actor,
        )
        warnings = [f"fetch truncated at {limit} issues; narrow the JQL or raise --limit"] if data["truncated"] else []
        return Result.success(data, warnings)
