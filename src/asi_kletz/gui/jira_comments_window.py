"""JiraCommentsWindow: one Toplevel per ticket showing its comment history, newest first.

Fed by ``jira comments`` through ``window.execute_quiet`` on a worker thread (a ``BackgroundFetch``
from ``jira_live_screen.py``, polled with ``after`` and applied on the Tk thread, so a gateway
wait never freezes the window; since 0.7.4); it never calls Hopper itself and never touches the
database. ``MainWindow.open_comments`` is the only place it is built. A theme pick destroys it
with the rest of the root's children (a Toplevel is one of them) and the next click brings it
back, one ``jira comments`` later; a fetch in flight at that moment is dropped when it lands.
``Theme.paint`` paints the root only, so the window sets its own background and leaves its ttk
children and ``tk.Text`` bodies to the styles and the option database.
"""

from __future__ import annotations

import math
import time
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..commands import Result
from .background import POLL_MS, WAIT_FETCH_TIMEOUT, BackgroundFetch
from .jira_live_screen import local_clock
from .screens import ScrollableFrame

if TYPE_CHECKING:
    from .main_window import MainWindow

SIZE = (640, 520)
MAX_BODY_LINES = 12
WRAP_GUESS = 80  # characters per display line, for the height of a body


def stamp(value: Any) -> str:
    """``2026-10-26T15:02:11.000-0600`` -> ``2026-10-26 15:02``: Jira's own time, no zone conversion."""
    return str(value or "")[:16].replace("T", " ")


def body_height(body: str) -> int:
    lines = sum(max(1, math.ceil(len(line) / WRAP_GUESS)) for line in body.splitlines() or [""])
    return min(max(lines, 1), MAX_BODY_LINES)


class JiraCommentsWindow(tk.Toplevel):
    def __init__(self, window: MainWindow, key: str) -> None:
        super().__init__(window)
        self.window = window
        self.key = key
        self.url: str | None = None
        self.last: Result | None = None  # the last good fetch, the one on the screen
        self.last_fetch: Result | None = None  # the last Result applied, good or not
        self._fetch: BackgroundFetch | None = None
        self._poll_job: str | None = None
        self.texts: list[tk.Text] = []
        palette = window.theme.palette
        self.title(f"{key} — Comments")
        self.geometry(f"{SIZE[0]}x{SIZE[1]}")
        self.resizable(True, True)
        self.configure(background=palette.bg)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.bind("<F5>", lambda e: self.fetch())

        # the panel styles (Title, Subtitle, Nav) carry the panel background, so the header is a panel
        header = ttk.Frame(self, padding=(10, 8), style="Nav.TFrame")
        header.pack(fill="x")
        self.title_var = tk.StringVar(value=key)
        self.state_var = tk.StringVar()
        self.url_var = tk.StringVar()
        title = ttk.Label(header, textvariable=self.title_var, style="Title.TLabel", wraplength=SIZE[0] - 40)
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.state_var, style="Subtitle.TLabel").grid(
            row=0, column=1, sticky="ne", padx=(12, 0)
        )
        self.url_label = ttk.Label(
            header, textvariable=self.url_var, style="Nav.TLabel", foreground=palette.accent, cursor="hand2"
        )
        self.url_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.url_label.bind("<Button-1>", lambda e: self.open_url())
        header.columnconfigure(0, weight=1)
        header.bind("<Configure>", lambda e: title.configure(wraplength=max(e.width - 160, 200)))

        toolbar = ttk.Frame(self, padding=(10, 6))
        toolbar.pack(fill="x")
        self.refresh_button = ttk.Button(toolbar, text="Refresh", command=self.fetch)
        self.refresh_button.pack(side="left")
        ttk.Button(toolbar, text="Close", command=self.close).pack(side="left", padx=6)
        self.status_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=12)

        self.body = ScrollableFrame(self)
        self.body.pack(fill="both", expand=True)

    # -- data -----------------------------------------------------------
    @property
    def fetching(self) -> bool:
        return self._fetch is not None

    def fetch(self) -> bool:
        """Start one ``jira comments`` on a worker thread; ``False`` while one already runs.

        ``_apply`` paints the Result on the Tk thread once the poll sees it; a failure leaves what
        is listed and the window open. The Refresh button is disabled meanwhile.
        """
        if self._fetch is not None:
            return False
        self._fetch = BackgroundFetch(self.window, "jira", action="comments", key=self.key).start()
        self.status_var.set("Fetching comments …")
        self.refresh_button.state(["disabled"])
        self._poll()
        return True

    def _poll(self) -> None:
        self._poll_job = None
        fetch = self._fetch
        if fetch is None or not self.winfo_exists():
            return  # closed or rebuilt mid-fetch: the worker finishes alone and its Result is dropped
        if not fetch.done:
            self._poll_job = self.after(POLL_MS, self._poll)
            return
        self._fetch = None
        self._apply(fetch.result)  # type: ignore[arg-type]  # `done` means it is set

    def _apply(self, result: Result) -> None:
        self.refresh_button.state(["!disabled"])
        self.window.report_quiet(result)  # the main status bar too, as every Jira screen reports there
        if result.ok:
            self.last = result
            data = result.data or {}
            self._render(data)
            self.status_var.set(f"{data.get('count', 0)} comments · fetched {local_clock(data.get('fetched_at'))}")
        else:
            self.status_var.set("Error: " + ("; ".join(result.errors) or "unknown error"))
        self.last_fetch = result

    def wait_fetch(self, timeout: float = WAIT_FETCH_TIMEOUT) -> Result | None:
        """Test helper: pump the Tk loop until the fetch in flight is applied; the Result applied last."""
        deadline = time.monotonic() + timeout
        while self._fetch is not None:
            if time.monotonic() > deadline:
                raise TimeoutError(f"jira comments did not finish within {timeout} s")
            self.window.update()
            time.sleep(0.01)
        return self.last_fetch

    def destroy(self) -> None:
        if self._poll_job is not None:  # never let a poll fire into a window that is gone
            self.after_cancel(self._poll_job)
            self._poll_job = None
        super().destroy()

    def _render(self, data: dict[str, Any]) -> None:
        inner = self.body.inner
        for child in inner.winfo_children():
            child.destroy()
        self.texts = []
        self.title_var.set(f"{data.get('key') or self.key}  {data.get('summary') or ''}".rstrip())
        self.state_var.set(str(data.get("status") or ""))
        self.url = data.get("url") or None
        self.url_var.set(self.url or "")
        comments = list(data.get("comments") or [])
        if not comments:
            ttk.Label(inner, text="No comments.", style="Muted.TLabel").pack(anchor="w", padx=10, pady=10)
            return
        for comment in comments:  # newest first, as the verb sends them
            meta = f"{comment.get('author') or 'unknown'} · {stamp(comment.get('created'))}"
            updated = comment.get("updated")
            if updated and updated != comment.get("created"):
                meta += f" · edited {stamp(updated)}"
            ttk.Label(inner, text=meta, style="Muted.TLabel").pack(anchor="w", padx=10, pady=(10, 2))
            body = str(comment.get("body") or "")
            text = tk.Text(inner, wrap="word", height=body_height(body), padx=6, pady=4)
            text.insert("1.0", body)
            text.configure(state="disabled")  # read-only, still selectable for copying
            text.pack(fill="x", padx=10)
            self.texts.append(text)
            ttk.Frame(inner, height=1, style="Rule.TFrame").pack(fill="x", padx=10, pady=(8, 0))

    # -- actions --------------------------------------------------------
    def open_url(self) -> None:
        if not self.url:
            return
        if self.window.interactive:
            webbrowser.open(self.url)
        else:
            self.window.set_status(f"Open: {self.url}")

    def close(self) -> None:
        if self.window.comment_windows.get(self.key) is self:
            self.window.comment_windows.pop(self.key, None)
        self.destroy()
