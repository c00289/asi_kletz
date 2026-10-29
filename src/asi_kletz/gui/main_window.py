"""MainWindow: navigation on the left, one Screen at a time on the right, status bar below.

The window never touches storage directly. Every change goes through ``run`` which calls
``Brain.execute`` with actor ``gui``; the event bus then refreshes whatever screen is open,
so edits made by the CLI or an agent against the same Brain appear live too. The theme picker
at the foot of the navigation column is the same: it runs the ``theme`` verb, and the window
repaints when the bus reports ``theme.changed``, whoever raised it. Three topics never refresh a
screen: ``theme.changed`` repaints instead, ``jira.live`` changes no database row (the JIRA
Live Data screen paints its own Result, which lives on the window as ``jira_live``) and neither does
``cs.exported`` (files written, 0.24.0). Those two are also the topics published from a worker
thread (the Jira fetches and ``cs export`` run off the Tk thread through ``execute_quiet``,
``gui/background.py``), so their branch in ``_on_event`` must return without touching a widget.

The window also owns the local automation server (``automation/server.py``): started after the
body is built, its port shown in the online indicator and written to the session file, stopped
and the file removed in ``close()`` before ``destroy()``. ``server=False`` or
``ASI_KLETZ_AUTOMATION=off`` leaves the window fully usable without it. Remote commands reach
the Tk thread through the server's ``on_main`` and pass ``remote_guard`` first, which refuses a
remote ``theme`` while the open screen has unsaved edits (a remote pick never prompts).
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from ..automation.session import session_path
from ..commands import Result
from ..locks import lock_dir
from ..prefs import prefs_path, prefs_problem, read_prefs
from ..version import __version__
from . import trace
from .jira_comments_window import JiraCommentsWindow
from .screens import Screen, ScreenFactory, build_default_screens
from .theme import Theme, ThemeFactory

if TYPE_CHECKING:
    from ..automation.server import AutomationServer
    from ..brain import Brain

PLAIN_TITLE = Theme.title


DEFAULT_SIZE = (1280, 800)
ONLINE = "◉ ONLINE"


def badge_text(title: str) -> str:
    """The theme badge: the title upper-cased with any parenthetical dropped (``Plain (native)`` -> ``PLAIN``)."""
    return re.sub(r"\s*\([^)]*\)", "", title).strip().upper()


def fit_geometry(width: int, height: int, screen_w: int, screen_h: int) -> tuple[str, bool]:
    """Geometry for a window that wants ``width`` x ``height`` on a ``screen_w`` x ``screen_h`` screen.

    Returns the geometry string and whether the window should open maximised ("zoomed"). The frame,
    the title bar and the taskbar take about 100 px, so on a laptop screen that cannot hold the full
    size a window of that size puts the status bar and the theme picker under the taskbar, where
    nobody can see them; maximising fits the work area exactly.
    """
    margin_w, margin_h = 16, 100
    if width + margin_w <= screen_w and height + margin_h <= screen_h:
        return f"{width}x{height}", False
    w = max(1, min(width, screen_w - margin_w))
    h = max(1, min(height, screen_h - margin_h))
    return f"{w}x{h}+0+0", True


class MainWindow(tk.Tk):
    def __init__(
        self,
        brain: Brain,
        factory: ScreenFactory | None = None,
        interactive: bool = True,
        theme: str | Theme | None = None,
        server: bool = True,
    ) -> None:
        super().__init__()
        self.brain = brain
        self.interactive = interactive
        warning = self._prefs_warning()
        self.theme = theme if isinstance(theme, Theme) else ThemeFactory.create(ThemeFactory.resolve(theme))
        self.theme.apply(self)
        # Tk's class binding makes a ttk combobox (and spinbox) pick its next value on the mouse wheel, so
        # scrolling a form with the pointer over one silently changed it (0.15.2: the owner's Safety Plan row
        # moved to PDP phase 2 while attaching a Jira ticket); here the wheel only ever scrolls
        for widget_class in ("TCombobox", "TSpinbox"):
            self.unbind_class(widget_class, "<MouseWheel>")
        self.theme_var = tk.StringVar(self, value=self.theme.title)
        self.online_var = tk.StringVar(self, value=ONLINE)
        self.badge_var = tk.StringVar(self, value=badge_text(self.theme.title))
        self.factory = factory or build_default_screens(brain)
        self._screens: dict[str, Screen] = {}
        self.current: Screen | None = None
        self.current_key: str | None = None
        self._refresh_job: str | None = None
        self._closed = False
        # the local automation server (None when off, or when it could not bind): owned here, not by a widget
        self.server: AutomationServer | None = None
        # the last `jira live` Result of this session: memory, not storage; it outlives the screens
        self.jira_live: Result | None = None
        self.comment_windows: dict[str, JiraCommentsWindow] = {}
        # the sprint and the week the Sprint Board and Weekly Status screens show: on the window, so a
        # theme pick (which recreates the screens) comes back to the same ones
        self.sprint_number: int | None = None
        self.week_start: str | None = None

        self.title(f"ASI Kletz {__version__}")
        geometry, zoom = fit_geometry(*DEFAULT_SIZE, self.winfo_screenwidth(), self.winfo_screenheight())
        self.geometry(geometry)
        if zoom:
            try:
                self.state("zoomed")  # Windows: fill the work area, taskbar excluded
            except tk.TclError:
                pass  # elsewhere the clamped geometry already fits
        self.minsize(900, 600)
        self._build_menu()
        self._build_body()
        self._bind_keys()
        trace.start(__version__, server=server)  # gui.log beside the preferences: why a window ends (0.18.1)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._handler = self.brain.events.subscribe("*", self._on_event)
        self.show("dashboard" if "dashboard" in self.factory else self.factory.items()[0][0])
        if warning:
            self.set_status("Warning: " + warning)
        if server:
            self._start_server()

    # -- the automation server -------------------------------------------
    def _start_server(self) -> None:
        """Bind the local server and write the session file; any failure is a status-bar warning."""
        from ..automation.server import AutomationServer
        from ..automation.session import automation_enabled, write_session

        if not automation_enabled():
            return
        server = AutomationServer(self)
        try:
            server.start()
            write_session(port=server.port, token=server.token, db=self.brain.db_path, started_at=server.started_at)
        except OSError as exc:
            server.stop()
            self.set_status(f"Warning: automation server not started ({exc}); the window runs without it")
            return
        self.server = server
        self.online_var.set(self._online_text())

    def _online_text(self) -> str:
        return f"{ONLINE} :{self.server.port}" if self.server is not None and self.server.running else ONLINE

    def remote_guard(self, verb: str, args: dict[str, Any]) -> Result | None:
        """Refuse a remote command that would destroy what the engineer is typing; ``None`` lets it run.

        One rule today: a remote ``theme <key>`` while the open screen reports ``is_dirty()`` is
        refused without a dialog (the verb never runs, so the preference is not latched either).
        A safety hook, not a permission system: approval mode is another plan.
        """
        if verb == "theme" and args.get("key"):
            dirty = getattr(self.current, "is_dirty", None)
            if callable(dirty) and dirty():
                result = Result.failure(
                    f"theme change refused: the {self.current_key} screen has unsaved edits", verb="theme"
                )
                result.warnings = ["save or discard the edits, then retry"]
                return result
        return None

    @staticmethod
    def _prefs_warning() -> str | None:
        """A corrupt preferences file or an unknown latched theme is ignored, and said so once."""
        problem = prefs_problem()
        if problem:
            return problem
        latched = read_prefs().get("theme")
        if latched and not ThemeFactory.known(str(latched)):
            return f"ignored unknown theme {latched!r} latched in {prefs_path()}; using {ThemeFactory.default_key()}"
        return None

    # -- layout ---------------------------------------------------------
    def _theme_choices(self) -> list[tuple[str, str]]:
        """``(key, title)`` for the picker: the 32 palettes in catalog order, then plain."""
        return [(entry.key, entry.title) for entry in ThemeFactory.entries()] + [(Theme.key, PLAIN_TITLE)]

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Export workbook", accelerator="Ctrl+E", command=self.export_workbook)
        file_menu.add_command(label="Import workbook…", command=lambda: self.show("transfer"))
        file_menu.add_separator()
        file_menu.add_command(label="Build Safety Plan document", command=self.build_safety_plan)
        file_menu.add_command(label="Build current week (tracker)", command=lambda: self.build_tracker("week"))
        file_menu.add_command(label="Build tracker history", command=lambda: self.build_tracker("history"))
        file_menu.add_separator()
        file_menu.add_command(label="Quit", accelerator="Ctrl+Q", command=self.close)
        menu.add_cascade(label="File", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        for key, title in self.factory.items():
            view_menu.add_command(label=title, command=lambda k=key: self.show(k))
        view_menu.add_separator()
        view_menu.add_cascade(label="Theme", menu=self._build_theme_menu(view_menu))
        menu.add_cascade(label="View", menu=view_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About", command=self.about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menu)

    def _build_theme_menu(self, parent: tk.Menu) -> tk.Menu:
        """View > Theme: one submenu per family with a radio item per tone, then Plain (native)."""
        theme_menu = tk.Menu(parent, tearoff=False)
        families: dict[str, tk.Menu] = {}
        for entry in ThemeFactory.entries():
            if entry.family not in families:
                families[entry.family] = tk.Menu(theme_menu, tearoff=False)
                theme_menu.add_cascade(label=entry.family.title(), menu=families[entry.family])
            families[entry.family].add_radiobutton(
                label=entry.tone.title(), variable=self.theme_var, value=entry.title,
                command=lambda k=entry.key: self.pick_theme(k),
            )
        theme_menu.add_separator()
        theme_menu.add_radiobutton(
            label=PLAIN_TITLE, variable=self.theme_var, value=PLAIN_TITLE, command=lambda: self.pick_theme(Theme.key)
        )
        return theme_menu

    def _build_body(self) -> None:
        paned = ttk.PanedWindow(self, orient="horizontal")
        nav_box = ttk.Frame(paned, padding=(0, 0), style="Nav.TFrame")
        brand = ttk.Frame(nav_box, padding=(12, 14, 12, 10), style="Nav.TFrame")
        brand.pack(fill="x")
        ttk.Label(brand, text="ASI KLETZ", style="Title.TLabel").pack(anchor="w")
        ttk.Label(brand, text=f"FUSA // v{__version__}", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Frame(nav_box, height=1, style="Rule.TFrame").pack(fill="x", padx=8)
        self._build_picker(nav_box)
        self.nav = tk.Listbox(
            nav_box, exportselection=False, activestyle="none", width=24, font=self.theme.ui
        )
        for _, title in self.factory.items():
            self.nav.insert("end", f"   {title.upper()}")
        self.nav.pack(fill="both", expand=True, padx=8, pady=8)
        self.nav.bind("<<ListboxSelect>>", self._on_nav)
        paned.add(nav_box, weight=0)
        self.content = ttk.Frame(paned)
        paned.add(self.content, weight=1)

        ttk.Frame(self, height=1, style="Rule.TFrame").pack(fill="x", side="bottom")
        status = self.status_bar = ttk.Frame(self, padding=(10, 4), style="Status.TFrame")
        status.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(value="Ready")
        # online indicator (with the server's port), theme badge, status text; the database on the right
        self.online_var.set(self._online_text())
        self.badge_var.set(badge_text(self.theme.title))
        self.online_label = ttk.Label(status, textvariable=self.online_var, style="Status.TLabel")
        self.online_label.pack(side="left", padx=(0, 14))
        self.badge_label = ttk.Label(
            status, textvariable=self.badge_var, style="StatusMuted.TLabel", font=self.theme.mono
        )
        self.badge_label.pack(side="left", padx=(0, 14))
        self.status_label = ttk.Label(status, textvariable=self.status_var, anchor="w", style="Status.TLabel")
        self.status_label.pack(side="left", fill="x", expand=True)
        ttk.Label(status, text=self.brain.db_path, style="StatusMuted.TLabel").pack(side="right")
        paned.pack(fill="both", expand=True)  # packed last: a short window squeezes the body, never the status bar

    def _build_picker(self, nav_box: ttk.Frame) -> None:
        """The theme combobox at the foot of the navigation column; read-only, so never blank."""
        choices = self._theme_choices()
        self._theme_by_title = {title: key for key, title in choices}
        picker = ttk.Frame(nav_box, padding=(8, 0, 8, 10), style="Nav.TFrame")
        picker.pack(fill="x", side="bottom")
        ttk.Label(picker, text="THEME", style="Nav.TLabel", font=self.theme.mono).pack(anchor="w", pady=(0, 2))
        self.theme_box = ttk.Combobox(
            picker, textvariable=self.theme_var, state="readonly", values=[title for _, title in choices]
        )
        self.theme_box.pack(fill="x")
        self.theme_box.bind("<<ComboboxSelected>>", self._on_theme_pick)

    def _bind_keys(self) -> None:
        self.bind_all("<Control-n>", lambda e: self._delegate("new"))
        self.bind_all("<Control-s>", lambda e: self._delegate("save"))
        self.bind_all("<Control-e>", lambda e: self.export_workbook())
        self.bind_all("<Control-q>", lambda e: self.close())
        self.bind_all("<F5>", lambda e: self.current and self.current.refresh())

    def _delegate(self, method: str) -> None:
        handler = getattr(self.current, method, None)
        if callable(handler):
            handler()

    # -- navigation -----------------------------------------------------
    def show(self, key: str) -> Screen:
        if key not in self._screens:
            self._screens[key] = self.factory.create(key, self.content, self)
        if self.current is not None and self.current is not self._screens[key]:
            self.current.pack_forget()
        self.current = self._screens[key]
        self.current_key = key
        self.current.pack(fill="both", expand=True)
        keys = [k for k, _ in self.factory.items()]
        index = keys.index(key)
        self.nav.selection_clear(0, "end")
        self.nav.selection_set(index)
        self.nav.see(index)
        self.title(f"ASI Kletz {__version__} — {self.factory.title(key)}")
        self.current.on_show()
        return self.current

    def _on_nav(self, _event: tk.Event) -> None:
        selection = self.nav.curselection()
        if selection:
            key = self.factory.items()[selection[0]][0]
            if key != self.current_key:
                self.show(key)

    # -- theme ----------------------------------------------------------
    def _on_theme_pick(self, _event: tk.Event | None = None) -> None:
        key = self._theme_by_title.get(self.theme_var.get())
        if key and key != self.theme.key:
            self.pick_theme(key)
        else:
            self._sync_theme_var()

    def _sync_theme_var(self) -> None:
        """The picker shows the theme that is painting the window, never anything else."""
        self.theme_var.set(self.theme.title)

    def pick_theme(self, key: str) -> Result:
        """Latch ``key`` through the ``theme`` verb; the ``theme.changed`` event then repaints the window."""
        dirty = getattr(self.current, "is_dirty", None)
        if callable(dirty) and dirty() and not self.confirm(
            "Change theme", "Changing the theme rebuilds the screen and drops unsaved edits. Change it anyway?"
        ):
            self._sync_theme_var()
            return Result.failure("cancelled", verb="theme")
        result = self.run("theme", key=key)
        if not result.ok:
            self._sync_theme_var()
        return result

    def set_theme(self, key: str) -> None:
        """Repaint by rebuilding: apply the theme to the root, then recreate menu, body and the open screen."""
        self._cancel_refresh()
        current = self.current_key
        self.theme = ThemeFactory.create(key)
        self.theme.apply(self)  # fonts, ttk base, styles, option database
        self.theme_var.set(self.theme.title)
        for child in self.winfo_children():  # menu, paned body, rule, status bar, comment windows
            child.destroy()
        self.comment_windows.clear()  # destroyed with the rest: a Toplevel is a child of the root
        self._screens.clear()
        self.current = None
        self.current_key = None
        self._build_menu()
        self._build_body()  # includes the picker, now showing `key`
        self.show(current or "dashboard")
        self.set_status(f"Theme: {self.theme.title}")

    # -- feedback -------------------------------------------------------
    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def status_text(self) -> str:
        return self.status_var.get()

    def notify_error(self, title: str, message: str) -> None:
        self.set_status(f"Error: {message}")
        if self.interactive:
            messagebox.showerror(title, message, parent=self)

    def confirm(self, title: str, message: str) -> bool:
        if not self.interactive:
            return True
        return bool(messagebox.askyesno(title, message, parent=self))

    def about(self) -> None:
        text = (
            f"ASI Kletz {__version__}\nFuSa safety-plan API with a tkinter front end.\n\n"
            f"Database: {self.brain.db_path}\n"
            f"Lock directory: {lock_dir()}  (one primary tool at a time; this window holds the slot)\n"
            + (
                f"Automation: {self.server.address}  (session file: {session_path()})"
                if self.server is not None and self.server.running
                else "Automation: off (no session file; started with --no-server or ASI_KLETZ_AUTOMATION=off)"
            )
        )
        if self.interactive:
            messagebox.showinfo("About ASI Kletz", text, parent=self)
        self.set_status(text.replace("\n", "  "))

    # -- commands -------------------------------------------------------
    def execute_quiet(self, verb: str, **args: Any) -> Result:
        """``Brain.execute`` as actor ``gui`` and nothing else: no status bar, no dialog, no widget.

        The one window method a worker thread may call. The Jira fetches run here off the Tk
        thread (``jira_live_screen.py``); every other caller goes through ``run`` / ``run_quiet``,
        which call this and then report on the Tk thread.
        """
        return self.brain.execute(verb, args, actor="gui")

    def report_quiet(self, result: Result) -> None:
        """The status-bar half of ``run_quiet`` for a Result obtained elsewhere (a worker thread)."""
        self._report(result, quiet=True)

    def report(self, result: Result, verb: str | None = None) -> Result:
        """What ``run`` says about a Result obtained elsewhere (a ``BackgroundFetch`` that ran off the Tk
        thread, 0.24.0): a failure is a status-bar line plus a dialog when interactive, warnings a status-bar
        line. Called on the Tk thread, after the poll."""
        if result.verb is None:
            result.verb = verb
        self._report(result, quiet=False)
        return result

    def _report(self, result: Result, *, quiet: bool) -> None:
        if not result.ok:
            message = "; ".join(result.errors) or "unknown error"
            if quiet:
                self.set_status(f"Error: {message}")
            else:
                self.notify_error(f"{result.verb or 'command'} failed", message)
        elif result.warnings:
            self.set_status("Warning: " + "; ".join(result.warnings))

    def _execute(self, verb: str, args: dict[str, Any], *, quiet: bool) -> Result:
        result = self.execute_quiet(verb, **args)
        if result.verb is None:
            result.verb = verb
        self._report(result, quiet=quiet)
        return result

    def run(self, verb: str, **args: Any) -> Result:
        """Run a verb as actor ``gui``; a failure goes to the status bar and, when interactive, a dialog."""
        return self._execute(verb, args, quiet=False)

    def run_quiet(self, verb: str, **args: Any) -> Result:
        """``run`` without the dialog: ``execute_quiet`` and then the status bar, on the Tk thread."""
        return self._execute(verb, args, quiet=True)

    def open_comments(self, key: str) -> JiraCommentsWindow:
        """The comments window of ``key``: one per ticket, brought to the front when it is already open."""
        win = self.comment_windows.get(key)
        if win is not None and win.winfo_exists():
            win.lift()
            win.focus_set()
            return win
        win = self.comment_windows[key] = JiraCommentsWindow(self, key)
        win.fetch()
        return win

    def export_workbook(self) -> Result:
        result = self.run("export", format="excel")
        if result.ok:
            detail = " (" + "; ".join(result.warnings) + ")" if result.warnings else ""
            self.set_status(f"Workbook written: {result.data['path']}" + detail)
        return result

    def build_safety_plan(self) -> Result:
        """File > Build Safety Plan document: ``document safety_plan`` on the transfer screen, so the log shows."""
        screen = self.show("transfer")
        return screen.build_document("safety_plan")

    def build_tracker(self, kind: str) -> Result:
        """File > Build current week / tracker history: ``tracker build`` on the Weekly Status screen."""
        screen = self.show("tracker")
        return screen.build_text(kind)

    # -- events ---------------------------------------------------------
    def _on_event(self, topic: str, event: dict[str, Any]) -> None:
        if topic == "theme.changed":
            key = str(event.get("theme") or "")
            if ThemeFactory.known(key) and ThemeFactory.canonical(key) != self.theme.key:
                self.set_theme(key)
            return
        if topic in ("jira.live", "cs.exported"):
            # No database row changed: the live screen paints its own Result, an export wrote files. These
            # handlers run on the worker thread that ran `jira live` or `cs export` (0.24.0), so they must
            # return before any Tk call: the `after` below would be a cross-thread Tk call. No other verb
            # runs off the Tk thread (`jira comments`, `confluence search`, `people lookup` and `stpa
            # refresh` without --apply publish nothing), so no other topic reaches here from a worker.
            return
        if self._refresh_job is not None:
            return
        self._refresh_job = self.after(50, self._refresh_after_event)

    def _refresh_after_event(self) -> None:
        self._refresh_job = None
        if self.current is not None:
            self.current.refresh()

    def _cancel_refresh(self) -> None:
        if self._refresh_job is not None:  # never let a refresh fire into widgets that are gone
            self.after_cancel(self._refresh_job)
            self._refresh_job = None

    def close(self) -> None:
        """Stop the server and clear the session file, then destroy the root. Idempotent."""
        if self._closed:
            return
        self._closed = True
        trace.note("close", via=trace.caller())
        self.brain.events.unsubscribe("*", self._handler)
        self._cancel_refresh()
        if self.server is not None:  # before destroy(): a request in flight gets its 504, not a dead window
            from ..automation.session import clear_session

            self.server.stop()
            self.server = None
            clear_session()
        self.destroy()
        trace.note("destroyed")
