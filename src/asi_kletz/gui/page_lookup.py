"""PageLookup: the Find page window beside the work product URLs box (0.23.0, Phase B of the Confluence
integration plan), the Look up window's pattern (``people_lookup.py``).

A person types part of a page title, picks the space (the default from ``kletz.toml``) and presses Search; one
``confluence search`` runs on a worker thread through ``BackgroundFetch`` and ``window.execute_quiet`` (never on
the Tk thread), the Tk thread polls it with ``after`` and lists the hits (title, space, last modified); Insert
hands the chosen page's URL to the URLs editor through ``on_pick``. No page body is shown in Kletz: the link
opens the browser, as the Open button does. Nothing is stored but the URL picked; nothing runs without a press;
a rejected session or a failed read is one line in the status bar and in this window, the editor untouched.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..commands import Result
from .jira_live_screen import POLL_MS, WAIT_FETCH_TIMEOUT, BackgroundFetch

if TYPE_CHECKING:
    from .main_window import MainWindow

TITLE = "Find a Confluence page"
SEARCHING = "Searching Confluence …"
NO_MATCH = "No page in {space} has {text!r} in its title; try fewer letters or another space"
INSERT = "Insert"
SEARCH = "Search"
FIND_PAGE = "Find page"


def hit_text(page: dict[str, Any]) -> str:
    """One list line: the title, the space key and the day of the last change."""
    when = str(page.get("last_modified") or "")[:10]
    return f"{page.get('title') or ''}  ·  {page.get('space_key') or ''}  ·  {when}".rstrip(" ·")


class PageLookup(tk.Toplevel):
    def __init__(self, window: MainWindow, on_pick: Callable[[str], None], space: str, initial: str = "") -> None:
        super().__init__(window)
        self.window = window
        self.on_pick = on_pick
        self.pages: list[dict[str, Any]] = []
        self.last: Result | None = None
        self._fetch: BackgroundFetch | None = None
        self._poll_job: str | None = None
        self.title(TITLE)
        self.transient(window)
        self.resizable(True, True)
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="Title").pack(side="left")
        self.query_var = tk.StringVar(value=initial)
        self.entry = ttk.Entry(top, textvariable=self.query_var, width=30)
        self.entry.pack(side="left", padx=(4, 8), fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.search())
        ttk.Label(top, text="Space").pack(side="left")
        self.space_var = tk.StringVar(value=space)
        self.space_combo = ttk.Combobox(top, textvariable=self.space_var, values=[space], width=8)
        self.space_combo.pack(side="left", padx=(4, 4))
        self.search_button = ttk.Button(top, text=SEARCH, command=self.search)
        self.search_button.pack(side="left")
        self.status_var = tk.StringVar(value="Type part of a page title and press Search")
        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel", wraplength=460).pack(
            anchor="w", pady=(6, 2)
        )
        middle = ttk.Frame(body)
        middle.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(middle, height=8, width=70, activestyle="dotbox", exportselection=False)
        bar = ttk.Scrollbar(middle, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=bar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda e: self.insert_selected())
        bottom = ttk.Frame(body)
        bottom.pack(fill="x", pady=(6, 0))
        self.insert_button = ttk.Button(bottom, text=INSERT, command=self.insert_selected, state="disabled")
        self.insert_button.pack(side="left")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.entry.focus_set()

    # -- the search, off the Tk thread ---------------------------------------------------------
    @property
    def searching(self) -> bool:
        return self._fetch is not None

    def search(self) -> bool:
        """Start one ``confluence search`` on the worker; ``False`` when one already runs or the box is empty."""
        text = " ".join(self.query_var.get().split())
        space = " ".join(self.space_var.get().split()).upper()
        if self._fetch is not None:
            return False
        if len(text) < 2:
            self.status_var.set("Type at least two characters of a title")
            return False
        args: dict[str, Any] = {"action": "search", "target": text}
        if space:
            args["space"] = space
        self._fetch = BackgroundFetch(self.window, "confluence", **args).start()
        self.status_var.set(SEARCHING)
        self.window.set_status(SEARCHING)
        self.search_button.state(["disabled"])
        self._poll()
        return True

    def _poll(self) -> None:
        self._poll_job = None
        fetch = self._fetch
        if fetch is None or not self.winfo_exists():
            return  # closed meanwhile: the worker finishes alone and its Result is dropped
        if not fetch.done:
            self._poll_job = self.after(POLL_MS, self._poll)
            return
        self._fetch = None
        self._apply(fetch.result)  # type: ignore[arg-type]  # `done` means it is set

    def _apply(self, result: Result) -> None:
        self.last = result
        self.search_button.state(["!disabled"])
        self.listbox.delete(0, "end")
        self.pages = []
        if not result.ok:
            message = "; ".join(result.errors) or "unknown error"
            self.status_var.set(message)
            self.window.set_status(f"Error: {message}")
            self.insert_button.state(["disabled"])
            return
        data: dict[str, Any] = result.data or {}
        self.pages = [p for p in (data.get("pages") or []) if p.get("url")]
        for page in self.pages:
            self.listbox.insert("end", hit_text(page))
        if self.pages:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.insert_button.state(["!disabled"])
            note = (
                f"{len(self.pages)} page(s) for {data.get('text')!r} in {data.get('space')}; pick one and press Insert"
            )
            if len(self.pages) >= int(data.get("limit") or 0):
                note += " (the first ones only; type more of the title for the rest)"
        else:
            self.insert_button.state(["disabled"])
            note = NO_MATCH.format(text=data.get("text"), space=data.get("space"))
        self.status_var.set(note)
        self.window.set_status(note)

    # -- the pick ------------------------------------------------------------------------------
    def selected(self) -> dict[str, Any] | None:
        picked = self.listbox.curselection()
        if not picked or int(picked[0]) >= len(self.pages):
            return None
        return self.pages[int(picked[0])]

    def insert_selected(self) -> str | None:
        """The chosen page's URL to the editor; the window stays open for another."""
        page = self.selected()
        if page is None:
            self.status_var.set("Pick a page first")
            return None
        url = str(page["url"])
        self.on_pick(url)
        self.window.set_status(f"Inserted {url}")
        return url

    def wait_search(self, timeout: float = WAIT_FETCH_TIMEOUT) -> Result | None:
        """Test helper: pump the Tk loop until the search in flight is applied; the Result applied last."""
        deadline = time.monotonic() + timeout
        while self._fetch is not None:
            if time.monotonic() > deadline:
                raise TimeoutError(f"confluence search did not finish within {timeout} s")
            self.window.update()
            time.sleep(0.01)
        return self.last

    def destroy(self) -> None:
        if self._poll_job is not None:
            try:
                self.after_cancel(self._poll_job)
            except Exception:  # noqa: BLE001  (the window may already be gone)
                pass
            self._poll_job = None
        self._fetch = None
        super().destroy()
