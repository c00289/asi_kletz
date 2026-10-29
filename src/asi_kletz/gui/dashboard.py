"""DashboardScreen: deliverable counts by status, the active sprint, counts by lifecycle phase, open
deliverables, recent changes.

The numbers come from ``generate.plan_queries``, the same helpers the diagrams and documents
use, so a count on the screen and the same count in a report cannot drift.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from ..generate import plan_queries as q
from ..generate import sprint_queries as sq
from .screens import PLAN_ENTITY, Screen, fit_columns
from .theme import GridBanner

TOTAL = "total"
PHASE_COLUMNS = ("lifecycle_phase", "deliverables", "done")
OPEN_COLUMNS = ("deliverable", "status", "deadline")  # in plan order; ``order`` is no column since 0.9.0
AUDIT_COLUMNS = ("ts", "actor", "action", "entity", "entity_id")  # entity_id stays: it is the trace, not a vestige
SPRINT_TILES = (
    ("sprint", "SPRINT"), ("committed", "COMMITTED"), ("done", "DONE"), ("to_go", "TO GO"),
    ("unpointed", "UNPOINTED"), ("days_left", "DAYS LEFT"), ("velocity", "VELOCITY"),
)
NO_SPRINT = "No active sprint (click to open the Sprint Board)"
# 0.23.0, Phase B of the Confluence integration plan: deliverables with a Confluence page among their URLs, with
# the placeholder still among them, with no URL at all (``plan_queries.counts_by_link``)
LINK_TILES = (("confluence", "CONFLUENCE PAGE"), ("placeholder", "PLACEHOLDER"), ("none", "NO URL"))
LINK_TITLE = "Work product links (click to open the plan)"
# 0.24.0: STPA lives here (the owner: "move everything to Kletz"). Two tiles, the structures and the analyses;
# the parts have no tile of their own, the two screens count them. A click opens the screen.
STPA_TILES = (
    ("control_structure", "CS STRUCTURES", "control_structures"), ("stpa_analysis", "STPA ANALYSES", "stpa"),
)
STPA_TITLE = "STPA (click to open the screen)"


class DashboardScreen(Screen):
    def build(self) -> None:
        self.statuses = q.statuses(self.brain)
        self.phases = q.phases(self.brain)
        banner = GridBanner(self, self.window.theme, "SAFETY PLAN OVERVIEW", "WHEEL LOADER // FUNCTIONAL SAFETY")
        banner.pack(fill="x", pady=(0, 8))
        self.tiles = ttk.LabelFrame(self, text="Deliverables by status (click to open the plan)")
        self.tiles.pack(fill="x", pady=(0, 8))
        self._tile_vars: dict[str, tk.StringVar] = {}
        for index, (key, caption) in enumerate([(TOTAL, "DELIVERABLES"), *((s, s.upper()) for s in self.statuses)]):
            var = tk.StringVar(value="0")
            self._tile_vars[key] = var
            tile = ttk.Frame(self.tiles, padding=8, style="Tile.TFrame")
            tile.grid(row=0, column=index, padx=4, pady=4, sticky="nsew")
            ttk.Label(tile, textvariable=var, style="TileCount.TLabel").pack()
            ttk.Label(tile, text=caption, style="TileName.TLabel").pack()
            for widget in (tile, *tile.winfo_children()):
                widget.bind("<Button-1>", lambda e: self.window.show("safety_plan"))
                widget.bind("<Enter>", lambda e, t=tile: t.configure(style="TileHover.TFrame"))
                widget.bind("<Leave>", lambda e, t=tile: t.configure(style="Tile.TFrame"))
            self.tiles.columnconfigure(index, weight=1)
        self._build_sprint_tiles()
        self._build_link_tiles()
        self._build_stpa_tiles()

        lower = ttk.PanedWindow(self, orient="horizontal")
        lower.pack(fill="both", expand=True)
        self.phase_table = self._table(lower, "Deliverables by lifecycle phase", PHASE_COLUMNS, (260, 90, 60))
        self.open_table = self._table(lower, "Open deliverables", OPEN_COLUMNS, (300, 90, 120))
        self.audit = self._table(lower, "Recent changes", AUDIT_COLUMNS, (140, 70, 90, 110, 60))

    def _build_sprint_tiles(self) -> None:
        """Where the active sprint stands: the numbers of ``sprint board`` as tiles; a click opens the board."""
        self.sprint_tiles = ttk.LabelFrame(self, text=NO_SPRINT)
        self.sprint_tiles.pack(fill="x", pady=(0, 8))
        self._sprint_vars: dict[str, tk.StringVar] = {}
        for index, (key, caption) in enumerate(SPRINT_TILES):
            var = tk.StringVar(value="–")
            self._sprint_vars[key] = var
            tile = ttk.Frame(self.sprint_tiles, padding=8, style="Tile.TFrame")
            tile.grid(row=0, column=index, padx=4, pady=4, sticky="nsew")
            ttk.Label(tile, textvariable=var, style="TileCount.TLabel").pack()
            ttk.Label(tile, text=caption, style="TileName.TLabel").pack()
            for widget in (tile, *tile.winfo_children()):
                widget.bind("<Button-1>", lambda e: self.window.show("sprint_board"))
                widget.bind("<Enter>", lambda e, t=tile: t.configure(style="TileHover.TFrame"))
                widget.bind("<Leave>", lambda e, t=tile: t.configure(style="Tile.TFrame"))
            self.sprint_tiles.columnconfigure(index, weight=1)

    def _build_link_tiles(self) -> None:
        """Where the work products point (0.23.0): a Confluence page, the placeholder, nowhere; a click opens
        the plan."""
        self.link_tiles = ttk.LabelFrame(self, text=LINK_TITLE)
        self.link_tiles.pack(fill="x", pady=(0, 8))
        self._link_vars: dict[str, tk.StringVar] = {}
        for index, (key, caption) in enumerate(LINK_TILES):
            var = tk.StringVar(value="0")
            self._link_vars[key] = var
            tile = ttk.Frame(self.link_tiles, padding=8, style="Tile.TFrame")
            tile.grid(row=0, column=index, padx=4, pady=4, sticky="nsew")
            ttk.Label(tile, textvariable=var, style="TileCount.TLabel").pack()
            ttk.Label(tile, text=caption, style="TileName.TLabel").pack()
            for widget in (tile, *tile.winfo_children()):
                widget.bind("<Button-1>", lambda e: self.window.show("safety_plan"))
                widget.bind("<Enter>", lambda e, t=tile: t.configure(style="TileHover.TFrame"))
                widget.bind("<Leave>", lambda e, t=tile: t.configure(style="Tile.TFrame"))
            self.link_tiles.columnconfigure(index, weight=1)

    def _refresh_link_tiles(self, rows: list[dict[str, Any]]) -> None:
        counts = q.counts_by_link(self.brain, rows)
        for key, _caption in LINK_TILES:
            self._link_vars[key].set(str(counts[key]))

    def _build_stpa_tiles(self) -> None:
        """The control structures and the STPA analyses (0.24.0), one tile each; a click opens its screen."""
        self.stpa_tiles = ttk.LabelFrame(self, text=STPA_TITLE)
        self.stpa_tiles.pack(fill="x", pady=(0, 8))
        self._stpa_vars: dict[str, tk.StringVar] = {}
        for index, (entity, caption, screen) in enumerate(STPA_TILES):
            var = tk.StringVar(value="0")
            self._stpa_vars[entity] = var
            tile = ttk.Frame(self.stpa_tiles, padding=8, style="Tile.TFrame")
            tile.grid(row=0, column=index, padx=4, pady=4, sticky="nsew")
            ttk.Label(tile, textvariable=var, style="TileCount.TLabel").pack()
            ttk.Label(tile, text=caption, style="TileName.TLabel").pack()
            for widget in (tile, *tile.winfo_children()):
                widget.bind("<Button-1>", lambda e, k=screen: self.window.show(k))
                widget.bind("<Enter>", lambda e, t=tile: t.configure(style="TileHover.TFrame"))
                widget.bind("<Leave>", lambda e, t=tile: t.configure(style="Tile.TFrame"))
            self.stpa_tiles.columnconfigure(index, weight=1)

    def _refresh_stpa_tiles(self) -> None:
        for entity, _caption, _screen in STPA_TILES:
            self._stpa_vars[entity].set(str(self.brain.service(entity).count()))

    def _refresh_sprint_tiles(self) -> None:
        active = sq.active_sprint(self.brain)
        if active is None:
            self.sprint_tiles.configure(text=NO_SPRINT)
            for var in self._sprint_vars.values():
                var.set("–")
            return
        board = sq.board(self.brain, active)
        phase = active.get("lifecycle_phase") or ""
        pace = "overdue" if board["overdue"] else f"{active.get('start') or '?'} to {active.get('end') or '?'}"
        self.sprint_tiles.configure(
            text=f"Sprint {active['number']} · {active.get('label') or ''} · {phase} · {pace} (click to open the board)"
        )
        self._sprint_vars["sprint"].set(str(active["number"]))
        self._sprint_vars["committed"].set(f"{board['committed']} / {board['capacity']}")
        self._sprint_vars["done"].set(str(board["done"]))
        self._sprint_vars["to_go"].set(str(board["to_go"]))
        self._sprint_vars["unpointed"].set(str(board["unpointed"]))
        self._sprint_vars["days_left"].set("overdue" if board["overdue"] else str(board["days_left"]))
        self._sprint_vars["velocity"].set("–" if board["velocity"] is None else f"{board['velocity']:g}")

    def _table(
        self, parent: ttk.PanedWindow, title: str, columns: tuple[str, ...], widths: tuple[int, ...]
    ) -> ttk.Treeview:
        box = ttk.LabelFrame(parent, text=title)
        tree = ttk.Treeview(box, columns=columns, show="headings", height=12)
        for column, width in zip(columns, widths, strict=True):
            tree.heading(column, text=column.replace("_", " "))
            tree.column(column, width=width, minwidth=40)
        bar = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        parent.add(box, weight=1)
        return tree

    def _fill(self, tree: ttk.Treeview, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            values = ["" if row.get(c) is None else str(row.get(c)).replace("\n", " ") for c in columns]
            tree.insert("", "end", values=values)
        self.window.theme.stripe(tree)
        fit_columns(tree)

    def refresh(self) -> None:
        result = self.brain.execute("list", entity=PLAN_ENTITY, order_by="order", actor="gui")
        if not result.ok:
            self.window.notify_error("Could not load the safety plan", "; ".join(result.errors))
            return
        rows: list[dict[str, Any]] = result.data
        counts = q.counts_by_status(self.brain, rows)
        self._tile_vars[TOTAL].set(str(counts[TOTAL]))
        for status in self.statuses:
            self._tile_vars[status].set(str(counts.get(status, 0)))
        self._refresh_sprint_tiles()
        self._refresh_link_tiles(rows)
        self._refresh_stpa_tiles()
        self._fill(self.phase_table, q.counts_by_phase(self.brain, rows), PHASE_COLUMNS)
        open_rows = q.open_rows(rows)
        self._fill(self.open_table, open_rows, OPEN_COLUMNS)
        self._fill(self.audit, self.brain.storage.audit_tail(25), AUDIT_COLUMNS)
        self.window.set_status(f"{len(open_rows)} open of {len(rows)} deliverables  |  Database: {self.brain.db_path}")
