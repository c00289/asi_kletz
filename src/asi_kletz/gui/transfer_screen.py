"""TransferScreen: export/import the workbook, dump/load JSON, build diagrams and documents, with a result log.

Generation lives here, in a third frame, because the generated files are views of the database
like the workbook and belong with the other transfers (it was also the way to add nothing to the
screen list, which 0.5.0 made a registration, not a count). The screen only ever calls
``self.window.run("diagram", ...)`` and ``self.window.run("document", ...)``.
"""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from ..commands import Result
from ..services import LOAD_MODES
from .screens import Screen

PHASE_PARAM = "phase"
PLAN_DOCUMENT = "safety_plan"


class TransferScreen(Screen):
    def build(self) -> None:
        self.last_primary: str | None = None
        book = ttk.LabelFrame(self, text="Excel workbook (a generated view of the database)")
        book.pack(fill="x", pady=(0, 8))
        ttk.Label(book, text="Workbook").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.workbook_var = tk.StringVar(value=self.brain.workbook_path)
        ttk.Entry(book, textvariable=self.workbook_var, width=70).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(book, text="Browse…", command=self._browse_workbook).grid(row=0, column=2, padx=4)
        ttk.Label(book, text="Import mode").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.mode_var = tk.StringVar(value="replace")
        ttk.Combobox(
            book, textvariable=self.mode_var, values=list(LOAD_MODES), state="readonly", width=10
        ).grid(row=1, column=1, sticky="w")
        buttons = ttk.Frame(book)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w", padx=6, pady=(4, 6))
        ttk.Button(buttons, text="Export workbook  (Ctrl+E)", command=self.export_workbook).pack(
            side="left", padx=(0, 6)
        )
        ttk.Button(buttons, text="Import workbook", command=self.import_workbook).pack(side="left")
        book.columnconfigure(1, weight=1)

        js = ttk.LabelFrame(self, text="JSON (portable dump for diffing, versioning, and AI tools)")
        js.pack(fill="x", pady=(0, 8))
        row = ttk.Frame(js)
        row.pack(fill="x", padx=6, pady=6)
        ttk.Button(row, text="Dump JSON…", command=self.dump_json).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Load JSON…", command=self.load_json).pack(side="left", padx=(0, 12))
        ttk.Label(row, text="Load mode").pack(side="left")
        self.json_mode_var = tk.StringVar(value="merge")
        ttk.Combobox(
            row, textvariable=self.json_mode_var, values=list(LOAD_MODES), state="readonly", width=10
        ).pack(side="left", padx=4)

        self._build_generate_frame()

        log_box = ttk.LabelFrame(self, text="Log")
        log_box.pack(fill="both", expand=True)
        self.log = tk.Text(log_box, height=12, wrap="word", state="disabled")
        bar = ttk.Scrollbar(log_box, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=bar.set)
        self.log.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    def _build_generate_frame(self) -> None:
        gen = ttk.LabelFrame(self, text="Diagrams and documents (generated views of the plan)")
        gen.pack(fill="x", pady=(0, 8))
        self.diagram_specs: list[dict[str, Any]] = self._catalog("diagram", "diagrams")
        self.document_specs: list[dict[str, Any]] = self._catalog("document", "documents")

        ttk.Label(gen, text="Diagram").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.diagram_var = tk.StringVar(value=self.diagram_specs[0]["title"] if self.diagram_specs else "")
        self.diagram_combo = ttk.Combobox(
            gen, textvariable=self.diagram_var, values=[s["title"] for s in self.diagram_specs],
            state="readonly", width=28,
        )
        self.diagram_combo.grid(row=0, column=1, sticky="w", pady=4)
        self.diagram_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_phase())
        ttk.Label(gen, text="Phase").grid(row=0, column=2, sticky="w", padx=(12, 4))
        self.phase_var = tk.StringVar()
        self.phase_combo = ttk.Combobox(
            gen, textvariable=self.phase_var, values=list(self.brain.lookups.get("lifecycle_phase", ())),
            state="readonly", width=34,
        )
        self.phase_combo.grid(row=0, column=3, sticky="w")
        ttk.Button(gen, text="Build diagram", command=self.build_diagram).grid(row=0, column=4, padx=6)

        ttk.Label(gen, text="Document").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.document_var = tk.StringVar(value=self.document_specs[0]["title"] if self.document_specs else "")
        self.document_combo = ttk.Combobox(
            gen, textvariable=self.document_var, values=[s["title"] for s in self.document_specs],
            state="readonly", width=28,
        )
        self.document_combo.grid(row=1, column=1, sticky="w", pady=4)
        ttk.Button(gen, text="Build document", command=self.build_document).grid(row=1, column=4, padx=6)

        ttk.Label(gen, text="Output folder").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.out_var = tk.StringVar(value=self.brain.out_dir)
        ttk.Entry(gen, textvariable=self.out_var, width=60).grid(row=2, column=1, columnspan=3, sticky="ew", pady=4)
        ttk.Button(gen, text="Browse…", command=self._browse_out).grid(row=2, column=4, padx=6)
        actions = ttk.Frame(gen)
        actions.grid(row=3, column=0, columnspan=5, sticky="w", padx=6, pady=(4, 6))
        ttk.Button(actions, text="Open", command=self.open_primary).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Open folder", command=self.open_folder).pack(side="left")
        gen.columnconfigure(3, weight=1)
        self._sync_phase()

    # -- helpers --------------------------------------------------------
    def _catalog(self, verb: str, key: str) -> list[dict[str, Any]]:
        result = self.window.run(verb)
        return list((result.data or {}).get(key, [])) if result.ok else []

    def _append(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _report(self, result: Result) -> Result:
        if result.ok:
            data = result.data or {}
            counts = ", ".join(
                f"{k}={v if isinstance(v, int) else v.get('inserted', v)}"
                for k, v in (data.get("entities") or {}).items()
            )
            self._append(f"[ok] {result.verb} -> {data.get('path') or data.get('primary') or ''}  {counts}")
            gaps = data.get("gaps") or {}
            if any(gaps.values()):  # 0.27.0: the Safety Plan sheet's gaps, shaded pinkish red
                self._append(f"     gaps shaded pinkish red: {gaps.get('placeholder', 0)} placeholder link(s), "
                             f"{gaps.get('no_url', 0)} without a URL, {gaps.get('no_ticket', 0)} without a ticket")
            for warning in result.warnings:
                self._append(f"     warning: {warning}")
        else:
            self._append(f"[failed] {result.verb}: " + "; ".join(result.errors))
        return result

    def _browse_workbook(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".xlsx", filetypes=[("Excel workbook", "*.xlsx")],
            initialfile=Path(self.workbook_var.get()).name, title="Workbook location",
        )
        if path:
            self.workbook_var.set(path)

    def _browse_out(self) -> None:
        path = filedialog.askdirectory(parent=self, initialdir=self.out_var.get() or None, title="Output folder")
        if path:
            self.out_var.set(path)

    def _spec_for(self, specs: list[dict[str, Any]], key_or_title: str) -> dict[str, Any] | None:
        return next((s for s in specs if key_or_title in (s["key"], s["title"])), None)

    def _sync_phase(self) -> None:
        """The phase combobox is live only for a diagram that declares a ``phase`` parameter."""
        spec = self._spec_for(self.diagram_specs, self.diagram_var.get())
        wants_phase = bool(spec and any(p["name"] == PHASE_PARAM for p in spec["params"]))
        self.phase_combo.configure(state="readonly" if wants_phase else "disabled")
        if wants_phase and not self.phase_var.get() and self.phase_combo["values"]:
            self.phase_var.set(self.phase_combo["values"][0])

    def phase_enabled(self) -> bool:
        return str(self.phase_combo.cget("state")) != "disabled"

    def select_diagram(self, key: str) -> None:
        spec = self._spec_for(self.diagram_specs, key)
        if spec is None:
            raise KeyError(f"unknown diagram {key!r}")
        self.diagram_var.set(spec["title"])
        self._sync_phase()

    def select_document(self, key: str) -> None:
        spec = self._spec_for(self.document_specs, key)
        if spec is None:
            raise KeyError(f"unknown document {key!r}")
        self.document_var.set(spec["title"])

    def _remember(self, result: Result) -> Result:
        if result.ok and result.data and result.data.get("primary"):
            self.last_primary = result.data["primary"]
            self.window.set_status(f"Written: {self.last_primary}")
        return result

    def _open_path(self, path: str | Path) -> bool:
        """Open a file or folder with the desktop's default program; never in a non-interactive window."""
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

    # -- actions --------------------------------------------------------
    def export_workbook(self, path: str | Path | None = None) -> Result:
        target = str(path or self.workbook_var.get() or self.brain.workbook_path)
        result = self._report(self.window.run("export", format="excel", out=target))
        if result.ok and result.data and result.data.get("path"):
            self.workbook_var.set(result.data["path"])  # 0.27.0: the stamped file just written is the import's default
        return result

    def import_workbook(self, path: str | Path | None = None, mode: str | None = None) -> Result:
        source = str(path or self.workbook_var.get())
        mode = mode or self.mode_var.get()
        if path is None and not self.window.confirm(
            "Import workbook",
            f"Import {Path(source).name} with mode '{mode}'?\n\n'replace' wipes every table first.",
        ):
            return Result.failure("cancelled", verb="import")
        return self._report(self.window.run("import", format="excel", path=source, mode=mode))

    def dump_json(self, path: str | Path | None = None) -> Result:
        if path is None:
            if not self.window.interactive:
                return Result.failure("no path given", verb="dump")
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="kletz.json",
            )
            if not path:
                return Result.failure("cancelled", verb="dump")
        return self._report(self.window.run("dump", out=str(path)))

    def load_json(self, path: str | Path | None = None, mode: str | None = None) -> Result:
        if path is None:
            if not self.window.interactive:
                return Result.failure("no path given", verb="load")
            path = filedialog.askopenfilename(parent=self, filetypes=[("JSON", "*.json")])
            if not path:
                return Result.failure("cancelled", verb="load")
        return self._report(self.window.run("load", path=str(path), mode=mode or self.json_mode_var.get()))

    def build_diagram(self, key: str | None = None, phase: str | None = None, out: str | Path | None = None) -> Result:
        if key is not None:
            self.select_diagram(key)
        spec = self._spec_for(self.diagram_specs, self.diagram_var.get())
        if spec is None:
            return self._report(Result.failure("no diagram selected", verb="diagram"))
        args: dict[str, Any] = {"name": spec["key"], "out": str(out or self.out_var.get() or self.brain.out_dir)}
        if self.phase_enabled():
            value = phase or self.phase_var.get()
            if value:
                args["param"] = {PHASE_PARAM: value}
        return self._remember(self._report(self.window.run("diagram", **args)))

    def build_document(self, key: str | None = None, out: str | Path | None = None) -> Result:
        if key is not None:
            self.select_document(key)
        spec = self._spec_for(self.document_specs, self.document_var.get())
        if spec is None:
            return self._report(Result.failure("no document selected", verb="document"))
        target = str(out or self.out_var.get() or self.brain.out_dir)
        self.window.set_status(f"Building {spec['title']}…")
        self.update_idletasks()
        return self._remember(self._report(self.window.run("document", name=spec["key"], out=target)))

    def open_primary(self) -> bool:
        """Open the last built file: the PDF of a document, the PNG of a diagram."""
        if not self.last_primary:
            self.window.set_status("Nothing built yet: build a diagram or a document first")
            return False
        return self._open_path(self.last_primary)

    def open_folder(self) -> bool:
        folder = Path(self.out_var.get() or self.brain.out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        return self._open_path(folder)
