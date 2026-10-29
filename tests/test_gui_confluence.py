"""0.23.0 in the window: the Find page button beside the work product URLs box and its window (the Confluence
search on a worker thread, the fetch monkeypatched; nothing here reaches Confluence), and the dashboard's work
product tile. No page body is shown in Kletz."""

from __future__ import annotations

import gc
import threading

import pytest

from asi_kletz.commands import Result
from asi_kletz.services.confluence_service import ConfluenceService
from tests.conftest import PLAN
from tests.test_gui import _tk_available

pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")

SITE = "https://asirobots.atlassian.net"
PAGE = "399343803"
CHILD = "5763236170"
WIKI = f"{SITE}/wiki/spaces/STPA/pages/{PAGE}/Locator+Safety+Function+STPA"
CHILD_WIKI = f"{SITE}/wiki/spaces/STPA/pages/{CHILD}/Low-precision+GPS+loss+scenario+details"
VIEW = f"{SITE}/wiki/pages/viewpage.action?pageId={PAGE}"
MS = "https://www.microsoft.com/"
NO_SESSION = "no Atlassian session for this account; run `asi-hopper auth login` once"
SAMPLE = {
    "text": "Locator", "cql": 'title ~ "Locator" AND type = page ORDER BY lastmodified DESC', "space": "STPA",
    "limit": 25, "fetched_at": "2026-10-29T20:00:00+00:00", "count": 2,
    "pages": [
        {"id": PAGE, "title": "Locator Safety Function STPA", "space_key": "STPA", "url": WIKI,
         "last_modified": "2021-10-20T20:49:25.061Z", "excerpt": None},
        {"id": CHILD, "title": "Low-precision GPS loss scenario details", "space_key": "STPA", "url": CHILD_WIKI,
         "last_modified": "2021-09-13T13:28:47.933Z", "excerpt": "[synthetic]"},
    ],
}


@pytest.fixture
def window(seeded):
    """The window of ``tests/test_gui.py``, the same way: headless, withdrawn, closed and collected after."""
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()


class FakeRun:
    """A stand-in for ``window.execute_quiet``: answers ``confluence search`` from SAMPLE or fails, on the worker
    thread where the real one runs, never touching Tk; any other verb goes to the real Brain."""

    def __init__(self, window) -> None:
        self.window = window
        self.args: list[dict] = []
        self.threads: list[threading.Thread] = []
        self.gate: threading.Event | None = None
        self.failure: str | None = None

    def __call__(self, verb, **args) -> Result:
        if verb != "confluence":
            return self.window.brain.execute(verb, args, actor="gui")
        self.args.append(args)
        self.threads.append(threading.current_thread())
        if self.gate is not None:
            assert self.gate.wait(5.0), "the test never opened the gate"
        if self.failure:
            return Result.failure(self.failure, verb=verb)
        return Result.success(dict(SAMPLE, text=args.get("target"), space=args.get("space")), verb=verb)


@pytest.fixture
def fake(window, monkeypatch):
    stub = FakeRun(window)
    monkeypatch.setattr(window, "execute_quiet", stub)
    return stub


@pytest.fixture
def session(monkeypatch):
    """Hopper holds a session: the probe says so without reading anything (the suite's default is False)."""
    monkeypatch.setattr(ConfluenceService, "has_session", lambda self: True)


def test_find_page_searches_off_the_tk_thread_and_inserts_the_url(window, seeded, fake, session):
    from asi_kletz.gui.page_lookup import INSERT, SEARCHING, TITLE, PageLookup, hit_text
    from asi_kletz.gui.widgets import FIND_PAGE, THE_LINK, UrlsWidget

    screen = window.show("safety_plan")
    widget = screen.widgets["urls"]
    assert isinstance(widget, UrlsWidget) and widget.find_button is not None
    assert widget.find_button.cget("text") == FIND_PAGE and not widget.find_button.instate(["disabled"])
    screen.select(1)
    assert fake.args == []  # nothing searched on show or select: no search without a press
    widget.find_button.invoke()
    dialog = screen.page_window
    assert isinstance(dialog, PageLookup) and dialog.title() == TITLE and dialog.winfo_exists()
    assert dialog.space_var.get() == "STPA" and list(dialog.space_combo.cget("values")) == ["STPA"]
    assert dialog.insert_button.cget("text") == INSERT and dialog.insert_button.instate(["disabled"])
    assert dialog.search() is False and fake.args == []  # an empty box searches nothing
    dialog.query_var.set("Locator")
    fake.gate = threading.Event()  # hold the worker: the search is in flight
    assert dialog.search() is True and dialog.searching and window.status_text() == SEARCHING
    assert dialog.search_button.instate(["disabled"])
    assert dialog.search() is False  # a second press while one runs is ignored
    fake.gate.set()
    result = dialog.wait_search()
    assert result is not None and result.ok and result.data["count"] == 2
    assert fake.args == [{"action": "search", "target": "Locator", "space": "STPA"}]
    assert fake.threads[0] is not threading.main_thread()  # off the Tk thread
    assert [dialog.listbox.get(i) for i in range(dialog.listbox.size())] == [hit_text(p) for p in SAMPLE["pages"]]
    assert dialog.listbox.get(0) == "Locator Safety Function STPA  ·  STPA  ·  2021-10-20"
    assert not dialog.insert_button.instate(["disabled"]) and dialog.listbox.curselection() == (0,)
    assert not dialog.search_button.instate(["disabled"])
    assert window.status_text() == "2 page(s) for 'Locator' in STPA; pick one and press Insert"
    assert dialog.insert_selected() == WIKI  # the first hit's URL, on a line of its own in the URLs box
    assert widget.get() == WIKI and widget.urls() == [WIKI] and window.status_text() == f"Inserted {WIKI}"
    assert [str(label.cget("text")) for label in widget.link_labels] == [f"confluence: {WIKI}" + THE_LINK]
    dialog.listbox.selection_clear(0, "end")
    dialog.listbox.selection_set(1)
    assert dialog.insert_selected() == CHILD_WIKI and widget.get() == f"{WIKI}\n{CHILD_WIKI}"
    assert dialog.winfo_exists()  # the window stays for another pick; no page body anywhere in it
    assert not any("HAZARD" in dialog.listbox.get(i) for i in range(dialog.listbox.size()))
    # Save writes the lines through the same verb an agent uses; the pick alone stored nothing
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] is None
    screen.save()
    assert window.status_text() == "Saved safety plan row 1"
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [WIKI, CHILD_WIKI]
    # another space, typed: the search carries it; a second press brings the same window back
    dialog.space_var.set("fst")
    assert dialog.search() and dialog.wait_search().ok
    assert fake.args[-1] == {"action": "search", "target": "Locator", "space": "FST"}
    widget.find_button.invoke()
    assert screen.page_window is dialog
    dialog.destroy()
    assert not dialog.winfo_exists()
    assert len(fake.args) == 2


def test_find_page_is_greyed_without_a_session(window, fake):
    from asi_kletz.gui.widgets import FIND_PAGE

    screen = window.show("safety_plan")  # the suite's default: the probe says no session
    widget = screen.widgets["urls"]
    assert widget.find_button is not None and widget.find_button.cget("text") == FIND_PAGE
    assert widget.find_button.instate(["disabled"]) and widget.find_enabled is False
    assert widget.find_page() is None and screen.page_window is None and fake.args == []
    widget.find_button.invoke()  # a disabled ttk button runs nothing
    assert screen.page_window is None and fake.args == []


def test_a_refused_search_is_one_line_and_the_editor_stays_usable(window, seeded, fake, session):
    screen = window.show("safety_plan")
    screen.select(2)
    widget = screen.widgets["urls"]
    widget.set([MS])
    fake.failure = NO_SESSION
    dialog = widget.find_page()
    dialog.query_var.set("Locator")
    assert dialog.search()
    result = dialog.wait_search()
    assert result is not None and not result.ok
    assert window.status_text() == f"Error: {NO_SESSION}" and dialog.status_var.get() == NO_SESSION
    assert dialog.listbox.size() == 0 and dialog.insert_button.instate(["disabled"])
    assert dialog.insert_selected() is None and widget.get() == MS  # the editor untouched
    assert not dialog.search_button.instate(["disabled"])  # another try is allowed
    fake.failure = None
    assert dialog.search() and dialog.wait_search().ok and dialog.listbox.size() == 2
    assert dialog.insert_selected() == WIKI and widget.get() == f"{MS}\n{WIKI}"
    dialog.destroy()  # Close: gone; the editor keeps the line
    assert not dialog.winfo_exists() and widget.get() == f"{MS}\n{WIKI}"


def test_the_dashboard_counts_where_the_work_products_point(window, seeded):
    from asi_kletz.gui.dashboard import LINK_TILES, LINK_TITLE

    dash = window.current
    assert dash.key == "dashboard" and dash.link_tiles.cget("text") == LINK_TITLE
    assert [k for k, _ in LINK_TILES] == ["confluence", "placeholder", "none"]
    assert {k: v.get() for k, v in dash._link_vars.items()} == {"confluence": "0", "placeholder": "0", "none": "3"}
    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [VIEW]}).ok
    assert seeded.execute("update", entity=PLAN, id=2, data={"urls": [MS]}).ok
    dash.refresh()
    assert {k: v.get() for k, v in dash._link_vars.items()} == {"confluence": "1", "placeholder": "1", "none": "1"}
    assert seeded.execute("update", entity=PLAN, id=3, data={"urls": [MS, WIKI]}).ok  # both at once
    dash.refresh()
    assert {k: v.get() for k, v in dash._link_vars.items()} == {"confluence": "2", "placeholder": "2", "none": "0"}
    tile = dash.link_tiles.winfo_children()[0]
    tile.event_generate("<Button-1>")
    window.update()
    assert window.current.key == "safety_plan"  # a click opens the plan
