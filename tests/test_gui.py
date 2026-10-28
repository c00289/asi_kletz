from __future__ import annotations

import gc
import re
import threading
import time
import tkinter as tk
from types import SimpleNamespace

import pytest

from asi_kletz.commands import Result, default_command_factory
from asi_kletz.schema import FieldSpec, FieldType
from tests.conftest import PLAN, REPO_ROOT

# the registered screens, in navigation order: the list is the design, not a cap
SCREENS = ["dashboard", "jira_live", "safety_plan", "safety_plan_matrix", "sprint_board", "tracker", "holidays",
           "transfer"]
TITLES = ["Dashboard", "JIRA Live Data", "Safety Plan", "Safety Plan Matrix", "Sprint Board", "Weekly Status",
          "Holidays", "Export / Import"]
# the identity column of the Safety Plan table: frozen on the left since 0.7.2; since 0.8.4 the three identity
# fields are one stacked column; since 0.9.0 ``id`` and ``order`` are no columns at all (docs/hidden-identity-plan.md)
FROZEN_PLAN = ["plan"]
STACKED_PLAN = ["pdp_phase", "lifecycle_phase", "deliverable"]  # on the tree, hidden: the stack shows them
NEVER_COLUMNS = ("id", "order", "uid")  # no table on any screen has a column so named
STACK_ROWS = 9  # the three seeded deliverables under three PDP phases and three lifecycle phases


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        del root
        gc.collect()  # delete the Tcl interpreter now, not while the next one is initialising
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")


@pytest.fixture
def window(seeded):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()  # same reason: a lingering interpreter torn down mid-startup breaks the next Tk()


def _nav_entries(window) -> list[str]:
    return [window.nav.get(i).strip() for i in range(window.nav.size())]


def _fonts(tree):
    """The body and heading fonts of a table, looked up the way ``fit_columns`` looks them up."""
    import tkinter.font as tkfont
    from tkinter import ttk

    style = ttk.Style(tree)
    body = tkfont.Font(tree, font=style.lookup("Treeview", "font") or "TkDefaultFont")
    head = tkfont.Font(tree, font=style.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    return body, head


def _widest(tree, column, extra=()) -> int:
    """The widest text of a column in pixels: its heading, its cells and ``extra``, in the real fonts."""
    body, head = _fonts(tree)
    texts = [str(tree.set(iid, column)) for iid in tree.get_children("")] + [str(t) for t in extra]
    return max([head.measure(str(tree.heading(column, "text"))), *(body.measure(t) for t in texts)])


def _assert_fitted(tree, extra=None, padding=24, max_width=600) -> None:
    """Every column at least as wide as its widest text plus the padding, within the cap."""
    assert list(tree["columns"])
    for column in tree["columns"]:
        want = min(_widest(tree, column, (extra or {}).get(column, ())) + padding, max_width)
        width = int(tree.column(column, "width"))
        assert want <= width <= max_width, (column, width, want)


def test_registered_screens_in_order(window):
    assert [k for k, _ in window.factory.items()] == SCREENS
    assert [t for _, t in window.factory.items()] == TITLES
    assert _nav_entries(window) == [t.upper() for t in TITLES]  # one entry per registered screen, in order
    assert window.factory.title("jira_live") == "JIRA Live Data" and window.nav.get(1).strip() == "JIRA LIVE DATA"
    menubar = window.nametowidget(window.cget("menu"))
    tops = [i for i in range(menubar.index("end") + 1) if menubar.type(i) == "cascade"]
    view_menu = window.nametowidget(menubar.entrycget(tops[1], "menu"))
    view_labels = [view_menu.entrycget(i, "label") for i in range(view_menu.index("end") + 1)
                   if view_menu.type(i) == "command"]
    assert view_labels == TITLES and view_labels[1] == "JIRA Live Data"


def test_navigation_and_dashboard(window):
    assert window.current.key == "dashboard"
    dash = window.current
    assert dash._tile_vars["total"].get() == "3"
    assert dash._tile_vars["Done"].get() == "1" and dash._tile_vars["Ongoing"].get() == "1"
    assert dash._tile_vars["Blocked"].get() == "0"
    table = dash.phase_table
    phases = {table.set(i, "lifecycle_phase"): table.set(i, "deliverables") for i in table.get_children()}
    assert phases["1. Concept Development"] == "1" and phases["10. Decommissioning"] == "0"
    opened = [dash.open_table.set(i, "deliverable") for i in dash.open_table.get_children()]
    assert opened == ["Hazard Analysis and Risk Assessment", "Functional Safety Concept"]  # plan order, no column
    assert tuple(dash.open_table["columns"]) == ("deliverable", "status", "deadline")
    assert tuple(dash.audit["columns"]) == ("ts", "actor", "action", "entity", "entity_id")  # the trace stays
    assert len(dash.audit.get_children()) == 3
    window.show("safety_plan")
    assert window.current_key == "safety_plan" and window.title().endswith("Safety Plan")


def test_entity_screen_create_update_delete(window, seeded):
    screen = window.show("safety_plan")
    assert len(screen.tree.get_children()) == STACK_ROWS
    screen.new()
    screen.widgets["deliverable"].set("line one\nline two")
    screen.widgets["order"].set("9")
    screen.widgets["status"].set("Blocked")
    screen.save()
    assert screen.selected_id is not None
    assert seeded.execute("count", entity=PLAN).data["count"] == 4
    row = seeded.execute("get", entity=PLAN, id=screen.selected_id).data
    assert row["order"] == 9 and row["deliverable"] == "line one\nline two" and row["status"] == "Blocked"

    screen.widgets["deadline"].set("edited")
    screen.save()
    assert seeded.execute("get", entity=PLAN, id=screen.selected_id).data["deadline"] == "edited"
    assert seeded.storage.audit_tail(1)[0]["actor"] == "gui"

    screen.delete()
    assert seeded.execute("count", entity=PLAN).data["count"] == 3
    assert screen.selected_id is None and "Deleted" in window.status_text()


def test_entity_screen_validation_shows_error(window, seeded):
    screen = window.show("safety_plan")
    screen.new()
    screen.widgets["order"].set("banana")
    screen.save()
    assert window.status_text().startswith("Error:") and "required" in window.status_text()
    assert seeded.execute("count", entity=PLAN).data["count"] == 3


def test_search_sort_and_select(window):
    screen = window.show("safety_plan")
    screen.search_var.set("hazard")
    assert [iid for iid, _ in _rows(screen.tree)] == ["pdp:2", "phase:2:2. HARA / Risk Assessment", "2"]
    screen.search_var.set("")
    screen.sort_by("order", desc=True)
    first = int(next(iid for iid in screen.tree.get_children() if iid.isdigit()))
    assert screen.by_id[first]["order"] == 3
    screen.select(first)
    assert screen.widgets["deliverable"].get() == "Functional Safety Concept"
    screen.duplicate()
    assert screen.selected_id is None and screen.widgets["order"].get() is None


def test_safety_plan_form_has_groups(window):
    screen = window.show("safety_plan")
    assert "loc_dms" in screen.widgets and "reviewer_pat" in screen.widgets
    assert "loc_dms" in screen.columns and "reviewer_pat" in screen.columns  # every source column is in the table
    screen.select(1)
    assert screen.widgets["loc_dms"].get() is True and screen.widgets["loc_jama"].get() is False


def test_safety_plan_table_shows_every_column(window, seeded):
    from asi_kletz.gui import entity_screen

    screen = window.show("safety_plan")
    schema = seeded.registry.get(PLAN)
    assert screen.columns == [f.name for f in schema.visible_fields if f.name != "order"] and len(screen.columns) == 62
    assert list(screen.tree["columns"]) == [*screen.columns, "plan"]  # the stacked column rides along
    assert screen.columns[:3] == ["pdp_phase", "lifecycle_phase", "deliverable"] and "uid" not in screen.columns
    assert screen.tree.heading("loc_dms", "text") == "DMS"
    long_author = "author_electronics_engineer_mechanical_and_electrical"
    assert screen.tree.heading(long_author, "text") == "Electronics Engineer (Mechanical and Electrical)"
    assert screen.tree.heading("status", "text") == schema.field("status").header
    assert screen.tree.heading("status", "text").startswith("Status (Pending/")
    body, head = _fonts(screen.tree)  # since 0.7.1 a column is as wide as its widest text, heading included
    assert int(screen.tree.column("loc_dms", "width")) == head.measure("DMS") + 24  # the heading, not 36 px
    assert str(screen.tree.column("loc_dms", "anchor")) == "center" and screen.tree.column("loc_dms", "stretch") == 0
    widest_deliverable = body.measure("Hazard Analysis and Risk Assessment") + 24
    assert int(screen.tree.column("deliverable", "width")) == widest_deliverable
    assert screen.tree.column("deliverable", "stretch") == 0  # fitted columns never stretch: Tk would shrink them
    assert screen.tree.set("1", "loc_dms") == "✓" and screen.tree.set("1", "loc_jama") == ""
    assert screen.tree.set("2", "loc_jama") == "✓"
    assert screen.tree.set("1", "reviewer_tech_lead_functional_safety") == "✓"
    assert screen.tree.set("1", "author_tech_lead_functional_safety") == ""  # the duplicate header maps to two fields
    screen.sort_by("loc_dms", desc=True)
    assert next(i for i in screen.tree.get_children() if i.isdigit()) == "1"  # the first deliverable row
    assert "Sorted by DMS" in window.status_text()
    assert not hasattr(entity_screen, "MAX_FLAG_COLUMNS") and not hasattr(entity_screen, "FLAG_WIDTH")


def test_columns_selector_narrows_the_flags(window, seeded):
    from asi_kletz.prefs import read_prefs

    screen = window.show("safety_plan")
    assert screen.columns_var.get() == "All"
    assert str(screen.columns_box.cget("state")) == "readonly"
    groups = ["Location", "Reference", "Author", "Verification", "Reviewer"]
    assert list(screen.columns_box.cget("values")) == ["All", *groups]
    # since 0.7.2 the frozen identity columns live in the left tree: the right one never displays them
    unfrozen = tuple(c for c in screen.columns if c not in FROZEN_PLAN and c not in STACKED_PLAN)
    assert screen.tree["displaycolumns"] == unfrozen and len(unfrozen) == 59  # 62 columns minus the three stacked

    screen.set_columns("Location")
    assert list(screen.tree["displaycolumns"]) == [
        "work_product_location", "loc_dms", "loc_jama", "loc_sharepoint", "work_product_reference",
        "author", "gate_reviewer", "deadline", "status",
    ]
    assert len(screen.tree["columns"]) == 63  # nothing rebuilt
    assert screen.tree.set("1", "reviewer_pat") == ""  # still readable while hidden

    screen.set_columns("Reviewer")
    shown = list(screen.tree["displaycolumns"])
    assert len(shown) == 13 and shown[-3:] == ["reviewer_technical_training_team", "deadline", "status"]
    assert not any(c.startswith("loc_") for c in shown)

    screen.select(2)
    seeded.execute("update", entity=PLAN, id=2, data={"deadline": "x"}, actor="agent")
    deadline = time.time() + 2
    while screen.tree.set("2", "deadline") != "x" and time.time() < deadline:
        window.update()
        time.sleep(0.02)
    assert len(screen.tree.get_children()) == STACK_ROWS and screen.tree.set("2", "deadline") == "x"
    assert list(screen.tree["displaycolumns"]) == shown and screen.selected_id == 2
    window.show("dashboard")
    assert window.show("safety_plan") is screen and screen.columns_var.get() == "Reviewer"

    screen.set_columns("All")
    assert screen.tree["displaycolumns"] == unfrozen and screen.columns_var.get() == "All"

    screen.set_columns("Author")
    assert window.pick_theme("pink-noir").ok
    rebuilt = window.show("safety_plan")
    assert rebuilt is not screen and rebuilt.columns_var.get() == "All"  # session memory, not a latch
    assert rebuilt.tree["displaycolumns"] == unfrozen
    assert "columns" not in read_prefs()


def test_safety_plan_table_scrolls_both_ways(window):
    from tkinter import ttk

    screen = window.show("safety_plan")
    assert isinstance(screen.xbar, ttk.Scrollbar) and str(screen.xbar.cget("orient")) == "horizontal"
    assert screen.xbar is screen.pane.xbar and screen.ybar is screen.pane.ybar  # the pane's bars (0.7.2)
    assert screen.xbar.grid_info()["row"] == 1 and screen.xbar.grid_info()["column"] == 0  # past the sash
    assert isinstance(screen.ybar, ttk.Scrollbar) and str(screen.ybar.cget("orient")) == "vertical"
    assert screen.ybar.grid_info()["row"] == 0 and screen.ybar.grid_info()["column"] == 1  # outside the split (0.7.3)
    assert screen.pane.split.panes() == (str(screen.pane.left), str(screen.tree))  # the two trees are its panes
    assert screen.pane.left.cget("xscrollcommand") == ""  # the frozen tree never scrolls sideways
    assert screen.tree.cget("xscrollcommand") and screen.tree.cget("yscrollcommand")
    window.update_idletasks()  # the window is withdrawn, so requested sizes are what Tk can report
    width = int(window.geometry().split("x")[0])
    assert screen.tree.winfo_reqwidth() > width  # the tree is wider than the window: the bar is the way across
    assert width <= 1280  # and the window did not grow to fit it
    paned = screen.form.master.master
    assert isinstance(paned, ttk.PanedWindow) and len(paned.panes()) == 2  # the form keeps its pane below


def test_matrix_toggle_and_group_switch(window, seeded):
    screen = window.show("safety_plan_matrix")
    assert screen.group_var.get() == "all"  # every flag at once, each column as wide as its heading
    flags = [f.name for f in screen.schema.fields if f.is_flag]
    assert list(screen.tree["columns"]) == ["plan", *flags]
    _, head = _fonts(screen.tree)
    assert int(screen.tree.column("loc_jama", "width")) == head.measure("JAMA") + 24
    assert int(screen.tree.column("reviewer_pat", "width")) == head.measure("PAT") + 24
    result = screen.toggle(1, "loc_jama")
    assert result.ok
    assert seeded.execute("get", entity=PLAN, id=1).data["loc_jama"] is True
    assert screen.tree.set("1", "loc_jama") == "✓"
    screen.set_group("reviewer")
    assert "reviewer_pat" in screen.tree["columns"] and "loc_jama" not in screen.tree["columns"]
    assert int(screen.tree.column("reviewer_pat", "width")) == head.measure("PAT") + 24  # one group: fitted again
    assert screen.tree.set("1", "reviewer_tech_lead_functional_safety") == "✓"


def test_event_bus_refreshes_open_screen(window, seeded):
    screen = window.show("safety_plan")
    seeded.execute("create", entity=PLAN, data={"deliverable": "from the API"}, actor="agent")
    deadline = time.time() + 2
    while len(screen.tree.get_children()) < STACK_ROWS + 3 and time.time() < deadline:
        window.update()
        time.sleep(0.02)
    # the new row sits under its own "(no PDP phase)" and "(no lifecycle phase)" headings
    assert len(screen.tree.get_children()) == STACK_ROWS + 3


def test_transfer_screen_round_trip(window, tmp_path, seeded):
    screen = window.show("transfer")
    exported = screen.export_workbook(tmp_path / "view.xlsx")
    assert exported.ok and (tmp_path / "view.xlsx").is_file()
    dumped = screen.dump_json(tmp_path / "dump.json")
    assert dumped.ok
    assert screen.load_json(tmp_path / "dump.json", mode="merge").ok
    assert screen.import_workbook(tmp_path / "view.xlsx", mode="replace").ok
    assert seeded.execute("count", entity=PLAN).data["count"] == 3
    assert "[ok] import" in screen.log.get("1.0", "end")
    assert not screen.dump_json().ok  # no dialog when not interactive


def test_widget_factory_round_trips(window, seeded):
    from asi_kletz.gui.widgets import WidgetFactory

    factory = WidgetFactory(seeded.lookups)
    plan = seeded.registry.get(PLAN)
    samples = {
        "work_product_location": ("hello", "hello"), "deliverable": ("a\nb", "a\nb"),
        "order": ("5", "5"), "status": ("Done", "Done"),
    }
    for field, (given, expected) in samples.items():
        widget = factory.create(window, plan.field(field))
        widget.set(given)
        assert widget.get() == expected
        widget.clear()
        assert widget.get() is None
    flag = factory.create(window, plan.field("loc_dms"))
    flag.set(1)
    assert flag.get() is True
    url = factory.create(window, FieldSpec("link", FieldType.URL))
    url.set("https://example.invalid")
    assert url.get() == "https://example.invalid"
    date = factory.create(window, FieldSpec("when", FieldType.DATE))
    date.set("2026-01-02")
    assert date.get() == "2026-01-02"
    enum = factory.create(window, plan.field("status"))
    assert list(enum.combo["values"]) == list(seeded.lookups["plan_status"])
    assert plan.field("status").type is FieldType.ENUM


def test_gui_verb_is_registered():
    assert "gui" in default_command_factory.verbs()


def test_cyan_neon_is_default_and_paints_ttk(window):
    from tkinter import ttk

    from asi_kletz.gui.theme import GridTheme, ThemeFactory

    assert isinstance(window.theme, GridTheme) and window.theme.key == "cyan-neon"
    style = ttk.Style(window)
    assert style.theme_use() == "clam"
    assert style.lookup("TButton", "foreground") == window.theme.palette.primary == "#1ad9ff"
    assert style.lookup("Treeview.Heading", "background") == window.theme.palette.panel
    assert set(ThemeFactory.keys()) >= {"tron", "plain", "amber-neon", "pink-noir"}
    assert [k for k, _ in window.factory.items()] == SCREENS  # the picker is a control, not a screen
    screen = window.show("safety_plan")
    first = screen.tree.get_children()[0]
    assert screen.tree.item(first, "tags") == ("pdp", "even")  # a PDP phase heading, striped


def test_plain_theme_and_unknown_theme(seeded):
    from asi_kletz.errors import NotFound
    from asi_kletz.gui.main_window import MainWindow
    from asi_kletz.gui.theme import ThemeFactory

    with pytest.raises(NotFound):
        ThemeFactory.create("neon-pink")
    win = MainWindow(seeded, interactive=False, theme="plain")
    win.withdraw()
    try:
        assert win.theme.key == "plain"
        assert win.show("dashboard").key == "dashboard"
    finally:
        win.close()
        del win
        gc.collect()


def test_gui_verb_accepts_theme_and_no_server():
    command = default_command_factory.get("gui")
    assert [a.name for a in command.arguments] == ["theme", "no-server"]
    assert command.arguments[1].type == "bool" and command.arguments[1].default is False


# -- the status bar: online indicator with the server's port, the theme badge --------------------
def test_theme_badge_follows_the_theme(window):
    from tkinter import ttk

    from asi_kletz.gui.main_window import badge_text

    assert badge_text("Plain (native)") == "PLAIN" and badge_text("Amber Neon") == "AMBER NEON"
    assert window.badge_var.get() == "CYAN NEON"
    assert str(window.badge_label.cget("textvariable")) == str(window.badge_var)
    assert str(window.badge_label.cget("style")) == "StatusMuted.TLabel"
    assert window.theme.mono[0] in str(window.badge_label.cget("font"))  # the mono face, as the status line
    slaves = window.status_bar.pack_slaves()
    assert slaves[:3] == [window.online_label, window.badge_label, window.status_label]
    assert window.pick_theme("plain").ok
    assert window.badge_var.get() == "PLAIN" and str(window.badge_label.cget("style")) == "StatusMuted.TLabel"
    assert window.pick_theme("gold-day").ok
    assert window.badge_var.get() == "GOLD DAY"
    assert window.status_bar.pack_slaves()[:3] == [window.online_label, window.badge_label, window.status_label]
    assert isinstance(window.online_label, ttk.Label)


def test_online_indicator_shows_the_port_and_the_server_survives_a_repaint(window):
    import json
    import threading

    from asi_kletz.automation.session import session_path

    server = window.server
    assert server is not None and server.running and window.online_var.get() == f"◉ ONLINE :{server.port}"
    assert json.loads(session_path().read_text(encoding="utf-8"))["port"] == server.port
    assert str(window.online_label.cget("textvariable")) == str(window.online_var)
    assert window.pick_theme("violet-dusk").ok
    assert window.server is server and server.running and window.online_var.get() == f"◉ ONLINE :{server.port}"
    answered: dict = {}

    def post():
        answered["value"] = server.on_main(lambda: window.current_key, timeout=5)

    thread = threading.Thread(target=post, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while thread.is_alive() and time.time() < deadline:
        window.update()
        time.sleep(0.01)
    assert answered == {"value": "dashboard"}  # the pump is alive after the rebuild
    assert [k for k, _ in window.factory.items()] == SCREENS


def test_transfer_screen_builds_diagrams_and_documents(window, tmp_path, seeded):
    screen = window.show("transfer")
    assert [k for k, _ in window.factory.items()] == SCREENS  # generation lives inside Export / Import
    assert [s["key"] for s in screen.diagram_specs] == ["lifecycle_overview", "phase_flow", "status_board", "pdp_map"]
    assert [s["key"] for s in screen.document_specs] == ["safety_plan", "status_report", "phase_checklist"]
    assert screen.out_var.get() == seeded.out_dir
    screen.select_diagram("lifecycle_overview")
    assert not screen.phase_enabled()
    result = screen.build_diagram(out=tmp_path / "views")
    assert result.ok, result.errors
    assert "[ok] diagram" in screen.log.get("1.0", "end")
    assert result.data["primary"].endswith("lifecycle_overview.png")
    assert (tmp_path / "views" / "lifecycle_overview.png").is_file()
    assert screen.last_primary == result.data["primary"]
    screen.select_diagram("phase_flow")
    assert screen.phase_enabled() and screen.phase_var.get() == "1. Concept Development"
    result = screen.build_diagram(phase="2. HARA / Risk Assessment", out=tmp_path / "views")
    assert result.ok and result.data["params"] == {"phase": "2"} and result.data["primary"].endswith("phase_flow_2.png")
    screen.select_diagram("status_board")
    assert not screen.phase_enabled()
    result = screen.build_document("phase_checklist", out=tmp_path / "views")
    assert result.ok, result.errors
    assert result.data["primary"].endswith("phase_checklist.pdf") and screen.last_primary == result.data["primary"]
    assert "[ok] document" in screen.log.get("1.0", "end")
    assert screen.open_primary() is False and "Would open" in window.status_text()  # never launches a program in tests
    assert screen.open_folder() is False
    assert seeded.storage.audit_tail(1)[0] | {"actor": "gui", "action": "generate"} == seeded.storage.audit_tail(1)[0]


def test_file_menu_builds_the_safety_plan(window, tmp_path, seeded):
    window.show("dashboard")
    screen = window.show("transfer")
    screen.out_var.set(str(tmp_path / "plan"))
    result = window.build_safety_plan()
    assert result.ok, result.errors
    assert window.current_key == "transfer" and result.data["name"] == "safety_plan"
    assert (tmp_path / "plan" / "safety_plan.pdf").is_file()
    assert (tmp_path / "plan" / "figures" / "lifecycle_overview.png").is_file()
    log = screen.log.get("1.0", "end")
    assert "[ok] document" in log and "kletz.toml has no doc_id" in log


# -- the theme picker ------------------------------------------------------------
def _themes_window(seeded, **kwargs):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False, **kwargs)
    win.withdraw()
    return win


def _close(win) -> None:
    win.close()
    del win
    gc.collect()


def test_theme_picker_lists_the_catalog_then_plain(window):
    from asi_kletz.gui.palettes import CATALOG

    assert window.theme_var.get() == "Cyan Neon"
    assert str(window.theme_box.cget("state")) == "readonly"
    assert list(window.theme_box.cget("values")) == [e.title for e in CATALOG.values()] + ["Plain (native)"]
    assert _nav_entries(window) == [t.upper() for t in TITLES]


def test_pick_theme_repaints_and_latches(window, seeded, tmp_path):
    from tkinter import ttk

    from asi_kletz.prefs import read_prefs

    window.show("safety_plan_matrix")
    result = window.pick_theme("pink-noir")
    assert result.ok, result.errors
    assert window.theme.key == "pink-noir" and window.theme_var.get() == "Pink Noir"
    style = ttk.Style(window)
    assert style.lookup("TButton", "foreground") == "#ec1380"
    assert read_prefs()["theme"] == "pink-noir"
    assert window.current_key == "safety_plan_matrix" and window.current.key == "safety_plan_matrix"
    assert window.status_text() == "Theme: Pink Noir"
    assert window.nav.cget("background") == window.theme.palette.panel
    assert _nav_entries(window) == [t.upper() for t in TITLES] and [k for k, _ in window.factory.items()] == SCREENS
    assert seeded.events.last(1)[0]["topic"] == "theme.changed"


def test_pick_plain_then_back_to_a_grid_palette(window):
    from tkinter import ttk

    from asi_kletz.gui.theme import native_look

    native = native_look(window).ttk_theme
    assert window.pick_theme("plain").ok
    style = ttk.Style(window)
    assert window.theme.key == "plain" and style.theme_use() == native and native != "clam"
    assert window.option_get("background", "Listbox") == ""
    assert window.nav.option_get("background", "Background") == ""  # the option database was cleared
    assert window.theme_var.get() == "Plain (native)"
    assert window.pick_theme("gold-day").ok
    assert style.theme_use() == "clam" and window.theme.key == "gold-day"
    assert window.nav.option_get("background", "Background") == window.theme.palette.panel
    assert window.nav.cget("background") == window.theme.palette.panel
    assert ("selected", window.theme.palette.text) in style.map("Treeview", "foreground")
    assert window.theme.palette.text != "#ffffff"


def test_pick_unknown_theme_leaves_the_window_as_it_was(window):
    result = window.pick_theme("sepia")
    assert not result.ok and window.theme.key == "cyan-neon" and window.theme_var.get() == "Cyan Neon"
    assert window.status_text().startswith("Error:")


def test_latched_theme_opens_on_launch_and_explicit_theme_does_not_write_it(seeded):
    from asi_kletz.prefs import prefs_path, write_prefs

    write_prefs(theme="violet-dusk")
    before = prefs_path().read_text(encoding="utf-8")
    win = _themes_window(seeded)
    try:
        assert win.theme.key == "violet-dusk" and win.theme_var.get() == "Violet Dusk"
    finally:
        _close(win)
    win = _themes_window(seeded, theme="plain")
    try:
        assert win.theme.key == "plain" and win.theme_var.get() == "Plain (native)"
    finally:
        _close(win)
    assert prefs_path().read_text(encoding="utf-8") == before


def test_unknown_latched_theme_falls_back_with_a_warning(seeded):
    from asi_kletz.prefs import write_prefs

    write_prefs(theme="sepia")
    win = _themes_window(seeded)
    try:
        assert win.theme.key == "cyan-neon"
        assert win.status_text().startswith("Warning:") and "sepia" in win.status_text()
    finally:
        _close(win)


def test_theme_verb_from_the_api_repaints_an_open_window(window, seeded):
    result = seeded.execute("theme", key="green-neon", actor="agent")
    assert result.ok and result.data["latched"] == "green-neon"
    deadline = time.time() + 2
    while window.theme.key != "green-neon" and time.time() < deadline:
        window.update()
        time.sleep(0.02)
    assert window.theme.key == "green-neon" and window.theme_var.get() == "Green Neon"
    event = seeded.events.last(1)[0]
    assert event["topic"] == "theme.changed" and event["theme"] == "green-neon" and event["actor"] == "agent"


def test_repaint_keeps_the_transfer_screen_working(window, tmp_path):
    window.show("transfer")
    assert window.pick_theme("blue-dusk").ok
    assert window.current_key == "transfer"
    screen = window.current
    screen.select_diagram("lifecycle_overview")
    result = screen.build_diagram(out=tmp_path / "views")
    assert result.ok, result.errors
    assert (tmp_path / "views" / "lifecycle_overview.png").is_file()
    assert "[ok] diagram" in screen.log.get("1.0", "end")


def test_view_menu_has_a_theme_cascade_and_file_menu_is_unchanged(window):
    menubar = window.nametowidget(window.cget("menu"))
    tops = [i for i in range(menubar.index("end") + 1) if menubar.type(i) == "cascade"]  # index 0 may be a tearoff
    assert [menubar.entrycget(i, "label") for i in tops] == ["File", "View", "Help"]
    file_menu = window.nametowidget(menubar.entrycget(tops[0], "menu"))
    file_labels = [file_menu.entrycget(i, "label") for i in range(file_menu.index("end") + 1)
                   if file_menu.type(i) == "command"]
    assert file_labels == [
        "Export workbook", "Import workbook…", "Build Safety Plan document", "Build current week (tracker)",
        "Build tracker history", "Quit",
    ]
    view_menu = window.nametowidget(menubar.entrycget(tops[1], "menu"))
    last = view_menu.index("end")
    assert view_menu.type(last) == "cascade" and view_menu.entrycget(last, "label") == "Theme"
    theme_menu = window.nametowidget(view_menu.entrycget(last, "menu"))
    cascades = [theme_menu.entrycget(i, "label") for i in range(theme_menu.index("end") + 1)
                if theme_menu.type(i) == "cascade"]
    assert cascades == ["Cyan", "Blue", "Violet", "Pink", "Red", "Amber", "Gold", "Green"]
    plain = theme_menu.index("end")
    assert theme_menu.type(plain) == "radiobutton" and theme_menu.entrycget(plain, "label") == "Plain (native)"
    pink = window.nametowidget(theme_menu.entrycget(3, "menu"))
    assert [pink.entrycget(i, "label") for i in range(4)] == ["Noir", "Neon", "Dusk", "Day"]
    assert str(pink.entrycget(1, "variable")) == str(window.theme_var)
    pink.invoke(0)
    assert window.theme.key == "pink-noir" and window.theme_var.get() == "Pink Noir"


def test_fit_geometry_keeps_the_full_size_only_when_the_screen_holds_it():
    from asi_kletz.gui.main_window import DEFAULT_SIZE, fit_geometry

    assert DEFAULT_SIZE == (1280, 800)
    assert fit_geometry(1280, 800, 1920, 1080) == ("1280x800", False)
    assert fit_geometry(1280, 800, 1280, 800) == ("1264x700+0+0", True)  # a 1280x800 laptop: maximise
    assert fit_geometry(1280, 800, 1366, 768) == ("1280x668+0+0", True)
    assert fit_geometry(1280, 800, 1300, 900) == ("1280x800", False)


def test_window_opens_zoomed_or_at_full_size(window):
    geometry, zoom = fit_geometry_for(window)
    if zoom:
        assert window.state() in ("zoomed", "withdrawn")  # the fixture withdraws it
    else:
        assert window.winfo_reqwidth() <= 1280


def fit_geometry_for(window):
    from asi_kletz.gui.main_window import DEFAULT_SIZE, fit_geometry

    return fit_geometry(*DEFAULT_SIZE, window.winfo_screenwidth(), window.winfo_screenheight())


# -- the JIRA Live Data screen ----------------------------------------------------------
LIVE_JQL = (
    "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser())"
    " ORDER BY updated DESC"
)


def _issue(key, issue_type, summary, status, category, priority, assignee, **extra):
    row = {
        "key": key, "issue_type": issue_type, "summary": summary, "status": status, "status_category": category,
        "resolution": "Done" if category == "done" else None, "priority": priority, "assignee": assignee,
        "reporter": "Bo", "labels": [], "components": [], "parent_key": None,
        "created": "2026-10-01T09:00:00.000-0600", "updated": "2026-10-20T09:00:00.000-0600",
        "due": "2026-11-20", "url": f"https://asirobots.atlassian.net/browse/{key}",
    }
    row.update(extra)
    return row


# five hand-written rows: two statuses among done rows, all three categories, two types, two priorities,
# two assignees plus one null, one null due date, labels, a parent; keys that sort numerically, not lexically
SAMPLE = {
    "jql": LIVE_JQL, "fetched_at": "2026-10-27T18:04:11+00:00", "count": 5, "truncated": False,
    "issues": [
        _issue("HWL-9", "Story", "Brake test plan", "Done", "done", "High", "Ana",
               labels=["safety", "VAT"], parent_key="HWL-1", due="2026-11-01"),
        _issue("HWL-10", "Bug", "E-stop guard missing", "In Progress", "indeterminate", "Medium", "Cy", due=None),
        _issue("HWL-100", "Story", "Loss scenarios", "To Do", "new", "High", "Ana", due="2026-12-01"),
        _issue("HWL-2", "Bug", "Old brake issue", "Done", "done", "Medium", "Cy", due="2026-10-15"),
        _issue("HWL-33", "Story", "Hazard list review", "To Do", "new", "High", None, due="2026-11-20"),
    ],
}
COMMENTS = {
    "key": "HWL-9", "summary": "Brake test plan", "url": "https://asirobots.atlassian.net/browse/HWL-9",
    "status": "Done", "fetched_at": "2026-10-27T18:04:11+00:00", "count": 3,
    "comments": [  # newest first, as the verb sends them; the first one edited
        {"id": "c3", "author": "Ana", "created": "2026-10-26T15:02:11.000-0600",
         "updated": "2026-10-26T15:40:00.000-0600", "body": "Reviewed the loss list; L3 needs a boundary note."},
        {"id": "c2", "author": "Bo", "created": "2026-10-24T10:00:00.000-0600",
         "updated": "2026-10-24T10:00:00.000-0600", "body": "Draft attached.\nSee the PDF."},
        {"id": "c1", "author": "Cy", "created": "2026-10-21T09:12:40.000-0600",
         "updated": "2026-10-21T09:12:40.000-0600", "body": "Opened."},
    ],
}
NO_SESSION = "no Atlassian session for this account; run `asi-hopper auth login` once"


class FakeRun:
    """A stand-in for ``window.execute_quiet``: answers ``jira`` from SAMPLE / COMMENTS or fails.

    It runs where the real one runs, on the worker thread, and like it never touches Tk. Any other
    verb goes to the real Brain (``pick_theme`` runs ``theme`` through the same door). It counts
    calls per action, records the thread of each ``jira`` call, sets ``started`` on entry and waits
    on ``gate`` when a test sets one, so a test can look at a fetch in flight.
    """

    def __init__(self, window) -> None:
        self.window = window
        self.calls: dict[str, int] = {"live": 0, "comments": 0}
        self.args: list[dict] = []
        self.threads: list[threading.Thread] = []
        self.started = threading.Event()
        self.gate: threading.Event | None = None
        self.failure: str | None = None
        self.comments: dict = COMMENTS

    def __call__(self, verb, **args) -> Result:
        if verb != "jira":
            return self.window.brain.execute(verb, args, actor="gui")
        self.calls[args["action"]] += 1
        self.args.append(args)
        self.threads.append(threading.current_thread())
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(5.0), "the test never opened the gate"
        if self.failure:
            return Result.failure(self.failure, verb=verb)
        if args["action"] == "live":
            return Result.success(SAMPLE, verb=verb)
        return Result.success(self.comments, verb=verb)


@pytest.fixture
def live(window, monkeypatch):
    fake = FakeRun(window)
    monkeypatch.setattr(window, "execute_quiet", fake)
    return fake


def _keys(screen) -> list[str]:
    return list(screen.tree.get_children())


def _fetched(window):
    """The live screen shown and filled by one Refresh: the window never fetches on its own."""
    screen = window.show("jira_live")
    assert screen.fetch() and screen.wait_fetch().ok
    return screen


def _comments(window, key):
    """``open_comments`` with its fetch applied."""
    win = window.open_comments(key)
    win.wait_fetch()
    return win


def _settle(window, live, rounds=10) -> None:
    """Let every worker finish, then pump the loop a while: whatever a late Result would do, happens now."""
    for thread in live.threads:
        thread.join(5.0)
        assert not thread.is_alive()
    for _ in range(rounds):
        window.update()
        time.sleep(0.02)


def _callback_errors(window, monkeypatch) -> list:
    """Tk's callback-error hook replaced by a list: an `after` firing into a dead widget would land here."""
    errors: list = []
    monkeypatch.setattr(window, "report_callback_exception", lambda *exc: errors.append(exc))
    return errors


def test_live_screen_does_not_connect_on_first_show(window, live, seeded):
    assert "jira_live_autofetch" not in seeded.config  # the default is in play, not a key
    screen = window.show("jira_live")
    assert live.calls == {"live": 0, "comments": 0} and window.jira_live is None and not screen.fetching
    assert screen.status_var.get() == "No fetch yet · press Refresh" and _keys(screen) == []
    assert "disabled" not in screen.refresh_button.state() and screen.count_var.get() == "0 of 0 issues"
    window.show("dashboard")
    assert window.show("jira_live") is screen and live.calls["live"] == 0
    assert window.pick_theme("pink-noir").ok and live.calls["live"] == 0  # a rebuild does not connect either
    assert window.current.status_var.get() == "No fetch yet · press Refresh"
    seeded.config["jira_live_autofetch"] = "true"  # not a boolean: load_config drops it, the screen ignores it
    try:
        window.show("dashboard")
        window.show("jira_live")
        assert live.calls["live"] == 0
    finally:
        del seeded.config["jira_live_autofetch"]


def test_live_screen_fetches_once_on_first_show_when_autofetch_is_on(window, live, seeded, monkeypatch):
    monkeypatch.setitem(seeded.config, "jira_live_autofetch", True)
    screen = window.show("jira_live")
    assert screen.wait_fetch().ok  # the fetch started on show; a fast worker may be applied already
    assert live.calls == {"live": 1, "comments": 0} and live.args[0] == {"action": "live"}
    assert window.jira_live.data is SAMPLE and len(_keys(screen)) == 5
    assert re.match(r"^5 issues · fetched \d\d:\d\d · project = HWL", screen.status_var.get())
    assert screen.count_var.get() == "5 of 5 issues" and window.status_text() == "Jira: 5 issues fetched"
    window.show("dashboard")
    assert window.show("jira_live") is screen and live.calls["live"] == 1  # already fetched this session
    assert _keys(screen) == ["HWL-9", "HWL-10", "HWL-100", "HWL-2", "HWL-33"]  # server order
    assert seeded.execute("count", entity=PLAN).data["count"] == 3


def test_live_screen_refresh_and_a_failure_after_a_success(window, live):
    screen = _fetched(window)
    assert live.calls["live"] == 1 and len(_keys(screen)) == 5
    live.failure = NO_SESSION
    assert screen.fetch()
    result = screen.wait_fetch()
    assert not result.ok and live.calls["live"] == 2
    assert len(_keys(screen)) == 5 and window.jira_live.ok  # the old rows stay
    assert window.status_text().startswith("Error: no Atlassian session")
    assert re.match(r"^5 issues · fetched", screen.status_var.get())  # the label describes the rows shown


def test_live_screen_first_fetch_fails_offline(seeded, monkeypatch):
    monkeypatch.setitem(seeded.config, "jira_live_autofetch", True)
    win = _themes_window(seeded)
    try:
        fake = FakeRun(win)
        fake.failure = NO_SESSION
        monkeypatch.setattr(win, "execute_quiet", fake)
        screen = win.show("jira_live")
        assert not screen.wait_fetch().ok
        assert _keys(screen) == [] and screen.status_var.get().startswith("Offline: no Atlassian session")
        assert win.jira_live is not None and not win.jira_live.ok
        assert win.status_text().startswith("Error:")
        win.show("dashboard")
        win.show("jira_live")
        assert fake.calls["live"] == 1 and not screen.fetching  # a failed first fetch is not retried on show
    finally:
        _close(win)


def test_live_screen_fetch_runs_off_the_tk_thread_and_applies_on_it(window, live, monkeypatch):
    screen = window.show("jira_live")
    painted: list[threading.Thread] = []
    repaint = screen.refresh
    monkeypatch.setattr(screen, "refresh", lambda: (painted.append(threading.current_thread()), repaint()))
    live.gate = threading.Event()
    assert screen.fetch() and screen.fetching
    assert "disabled" in screen.refresh_button.state()
    assert screen.status_var.get() == "Fetching Jira … up to 2000 issues, this can take a minute"
    assert window.status_text() == "Fetching Jira …"
    assert live.started.wait(5.0)
    for _ in range(3):
        window.update()  # the Tk thread keeps serving while the worker waits on the gate
    assert screen.fetch() is False and screen.fetching  # a second Refresh is ignored, not queued
    assert painted == [] and _keys(screen) == [] and live.calls["live"] == 1
    live.gate.set()
    result = screen.wait_fetch()
    assert result.ok and result.data is SAMPLE and live.calls["live"] == 1
    assert len(live.threads) == 1 and live.threads[0] is not threading.main_thread() and live.threads[0].daemon
    assert painted == [threading.main_thread()]  # applied on the Tk thread, once the worker was done
    assert "disabled" not in screen.refresh_button.state() and not screen.fetching
    assert len(_keys(screen)) == 5 and window.status_text() == "Jira: 5 issues fetched"
    assert screen.fetch() and screen.wait_fetch().ok and live.calls["live"] == 2  # the gate stays open


def test_live_screen_destroyed_mid_fetch_drops_the_result(window, live, monkeypatch):
    errors = _callback_errors(window, monkeypatch)
    screen = window.show("jira_live")
    live.gate = threading.Event()
    assert screen.fetch() and live.started.wait(5.0)
    window.update()
    assert window.pick_theme("pink-noir").ok  # rebuilds every screen while the worker is still out
    assert not screen.winfo_exists() and window.current is not screen and window.current_key == "jira_live"
    assert "disabled" not in window.current.refresh_button.state() and not window.current.fetching
    assert window.current.status_var.get() == "No fetch yet · press Refresh"
    live.gate.set()
    _settle(window, live)
    assert window.jira_live is None and _keys(window.current) == [] and errors == []  # dropped, quietly
    assert live.calls["live"] == 1
    assert window.current.fetch() and window.current.wait_fetch().ok and len(_keys(window.current)) == 5


def test_live_screen_closing_the_window_mid_fetch_does_not_wait(seeded, monkeypatch):
    win = _themes_window(seeded)
    fake = FakeRun(win)
    fake.gate = threading.Event()
    monkeypatch.setattr(win, "execute_quiet", fake)
    screen = win.show("jira_live")
    assert screen.fetch() and fake.started.wait(5.0)
    started = time.monotonic()
    win.close()  # returns at once: nobody joins the worker
    assert time.monotonic() - started < 2.0 and fake.threads[0].is_alive()
    fake.gate.set()
    fake.threads[0].join(5.0)
    assert not fake.threads[0].is_alive() and fake.calls["live"] == 1 and screen.last_fetch is None
    del win, screen
    gc.collect()
    assert seeded.execute("count", entity=PLAN).data["count"] == 3


def test_live_screen_sorts_on_values_not_cells(window, live):
    screen = _fetched(window)
    screen.sort_by("key")
    assert _keys(screen) == ["HWL-2", "HWL-9", "HWL-10", "HWL-33", "HWL-100"]
    assert screen.tree.heading("key", "text") == "Key ▲"
    screen.sort_by("key")
    assert _keys(screen) == ["HWL-100", "HWL-33", "HWL-10", "HWL-9", "HWL-2"]
    assert screen.tree.heading("key", "text") == "Key ▼" and screen.tree.heading("summary", "text") == "Summary"
    screen.sort_by("due")
    assert _keys(screen) == ["HWL-2", "HWL-9", "HWL-33", "HWL-100", "HWL-10"]  # the null due last
    screen.sort_by("due")
    assert _keys(screen) == ["HWL-100", "HWL-33", "HWL-9", "HWL-2", "HWL-10"]  # and last again
    screen.clear_filters()
    assert _keys(screen) == ["HWL-9", "HWL-10", "HWL-100", "HWL-2", "HWL-33"] and screen.sort_column is None
    assert screen.tree.heading("due", "text") == "Due"


def test_live_screen_filters_locally(window, live):
    screen = _fetched(window)
    screen.filter_var.set("hwl-1")
    assert _keys(screen) == ["HWL-10", "HWL-100"] and live.calls["live"] == 1
    screen.filter_var.set("brake")
    assert _keys(screen) == ["HWL-9", "HWL-2"]  # summary only; no key says brake
    screen.filter_var.set("")
    screen.filters["status"].set("Done")
    screen._populate()
    assert _keys(screen) == ["HWL-9", "HWL-2"] and screen.count_var.get() == "2 of 5 issues"
    assert list(screen.boxes["status_category"].cget("values")) == ["(all)", "new", "indeterminate", "done"]
    assert list(screen.boxes["status"].cget("values")) == ["(all)", "Done", "In Progress", "To Do"]
    assignees = list(screen.boxes["assignee"].cget("values"))
    assert assignees == ["(all)", "Ana", "Cy", "(none)"]
    screen.filters["status"].set("(all)")
    screen.filters["assignee"].set("(none)")
    screen._populate()
    assert _keys(screen) == ["HWL-33"]
    screen.filters["assignee"].set("(all)")
    screen.filters["issue_type"].set("Bug")
    screen._populate()
    assert _keys(screen) == ["HWL-10", "HWL-2"]
    screen.filters["priority"].set("Medium")
    screen.filters["issue_type"].set("Story")
    screen._populate()
    assert _keys(screen) == []  # AND: no Medium story
    screen.filters["priority"].set("High")
    screen._populate()
    assert _keys(screen) == ["HWL-9", "HWL-100", "HWL-33"]
    screen.filters["status_category"].set("new")
    screen._populate()
    assert _keys(screen) == ["HWL-100", "HWL-33"]
    screen.clear_filters()
    assert len(_keys(screen)) == 5 and all(v.get() == "(all)" for v in screen.filters.values())
    assert screen.filter_var.get() == "" and live.calls["live"] == 1


def test_live_screen_mutes_done_rows_and_shapes_cells(window, live):
    screen = _fetched(window)
    for iid in _keys(screen):
        tags = screen.tree.item(iid, "tags")
        assert tags[0] in ("odd", "even")
        assert ("muted" in tags) == (screen.row(iid)["status_category"] == "done"), iid
    assert str(screen.tree.tag_configure("muted", "foreground")) == window.theme.palette.muted  # cyan-neon: #609da9
    assert screen.tree.set("HWL-9", "comments") == "[Comments]"
    assert screen.tree.set("HWL-9", "labels") == "safety, VAT" and screen.tree.set("HWL-10", "labels") == ""
    assert screen.tree.set("HWL-9", "created") == "2026-10-01" and len(screen.tree.set("HWL-9", "updated")) == 10
    assert screen.tree.set("HWL-33", "assignee") == "" and screen.tree.set("HWL-10", "due") == ""
    assert screen.tree.set("HWL-9", "parent_key") == "HWL-1" and screen.tree.set("HWL-9", "resolution") == "Done"
    assert list(screen.tree["columns"])[:4] == ["comments", "key", "issue_type", "summary"]
    assert len(screen.tree["columns"]) == 15 and screen.tree.column("summary", "stretch") == 0
    assert screen.tree.column("comments", "stretch") == 0 and screen.tree.heading("comments", "command") == ""


def test_live_screen_opens_the_focused_issue(window, live):
    screen = _fetched(window)
    screen.open_selected()
    assert window.status_text() == "Select an issue first"
    screen.tree.focus("HWL-9")
    screen.open_selected()
    assert window.status_text() == "Open: https://asirobots.atlassian.net/browse/HWL-9"  # not interactive


def test_live_screen_keeps_its_rows_across_a_theme_pick(window, live):
    screen = _fetched(window)
    assert window.pick_theme("pink-noir").ok
    assert window.current_key == "jira_live" and window.current is not screen
    assert live.calls["live"] == 1 and len(_keys(window.current)) == 5
    assert str(window.current.tree.tag_configure("muted", "foreground")) == "#955073"  # pink-noir's muted
    assert [k for k, _ in window.factory.items()] == SCREENS


def test_jira_live_event_does_not_refresh_the_open_screen(window, seeded):
    assert window.current_key == "dashboard"
    seeded.events.publish("jira.live", count=0, jql="x", truncated=False, fetched_at="", actor="agent")
    assert window._refresh_job is None
    seeded.events.publish("entity.created", entity=PLAN, id=1, actor="agent")
    assert window._refresh_job is not None
    assert seeded.execute("count", entity=PLAN).data["count"] == 3


def test_run_quiet_still_reports_on_the_status_bar(window):
    """The status-bar half of ``run_quiet`` survived the split: a failure is `Error:`, a warning `Warning:`."""
    result = window.run_quiet("jira", action="comments", key="")
    assert not result.ok and result.verb == "jira"
    assert window.status_text() == "Error: jira comments needs an issue key, e.g. HWL-2572"
    assert window.run_quiet("count", entity=PLAN).ok and window.status_text().startswith("Error:")  # untouched
    assert window.execute_quiet("count", entity=PLAN).data["count"] == 3  # the bare door: no status change


# -- the comments column and window --------------------------------------------------------
def _meta_labels(win) -> list[str]:
    from tkinter import ttk

    return [w.cget("text") for w in win.body.inner.winfo_children()
            if isinstance(w, ttk.Label) and str(w.cget("style")) == "Muted.TLabel"]


def test_comments_click_is_routed_by_column(window, live, monkeypatch):
    screen = _fetched(window)
    monkeypatch.setattr(screen.tree, "identify_column", lambda x: "#3")
    monkeypatch.setattr(screen.tree, "identify_row", lambda y: "HWL-9")
    assert screen._on_click(SimpleNamespace(x=5, y=5)) is None and window.comment_windows == {}
    monkeypatch.setattr(screen.tree, "identify_column", lambda x: "#1")
    assert screen._on_click(SimpleNamespace(x=5, y=5)) == "break"
    assert "HWL-9" in window.comment_windows and window.comment_windows["HWL-9"].wait_fetch().ok
    assert live.calls["comments"] == 1 and live.args[-1] == {"action": "comments", "key": "HWL-9"}
    screen.tree.focus("HWL-10")
    screen._on_key_c(None)
    assert set(window.comment_windows) == {"HWL-9", "HWL-10"}
    assert window.comment_windows["HWL-10"].wait_fetch().ok and live.calls["comments"] == 2
    assert [k for k, _ in window.factory.items()] == SCREENS  # a Toplevel is not a screen


def test_comments_window_lists_newest_first(window, live, seeded):
    _fetched(window)
    win = _comments(window, "HWL-9")
    assert win.title() == "HWL-9 — Comments" and win.cget("background") == window.theme.palette.bg
    assert win.winfo_exists() and live.calls["comments"] == 1
    metas = _meta_labels(win)
    assert len(metas) == 3 and metas[0].startswith("Ana · 2026-10-26 15:02")
    assert metas[0].endswith("· edited 2026-10-26 15:40") and "edited" not in metas[1] and "edited" not in metas[2]
    assert metas[1].startswith("Bo · 2026-10-24 10:00") and metas[2].startswith("Cy · 2026-10-21 09:12")
    assert [str(t.cget("state")) for t in win.texts] == ["disabled"] * 3
    assert [t.get("1.0", "end-1c") for t in win.texts] == [c["body"] for c in COMMENTS["comments"]]
    assert re.match(r"^3 comments · fetched \d\d:\d\d$", win.status_var.get())
    assert win.title_var.get() == "HWL-9  Brake test plan" and win.state_var.get() == "Done"
    assert window.open_comments("HWL-9") is win and len(window.comment_windows) == 1
    other = _comments(window, "HWL-10")
    assert other is not win and len(window.comment_windows) == 2 and live.calls["comments"] == 2
    win.open_url()
    assert window.status_text() == "Open: https://asirobots.atlassian.net/browse/HWL-9"
    assert seeded.execute("count", entity=PLAN).data["count"] == 3


def test_comments_window_refresh_failure_and_empty_history(window, live):
    _fetched(window)
    win = _comments(window, "HWL-9")
    assert win.fetch() and win.wait_fetch().ok and live.calls["comments"] == 2 and len(_meta_labels(win)) == 3
    live.failure = NO_SESSION
    assert win.fetch() and not win.wait_fetch().ok
    assert len(_meta_labels(win)) == 3 and win.winfo_exists()
    assert win.status_var.get().startswith("Error: no Atlassian session") and window.status_text().startswith("Error:")
    live.failure = None
    live.comments = {**COMMENTS, "key": "HWL-2", "summary": "Old brake issue", "count": 0, "comments": []}
    empty = _comments(window, "HWL-2")
    assert _meta_labels(empty) == ["No comments."] and empty.texts == []


def test_comments_window_fetch_runs_off_the_tk_thread(window, live):
    _fetched(window)
    live.gate = threading.Event()
    win = window.open_comments("HWL-9")
    assert win.fetching and "disabled" in win.refresh_button.state()
    assert win.status_var.get() == "Fetching comments …" and live.started.wait(5.0)
    window.update()
    assert win.fetch() is False and win.fetching and _meta_labels(win) == []  # ignored while one runs
    assert window.open_comments("HWL-9") is win and win.fetching  # a second click lifts it, no second fetch
    live.gate.set()
    result = win.wait_fetch()
    assert result.ok and live.calls["comments"] == 1 and live.threads[-1] is not threading.main_thread()
    assert "disabled" not in win.refresh_button.state() and len(_meta_labels(win)) == 3
    assert re.match(r"^3 comments · fetched \d\d:\d\d$", win.status_var.get()) and win.last is result


def test_comments_window_destroyed_mid_fetch_drops_the_result(window, live, monkeypatch):
    errors = _callback_errors(window, monkeypatch)
    _fetched(window)
    live.gate = threading.Event()
    win = window.open_comments("HWL-9")
    assert live.started.wait(5.0)
    win.close()  # Close (or Escape) while the worker is out
    assert not win.winfo_exists() and window.comment_windows == {}
    live.started.clear()
    other = window.open_comments("HWL-10")
    assert live.started.wait(5.0)
    assert window.pick_theme("pink-noir").ok and not other.winfo_exists()  # a rebuild while the worker is out
    live.gate.set()
    _settle(window, live)
    assert errors == [] and win.last_fetch is None and other.last_fetch is None  # dropped, quietly
    assert live.calls["comments"] == 2 and window.comment_windows == {}
    back = _comments(window, "HWL-9")
    assert back.winfo_exists() and len(_meta_labels(back)) == 3


def test_comments_window_closes_with_close_and_with_a_theme_pick(window, live):
    _fetched(window)
    win = _comments(window, "HWL-9")
    win.close()
    assert "HWL-9" not in window.comment_windows and not win.winfo_exists()
    again = _comments(window, "HWL-9")
    destroyed = []
    again.bind("<Destroy>", lambda e: destroyed.append(e.widget), add="+")
    assert window.pick_theme("pink-noir").ok
    assert window.comment_windows == {} and destroyed and not again.winfo_exists()
    back = _comments(window, "HWL-9")
    assert back.winfo_exists() and back.cget("background") == "#0a0306"  # pink-noir's bg


def test_comments_windows_close_with_the_main_window(seeded, monkeypatch):
    win = _themes_window(seeded)
    fake = FakeRun(win)
    monkeypatch.setattr(win, "execute_quiet", fake)
    win.show("jira_live")
    comments = _comments(win, "HWL-9")
    destroyed = []
    comments.bind("<Destroy>", lambda e: destroyed.append(e.widget), add="+")
    win.close()
    assert destroyed
    del win, comments
    gc.collect()
    assert seeded.execute("count", entity=PLAN).data["count"] == 3



# -- the family lock -----------------------------------------------------------------------
def test_gui_entry_point_returns_3_without_a_window_while_a_holder_runs(tmp_path, monkeypatch, capsys):
    from asi_kletz.gui import app
    from tests.test_locks import _release, hold_brain

    launched: list[object] = []
    monkeypatch.setattr(app, "launch", lambda brain, **kw: launched.append(brain))
    monkeypatch.setattr(app, "ask_retry", lambda exc: pytest.fail("no dialog when not interactive"))
    proc = hold_brain(tmp_path / "held.db")
    try:
        assert app.main(["--db", str(tmp_path / "gui.db")], interactive=False) == 3
        assert launched == [] and not (tmp_path / "gui.db").exists()
        assert f"asi_kletz is running (pid {proc.held_pid}" in capsys.readouterr().err
    finally:
        _release(proc)
    assert app.main(["--db", str(tmp_path / "gui.db")], interactive=False) == 0 and len(launched) == 1


def test_busy_dialog_retry_once_then_quit(tmp_path, monkeypatch):
    from asi_kletz.gui import app
    from tests.test_locks import _release, hold_brain

    launched: list[object] = []
    asked: list[str] = []
    monkeypatch.setattr(app, "launch", lambda brain, **kw: launched.append(brain))
    proc = hold_brain(tmp_path / "held.db")
    try:
        monkeypatch.setattr(app, "ask_retry", lambda exc: asked.append(str(exc)) or True)  # Retry, still busy
        assert app.main(["--db", str(tmp_path / "gui.db")]) == 3
        assert len(asked) == 1 and launched == []  # Retry re-attempts once, then the refusal is final
        asked.clear()
        monkeypatch.setattr(app, "ask_retry", lambda exc: asked.append(str(exc)) or False)  # Quit
        assert app.main(["--db", str(tmp_path / "gui.db")]) == 3 and len(asked) == 1

        def retry_after_the_holder_leaves(exc):
            asked.append(str(exc))
            _release(proc)
            return True

        monkeypatch.setattr(app, "ask_retry", retry_after_the_holder_leaves)
        assert app.main(["--db", str(tmp_path / "gui.db")]) == 0 and len(launched) == 1
    finally:
        _release(proc)


def test_about_box_names_the_lock_directory(window, tmp_path):
    window.about()
    assert f"Lock directory: {tmp_path / 'locks'}" in window.status_text()


def test_wide_tables_scroll_sideways_and_name_clipped_headings(window, seeded, monkeypatch):
    from types import SimpleNamespace

    from asi_kletz.gui.screens import scroll_sideways

    for key in ("safety_plan", "safety_plan_matrix"):
        screen = window.show(key)
        tree = screen.tree
        assert tree.bind("<Shift-MouseWheel>") and tree.bind("<Left>") and tree.bind("<Right>")
        moves: list[tuple] = []
        monkeypatch.setattr(tree, "xview_scroll", lambda n, what, m=moves: m.append((n, what)))
        tree.event_generate("<Shift-MouseWheel>", delta=-120)  # key events never reach a withdrawn window
        assert scroll_sideways(tree, -3) == "break" and scroll_sideways(tree, 3) == "break"
        assert moves == [(3, "units"), (-3, "units"), (3, "units")]
        # columns fit their headings since 0.7.1, so the hint needs one squeezed by hand (as a user can drag it):
        # a 36 px heading cannot show "JAMA", and hovering it names the column
        tree.column("loc_jama", width=36)
        shown = list(tree["displaycolumns"])  # "#n" counts displayed columns; the frozen ones are on the left
        monkeypatch.setattr(tree, "identify", lambda region, x, y: "heading")
        monkeypatch.setattr(tree, "identify_column", lambda x, c=shown: "#" + str(c.index("loc_jama") + 1))
        screen._on_heading_motion(SimpleNamespace(x=5, y=5))
        assert window.status_text() == "Column: JAMA"
        window.set_status("untouched")
        screen._on_heading_motion(SimpleNamespace(x=5, y=5))  # same heading: no repeat
        assert window.status_text() == "untouched"
        wide = "reviewer_tech_lead_functional_safety"  # "Tech Lead - Functional Safety", shown on the right
        monkeypatch.setattr(tree, "identify_column", lambda x, c=shown, w=wide: "#" + str(c.index(w) + 1))
        screen._on_heading_motion(SimpleNamespace(x=5, y=5))  # a wide heading needs no hint
        assert window.status_text() == "untouched"


# -- every column as wide as the longest string in its domain (0.7.1) --------------------------------


def test_fit_columns_measures_headings_cells_and_extra(window):
    from tkinter import ttk

    from asi_kletz.gui.screens import fit_columns

    tree = ttk.Treeview(window, columns=("a", "b", "c", "d", "e"), show="headings")
    body, head = _fonts(tree)
    long_heading = "A heading much longer than anything in its cells"
    long_cell = "a cell value that is wider than its one-letter heading"
    extra_value = "Out-of-Scope, a value of the domain that no row holds"
    for column, text in zip(tree["columns"], ("A", long_heading, "C", "D", ""), strict=True):
        tree.heading(column, text=text)
    tree.column("c", stretch=True)  # fit_columns turns it off: a stretchable column is shrunk towards minwidth
    tree.insert("", "end", values=(long_cell, "x", "W" * 200, "", ""))
    tree.insert("", "end", values=("short", "y", "", "", ""))
    widths = fit_columns(tree, {"d": [extra_value]})
    assert widths == {c: int(tree.column(c, "width")) for c in tree["columns"]}
    assert widths["a"] == body.measure(long_cell) + 24  # the widest cell, in the body font
    assert widths["b"] == head.measure(long_heading) + 24  # the heading wins, in the heading font
    assert widths["c"] == 600 and body.measure("W" * 200) + 24 > 600  # capped
    assert widths["d"] == body.measure(extra_value) + 24  # the domain widens a column with no such cell
    assert widths["e"] == 40  # an empty column keeps the floor
    for column, width in widths.items():  # minwidth == width and stretch off, so Tk never squeezes a fitted column
        assert int(tree.column(column, "minwidth")) == width and tree.column(column, "stretch") == 0
    again = fit_columns(tree, min_width=80, max_width=200, padding=0)
    assert again["e"] == 80 and again["a"] == 200
    assert int(tree.column("a", "width")) == 200 and int(tree.column("a", "minwidth")) == 200
    assert int(tree.column("e", "width")) == 80 and int(tree.column("e", "minwidth")) == 80
    tree.destroy()


def _enum_extra(screen) -> dict[str, tuple[str, ...]]:
    return {
        s.name: screen.brain.lookups[s.lookup] for s in screen.schema.fields if s.type is FieldType.ENUM and s.lookup
    }


def test_safety_plan_columns_fit_their_domain(window, seeded):
    screen = window.show("safety_plan")
    tree = screen.tree
    extra = _enum_extra(screen)
    assert set(extra) == {"pdp_phase", "lifecycle_phase", "status"}
    _assert_fitted(tree, extra)
    body, head = _fonts(tree)
    title = "Tech Lead - Functional Safety"  # a flag column is as wide as its heading, the source column title
    assert tree.heading("reviewer_tech_lead_functional_safety", "text") == title
    assert int(tree.column("reviewer_tech_lead_functional_safety", "width")) == head.measure(title) + 24
    assert int(tree.column("status", "width")) >= body.measure("Out-of-Scope") + 24
    screen.set_columns("Reviewer")  # a narrowed column set is fitted again
    _assert_fitted(tree, extra)
    screen.search_var.set("no such row")  # an empty table keeps its heading-fitted widths
    assert tree.get_children() == ()
    _assert_fitted(tree, extra)
    assert int(tree.column("reviewer_tech_lead_functional_safety", "width")) == head.measure(title) + 24
    assert int(tree.column("lifecycle_phase", "width")) >= max(body.measure(p) for p in extra["lifecycle_phase"]) + 24


def test_enum_column_fits_the_longest_lookup_value(window, seeded):
    for row_id in (2, 3):  # keep row 1 alone: lifecycle "1. Concept Development", status "Done"
        assert seeded.execute("delete", entity=PLAN, id=row_id, actor="agent").ok
    screen = window.show("safety_plan")
    screen.refresh()
    tree = screen.tree
    assert [tree.set(i, "lifecycle_phase") for i in tree.get_children() if i.isdigit()] == ["1. Concept Development"]
    body, head = _fonts(tree)
    phases = seeded.lookups["lifecycle_phase"]
    longest = max(phases, key=body.measure)
    on_screen = max(head.measure(tree.heading("lifecycle_phase", "text")), body.measure("1. Concept Development"))
    assert body.measure(longest) > on_screen  # the rows alone would leave the column narrower
    assert int(tree.column("lifecycle_phase", "width")) == body.measure(longest) + 24
    assert int(tree.column("pdp_phase", "width")) >= max(body.measure(v) for v in seeded.lookups["pdp_phase"]) + 24


def test_matrix_columns_fit_their_headings(window, seeded):
    from asi_kletz.gui import matrix_screen

    assert not hasattr(matrix_screen, "ALL_WIDTH")
    screen = window.show("safety_plan_matrix")
    _, head = _fonts(screen.tree)
    title = "Tech Lead - Functional Safety"
    assert screen.group_var.get() == "all"
    _assert_fitted(screen.tree)
    assert int(screen.tree.column("reviewer_tech_lead_functional_safety", "width")) == head.measure(title) + 24
    assert int(screen.tree.column("loc_jama", "width")) == head.measure("JAMA") + 24
    screen.set_group("reviewer")
    _assert_fitted(screen.tree)
    assert int(screen.tree.column("reviewer_tech_lead_functional_safety", "width")) == head.measure(title) + 24
    screen.set_group("location")
    _assert_fitted(screen.tree)
    assert int(screen.tree.column("loc_jama", "width")) == head.measure("JAMA") + 24


def test_live_screen_columns_fit_their_text(window, live):
    screen = _fetched(window)
    assert len(_keys(screen)) == 5 and screen.columns[0] == "comments" and len(screen.columns) == 15
    _assert_fitted(screen.tree)
    body, _ = _fonts(screen.tree)
    assert int(screen.tree.column("comments", "width")) >= body.measure("[Comments]") + 24
    assert int(screen.tree.column("summary", "width")) >= body.measure("E-stop guard missing") + 24
    assert screen.tree.column("summary", "stretch") == 0  # fitted, never stretched: Tk would shrink it to minwidth
    screen.sort_by("key")  # a repaint, with a sort mark in the heading, fits again
    _assert_fitted(screen.tree)
    screen.filter_var.set("no such issue")
    assert _keys(screen) == []
    _assert_fitted(screen.tree)  # an empty table keeps its heading-fitted widths


def test_dashboard_tables_fit_their_text(window):
    dash = window.current
    body, _ = _fonts(dash.open_table)
    for tree in (dash.phase_table, dash.open_table, dash.audit):
        assert tree.get_children()
        _assert_fitted(tree)
    widest = body.measure("Hazard Analysis and Risk Assessment") + 24
    assert int(dash.open_table.column("deliverable", "width")) == widest
    assert int(dash.phase_table.column("lifecycle_phase", "width")) >= body.measure("10. Decommissioning") + 24


# -- frozen identity columns: two trees in lock-step (0.7.2) -----------------------------------------


def _rows(tree) -> list[tuple[str, tuple]]:
    """Every row of a table as (iid, tags), in order: what two trees in lock-step must agree on."""
    return [(iid, tuple(tree.item(iid, "tags"))) for iid in tree.get_children("")]


def _cells(tree, column) -> list[str]:
    return [tree.set(iid, column) for iid in tree.get_children("")]


def _click_heading(tree, column) -> None:
    """Run a heading's click command the way Tk would; a withdrawn window gets no pointer events."""
    tree.tk.call(tree.heading(column, "command"))


def test_frozen_pane_keeps_two_trees_in_step():
    from asi_kletz.gui.screens import FrozenPane

    root = tk.Tk()
    root.withdraw()
    try:
        pane = FrozenPane(root, ["id", "name", "a", "b"], ["id", "name"])
        pane.pack(fill="both", expand=True)
        left, right = pane.left, pane.right
        assert pane.frozen == ("id", "name")
        assert tuple(left["columns"]) == ("id", "name") and tuple(right["columns"]) == ("id", "name", "a", "b")
        assert right["displaycolumns"] == ("a", "b")  # the frozen columns are shown by the left tree only
        assert pane.split.panes() == (str(left), str(right))  # the trees are the panes of the split (0.7.3)
        assert pane.ybar.grid_info()["column"] == 1 and pane.ybar.grid_info()["row"] == 0
        assert pane.xbar.grid_info()["row"] == 1 and pane.xbar.grid_info()["column"] == 0
        assert left.cget("xscrollcommand") == "" and right.cget("xscrollcommand")  # left never scrolls sideways
        assert left.cget("yscrollcommand") and right.cget("yscrollcommand")

        right.heading("name", text="Name")
        right.column("id", anchor="center")
        right.tag_configure("odd", background="#123456")
        right.tag_configure("done", foreground="#654321")
        for i in range(40):
            tags = ("odd" if i % 2 else "even", "done") if i < 3 else ("odd" if i % 2 else "even",)
            right.insert("", "end", iid=str(i), values=(i, f"row {i}", i * 2, i * 3), tags=tags)
        pane.mirror()
        assert _rows(left) == _rows(right) and len(_rows(left)) == 40  # same iids, same order, same tags
        assert _cells(left, "name") == _cells(right, "name") and left.set("7", "id") == "7"
        assert left.heading("name", "text") == "Name" and str(left.column("id", "anchor")) == "center"
        assert left.tag_configure("odd")["background"] == "#123456"
        assert left.tag_configure("done")["foreground"] == "#654321"
        assert left.column("name", "stretch") == 0 and left.column("id", "stretch") == 0
        _assert_fitted(left)

        left.selection_set("3")  # the selection follows both ways
        root.update()
        assert right.selection() == ("3",)
        right.selection_set("9")
        root.update()
        assert left.selection() == ("9",)
        right.selection_remove("9")
        root.update()
        assert left.selection() == () and right.selection() == ()

        # scrolling one tree moves the other through its yscrollcommand, which Tk runs only when it
        # redraws a mapped widget; a withdrawn window never redraws, so call it the way Tk would
        pane._scrolled(right, left, "0.5", "0.75")
        assert left.yview()[0] == pytest.approx(0.5) and pane.ybar.get()[0] == pytest.approx(0.5)
        pane._scrolled(left, right, "0.25", "0.5")
        assert right.yview()[0] == pytest.approx(0.25) and pane.ybar.get()[0] == pytest.approx(0.25)
        pane.yview("moveto", "0.1")  # the shared vertical bar
        root.update_idletasks()
        assert left.yview()[0] == pytest.approx(0.1) and right.yview()[0] == pytest.approx(0.1)
        assert pane.yview() == right.yview()
        left.event_generate("<MouseWheel>", delta=-120)  # the wheel over either tree moves both
        root.update_idletasks()
        assert left.yview()[0] == right.yview()[0] > 0.1

        pane.set_display(["id", "b", "name"])  # the display never includes a frozen column
        assert right["displaycolumns"] == ("b",)
        pane.set_display(["id", "name", "a", "b"])
        assert right["displaycolumns"] == ("a", "b")
        sorts: list[str] = []
        pane.on_sort = sorts.append
        _click_heading(left, "name")  # a left heading sorts through the screen's callback
        assert sorts == ["name"]
    finally:
        root.destroy()
        gc.collect()


def test_safety_plan_freezes_the_identity_columns(window, seeded):
    from asi_kletz.gui.entity_screen import FROZEN
    from asi_kletz.gui.screens import PLAN_HEADER, FrozenPane

    screen = window.show("safety_plan")
    pane, left, right = screen.pane, screen.pane.left, screen.tree
    assert isinstance(pane, FrozenPane) and list(FROZEN) == FROZEN_PLAN and pane.frozen == tuple(FROZEN_PLAN)
    assert right is pane.right and screen.ybar is pane.ybar and screen.xbar is pane.xbar
    assert list(right["columns"]) == [*screen.columns, "plan"]  # the right tree still owns every column
    hidden = (*FROZEN, *STACKED_PLAN)
    assert not any(c in hidden for c in right["displaycolumns"]) and len(right["displaycolumns"]) == 59
    assert tuple(left["columns"]) == tuple(FROZEN_PLAN)
    assert _rows(left) == _rows(right) and [t for _, t in _rows(left)] == [
        ("pdp", "even"), ("phase", "odd"), ("even",), ("pdp", "odd"), ("phase", "even"), ("odd",),
        ("pdp", "even"), ("phase", "odd"), ("even",),
    ]
    for column in FROZEN:
        assert _cells(left, column) == _cells(right, column)
        assert left.heading(column, "text") == right.heading(column, "text")
    assert left.heading("plan", "text") == PLAN_HEADER
    assert _cells(left, "plan")[:3] == ["PDP phase 1", "    1. Concept Development", "        Safety Plan"]
    _assert_fitted(left, _enum_extra(screen))  # the frozen enum columns fit their whole lookup too
    assert int(left.column("plan", "width")) == int(right.column("plan", "width"))
    assert left.tag_configure("odd")["background"] == right.tag_configure("odd")["background"]

    screen.set_columns("Location")  # a column choice hides nothing frozen and leaves the left tree alone
    assert "loc_dms" in right["displaycolumns"] and not any(c in hidden for c in right["displaycolumns"])
    assert _rows(left) == _rows(right)

    screen.sort_by("deliverable")  # sorting reorders both identically; the stack follows the sorted order
    titles = [t for t in _cells(right, "deliverable") if t]
    assert titles == sorted(titles, key=str.casefold)
    assert [t.strip() for t in _cells(left, "plan") if t.startswith("        ")] == titles
    assert _rows(left) == _rows(right)
    screen.sort_by("deliverable")  # again: descending
    assert [t for t in _cells(right, "deliverable") if t] == titles[::-1]
    assert window.status_text() == "Sorted by Safety Deliverables, descending"
    assert _rows(left) == _rows(right)
    _click_heading(left, "plan")  # the stacked heading, on either side, is the way back to the plan's order
    assert [t for t in _cells(right, "deliverable") if t] == [r["deliverable"] for r in screen.rows]
    assert window.status_text() == "Plan order" and screen.sort_key is None and _rows(left) == _rows(right)

    left.selection_set("2")  # selecting through the frozen tree fills the form
    window.update()
    assert right.selection() == ("2",) and screen.selected_id == 2
    assert screen.widgets["deliverable"].get() == screen.by_id[2]["deliverable"]
    screen.select(3)  # and the other way round
    window.update()
    assert left.selection() == ("3",)

    screen.refresh()  # a refresh keeps both in step, selection included
    assert _rows(left) == _rows(right) and left.selection() == ("3",)


def test_matrix_freezes_the_fixed_columns(window, seeded, monkeypatch):
    from asi_kletz.gui.matrix_screen import FIXED, PLAN_HEADER

    screen = window.show("safety_plan_matrix")
    pane, left, right = screen.pane, screen.pane.left, screen.tree
    assert pane.frozen == FIXED and right is pane.right and tuple(left["columns"]) == FIXED
    flags = [f.name for f in screen.schema.fields if f.is_flag]
    assert list(right["displaycolumns"]) == flags  # the right tree shows the flags alone
    assert _rows(left) == _rows(right) and len(_rows(left)) == 9  # 3 PDP phases, 3 lifecycle phases, 3 deliverables
    for column in FIXED:
        assert _cells(left, column) == _cells(right, column)
    assert left.set("1", "plan").strip() == next(r["deliverable"] for r in screen.rows if r["id"] == 1)
    assert left.heading("plan", "text") == PLAN_HEADER

    screen.set_group("reviewer")
    reviewers = [f.name for f in screen.groups["reviewer"]]
    assert list(right["displaycolumns"]) == reviewers and list(right["columns"]) == [*FIXED, *reviewers]
    assert _rows(left) == _rows(right)
    assert screen.toggle(1, "reviewer_pat").ok and right.set("1", "reviewer_pat") == "✓"
    assert _rows(left) == _rows(right)

    # a click lands on the displayed column: "#1" is the first reviewer flag, not `order`
    monkeypatch.setattr(right, "identify", lambda region, x, y: "cell")
    monkeypatch.setattr(right, "identify_row", lambda y: "2")
    monkeypatch.setattr(right, "identify_column", lambda x: "#1")
    before = seeded.execute("get", entity=PLAN, id=2).data[reviewers[0]]
    screen._on_click(SimpleNamespace(x=5, y=5))
    assert seeded.execute("get", entity=PLAN, id=2).data[reviewers[0]] is (not before)
    assert right.set("2", reviewers[0]) == ("" if before else "✓") and _rows(left) == _rows(right)

    window.update()  # drain the refresh's queued selection events, as the loop does before a user can click
    left.selection_set("3")
    window.update()
    assert right.selection() == ("3",)


def test_matrix_stacks_pdp_phase_over_lifecycle_phase_over_deliverable(window, seeded, monkeypatch):
    """Owner, 2026-10-28: the three identity columns were crowded; stack them instead."""
    from types import SimpleNamespace

    from asi_kletz.gui.matrix_screen import INDENT, PDP_TAG, PHASE_TAG, stack

    rows = seeded.execute("list", entity=PLAN).data
    lines = stack(rows)
    assert [(iid, level) for iid, level, _, _ in lines] == [
        ("pdp:1", 0), ("phase:1:1. Concept Development", 1), ("1", 2),
        ("pdp:2", 0), ("phase:2:2. HARA / Risk Assessment", 1), ("2", 2),
        ("pdp:3", 0), ("phase:3:3. Functional Safety Concept (FSC)", 1), ("3", 2),
    ]
    assert lines[0][2] == "PDP phase 1" and lines[1][2] == INDENT + "1. Concept Development"
    assert lines[2][2] == INDENT * 2 + "Safety Plan" and lines[2][3] is rows[0]
    # a plan out of order shows the truth of its order: the same phase opens again
    twice = stack([rows[0], rows[1], rows[0]])
    assert [iid for iid, _, _, _ in twice] == ["pdp:1", "phase:1:1. Concept Development", "1",
                                              "pdp:2", "phase:2:2. HARA / Risk Assessment", "2",
                                              "pdp:1", "phase:1:1. Concept Development", "1"]
    # a row without phases still has a place
    assert [t for _, _, t, _ in stack([{"id": 9, "deliverable": "Loose"}])] == [
        "(no PDP phase)", INDENT + "(no lifecycle phase)", INDENT * 2 + "Loose"]

    screen = window.show("safety_plan_matrix")
    left, right = screen.pane.left, screen.tree
    assert [iid for iid, _ in _rows(right)] == [iid for iid, _, _, _ in lines]
    assert _cells(right, "plan") == [text for _, _, text, _ in lines]
    assert all(right.set("pdp:1", f.name) == "" for f in screen.flags)  # a group row has no flags
    # group rows wear their tag first (colour and font), then the stripe (background); deliverables the stripe alone
    assert right.item("pdp:1", "tags")[0] == PDP_TAG
    assert right.item("phase:1:1. Concept Development", "tags")[0] == PHASE_TAG
    assert tuple(right.item("1", "tags")) in (("odd",), ("even",))
    assert _rows(left) == _rows(right)
    palette = window.theme.palette
    for tree in (left, right):
        assert str(tree.tag_configure(PDP_TAG, "foreground")) == palette.primary
        assert str(tree.tag_configure(PHASE_TAG, "foreground")) == palette.accent

    # a click on a group row toggles nothing
    monkeypatch.setattr(right, "identify", lambda region, x, y: "cell")
    monkeypatch.setattr(right, "identify_row", lambda y: "pdp:1")
    monkeypatch.setattr(right, "identify_column", lambda x: "#1")
    before = seeded.execute("get", entity=PLAN, id=1).data
    screen._on_click(SimpleNamespace(x=5, y=5))
    assert seeded.execute("get", entity=PLAN, id=1).data == before

    # the search keeps a deliverable and the two group rows above it, nothing else
    screen.search_var.set("hazard")
    assert [iid for iid, _ in _rows(right)] == ["pdp:2", "phase:2:2. HARA / Risk Assessment", "2"]
    assert _rows(left) == _rows(right)
    screen.search_var.set("")
    assert len(_rows(right)) == 9


def test_safety_plan_group_rows_are_headings_not_records(window, seeded):
    """Owner, 2026-10-28: the stack on the table too. A PDP or lifecycle phase row selects nothing."""
    from asi_kletz.gui.screens import PDP_TAG, PHASE_TAG

    screen = window.show("safety_plan")
    left, right = screen.pane.left, screen.tree
    screen.select(2)
    assert screen.selected_id == 2 and screen.widgets["deliverable"].get() == "Hazard Analysis and Risk Assessment"
    right.selection_set("pdp:3")
    screen._on_select()
    assert screen.selected_id == 2 and screen.widgets["deliverable"].get() == "Hazard Analysis and Risk Assessment"
    assert right.item("pdp:3", "tags")[0] == PDP_TAG
    assert right.item("phase:3:3. Functional Safety Concept (FSC)", "tags")[0] == PHASE_TAG
    assert all(right.set("pdp:3", c) == "" for c in screen.columns)  # a group row has no data cells
    palette = window.theme.palette
    for tree in (left, right):
        assert str(tree.tag_configure(PDP_TAG, "foreground")) == palette.primary
        assert str(tree.tag_configure(PHASE_TAG, "foreground")) == palette.accent
    window.update()
    left.selection_set("3")  # a deliverable through the frozen tree still fills the form
    window.update()
    assert screen.selected_id == 3 and screen.widgets["deliverable"].get() == "Functional Safety Concept"


def test_frozen_pane_split_is_draggable(window, monkeypatch):
    """The two trees are the panes of a horizontal PanedWindow; the sash lands on the full fitted width (the
    longest row of the left pane), leaving the right pane RIGHT_MIN px."""
    from tkinter import ttk

    from asi_kletz.gui.screens import RIGHT_MIN

    screen = window.show("safety_plan")
    pane, split = screen.pane, screen.pane.split
    assert isinstance(split, ttk.PanedWindow) and str(split.cget("orient")) == "horizontal"
    assert split.panes() == (str(pane.left), str(pane.right)) and split.master is pane
    assert int(split.pane(pane.left, "weight")) == 0 and int(split.pane(pane.right, "weight")) == 1
    assert pane.ybar.master is pane and pane.ybar.grid_info() == {**pane.ybar.grid_info(), "row": 0, "column": 1}
    assert pane.xbar.grid_info()["row"] == 1 and pane.xbar.grid_info()["column"] == 0
    widths = {c: int(pane.left.column(c, "width")) for c in pane.frozen}
    fitted = sum(widths.values())
    assert pane.fitted_width() == fitted > 0 and RIGHT_MIN == 120

    window.update_idletasks()  # runs the after_idle that places the sash
    assert pane._sash_job is None
    pos = split.sashpos(0)  # a withdrawn window is never mapped, so Tk may answer 0; the call itself must work
    width = split.winfo_width()
    if split.winfo_ismapped() and width > 1:  # a mapped window has a width: the full fitted width, right keeps its room
        assert pos == max(1, min(fitted, width - RIGHT_MIN))
        assert not pane._sash_pending
    else:  # not mapped: the placement waits for <Map> (a sash set before the split has its geometry clamps to 0)
        assert pane._sash_pending

    split.sashpos(0, max(fitted // 2, 1))  # dragging the sash never changes a column width
    window.update_idletasks()
    assert {c: int(pane.left.column(c, "width")) for c in pane.frozen} == widths

    # the arithmetic, with the geometry a mapped 1000 px split would report
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(split, "winfo_ismapped", lambda: True)
    monkeypatch.setattr(split, "winfo_width", lambda: 1000)
    monkeypatch.setattr(split, "sashpos", lambda index, newpos=None: calls.append((index, newpos)) or newpos)
    pane._place_sash()
    assert calls == [(0, min(fitted, 880))]  # the longest row in full; a 1000 px split has the room
    monkeypatch.setattr(split, "winfo_width", lambda: 400)  # a narrow window: right keeps RIGHT_MIN px
    pane._place_sash()
    assert calls[-1] == (0, max(1, min(fitted, 280))) and calls[-1][1] <= 400 - RIGHT_MIN
    monkeypatch.setattr(split, "winfo_width", lambda: 100)  # narrower than the reserve: the sash stays at 1, never 0
    pane._place_sash()
    assert calls[-1] == (0, 1)
    monkeypatch.setattr(split, "winfo_width", lambda: 400)
    assert not pane._sash_pending
    monkeypatch.setattr(split, "winfo_ismapped", lambda: False)  # not mapped: nothing is set, the <Map> will
    pane._place_sash()
    assert len(calls) == 3 and pane._sash_pending
    monkeypatch.setattr(split, "winfo_ismapped", lambda: True)
    pane._on_map()  # the pending placement runs on <Map>, after the idle
    assert pane._sash_job is not None
    window.update_idletasks()
    assert calls[-1] == (0, max(1, min(fitted, 280))) and len(calls) == 4 and not pane._sash_pending
    pane._on_map()  # a <Map> with nothing pending (the screen shown again) leaves the user's sash alone
    assert pane._sash_job is None

    pane.mirror(screen._domain())  # every mirror places the sash again, once, after the idle
    assert pane._sash_job is not None
    pane.mirror(screen._domain())
    window.update_idletasks()
    assert pane._sash_job is None and calls[-1] == (0, max(1, min(fitted, 280))) and len(calls) == 5


# -- the Sprint Board, the Weekly Status and the dashboard's sprint tiles (0.8.1) ------------------------
ITEM = "sprint_item"
TRACKER_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "tracker_2026-10-28.txt"


def _sprint(brain):
    """Sprint 1, active, with three items: 3 points to do, 3 in progress, 2 done (capacity is the rule, 8)."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-10", "status": "Active", "goal": "Clear the backlog",
    }).ok
    for order, (title, points, status, extra) in enumerate([
        ("Safety Plan dated", 3, "To Do", {"kind": "Deliverable", "plan_row": 1}),
        ("Perform Platform Activity Flow", 3, "In Progress", {"kind": "Jira", "jira_key": "HWL-2553"}),
        ("Intro meeting", 2, "Done", {"kind": "Meeting"}),
    ], 1):
        assert brain.execute("create", entity=ITEM, data={
            "sprint": 1, "order": order, "title": title, "points": points, "status": status, **extra,
        }).ok


def _lane(screen, status):
    tree = screen.lanes[status]
    return [tree.set(i, "title") for i in tree.get_children()]


def test_dashboard_shows_where_the_active_sprint_stands(window, seeded):
    dash = window.current
    assert dash._sprint_vars["sprint"].get() == "–" and "No active sprint" in dash.sprint_tiles.cget("text")
    _sprint(seeded)
    dash.refresh()
    assert dash._sprint_vars["sprint"].get() == "1" and dash._sprint_vars["committed"].get() == "8 / 8"
    assert dash._sprint_vars["done"].get() == "2" and dash._sprint_vars["to_go"].get() == "6"
    assert dash._sprint_vars["unpointed"].get() == "0" and dash._sprint_vars["velocity"].get() == "–"
    assert dash.sprint_tiles.cget("text").startswith("Sprint 1 · SPRINT 1 · 3. Functional Safety Concept (FSC)")
    seeded.execute("sprint", action="close", as_of="2026-11-10")
    time.sleep(0.1)
    window.update()  # the event bus refreshes the open screen after 50 ms
    assert dash._sprint_vars["sprint"].get() == "2" and dash._sprint_vars["velocity"].get() == "2"
    assert dash._sprint_vars["committed"].get() == "6 / 8"


def test_sprint_board_lanes_form_and_save(window, seeded):
    screen = window.show("sprint_board")
    assert screen.board is None and screen.sprint_var.get() == "" and "No sprint yet" in screen.goal_var.get()
    _sprint(seeded)
    screen.refresh()
    assert screen.sprint_var.get() == "1 · SPRINT 1 · Active" and window.sprint_number == 1
    assert _lane(screen, "To Do") == ["Safety Plan dated"] and _lane(screen, "Done") == ["Intro meeting"]
    assert screen.points_var.get() == "8 / 8 points committed · 2 done · 6 to go · 0 unpointed"
    pace = screen.pace_var.get()
    assert pace.startswith("2026-10-27 to 2026-11-10 · ") and "velocity no closed sprint" in pace
    assert int(screen.bar.cget("value")) == 8 and int(screen.bar.cget("maximum")) == 8
    assert "Clear the backlog" in screen.goal_var.get()
    # select the In Progress item: the form fills, the other lanes drop their selection
    tree = screen.lanes["In Progress"]
    iid = tree.get_children()[0]
    tree.selection_set(iid)
    tree.event_generate("<<TreeviewSelect>>")
    assert screen.selected == int(iid) and screen.widgets["title"].get() == "Perform Platform Activity Flow"
    assert screen.widgets["jira_key"].get() == "HWL-2553" and screen.widgets["points"].get() == "3"
    # 8 points on one item: over capacity is a warning on the summary, never a refusal
    screen.widgets["points"].set("8")
    screen.widgets["status"].set("Done")
    assert screen.save().ok
    assert _lane(screen, "Done") == ["Perform Platform Activity Flow", "Intro meeting"]
    assert screen.warn_var.get() == "sprint 1 committed 13 of 8 points"
    assert screen.points_var.get().startswith("13 / 8 points committed · 10 done")
    # a new item from the form
    screen.new()
    screen.widgets["title"].set("Ask the systems team")
    screen.widgets["kind"].set("Question")
    assert screen.save().ok and _lane(screen, "To Do") == ["Safety Plan dated", "Ask the systems team"]
    assert screen.selected is not None and seeded.execute("count", entity=ITEM).data["count"] == 4
    # carry the new one into the next sprint, then close sprint 1: the board moves to sprint 2
    assert screen.carry().ok
    assert _lane(screen, "To Do") == ["Safety Plan dated"]
    assert screen.close_sprint().ok
    assert screen.sprint_var.get() == "2 · SPRINT 2 · Active" and window.sprint_number == 2
    assert sorted(_lane(screen, "To Do")) == ["Ask the systems team", "Safety Plan dated"]
    assert [s[0] for s in [v.split(" · ") for v in screen.sprint_box["values"]]] == ["1", "2"]
    assert window.status_text() == "Sprint 1 closed: 10 points done, 1 item(s) carried into sprint 2"
    screen.refresh()
    assert window.status_text().startswith("Sprint 2: 3 / 8 points committed")


def test_sprint_board_survives_a_theme_pick_and_start_refuses_twice(window, seeded):
    _sprint(seeded)
    screen = window.show("sprint_board")
    assert window.sprint_number == 1
    assert not screen.start_sprint().ok and "is active" in window.status_text()
    window.pick_theme("amber-neon")
    assert window.current_key == "sprint_board" and window.current.sprint_var.get() == "1 · SPRINT 1 · Active"
    assert [k for k, _ in window.factory.items()] == SCREENS


def test_tracker_screen_loads_saves_and_builds(window, seeded, tmp_path):
    screen = window.show("tracker")
    assert screen.week_var.get() == "" and "No week yet" in window.status_text()
    assert not screen.save("Outcomes").ok
    imported = seeded.execute("tracker", action="import", what=str(TRACKER_FIXTURE))
    assert imported.ok, imported.errors
    screen.refresh()
    assert screen.week_var.get() == "WEEK OF 10/26 - 11/01 · sprint 2" and window.week_start == "2026-10-26"
    assert len(screen.week_box["values"]) == 3 and screen.week_box["values"][-1] == "WEEK OF 10/12 - 10/18 · sprint 1"
    assert screen.note_var.get() == "Phase 2 closed 10/27; Phase 3 Sprint 2 opened 10/27"
    assert screen.pane_text("Outcomes").startswith("- Phase 2 closed on schedule on 10/27")
    assert screen.pane_text("Issues").startswith("Platform Safety Plan deliverables")
    jira = screen.jira.get("1.0", "end-1c")
    assert jira.startswith("Jira issues (project HWL, open items I am assigned, reported or watching, as of ")
    assert "  HWL-2554  Story  Perform Platform Safety Plan" in jira and str(screen.jira.cget("state")) == "disabled"
    assert not screen.is_dirty()
    screen.texts["Outcomes"].insert("end", "\n- Mentor meeting held.")
    assert screen.is_dirty()
    assert screen.save("Outcomes").ok and not screen.is_dirty()
    row = seeded.execute("list", entity="week", filter=["start=2026-10-26", "section=Outcomes"]).data[0]
    assert row["text"].endswith("\n- Mentor meeting held.")
    # a week of the closed sprint shows its frozen or empty Jira section, never a built one
    screen.week_var.set("WEEK OF 10/19 - 10/25 · sprint 1")
    screen._on_pick()
    assert window.week_start == "2026-10-19" and screen.jira.get("1.0", "end-1c") == ""
    assert screen.pane_text("Outcomes").startswith("- Integrated into the Wheel Loader daily stand-up")
    # build both files into the Brain's out_dir; Open on a non-interactive window only says so
    built = screen.build_text("week")
    assert built.ok and built.data["path"].endswith("tracker_week.txt")
    assert (tmp_path / "out" / "tracker_week.txt").is_file()
    assert window.status_text().startswith("Written:") and screen.open_primary() is False
    assert "Would open" in window.status_text()
    assert window.build_tracker("history").ok and window.current_key == "tracker"
    assert (tmp_path / "out" / "tracker_history.txt").read_text(encoding="utf-8").startswith("WHEEL LOADER")


def test_tracker_screen_new_week_joins_the_active_sprint(window, seeded):
    _sprint(seeded)
    screen = window.show("tracker")
    created = screen.new_week()
    assert created.ok, created.errors
    import datetime as dt

    from asi_kletz.generate.sprint_queries import week_start

    start = week_start(dt.date.today()).isoformat()
    assert window.week_start == start and screen.week_var.get().endswith("· sprint 1")
    assert screen.pane_text("Outcomes") == "-"
    again = screen.new_week()
    assert again.ok and again.warnings == ["that week already exists"]
    assert seeded.execute("count", entity="week").data["count"] == 1


# -- the hidden identity (0.9.0): no id, no order, no uid on any table; the details title names the row ----


def _trees(widget) -> list:
    from tkinter import ttk

    found = [widget] if isinstance(widget, ttk.Treeview) else []
    for child in widget.winfo_children():
        found.extend(_trees(child))
    return found


def test_no_table_on_any_screen_has_an_id_order_or_uid_column(window, seeded):
    """Owner, 2026-10-28: the leftmost ``order`` and ``id`` columns are vestigial; the uid is never shown."""
    from asi_kletz.gui.entity_screen import FROZEN, HANDLES, IDENTITY
    from asi_kletz.gui.matrix_screen import FIXED, FIXED_WIDTHS, SEARCHED

    assert FROZEN == ("plan",) and HANDLES == ("id", "order")
    assert IDENTITY == ("pdp_phase", "lifecycle_phase", "deliverable")
    assert FIXED == ("plan",) and FIXED_WIDTHS == (360,) and "order" in SEARCHED
    seen = 0
    for key in SCREENS:
        screen = window.show(key)
        for tree in _trees(screen):
            seen += 1
            columns = tuple(tree["columns"])
            assert not any(c in NEVER_COLUMNS for c in columns), (key, columns)
            assert not any(c in NEVER_COLUMNS for c in tree["displaycolumns"]), (key, tree["displaycolumns"])
            assert "entity_id" in columns or not any("id" in c.split("_") for c in columns), (key, columns)
    assert seen >= 9  # the dashboard's three, the two frozen pairs of the plan screens, the board's lanes, and more
    plan = window.show("safety_plan")
    assert plan.pane.frozen == ("plan",) and tuple(plan.pane.left["columns"]) == ("plan",)
    assert len(plan.tree["displaycolumns"]) == 59 and "uid" not in plan.tree["columns"]
    matrix = window.show("safety_plan_matrix")
    assert tuple(matrix.pane.left["columns"]) == ("plan",) and matrix.tree.set("1", "plan").strip() == "Safety Plan"
    matrix.search_var.set("2")  # a typed number still finds the row by its order
    assert [iid for iid, _ in _rows(matrix.tree)] == ["pdp:2", "phase:2:2. HARA / Risk Assessment", "2"]


def test_form_has_order_but_no_uid_and_the_details_title_names_the_row(window, seeded):
    from asi_kletz.gui.widgets import WidgetFactory
    from asi_kletz.schema import uid_field

    screen = window.show("safety_plan")
    assert "order" in screen.widgets and "uid" not in screen.widgets and "id" not in screen.widgets
    assert set(screen.widgets) == {f.name for f in screen.schema.visible_fields}
    with pytest.raises(ValueError, match="hidden"):
        WidgetFactory(seeded.lookups).create(screen.form.inner, uid_field())
    assert screen.form_box.cget("text") == "Safety Plan Row details"
    screen.select(2)
    assert screen.form_box.cget("text") == "Safety Plan Row details · row 2"
    assert window.status_text() == "Safety Plan Row 2 selected" and screen.widgets["order"].get() == "2"
    window.update()  # drain the selection events, as the loop does before a user can click the left tree
    screen.pane.left.selection_set("3")
    window.update()
    assert screen.form_box.cget("text") == "Safety Plan Row details · row 3" and screen.selected_id == 3
    # saving keeps the title on the saved row; the uid is untouched (the form never sends it)
    uid = screen.by_id[3]["uid"]
    screen.widgets["deadline"].set("soon")
    screen.save()
    assert screen.form_box.cget("text") == "Safety Plan Row details · row 3" and screen.by_id[3]["uid"] == uid
    assert seeded.execute("get", entity=PLAN, id=3).data["deadline"] == "soon"
    # duplicating makes a new row with a new uid and no order; the title names it once saved
    screen.duplicate()
    assert screen.form_box.cget("text") == "Safety Plan Row details" and screen.selected_id is None
    screen.widgets["order"].set("4")
    screen.save()
    assert screen.selected_id == 4 and screen.form_box.cget("text") == "Safety Plan Row details · row 4"
    copy = seeded.execute("get", entity=PLAN, id=4).data
    assert copy["deliverable"] == "Functional Safety Concept" and copy["uid"] != uid and copy["order"] == 4
    # deleting empties the form and the title
    screen.delete()
    assert screen.form_box.cget("text") == "Safety Plan Row details" and screen.selected_id is None
    assert seeded.execute("count", entity=PLAN).data["count"] == 3
    screen.new()
    assert screen.form_box.cget("text") == "Safety Plan Row details"


# -- the Holidays screen (0.10.0): the generic table and form, no stack, no frozen column ----------------


def test_holidays_screen_lists_the_loaded_rows_without_a_frozen_column(window, seeded):
    from tests.conftest import SEED_HOLIDAYS

    assert window.factory.title("holidays") == "Holidays" and SCREENS.index("holidays") == SCREENS.index("tracker") + 1
    screen = window.show("holidays")
    assert screen.columns == ["date", "name", "status", "note"] and not screen.stacked
    assert screen.pane.frozen == () and tuple(screen.tree["displaycolumns"]) == ("date", "name", "status", "note")
    assert screen.tree.get_children() == () and screen.columns_box is None  # no flag groups, no Columns box
    assert seeded.execute("holiday", action="load", file=str(SEED_HOLIDAYS), actor="agent").ok
    deadline = time.time() + 2
    while len(screen.tree.get_children()) != 52 and time.time() < deadline:
        window.update()
        time.sleep(0.02)
    first = screen.tree.get_children()[0]
    assert len(screen.tree.get_children()) == 52 and screen.tree.set(first, "name") == "New Year's Day"
    screen.select(int(screen.tree.get_children()[0]))
    assert screen.form_box.cget("text") == "Holiday details · row 1" and screen.widgets["status"].get() == "assumed"
    assert set(screen.widgets) == {"date", "name", "status", "note"}
    assert window.status_text() == "Holiday 1 selected"
