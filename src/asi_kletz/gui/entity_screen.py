"""EntityScreen: the generic table-plus-form page produced for every entity from its schema."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING, Any

from ..generate.plan_schedule import SOURCE_DEFAULT, SOURCE_POINTS, weight_of
from ..schema import EntitySchema, FieldSpec, FieldType
from ..schema.people import is_role, people_lines, people_of, people_text
from ..schema.urls import urls_text
from .screens import (
    INDENT,
    PDP_TAG,
    PHASE_TAG,
    PLAN,
    PLAN_HEADER,
    STACKED,
    Screen,
    ScrollableFrame,
    bind_horizontal_scroll,
    fit_columns,
    heading_under,
    is_group,
    stack,
    style_group_rows,
)
from .widgets import LOOK_UP, FieldWidget, JiraPickerWidget, PeopleWidget, PointsWidget, WidgetFactory, append_line

if TYPE_CHECKING:
    from .main_window import MainWindow
    from .people_lookup import PeopleLookup

TRUNCATE = 70  # a cell shows this much of a long text; the column fits the clipped text, not the value
HANDLES = ("id", "order")  # the handles have no column anywhere (0.9.0): the status bar and the details title name them
# 0.14.0, the owner: "the first item is a button that asks you for a local folder to save a new version or view of
# the model in the form of that safety plan deliverable; then following that please have all the parameters for
# the doc and then after that all content as is today". The standards pane sits at the top of the Safety Plan's
# details form: the Export document… button and the row's standards, the Document parameters box, the row's own
# values as the export fills them, then the form as before.
EXPORT_BUTTON = "Export document…"
SAVE_PARAMETERS = "Save parameters"
SELECT_A_ROW = "Select a deliverable to see its standards"
# 0.19.0: a role in the Document parameters box is a small text box, one person per line as ``Name <email>``,
# with a caption saying how many people it holds, or that its value is a legacy name with no email yet, or that
# it holds no one; Save parameters writes the lines through `create` / `update parameter` (`people`), whose guard
# names the role and the line of anything wrong, in the status bar.
PEOPLE_CAPTION = "one per line: Name <email>"
LEGACY_CAPTION = "no email yet: complete each line as Name <email>"
EMPTY_CAPTION = "no one yet; " + PEOPLE_CAPTION
# 0.11.3, the owner: the Safety Plan screen is one table, no frozen split and no flag columns; the flags are the
# Safety Plan Matrix's business. The table shows the plan stacked (PDP phase > lifecycle phase > deliverable) in
# one column and every other non-flag visible field beside it; the form below still edits everything.


def cell_text(spec: FieldSpec | None, value: Any) -> str:
    if value is None:
        return ""
    if spec is not None and spec.type is FieldType.BOOL:
        return "✓" if value else ""
    if isinstance(value, (list, tuple)):  # the people of a role: ``Ann Lee <ann@...>; Ben Ray <ben@...>``;
        # the work product URLs: ``https://a; https://b`` (0.20.0)
        value = urls_text(value) if spec is not None and spec.picker == "urls" else people_text(value)
    text = str(value).replace("\n", " ")
    return text if len(text) <= TRUNCATE else text[: TRUNCATE - 1] + "…"


def role_caption(row: dict[str, Any] | None) -> str:
    """What the caption beside a role's box says for its stored row: the count, the legacy state, or no one."""
    people = people_of(row.get("people")) if row and row.get("people") else []
    if people:
        return f"{len(people)} {'person' if len(people) == 1 else 'people'}; {PEOPLE_CAPTION}"
    if row and row.get("value") not in (None, ""):
        return LEGACY_CAPTION
    return EMPTY_CAPTION


class EntityScreen(Screen):
    def __init__(self, master: tk.Misc, window: MainWindow, schema: EntitySchema) -> None:
        self.schema = schema
        self.rows: list[dict[str, Any]] = []
        self.by_id: dict[int, dict[str, Any]] = {}
        self.selected_id: int | None = None
        self.sort_key: str | None = None
        self.sort_desc = False
        self.widgets: dict[str, FieldWidget] = {}
        self.standards: list[dict[str, Any]] = []  # the selected row's standards (0.14.0), from `standards for`
        self.standards_dir = ""
        self.param_vars: dict[str, tk.StringVar] = {}  # the document-level parameters of those standards
        self.param_entries: dict[str, ttk.Entry] = {}  # the plain ones (vehicle_type): one entry each
        self.param_texts: dict[str, tk.Text] = {}  # the roles (0.19.0): one small box each, a person per line
        self.param_initial: dict[str, str] = {}  # what each role's box showed when built: unchanged is not saved
        self.jira_statuses: dict[str, str | None] = {}  # the statuses the last export of this session fetched
        self.ticket_loader: Any = None  # the Load tickets fetch in flight, made on the first press (0.15.0)
        self.lookup_buttons: dict[str, ttk.Button] = {}  # the pane's Look up button per role (0.20.0)
        self.lookup_window: PeopleLookup | None = None  # the Outlook search window, one at a time (0.20.0)
        super().__init__(master, window)

    # -- layout ---------------------------------------------------------
    def build(self) -> None:
        # the plan is stacked (PDP phase > lifecycle phase > deliverable in one column) when the entity has the
        # three fields; the columns beside it are every visible non-flag field, the handles and the stacked
        # three excepted. A flag has no column: the Safety Plan Matrix shows the flags (0.11.3).
        self.stacked = all(self.schema.has(name) for name in STACKED)
        self.columns = [
            f.name for f in self.schema.visible_fields
            if f.name not in HANDLES and not f.is_flag and not (self.stacked and f.name in STACKED)
        ]
        tree_columns = [PLAN, *self.columns] if self.stacked else list(self.columns)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate())
        ttk.Entry(toolbar, textvariable=self.search_var, width=30).pack(side="left", padx=(4, 12))
        for text, command in (
            ("New", self.new), ("Save", self.save), ("Delete", self.delete),
            ("Duplicate", self.duplicate), ("Refresh", self.refresh),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)
        self.count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)

        table = ttk.Frame(paned)
        self.tree = ttk.Treeview(table, columns=tree_columns, show="headings", selectmode="browse")
        self.ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.xbar = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.ybar.set, xscrollcommand=self.xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.ybar.grid(row=0, column=1, sticky="ns")
        self.xbar.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        if self.stacked:
            self.tree.heading(PLAN, text=PLAN_HEADER, command=lambda: self.sort_by(PLAN))
            self.tree.column(PLAN, width=360, minwidth=40, stretch=False, anchor="w")
        for name in self.columns:
            spec = self.schema.field(name)
            self.tree.heading(name, text=spec.header, command=lambda n=name: self.sort_by(n))
            # starting widths only: ``fit_columns`` has the last word after every fill
            if spec.type in (FieldType.INT, FieldType.BOOL):
                width = 60
            elif spec.type in (FieldType.MULTILINE, FieldType.URL):
                width = 320
            elif spec.type is FieldType.DATE:
                width = 100
            else:
                width = 180
            self.tree.column(name, width=width, minwidth=40, stretch=spec.type is FieldType.MULTILINE, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        bind_horizontal_scroll(self.tree)
        self._heading_hint: str | None = None
        self.tree.bind("<Motion>", self._on_heading_motion)
        paned.add(table, weight=3)

        # the details frame names the selected row (``Safety Plan Row details · row 2``): the handle a command
        # needs is on screen without a column
        self.form_box = ttk.LabelFrame(paned, text=self.details_title(None))
        self.form = ScrollableFrame(self.form_box)
        self.form.pack(fill="both", expand=True)
        self._build_form(self.form.inner)
        paned.add(self.form_box, weight=2)

    def details_title(self, row_id: int | None) -> str:
        title = f"{self.schema.label} details"
        return title if row_id is None else f"{title} · row {row_id}"

    def _build_form(self, parent: ttk.Frame) -> None:
        factory = WidgetFactory(self.brain.lookups)
        parent.columnconfigure(1, weight=1)
        row = 0
        if self.stacked:  # the Safety Plan: the standards pane first (0.14.0), then the form as before
            self._build_standards_pane(parent)
            row = 1
        for spec in self.schema.visible_fields:  # a hidden field has no widget
            if spec.group:
                continue
            ttk.Label(parent, text=spec.header + (" *" if spec.required else "")).grid(
                row=row, column=0, sticky="ne", padx=(4, 8), pady=3
            )
            extra: dict[str, Any] = {}
            if spec.picker == "jira":
                extra["load"] = self.load_tickets
            elif spec.picker == "people":  # 0.20.0: the Look up button opens the Outlook search
                extra["lookup"] = self.lookup_people
            elif spec.picker == "urls":  # 0.22.0: the link lines carry the kind; the owner's extra kinds too
                extra["hosts"] = self.brain.url_hosts
            widget = factory.create(parent, spec, **extra)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            self.widgets[spec.name] = widget
            row += 1
        if self.is_parameters:  # the Parameters screen: the name decides which of Value and People is live
            self.widgets["name"].var.trace_add("write", lambda *_: self._sync_parameter_widgets())
            self._sync_parameter_widgets()
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

    # -- the Parameters screen (0.19.0) ---------------------------------------------------------------
    @property
    def is_parameters(self) -> bool:
        """The Parameters screen: an entity with a ``name``, a ``value`` and a ``people`` editor."""
        return (
            self.schema.name == "parameter"
            and isinstance(self.widgets.get("people"), PeopleWidget)
            and "name" in self.widgets and "value" in self.widgets
        )

    def _sync_parameter_widgets(self) -> None:
        """A role row edits its people and shows its value read-only (a legacy name, or nothing); any other
        row edits its value and its people box is greyed."""
        role = is_role((self.widgets["name"].get() or "").strip())
        self.widgets["value"].entry.configure(state="readonly" if role else "normal")
        self.widgets["people"].set_enabled(role)

    # -- the Jira pickers (0.15.0) ---------------------------------------------------------------------
    def pickers(self) -> list[JiraPickerWidget]:
        return [w for w in self.widgets.values() if isinstance(w, JiraPickerWidget)]

    def feed_pickers(self) -> None:
        """Every picker lists the issues of the window's last JIRA Live Data fetch (``window.jira_live``)."""
        result = self.window.jira_live
        issues = list((result.data or {}).get("issues") or []) if result is not None and result.ok else []
        for widget in self.pickers():
            widget.set_issues(issues)

    def set_pickers_busy(self, busy: bool) -> None:
        for widget in self.pickers():
            widget.load_button.state(["disabled"] if busy else ["!disabled"])

    def load_tickets(self) -> bool:
        """Load tickets: the live screen's fetch, because a person pressed it; the pickers fill when it lands."""
        from .ticket_loader import TicketLoader

        if self.ticket_loader is None:
            self.ticket_loader = TicketLoader(self)
        return self.ticket_loader.fetch()

    # -- the Outlook lookup (0.20.0) ---------------------------------------------------------------------
    def lookup_people(self, insert: Callable[[str], None], initial: str = "") -> PeopleLookup:
        """Look up: the Outlook search window (one at a time; a second press brings it to the front with the
        new target); the picked ``Name <email>`` line goes to ``insert``, the editor that asked."""
        from .people_lookup import PeopleLookup

        win = self.lookup_window
        if win is not None and win.winfo_exists():
            win.on_pick = insert
            if initial:
                win.query_var.set(initial)
            win.lift()
            win.entry.focus_set()
            return win
        win = self.lookup_window = PeopleLookup(self.window, insert, initial)
        return win

    def lookup_for_role(self, name: str) -> PeopleLookup:
        """The pane's Look up button of a role: the pick lands as a new line of that role's box."""
        return self.lookup_people(lambda line, n=name: append_line(self.param_texts[n], line))

    def destroy(self) -> None:
        if self.ticket_loader is not None:
            self.ticket_loader.cancel()
        if self.lookup_window is not None and self.lookup_window.winfo_exists():
            self.lookup_window.destroy()
        super().destroy()

    # -- the standards pane (0.14.0) ---------------------------------------------------------------
    def _build_standards_pane(self, parent: ttk.Frame) -> None:
        pane = ttk.Frame(parent)
        pane.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=(2, 8))
        top = ttk.Frame(pane)
        top.pack(fill="x")
        self.export_button = ttk.Button(top, text=EXPORT_BUTTON, command=self.export_document, state="disabled")
        self.export_button.pack(side="left")
        self.standard_var = tk.StringVar(value=SELECT_A_ROW)
        ttk.Label(top, textvariable=self.standard_var, style="Muted.TLabel", wraplength=700).pack(
            side="left", padx=(8, 0), fill="x", expand=True
        )
        self.params_box = ttk.LabelFrame(pane, text="Document parameters")
        self.params_box.pack(fill="x", pady=(6, 0))
        self.params_box.columnconfigure(1, weight=1)
        self.save_params_button = ttk.Button(self.params_box, text=SAVE_PARAMETERS, command=self.save_parameters)
        self.params_note = ttk.Label(self.params_box, text="", style="Muted.TLabel")
        self.row_values_var = tk.StringVar()
        ttk.Label(pane, textvariable=self.row_values_var, style="Muted.TLabel", wraplength=700).pack(
            anchor="w", pady=(4, 0)
        )
        self._refresh_standards(None)

    def _refresh_standards(self, row: dict[str, Any] | None) -> None:
        """What the pane says for ``row``: its standards, their document parameters prefilled from the
        ``parameter`` table, the row's own values as the export fills them. ``None`` empties it."""
        if not self.stacked:
            return
        self.standards = []
        if row is not None:
            result = self.window.run_quiet("standards", action="for", row=row["id"])
            if result.ok:
                self.standards = list(result.data.get("standards") or [])
                self.standards_dir = str(result.data.get("standards_dir") or "")
        if row is None:
            self.standard_var.set(SELECT_A_ROW)
        elif self.standards:
            self.standard_var.set("Standard: " + ", ".join(f"{s['title']} ({s['folder']})" for s in self.standards))
        else:
            self.standard_var.set(
                f"No standard for this deliverable: its QMS references name none in {self.standards_dir}"
            )
        self.export_button.configure(state="normal" if self.standards else "disabled")
        self._rebuild_parameter_entries()
        self.row_values_var.set(self._row_values_text(row))

    def _rebuild_parameter_entries(self) -> None:
        for child in self.params_box.winfo_children():
            if child not in (self.save_params_button, self.params_note):
                child.destroy()
        self.save_params_button.grid_forget()
        self.params_note.grid_forget()
        self.param_vars, self.param_entries, self.param_texts, self.param_initial = {}, {}, {}, {}
        self.lookup_buttons = {}
        names: list[str] = []
        for standard in self.standards:
            names.extend(n for n in standard.get("document_parameters", ()) if n not in names)
        stored = self._stored_rows()
        for index, name in enumerate(names):
            ttk.Label(self.params_box, text=name).grid(row=index, column=0, sticky="nw", padx=4, pady=1)
            row = stored.get(name)
            if is_role(name):  # a small box, one person per line; a legacy name prefilled so it can be completed
                if row and row.get("people"):
                    initial = people_lines(row["people"])
                else:
                    initial = str((row or {}).get("value") or "")
                lines = initial.count("\n") + 1
                box = tk.Text(self.params_box, height=max(2, min(lines + 1, 5)), width=48, wrap="none")
                box.insert("1.0", initial)
                box.grid(row=index, column=1, sticky="ew", padx=(0, 4), pady=1)
                ttk.Label(self.params_box, text=role_caption(row), style="Muted.TLabel").grid(
                    row=index, column=2, sticky="nw", padx=(0, 4), pady=1
                )
                button = ttk.Button(self.params_box, text=LOOK_UP, command=lambda n=name: self.lookup_for_role(n))
                button.grid(row=index, column=3, sticky="nw", padx=(0, 4), pady=1)
                self.param_texts[name], self.param_initial[name] = box, initial
                self.lookup_buttons[name] = button
                continue
            var = tk.StringVar(value=str((row or {}).get("value") or ""))
            entry = ttk.Entry(self.params_box, textvariable=var, width=40)
            entry.grid(row=index, column=1, sticky="ew", padx=(0, 4), pady=1)
            self.param_vars[name], self.param_entries[name] = var, entry
        if names:
            self.save_params_button.grid(row=len(names), column=0, columnspan=3, sticky="w", padx=4, pady=(4, 2))
        else:
            text = "No document parameters: the selected deliverable has no standard" if self.standards == [] else ""
            self.params_note.configure(text=text)
            self.params_note.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=2)

    def _stored_rows(self) -> dict[str, dict[str, Any]]:
        """``{name: row}`` from the ``parameter`` table: the global row, a selected standard's own winning."""
        result = self.window.run_quiet("list", entity="parameter", order_by="standard,name,id")
        folders = {s["folder"] for s in self.standards}
        rows: dict[str, dict[str, Any]] = {}
        for row in result.data or []:
            if (row.get("standard") or "") in ("", *folders):
                rows[row["name"]] = row  # "" sorts first, so a standard's own row overwrites the global one
        return rows

    def people_text_of(self, name: str) -> str:
        """What a role's box holds now, as typed (one person per line)."""
        return self.param_texts[name].get("1.0", "end-1c").strip()

    def _row_values_text(self, row: dict[str, Any] | None) -> str:
        if row is None:
            return ""
        order = row.get("order")
        head = f"This row (row_{order}_*): " if order is not None else "This row: "
        weight, source = weight_of(row, self.brain.default_points)
        if source == SOURCE_POINTS:
            points = f"{weight} points"
        elif source == SOURCE_DEFAULT:
            points = f"{weight} points (the panel's default, no points chosen)"
        else:
            points = f"no points chosen and no default (the floor {weight} is not exported)"
        sprint_end = f"sprint end {row['sprint_end']}" if row.get("sprint_end") else "no sprint end (unscheduled)"
        key = (row.get("jira_key") or "").strip().upper()
        if not key:
            jira = "no Jira key: the status stays unfilled"
        elif self.jira_statuses.get(key):
            jira = f"Jira {key}: {self.jira_statuses[key]} (as of the last export)"
        else:
            jira = f"Jira {key}: status fetched on export"
        return head + " · ".join((points, sprint_end, jira))

    def save_parameters(self) -> None:
        """Upsert the pane's values as ``parameter`` rows through the verbs, so an agent can do the same: a plain
        parameter's entry as ``value``, a role's lines as ``people`` (the guard sorts them; its errors, naming
        the role and the line, reach the status bar through ``window.run``). A role's box left as it was built
        (a legacy name included) is not saved."""
        if self.selected_id is None or not (self.param_vars or self.param_texts):
            self.window.set_status("Select a deliverable with a standard to save its parameters")
            return
        existing = self.window.run_quiet("list", entity="parameter")
        folders = {s["folder"] for s in self.standards}
        by_name: dict[str, dict[str, Any]] = {}
        for row in sorted(existing.data or [], key=lambda r: (r.get("standard") or "") != ""):  # global first
            if (row.get("standard") or "") in ("", *folders):
                by_name.setdefault(row["name"], row)
        saved = 0
        for name, var in self.param_vars.items():
            value = var.get().strip()
            current = by_name.get(name)
            if current is None:
                if not value:
                    continue
                result = self.window.run("create", entity="parameter", data={"name": name, "value": value})
            elif (current.get("value") or "") != value:
                result = self.window.run("update", entity="parameter", id=current["id"], data={"value": value})
            else:
                continue
            if not result.ok:
                return
            saved += 1
        for name in self.param_texts:
            text = self.people_text_of(name)
            current = by_name.get(name)
            if text == self.param_initial[name] or (current is None and not text):
                continue
            if current is None:
                result = self.window.run("create", entity="parameter", data={"name": name, "people": text})
            else:
                result = self.window.run("update", entity="parameter", id=current["id"], data={"people": text})
            if not result.ok:
                return
            saved += 1
        if saved:
            self._refresh_standards(self.by_id.get(self.selected_id))  # the captions and the sorted lines
        self.window.set_status(f"Saved {saved} parameter(s)" if saved else "Parameters unchanged")

    def export_document(self) -> None:
        """The owner's first item: a folder, then ``plan export`` for the selected row into it."""
        if self.selected_id is None or not self.standards:
            self.window.set_status("Select a deliverable with a standard to export")
            return
        if self.window.interactive:
            folder = filedialog.askdirectory(
                parent=self.window, initialdir=self.brain.out_dir, title="Folder for the exported document",
            )
            if not folder:
                self.window.set_status("Export cancelled")
                return
        else:
            folder = self.brain.out_dir
        result = self.window.run("plan", action="export", row=self.selected_id, out=folder)
        if not result.ok:
            return
        self.jira_statuses.update(result.data.get("statuses") or {})
        files = [Path(p).name for e in result.data["exports"] for p in e["files"].values()]
        unfilled = sum(len(e["unfilled"]) for e in result.data["exports"])
        exact = [fmt for e in result.data["exports"] for fmt, yes in (e.get("exact") or {}).items() if yes]
        how = f" ({' and '.join(sorted(set(exact)))} the template exactly)" if exact else ""
        self.window.set_status(f"Exported {', '.join(files)} to {folder}{how}; {unfilled} parameter(s) still unfilled")
        row = self.by_id.get(self.selected_id)
        self.row_values_var.set(self._row_values_text(row))

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
            self.form_box.configure(text=self.details_title(None))
        self._populate()
        self.feed_pickers()  # a fetch on the live screen since the last refresh reaches the pickers too

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
                if isinstance(v, (list, tuple)):  # the people column, the urls column: sorted by their text
                    v = urls_text(v) if self.schema.field(key).picker == "urls" else people_text(v)
                return (0, v.casefold() if isinstance(v, str) else v)

            rows = sorted(rows, key=sort_value, reverse=self.sort_desc)
        return rows

    def _values(self, row: dict[str, Any]) -> list[str]:
        """One cell per data column, in the tree's column order."""
        return [cell_text(self.schema.field(c), row.get(c)) for c in self.columns]

    def _insert_stacked(self, rows: list[dict[str, Any]]) -> None:
        """The rows as the stack: a PDP phase row, its lifecycle phase rows, their deliverables; the group
        rows have blank data cells and their tag, a deliverable row has every data cell plus the stacked text."""
        blanks = [""] * len(self.columns)
        spec = self.schema.field("deliverable")
        for iid, level, text, row in stack(rows):
            if row is None:
                tag = PDP_TAG if level == 0 else PHASE_TAG
                self.tree.insert("", "end", iid=iid, values=[text, *blanks], tags=(tag,))
            else:
                plan = INDENT * 2 + cell_text(spec, row.get("deliverable"))
                self.tree.insert("", "end", iid=iid, values=[plan, *self._values(row)])

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

    def _domain(self) -> dict[str, Any]:
        """The rest of each enum column's domain: every value of its lookup (the list ``EnumWidget`` offers)."""
        lookups = self.brain.lookups
        return {
            spec.name: lookups.get(spec.lookup or "", ())
            for spec in self.schema.visible_fields
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
        header = self.schema.field(column).header
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
        self.form_box.configure(text=self.details_title(row_id))
        self._hand_defaults(row)
        for name, widget in self.widgets.items():
            widget.set(row.get(name))
        if self.is_parameters:
            self._sync_parameter_widgets()
        self._refresh_standards(row)
        self.window.set_status(f"{self.schema.label} {row_id} selected")

    def _hand_defaults(self, row: dict[str, Any] | None) -> None:
        """A field with ``default_from`` (points) shows that field's value as its placeholder: the row's default,
        else the floor from kletz.toml (``Brain.default_points``)."""
        for name, widget in self.widgets.items():
            spec = self.schema.field(name)
            if spec.default_from and isinstance(widget, PointsWidget):
                value = (row or {}).get(spec.default_from)
                widget.set_default(value if value not in (None, "") else self.brain.default_points)

    def form_data(self) -> dict[str, Any]:
        """What Save sends: the editable fields only (a calculated field or a loader's is shown, never sent)."""
        editable = {spec.name for spec in self.schema.editable_fields}
        return {name: widget.get() for name, widget in self.widgets.items() if name in editable}

    # -- actions --------------------------------------------------------
    def new(self) -> None:
        self.selected_id = None
        self.form_box.configure(text=self.details_title(None))
        self.tree.selection_remove(*self.tree.selection())
        self._hand_defaults(None)
        self._refresh_standards(None)
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
        self.form_box.configure(text=self.details_title(None))
        self.tree.selection_remove(*self.tree.selection())
        if "order" in self.widgets:
            self.widgets["order"].clear()
        self.window.set_status("Duplicating: edit the form and press Save to create the copy")
