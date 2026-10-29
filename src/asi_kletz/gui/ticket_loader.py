"""TicketLoader: the Load tickets button of a Jira picker, through the JIRA Live Data screen's own path.

A person pressed Load tickets (the window never connects on its own): one ``jira live`` runs on a worker
thread through ``BackgroundFetch`` and ``window.execute_quiet``, exactly as the live screen's Refresh runs
it; a rejected session becomes one ``jira login`` (the browser opens for the approval) and the fetch runs
again, once per press, as the live screen does since 0.11.1; the Result lands on ``window.jira_live`` (the
one place a fetch lives, so the live screen paints the same rows) and the screen's pickers are fed from it.
Nothing from Jira is stored.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..commands import Result
from .jira_live_screen import POLL_MS, WAIT_FETCH_TIMEOUT, BackgroundFetch

if TYPE_CHECKING:
    from .entity_screen import EntityScreen


class TicketLoader:
    def __init__(self, screen: EntityScreen) -> None:
        self.screen = screen
        self.window = screen.window
        self._fetch: BackgroundFetch | None = None
        self._poll_job: str | None = None
        self._login_tried = False  # one sign-in per press: a second rejection reports Offline
        self.last_fetch: Result | None = None

    @property
    def fetching(self) -> bool:
        return self._fetch is not None

    def fetch(self, *, after_login: bool = False) -> bool:
        """Start one ``jira live`` on the worker; ``False`` when one already runs (a second press is ignored)."""
        if self._fetch is not None:
            return False
        if not after_login:
            self._login_tried = False
        self._fetch = BackgroundFetch(self.window, "jira", action="live").start()
        self.window.set_status("Loading Jira tickets …")
        self.screen.set_pickers_busy(True)
        self._poll()
        return True

    def _sign_in(self) -> None:
        self._login_tried = True
        self._fetch = BackgroundFetch(self.window, "jira", action="login").start()
        self.window.set_status("Signing in to Atlassian … approve in the browser, the tickets follow")
        self._poll()

    def _poll(self) -> None:
        self._poll_job = None
        fetch = self._fetch
        if fetch is None or not self.screen.winfo_exists():
            return  # cancelled, or the screen is gone: the worker finishes alone and its Result is dropped
        if not fetch.done:
            self._poll_job = self.screen.after(POLL_MS, self._poll)
            return
        self._fetch = None
        result: Result = fetch.result  # type: ignore[assignment]  # `done` means it is set
        if fetch.args.get("action") == "login":
            self._apply_login(result)
        else:
            self._apply(result)

    def _apply_login(self, result: Result) -> None:
        if result.ok:
            account = (result.data or {}).get("account") or {}
            who = account.get("display_name") or account.get("name") or account.get("account_id") or "Atlassian"
            self.window.set_status(f"Signed in to Atlassian as {who}; loading tickets …")
            self.fetch(after_login=True)
            return
        self.screen.set_pickers_busy(False)
        self.window.report_quiet(result)
        self.last_fetch = result

    def _apply(self, result: Result) -> None:
        if not result.ok and not self._login_tried and self._is_rejected(result):
            self._sign_in()
            return
        if result.ok:
            self._login_tried = False
        self.screen.set_pickers_busy(False)
        self.window.report_quiet(result)
        if result.ok or self.window.jira_live is None:
            self.window.jira_live = result
        if result.ok:
            self.window.set_status(f"Jira: {result.data['count']} tickets loaded; pick one per deliverable")
        self.last_fetch = result
        self.screen.feed_pickers()

    @staticmethod
    def _is_rejected(result: Result) -> bool:
        return any("no Atlassian session" in e for e in result.errors)

    def wait_fetch(self, timeout: float = WAIT_FETCH_TIMEOUT) -> Result | None:
        """Test helper: pump the Tk loop until the fetch in flight is applied; the Result applied last."""
        deadline = time.monotonic() + timeout
        while self._fetch is not None:
            if time.monotonic() > deadline:
                raise TimeoutError(f"jira live did not finish within {timeout} s")
            self.window.update()
            time.sleep(0.01)
        return self.last_fetch

    def cancel(self) -> None:
        if self._poll_job is not None:
            try:
                self.screen.after_cancel(self._poll_job)
            except Exception:  # noqa: BLE001  (the screen may already be gone)
                pass
            self._poll_job = None


__all__: list[Any] = ["TicketLoader"]
