"""SprintBoardScreen: one sprint at a time, where it stands and what it holds.

The toolbar picks the sprint (the active one first); the summary shows the points committed against
the capacity, done, to go, unpointed, the days left and the velocity, with the capacity warnings;
three lanes (To Do, In Progress, Done) list the items; the form below edits the selected one. Every
button is a verb through ``window.run`` (``sprint board|start|close|carry``, the generic CRUD of
``sprint_item``, ``tracker build``), so an agent can do the same from the automation server. The
numbers come from ``sprint board``, the same helpers the tracker text and the dashboard use.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..commands import Result
from ..generate import plan_queries as pq
from .screens import Screen, fit_columns
from .widgets import WidgetFactory

ITEM = "sprint_item"
SPRINT = "sprint"
LANES = (("To Do", "TO DO"), ("In Progress", "IN PROGRESS"), ("Done", "DONE"))
LANE_COLUMNS = ("points", "kind", "title", "ref")
LANE_HEADINGS = {"points": "pts", "kind": "kind", "title": "item", "ref": "ref"}
FORM_FIELDS = ("kind", "title", "plan_row", "jira_key", "points", "target", "note", "status", "order")
NO_SPRINT = "No sprint yet: press Start sprint, or import the tracker text (asi-kletz tracker import)."


def sprint_label(sprint: dict[str, Any]) -> str:
    label = sprint.get("label") or f"SPRINT {sprint['number']}"
    return f"{sprint['number']} · {label} · {sprint.get('status') or '-'}"


def item_ref(item: dict[str, Any]) -> str:
    if item.get("jira_key"):
        return str(item["jira_key"])
    if item.get("plan_row"):
        return f"plan #{item['plan_row']}"
    return ""


def summary_text(board: dict[str, Any]) -> str:
    """``9 / 10 points committed · 3 done · 6 to go · 2 unpointed``."""
    return (
        f"{board['committed']} / {board['capacity']} points committed · {board['done']} done · "
        f"{board['to_go']} to go · {board['unpointed']} unpointed"
    )


def pace_text(board: dict[str, Any]) -> str:
    sprint = board["sprint"]
    when = f"{sprint.get('start') or '?'} to {sprint.get('end') or '?'}"
    days = "overdue" if board["overdue"] else f"{board['days_left']} days left"
    speed = "no closed sprint" if board["velocity"] is None else f"{board['velocity']:g} points per sprint"
    return f"{when} · {days} · velocity {speed}"


class SprintBoardScreen(Screen):
    def build(self) -> None:
        self.sprints: list[dict[str, Any]] = []
        self.board: dict[str, Any] | None = None
        self.selected: int | None = None
        self._selecting = False
        self.factory = WidgetFactory(self.brain.lookups)
        self.schema = self.brain.registry.get(ITEM)

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Label(bar, text="Sprint").pack(side="left", padx=(0, 6))
        self.sprint_var = tk.StringVar()
        self.sprint_box = ttk.Combobox(bar, textvariable=self.sprint_var, state="readonly", width=34)
        self.sprint_box.pack(side="left")
        self.sprint_box.bind("<<ComboboxSelected>>", self._on_pick)
        ttk.Button(bar, text="Start sprint", command=self.start_sprint).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Close sprint", command=self.close_sprint).pack(side="left", padx=4)
        ttk.Button(bar, text="Build week", command=lambda: self.build_text("week")).pack(side="left", padx=(12, 4))
        ttk.Button(bar, text="Build history", command=lambda: self.build_text("history")).pack(side="left", padx=4)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="right")

        where = ttk.LabelFrame(self, text="Where we are")
        where.pack(fill="x", pady=(0, 8))
        self.goal_var = tk.StringVar(value=NO_SPRINT)
        goal = ttk.Label(where, textvariable=self.goal_var)
        goal.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))
        self.bar = ttk.Progressbar(where, orient="horizontal", mode="determinate", maximum=10, length=320)
        self.bar.grid(row=1, column=0, sticky="w", padx=8, pady=2)
        self.points_var = tk.StringVar()
        ttk.Label(where, textvariable=self.points_var, style="Status.TLabel").grid(row=1, column=1, sticky="w", padx=8)
        self.pace_var = tk.StringVar()
        pace = ttk.Label(where, textvariable=self.pace_var, style="Muted.TLabel")
        pace.grid(row=2, column=0, columnspan=2, sticky="w", padx=8)
        self.warn_var = tk.StringVar()
        ttk.Label(where, textvariable=self.warn_var, style="Muted.TLabel").grid(
            row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6)
        )
        where.columnconfigure(1, weight=1)

        lanes = ttk.PanedWindow(self, orient="horizontal")
        lanes.pack(fill="both", expand=True, pady=(0, 8))
        self.lanes: dict[str, ttk.Treeview] = {}
        for status, caption in LANES:
            box = ttk.LabelFrame(lanes, text=caption)
            tree = ttk.Treeview(box, columns=LANE_COLUMNS, show="headings", height=9, selectmode="browse")
            for column in LANE_COLUMNS:
                tree.heading(column, text=LANE_HEADINGS[column])
                tree.column(column, width=60, minwidth=30)
            ybar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=ybar.set)
            tree.pack(side="left", fill="both", expand=True)
            ybar.pack(side="right", fill="y")
            tree.bind("<<TreeviewSelect>>", lambda e, s=status: self._on_select(s))
            lanes.add(box, weight=1)
            self.lanes[status] = tree

        form = ttk.LabelFrame(self, text="Item")
        form.pack(fill="x")
        self.widgets: dict[str, Any] = {}
        for index, name in enumerate(FORM_FIELDS):
            spec = self.schema.field(name)
            row, column = divmod(index, 3)
            label = ttk.Label(form, text=spec.header.split(" (")[0])
            label.grid(row=row, column=column * 2, sticky="nw", padx=(8, 4), pady=3)
            widget = self.factory.create(form, spec, width=14 if spec.name != "title" else 36, height=3)
            widget.grid(row=row, column=column * 2 + 1, sticky="ew", padx=(0, 8), pady=3)
            self.widgets[name] = widget
        for column in (1, 3, 5):
            form.columnconfigure(column, weight=1)
        buttons = ttk.Frame(form)
        buttons.grid(row=3, column=0, columnspan=6, sticky="w", padx=8, pady=(4, 8))
        ttk.Button(buttons, text="New", command=self.new).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Delete", command=self.delete).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Carry to next sprint", command=self.carry).pack(side="left")

    # -- state -----------------------------------------------------------------------------
    def current_number(self) -> int | None:
        """The sprint shown: the picked one, else the window's remembered one, else the active, else the last."""
        picked = self.sprint_var.get().split(" · ")[0]
        if picked.isdigit() and any(s["number"] == int(picked) for s in self.sprints):
            return int(picked)
        remembered = self.window.sprint_number
        if remembered is not None and any(s["number"] == remembered for s in self.sprints):
            return remembered
        active = next((s for s in self.sprints if s.get("status") == "Active"), None)
        if active is not None:
            return active["number"]
        return self.sprints[-1]["number"] if self.sprints else None

    def _on_pick(self, _event: tk.Event | None = None) -> None:
        picked = self.sprint_var.get().split(" · ")[0]
        if picked.isdigit():
            self.window.sprint_number = int(picked)
            self.selected = None
            self.refresh()

    def refresh(self) -> None:
        listed = self.window.run_quiet("list", entity=SPRINT)
        self.sprints = list(listed.data or []) if listed.ok else []
        self.sprint_box["values"] = [sprint_label(s) for s in self.sprints]
        number = self.current_number()
        for tree in self.lanes.values():
            tree.delete(*tree.get_children())
        if number is None:
            self.board = None
            self.sprint_var.set("")
            self.goal_var.set(NO_SPRINT)
            self.points_var.set("")
            self.pace_var.set("")
            self.warn_var.set("")
            self.bar.configure(value=0)
            self.window.set_status("No sprint yet")
            return
        self.window.sprint_number = number
        self.sprint_var.set(next(sprint_label(s) for s in self.sprints if s["number"] == number))
        result = self.window.run_quiet("sprint", action="board", number=number)
        if not result.ok:
            self.board = None
            return
        board = self.board = result.data
        sprint = board["sprint"]
        goal = pq.one_line(sprint.get("goal")) or "no goal set"
        self.goal_var.set(f"{sprint.get('lifecycle_phase') or ''} — {sprint.get('label') or ''} — {goal}")
        self.bar.configure(maximum=max(1, board["capacity"]), value=min(board["committed"], board["capacity"]))
        self.points_var.set(summary_text(board))
        self.pace_var.set(pace_text(board))
        self.warn_var.set("; ".join(board["warnings"]))
        carried = 0
        for item in board["items"]:
            status = item.get("status") or "To Do"
            if status == "Carried":
                carried += 1
                continue
            tree = self.lanes.get(status, self.lanes["To Do"])
            tree.insert("", "end", iid=str(item["id"]), values=(
                item.get("points") or "", item.get("kind") or "", pq.one_line(item.get("title"), 70), item_ref(item),
            ))
        for tree in self.lanes.values():
            self.window.theme.stripe(tree)
            fit_columns(tree, max_width=360)
        if self.selected is not None:
            for tree in self.lanes.values():
                if tree.exists(str(self.selected)):
                    self._selecting = True
                    tree.selection_set(str(self.selected))
                    self._selecting = False
                    break
            else:
                self.selected = None
                self._clear_form()
        extra = f" · {carried} carried on" if carried else ""
        self.window.set_status(f"Sprint {number}: {summary_text(board)} · {pace_text(board)}{extra}")

    # -- selection and form -------------------------------------------------------------------
    def _on_select(self, status: str) -> None:
        if self._selecting:
            return
        tree = self.lanes[status]
        selection = tree.selection()
        if not selection:
            return
        self._selecting = True
        try:
            for other_status, other in self.lanes.items():
                if other_status != status and other.selection():
                    other.selection_remove(*other.selection())
        finally:
            self._selecting = False
        self.selected = int(selection[0])
        item = next((i for i in (self.board or {}).get("items", []) if i["id"] == self.selected), None)
        if item is not None:
            for name, widget in self.widgets.items():
                widget.set(item.get(name))

    def _clear_form(self) -> None:
        for widget in self.widgets.values():
            widget.clear()

    def form_data(self) -> dict[str, Any]:
        return {name: widget.get() for name, widget in self.widgets.items()}

    def new(self) -> None:
        self.selected = None
        for tree in self.lanes.values():
            if tree.selection():
                tree.selection_remove(*tree.selection())
        self._clear_form()
        self.widgets["status"].set("To Do")
        self.widgets["kind"].set("Other")
        self.widgets["title"].focus_field()

    def save(self) -> Result:
        number = self.current_number()
        if number is None:
            return self.window.run("sprint", action="board")  # reports "no active sprint"
        data = self.form_data()
        if self.selected is None:
            data["sprint"] = number
            result = self.window.run("create", entity=ITEM, data=data)
            if result.ok:
                self.selected = int(result.data["id"])
        else:
            result = self.window.run("update", entity=ITEM, id=self.selected, data=data)
        if result.ok:
            self.refresh()
            if result.warnings:
                self.window.set_status("Warning: " + "; ".join(result.warnings))
        return result

    def delete(self) -> Result:
        if self.selected is None:
            return Result.failure("select an item first", verb="delete")
        if not self.window.confirm("Delete item", "Delete the selected sprint item?"):
            return Result.failure("cancelled", verb="delete")
        result = self.window.run("delete", entity=ITEM, id=self.selected)
        if result.ok:
            self.selected = None
            self._clear_form()
            self.refresh()
        return result

    def carry(self) -> Result:
        if self.selected is None:
            return Result.failure("select an item first", verb="sprint")
        result = self.window.run("sprint", action="carry", item=self.selected)
        if result.ok:
            self.selected = None
            self._clear_form()
            self.refresh()
        return result

    # -- sprint actions -----------------------------------------------------------------------------
    def start_sprint(self) -> Result:
        result = self.window.run("sprint", action="start")
        if result.ok:
            self.window.sprint_number = int(result.data["number"])
            self.sprint_var.set("")
            self.refresh()
        return result

    def close_sprint(self) -> Result:
        number = self.current_number()
        if number is None:
            return Result.failure("no sprint to close", verb="sprint")
        if not self.window.confirm(
            "Close sprint", f"Close sprint {number}? Done is counted, every open item is carried into the next sprint."
        ):
            return Result.failure("cancelled", verb="sprint")
        result = self.window.run("sprint", action="close", number=number)
        if result.ok:
            data = result.data
            self.window.sprint_number = int(data["next"]) if data.get("next") else None
            self.sprint_var.set("")
            self.selected = None
            self._clear_form()
            self.refresh()
            self.window.set_status(
                f"Sprint {number} closed: {data['done']} points done, {data['carried']} item(s) carried into "
                f"sprint {data['next']}"
            )
        return result

    def build_text(self, kind: str) -> Result:
        result = self.window.run("tracker", action="build", what=kind)
        if result.ok:
            self.window.set_status(f"Written: {result.data['path']}")
        return result
