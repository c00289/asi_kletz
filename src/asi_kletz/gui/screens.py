"""Screen base class, ScreenFactory, the ScrollableFrame and FrozenPane helpers, and the built-in screens."""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Iterable, Mapping
from tkinter import ttk
from typing import TYPE_CHECKING, Any, ClassVar

from ..errors import NotFound

if TYPE_CHECKING:
    from ..brain import Brain
    from .main_window import MainWindow
    from .theme import Theme

PLAN_ENTITY = "safety_plan_row"

# -- the plan as a stack (0.8.3 on the matrix, 0.8.4 on the table) ------------------------------------
# Owner, 2026-10-28: the PDP phase, the lifecycle phase and the deliverable side by side crowded the
# screens; stack them. One column, read top down: a PDP phase row, its lifecycle phase rows indented
# under it, their deliverables indented under those, in the rows' own order.
PLAN = "plan"  # the stacked column's name on a tree; not a field of the schema
PLAN_HEADER = "PDP phase  ›  Safety lifecycle phase  ›  Safety deliverable"
STACKED = ("pdp_phase", "lifecycle_phase", "deliverable")  # the fields the stack replaces on a table
INDENT = "    "  # one level of the stack
PDP_TAG, PHASE_TAG = "pdp", "phase"  # the group rows' tags; a deliverable row carries the stripe tag alone


def pdp_title(value: Any) -> str:
    return f"PDP phase {value}" if value not in (None, "") else "(no PDP phase)"


def phase_title(value: Any) -> str:
    return str(value) if value not in (None, "") else "(no lifecycle phase)"


def stack(rows: list[dict[str, Any]]) -> list[tuple[str, int, str, dict[str, Any] | None]]:
    """The plan as a stack: ``(iid, level, text, row)`` per line, in the rows' own order.

    Level 0 is a PDP phase (iid ``pdp:<value>``), level 1 a lifecycle phase under it
    (``phase:<pdp>:<value>``), level 2 a deliverable (the row id, ``row`` set). A group line opens
    whenever the value changes between consecutive rows, so a plan kept in order (as the Safety
    Plan is, by ``order``) shows every phase once; a plan out of order shows the truth of its order:
    the same phase opens again, its iid suffixed ``#2``, ``#3``, ... since a Treeview item id must be
    unique (0.15.1: a plan with PDP phase 2 at order 1 and again at order 8 broke every stacked screen).
    """
    lines: list[tuple[str, int, str, dict[str, Any] | None]] = []
    opened: dict[str, int] = {}

    def iid_of(group: str) -> str:
        opened[group] = opened.get(group, 0) + 1
        return group if opened[group] == 1 else f"{group}#{opened[group]}"

    pdp = phase = object()
    for row in rows:
        if row.get("pdp_phase") != pdp:
            pdp, phase = row.get("pdp_phase"), object()
            lines.append((iid_of(f"pdp:{pdp}"), 0, pdp_title(pdp), None))
        if row.get("lifecycle_phase") != phase:
            phase = row.get("lifecycle_phase")
            lines.append((iid_of(f"phase:{pdp}:{phase}"), 1, INDENT + phase_title(phase), None))
        deliverable = "" if row.get("deliverable") is None else str(row["deliverable"]).replace("\n", " ")
        lines.append((str(row["id"]), 2, INDENT * 2 + deliverable, row))
    return lines


def is_group(iid: str) -> bool:
    """A group row of the stack (a PDP or lifecycle phase), as opposed to a deliverable row keyed by its id."""
    return not iid.isdigit()


def style_group_rows(tree: ttk.Treeview, theme: Theme) -> None:
    """Stripe the rows, then put the group tags back in front: the first tag wins an option, so a
    group row takes its colour and font from its group tag and its background from the stripe."""
    groups = {iid: tree.item(iid, "tags") for iid in tree.get_children() if is_group(iid)}
    theme.stripe(tree)
    tree.tag_configure(PDP_TAG, foreground=theme.palette.primary, font=theme.heading)
    tree.tag_configure(PHASE_TAG, foreground=theme.palette.accent, font=theme.heading)
    for iid, tags in groups.items():
        tree.item(iid, tags=(*tags, *tree.item(iid, "tags")))


class Screen(ttk.Frame):
    """One page in the main window. Subclasses override ``build`` and ``refresh``."""

    key: ClassVar[str] = ""
    title: ClassVar[str] = ""

    def __init__(self, master: tk.Misc, window: MainWindow) -> None:
        super().__init__(master, padding=8)
        self.window = window
        self.brain: Brain = window.brain
        self.build()

    def build(self) -> None:
        pass

    def refresh(self) -> None:
        pass

    def on_show(self) -> None:
        self.refresh()


class ScrollableFrame(ttk.Frame):
    """A frame with a vertical scrollbar; put children in ``.inner``."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")


NARROW_HEADING = 60  # a column narrower than this cannot show its heading: hover names it
RIGHT_MIN = 120  # the frozen pane opens at its full fitted width; the scrolling pane keeps at least this many px


def bind_horizontal_scroll(tree: ttk.Treeview) -> None:
    """Shift+wheel and the arrow keys scroll a wide table sideways; the scrollbar alone is easy to miss."""

    tree.bind("<Shift-MouseWheel>", lambda e: scroll_sideways(tree, int(-e.delta / 120) * 3))
    tree.bind("<Left>", lambda e: scroll_sideways(tree, -3))
    tree.bind("<Right>", lambda e: scroll_sideways(tree, 3))


def scroll_sideways(tree: ttk.Treeview, units: int) -> str:
    """Scroll a table sideways by ``units`` columns-worth; returns "break" so Tk does nothing else."""
    tree.xview_scroll(units, "units")
    return "break"


def fit_columns(
    tree: ttk.Treeview,
    extra: Mapping[str, Iterable[str]] | None = None,
    *,
    min_width: int = 40,
    max_width: int = 600,
    padding: int = 24,
) -> dict[str, int]:
    """Size every column of ``tree`` to its widest text, measured in pixels with the real fonts.

    The candidates of a column are its heading (the ``Treeview.Heading`` font), every cell the
    tree holds for it (the ``Treeview`` font) and ``extra[column]``, the rest of its domain: an
    enum field's lookup values, so the column fits "Out-of-Scope" even while no row says so.
    The width is the widest candidate plus ``padding``, clamped to ``[min_width, max_width]``.
    Every fitted column gets ``minwidth`` equal to its width and ``stretch`` off: a column left
    stretchable is shrunk by Tk towards its minwidth whenever the fitted total exceeds the widget
    width, which collapsed a correctly measured Summary to "Summa". Works on a withdrawn window:
    ``font measure`` needs no mapping. Returns ``{column: width}``.
    """
    style = ttk.Style(tree)
    body = tkfont.Font(tree, font=style.lookup("Treeview", "font") or "TkDefaultFont")
    head = tkfont.Font(tree, font=style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    rows = tree.get_children("")
    widths: dict[str, int] = {}
    for column in tree["columns"]:
        widest = head.measure(str(tree.heading(column, "text")))
        texts = [str(tree.set(iid, column)) for iid in rows]
        if extra:
            texts.extend(str(text) for text in extra.get(column, ()))
        if texts:
            widest = max(widest, max(body.measure(text) for text in texts))
        width = max(min_width, min(widest + padding, max_width))
        tree.column(column, width=width, minwidth=width, stretch=False)
        widths[column] = width
    return widths


def heading_under(tree: ttk.Treeview, event: tk.Event) -> str | None:
    """The full heading text under the pointer when it is over a column too narrow to show it."""
    if tree.identify("region", event.x, event.y) != "heading":
        return None
    column = tree.identify_column(event.x)
    if not column:
        return None
    name = tree.column(column, "id")
    if int(tree.column(name, "width")) >= NARROW_HEADING:
        return None
    return str(tree.heading(name, "text")) or None


class FrozenPane(ttk.Frame):
    """Two tables in lock-step: the ``frozen`` columns stay put on the left while the rest scrolls sideways.

    ``ttk.Treeview`` cannot pin a column, so the pane holds two. ``left`` shows the frozen columns
    only; ``right`` owns every column of ``columns`` but displays the others, so a screen keeps
    working on ``right`` alone (``set``, ``item``, ``column``, ``heading``, ``insert``, ``delete``,
    ``get_children``) and calls ``mirror()`` after every fill or sort. ``mirror`` rebuilds ``left``
    from ``right``: the same iids in the same order, the frozen cells, each row's tags and the tag
    colours (striping, done, muted), the heading texts and anchors, then fits the frozen columns
    with ``fit_columns`` (``stretch`` off, so ``left`` is exactly as wide as its columns and never
    needs a horizontal bar). The two trees are the panes of ``split``, a horizontal
    ``ttk.PanedWindow`` (``left`` weight 0, ``right`` weight 1): after every ``mirror`` the sash
    sits where ``left`` shows its fitted columns in full (its longest row), leaving ``right`` at least
    ``RIGHT_MIN`` px
    (``place_sash``, once the split is mapped: Tk clamps a sash set before the split has its
    geometry to 0), and the user may drag it either way; dragging clips a tree, it never changes
    a column width. One vertical bar outside the split drives both trees and each tree's
    own scrolling moves the other; the horizontal bar under ``right`` drives ``right`` alone; the
    selection follows both ways; the wheel over either tree scrolls both (Shift+wheel and the
    arrow keys are bound by the screen on ``right``); a click on a left heading calls
    ``on_sort(column)``, the callable the screen sets.
    """

    def __init__(self, master: tk.Misc, columns: Iterable[str], frozen: Iterable[str]) -> None:
        super().__init__(master)
        self.frozen = tuple(frozen)
        self.on_sort: Callable[[str], None] | None = None
        self._syncing = False
        self._sash_job: str | None = None
        self._sash_pending = False  # a placement asked for while the split was not mapped: done on <Map>
        self.split = ttk.PanedWindow(self, orient="horizontal")
        self.left = ttk.Treeview(self.split, columns=self.frozen, show="headings", selectmode="browse")
        self.right = ttk.Treeview(self.split, columns=list(columns), show="headings", selectmode="browse")
        self.split.add(self.left, weight=0)
        self.split.add(self.right, weight=1)
        self.ybar = ttk.Scrollbar(self, orient="vertical", command=self.yview)
        self.xbar = ttk.Scrollbar(self, orient="horizontal", command=self.right.xview)
        self.left.configure(yscrollcommand=lambda first, last: self._scrolled(self.left, self.right, first, last))
        self.right.configure(
            yscrollcommand=lambda first, last: self._scrolled(self.right, self.left, first, last),
            xscrollcommand=self.xbar.set,
        )
        self.split.grid(row=0, column=0, sticky="nsew")
        self.ybar.grid(row=0, column=1, sticky="ns")
        self.xbar.grid(row=1, column=0, sticky="ew")  # under ``right`` alone: ``_align_xbar`` pads it past the sash
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.right.bind("<Configure>", self._align_xbar, add="+")  # a dragged sash moves ``right``: follow it
        self.split.bind("<Map>", self._on_map, add="+")
        for column in self.frozen:
            self.left.column(column, stretch=False)
            self.left.heading(column, command=lambda c=column: self._sort(c))
        self.left.bind("<<TreeviewSelect>>", lambda e: self._follow(self.left, self.right))
        self.right.bind("<<TreeviewSelect>>", lambda e: self._follow(self.right, self.left))
        self.left.bind("<MouseWheel>", self._wheel)
        self.right.bind("<MouseWheel>", self._wheel)
        self.set_display(self.right["columns"])

    def set_display(self, names: Iterable[str]) -> None:
        """``right`` displays ``names`` minus the frozen columns, which ``left`` shows instead."""
        self.right["displaycolumns"] = [name for name in names if name not in self.frozen]

    def mirror(self, extra: Mapping[str, Iterable[str]] | None = None) -> None:
        """Rebuild ``left`` from ``right``; ``extra`` is passed on to ``fit_columns`` for the frozen columns."""
        left, right = self.left, self.right
        left.delete(*left.get_children(""))
        for tag in self.tk.call(right, "tag", "names"):
            options = {name: value for name, value in right.tag_configure(tag).items() if value != ""}
            if options:
                left.tag_configure(tag, **options)
        for column in self.frozen:
            left.heading(column, text=right.heading(column, "text"))
            left.column(column, anchor=right.column(column, "anchor"))
        for iid in right.get_children(""):
            values = [right.set(iid, column) for column in self.frozen]
            left.insert("", "end", iid=iid, values=values, tags=right.item(iid, "tags"))
        fit_columns(left, extra)
        self.place_sash()
        self._follow(right, left)
        left.yview_moveto(right.yview()[0])

    def fitted_width(self) -> int:
        """The width of ``left``'s columns together: what the frozen pane needs to show them all."""
        return sum(int(self.left.column(column, "width")) for column in self.frozen)

    def place_sash(self) -> None:
        """Put the sash where ``left`` shows its fitted columns in full: as wide as its longest row.

        Owner, 2026-10-28: the left pane of the Safety Plan and of the Safety Plan Matrix is as wide as
        the longest row it holds. Runs after the idle so a mapped window has its geometry: the one cap
        is that ``right`` keeps ``RIGHT_MIN`` px of the split's actual width. While the split is not
        mapped (a screen built but not yet shown, a
        withdrawn window) the placement waits for its ``<Map>``: Tk clamps a sash set on a split
        that has no geometry yet to 0, and a weight-0 pane never grows back from 0 on its own.
        Where the user drags the sash afterwards is the user's business until the next ``mirror``.
        """
        if self._sash_job is not None:
            self.after_cancel(self._sash_job)
        self._sash_job = self.after_idle(self._place_sash)

    def _place_sash(self) -> None:
        self._sash_job = None
        if not self.winfo_exists():
            return
        if not self.split.winfo_ismapped() or self.split.winfo_width() <= 1:
            self._sash_pending = True
            return
        self._sash_pending = False
        self.split.sashpos(0, max(1, min(self.fitted_width(), self.split.winfo_width() - RIGHT_MIN)))
        self._align_xbar()

    def _on_map(self, event: tk.Event | None = None) -> None:
        if self._sash_pending:
            self.place_sash()

    def _align_xbar(self, event: tk.Event | None = None) -> None:
        """Keep the horizontal bar under ``right``: its left edge follows the sash."""
        self.xbar.grid_configure(padx=(self.right.winfo_x(), 0))

    def destroy(self) -> None:
        if self._sash_job is not None:
            self.after_cancel(self._sash_job)
            self._sash_job = None
        super().destroy()

    def yview(self, *args: str) -> tuple[float, float] | None:
        """The vertical bar's command: both trees move together."""
        if not args:
            return self.right.yview()
        self.right.yview(*args)
        self.left.yview(*args)
        return None

    def _scrolled(self, source: ttk.Treeview, other: ttk.Treeview, first: str, last: str) -> None:
        self.ybar.set(first, last)
        if self._syncing:
            return
        self._syncing = True
        try:
            other.yview_moveto(float(first))
        finally:
            self._syncing = False

    def _follow(self, source: ttk.Treeview, other: ttk.Treeview) -> None:
        """Select in ``other`` what ``source`` selected; a no-op when they agree, which ends the echo."""
        if self._syncing:
            return
        selection = source.selection()
        if selection == other.selection() or not all(other.exists(iid) for iid in selection):
            return
        self._syncing = True
        try:
            if selection:
                other.selection_set(selection)
                other.see(selection[0])
            else:
                other.selection_remove(*other.selection())
        finally:
            self._syncing = False

    def _wheel(self, event: tk.Event) -> str:
        units = int(-event.delta / 120)
        self.right.yview_scroll(units, "units")
        self.left.yview_scroll(units, "units")
        return "break"

    def _sort(self, column: str) -> None:
        if self.on_sort is not None:
            self.on_sort(column)


ScreenBuilder = Callable[[tk.Misc, "MainWindow"], Screen]


class ScreenFactory:
    """Key -> (title, builder). The navigation list is built from this."""

    def __init__(self) -> None:
        self._builders: dict[str, tuple[str, ScreenBuilder]] = {}

    def register(self, key: str, title: str, builder: ScreenBuilder) -> None:
        if key in self._builders:
            raise ValueError(f"screen {key!r} already registered")
        self._builders[key] = (title, builder)

    def create(self, key: str, master: tk.Misc, window: MainWindow) -> Screen:
        try:
            title, builder = self._builders[key]
        except KeyError:
            raise NotFound(f"unknown screen {key!r}; known: {', '.join(self._builders)}") from None
        screen = builder(master, window)
        screen.key = key
        screen.title = title
        return screen

    def items(self) -> list[tuple[str, str]]:
        return [(key, title) for key, (title, _) in self._builders.items()]

    def title(self, key: str) -> str:
        return self._builders[key][0]

    def __contains__(self, key: object) -> bool:
        return key in self._builders


def build_default_screens(brain: Brain) -> ScreenFactory:
    """The screens of the window, in navigation order: Dashboard, JIRA Live Data, Safety Plan,
    Safety Plan Matrix, Sprint Board, Weekly Status, Holidays, Parameters, Export / Import.

    A screen is added by registration here; the list is the design, not a cap. Registering
    another entity still gives it a table, commands, JSON and a workbook sheet, never a screen
    by itself.
    """
    from .dashboard import DashboardScreen
    from .entity_screen import EntityScreen
    from .jira_live_screen import JiraLiveScreen
    from .matrix_screen import SafetyPlanMatrixScreen
    from .sprint_board_screen import SprintBoardScreen
    from .tracker_screen import TrackerScreen
    from .transfer_screen import TransferScreen

    plan = brain.registry.get(PLAN_ENTITY)
    holiday = brain.registry.get("holiday")  # the generic table and form: no stack, so no frozen column
    parameter = brain.registry.get("parameter")  # the standards' document-level parameters (0.14.0)
    factory = ScreenFactory()
    factory.register("dashboard", "Dashboard", DashboardScreen)
    factory.register("jira_live", "JIRA Live Data", JiraLiveScreen)
    factory.register("safety_plan", "Safety Plan", lambda master, window: EntityScreen(master, window, plan))
    factory.register("safety_plan_matrix", "Safety Plan Matrix", SafetyPlanMatrixScreen)
    factory.register("sprint_board", "Sprint Board", SprintBoardScreen)
    factory.register("tracker", "Weekly Status", TrackerScreen)
    factory.register("holidays", "Holidays", lambda master, window: EntityScreen(master, window, holiday))
    factory.register("parameters", "Parameters", lambda master, window: EntityScreen(master, window, parameter))
    factory.register("transfer", "Export / Import", TransferScreen)
    return factory
