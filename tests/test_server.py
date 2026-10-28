"""The automation server against a real ``MainWindow`` over ``urllib``.

The Tk thread is the test thread, so every request runs on a helper thread while the test pumps
``window.update()``; the timeout test is the one that deliberately does not pump.
"""

from __future__ import annotations

import gc
import json
import os
import socket
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from collections import deque
from typing import Any

import pytest

from asi_kletz.automation.session import ENV_AUTOMATION, read_session, session_path
from tests.conftest import PLAN
from tests.test_gui import SCREENS, TITLES, _tk_available

pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")


@pytest.fixture
def window(seeded):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()


def _session() -> dict[str, Any]:
    return json.loads(session_path().read_text(encoding="utf-8"))


def _pump(window, until, timeout: float = 10.0) -> None:
    """Drive the Tk loop until ``until()`` is true; stops quietly once the window is destroyed."""
    deadline = time.time() + timeout
    while not until() and time.time() < deadline:
        try:
            window.update()
        except tk.TclError:
            break
        time.sleep(0.01)


def _send(url: str, method: str, body: Any, headers: dict[str, str], timeout: float, out: dict[str, Any]) -> None:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as answer:
            out["status"], out["body"] = answer.status, json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        out["status"], out["body"] = exc.code, json.loads(exc.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        out["error"] = exc


def _call(window, method: str, path: str, body: Any = None, *, token: str | None = None,
          headers: dict[str, str] | None = None, pump: bool = True, timeout: float = 10.0) -> tuple[int, dict]:
    """One request to the window's server from a helper thread; the Tk loop is pumped meanwhile."""
    session = _session()
    sent = {"Authorization": f"Bearer {session['token'] if token is None else token}"}
    sent.update(headers or {})
    out: dict[str, Any] = {}
    thread = threading.Thread(
        target=_send, args=(session["address"] + path, method, body, sent, timeout, out), daemon=True
    )
    thread.start()
    if pump:
        _pump(window, lambda: not thread.is_alive(), timeout + 2)
    thread.join(timeout + 2)
    assert not thread.is_alive(), f"{method} {path} did not finish"
    if "error" in out:
        raise out["error"]
    return out["status"], out["body"]


def _on_main(window, fn, timeout: float = 10.0):
    """Post ``fn`` through ``on_main`` from a helper thread and pump until it is answered."""
    out: dict[str, Any] = {}

    def go():
        try:
            out["value"] = window.server.on_main(fn, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    _pump(window, lambda: not thread.is_alive(), timeout + 2)
    thread.join(1)
    if "error" in out:
        raise out["error"]
    return out["value"]


# -- status and the session file -------------------------------------------------------------
def test_status_answers_with_the_window_facts(window, seeded):
    session = _session()
    assert session["tool"] == "asi_kletz" and session["pid"] == os.getpid() and len(session["token"]) == 32
    assert session["address"] == f"http://127.0.0.1:{session['port']}" and session["db"] == seeded.db_path
    assert session["started_at"] == window.server.started_at and read_session() is not None
    status, body = _call(window, "GET", "/status")
    assert status == 200 and body["ok"] and body["verb"] == "status"
    data = body["data"]
    assert data["tool"] == "asi_kletz" and data["pid"] == os.getpid() and data["db"] == seeded.db_path
    assert data["screen"] == "dashboard" and data["theme"] == {"key": "cyan-neon", "title": "Cyan Neon"}
    assert data["port"] == session["port"] == window.server.port and isinstance(data["events_seq"], int)
    assert data["requests"] >= 1 and data["uptime_s"] >= 0 and data["version"] == session["version"]
    assert data["lock"]["family"]["pid"] == os.getpid() and data["lock"]["database"]["db"] == seeded.db_path
    assert window.online_var.get() == f"◉ ONLINE :{window.server.port}"


def test_execute_read_verb_is_byte_equal_to_the_api(window, seeded):
    status, body = _call(window, "POST", "/execute", {"verb": "count", "args": {"entity": PLAN}, "actor": "agent"})
    assert status == 200
    assert body == {"ok": True, "verb": "count", "data": {"entity": PLAN, "count": 3}, "errors": [], "warnings": []}
    assert json.dumps(body, separators=(", ", ": ")) == seeded.execute("count", entity=PLAN).to_json(indent=None)


def test_execute_write_verb_refreshes_the_open_screen(window, seeded):
    screen = window.show("safety_plan")
    assert screen.tree.set("3", "status") == "Pending"
    status, body = _call(
        window, "POST", "/execute",
        {"verb": "update", "args": {"entity": PLAN, "id": 3, "data": {"status": "Done"}}, "actor": "agent"},
    )
    assert status == 200 and body["ok"] and body["data"]["status"] == "Done"
    _pump(window, lambda: screen.tree.set("3", "status") == "Done", 2)
    assert screen.tree.set("3", "status") == "Done"
    assert seeded.storage.audit_tail(1)[0]["actor"] == "agent"
    event = seeded.events.last(1)[0]
    assert event["topic"] == "entity.updated" and isinstance(event["seq"], int) and event["seq"] >= 1


def test_execute_without_an_actor_runs_as_agent_never_gui(window, seeded):
    _, body = _call(
        window, "POST", "/execute", {"verb": "create", "args": {"entity": PLAN, "data": {"deliverable": "remote"}}}
    )
    assert body["ok"], body["errors"]
    assert seeded.storage.audit_tail(1)[0]["actor"] == "agent"
    _, body = _call(window, "POST", "/execute", {"args": {"entity": PLAN}})
    assert not body["ok"] and "verb" in body["errors"][0]
    _, body = _call(window, "POST", "/execute", {"verb": "count", "args": [1]})
    assert not body["ok"] and "'args' must be an object" in body["errors"][0]


def test_jobs_run_on_the_main_thread(window):
    seen: dict[str, Any] = {}

    def job():
        seen["thread"] = threading.current_thread()
        return 42

    assert _on_main(window, job) == 42
    assert seen["thread"] is threading.main_thread()
    handler_threads = [t for t in threading.enumerate() if t.name == "asi-kletz-automation"]
    assert handler_threads and all(t.daemon and t is not threading.main_thread() for t in handler_threads)


def test_a_job_that_raises_is_a_500_result(window, monkeypatch):
    def boom():
        raise RuntimeError("no such screen widget")

    monkeypatch.setattr(window.server, "status_data", boom)
    status, body = _call(window, "GET", "/status")
    assert status == 500 and not body["ok"] and body["errors"] == ["RuntimeError: no such screen widget"]


# -- events ------------------------------------------------------------------------------------
def test_events_since_with_seq_limit_and_history_warning(window, seeded):
    seeded.execute("create", entity=PLAN, data={"deliverable": "a"}, actor="agent")
    seeded.execute("create", entity=PLAN, data={"deliverable": "b"}, actor="agent")
    latest = seeded.events.seq
    status, body = _call(window, "GET", "/events?since=0")
    assert status == 200 and body["ok"] and body["verb"] == "events"
    seqs = [e["seq"] for e in body["data"]["events"]]
    assert seqs == sorted(seqs) == list(range(1, latest + 1)) and body["data"]["seq"] == latest
    assert body["data"]["since"] == 0 and body["warnings"] == []
    assert body["data"]["events"][-1]["topic"] == "entity.created" and body["data"]["events"][-1]["actor"] == "agent"
    _, body = _call(window, "GET", f"/events?since={latest}")
    assert body["data"]["events"] == []
    _, body = _call(window, "GET", f"/events?since={latest - 1}")
    assert [e["seq"] for e in body["data"]["events"]] == [latest]
    _, body = _call(window, "GET", "/events?since=0&limit=1")
    assert [e["seq"] for e in body["data"]["events"]] == [1]
    status, body = _call(window, "GET", "/events?since=x")
    assert status == 400 and not body["ok"]
    # the history is bounded: once the oldest event has fallen out, an older `since` is warned about
    seeded.events.history = deque(seeded.events.history, maxlen=2)
    seeded.execute("create", entity=PLAN, data={"deliverable": "c"}, actor="agent")
    _, body = _call(window, "GET", "/events?since=0")
    assert len(body["data"]["events"]) == 2 and body["warnings"] and "no longer in the history" in body["warnings"][0]
    _, body = _call(window, "GET", f"/events?since={seeded.events.seq - 2}")
    assert len(body["data"]["events"]) == 2 and body["warnings"] == []


# -- puppeting -----------------------------------------------------------------------------------
def test_screen_shows_and_screens_marks_it(window):
    status, body = _call(window, "POST", "/screen", {"show": "safety_plan_matrix"})
    assert status == 200 and body["ok"] and body["verb"] == "screen"
    assert body["data"] == {"screen": "safety_plan_matrix", "title": "Safety Plan Matrix"}
    assert window.current_key == "safety_plan_matrix" and window.title().endswith("Safety Plan Matrix")
    assert window.nav.curselection() == (SCREENS.index("safety_plan_matrix"),)
    _, body = _call(window, "GET", "/screens")
    screens = body["data"]["screens"]
    assert [s["key"] for s in screens] == SCREENS and [s["title"] for s in screens] == TITLES
    assert [s["key"] for s in screens if s["current"]] == ["safety_plan_matrix"]
    status, body = _call(window, "POST", "/screen", {"show": "nope"})
    assert status == 200 and not body["ok"] and "unknown screen" in body["errors"][0]
    assert window.current_key == "safety_plan_matrix"
    _, body = _call(window, "POST", "/screen", {})
    assert not body["ok"] and "show" in body["errors"][0]


# -- remote theme ------------------------------------------------------------------------------
def test_remote_theme_recolours_the_window_and_the_badge(window, seeded):
    from asi_kletz.prefs import read_prefs

    server = window.server
    status, body = _call(window, "POST", "/execute", {"verb": "theme", "args": {"key": "pink-noir"}})
    assert status == 200 and body["ok"] and body["data"]["latched"] == "pink-noir"
    assert window.theme.key == "pink-noir" and window.badge_var.get() == "PINK NOIR"
    assert window.online_var.get().endswith(f":{server.port}") and window.server is server
    assert read_prefs()["theme"] == "pink-noir"
    assert window.nav.size() == len(SCREENS) and window.current_key == "dashboard"
    assert seeded.events.last(1)[0]["actor"] == "agent"
    _, body = _call(window, "GET", "/status")  # the server survived the rebuild
    assert body["data"]["theme"]["key"] == "pink-noir"


def test_remote_theme_is_refused_on_a_dirty_screen_without_a_dialog(window, monkeypatch):
    from asi_kletz.prefs import read_prefs

    window.show("safety_plan")
    monkeypatch.setattr(window.current, "is_dirty", lambda: True, raising=False)
    monkeypatch.setattr(window, "confirm", lambda *a, **k: pytest.fail("a remote pick must never prompt"))
    status, body = _call(window, "POST", "/execute", {"verb": "theme", "args": {"key": "green-day"}})
    assert status == 200 and not body["ok"] and body["verb"] == "theme"
    assert "refused" in body["errors"][0] and "safety_plan" in body["errors"][0]
    assert body["warnings"] == ["save or discard the edits, then retry"]
    assert window.theme.key == "cyan-neon" and "theme" not in read_prefs()
    assert window.remote_guard("theme", {"key": "green-day"}) is not None
    assert window.remote_guard("theme", {}) is None and window.remote_guard("count", {"entity": PLAN}) is None
    _, body = _call(window, "POST", "/execute", {"verb": "theme", "args": {}})  # listing is not a change
    assert body["ok"] and len(body["data"]["themes"]) == 32


def test_gui_verb_is_refused_through_the_server(window):
    status, body = _call(window, "POST", "/execute", {"verb": "gui"})
    assert status == 200 and not body["ok"] and body["errors"] == ["the window is already open"]


def test_document_builds_through_the_server_on_the_tk_thread(window, seeded, tmp_path):
    window.show("transfer")
    out = tmp_path / "plan"
    status, body = _call(
        window, "POST", "/execute", {"verb": "document", "args": {"name": "safety_plan", "out": str(out)}},
        timeout=120,
    )
    assert status == 200 and body["ok"], body["errors"]
    assert body["data"]["name"] == "safety_plan" and (out / "safety_plan.pdf").is_file()
    assert seeded.storage.audit_tail(1)[0]["actor"] == "agent"
    assert seeded.events.last(1)[0]["topic"] == "generated"


# -- transport refusals ------------------------------------------------------------------------
def test_bad_token_origin_method_body_and_path(window):
    status, body = _call(window, "GET", "/status", token="0" * 32)
    assert status == 401 and body == {"ok": False, "verb": None, "data": None, "errors": ["bad token"], "warnings": []}
    status, body = _call(window, "GET", "/status", token="")
    assert status == 401 and body["errors"] == ["bad token"]
    status, body = _call(window, "GET", "/status", headers={"Origin": "http://evil.example"})
    assert status == 403 and not body["ok"]
    status, body = _call(window, "GET", "/execute")
    assert status == 405 and not body["ok"]
    status, body = _call(window, "POST", "/execute", [1, 2])
    assert status == 400 and not body["ok"]
    status, body = _call(window, "POST", "/execute", "{not json", headers={"Content-Type": "application/json"})
    assert status == 400 and not body["ok"]
    status, body = _call(window, "GET", "/nope")
    assert status == 404 and not body["ok"]
    _, body = _call(window, "GET", "/status")
    assert body["data"]["requests"] >= 8  # every request counts, refused ones included


def test_a_slow_window_answers_504_and_the_job_still_runs(window):
    window.server.job_timeout = 0.2
    status, body = _call(window, "POST", "/execute", {"verb": "theme", "args": {"key": "gold-day"}}, pump=False)
    assert status == 504 and not body["ok"] and "did not answer" in body["errors"][0]
    assert window.theme.key == "cyan-neon"
    _pump(window, lambda: window.theme.key == "gold-day", 2)
    assert window.theme.key == "gold-day" and window.badge_var.get() == "GOLD DAY"


# -- lifecycle -----------------------------------------------------------------------------------
def test_quit_closes_the_window_and_removes_the_session(window):
    status, body = _call(window, "POST", "/quit")
    assert status == 200 and body == {"ok": True, "verb": "quit", "data": {"quit": True}, "errors": [], "warnings": []}
    _pump(window, lambda: not session_path().exists(), 2)
    assert not session_path().exists() and window.server is None
    with pytest.raises(tk.TclError):
        window.winfo_exists()


def test_no_server_and_automation_off_write_no_file(seeded, monkeypatch):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False, server=False)
    win.withdraw()
    try:
        assert win.server is None and not session_path().exists() and win.online_var.get() == "◉ ONLINE"
        assert win.badge_var.get() == "CYAN NEON"
    finally:
        win.close()
        del win
        gc.collect()
    monkeypatch.setenv(ENV_AUTOMATION, "off")
    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    try:
        assert win.server is None and not session_path().exists() and win.online_var.get() == "◉ ONLINE"
        win.about()
        assert "Automation: off" in win.status_text()
    finally:
        win.close()
        del win
        gc.collect()


def test_close_removes_the_session_and_the_port_refuses(seeded):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    port = win.server.port
    assert session_path().exists() and read_session()["port"] == port
    win.about()
    assert f"http://127.0.0.1:{port}" in win.status_text()
    win.close()
    win.close()  # idempotent
    del win
    gc.collect()
    assert not session_path().exists() and read_session() is None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
    assert not [t for t in threading.enumerate() if t.name == "asi-kletz-automation"]


def test_a_stale_session_of_another_window_is_left_alone(seeded):
    from asi_kletz.automation.session import clear_session, write_session
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    try:
        write_session(port=1, token="x" * 32, db=None, started_at="2026-10-27T00:00:00Z")  # our pid: overwritten
        assert read_session()["port"] == 1
    finally:
        win.close()
        del win
        gc.collect()
    assert not session_path().exists()
    write_session(port=2, token="y" * 32, db=None, started_at="2026-10-27T00:00:00Z")
    clear_session(pid=os.getpid() + 1)  # another pid: not ours to remove
    assert session_path().exists()
    clear_session()
    assert not session_path().exists()


# -- the session verb, in process ---------------------------------------------------------------
def test_session_verb_reports_the_open_window_without_the_token(window, capsys):
    from asi_kletz.automation.cli import main

    window.show("safety_plan")
    assert main(["session"]) == 0
    out = capsys.readouterr().out
    body = json.loads(out)
    data = body["data"]
    assert body["ok"] and data["present"] and data["alive"] and data["reachable"]
    assert data["session"]["pid"] == os.getpid() and data["session"]["port"] == window.server.port
    assert data["status"]["screen"] == "safety_plan" and data["quit"] is False
    assert "token" not in out and _session()["token"] not in out
    assert data["path"] == str(session_path())
    through = window.brain.execute("session")  # callable in process too: the window's own session
    assert through.ok and through.data["reachable"] and through.data["session"]["pid"] == os.getpid()


def test_session_quit_closes_the_window_then_fails_the_second_time(window, capsys):
    from asi_kletz.automation.cli import main

    assert main(["session", "--quit"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] and body["data"]["quit"] is True
    _pump(window, lambda: not session_path().exists(), 2)
    assert not session_path().exists()
    assert main(["session", "--quit"]) == 1
    body = json.loads(capsys.readouterr().out)
    assert not body["ok"] and "no live automation session" in body["errors"][0] and body["data"]["present"] is False
