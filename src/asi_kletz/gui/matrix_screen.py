"""SafetyPlanMatrixScreen: deliverables as rows, one flag group as columns, click a cell to toggle."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..commands import Result
from ..schema import FieldSpec
from .screens import PLAN_ENTITY, FrozenPane, Screen, bind_horizontal_scroll, fit_columns, heading_under

ENTITY = PLAN_ENTITY
FIXED = ("order", "pdp_phase", "lifecycle_phase", "deliverable")  # frozen on the left since 0.7.2
FIXED_WIDTHS = (50, 50, 190, 320)  # starting widths only: ``fit_columns`` has the last word after every fill
CHECK = "✓"
ALL_GROUPS = "all"  # every flag at once, in source order: the default since 0.7.0


class SafetyPlanMatrixScreen(Screen):
    def build(self) -> None:
        self.schema = self.brain.registry.get(ENTITY)
        self.groups: dict[str, list[FieldSpec]] = {ALL_GROUPS: [s for s in self.schema.fields if s.is_flag]}
        self.groups.update(
            {name: [s for s in specs if s.is_flag] for name, specs in self.schema.groups().items() if name}
        )
        self.rows: list[dict[str, Any]] = []
        self.flags: list[FieldSpec] = []

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Flag group").pack(side="left")
        self.group_var = tk.StringVar(value=next(iter(self.groups)))
        combo = ttk.Combobox(bar, textvariable=self.group_var, values=list(self.groups), state="readonly", width=16)
        combo.pack(side="left", padx=(4, 12))
        combo.bind("<<ComboboxSelected>>", lambda e: self.set_group(self.group_var.get()))
        ttk.Label(bar, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate())
        ttk.Entry(bar, textvariable=self.search_var, width=24).pack(side="left", padx=(4, 12))
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Label(bar, text="Click a flag cell to toggle it", style="Muted.TLabel").pack(side="right")

        # the fixed columns stay put on the left while the flag columns scroll on the right; ``self.tree``
        # is the right tree, which owns every column (``set_group`` rebuilds them) and holds the flag cells
        self.pane = FrozenPane(self, FIXED, FIXED)
        self.pane.pack(fill="both", expand=True)
        self.tree = self.pane.right
        self.tree.bind("<Button-1>", self._on_click)
        bind_horizontal_scroll(self.tree)
        self._heading_hint: str | None = None
        self.tree.bind("<Motion>", self._on_heading_motion)
        self.set_group(self.group_var.get(), reload=False)

    def set_group(self, group: str, reload: bool = True) -> None:
        self.flags = self.groups[group]
        self.group_var.set(group)
        columns = [*FIXED, *(f.name for f in self.flags)]
        self.tree["displaycolumns"] = "#all"  # Tk checks the old display against the new columns first
        self.tree.configure(columns=columns)
        for name, width in zip(FIXED, FIXED_WIDTHS, strict=True):
            self.tree.heading(name, text=self.schema.field(name).header)
            self.tree.column(name, width=width, minwidth=40, stretch=name == "deliverable")
        for spec in self.flags:  # a flag column is as wide as its heading, the source column title
            self.tree.heading(spec.name, text=spec.header)
            self.tree.column(spec.name, width=60, minwidth=40, anchor="center", stretch=False)
        fit_columns(self.tree)
        self.pane.set_display(columns)  # configuring ``columns`` reset the display to every column
        if reload:
            self.refresh()

    def refresh(self) -> None:
        result = self.brain.execute("list", entity=ENTITY, actor="gui")
        if not result.ok:
            self.window.notify_error("Could not load the safety plan", "; ".join(result.errors))
            return
        self.rows = result.data
        self._populate()

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        needle = self.search_var.get().strip().casefold()
        for row in self.rows:
            if needle and needle not in " ".join(str(row.get(c) or "") for c in FIXED).casefold():
                continue
            values = [("" if row.get(c) is None else str(row[c]).replace("\n", " ")) for c in FIXED]
            values += [CHECK if row.get(f.name) else "" for f in self.flags]
            self.tree.insert("", "end", iid=str(row["id"]), values=values)
        self.window.theme.stripe(self.tree)
        fit_columns(self.tree)
        self.pane.mirror()
        total = sum(1 for r in self.rows for f in self.flags if r.get(f.name))
        self.window.set_status(f"{self.group_var.get()}: {total} flags set across {len(self.rows)} deliverables")

    def _on_heading_motion(self, event: tk.Event) -> None:
        text = heading_under(self.tree, event)
        if text != self._heading_hint:
            self._heading_hint = text
            if text:
                self.window.set_status(f"Column: {text}")

    def _on_click(self, event: tk.Event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        iid = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not iid or not column:
            return
        field = self.tree.column(column, "id")  # ``#n`` counts displayed columns, so resolve it by name
        if field not in FIXED:
            self.toggle(int(iid), field)

    def toggle(self, row_id: int, field: str) -> Result:
        current = next((r for r in self.rows if r["id"] == row_id), None)
        value = not (current or {}).get(field, False)
        result = self.window.run("update", entity=ENTITY, id=row_id, data={field: value})
        if result.ok:
            self.refresh()
            header = self.schema.field(field).header
            self.window.set_status(f"{header}: {'set' if value else 'cleared'} on row {row_id}")
        return result
