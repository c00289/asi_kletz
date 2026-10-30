"""PeopleLookup: the Look up window beside a role's people editor (0.20.0, "use the outlook method").

A person types part of a name and presses Search; one ``people lookup`` runs on a worker thread through
``BackgroundFetch`` and ``window.execute_quiet`` (never on the Tk thread: a GAL walk takes seconds), the Tk
thread polls it with ``after`` and paints the matches (name, email) in a small list; Insert hands the chosen
``Name <email>`` line to the editor through ``on_pick``. Nothing is stored but that line; nothing runs without
a press; a machine without Outlook, or a refused COM call, gives one clear line in the window's status bar
and in this window, and the editor stays usable.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..commands import Result
from .background import POLL_MS, WAIT_FETCH_TIMEOUT, BackgroundFetch

if TYPE_CHECKING:
    from .main_window import MainWindow

TITLE = "Look up a person in Outlook"
SEARCHING = "Searching the Outlook address book …"
NO_MATCH = "No one in the address book matches {text!r}; try fewer letters"
INSERT = "Insert"
SEARCH = "Search"


class PeopleLookup(tk.Toplevel):
    def __init__(self, window: MainWindow, on_pick: Callable[[str], None], initial: str = "") -> None:
        super().__init__(window)
        self.window = window
        self.on_pick = on_pick
        self.matches: list[dict[str, str]] = []
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
        ttk.Label(top, text="Name").pack(side="left")
        self.query_var = tk.StringVar(value=initial)
        self.entry = ttk.Entry(top, textvariable=self.query_var, width=36)
        self.entry.pack(side="left", padx=(4, 4), fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.search())
        self.search_button = ttk.Button(top, text=SEARCH, command=self.search)
        self.search_button.pack(side="left")
        self.status_var = tk.StringVar(value="Type part of a name and press Search")
        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel", wraplength=420).pack(
            anchor="w", pady=(6, 2)
        )
        middle = ttk.Frame(body)
        middle.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(middle, height=8, width=60, activestyle="dotbox", exportselection=False)
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
        """Start one ``people lookup`` on the worker; ``False`` when one already runs or the box is empty."""
        text = " ".join(self.query_var.get().split())
        if self._fetch is not None:
            return False
        if len(text) < 2:
            self.status_var.set("Type at least two characters of a name")
            return False
        self._fetch = BackgroundFetch(self.window, "people", action="lookup", text=text).start()
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
        self.matches = []
        if not result.ok:
            message = "; ".join(result.errors) or "unknown error"
            self.status_var.set(message)
            self.window.set_status(f"Error: {message}")
            self.insert_button.state(["disabled"])
            return
        data: dict[str, Any] = result.data or {}
        self.matches = list(data.get("matches") or [])
        for match in self.matches:
            self.listbox.insert("end", match["text"])
        if self.matches:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.insert_button.state(["!disabled"])
            note = f"{len(self.matches)} match(es) for {data.get('text')!r}; pick one and press Insert"
            if len(self.matches) >= int(data.get("limit") or 0):
                note += " (the first ones only; type more letters for the rest)"
        else:
            self.insert_button.state(["disabled"])
            note = NO_MATCH.format(text=data.get("text"))
        self.status_var.set(note)
        self.window.set_status(note)

    # -- the pick ------------------------------------------------------------------------------
    def selected(self) -> dict[str, str] | None:
        picked = self.listbox.curselection()
        if not picked or int(picked[0]) >= len(self.matches):
            return None
        return self.matches[int(picked[0])]

    def insert_selected(self) -> str | None:
        """The chosen ``Name <email>`` line to the editor; the window stays open for another."""
        match = self.selected()
        if match is None:
            self.status_var.set("Pick a match first")
            return None
        self.on_pick(match["text"])
        self.window.set_status(f"Inserted {match['text']}")
        return match["text"]

    def wait_search(self, timeout: float = WAIT_FETCH_TIMEOUT) -> Result | None:
        """Test helper: pump the Tk loop until the search in flight is applied; the Result applied last."""
        deadline = time.monotonic() + timeout
        while self._fetch is not None:
            if time.monotonic() > deadline:
                raise TimeoutError(f"people lookup did not finish within {timeout} s")
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
