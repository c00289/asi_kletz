"""SafetyPlanMatrixScreen: the plan stacked as PDP phase > lifecycle phase > deliverable on the left,
one flag group as columns on the right, click a flag cell to toggle it."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..commands import Result
from ..schema import FieldSpec
from .screens import PLAN_ENTITY, FrozenPane, Screen, bind_horizontal_scroll, fit_columns, heading_under

ENTITY = PLAN_ENTITY
PLAN = "plan"  # the one stacked column: PDP phase, its lifecycle phases, their deliverables (0.8.3)
PLAN_HEADER = "PDP phase  ›  Safety lifecycle phase  ›  Safety deliverable"
FIXED = ("order", PLAN)  # frozen on the left since 0.7.2; stacked since 0.8.3
FIXED_WIDTHS = (50, 360)  # starting widths only: ``fit_columns`` has the last word after every fill
INDENT = "    "  # one level of the stack
SEARCHED = ("order", "pdp_phase", "lifecycle_phase", "deliverable")  # the search box reads these, as before the stack
PDP_TAG, PHASE_TAG = "pdp", "phase"  # the group rows; a deliverable row carries the stripe tag alone
CHECK = "✓"
ALL_GROUPS = "all"  # every flag at once, in source order: the default since 0.7.0


def pdp_title(value: Any) -> str:
    return f"PDP phase {value}" if value not in (None, "") else "(no PDP phase)"


def phase_title(value: Any) -> str:
    return str(value) if value not in (None, "") else "(no lifecycle phase)"


def stack(rows: list[dict[str, Any]]) -> list[tuple[str, int, str, dict[str, Any] | None]]:
    """The plan as a stack: ``(iid, level, text, row)`` per line, in the rows' own order.

    Level 0 is a PDP phase (iid ``pdp:<value>``), level 1 a lifecycle phase under it
    (``phase:<pdp>:<value>``), level 2 a deliverable (the row id, ``row`` set). A group line opens
    whenever the value changes between consecutive rows, so a plan kept in order (as the Safety
    Plan is, by ``order``) shows every phase once; a plan out of order shows the truth of its order.
    """
    lines: list[tuple[str, int, str, dict[str, Any] | None]] = []
    pdp = phase = object()
    for row in rows:
        if row.get("pdp_phase") != pdp:
            pdp, phase = row.get("pdp_phase"), object()
            lines.append((f"pdp:{pdp}", 0, pdp_title(pdp), None))
        if row.get("lifecycle_phase") != phase:
            phase = row.get("lifecycle_phase")
            lines.append((f"phase:{pdp}:{phase}", 1, INDENT + phase_title(phase), None))
        deliverable = "" if row.get("deliverable") is None else str(row["deliverable"]).replace("\n", " ")
        lines.append((str(row["id"]), 2, INDENT * 2 + deliverable, row))
    return lines


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
            self.tree.heading(name, text=PLAN_HEADER if name == PLAN else self.schema.field(name).header)
            self.tree.column(name, width=width, minwidth=40, stretch=name == PLAN)
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

    def _matches(self, row: dict[str, Any], needle: str) -> bool:
        return needle in " ".join(str(row.get(c) or "") for c in SEARCHED).casefold()

    def _populate(self) -> None:
        tree = self.tree
        tree.delete(*tree.get_children())
        needle = self.search_var.get().strip().casefold()
        blanks = [""] * len(self.flags)
        pending: list[tuple[str, int, str]] = []  # group lines not yet inserted: shown once a deliverable under them is
        for iid, level, text, row in stack(self.rows):
            if row is None:
                del pending[level:]  # a new group at this level replaces the pending ones from this level down
                pending.append((iid, level, text))
                continue
            if needle and not self._matches(row, needle):
                continue
            for group_iid, group_level, group_text in pending:
                tree.insert("", "end", iid=group_iid, values=["", group_text, *blanks],
                            tags=(PDP_TAG if group_level == 0 else PHASE_TAG,))
            pending.clear()
            values = ["" if row.get("order") is None else str(row["order"]), text]
            values += [CHECK if row.get(f.name) else "" for f in self.flags]
            tree.insert("", "end", iid=iid, values=values)
        self._style_groups()
        fit_columns(tree)
        self.pane.mirror()
        total = sum(1 for r in self.rows for f in self.flags if r.get(f.name))
        self.window.set_status(f"{self.group_var.get()}: {total} flags set across {len(self.rows)} deliverables")

    def _style_groups(self) -> None:
        """Stripe the rows, then put the group tags back in front: the first tag wins an option, so a
        group row takes its colour and font from its group tag and its background from the stripe."""
        tree, theme = self.tree, self.window.theme
        groups = {iid: tree.item(iid, "tags") for iid in tree.get_children() if not iid.isdigit()}
        theme.stripe(tree)
        tree.tag_configure(PDP_TAG, foreground=theme.palette.primary, font=theme.heading)
        tree.tag_configure(PHASE_TAG, foreground=theme.palette.accent, font=theme.heading)
        for iid, tags in groups.items():
            tree.item(iid, tags=(*tags, *tree.item(iid, "tags")))

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
        if not iid or not column or not iid.isdigit():  # a group row has no flags to toggle
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
