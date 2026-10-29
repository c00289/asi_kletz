"""ControlStructureScreen: the CRUD for STPA control structures (docs/control-structure-plan.md, 5; 0.24.0).

Three panes. **Left**, the structures: one row each with its system, status, revision and the six
counts, and the buttons New from… (the factory's builders), Duplicate, Delete (asks, then
``cascade``), Import draw.io…, Validate (the report in the status bar and the panel under the
list) and Export… (the dialog). **Middle**, the selected structure's parts as a stacked tree, the
``stack()`` idea of the Safety Plan: a controller row, under it its algorithms, its process-model
entries and the arrows that leave it with their signals; the notes at the end; a search box; a
form for whatever row is selected with Save, New child (the kind depends on the selection) and
Delete. **Right**, the preview: escher's PNG of the structure, re-rendered off the Tk thread
after every save into ``figures/`` under the out folder, scaled to fit, the OCR verdict and the
layout-issue count under it, and Open in VS Code on the ``.drawio`` when ``code`` is on the PATH.

Every button calls a verb through the window (``window.run``); the two things that take seconds,
``cs export`` and the preview's render, run on a worker thread (``BackgroundFetch``) and are
polled with ``after``, so the Tk thread only ever shows "Exporting…" and the answer. The export
dialog's work is the ``cs export`` verb: an agent gets the same Result from ``/execute``. The wheel
rule holds (the window unbinds the wheel from every combobox), and every Treeview iid is unique.
"""

from __future__ import annotations

import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk
from typing import TYPE_CHECKING, Any

from ..commands import Result
from ..prefs import read_prefs, write_prefs
from ..schema import FieldSpec, FieldType, slugify
from ..services.control_structure_service import DATASET_KEYS, PART_ENTITIES
from ..stpa.factory import DEFAULT_FORMATS, EXPORT_DIR, FORMATS
from .background import POLL_MS, BackgroundFetch
from .screens import Screen, ScrollableFrame, fit_columns
from .widgets import FieldWidget, ListWidget, WidgetFactory

if TYPE_CHECKING:
    from .main_window import MainWindow

INDENT = "    "
PREVIEW_FORMATS = ("drawio", "png")  # the picture to look at and the file Open in VS Code opens
PREF_EXPORT_DIR = "cs_export_dir"  # the preferences key: the last folder exported into
STRUCTURE_COLUMNS = ("name", "system", "status", "revision", *DATASET_KEYS.values())
COUNT_HEADERS = {
    "controllers": "controllers", "algorithms": "algorithms", "process_model_entries": "process model",
    "edges": "edges", "signals": "signals", "notes": "notes",
}
PART_LABELS = {
    "cs_controller": "controller", "cs_algorithm": "algorithm", "cs_process_model_entry": "process model entry",
    "cs_edge": "edge", "cs_signal": "signal", "cs_note": "note",
}
# which field of a part names its controller or its edge: the form offers the keys in a list
KEY_FIELDS = {
    "cs_algorithm": {"controller": "controllers"},
    "cs_process_model_entry": {"controller": "controllers"},
    "cs_edge": {"source": "controllers", "target": "controllers"},
    "cs_signal": {"edge": "edges"},
    "cs_note": {"attached_to": "controllers"},
}
NOTES_IID = "notes"


# -- the stack -----------------------------------------------------------------------------------
def stack(parts: dict[str, list[dict[str, Any]]]) -> list[tuple[str, int, str, str, str, str | None, dict | None]]:
    """The parts as a stack: ``(iid, level, text, kind, detail, entity, row)`` per line.

    Level 0 is a controller (iid ``controller:<key>``), level 1 its algorithms (``algorithm:<id>``),
    its process-model entries (``entry:<id>``) and the edges leaving it (``edge:<key>``), level 2
    the signals of an edge (``signal:<id>``). An edge whose source is no controller opens the group
    ``Edges without a source``; the notes close the stack under a ``Notes`` line. A Treeview iid
    must be unique: a group that repeats gets ``#2``, ``#3`` ... (the parts' keys are unique within
    a structure by rule, but a workbook edited by hand may say otherwise, and the screen paints it).
    """
    from ..schema.lists import lines_of

    lines: list[tuple[str, int, str, str, str, str | None, dict | None]] = []
    opened: dict[str, int] = {}

    def iid_of(group: str) -> str:
        opened[group] = opened.get(group, 0) + 1
        return group if opened[group] == 1 else f"{group}#{opened[group]}"

    algorithms: dict[str, list[dict]] = {}
    for a in parts.get("algorithms", []):
        algorithms.setdefault(a.get("controller") or "", []).append(a)
    entries: dict[str, list[dict]] = {}
    for p in parts.get("process_model_entries", []):
        entries.setdefault(p.get("controller") or "", []).append(p)
    edges: dict[str, list[dict]] = {}
    for e in parts.get("edges", []):
        edges.setdefault(e.get("source") or "", []).append(e)
    signals: dict[str, list[dict]] = {}
    for s in parts.get("signals", []):
        signals.setdefault(s.get("edge") or "", []).append(s)

    def edge_lines(e: dict, level: int) -> None:
        text = f"{'↑' if e.get('kind') == 'feedback' else '↓'} {e.get('target') or ''}"
        carried = signals.get(e.get("key") or "", [])
        detail = f"{len(carried)} signal{'s' if len(carried) != 1 else ''}"
        lines.append((iid_of(f"edge:{e.get('key')}"), level, INDENT * level + text, str(e.get("kind") or ""),
                      detail, "cs_edge", e))
        for s in carried:
            lines.append((iid_of(f"signal:{s['id']}"), level + 1, INDENT * (level + 1) + str(s.get("signal_id") or ""),
                          "signal", str(s.get("name") or ""), "cs_signal", s))

    seen_sources: set[str] = set()
    for c in parts.get("controllers", []):
        key = c.get("key") or ""
        seen_sources.add(key)
        detail = (c.get("responsibility") or "").splitlines()[0] if c.get("responsibility") else ""
        lines.append((iid_of(f"controller:{key}"), 0, str(c.get("name") or key), str(c.get("kind") or ""), detail,
                      "cs_controller", c))
        for a in algorithms.get(key, []):
            lines.append((iid_of(f"algorithm:{a['id']}"), 1, INDENT + str(a.get("code") or ""), "algorithm",
                          str(a.get("name") or ""), "cs_algorithm", a))
        for p in entries.get(key, []):
            variables = ", ".join(lines_of(p.get("variables")).splitlines())
            lines.append((iid_of(f"entry:{p['id']}"), 1, INDENT + str(p.get("heading") or ""), "process model",
                          variables, "cs_process_model_entry", p))
        for e in edges.get(key, []):
            edge_lines(e, 1)
    orphans = [e for source, group in edges.items() if source not in seen_sources for e in group]
    if orphans:
        lines.append((iid_of("edges:orphans"), 0, "Edges without a source", "", "", None, None))
        for e in orphans:
            edge_lines(e, 1)
    notes = parts.get("notes", [])
    if notes:
        lines.append((iid_of(NOTES_IID), 0, "Notes", "", f"{len(notes)}", None, None))
        for n in notes:
            text = (n.get("text") or "").replace("\n", " ")
            lines.append((iid_of(f"note:{n['id']}"), 1, INDENT + text, "note", str(n.get("attached_to") or ""),
                          "cs_note", n))
    return lines


class KeyWidget(FieldWidget):
    """A key field (a controller's or an edge's) as an editable combobox offering the current keys."""

    def build(self) -> None:
        self.var = tk.StringVar()
        self.combo = ttk.Combobox(self, textvariable=self.var, values=[], width=self.options.get("width", 30))
        self.combo.pack(side="left", fill="x", expand=True)

    def offer(self, keys: list[str]) -> None:
        self.combo.configure(values=list(keys))

    def get(self) -> Any:
        text = self.var.get().strip()
        return text or None

    def set(self, value: Any) -> None:
        self.var.set("" if value is None else str(value))

    def focus_field(self) -> None:
        self.combo.focus_set()


def _load_photo(path: str | Path, box: tuple[int, int]) -> tuple[Any, tuple[int, int]]:
    """The PNG at ``path`` as a Tk image scaled to fit ``box`` (width, height); Pillow when it is
    there (escher brings it), else ``tk.PhotoImage`` shrunk by an integer factor."""
    try:
        from PIL import Image, ImageTk
    except ImportError:  # pragma: no cover - Pillow comes with asi_escher
        image = tk.PhotoImage(file=str(path))
        factor = max(1, -(-image.width() // max(1, box[0])), -(-image.height() // max(1, box[1])))
        if factor > 1:
            image = image.subsample(factor, factor)
        return image, (image.width(), image.height())
    with Image.open(path) as source:
        picture = source.convert("RGBA")
        picture.thumbnail((max(1, box[0]), max(1, box[1])))
        return ImageTk.PhotoImage(picture), picture.size


class ControlStructureScreen(Screen):
    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        self.structures: list[dict[str, Any]] = []
        self.by_id: dict[int, dict[str, Any]] = {}
        self.structure_id: int | None = None
        self.parts: dict[str, list[dict[str, Any]]] = {k: [] for k in DATASET_KEYS.values()}
        self.lines: list[tuple] = []
        self.by_iid: dict[str, tuple] = {}
        self.selected: tuple[str, int] | None = None  # (entity, id) of the part in the form
        self.editing: str | None = None  # the entity of the form shown; a new row when ``selected`` is None
        self.forms: dict[str, tuple[ttk.Frame, dict[str, FieldWidget]]] = {}
        self.last_validation: dict[str, Any] | None = None
        self.last_export: Result | None = None
        self.last_preview: dict[str, Any] | None = None
        self.preview_path: str | None = None
        self.preview_fetch: BackgroundFetch | None = None
        self._preview_pending = False
        self._preview_job: str | None = None
        self._photo: Any = None
        self.code_path = shutil.which("code")
        super().__init__(master, window)

    # -- layout ---------------------------------------------------------
    def poll_later(self, callback: Any) -> None:
        """``after(POLL_MS, callback)``, remembered so ``destroy`` cancels what is still pending."""
        self._jobs.add(self.after(POLL_MS, callback))

    def destroy(self) -> None:
        if self._preview_job is not None:
            self._jobs.add(self._preview_job)
        for job in list(self._jobs):
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._jobs.clear()
        super().destroy()

    def build(self) -> None:
        self._jobs: set[str] = set()
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        self._build_left(paned)
        self._build_middle(paned)
        self._build_right(paned)

    def _build_left(self, paned: ttk.PanedWindow) -> None:
        left = ttk.Frame(paned)
        toolbar = ttk.Frame(left)
        toolbar.pack(fill="x", pady=(0, 6))
        for text, command in (
            ("New from…", self.new_from), ("Duplicate", self.duplicate), ("Delete", self.delete_structure),
            ("Import draw.io…", self.import_drawio), ("Validate", self.validate), ("Export…", self.export),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 4), pady=(0, 4))
        self.count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

        table = ttk.Frame(left)
        table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table, columns=STRUCTURE_COLUMNS, show="headings", selectmode="browse", height=8)
        for column in STRUCTURE_COLUMNS:
            self.tree.heading(column, text=COUNT_HEADERS.get(column, column))
            self.tree.column(column, width=70, minwidth=40, stretch=False)
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_structure_select)

        box = ttk.LabelFrame(left, text="Validation")
        box.pack(fill="both", expand=False, pady=(6, 0))
        self.validation = tk.Listbox(box, height=6, activestyle="none", font=self.window.theme.ui)
        bar = ttk.Scrollbar(box, orient="vertical", command=self.validation.yview)
        self.validation.configure(yscrollcommand=bar.set)
        self.validation.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        paned.add(left, weight=2)

    def _build_middle(self, paned: ttk.PanedWindow) -> None:
        middle = ttk.Frame(paned)
        toolbar = ttk.Frame(middle)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Label(toolbar, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._populate_parts())
        ttk.Entry(toolbar, textvariable=self.search_var, width=24).pack(side="left", padx=(4, 12))
        ttk.Button(toolbar, text="Save", command=self.save).pack(side="left", padx=2)
        self.new_child_button = ttk.Button(toolbar, text="New child ▾", command=self.new_child)
        self.new_child_button.pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete", command=self.delete_part).pack(side="left", padx=2)
        self.parts_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.parts_var, style="Muted.TLabel").pack(side="right")

        split = ttk.PanedWindow(middle, orient="vertical")
        split.pack(fill="both", expand=True)
        table = ttk.Frame(split)
        self.parts_tree = ttk.Treeview(table, columns=("part", "kind", "detail"), show="headings", selectmode="browse")
        for column, header, width in (("part", "part", 260), ("kind", "kind", 110), ("detail", "detail", 240)):
            self.parts_tree.heading(column, text=header)
            self.parts_tree.column(column, width=width, minwidth=40, stretch=column == "detail")
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.parts_tree.yview)
        self.parts_tree.configure(yscrollcommand=ybar.set)
        self.parts_tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.parts_tree.bind("<<TreeviewSelect>>", self._on_part_select)
        split.add(table, weight=3)

        self.form_box = ttk.LabelFrame(split, text="Details")
        self.form = ScrollableFrame(self.form_box)
        self.form.pack(fill="both", expand=True)
        self.form_hint = ttk.Label(self.form.inner, text="Select a part, or press New child.", style="Muted.TLabel")
        self.form_hint.pack(anchor="w", padx=6, pady=6)
        split.add(self.form_box, weight=2)
        paned.add(middle, weight=3)

    def _build_right(self, paned: ttk.PanedWindow) -> None:
        right = ttk.LabelFrame(paned, text="Preview (escher's PNG, re-rendered after every save)")
        self.preview = ttk.Label(right, anchor="center")
        self.preview.pack(fill="both", expand=True, padx=4, pady=4)
        self.preview.bind("<Configure>", self._on_preview_resize)
        self.verdict_var = tk.StringVar(value="No structure selected.")
        ttk.Label(right, textvariable=self.verdict_var, wraplength=360, justify="left", style="Muted.TLabel").pack(
            fill="x", padx=6
        )
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", padx=4, pady=(4, 6))
        ttk.Button(buttons, text="Re-render", command=self.render_preview).pack(side="left")
        self.vscode_button = ttk.Button(buttons, text="Open in VS Code", command=self.open_in_vscode, state="disabled")
        self.vscode_button.pack(side="left", padx=(6, 0))
        paned.add(right, weight=2)

    # -- data: the structures ---------------------------------------------
    def refresh(self) -> None:
        result = self.brain.execute("cs", action="list", actor="gui")
        if not result.ok:
            self.window.notify_error("Could not load control structures", "; ".join(result.errors))
            return
        self.structures = list(result.data)
        self.by_id = {r["id"]: r for r in self.structures}
        if self.structure_id not in self.by_id:
            self.structure_id = None
        self._populate_structures()
        if self.structure_id is not None:
            self._load_parts()

    def _populate_structures(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for r in self.structures:
            counts = r.get("counts") or {}
            values = [r.get("name") or "", r.get("system") or "", r.get("status") or "", r.get("revision") or ""]
            values += [counts.get(k, 0) for k in DATASET_KEYS.values()]
            self.tree.insert("", "end", iid=str(r["id"]), values=values)
        self.window.theme.stripe(self.tree)
        fit_columns(self.tree, {"status": self.brain.lookups.get("cs_status", ())})
        self.count_var.set(f"{len(self.structures)} structure{'s' if len(self.structures) != 1 else ''}")
        if self.structure_id is not None and self.tree.exists(str(self.structure_id)):
            self.tree.selection_set(str(self.structure_id))

    def _on_structure_select(self, _event: tk.Event | None = None) -> None:
        selection = self.tree.selection()
        if selection and int(selection[0]) != self.structure_id:
            self.select_structure(int(selection[0]))

    @property
    def structure(self) -> dict[str, Any] | None:
        return self.by_id.get(self.structure_id) if self.structure_id is not None else None

    @property
    def slug(self) -> str | None:
        row = self.structure
        return row["slug"] if row else None

    def select_structure(self, structure_id: int | None) -> None:
        """Show ``structure_id``'s parts, clear the form, render the preview."""
        self.structure_id = structure_id if structure_id in self.by_id else None
        if self.structure_id is not None and self.tree.exists(str(self.structure_id)):
            self.tree.selection_set(str(self.structure_id))
            self.tree.see(str(self.structure_id))
        self.selected = None
        self._show_form(None)
        self.validation.delete(0, "end")
        self.last_validation = None
        self._load_parts()
        if self.structure_id is None:
            self._clear_preview("No structure selected.")
            self.window.set_status("No control structure selected")
        else:
            self.window.set_status(f"Control structure {self.structure_id} selected: {self.structure['name']}")
            self.render_preview()

    # -- data: the parts ----------------------------------------------------
    def _load_parts(self) -> None:
        if self.structure_id is None:
            self.parts = {k: [] for k in DATASET_KEYS.values()}
        else:
            result = self.brain.execute("cs", action="get", target=self.structure_id, actor="gui")
            if not result.ok:
                self.window.notify_error("Could not load the parts", "; ".join(result.errors))
                return
            self.parts = result.data["parts"]
        self.lines = stack(self.parts)
        self.by_iid = {line[0]: line for line in self.lines}
        self._populate_parts()
        self._offer_keys()

    def _visible_lines(self) -> list[tuple]:
        needle = self.search_var.get().strip().casefold()
        if not needle:
            return list(self.lines)
        matches = [
            index for index, line in enumerate(self.lines)
            if any(needle in str(v).casefold() for v in (line[2], line[3], line[4]))
            or (line[6] and any(needle in str(v).casefold() for v in line[6].values() if v not in (None, "")))
        ]
        keep: set[int] = set()
        for index in matches:  # a match keeps the lines above it that open its groups
            keep.add(index)
            level = self.lines[index][1]
            for back in range(index - 1, -1, -1):
                if self.lines[back][1] < level:
                    keep.add(back)
                    level = self.lines[back][1]
                    if level == 0:
                        break
        return [line for index, line in enumerate(self.lines) if index in keep]

    def _populate_parts(self) -> None:
        self.parts_tree.delete(*self.parts_tree.get_children())
        shown = self._visible_lines()
        for iid, _level, text, kind, detail, _entity, _row in shown:
            self.parts_tree.insert("", "end", iid=iid, values=[text, kind, detail])
        self.window.theme.stripe(self.parts_tree)
        fit_columns(self.parts_tree, max_width=420)
        total = sum(len(v) for v in self.parts.values())
        self.parts_var.set(f"{len(shown)} of {len(self.lines)} rows · {total} parts")
        current = self._iid_of(self.selected) if self.selected else None
        if current and self.parts_tree.exists(current):
            self.parts_tree.selection_set(current)

    def _iid_of(self, selected: tuple[str, int]) -> str | None:
        entity, row_id = selected
        for iid, _l, _t, _k, _d, ent, row in self.lines:
            if ent == entity and row and row["id"] == row_id:
                return iid
        return None

    def _on_part_select(self, _event: tk.Event | None = None) -> None:
        selection = self.parts_tree.selection()
        if selection:
            self._load_part(selection[0])  # never selection_set here: that fires this event again

    def select_part(self, iid: str) -> None:
        """Select ``iid`` in the tree and fill the form with the row behind it (a group line clears it)."""
        if self.parts_tree.exists(iid) and self.parts_tree.selection() != (iid,):
            self.parts_tree.selection_set(iid)
            self.parts_tree.see(iid)
        self._load_part(iid)

    def _load_part(self, iid: str) -> None:
        line = self.by_iid.get(iid)
        if line is None:
            return
        _iid, _level, _text, _kind, _detail, entity, row = line
        if entity is None or row is None:
            self.selected = None
            self._show_form(None)
            return
        self.selected = (entity, int(row["id"]))
        self._show_form(entity, row)
        self.window.set_status(f"{self.brain.registry.get(entity).label} {row['id']} selected")

    # -- the form -------------------------------------------------------------
    def _form_for(self, entity: str) -> tuple[ttk.Frame, dict[str, FieldWidget]]:
        if entity in self.forms:
            return self.forms[entity]
        schema = self.brain.registry.get(entity)
        factory = WidgetFactory(self.brain.lookups)
        frame = ttk.Frame(self.form.inner)
        frame.columnconfigure(1, weight=1)
        widgets: dict[str, FieldWidget] = {}
        keyed = KEY_FIELDS.get(entity, {})
        grid_row = 0
        for spec in schema.fields:
            if spec.hidden or spec.name == "structure":
                continue
            ttk.Label(frame, text=spec.header + (" *" if spec.required else "")).grid(
                row=grid_row, column=0, sticky="ne", padx=(4, 8), pady=3
            )
            if spec.name in keyed:
                widget: FieldWidget = KeyWidget(frame, spec, self.brain.lookups)
            elif spec.type is FieldType.JSON:  # a list, one item per line
                widget = ListWidget(frame, spec, self.brain.lookups, **self._widget_options(spec))
            else:
                widget = factory.create(frame, spec, **self._widget_options(spec))
            widget.grid(row=grid_row, column=1, sticky="ew", pady=3)
            widgets[spec.name] = widget
            grid_row += 1
        self.forms[entity] = (frame, widgets)
        return frame, widgets

    @staticmethod
    def _widget_options(spec: FieldSpec) -> dict[str, Any]:
        return {"height": 3} if spec.type in (FieldType.MULTILINE, FieldType.JSON) else {}

    def _offer_keys(self) -> None:
        keys = {
            "controllers": [c.get("key") or "" for c in self.parts.get("controllers", [])],
            "edges": [e.get("key") or "" for e in self.parts.get("edges", [])],
        }
        for entity, (_frame, widgets) in self.forms.items():
            for field, source in KEY_FIELDS.get(entity, {}).items():
                widget = widgets.get(field)
                if isinstance(widget, KeyWidget):
                    widget.offer(keys[source])

    def _show_form(self, entity: str | None, row: dict[str, Any] | None = None, prefill: dict | None = None) -> None:
        for other, (frame, _w) in self.forms.items():
            if other != entity:
                frame.pack_forget()
        self.editing = entity
        if entity is None:
            self.form_hint.pack(anchor="w", padx=6, pady=6)
            self.form_box.configure(text="Details")
            return
        self.form_hint.pack_forget()
        frame, widgets = self._form_for(entity)
        self._offer_keys()
        frame.pack(fill="both", expand=True)
        label = self.brain.registry.get(entity).label
        for name, widget in widgets.items():
            widget.set((row or {}).get(name, (prefill or {}).get(name)))
        self.form_box.configure(text=f"{label} details" + (f" · row {row['id']}" if row else " · new"))

    def form_data(self) -> dict[str, Any]:
        if self.editing is None:
            return {}
        _frame, widgets = self._form_for(self.editing)
        return {name: widget.get() for name, widget in widgets.items()}

    @property
    def widgets(self) -> dict[str, FieldWidget]:
        """The widgets of the form shown (empty when none is)."""
        return self._form_for(self.editing)[1] if self.editing else {}

    # -- actions on a part --------------------------------------------------
    def child_options(self) -> list[tuple[str, dict[str, Any]]]:
        """What New child can make for the selection: ``(entity, prefill)`` pairs, the first the default."""
        if self.structure_id is None:
            return []
        if self.selected is None:
            return [("cs_controller", {}), ("cs_note", {})]
        entity, row_id = self.selected
        row = next((r for r in self.parts[DATASET_KEYS[entity]] if r["id"] == row_id), {})
        if entity == "cs_controller":
            key = row.get("key")
            return [
                ("cs_algorithm", {"controller": key}), ("cs_process_model_entry", {"controller": key}),
                ("cs_edge", {"source": key}), ("cs_note", {"attached_to": key}), ("cs_controller", {}),
            ]
        if entity == "cs_edge":
            return [("cs_signal", {"edge": row.get("key")}), ("cs_edge", {"source": row.get("source")})]
        if entity == "cs_signal":
            return [("cs_signal", {"edge": row.get("edge")})]
        if entity in ("cs_algorithm", "cs_process_model_entry"):
            return [(entity, {"controller": row.get("controller")})]
        return [("cs_note", {})]

    def new_child(self, entity: str | None = None) -> None:
        """Start a new part: ``entity`` when given, else the one choice, else a menu under the button."""
        options = self.child_options()
        if not options:
            self.window.set_status("Select a control structure first")
            return
        if entity is None and len(options) > 1 and self.window.interactive:
            menu = tk.Menu(self, tearoff=False)
            for ent, _prefill in options:
                menu.add_command(label=f"New {PART_LABELS[ent]}", command=lambda e=ent: self.new_child(e))
            x = self.new_child_button.winfo_rootx()
            y = self.new_child_button.winfo_rooty() + self.new_child_button.winfo_height()
            menu.tk_popup(x, y)
            return
        chosen = next(((e, p) for e, p in options if e == entity), None) if entity else options[0]
        if chosen is None:
            if entity not in PART_ENTITIES:
                self.window.set_status(f"Unknown part {entity!r}")
                return
            chosen = (entity, {})
        ent, prefill = chosen
        self.selected = None
        self.parts_tree.selection_remove(*self.parts_tree.selection())
        self._show_form(ent, None, prefill)
        widgets = self.widgets
        if widgets:
            first = next((w for n, w in widgets.items() if n not in prefill), next(iter(widgets.values())))
            first.focus_field()
        self.window.set_status(f"New {PART_LABELS[ent]}: fill the form and press Save (Ctrl+S)")

    new = new_child  # Ctrl+N

    def save(self) -> Result:
        if self.editing is None or self.slug is None:
            self.window.set_status("Nothing to save: select a part or press New child")
            return Result.failure("nothing to save", verb="update")
        entity = self.editing
        data = {**self.form_data(), "structure": self.slug}
        if self.selected is not None and self.selected[0] == entity:
            result = self.window.run("update", entity=entity, id=self.selected[1], data=data)
        else:
            result = self.window.run("create", entity=entity, data=data)
        if not result.ok:
            return result
        self.selected = (entity, int(result.data["id"]))
        self.refresh()
        iid = self._iid_of(self.selected)
        if iid:
            self.select_part(iid)
        note = f"Saved {PART_LABELS[entity]} {self.selected[1]}"
        if result.warnings:
            note += " (" + "; ".join(result.warnings) + ")"
        self.window.set_status(note)
        self.render_preview()
        return result

    def delete_part(self) -> Result:
        if self.selected is None:
            self.window.set_status("Select a part to delete")
            return Result.failure("nothing selected", verb="delete")
        entity, row_id = self.selected
        label = PART_LABELS[entity]
        question = f"Delete {label} {row_id}?"
        if entity == "cs_controller":
            question += " Its algorithms, process-model entries and the edges touching it go with it."
        elif entity == "cs_edge":
            question += " The signals it carries go with it."
        if not self.window.confirm("Delete", question):
            return Result.failure("cancelled", verb="delete")
        result = self.window.run("delete", entity=entity, id=row_id, cascade=True)
        if result.ok:
            self.selected = None
            self._show_form(None)
            self.refresh()
            self.window.set_status(f"Deleted {label} {row_id}")
            self.render_preview()
        return result

    # -- actions on a structure ---------------------------------------------
    def new_from(self) -> NewFromDialog:
        """New from…: the factory's builders in a small dialog; ``ok()`` runs ``cs new``."""
        return NewFromDialog(self)

    def create_structure(self, builder: str, **options: Any) -> Result:
        """``cs new <builder>`` with ``name``, ``system`` and ``path`` (``--from``); the new structure is selected."""
        args = {k: v for k, v in options.items() if v not in (None, "")}
        if "path" in args:
            args["from"] = args.pop("path")
        result = self.window.run("cs", action="new", target=builder, **args)
        if result.ok:
            self.refresh()
            self.select_structure(int(result.data["id"]))
            note = f"Created control structure {result.data['id']}: {result.data['name']}"
            if result.warnings:
                note += f" ({len(result.warnings)} warning{'s' if len(result.warnings) != 1 else ''})"
            self.window.set_status(note)
        return result

    def duplicate(self, name: str | None = None) -> Result:
        row = self.structure
        if row is None:
            self.window.set_status("Select a control structure to duplicate")
            return Result.failure("nothing selected", verb="cs")
        if name is None:
            if self.window.interactive:
                name = simpledialog.askstring("Duplicate", "Name of the copy:", initialvalue=f"{row['name']} (copy)",
                                              parent=self.window)
                if not name:
                    return Result.failure("cancelled", verb="cs")
            else:
                name = f"{row['name']} (copy)"
        result = self.window.run("cs", action="duplicate", target=row["id"], name=name)
        if result.ok:
            self.refresh()
            self.select_structure(int(result.data["id"]))
            self.window.set_status(f"Duplicated {row['name']} as control structure {result.data['id']}: {name}")
        return result

    def delete_structure(self) -> Result:
        row = self.structure
        if row is None:
            self.window.set_status("Select a control structure to delete")
            return Result.failure("nothing selected", verb="cs")
        counts = row.get("counts") or {}
        total = sum(counts.values())
        if not self.window.confirm("Delete", f"Delete {row['name']} and its {total} parts? This cannot be undone."):
            return Result.failure("cancelled", verb="cs")
        result = self.window.run("cs", action="delete", target=row["id"], cascade=True)
        if result.ok:
            self.structure_id = None
            self.refresh()
            self.select_structure(None)
            self.window.set_status(f"Deleted control structure {row['id']}: {row['name']} ({total} parts)")
        return result

    def import_drawio(self, path: str | Path | None = None) -> Result:
        if path is None:
            if not self.window.interactive:
                return Result.failure("no path given", verb="cs")
            path = filedialog.askopenfilename(
                parent=self.window, title="Import draw.io", filetypes=[("draw.io", "*.drawio *.xml"), ("All", "*.*")],
            )
            if not path:
                return Result.failure("cancelled", verb="cs")
        # the file keeps its own name; its slug is the next free one, so a file exported from this very
        # database (the round trip) imports beside its origin instead of being refused
        taken = {r["slug"] for r in self.structures}
        base = slugify(Path(str(path)).stem) or "imported"
        slug, n = base, 1
        while slug in taken:
            n += 1
            slug = f"{base}_{n}"
        result = self.window.run("cs", action="import", target=str(path), slug=slug)
        if result.ok:
            self.refresh()
            self.select_structure(int(result.data["id"]))
            note = f"Imported {Path(str(path)).name} as control structure {result.data['id']}: {result.data['name']}"
            if result.warnings:
                note += f" ({len(result.warnings)} warning{'s' if len(result.warnings) != 1 else ''})"
            self.window.set_status(note)
        return result

    def validate(self) -> Result:
        row = self.structure
        if row is None:
            self.window.set_status("Select a control structure to validate")
            return Result.failure("nothing selected", verb="cs")
        result = self.brain.execute("cs", action="validate", target=row["id"], actor="gui")
        self.validation.delete(0, "end")
        if result.data is None:
            self.window.report(result, "cs validate")
            return result
        report = result.data
        self.last_validation = report
        for error in report.get("errors", []):
            self.validation.insert("end", f"error: {error}")
        for warning in report.get("warnings", []):
            self.validation.insert("end", f"warning: {warning}")
        for note in report.get("info", []):
            self.validation.insert("end", f"info: {note}")
        if not self.validation.size():
            self.validation.insert("end", "No errors, no warnings.")
        errors, warnings, info = report.get("errors", []), report.get("warnings", []), report.get("info", [])
        head = "Valid" if report.get("ok") else "Invalid"
        summary = (f"{head}: {len(errors)} error{'s' if len(errors) != 1 else ''}, "
                   f"{len(warnings)} warning{'s' if len(warnings) != 1 else ''}, {len(info)} info")
        detail = "; ".join([*errors, *warnings])
        self.window.set_status(f"{summary}" + (f" — {detail}" if detail else ""))
        return result

    # -- export -----------------------------------------------------------------
    def export(self) -> ExportDialog | None:
        """Export…: the dialog; its Export button runs ``export_structure``."""
        if self.structure is None:
            self.window.set_status("Select a control structure to export")
            return None
        return ExportDialog(self)

    def default_export_dir(self) -> str:
        """The last folder exported into (the preferences), else ``control_structures/`` under the out folder."""
        remembered = read_prefs().get(PREF_EXPORT_DIR)
        if isinstance(remembered, str) and remembered.strip():
            return remembered
        return str(Path(self.brain.out_dir) / EXPORT_DIR)

    def export_structure(self, out_dir: str | Path, formats: tuple[str, ...] | list[str], *, ocr: bool = True,
                         on_done: Any = None) -> BackgroundFetch:
        """``cs export`` on a worker thread: the dialog's work and an agent's verb are the same. The
        folder is remembered in the preferences; ``on_done(result)`` runs on the Tk thread after the
        status bar has named every file and the OCR verdict."""
        row = self.structure
        if row is None:
            raise ValueError("no control structure selected")
        write_prefs(**{PREF_EXPORT_DIR: str(out_dir)})
        fetch = BackgroundFetch(
            self.window, "cs", action="export", target=row["id"], out=str(out_dir), format=list(formats),
            no_ocr=not ocr,
        ).start()
        self.window.set_status(f"Exporting {row['name']} to {out_dir}…")

        def poll() -> None:
            if not fetch.done:
                self.poll_later(poll)
                return
            result = fetch.result
            self.last_export = result
            self.window.report(result, "cs export")
            if result.ok:
                data = result.data
                files = ", ".join(data.get("files", []))
                self.window.set_status(f"Exported {row['name']}: {files} (OCR: {data.get('ocr_verdict')})")
            if on_done is not None:
                on_done(result)

        self.poll_later(poll)
        return fetch

    # -- the preview --------------------------------------------------------------
    def _clear_preview(self, text: str) -> None:
        self._photo = None
        self.preview.configure(image="", text="")
        self.preview_path = None
        self.last_preview = None
        self.verdict_var.set(text)
        self.vscode_button.configure(state="disabled")

    def render_preview(self) -> BackgroundFetch | None:
        """Render the selected structure to ``figures/<slug>.png`` (and ``.drawio``) off the Tk thread
        and show it; a render asked for while one runs follows it."""
        row = self.structure
        if row is None:
            self._clear_preview("No structure selected.")
            return None
        if self.preview_fetch is not None and not self.preview_fetch.done:
            self._preview_pending = True
            return self.preview_fetch
        self._preview_pending = False
        diagram = self.brain.factory.to_diagram(row)  # the rows are read here, on the Tk thread
        out = self.brain.factory.preview_dir()
        self.verdict_var.set("Rendering…")
        fetch = BackgroundFetch.call(
            self.window, "preview", self.brain.factory.build_files, diagram, out, row["slug"], PREVIEW_FORMATS,
            ocr=True,
        ).start()
        self.preview_fetch = fetch
        self.poll_later(lambda: self._poll_preview(fetch, row))
        return fetch

    def _poll_preview(self, fetch: BackgroundFetch, row: dict[str, Any]) -> None:
        if not fetch.done:
            self.poll_later(lambda: self._poll_preview(fetch, row))
            return
        result = fetch.result
        if self.preview_fetch is fetch:
            if not result.ok:
                self._clear_preview("Preview failed: " + "; ".join(result.errors))
            else:
                self.last_preview = result.data
                self.preview_path = result.data.get("paths", {}).get("png")
                self._show_picture()
                issues = len(result.data.get("layout_issues") or [])
                self.verdict_var.set(
                    f"{row['name']} · OCR: {result.data.get('ocr_verdict')} · "
                    f"{issues} layout issue{'s' if issues != 1 else ''} · {Path(self.preview_path or '').name}"
                )
                drawio = result.data.get("paths", {}).get("drawio")
                self.vscode_button.configure(state="normal" if (drawio and self.code_path) else "disabled")
        if self._preview_pending and self.structure is not None:
            self.render_preview()

    def _show_picture(self) -> None:
        if not self.preview_path or not Path(self.preview_path).is_file():
            return
        width, height = self.preview.winfo_width(), self.preview.winfo_height()
        if width < 50 or height < 50:  # not mapped yet (a withdrawn window): a sensible box
            width, height = 480, 360
        try:
            self._photo, _size = _load_photo(self.preview_path, (width - 8, height - 8))
        except (OSError, tk.TclError) as exc:
            self.preview.configure(image="", text=f"(picture not readable: {exc})")
            return
        self.preview.configure(image=self._photo, text="")

    def _on_preview_resize(self, _event: tk.Event) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(150, self._refit)

    def _refit(self) -> None:
        self._preview_job = None
        if self.preview_path:
            self._show_picture()

    def open_in_vscode(self, path: str | None = None) -> str | None:
        """``code <file>`` on the preview's (or ``path``'s) ``.drawio``; the status bar names it either way."""
        path = path or ((self.last_preview or {}).get("paths") or {}).get("drawio")
        if not path:
            self.window.set_status("No .drawio file to open: render or export first")
            return None
        if self.code_path and self.window.interactive:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen([self.code_path, path], shell=False, creationflags=flags)
        self.window.set_status(f"Open in VS Code: code {path}")
        return path


# -- dialogs ---------------------------------------------------------------------------------------
class NewFromDialog(tk.Toplevel):
    """New from…: the factory's builders, their availability and the options each takes."""

    def __init__(self, screen: ControlStructureScreen) -> None:
        super().__init__(screen.window)
        self.screen = screen
        self.window = screen.window
        self.result: Result | None = None
        self.title("New control structure from…")
        self.resizable(False, False)
        catalog = screen.brain.execute("cs", action="builders", actor="gui")
        self.builders: list[dict[str, Any]] = list((catalog.data or {}).get("builders", [])) if catalog.ok else []
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Builder").grid(row=0, column=0, sticky="w", pady=3)
        self.builder_var = tk.StringVar(value=self.builders[0]["name"] if self.builders else "")
        self.builder_box = ttk.Combobox(
            body, textvariable=self.builder_var, values=[b["name"] for b in self.builders], state="readonly", width=40,
        )
        self.builder_box.grid(row=0, column=1, columnspan=2, sticky="ew", pady=3)
        self.builder_box.bind("<<ComboboxSelected>>", lambda e: self._on_builder())
        self.description_var = tk.StringVar()
        ttk.Label(body, textvariable=self.description_var, wraplength=420, justify="left", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        ttk.Label(body, text="Name").grid(row=2, column=0, sticky="w", pady=3)
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(body, textvariable=self.name_var, width=44)
        self.name_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=3)
        ttk.Label(body, text="System").grid(row=3, column=0, sticky="w", pady=3)
        self.system_var = tk.StringVar()
        ttk.Entry(body, textvariable=self.system_var, width=44).grid(row=3, column=1, columnspan=2, sticky="ew", pady=3)
        self.path_label = ttk.Label(body, text="File")
        self.path_label.grid(row=4, column=0, sticky="w", pady=3)
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(body, textvariable=self.path_var, width=36)
        self.path_entry.grid(row=4, column=1, sticky="ew", pady=3)
        self.browse_button = ttk.Button(body, text="Browse…", command=self.browse)
        self.browse_button.grid(row=4, column=2, padx=(4, 0))
        self.source_label = ttk.Label(body, text="Source structure")
        self.source_label.grid(row=5, column=0, sticky="w", pady=3)
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(
            body, textvariable=self.source_var, values=[r["slug"] for r in screen.structures], state="readonly",
        )
        self.source_box.grid(row=5, column=1, columnspan=2, sticky="ew", pady=3)
        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e", pady=(10, 0))
        self.ok_button = ttk.Button(buttons, text="Create", command=self.ok)
        self.ok_button.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="left")
        self._on_builder()
        if self.window.interactive:
            self.transient(self.window)
            self.grab_set()
            self.name_entry.focus_set()
        else:
            self.withdraw()

    @property
    def builder(self) -> dict[str, Any] | None:
        return next((b for b in self.builders if b["name"] == self.builder_var.get()), None)

    def _on_builder(self) -> None:
        spec = self.builder
        if spec is None:
            self.description_var.set("No builder.")
            return
        text = spec["description"]
        if not spec["available"]:
            text += f"\nUnavailable: {spec.get('reason')}"
        self.description_var.set(text)
        takes_path = "path" in spec["options"] and spec["name"] != "clone"
        clone = spec["name"] == "clone"
        self.path_label.configure(text="Folder" if spec["name"] == "from_datasets" else "File")
        for widget in (self.path_entry, self.browse_button):
            widget.configure(state="normal" if takes_path else "disabled")
        self.source_box.configure(state="readonly" if clone else "disabled")
        self.ok_button.configure(state="normal" if spec["available"] else "disabled")

    def browse(self) -> None:
        spec = self.builder or {}
        if spec.get("name") == "from_datasets":
            path = filedialog.askdirectory(parent=self, title="Datasets folder")
        else:
            path = filedialog.askopenfilename(parent=self, title="draw.io file",
                                              filetypes=[("draw.io", "*.drawio *.xml"), ("All", "*.*")])
        if path:
            self.path_var.set(path)

    def ok(self) -> Result:
        spec = self.builder
        if spec is None:
            self.result = Result.failure("choose a builder", verb="cs")
            self.window.set_status("Choose a builder")
            return self.result
        options: dict[str, Any] = {"name": self.name_var.get().strip(), "system": self.system_var.get().strip()}
        if spec["name"] == "clone":
            options["path"] = self.source_var.get().strip()
        elif "path" in spec["options"]:
            options["path"] = self.path_var.get().strip()
        self.result = self.screen.create_structure(spec["name"], **options)
        if self.result.ok:
            self.destroy()
        return self.result

    def cancel(self) -> None:
        self.result = Result.failure("cancelled", verb="cs")
        self.destroy()


class ExportDialog(tk.Toplevel):
    """Export…: the destination folder (remembered), the three formats with Select all / Select none,
    ``drawio`` and ``png`` checked by default, the OCR gate on by default, a preview of the file names,
    Export. The work is ``cs export`` on a worker thread; the result names every file in the status
    bar and here, with Open in VS Code on the ``.drawio`` when ``code`` is on the PATH."""

    def __init__(self, screen: ControlStructureScreen) -> None:
        super().__init__(screen.window)
        self.screen = screen
        self.window = screen.window
        self.structure = dict(screen.structure or {})
        self.result: Result | None = None
        self.fetch: BackgroundFetch | None = None
        self.title(f"Export {self.structure.get('name', '')}")
        self.resizable(False, False)
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="Folder").grid(row=0, column=0, sticky="w", pady=3)
        self.folder_var = tk.StringVar(value=screen.default_export_dir())
        self.folder_var.trace_add("write", lambda *_: self._preview_names())
        ttk.Entry(body, textvariable=self.folder_var, width=52).grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Button(body, text="Browse…", command=self.browse).grid(row=0, column=2, padx=(4, 0))

        formats = ttk.LabelFrame(body, text="Formats")
        formats.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        self.format_vars: dict[str, tk.BooleanVar] = {}
        self.checks: dict[str, ttk.Checkbutton] = {}
        for column, fmt in enumerate(FORMATS):
            var = tk.BooleanVar(value=fmt in DEFAULT_FORMATS)
            var.trace_add("write", lambda *_: self._preview_names())
            self.format_vars[fmt] = var
            check = ttk.Checkbutton(formats, text=fmt, variable=var)
            check.grid(row=0, column=column, sticky="w", padx=8, pady=4)
            self.checks[fmt] = check
        ttk.Button(formats, text="Select all", command=self.select_all).grid(row=0, column=3, padx=(16, 4), pady=4)
        ttk.Button(formats, text="Select none", command=self.select_none).grid(row=0, column=4, padx=4, pady=4)
        self.ocr_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(formats, text="OCR gate on the PNG (reads the picture back; a few seconds)",
                        variable=self.ocr_var).grid(row=1, column=0, columnspan=5, sticky="w", padx=8, pady=(0, 4))

        ttk.Label(body, text="Files").grid(row=2, column=0, sticky="nw", pady=3)
        self.preview_var = tk.StringVar()
        ttk.Label(body, textvariable=self.preview_var, justify="left", wraplength=440, style="Muted.TLabel").grid(
            row=2, column=1, columnspan=2, sticky="w", pady=3
        )
        self.status_var = tk.StringVar()
        ttk.Label(body, textvariable=self.status_var, justify="left", wraplength=440).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )
        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(10, 0))
        self.export_button = ttk.Button(buttons, text="Export", command=self.export)
        self.export_button.pack(side="left", padx=(0, 6))
        self.vscode_button = ttk.Button(buttons, text="Open in VS Code", command=self.open_in_vscode, state="disabled")
        self.vscode_button.pack(side="left", padx=(0, 6))
        self.close_button = ttk.Button(buttons, text="Close", command=self.close)
        self.close_button.pack(side="left")
        self._preview_names()
        self.protocol("WM_DELETE_WINDOW", self.close)
        if self.window.interactive:
            self.transient(self.window)
            self.grab_set()
        else:
            self.withdraw()

    # -- the choices ---------------------------------------------------------
    def formats(self) -> tuple[str, ...]:
        return tuple(fmt for fmt in FORMATS if self.format_vars[fmt].get())

    def select_all(self) -> None:
        for var in self.format_vars.values():
            var.set(True)

    def select_none(self) -> None:
        for var in self.format_vars.values():
            var.set(False)

    def file_names(self) -> list[str]:
        slug = self.structure.get("slug") or "structure"
        folder = Path(self.folder_var.get().strip() or ".")
        return [str(folder / f"{slug}.{fmt}") for fmt in self.formats()]

    def _preview_names(self) -> None:
        names = self.file_names()
        self.preview_var.set("\n".join(names) if names else "(no format selected)")

    def browse(self) -> None:
        path = filedialog.askdirectory(parent=self, initialdir=self.folder_var.get() or None, title="Export folder")
        if path:
            self.folder_var.set(path)

    # -- the work ------------------------------------------------------------
    def export(self) -> BackgroundFetch | None:
        formats = self.formats()
        if not formats:
            self.status_var.set("Select at least one format.")
            self.window.set_status("Select at least one format")
            return None
        folder = self.folder_var.get().strip()
        if not folder:
            self.status_var.set("Name the destination folder.")
            return None
        self.export_button.configure(state="disabled")
        self.status_var.set("Exporting…")
        self.fetch = self.screen.export_structure(folder, formats, ocr=bool(self.ocr_var.get()), on_done=self._done)
        return self.fetch

    def _done(self, result: Result) -> None:
        self.result = result
        if not self.winfo_exists():
            return
        self.export_button.configure(state="normal")
        if result.ok:
            data = result.data or {}
            lines = [f"Written: {f}" for f in data.get("files", [])]
            lines.append(f"OCR: {data.get('ocr_verdict')}")
            issues = data.get("layout_issues") or []
            if issues:
                lines.append(f"{len(issues)} layout issue{'s' if len(issues) != 1 else ''}")
            self.status_var.set("\n".join(lines))
            drawio = (data.get("paths") or {}).get("drawio")
            self.vscode_button.configure(state="normal" if (drawio and self.screen.code_path) else "disabled")
        else:
            self.status_var.set("Failed: " + "; ".join(result.errors))

    def open_in_vscode(self) -> str | None:
        drawio = ((self.result.data if self.result and self.result.ok else {}) or {}).get("paths", {}).get("drawio")
        return self.screen.open_in_vscode(drawio) if drawio else None

    def close(self) -> None:
        self.destroy()


__all__ = ["ControlStructureScreen", "ExportDialog", "NewFromDialog", "PREF_EXPORT_DIR", "stack"]
