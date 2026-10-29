"""StpaScreen: the STPA analyses read from Confluence, their parts, and the verbs behind every button (0.24.0).

The screen is a client of the command path like every other one: New from… runs ``stpa new``,
Validate ``stpa validate``, Export… ``stpa export``, Delete ``stpa delete --cascade``, and **Refresh
from Confluence** runs ``stpa refresh`` (the report) on a worker thread (``BackgroundFetch``), never on
the Tk thread, because it reads Confluence through asi_hopper; the report is shown first and ``--apply``
runs on the Tk thread through ``window.run`` once confirmed. The parts (losses, hazards, UCAs, scenarios,
constraints) are read-only tables here; the generic ``create`` / ``update`` / ``delete`` verbs edit
them. No table shows ``id``, ``order`` or ``uid`` (docs/hidden-identity-plan.md, 3.3).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from ..commands import Result
from ..schema.lists import list_of
from ..services.stpa_service import DATASET_KEYS, PART_ENTITIES
from .background import POLL_MS, BackgroundFetch
from .screens import Screen, fit_columns

ANALYSIS_COLUMNS = ("name", "system", "status", "source", "version", "hazards", "ucas", "scenarios", "constraints")
PART_COLUMNS = {
    "stpa_loss": ("code", "text", "cite"),
    "stpa_hazard": ("code", "parent", "text", "losses", "retired", "cite"),
    "stpa_uca": (
        "code",
        "controller",
        "control_action",
        "category",
        "text",
        "hazards",
        "retired",
        "duplicate_of",
        "cs_controller",
        "cs_signal",
        "cite",
    ),
    "stpa_constraint": ("code", "text", "cite"),
    "stpa_scenario": (
        "row",
        "uca",
        "counterpart",
        "types",
        "causal_factors",
        "beliefs",
        "constraints",
        "retired",
        "cite",
    ),
}
TAB_TITLES = {
    "stpa_loss": "Losses",
    "stpa_hazard": "Hazards",
    "stpa_uca": "UCAs",
    "stpa_constraint": "Constraints",
    "stpa_scenario": "Scenarios",
}
TRUNCATE = 90


def cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "✓" if value else ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    elif isinstance(value, str) and value.startswith("["):  # a JSON list a row still carries as text
        value = ", ".join(str(v) for v in list_of(value))
    text = str(value).replace("\n", " ")
    return text if len(text) <= TRUNCATE else text[: TRUNCATE - 1] + "…"


class StpaScreen(Screen):
    def build(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.selected: str | None = None  # the selected analysis's slug
        self.last_report: dict[str, Any] | None = None
        self.last_result: Result | None = None
        self._fetch: BackgroundFetch | None = None  # the refresh in flight, on its worker thread
        self._job: str | None = None  # the after() id while a refresh runs
        self._refresh_from: str | None = None

        maker = ttk.LabelFrame(self, text="New analysis")
        maker.pack(fill="x", pady=(0, 6))
        ttk.Label(maker, text="From").grid(row=0, column=0, sticky="w", padx=(6, 4), pady=4)
        self.builder_var = tk.StringVar()
        self.builder_box = ttk.Combobox(maker, textvariable=self.builder_var, state="readonly", width=18)
        self.builder_box.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(maker, text="Name").grid(row=0, column=2, sticky="w", padx=(12, 4))
        self.name_var = tk.StringVar()
        ttk.Entry(maker, textvariable=self.name_var, width=28).grid(row=0, column=3, sticky="ew")
        ttk.Label(maker, text="Bundle folder / page id / analysis").grid(row=0, column=4, sticky="w", padx=(12, 4))
        self.from_var = tk.StringVar()
        ttk.Entry(maker, textvariable=self.from_var, width=40).grid(row=0, column=5, sticky="ew")
        ttk.Button(maker, text="Browse…", command=self._browse_bundle).grid(row=0, column=6, padx=4)
        ttk.Button(maker, text="Create", command=self.create).grid(row=0, column=7, padx=(4, 6))
        maker.columnconfigure(5, weight=1)

        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 6))
        self.refresh_button = ttk.Button(toolbar, text="Refresh from Confluence", command=self.start_refresh)
        self.refresh_button.pack(side="left", padx=2)
        for text, command in (
            ("Validate", self.validate),
            ("Link structure…", self.link_structure),
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
        self.tree = ttk.Treeview(top, columns=ANALYSIS_COLUMNS, show="headings", selectmode="browse", height=6)
        for column in ANALYSIS_COLUMNS:
            self.tree.heading(column, text=column.replace("_", " "))
            self.tree.column(column, width=120, minwidth=40, stretch=False)
        bar = ttk.Scrollbar(top, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(top, weight=2)

        self.tabs = ttk.Notebook(paned)
        self.part_trees: dict[str, ttk.Treeview] = {}
        for entity in PART_ENTITIES:
            frame = ttk.Frame(self.tabs)
            columns = PART_COLUMNS[entity]
            tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
            for column in columns:
                tree.heading(column, text=column.replace("_", " "))
                tree.column(column, width=120, minwidth=40, stretch=False)
            ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            tree.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            self.tabs.add(frame, text=TAB_TITLES[entity])
            self.part_trees[entity] = tree
        report = ttk.Frame(self.tabs)
        self.log = tk.Text(report, height=8, wrap="word", state="disabled")
        log_bar = ttk.Scrollbar(report, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_bar.pack(side="right", fill="y")
        self.tabs.add(report, text="Report")
        paned.add(self.tabs, weight=3)

    def destroy(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        super().destroy()

    # -- data -----------------------------------------------------------
    def refresh(self) -> None:
        builders = self.brain.execute("stpa", action="builders", actor="gui")
        names = [b["name"] for b in (builders.data or {}).get("builders", [])] if builders.ok else []
        self.builder_box["values"] = names
        if names and self.builder_var.get() not in names:
            self.builder_var.set("from_bundle" if "from_bundle" in names else names[0])
        listed = self.brain.execute("stpa", action="list", actor="gui")
        self.rows = list(listed.data or []) if listed.ok else []
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            counts = row.get("counts") or {}
            self.tree.insert(
                "",
                "end",
                iid=row["slug"],
                values=[
                    cell(row.get("name")),
                    cell(row.get("system")),
                    cell(row.get("status")),
                    cell(row.get("source_kind")),
                    cell(row.get("source_version")),
                    counts.get("hazards", 0),
                    counts.get("ucas", 0),
                    counts.get("scenarios", 0),
                    counts.get("constraints", 0),
                ],
            )
        self.window.theme.stripe(self.tree)
        fit_columns(self.tree)
        self.count_var.set(f"{len(self.rows)} analyses")
        if self.selected and self.tree.exists(self.selected):
            self.tree.selection_set(self.selected)
        else:
            self.selected = None
            for tree in self.part_trees.values():
                tree.delete(*tree.get_children())
        if self.selected:
            self._fill_parts(self.selected)

    def select(self, slug: str) -> None:
        if not self.tree.exists(slug):
            raise KeyError(f"no analysis {slug!r} listed")
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
            if changed:  # a re-selection after a reload keeps the status line a verb just wrote
                self.window.set_status(f"STPA analysis {self.selected} selected")

    def _fill_parts(self, slug: str) -> None:
        got = self.brain.execute("stpa", action="get", target=slug, actor="gui")
        parts = (got.data or {}).get("parts", {}) if got.ok else {}
        for entity, tree in self.part_trees.items():
            tree.delete(*tree.get_children())
            columns = PART_COLUMNS[entity]
            for row in parts.get(DATASET_KEYS[entity], []):
                tree.insert("", "end", iid=str(row["id"]), values=[cell(row.get(c)) for c in columns])
            self.window.theme.stripe(tree)
            fit_columns(tree)

    def _require_selection(self, what: str) -> str | None:
        if not self.selected:
            self.window.set_status(f"{what}: select an analysis first")
            return None
        return self.selected

    # -- the log --------------------------------------------------------
    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.tabs.select(len(PART_ENTITIES))  # the Report tab

    def _log_result(self, title: str, result: Result) -> None:
        self._log(f"[{'ok' if result.ok else 'failed'}] {title}")
        for error in result.errors:
            self._log(f"  error: {error}")
        for warning in result.warnings:
            self._log(f"  warning: {warning}")

    # -- the verbs behind the buttons -------------------------------------
    def _browse_bundle(self) -> None:
        if not self.window.interactive:
            return
        folder = filedialog.askdirectory(parent=self, title="A Hopper evidence bundle folder")
        if folder:
            self.from_var.set(folder)

    def create(self) -> Result:
        builder = self.builder_var.get().strip()
        if not builder:
            result = Result.failure("pick a builder")
            self.window.notify_error("stpa new failed", result.errors[0])
            return result
        args: dict[str, Any] = {"action": "new", "target": builder}
        if self.name_var.get().strip():
            args["name"] = self.name_var.get().strip()
        source = self.from_var.get().strip()
        if source:
            args["page" if builder == "from_confluence" else "from"] = source
        result = self.window.run("stpa", **args)
        self.last_result = result
        self._log_result(f"stpa new {builder}", result)
        if result.ok:
            self.selected = result.data["slug"]
            counts = result.data.get("counts") or {}
            self.window.set_status(
                f"Analysis {result.data['name']} created: " + ", ".join(f"{v} {k}" for k, v in counts.items())
            )
            self.refresh()
        return result

    def validate(self) -> Result | None:
        slug = self._require_selection("Validate")
        if slug is None:
            return None
        result = self.window.run("stpa", action="validate", target=slug)
        self.last_result = result
        self._log_result(f"stpa validate {slug}", result)
        if result.ok and not result.warnings:
            self.window.set_status(f"{slug}: every rule holds")
        return result

    def link_structure(self, structure: str | None = None, apply: bool = False) -> Result | None:
        slug = self._require_selection("Link structure")
        if slug is None:
            return None
        if structure is None:
            structure = self.from_var.get().strip() or None
        if not structure and not next((r for r in self.rows if r["slug"] == slug), {}).get("control_structure"):
            self.window.set_status("Link structure: type the control structure's slug in the From box")
            return None
        result = self.window.run("stpa", action="link", target=slug, structure=structure, apply=apply)
        self.last_result = result
        self._log_result(f"stpa link {slug} --structure {structure or '(the one the analysis names)'}", result)
        if result.ok:
            for u in result.data["ucas"]:
                self._log(f"  {u['code']}: {u['status']} -> {u['cs_controller'] or '-'} / {u['cs_signal'] or '-'}")
            if (
                not apply
                and result.data["exact"]
                and self.window.confirm("Link structure", f"Write the {result.data['exact']} exact match(es)?")
            ):
                return self.link_structure(structure, apply=True)
            self.refresh()
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
        result = self.window.run("stpa", **args)
        self.last_result = result
        self._log_result(f"stpa export {slug}", result)
        if result.ok:
            for path in result.data["files"]:
                self._log(f"  wrote {path}")
            self.window.set_status(f"Exported {slug}: {len(result.data['files'])} file(s) in {result.data['out']}")
        return result

    def delete(self) -> Result | None:
        slug = self._require_selection("Delete")
        if slug is None:
            return None
        if not self.window.confirm("Delete analysis", f"Delete {slug} and every part of it?"):
            return None
        result = self.window.run("stpa", action="delete", target=slug, cascade=True)
        self.last_result = result
        self._log_result(f"stpa delete {slug} --cascade", result)
        if result.ok:
            self.selected = None
            self.refresh()
        return result

    # -- refresh from Confluence, off the Tk thread ------------------------
    def start_refresh(self, path: str | None = None) -> bool:
        """Run ``stpa refresh <slug> [--from <bundle>]`` (the report, nothing written) on a worker thread
        (``BackgroundFetch``, ``window.execute_quiet``); ``_poll`` picks the Result up on the Tk thread and
        shows it. Returns whether a run started."""
        slug = self._require_selection("Refresh from Confluence")
        if slug is None or self._job is not None:
            return False
        self._refresh_from = path
        self.refresh_button.configure(state="disabled")
        self.window.set_status(f"Refreshing {slug} from Confluence…")
        args: dict[str, Any] = {"action": "refresh", "target": slug}
        if path:
            args["from"] = path
        self._fetch = BackgroundFetch(self.window, "stpa", **args).start()
        self._job = self.after(POLL_MS, self._poll)
        return True

    @property
    def refreshing(self) -> bool:
        return self._job is not None

    def _poll(self) -> None:
        fetch = self._fetch
        if fetch is None or not fetch.done:
            self._job = self.after(POLL_MS, self._poll)
            return
        self._job = None
        self._fetch = None
        self.refresh_button.configure(state="normal")
        self._finish_refresh(fetch.result)

    def _finish_refresh(self, result: Result) -> None:
        self.last_result = result
        slug = self.selected or "?"
        self._log_result(f"stpa refresh {slug}", result)
        if not result.ok:
            self.window.notify_error("stpa refresh failed", "; ".join(result.errors) or "unknown error")
            return
        report = result.data
        self.last_report = report
        source = report.get("source") or {}
        self._log(f"  page {source.get('source_page_id')} v{source.get('source_version')}")
        if report.get("same"):
            self._log("  no changes: the page says what the rows say")
            self.window.set_status(f"{slug}: the page is unchanged")
            return
        for bucket in ("new", "changed", "retired", "removed"):
            for key, items in (report.get(bucket) or {}).items():
                names = [i["key"] if isinstance(i, dict) else str(i) for i in items]
                self._log(f"  {bucket} {key}: {', '.join(names)}")
                for item in items:
                    if isinstance(item, dict):
                        for field, diff in item["fields"].items():
                            self._log(f"    {item['key']} {field}: {diff['before']!r} -> {diff['after']!r}")
        self.window.set_status(f"{slug}: the page changed; the report is in the Report tab")
        if self.window.confirm("Apply the refresh", f"Apply the changes read from the page to {slug}?"):
            self.apply_refresh()

    def apply_refresh(self) -> Result | None:
        slug = self._require_selection("Apply refresh")
        if slug is None:
            return None
        args: dict[str, Any] = {"action": "refresh", "target": slug, "apply": True}
        if self._refresh_from:
            args["from"] = self._refresh_from
        result = self.window.run("stpa", **args)
        self.last_result = result
        self._log_result(f"stpa refresh {slug} --apply", result)
        if result.ok:
            touched = result.data.get("touched") or {}
            self.window.set_status(f"{slug} refreshed: " + ", ".join(f"{v} {k}" for k, v in touched.items() if v))
            self.refresh()
        return result
