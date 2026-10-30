"""JiraLiveScreen: the JIRA Live Data window, a read-only view over Jira held in memory.

One action, Refresh, runs ``jira live`` through the window; the Result lives on the window object
(``window.jira_live``), so a theme pick, which rebuilds every screen, repaints without a second
fetch. The text box and the drop-downs filter the last fetch locally and never cost a Jira call.
The first column is ``[Comments]``, the per-row button: a click there opens the ticket's comments
window. Nothing here reads or writes the database; the one table is not even read by this screen.

The fetch never runs on the Tk thread (0.7.4). A ``jira live`` of the house default is up to 2,000
issues at 50 a page, tens of seconds on a good link, and any gateway wait came on top: run
synchronously it froze the whole window. ``fetch`` starts a ``BackgroundFetch`` (a daemon thread
that calls ``window.execute_quiet`` and touches no widget), the Tk thread polls it with ``after``
and applies the Result here, on the Tk thread, as before. While it runs the Refresh button is
disabled and a second ``fetch`` is ignored; a screen destroyed meanwhile (theme pick, close)
cancels its poll and the worker's Result is dropped when it lands. The screen never connects on
its own: ``on_show`` fetches only when ``jira_live_autofetch`` is explicitly true.
"""

from __future__ import annotations

import datetime as dt
import time
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any

from ..commands import Result
from ..services.jira_service import AUTOFETCH_DEFAULT, LIVE_LIMIT
from .background import POLL_MS, WAIT_FETCH_TIMEOUT, BackgroundFetch
from .screens import Screen, fit_columns

ALL = "(all)"
NONE = "(none)"
COMMENTS_LABEL = "[Comments]"
SUMMARY_TRUNCATE = 90
CATEGORY_ORDER = ("new", "indeterminate", "done")
FILTER_FIELDS = (
    ("status", "Status"), ("status_category", "Category"), ("issue_type", "Type"),
    ("priority", "Priority"), ("assignee", "Assignee"),
)
# column id, heading, starting width, stretch (plan section 3.5); ``fit_columns`` has the last word after a fill
COLUMNS: tuple[tuple[str, str, int, bool], ...] = (
    ("comments", "Comments", 90, False),
    ("key", "Key", 90, False),
    ("issue_type", "Type", 90, False),
    ("summary", "Summary", 420, True),
    ("status", "Status", 130, False),
    ("status_category", "Category", 110, False),
    ("priority", "Priority", 100, False),
    ("assignee", "Assignee", 150, False),
    ("reporter", "Reporter", 150, False),
    ("labels", "Labels", 160, False),
    ("parent_key", "Parent", 90, False),
    ("created", "Created", 100, False),
    ("updated", "Updated", 100, False),
    ("due", "Due", 100, False),
    ("resolution", "Resolution", 110, False),
)
HEADINGS = {column: heading for column, heading, _, _ in COLUMNS}
DATE_COLUMNS = {"created", "updated", "due"}
COMMENTS_COLUMN = "#1"


def cell_text(column: str, value: Any) -> str:
    """The display text of one cell: dates to ``YYYY-MM-DD``, labels joined, the summary clipped."""
    if column == "comments":
        return COMMENTS_LABEL
    if value is None:
        return ""
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value)
    text = str(value).replace("\n", " ")
    if column in DATE_COLUMNS:
        return text[:10]
    if column == "summary" and len(text) > SUMMARY_TRUNCATE:
        return text[: SUMMARY_TRUNCATE - 1] + "…"
    return text


def key_sort_value(key: Any) -> tuple[str, int]:
    """``HWL-2620`` -> ``("HWL", 2620)``: keys sort numerically, so HWL-2620 comes after HWL-999."""
    text = str(key or "")
    prefix, sep, number = text.rpartition("-")
    if sep and number.isdigit():
        return (prefix, int(number))
    return (text, -1)


def local_clock(fetched_at: Any) -> str:
    """``fetched_at`` (UTC ISO 8601) as local ``hh:mm``; the text itself when it does not parse."""
    try:
        return dt.datetime.fromisoformat(str(fetched_at)).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return str(fetched_at or "?")


class JiraLiveScreen(Screen):
    """Toolbar (Refresh, status line), filter row, and the 15-column table with ``[Comments]`` first."""

    # -- layout ---------------------------------------------------------
    def build(self) -> None:
        self.sort_column: str | None = None
        self.sort_desc = False
        self.columns = [column for column, _, _, _ in COLUMNS]

        # the fetch in flight, its poll and the last Result applied (None between fetches / before any)
        self._fetch: BackgroundFetch | None = None
        self._poll_job: str | None = None
        self._user_fetch = False  # the fetch in flight was asked for by a person (Refresh), not the first show
        self._login_tried = False  # one sign-in per Refresh: a second rejection shows Offline
        self.last_fetch: Result | None = None

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        self.refresh_button = ttk.Button(toolbar, text="Refresh", command=self.fetch)
        self.refresh_button.pack(side="left")
        self.status_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=12)

        # The filters as a grid, three equal columns that fit any window width (one long row clipped
        # at the right edge). Row one: what and where it stands (find, status, category). Row two:
        # kind, urgency, owner (type, priority, assignee). Reset and the count close the grid.
        self.filters: dict[str, tk.StringVar] = {}
        self.boxes: dict[str, ttk.Combobox] = {}
        grid = ttk.Frame(self)
        grid.pack(fill="x", pady=(0, 8))
        for col in range(3):
            grid.columnconfigure(col, weight=1, uniform="filters")
        grid.columnconfigure(3, weight=0)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._populate())
        ttk.Label(grid, text="FIND", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(grid, textvariable=self.filter_var).grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(0, 6))
        for slot, (field, caption) in enumerate(FILTER_FIELDS, start=1):  # cell 0 is Find
            row, col = divmod(slot, 3)
            ttk.Label(grid, text=caption.upper(), style="Muted.TLabel").grid(row=row * 2, column=col, sticky="w")
            var = tk.StringVar(value=ALL)
            box = ttk.Combobox(grid, textvariable=var, values=[ALL], state="readonly")
            box.grid(row=row * 2 + 1, column=col, sticky="ew", padx=(0, 12), pady=(0, 6))
            box.bind("<<ComboboxSelected>>", lambda _e: self._populate())
            self.filters[field] = var
            self.boxes[field] = box
        tail = ttk.Frame(grid)
        tail.grid(row=3, column=3, sticky="se", pady=(0, 6))
        ttk.Button(tail, text="Clear filters", command=self.clear_filters).pack(side="left", padx=(0, 10))
        self.count_var = tk.StringVar(value="0 of 0 issues")
        ttk.Label(tail, textvariable=self.count_var, style="Muted.TLabel").pack(side="left")

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=self.columns, show="headings", selectmode="browse")
        self.ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.xbar = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.ybar.set, xscrollcommand=self.xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.ybar.grid(row=0, column=1, sticky="ns")
        self.xbar.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        for column, heading, width, stretch in COLUMNS:
            if column == "comments":  # the per-row button: no sort, centred
                self.tree.heading(column, text=heading)
                self.tree.column(column, width=width, minwidth=width, stretch=False, anchor="center")
                continue
            self.tree.heading(column, text=heading, command=lambda c=column: self.sort_by(c))
            self.tree.column(column, width=width, minwidth=40, stretch=stretch)
        # stripes set only `background`, `muted` only `foreground`: a done row is dim on its stripe
        self.tree.tag_configure("muted", foreground=self.window.theme.palette.muted)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda e: self.open_selected())
        self.tree.bind("<Key-c>", self._on_key_c)
        self.tree.bind("<Motion>", self._on_motion)

    # -- data -----------------------------------------------------------
    @property
    def issues(self) -> list[dict[str, Any]]:
        """The rows of the last good fetch, or none."""
        result = self.window.jira_live
        if result is None or not result.ok or not result.data:
            return []
        return list(result.data.get("issues") or [])

    def row(self, key: str) -> dict[str, Any] | None:
        return next((r for r in self.issues if r.get("key") == key), None)

    @property
    def fetching(self) -> bool:
        return self._fetch is not None

    def fetch(self, *, user: bool = True, after_login: bool = False) -> bool:
        """The Refresh button: start one ``jira live`` on a worker thread. ``False`` when one already runs.

        The Result is applied by ``_apply`` on the Tk thread once the poll sees it; the button is
        disabled meanwhile, and a second call (F5, a stray click) is ignored, not queued. ``user``
        says a person pressed Refresh: only then may a rejected session turn into a sign-in
        (``_sign_in``); the opt-in first-show fetch never opens a browser.
        """
        if self._fetch is not None:
            return False
        self._user_fetch = user
        if not after_login:
            self._login_tried = False  # one sign-in per Refresh a person presses
        self._fetch = BackgroundFetch(self.window, "jira", action="live").start()
        self.status_var.set(f"Fetching Jira … up to {LIVE_LIMIT} issues, this can take a minute")
        self.window.set_status("Fetching Jira …")
        self.refresh_button.state(["disabled"])
        self._poll()
        return True

    def _sign_in(self) -> None:
        """A Refresh met a rejected session: run ``jira login`` on the worker (the browser opens for the
        approval), then fetch again. Once per Refresh: a second rejection shows Offline as before."""
        self._login_tried = True
        self._fetch = BackgroundFetch(self.window, "jira", action="login").start()
        self.status_var.set("Signing in to Atlassian … approve in the browser, the fetch follows")
        self.window.set_status("Signing in to Atlassian …")
        self.refresh_button.state(["disabled"])
        self._poll()

    def _poll(self) -> None:
        self._poll_job = None
        fetch = self._fetch
        if fetch is None or not self.winfo_exists():
            return  # cancelled, or the screen is gone: the worker finishes alone and its Result is dropped
        if not fetch.done:
            self._poll_job = self.after(POLL_MS, self._poll)
            return
        self._fetch = None
        if fetch.verb == "jira" and fetch.args.get("action") == "login":
            self._apply_login(fetch.result)  # type: ignore[arg-type]
            return
        self._apply(fetch.result)  # type: ignore[arg-type]  # `done` means it is set

    def _apply_login(self, result: Result) -> None:
        """The sign-in's Result, on the Tk thread: signed in means the Refresh goes on; failed means Offline."""
        if result.ok:
            account = (result.data or {}).get("account") or {}
            who = account.get("display_name") or account.get("name") or account.get("account_id") or "Atlassian"
            self.window.set_status(f"Signed in to Atlassian as {who}; fetching …")
            self.fetch(user=True, after_login=True)
            return
        self.refresh_button.state(["!disabled"])
        self.window.report_quiet(result)
        first = result.errors[0] if result.errors else "unknown error"
        self.status_var.set(f"{first} · press Refresh")
        self.last_fetch = result  # the Result applied last, for whoever waits on the Refresh

    def _apply(self, result: Result) -> None:
        """A fetched Result, on the Tk thread: a failure after a success keeps the rows.

        A rejected session on a Refresh a person pressed becomes one sign-in (``_sign_in``) and the
        Result is held back until the fetch after it; the first-show fetch, and a second rejection
        in the same Refresh, show Offline as before.
        """
        if not result.ok and self._user_fetch and not self._login_tried and self._is_rejected(result):
            self._sign_in()
            return
        if result.ok:
            self._login_tried = False  # a fetch that succeeds ends the Refresh cleanly
        self.refresh_button.state(["!disabled"])
        self.window.report_quiet(result)  # `Error: ...` / `Warning: ...` in the status bar, no dialog
        if result.ok or self.window.jira_live is None:
            self.window.jira_live = result
        if result.ok and not result.warnings:
            self.window.set_status(f"Jira: {result.data['count']} issues fetched")
        self.last_fetch = result
        self.refresh()

    @staticmethod
    def _is_rejected(result: Result) -> bool:
        """asi_hopper's ``AuthRequired`` text, passed through by the ``jira`` verb as the error."""
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

    def destroy(self) -> None:
        if self._poll_job is not None:  # never let a poll fire into widgets that are gone
            self.after_cancel(self._poll_job)
            self._poll_job = None
        super().destroy()

    def refresh(self) -> None:
        """Repaint from ``window.jira_live``; never fetches."""
        result = self.window.jira_live
        if result is None:
            self.status_var.set("No fetch yet · press Refresh")
        elif not result.ok:
            first = result.errors[0] if result.errors else "unknown error"
            self.status_var.set(f"Offline: {first} · press Refresh")
        else:
            data = result.data or {}
            text = (
                f"{data.get('count', 0)} issues · fetched {local_clock(data.get('fetched_at'))} · {data.get('jql', '')}"
            )
            if data.get("truncated"):
                text += f" · truncated at {data.get('count')}"
            self.status_var.set(text)
        self._rebuild_filters()
        self._populate()

    def on_show(self) -> None:
        """A repaint; the one fetch on first show only when kletz.toml says ``jira_live_autofetch = true``."""
        self.refresh()  # "No fetch yet · press Refresh" until the engineer asks
        if self.window.jira_live is None and self.brain.config.get("jira_live_autofetch", AUTOFETCH_DEFAULT) is True:
            self.fetch(user=False)  # the opt-in first fetch: a rejected session is reported, never a browser

    # -- filters and sorting --------------------------------------------
    def _rebuild_filters(self) -> None:
        """Combobox values from the distinct values present; a choice that is gone resets to ``(all)``."""
        issues = self.issues
        for field, var in self.filters.items():
            present = {r.get(field) for r in issues}
            values = sorted((v for v in present if v is not None), key=lambda v: str(v).casefold())
            if field == "status_category":
                values = [c for c in CATEGORY_ORDER if c in present] + [v for v in values if v not in CATEGORY_ORDER]
            choices = [ALL, *values] + ([NONE] if None in present else [])
            self.boxes[field].configure(values=choices)
            if var.get() not in choices:
                var.set(ALL)

    def _visible_rows(self) -> list[dict[str, Any]]:
        rows = self.issues
        needle = self.filter_var.get().strip().casefold()
        if needle:
            rows = [
                r for r in rows
                if needle in (r.get("key") or "").casefold() or needle in (r.get("summary") or "").casefold()
            ]
        for field, var in self.filters.items():
            choice = var.get()
            if choice == ALL:
                continue
            want = None if choice == NONE else choice
            rows = [r for r in rows if r.get(field) == want]
        column = self.sort_column
        if column:  # None sorts last in both directions
            present = [r for r in rows if r.get(column) is not None]
            missing = [r for r in rows if r.get(column) is None]
            rows = sorted(present, key=lambda r: self._sort_value(r, column), reverse=self.sort_desc) + missing
        return rows

    @staticmethod
    def _sort_value(row: dict[str, Any], column: str) -> Any:
        """Sort on the row's value, not the cell text: full timestamps for dates, numbers for keys."""
        value = row.get(column)
        if column == "key":
            return key_sort_value(value)
        if isinstance(value, list | tuple):
            return ", ".join(str(v) for v in value).casefold()
        return str(value).casefold()

    def _populate(self) -> None:
        issues = self.issues
        rows = self._visible_rows()
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            iid = str(r.get("key") or "")
            if not iid or self.tree.exists(iid):
                continue
            self.tree.insert("", "end", iid=iid, values=[cell_text(c, r.get(c)) for c in self.columns])
        self.window.theme.stripe(self.tree)  # replaces every tag tuple, so the muted tag goes on after it
        for r in rows:
            iid = str(r.get("key") or "")
            if r.get("status_category") == "done" and self.tree.exists(iid):
                self.tree.item(iid, tags=(*self._tags(iid), "muted"))
        fit_columns(self.tree)
        self.count_var.set(f"{len(rows)} of {len(issues)} issues")

    def _tags(self, iid: str) -> tuple[str, ...]:
        tags = self.tree.item(iid, "tags")
        return (tags,) if isinstance(tags, str) else tuple(tags)

    def sort_by(self, column: str, desc: bool | None = None) -> None:
        """The same column toggles the direction; a new column starts ascending."""
        if desc is None:
            desc = not self.sort_desc if self.sort_column == column else False
        self.sort_column, self.sort_desc = column, desc
        self._mark_headings()
        self._populate()

    def _mark_headings(self) -> None:
        for column, heading in HEADINGS.items():
            if column == "comments":
                continue
            mark = ""
            if column == self.sort_column:
                mark = " ▼" if self.sort_desc else " ▲"
            self.tree.heading(column, text=heading + mark)

    def clear_filters(self) -> None:
        """Text box empty, every combobox ``(all)``, no sort: the server's order again."""
        self.filter_var.set("")
        for var in self.filters.values():
            var.set(ALL)
        self.sort_column, self.sort_desc = None, False
        self._mark_headings()
        self._populate()

    # -- opening an issue and its comments ------------------------------
    def open_url(self, url: str | None) -> None:
        if not url:
            self.window.set_status("This issue has no URL")
            return
        if self.window.interactive:
            webbrowser.open(url)
        else:
            self.window.set_status(f"Open: {url}")

    def open_selected(self) -> None:
        """The focused row's URL in the browser; the status bar names it when the window is not interactive."""
        row = self.row(self.tree.focus())
        if row is None:
            self.window.set_status("Select an issue first")
            return
        self.open_url(row.get("url"))

    def _on_click(self, event: tk.Event) -> str | None:
        """A click in the Comments column opens that row's comments; any other column selects as usual."""
        if self.tree.identify_column(event.x) != COMMENTS_COLUMN:
            return None
        key = self.tree.identify_row(event.y)
        if key:
            self.window.open_comments(key)
        return "break"

    def _on_double_click(self, event: tk.Event) -> str | None:
        if self.tree.identify_column(event.x) == COMMENTS_COLUMN:
            return "break"
        self.open_selected()
        return None

    def _on_key_c(self, _event: tk.Event | None = None) -> None:
        key = self.tree.focus()
        if key:
            self.window.open_comments(key)

    def _on_motion(self, event: tk.Event) -> None:
        """A hand cursor over a ``[Comments]`` cell: the one per-cell signal a Treeview allows."""
        over = self.tree.identify_column(event.x) == COMMENTS_COLUMN and bool(self.tree.identify_row(event.y))
        cursor = "hand2" if over else ""
        if str(self.tree.cget("cursor")) != cursor:
            self.tree.configure(cursor=cursor)
