"""TrackerScreen: the Weekly Status, one week at a time.

The toolbar picks the week (the current one first); the Note line, the Outcomes and the Issues panes
are the engineer's text, saved per pane through the generic CRUD of ``week``; the Jira pane is the
section as the tracker text will print it (built from the sprint's items while the week is current,
the frozen text once the sprint closed) and is read-only here, the items being edited on the Sprint
Board. ``Build week`` and ``Build history`` run ``tracker build``; ``Open`` opens the last built file.
"""

from __future__ import annotations

import datetime as dt
import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import ttk
from typing import Any

from ..commands import Result
from ..generate import sprint_queries as q
from ..tracker import format as fmt
from .screens import Screen

WEEK = "week"
PANES = ((fmt.SECTION_OUTCOMES, "Outcomes"), (fmt.SECTION_ISSUES, "Miscellaneous issues (printed indented)"))
NO_WEEK = "No week yet: press New week (it joins the active sprint), or import the tracker text."


def week_label(start: str, sprint: int) -> str:
    day = q.parse_date(start)
    return f"WEEK OF {day.strftime('%m/%d')} - {(day + dt.timedelta(days=6)).strftime('%m/%d')} · sprint {sprint}"


class TrackerScreen(Screen):
    def build(self) -> None:
        self.weeks: dict[str, list[dict[str, Any]]] = {}
        self.last_primary: str | None = None
        self._loaded: dict[str, str] = {}

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Week").pack(side="left", padx=(0, 6))
        self.week_var = tk.StringVar()
        self.week_box = ttk.Combobox(bar, textvariable=self.week_var, state="readonly", width=34)
        self.week_box.pack(side="left")
        self.week_box.bind("<<ComboboxSelected>>", self._on_pick)
        ttk.Button(bar, text="New week", command=self.new_week).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Build week", command=lambda: self.build_text("week")).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Build history", command=lambda: self.build_text("history")).pack(side="left", padx=4)
        ttk.Button(bar, text="Open", command=self.open_primary).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Open folder", command=self.open_folder).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="right")

        note = ttk.Frame(self)
        note.pack(fill="x", pady=(0, 6))
        ttk.Label(note, text="Note on the heading line").pack(side="left", padx=(0, 6))
        self.note_var = tk.StringVar()
        ttk.Entry(note, textvariable=self.note_var).pack(side="left", fill="x", expand=True)
        ttk.Button(note, text="Save", command=lambda: self.save(fmt.SECTION_NOTE)).pack(side="left", padx=(6, 0))

        panes = ttk.PanedWindow(self, orient="vertical")
        panes.pack(fill="both", expand=True)
        self.texts: dict[str, tk.Text] = {}
        for section, caption in PANES:
            box = ttk.LabelFrame(panes, text=caption)
            text = tk.Text(box, height=8, wrap="none", undo=True)
            ybar = ttk.Scrollbar(box, orient="vertical", command=text.yview)
            text.configure(yscrollcommand=ybar.set)
            text.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            save = ttk.Button(box, text="Save", command=lambda s=section: self.save(s))
            save.grid(row=1, column=0, sticky="w", pady=4)
            box.rowconfigure(0, weight=1)
            box.columnconfigure(0, weight=1)
            panes.add(box, weight=1)
            self.texts[section] = text
        jira_box = ttk.LabelFrame(panes, text="Jira issues (built from the Sprint Board; frozen at sprint close)")
        self.jira = tk.Text(jira_box, height=8, wrap="none", state="disabled")
        jbar = ttk.Scrollbar(jira_box, orient="vertical", command=self.jira.yview)
        self.jira.configure(yscrollcommand=jbar.set)
        self.jira.grid(row=0, column=0, sticky="nsew")
        jbar.grid(row=0, column=1, sticky="ns")
        jira_box.rowconfigure(0, weight=1)
        jira_box.columnconfigure(0, weight=1)
        panes.add(jira_box, weight=1)

    # -- state -----------------------------------------------------------------------------
    def current_start(self) -> str | None:
        picked = self._start_of(self.week_var.get())
        if picked in self.weeks:
            return picked
        remembered = self.window.week_start
        if remembered in self.weeks:
            return remembered
        today = dt.date.today()
        current = [s for s in self.weeks if q.parse_date(s) <= today]
        return max(current) if current else (max(self.weeks) if self.weeks else None)

    def _start_of(self, label: str) -> str | None:
        for start, rows in self.weeks.items():
            if week_label(start, rows[0]["sprint"]) == label:
                return start
        return None

    def _on_pick(self, _event: tk.Event | None = None) -> None:
        start = self._start_of(self.week_var.get())
        if start:
            self.window.week_start = start
            self.refresh()

    def refresh(self) -> None:
        listed = self.window.run_quiet("list", entity=WEEK)
        rows = list(listed.data or []) if listed.ok else []
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in sorted(rows, key=lambda r: (r.get("start") or "", r.get("order") or 0, r["id"])):
            grouped.setdefault(row["start"], []).append(row)
        self.weeks = dict(sorted(grouped.items(), reverse=True))
        self.week_box["values"] = [week_label(start, rows[0]["sprint"]) for start, rows in self.weeks.items()]
        start = self.current_start()
        if start is None:
            self.week_var.set("")
            self.note_var.set("")
            for text in self.texts.values():
                text.delete("1.0", "end")
            self._set_jira("")
            self._loaded = {}
            self.window.set_status(NO_WEEK)
            return
        self.window.week_start = start
        rows = self.weeks[start]
        self.week_var.set(week_label(start, rows[0]["sprint"]))
        by_section = {row["section"]: row for row in rows}
        self.note_var.set((by_section.get(fmt.SECTION_NOTE) or {}).get("text") or "")
        self._loaded = {fmt.SECTION_NOTE: self.note_var.get()}
        for section, text in self.texts.items():
            value = (by_section.get(section) or {}).get("text") or ""
            text.delete("1.0", "end")
            text.insert("1.0", value)
            self._loaded[section] = value
        self._set_jira(self._jira_text(start, rows[0]["sprint"], by_section.get(fmt.SECTION_JIRA)))
        self.window.set_status(f"{week_label(start, rows[0]['sprint'])} · {len(rows)} section(s)")

    def _jira_text(self, start: str, number: int, frozen: dict[str, Any] | None) -> str:
        if frozen and frozen.get("text"):
            return str(frozen["text"])
        today = dt.date.today()
        tracker = self.brain.tracker.tracker(today)
        sprint = next((s for s in tracker.sprints if s.number == number), None)
        if sprint is None or sprint.status == "Closed":
            return ""
        newest = max((w.start for w in sprint.weeks), default=None)
        if newest is not None and newest.isoformat() != start:
            return f"(the Jira section prints under the sprint's newest week, {newest.strftime('%m/%d')})"
        return fmt.render_jira(sprint, today, tracker.jira_scope) or "(no Jira items on the Sprint Board)"

    def _set_jira(self, text: str) -> None:
        self.jira.configure(state="normal")
        self.jira.delete("1.0", "end")
        self.jira.insert("1.0", text)
        self.jira.configure(state="disabled")

    def pane_text(self, section: str) -> str:
        if section == fmt.SECTION_NOTE:
            return self.note_var.get().strip()
        return self.texts[section].get("1.0", "end-1c").rstrip()

    def is_dirty(self) -> bool:
        return any(self.pane_text(section) != loaded.rstrip() for section, loaded in self._loaded.items())

    # -- actions ---------------------------------------------------------------------------------
    def save(self, section: str) -> Result:
        start = self.current_start()
        if start is None:
            return Result.failure("no week to save into; press New week", verb="update")
        rows = self.weeks[start]
        text = self.pane_text(section)
        existing = next((row for row in rows if row["section"] == section), None)
        if existing is not None:
            result = self.window.run("update", entity=WEEK, id=existing["id"], data={"text": text or None})
        else:
            result = self.window.run("create", entity=WEEK, data={
                "start": start, "sprint": rows[0]["sprint"], "section": section,
                "order": fmt.SECTION_ORDER[section], "text": text or None,
            })
        if result.ok:
            self.refresh()
            self.window.set_status(f"{section} saved for {week_label(start, rows[0]['sprint'])}")
        return result

    def new_week(self) -> Result:
        """The week of today in the active sprint, opened with an empty Outcomes line."""
        start = q.week_start(dt.date.today()).isoformat()
        if start in self.weeks:
            self.window.week_start = start
            self.week_var.set("")
            self.refresh()
            return Result.success({"start": start}, ["that week already exists"], verb="tracker")
        result = self.window.run("tracker", action="add", what="- ", section=fmt.SECTION_OUTCOMES)
        if result.ok:
            self.window.week_start = result.data["start"]
            self.week_var.set("")
            self.refresh()
        return result

    def build_text(self, kind: str) -> Result:
        """``tracker build history|week`` into the Brain's output folder; the path goes to the status bar."""
        result = self.window.run("tracker", action="build", what=kind)
        if result.ok:
            self.last_primary = result.data["path"]
            self.window.set_status(f"Written: {self.last_primary}")
        return result

    def _open_path(self, path: str | Path) -> bool:
        target = Path(path)
        if not target.exists():
            self.window.notify_error("Open", f"{target} does not exist; build it first")
            return False
        if not self.window.interactive:
            self.window.set_status(f"Would open {target}")
            return False
        if hasattr(os, "startfile"):
            os.startfile(str(target))  # noqa: S606  (Windows shell open; guarded above)
        else:
            webbrowser.open(target.resolve().as_uri())
        return True

    def open_primary(self) -> bool:
        if not self.last_primary:
            self.window.set_status("Nothing built yet: press Build week or Build history first")
            return False
        return self._open_path(self.last_primary)

    def open_folder(self) -> bool:
        folder = Path(self.brain.out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        return self._open_path(folder)
