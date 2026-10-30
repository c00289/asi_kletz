"""HaraScreen: the HARAs, their parts, the derived Summary and the verbs behind every button (0.28.0).

The screen is a client of the command path like every other one: New from workbook… runs ``hara new
from_workbook``, Recompute ``hara recompute``, Check ``hara check``, Validate ``hara validate``, Export…
``hara export``, Delete ``hara delete --cascade``. The parts are read-only tables here (the generic
``create`` / ``update`` / ``delete`` verbs edit them); the Summary tab is ``hara summary``, computed, never
stored. No table shows ``id``, ``order`` or ``uid`` (docs/hidden-identity-plan.md, 3.3).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from ..commands import Result
from ..schema.definitions import HARA_CONTEXTS
from ..services.hara_service import DATASET_KEYS, PART_ENTITIES
from .screens import Screen, fit_columns
from .stpa_screen import cell

HARA_COLUMNS = (
    "name",
    "system",
    "vehicle_code",
    "status",
    "analysis",
    "functions",
    "ratings",
    "assessments",
    "hazards",
)
SUMMARY_COLUMNS = (
    "hazard",
    "text",
    "safety_goal",
    *HARA_CONTEXTS,
    "mplr",
    "plr",
    "agplr",
    "sil",
    "typed_mplr",
    "agrees",
)
PART_COLUMNS = {
    "hara_vehicle": ("letter", "iso_vehicle", "asi_vehicle", "projects"),
    "hara_function": ("name", "kind", "vehicles", "cumulative_mplr", "specific_mplr", "definition"),
    "hara_use_case": ("name", "base", "vehicles", "definition"),
    "hara_failure_mode": ("name",),
    "hara_assumption": ("source", "vehicle", "text"),
    "hara_rating": ("function", "use_case", "failure_mode", "ratings", "cumulative", "comment"),
    "hara_assessment": (
        "context",
        "hazard",
        "scenario",
        "event",
        "function",
        "use_case",
        "failure_mode",
        "mplr",
        "stated_mplr",
        "cumulative_mplr",
        "safety_goal",
        "sg_mplr",
        "comment",
    ),
    "hara_approval": ("event", "role", "decision", "comment"),
}
TAB_TITLES = {
    "hara_vehicle": "Vehicles",
    "hara_function": "Functions",
    "hara_use_case": "Use cases",
    "hara_failure_mode": "Failure modes",
    "hara_assumption": "Assumptions",
    "hara_rating": "Ratings",
    "hara_assessment": "Assessments",
    "hara_approval": "Approvals",
}
SUMMARY_TAB = "Summary"
REPORT_TAB = "Report"
DIFFER_TAG = "differ"


class HaraScreen(Screen):
    def build(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.selected: str | None = None  # the selected HARA's slug
        self.last_result: Result | None = None
        self.last_summary: dict[str, Any] | None = None

        maker = ttk.LabelFrame(self, text="New HARA")
        maker.pack(fill="x", pady=(0, 6))
        ttk.Label(maker, text="From").grid(row=0, column=0, sticky="w", padx=(6, 4), pady=4)
        self.builder_var = tk.StringVar()
        self.builder_box = ttk.Combobox(maker, textvariable=self.builder_var, state="readonly", width=16)
        self.builder_box.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(maker, text="Name").grid(row=0, column=2, sticky="w", padx=(12, 4))
        self.name_var = tk.StringVar()
        ttk.Entry(maker, textvariable=self.name_var, width=24).grid(row=0, column=3, sticky="ew")
        ttk.Label(maker, text="Workbook / HARA").grid(row=0, column=4, sticky="w", padx=(12, 4))
        self.from_var = tk.StringVar()
        ttk.Entry(maker, textvariable=self.from_var, width=40).grid(row=0, column=5, sticky="ew")
        ttk.Button(maker, text="Browse…", command=self._browse).grid(row=0, column=6, padx=4)
        ttk.Label(maker, text="Vehicle").grid(row=0, column=7, sticky="w", padx=(12, 4))
        self.vehicle_var = tk.StringVar()
        ttk.Entry(maker, textvariable=self.vehicle_var, width=6).grid(row=0, column=8, sticky="w")
        ttk.Button(maker, text="Create", command=self.create).grid(row=0, column=9, padx=(4, 6))
        maker.columnconfigure(5, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        for text, command in (
            ("Recompute MPLr", self.recompute),
            ("Check", self.check),
            ("Validate", self.validate),
            ("Export…", self.export),
            ("Delete", self.delete),
            ("Reload", self.refresh),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)
        self.count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.count_var, style="Muted.TLabel").pack(side="right")

        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True)
        top = ttk.Frame(paned)
        self.tree = ttk.Treeview(top, columns=HARA_COLUMNS, show="headings", selectmode="browse", height=4)
        for column in HARA_COLUMNS:
            self.tree.heading(column, text=column.replace("_", " "))
            self.tree.column(column, width=120, minwidth=40, stretch=False)
        bar = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(top, weight=1)

        self.tabs = ttk.Notebook(paned)
        self.summary_tree = self._table(self.tabs, SUMMARY_COLUMNS, SUMMARY_TAB)
        self.part_trees: dict[str, ttk.Treeview] = {}
        for entity in PART_ENTITIES:
            self.part_trees[entity] = self._table(self.tabs, PART_COLUMNS[entity], TAB_TITLES[entity])
        report = ttk.Frame(self.tabs)
        self.log = tk.Text(report, height=8, wrap="word", state="disabled")
        log_bar = ttk.Scrollbar(report, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_bar.pack(side="right", fill="y")
        self.tabs.add(report, text=REPORT_TAB)
        paned.add(self.tabs, weight=4)

    def _table(self, parent: ttk.Notebook, columns: tuple[str, ...], title: str) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for column in columns:
            tree.heading(column, text=column.replace("_", " "))
            tree.column(column, width=110, minwidth=40, stretch=False)
        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        parent.add(frame, text=title)
        return tree

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        builders = self.brain.execute("hara", action="builders", actor="gui")
        names = [b["name"] for b in (builders.data or {}).get("builders", [])] if builders.ok else []
        self.builder_box["values"] = names
        if names and self.builder_var.get() not in names:
            self.builder_var.set("from_workbook" if "from_workbook" in names else names[0])
        listed = self.brain.execute("hara", action="list", actor="gui")
        self.rows = list(listed.data or []) if listed.ok else []
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            counts = row.get("counts") or {}
            step1 = row.get("step1") or {}
            self.tree.insert(
                "",
                "end",
                iid=row["slug"],
                values=[
                    cell(row.get("name")),
                    cell(row.get("system")),
                    cell(row.get("vehicle_code")),
                    cell(row.get("status")),
                    cell(row.get("analysis")),
                    counts.get("functions", 0),
                    counts.get("ratings", 0),
                    counts.get("assessments", 0),
                    step1.get("hazards", 0),
                ],
            )
        self.window.theme.stripe(self.tree)
        fit_columns(self.tree)
        self.count_var.set(f"{len(self.rows)} HARAs")
        if self.selected and self.tree.exists(self.selected):
            self.tree.selection_set(self.selected)
        else:
            self.selected = None
            self.summary_tree.delete(*self.summary_tree.get_children())
            for tree in self.part_trees.values():
                tree.delete(*tree.get_children())
        if self.selected:
            self._fill_parts(self.selected)

    def select(self, slug: str) -> None:
        if not self.tree.exists(slug):
            raise KeyError(f"no HARA {slug!r} listed")
        self.tree.selection_set(slug)
        self.tree.see(slug)
        self.selected = slug
        self._fill_parts(slug)

    def _on_select(self, _event: tk.Event | None = None) -> None:
        picked = self.tree.selection()
        if picked:
            changed = self.selected != str(picked[0])
            self.selected = str(picked[0])
            self._fill_parts(self.selected)
            if changed:
                self.window.set_status(f"HARA {self.selected} selected")

    def _fill_parts(self, slug: str) -> None:
        got = self.brain.execute("hara", action="get", target=slug, actor="gui")
        parts = (got.data or {}).get("parts", {}) if got.ok else {}
        for entity, tree in self.part_trees.items():
            tree.delete(*tree.get_children())
            columns = PART_COLUMNS[entity]
            differing: list[str] = []
            for row in parts.get(DATASET_KEYS[entity], []):
                if entity == "hara_assessment" and row.get("stated_mplr") and row.get("mplr") != row.get("stated_mplr"):
                    differing.append(str(row["id"]))
                tree.insert("", "end", iid=str(row["id"]), values=[cell(row.get(c)) for c in columns])
            self._stripe_and_mark(tree, differing)
            fit_columns(tree)
        summary = self.brain.execute("hara", action="summary", target=slug, actor="gui")
        self.last_summary = summary.data if summary.ok else None
        self.summary_tree.delete(*self.summary_tree.get_children())
        differing = []
        for entry in (summary.data or {}).get("hazards", []) if summary.ok else []:
            values = [
                entry["hazard"],
                cell(entry.get("text")),
                entry.get("safety_goal") or "",
                *[entry["contexts"].get(c, "") for c in HARA_CONTEXTS],
                entry.get("mplr", ""),
                entry.get("plr", ""),
                entry.get("agplr", ""),
                entry.get("sil", ""),
                entry.get("typed_mplr", ""),
                "" if entry.get("agrees") is None else ("✓" if entry["agrees"] else "✗"),
            ]
            if entry.get("agrees") is False:
                differing.append(entry["hazard"])
            self.summary_tree.insert("", "end", iid=entry["hazard"], values=values)
        self._stripe_and_mark(self.summary_tree, differing)
        fit_columns(self.summary_tree)

    def _stripe_and_mark(self, tree: ttk.Treeview, differing: list[str]) -> None:
        """Stripe the rows, then put the differ tag in front of the stripe tag on the rows whose computed MPLr
        is not the workbook's: the first tag wins the colour (the stripe replaces every tag, so it goes first)."""
        self.window.theme.stripe(tree)
        tree.tag_configure(DIFFER_TAG, foreground=self.window.theme.palette.accent)
        for iid in differing:
            tree.item(iid, tags=(DIFFER_TAG, *tree.item(iid, "tags")))

    def _require_selection(self, what: str) -> str | None:
        if not self.selected:
            self.window.set_status(f"{what}: select a HARA first")
            return None
        return self.selected

    # -- the log --------------------------------------------------------
    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.tabs.select(len(PART_ENTITIES) + 1)  # the Report tab, after Summary and the parts

    def _log_result(self, title: str, result: Result) -> None:
        self._log(f"[{'ok' if result.ok else 'failed'}] {title}")
        for error in result.errors:
            self._log(f"  error: {error}")
        for warning in result.warnings:
            self._log(f"  warning: {warning}")

    # -- the verbs behind the buttons -------------------------------------
    def _browse(self) -> None:
        if not self.window.interactive:
            return
        path = filedialog.askopenfilename(
            parent=self, title="A HARA workbook", filetypes=[("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")]
        )
        if path:
            self.from_var.set(path)

    def create(self) -> Result:
        builder = self.builder_var.get().strip()
        if not builder:
            result = Result.failure("pick a builder")
            self.window.notify_error("hara new failed", result.errors[0])
            return result
        args: dict[str, Any] = {"action": "new", "target": builder}
        if self.name_var.get().strip():
            args["name"] = self.name_var.get().strip()
        if self.from_var.get().strip():
            args["from"] = self.from_var.get().strip()
        if self.vehicle_var.get().strip():
            args["vehicle"] = self.vehicle_var.get().strip()
        result = self.window.run("hara", **args)
        self.last_result = result
        self._log_result(f"hara new {builder}", result)
        if result.ok:
            self.selected = result.data["slug"]
            counts = result.data.get("counts") or {}
            mplr = result.data.get("mplr") or {}
            self.window.set_status(
                f"HARA {result.data['name']} created: "
                + ", ".join(f"{v} {k}" for k, v in counts.items())
                + f"; MPLr computed for {mplr.get('rows', 0)} rows under vehicle {mplr.get('vehicle_code') or '-'}"
            )
            self.refresh()
        return result

    def recompute(self) -> Result | None:
        slug = self._require_selection("Recompute MPLr")
        if slug is None:
            return None
        result = self.window.run("hara", action="recompute", target=slug)
        self.last_result = result
        self._log_result(f"hara recompute {slug}", result)
        if result.ok:
            d = result.data
            self._log(
                f"  {d['rows']} rows, {d['changed']} changed, {d['not_found']} without a rating key, "
                f"{d['empty']} empty, "
                f"vehicle {d.get('vehicle_code') or '-'}"
            )
            self.window.set_status(f"{slug}: MPLr recomputed, {d['changed']} row(s) moved")
            self._fill_parts(slug)
        return result

    def check(self) -> Result | None:
        slug = self._require_selection("Check")
        if slug is None:
            return None
        result = self.window.run("hara", action="check", target=slug)
        self.last_result = result
        self._log_result(f"hara check {slug}", result)
        if result.ok:
            for context, c in result.data["contexts"].items():
                self._log(
                    f"  {context}: {c['rows']} rows, {c['agree']} agree, {c['differ']} differ, "
                    f"{c['not_found']} without a rating key, {c['unstated']} unstated"
                )
                for x in c["examples"]:
                    self._log(
                        f"    {x['event']} · {x['function']} · {x['use_case']} · {x['failure_mode']}: "
                        f"computed {x['computed'] or '(empty)'}, stated {x['stated']}"
                    )
            s = result.data["summary"]
            self._log(f"  Summary: {s['agree']} hazards agree, {s['differ']} differ, {s['untyped']} untyped")
            for h in result.data["hazards_differing"]:
                self._log(f"    {h['hazard']}: computed {h['computed'] or '(empty)'}, typed {h['typed']}")
            for bucket, names in result.data["unknown"].items():
                if names:
                    self._log(f"  {bucket} used but not listed: {', '.join(names)}")
            self.window.set_status(f"{slug}: check in the Report tab")
        return result

    def validate(self) -> Result | None:
        slug = self._require_selection("Validate")
        if slug is None:
            return None
        result = self.window.run("hara", action="validate", target=slug)
        self.last_result = result
        self._log_result(f"hara validate {slug}", result)
        if result.ok and not result.warnings:
            self.window.set_status(f"{slug}: every rule holds")
        return result

    def export(self, folder: str | None = None) -> Result | None:
        slug = self._require_selection("Export")
        if slug is None:
            return None
        if folder is None and self.window.interactive:
            folder = filedialog.askdirectory(parent=self, title="Export folder") or None
            if folder is None:
                return None
        args: dict[str, Any] = {"action": "export", "target": slug}
        if folder:
            args["out"] = folder
        result = self.window.run("hara", **args)
        self.last_result = result
        self._log_result(f"hara export {slug}", result)
        if result.ok:
            for path in result.data["files"]:
                self._log(f"  wrote {path}")
            self.window.set_status(f"Exported {slug}: {len(result.data['files'])} file(s) in {result.data['out']}")
        return result

    def delete(self) -> Result | None:
        slug = self._require_selection("Delete")
        if slug is None:
            return None
        if not self.window.confirm("Delete HARA", f"Delete {slug} and every part of it?"):
            return None
        result = self.window.run("hara", action="delete", target=slug, cascade=True)
        self.last_result = result
        self._log_result(f"hara delete {slug} --cascade", result)
        if result.ok:
            if result.data.get("analysis_kept"):
                self._log(f"  STPA analysis {result.data['analysis_kept']} kept: its step 3 has begun")
            self.selected = None
            self.refresh()
        return result
