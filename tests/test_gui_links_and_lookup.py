"""0.20.0 in the window: the work product URLs editor with its links and Open button (``webbrowser.open``
monkeypatched), and the Look up button beside each role's people editor, the Outlook search on a worker
thread (the COM function monkeypatched; nothing here launches Outlook)."""

from __future__ import annotations

import gc
import json
import threading

import pytest

from asi_kletz.services import outlook_service as outlook
from asi_kletz.services.outlook_service import NO_OUTLOOK, OutlookUnavailable
from tests.conftest import PLAN
from tests.test_gui import _tk_available

pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")


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

MS = "https://www.microsoft.com/"
A = "https://dms.example.com/doc/17"
B = "http://jama.example.com/items/2554"
ANN = "Ann Lee <ann.lee@asirobots.com>"
ZED = "Zed Young <zed.young@asirobots.com>"


@pytest.fixture
def com(monkeypatch):
    """The COM call replaced: two matches, the thread of every call recorded; ``com.failure`` makes it refuse."""

    class Com:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.threads: list[threading.Thread] = []
            self.failure: Exception | None = None
            self.gate: threading.Event | None = None  # set by a test that wants to look at a search in flight

        def __call__(self, text, timeout=outlook.TIMEOUT, limit=outlook.LIMIT):
            self.calls.append(text)
            self.threads.append(threading.current_thread())
            if self.gate is not None:
                assert self.gate.wait(5.0), "the test never opened the gate"
            if self.failure is not None:
                raise self.failure
            return json.dumps([
                {"name": "Zed Young", "email": "zed.young@asirobots.com"},
                {"name": "Ann Lee", "email": "ann.lee@asirobots.com"},
            ])

    stub = Com()
    monkeypatch.setattr(outlook, "run_outlook", stub)
    return stub


@pytest.fixture
def pane(window, seeded, tmp_path, monkeypatch):
    """The Safety Plan screen with row 1 on a standard that has a role parameter (``fusa_engineer``)."""
    from tests.test_standards import SOURCE

    root = tmp_path / "standards"
    (root / "qf-17-test").mkdir(parents=True)
    (root / "qf-17-test" / "qf-17-test.md").write_text(SOURCE, encoding="utf-8")
    monkeypatch.setenv("ASI_KLETZ_STANDARDS", str(root))
    screen = window.show("safety_plan")
    screen.select(1)
    assert list(screen.param_texts) == ["fusa_engineer"] and list(screen.lookup_buttons) == ["fusa_engineer"]
    return screen


def test_urls_editor_shows_the_links_and_open_launches_the_first(window, seeded, monkeypatch):
    from asi_kletz.gui.entity_screen import cell_text
    from asi_kletz.gui.widgets import OPEN, THE_LINK, UrlsWidget

    opened: list[str] = []
    monkeypatch.setattr("asi_kletz.gui.widgets.webbrowser.open", lambda url: opened.append(url) or True)
    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [MS, A]}).ok
    screen = window.show("safety_plan")
    widget = screen.widgets["urls"]
    assert isinstance(widget, UrlsWidget) and widget.open_button.cget("text") == OPEN
    assert "urls" in screen.columns and screen.schema.field("urls").header == "Work product URLs"
    screen.select(3)  # no URL: nothing to open, no links
    assert widget.get() is None and widget.link_labels == [] and str(widget.open_button.cget("state")) == "disabled"
    assert widget.open_first() is None and opened == []
    screen.select(1)  # two URLs, in the order stored; the first marked as the link; the kind as a prefix (0.22.0)
    assert widget.get() == f"{MS}\n{A}"
    assert [str(label.cget("text")) for label in widget.link_labels] == [f"placeholder: {MS}" + THE_LINK, f"other: {A}"]
    assert str(widget.open_button.cget("state")) == "normal"
    assert widget.open_first() == MS and opened == [MS]  # Open: the first in the browser
    widget.open_url(A)  # a click on any other line: that one
    assert opened == [MS, A]
    cells = dict(zip(["plan", *screen.columns], screen.tree.item("1")["values"], strict=True))  # stacked first
    assert cells["urls"] == f"{MS}; {A}" and cell_text(screen.schema.field("urls"), [B, A]) == f"{B}; {A}"
    # typed in another order and saved: the order kept exactly as typed, through the same verb an agent uses
    widget.set(f"{B}\n{MS}")
    assert [str(label.cget("text")) for label in widget.link_labels] == [f"other: {B}" + THE_LINK, f"placeholder: {MS}"]
    screen.save()
    assert window.status_text() == "Saved safety plan row 1"
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [B, MS]
    assert widget.get() == f"{B}\n{MS}" and widget.urls() == [B, MS]
    widget.set(f"{B}\nnope")  # a bad line: refused by the verb, named in the status bar; nothing changes
    screen.save()
    assert window.status_text() == (
        "Error: urls, line 2 ('nope'): not an absolute http(s) URL; write an absolute http(s) URL, one per line"
    )
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [B, MS]
    widget.set(None)
    screen.save()
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] is None and widget.link_labels == []


def test_look_up_searches_outlook_off_the_tk_thread_and_inserts_the_pick(pane, window, seeded, com):
    from asi_kletz.gui.people_lookup import INSERT, SEARCHING, TITLE, PeopleLookup
    from asi_kletz.gui.widgets import LOOK_UP

    assert com.calls == []  # nothing searched on show or select: no search without a press
    button = pane.lookup_buttons["fusa_engineer"]
    assert button.cget("text") == LOOK_UP
    button.invoke()
    dialog = pane.lookup_window
    assert isinstance(dialog, PeopleLookup) and dialog.title() == TITLE and dialog.winfo_exists()
    assert com.calls == [] and dialog.insert_button.instate(["disabled"])
    assert dialog.insert_button.cget("text") == INSERT
    assert dialog.search() is False and com.calls == []  # an empty box searches nothing
    dialog.query_var.set("ann")
    com.gate = threading.Event()  # hold the worker: the search is in flight
    assert dialog.search() is True and dialog.searching and window.status_text() == SEARCHING
    assert dialog.search_button.instate(["disabled"])
    assert dialog.search() is False  # a second press while one runs is ignored
    com.gate.set()
    result = dialog.wait_search()
    assert result is not None and result.ok and result.data["count"] == 2
    assert com.calls == ["ann"] and com.threads[0] is not threading.main_thread()  # off the Tk thread
    assert [dialog.listbox.get(i) for i in range(dialog.listbox.size())] == [ZED, ANN]
    assert not dialog.insert_button.instate(["disabled"]) and dialog.listbox.curselection() == (0,)
    assert not dialog.search_button.instate(["disabled"])
    assert window.status_text() == "2 match(es) for 'ann'; pick one and press Insert"
    assert dialog.insert_selected() == ZED  # the first match, into the role's box, on a line of its own
    assert pane.people_text_of("fusa_engineer") == ZED and window.status_text() == f"Inserted {ZED}"
    dialog.listbox.selection_clear(0, "end")
    dialog.listbox.selection_set(1)
    assert dialog.insert_selected() == ANN and pane.people_text_of("fusa_engineer") == f"{ZED}\n{ANN}"
    assert dialog.winfo_exists()  # the window stays for another pick
    # Save parameters writes the lines through the verb, which sorts them; nothing else was stored by the lookup
    pane.save_parameters()
    assert window.status_text() == "Saved 1 parameter(s)"
    rows = {r["name"]: r for r in seeded.execute("list", entity="parameter").data}
    assert [p["name"] for p in rows["fusa_engineer"]["people"]] == ["Ann Lee", "Zed Young"]
    assert len(rows) == 1 and len(com.calls) == 1
    # a second press (the pane was rebuilt by the save, so its button is new) brings the same window back
    pane.lookup_buttons["fusa_engineer"].invoke()
    assert pane.lookup_window is dialog
    dialog.destroy()
    assert not dialog.winfo_exists()


def test_a_refused_lookup_leaves_one_line_and_the_editor_usable(pane, window, com):
    com.failure = OutlookUnavailable(NO_OUTLOOK + "Retrieving the COM class factory failed")
    pane.lookup_buttons["fusa_engineer"].invoke()
    dialog = pane.lookup_window
    dialog.query_var.set("Roy")
    assert dialog.search()
    result = dialog.wait_search()
    assert result is not None and not result.ok
    line = NO_OUTLOOK + "Retrieving the COM class factory failed"
    assert window.status_text() == f"Error: {line}" and dialog.status_var.get() == line
    assert dialog.listbox.size() == 0 and dialog.insert_button.instate(["disabled"])
    assert dialog.insert_selected() is None
    assert not dialog.search_button.instate(["disabled"])  # another try is allowed
    box = pane.param_texts["fusa_engineer"]
    assert str(box.cget("state")) == "normal"  # the editor is still usable
    box.insert("end", ANN)
    assert pane.people_text_of("fusa_engineer") == ANN
    com.failure = None
    dialog.query_var.set("ann")
    assert dialog.search() and dialog.wait_search().ok and dialog.listbox.size() == 2
    assert dialog.insert_selected() == ZED and pane.people_text_of("fusa_engineer") == f"{ANN}\n{ZED}"


def test_the_parameters_screen_looks_up_people_for_a_role(window, seeded, com):
    from asi_kletz.gui.people_lookup import PeopleLookup
    from asi_kletz.gui.widgets import LOOK_UP

    screen = window.show("parameters")
    people = screen.widgets["people"]
    assert people.lookup_button is not None and people.lookup_button.cget("text") == LOOK_UP
    screen.new()
    screen.widgets["name"].set("vehicle_type")  # not a role: the box and its button are greyed
    assert people.lookup_button.instate(["disabled"]) and people.look_up() is None
    assert screen.lookup_window is None and com.calls == []
    screen.widgets["name"].set("robot_chief")
    assert not people.lookup_button.instate(["disabled"])
    dialog = people.look_up()
    assert isinstance(dialog, PeopleLookup) and screen.lookup_window is dialog
    dialog.query_var.set("zed")
    assert dialog.search() and dialog.wait_search().ok
    assert dialog.insert_selected() == ZED and people.get() == ZED
    screen.save()
    assert window.status_text().startswith("Saved parameter")
    row = seeded.execute("get", entity="parameter", id=screen.selected_id).data
    assert row["people"] == [{"name": "Zed Young", "email": "zed.young@asirobots.com"}] and row["value"] is None
    assert com.calls == ["zed"]
    dialog.destroy()  # Close: gone; the editor keeps the line
    assert not dialog.winfo_exists() and people.get() == ZED
