"""EntityScreen: the generic table-plus-form page produced for every entity from its schema."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

from ..schema import EntitySchema, FieldSpec, FieldType
from .screens import (
    INDENT,
    PDP_TAG,
    PHASE_TAG,
    PLAN,
    PLAN_HEADER,
    STACKED,
    FrozenPane,
    Screen,
    ScrollableFrame,
    bind_horizontal_scroll,
    fit_columns,
    heading_under,
    is_group,
    stack,
    style_group_rows,
)
from .widgets import FieldWidget, WidgetFactory

if TYPE_CHECKING:
    from .main_window import MainWindow

TRUNCATE = 70  # a cell shows this much of a long text; the column fits the clipped text, not the value
ALL_COLUMNS = "All"
# the identity columns of the Safety Plan stay put while the rest scrolls (0.7.2); since 0.8.4 the PDP phase,
# the lifecycle phase and the deliverable are one stacked column, ``plan``, on an entity that has all three
FROZEN = ("id", "order", PLAN)
IDENTITY = ("id", "order", *STACKED)  # the frozen set of an entity that lacks the stack


def cell_text(spec: FieldSpec | None, value: Any) -> str:
    if value is None:
        return ""
    if spec is not None and spec.type is FieldType.BOOL:
        return "✓" if value else ""
    text = str(value).replace("\n", " ")
    return text if len(text) <= TRUNCATE else text[: TRUNCATE - 1] + "…"


class EntityScreen(Screen):
    def __init__(self, master: tk.Misc, window: MainWindow, schema: EntitySchema) -> None:
        self.schema = schema
        self.rows: list[dict[str, Any]] = []
        self.by_id: dict[int, dict[str, Any]] = {}
        self.selected_id: int | None = None
        self.sort_key: str | None = None
        self.sort_desc = False
        self.widgets: dict[str, FieldWidget] = {}
        super().__init__(master, window)

    # -- layout ---------------------------------------------------------
    def build(self) -> None:
        # every column of the source sheet, in source order, behind the surrogate key
        self.columns = ["id"] + [f.name for f in self.schema.fields]
        # the plan is stacked (PDP phase > lifecycle phase > deliverable in one frozen column) when the
        # entity has the three fields; the three data columns stay on the tree, hidden, so ``set`` still answers
        self.stacked = all(self.schema.has(name) for name in STACKED)
        # the `Columns` selector: `All`, then one entry per flag group, titled like the form's group boxes
        self.column_groups: dict[str, str] = {
            group.capitalize(): group
            for group, specs in self.schema.groups().items()
            if group and any(s.is_flag for s in specs)
        }

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate())
        ttk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side="left", padx=(4, 12))
        self.columns_var = tk.StringVar(value=ALL_COLUMNS)
        self.columns_box: ttk.Combobox | None = None
        if self.column_groups:
            ttk.Label(toolbar, text="Columns").pack(side="left")
            self.columns_box = ttk.Combobox(
                toolbar, textvariable=self.columns_var, state="readonly",
                values=[ALL_COLUMNS, *self.column_groups], width=12,
            )
            self.columns_box.pack(side="left", padx=(4, 12))
            self.columns_box.bind("<<ComboboxSelected>>", lambda e: self.set_columns(self.columns_var.get()))
        for text, command in (
            ("New", self.new), ("Save", self.save), ("Delete", self.delete),
            ("Duplicate", self.duplicate), ("Refresh", self.refresh),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)
        self.count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)

        # two trees in lock-step: the frozen identity columns on the left, the rest scrolling on the right;
        # ``self.tree`` is the right one and still owns every column, so the whole screen works on it
        tree_columns = [*self.columns, PLAN] if self.stacked else self.columns
        frozen = FROZEN if self.stacked else [c for c in IDENTITY if c in self.columns]
        self.pane = FrozenPane(paned, tree_columns, frozen)
        self.pane.on_sort = self.sort_by
        self.tree = self.pane.right
        self.ybar, self.xbar = self.pane.ybar, self.pane.xbar
        if self.stacked:
            self.tree.heading(PLAN, text=PLAN_HEADER, command=lambda: self.sort_by(PLAN))
            self.tree.column(PLAN, width=360, minwidth=40, stretch=False, anchor="w")
        for name in self.columns:
            spec = None if name == "id" else self.schema.field(name)
            header = "id" if spec is None else spec.header
            self.tree.heading(name, text=header, command=lambda n=name: self.sort_by(n))
            # starting widths only: ``fit_columns`` has the last word after every fill
            if spec is None or spec.type in (FieldType.INT, FieldType.BOOL):
                width = 60
            elif spec.type in (FieldType.MULTILINE, FieldType.URL):
                width = 320
            elif spec.type is FieldType.DATE:
                width = 100
            else:
                width = 180
            stretch = spec is not None and spec.type is FieldType.MULTILINE
            anchor = "center" if spec is not None and spec.is_flag else "w"
            self.tree.column(name, width=width, minwidth=40, stretch=stretch, anchor=anchor)
        self.pane.set_display(self._shown(ALL_COLUMNS))  # the stacked fields are hidden from the start
        self.tree.bind("<<TreeviewSelect>>", self._on_select, add="+")  # after the pane's own selection sync
        bind_horizontal_scroll(self.tree)
        self._heading_hint: str | None = None
        self.tree.bind("<Motion>", self._on_heading_motion)
        paned.add(self.pane, weight=3)

        form_box = ttk.LabelFrame(paned, text=f"{self.schema.label} details")
        self.form = ScrollableFrame(form_box)
        self.form.pack(fill="both", expand=True)
        self._build_form(self.form.inner)
        paned.add(form_box, weight=2)

    def _build_form(self, parent: ttk.Frame) -> None:
        factory = WidgetFactory(self.brain.lookups)
        parent.columnconfigure(1, weight=1)
        row = 0
        for spec in self.schema.fields:
            if spec.group:
                continue
            ttk.Label(parent, text=spec.header + (" *" if spec.required else "")).grid(
                row=row, column=0, sticky="ne", padx=(4, 8), pady=3
            )
            widget = factory.create(parent, spec)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.widgets[spec.name] = widget
            row += 1
        for group, specs in self.schema.groups().items():
            if not group:
                continue
            box = ttk.LabelFrame(parent, text=group.capitalize())
            box.grid(row=row, column=0, columnspan=2, sticky="ew", padx=4, pady=6)
            grid_row = 0
            flag_col = 0
            for spec in specs:
                if spec.is_flag:
                    widget = factory.create(box, spec)
                    widget.grid(row=grid_row, column=flag_col, sticky="w", padx=4, pady=1)
                    flag_col += 1
                    if flag_col == 3:
                        flag_col = 0
                        grid_row += 1
                else:
                    if flag_col:
                        grid_row += 1
                        flag_col = 0
                    ttk.Label(box, text=spec.header).grid(row=grid_row, column=0, sticky="w", padx=4, pady=2)
                    widget = factory.create(box, spec)
                    widget.grid(row=grid_row, column=1, columnspan=2, sticky="ew", pady=2)
                    grid_row += 1
                self.widgets[spec.name] = widget
            row += 1

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        result = self.brain.execute("list", entity=self.schema.name, actor="gui")
        if not result.ok:
            self.window.notify_error("Could not load rows", "; ".join(result.errors))
            return
        self.rows = result.data
        self.by_id = {r["id"]: r for r in self.rows}
        if self.selected_id not in self.by_id:
            self.selected_id = None
        self._populate()

    def _visible_rows(self) -> list[dict[str, Any]]:
        needle = self.search_var.get().strip().casefold()
        rows = self.rows
        if needle:
            rows = [r for r in rows if any(needle in str(v).casefold() for v in r.values() if v not in (None, ""))]
        if self.sort_key:
            key = self.sort_key

            def sort_value(r: dict[str, Any]) -> tuple[int, Any]:
                v = r.get(key)
                if v is None:
                    return (1, 0)
                return (0, v.casefold() if isinstance(v, str) else v)

            rows = sorted(rows, key=sort_value, reverse=self.sort_desc)
        return rows

    def _values(self, row: dict[str, Any]) -> list[str]:
        """One cell per data column, in the tree's column order."""
        return [cell_text(None if c == "id" else self.schema.field(c), row.get(c)) for c in self.columns]

    def _insert_stacked(self, rows: list[dict[str, Any]]) -> None:
        """The rows as the stack: a PDP phase row, its lifecycle phase rows, their deliverables; the group
        rows have blank data cells and their tag, a deliverable row has every data cell plus the stacked text."""
        blanks = [""] * len(self.columns)
        spec = self.schema.field("deliverable")
        for iid, level, text, row in stack(rows):
            if row is None:
                tag = PDP_TAG if level == 0 else PHASE_TAG
                self.tree.insert("", "end", iid=iid, values=[*blanks, text], tags=(tag,))
            else:
                plan = INDENT * 2 + cell_text(spec, row.get("deliverable"))
                self.tree.insert("", "end", iid=iid, values=[*self._values(row), plan])

    def _populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        shown = self._visible_rows()
        if self.stacked:
            self._insert_stacked(shown)
            style_group_rows(self.tree, self.window.theme)
        else:
            for r in shown:
                self.tree.insert("", "end", iid=str(r["id"]), values=self._values(r))
            self.window.theme.stripe(self.tree)
        self.fit()
        self.count_var.set(f"{len(shown)} of {len(self.rows)} rows")
        if self.selected_id is not None and self.tree.exists(str(self.selected_id)):
            self.tree.selection_set(str(self.selected_id))
        self.pane.mirror(self._domain())

    def _domain(self) -> dict[str, Any]:
        """The rest of each enum column's domain: every value of its lookup (the list ``EnumWidget`` offers)."""
        lookups = self.brain.lookups
        return {
            spec.name: lookups.get(spec.lookup or "", ())
            for spec in self.schema.fields
            if spec.type is FieldType.ENUM and spec.lookup
        }

    def fit(self) -> dict[str, int]:
        """Every column as wide as the widest text in its domain: heading, cells, and for an enum field
        every value of its lookup, so a status column holds "Out-of-Scope" before any row says so.
        """
        return fit_columns(self.tree, self._domain())

    def sort_by(self, column: str, desc: bool | None = None) -> None:
        if column == PLAN:  # the stacked column's heading: back to the plan's own order
            self.sort_key, self.sort_desc = None, False
            self._populate()
            self.window.set_status("Plan order")
            return
        if desc is None:
            desc = not self.sort_desc if self.sort_key == column else False
        self.sort_key, self.sort_desc = column, desc
        self._populate()
        header = "id" if column == "id" else self.schema.field(column).header
        self.window.set_status(f"Sorted by {header}" + (", descending" if desc else ""))

    def _on_heading_motion(self, event: tk.Event) -> None:
        """Hovering a heading too narrow to show its text names the column; columns fit their headings
        since 0.7.1, so this rarely fires, but a user can still drag one narrow.
        """
        text = heading_under(self.tree, event)
        if text != self._heading_hint:
            self._heading_hint = text
            if text:
                self.window.set_status(f"Column: {text}")

    def set_columns(self, choice: str) -> None:
        """Show every column (`All`) or the non-flag columns plus one flag group, through ``displaycolumns``.

        The tree is never rebuilt: headings, widths, the sort and the selection survive, and a hidden
        column still answers ``tree.set``. The choice lives on this screen instance only.
        """
        self.pane.set_display(self._shown(choice))  # the frozen columns are on the left whatever the choice
        self.columns_var.set(choice)
        self.fit()

    def _shown(self, choice: str) -> list[str]:
        """The data columns the right tree displays for ``choice``; the stacked fields never, they are the
        ``plan`` column on the left."""
        if choice == ALL_COLUMNS:
            shown = self.columns
        else:
            group = self.column_groups[choice]
            shown = [
                c for c in self.columns
                if c == "id" or not self.schema.field(c).is_flag or self.schema.field(c).group == group
            ]
        return [c for c in shown if c not in STACKED] if self.stacked else list(shown)

    def select(self, row_id: int) -> None:
        if self.tree.exists(str(row_id)):
            self.tree.selection_set(str(row_id))
            self.tree.see(str(row_id))
        self._load(row_id)

    def _on_select(self, _event: tk.Event | None = None) -> None:
        selection = self.tree.selection()
        if selection and not is_group(selection[0]):  # a PDP or lifecycle phase row is a heading, not a record
            self._load(int(selection[0]))

    def _load(self, row_id: int) -> None:
        row = self.by_id.get(row_id)
        if row is None:
            return
        self.selected_id = row_id
        for name, widget in self.widgets.items():
            widget.set(row.get(name))
        self.window.set_status(f"{self.schema.label} {row_id} selected")

    def form_data(self) -> dict[str, Any]:
        return {name: widget.get() for name, widget in self.widgets.items()}

    # -- actions --------------------------------------------------------
    def new(self) -> None:
        self.selected_id = None
        self.tree.selection_remove(*self.tree.selection())
        for widget in self.widgets.values():
            widget.clear()
        if self.widgets:
            next(iter(self.widgets.values())).focus_field()
        self.window.set_status(f"New {self.schema.label.lower()}: fill the form and press Save (Ctrl+S)")

    def save(self) -> None:
        data = self.form_data()
        if self.selected_id is None:
            result = self.window.run("create", entity=self.schema.name, data=data)
        else:
            result = self.window.run("update", entity=self.schema.name, id=self.selected_id, data=data)
        if not result.ok:
            return
        self.selected_id = result.data["id"]
        self.refresh()
        self.select(self.selected_id)
        note = f"Saved {self.schema.label.lower()} {self.selected_id}"
        if result.warnings:
            note += " (" + "; ".join(result.warnings) + ")"
        self.window.set_status(note)

    def delete(self) -> None:
        if self.selected_id is None:
            self.window.set_status("Select a row to delete")
            return
        row_id = self.selected_id
        if not self.window.confirm("Delete", f"Delete {self.schema.label.lower()} {row_id}?"):
            return
        result = self.window.run("delete", entity=self.schema.name, id=row_id)
        if result.ok:
            self.new()
            self.refresh()
            self.window.set_status(f"Deleted {self.schema.label.lower()} {row_id}")

    def duplicate(self) -> None:
        if self.selected_id is None:
            self.window.set_status("Select a row to duplicate")
            return
        self.selected_id = None
        self.tree.selection_remove(*self.tree.selection())
        if "order" in self.widgets:
            self.widgets["order"].clear()
        self.window.set_status("Duplicating: edit the form and press Save to create the copy")
