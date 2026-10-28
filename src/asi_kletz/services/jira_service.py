"""JiraService: a read-only door to Jira through asi_hopper for the JIRA Live Data window.

The smallest service that serves the ``jira`` verb: ``live`` fetches a JQL and returns the row
convention shared with the sister tool, ``comments`` fetches one issue's comment history newest
first. Nothing here is stored: the result is a view held in memory by whoever asked. Both imports
of ``asi_hopper`` are inside functions, so ``import asi_kletz`` and ``Brain(":memory:")`` never
load it; the same rule the generators follow.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..errors import CommandError

if TYPE_CHECKING:
    from ..brain import Brain

# the issues that involve the person running the tool, past and present, newest first
LIVE_JQL = (
    "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser())"
    " ORDER BY updated DESC"
)
LIVE_LIMIT = 2000
# `jira_live_autofetch` when kletz.toml does not say: the window never connects on its own (0.7.4)
AUTOFETCH_DEFAULT = False
LIVE_FIELDS = (
    "key", "issue_type", "summary", "status", "status_category", "resolution", "priority",
    "assignee", "reporter", "labels", "components", "parent_key", "created", "updated", "due", "url",
)
INSTALL_HINT = "asi_hopper is not installed: run `uv add --editable ../asi_hopper` in asi_kletz"


def _now() -> str:
    """UTC ISO 8601 to the second, the format the event bus stamps on ``ts``."""
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def live_row(record: Any) -> dict[str, Any]:
    """An asi_hopper IssueRecord -> the row of the JIRA Live Data convention (plan section 3.1)."""
    return {
        "key": record.key, "issue_type": record.issue_type, "summary": record.summary,
        "status": record.status, "status_category": record.status_category,
        "resolution": record.resolution, "priority": record.priority,
        "assignee": record.assignee, "reporter": record.reporter,
        "labels": list(record.labels), "components": list(record.components),
        "parent_key": record.parent.key if record.parent else None,
        "created": record.created, "updated": record.updated, "due": record.due, "url": record.url,
    }


def comment_row(comment: Any) -> dict[str, Any]:
    """An asi_hopper Comment -> the comments convention: no ``author_id``, a body that is never ``None``."""
    return {
        "id": comment.id, "author": comment.author, "created": comment.created,
        "updated": comment.updated, "body": comment.body or "",
    }


class JiraService:
    """A read-only door to Jira for the JIRA Live Data window. Never writes to the database."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    def open_hopper(self) -> Any:
        """A read-only, non-interactive Hopper. A missing session is reported, never a browser."""
        try:
            from asi_hopper import Hopper
        except ImportError:
            raise CommandError(INSTALL_HINT) from None
        return Hopper(interactive=False)

    def live_jql(self, override: str | None = None) -> str:
        """``--jql``, else ``jira_live_jql`` in kletz.toml, else the house default."""
        return override or self.brain.config.get("jira_live_jql") or LIVE_JQL

    def live(self, jql: str | None = None, limit: int = LIVE_LIMIT, *, hopper: Any = None) -> dict[str, Any]:
        """Fetch ``jql`` live and return the convention's dict. Nothing is written anywhere.

        Hopper's ``limit`` returns exactly ``limit`` rows whether the query matched ``limit`` or many
        more, so one extra row is asked for: ``truncated`` is true exactly when it arrives, and it
        is dropped.
        """
        if limit < 1:
            raise CommandError("limit must be at least 1")
        jql = self.live_jql(jql)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            from asi_hopper import LIST_FIELDS  # lazy: ``import asi_kletz`` never loads asi_hopper

            # list fields only, 50 a page: a page of full records can exceed the MCP transport's
            # event size limit (the 1 MB default killed every real fetch), a page of these never does
            records = self._guard(
                lambda: hopper.search(jql, fields=LIST_FIELDS, all_pages=True, limit=limit + 1, page_size=50)
            )
        finally:
            if own:
                hopper.close()
        issues = [live_row(r) for r in records[:limit]]
        return {
            "jql": jql,
            "fetched_at": _now(),
            "count": len(issues),
            "truncated": len(records) > limit,
            "issues": issues,
        }

    def comments(self, key: str | None, *, hopper: Any = None) -> dict[str, Any]:
        """The comment history of ``key``, newest first (by ``created``, ties by ``id``)."""
        key = (key or "").strip().upper()
        if not key:
            raise CommandError("jira comments needs an issue key, e.g. HWL-2572")
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            record = self._guard(lambda: hopper.get(key, comments=True))
        finally:
            if own:
                hopper.close()
        items = sorted(
            (comment_row(c) for c in record.comments),
            key=lambda c: (c["created"] or "", c["id"] or ""), reverse=True,
        )
        return {
            "key": record.key, "summary": record.summary, "url": record.url, "status": record.status,
            "fetched_at": _now(), "count": len(items), "comments": items,
        }

    def login(self) -> dict[str, Any]:
        """Sign in to Atlassian in the browser, once, because a person asked (Refresh on a rejected
        session, or ``jira login``): the window never connects on its own.

        The stored session is cleared first: a rejected session keeps a stale client registration
        that the next sign-in would reuse (asi_hopper 0.1.5, `auth status`), so this is `auth logout`
        then `auth login` in one step. One interactive Hopper opens the consent page and waits for
        the approval; the caller runs this off the UI thread, as it runs the fetches.
        """
        try:
            from asi_hopper import Hopper
            from asi_hopper.errors import AuthRequired, HopperError
        except ImportError:
            raise CommandError(INSTALL_HINT) from None
        hopper = Hopper(interactive=True)
        try:
            hopper.session_store().clear()
            account = hopper.whoami()
        except AuthRequired as exc:
            raise CommandError(f"Sign-in failed: {exc}") from None
        except HopperError as exc:
            raise CommandError(f"Sign-in failed: {exc}") from None
        finally:
            hopper.close()
        return {"signed_in": True, "account": account, "signed_in_at": _now()}

    @staticmethod
    def _guard(call: Callable[[], Any]) -> Any:
        """Hopper's errors become command errors: the login hint as is, everything else prefixed."""
        from asi_hopper.errors import AuthRequired, HopperError

        try:
            return call()
        except AuthRequired as exc:
            raise CommandError(str(exc)) from None
        except HopperError as exc:
            raise CommandError(f"Jira read failed: {exc}") from None
