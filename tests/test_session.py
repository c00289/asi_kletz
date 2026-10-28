"""The session file, pid liveness, and the CLI forwarding to a running window.

Forwarding needs a lock refusal that names a live Kletz window: ``Brain`` is monkeypatched to
raise ``PrimaryToolBusy`` with the holder a real window of this process would write, and the
window with its server is real. ``main()`` then runs on a helper thread while the test, which
is the Tk thread, pumps the window. The sister tool's name appears here only as the holder of a
simulated refusal, spelled in two parts as the lock tests do.
"""

from __future__ import annotations

import gc
import json
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from typing import Any

import pytest

from asi_kletz.automation.session import (
    ENV_SESSION,
    SessionUnreachable,
    automation_enabled,
    clear_session,
    forward,
    pid_alive,
    probe,
    read_session,
    session_path,
    write_session,
)
from asi_kletz.prefs import prefs_path
from tests.conftest import PLAN

SISTER = "asi_" + "dewey"


def _finished_pid() -> int:
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    pid = int(proc.stdout.strip())
    assert proc.returncode == 0
    return pid


# -- the file ----------------------------------------------------------------------------------
def test_session_path_is_the_override_during_tests_and_beside_prefs_otherwise(tmp_path, monkeypatch):
    assert session_path() == tmp_path / "session.json" and os.environ[ENV_SESSION] == str(session_path())
    monkeypatch.delenv(ENV_SESSION)
    assert session_path() == prefs_path().with_name("session.json")
    assert session_path().parent == prefs_path().parent
    assert automation_enabled()


def test_write_read_and_clear(tmp_path):
    file = write_session(port=51234, token="ab" * 16, db=str(tmp_path / "k.db"), started_at="2026-10-27T17:02:11Z")
    assert file == session_path() and file.is_file()
    raw = json.loads(file.read_text(encoding="utf-8"))
    assert raw == {
        "tool": "asi_kletz", "version": raw["version"], "pid": os.getpid(), "started_at": "2026-10-27T17:02:11Z",
        "host": "127.0.0.1", "port": 51234, "address": "http://127.0.0.1:51234", "token": "ab" * 16,
        "db": str(tmp_path / "k.db"),
    }
    session = read_session()
    assert session is not None and session["pid"] == os.getpid() and session["token"] == "ab" * 16
    clear_session(os.getpid() + 1)  # another pid: left alone
    assert file.exists()
    clear_session()
    assert not file.exists() and read_session() is None
    clear_session()  # nothing to do


def test_read_session_is_none_for_missing_corrupt_foreign_or_dead(tmp_path):
    assert read_session() is None
    session_path().write_text("{not json", encoding="utf-8")
    assert read_session() is None
    session_path().write_text("[1, 2]", encoding="utf-8")
    assert read_session() is None
    good = {"tool": "asi_kletz", "pid": os.getpid(), "port": 1, "token": "t" * 32, "address": "http://127.0.0.1:1"}
    session_path().write_text(json.dumps(good | {"tool": SISTER}), encoding="utf-8")
    assert read_session() is None
    session_path().write_text(json.dumps(good | {"pid": _finished_pid()}), encoding="utf-8")
    assert read_session() is None
    session_path().write_text(json.dumps(good | {"token": ""}), encoding="utf-8")
    assert read_session() is None
    session_path().write_text(json.dumps(good), encoding="utf-8")
    assert read_session() == good | {"host": "127.0.0.1"}


def test_pid_alive():
    assert pid_alive(os.getpid())
    assert not pid_alive(_finished_pid())
    assert not pid_alive(0) and not pid_alive(-1)


def test_probe_and_forward_need_a_listening_server(tmp_path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    session = {"pid": os.getpid(), "port": port, "token": "t" * 32, "address": f"http://127.0.0.1:{port}"}
    assert probe(session, timeout=0.5) is None
    with pytest.raises(SessionUnreachable):
        forward(session, "count", {"entity": PLAN}, timeout=0.5)


# -- forwarding ----------------------------------------------------------------------------------
pytest.importorskip("asi_kletz.locks")
from asi_kletz.locks import PrimaryToolBusy  # noqa: E402
from tests.test_gui import _tk_available  # noqa: E402


def _refusing_brain(monkeypatch, holder: dict[str, Any] | None, slot: str = "family") -> None:
    class RefusedBrain:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise PrimaryToolBusy(slot, holder)

    monkeypatch.setattr("asi_kletz.brain.Brain", RefusedBrain)


def _run(argv: list[str], capsys, window=None, timeout: float = 15.0) -> tuple[int, dict, str]:
    """``main(argv)`` on a helper thread (the test thread is the Tk thread); pumps ``window`` meanwhile."""
    from asi_kletz.automation.cli import main

    out: dict[str, Any] = {}

    def go():
        try:
            out["code"] = main(argv)
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while thread.is_alive() and time.time() < deadline:
        if window is not None:
            try:
                window.update()
            except tk.TclError:
                pass
        time.sleep(0.01)
    thread.join(1)
    assert not thread.is_alive(), f"main({argv}) did not finish"
    if "error" in out:
        raise out["error"]
    captured = capsys.readouterr()
    return out["code"], json.loads(captured.out), captured.err


@pytest.fixture
def window(seeded):
    if not _tk_available():
        pytest.skip("no display for tkinter")
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()


def _own_holder() -> dict[str, Any]:
    return {"tool": "asi_kletz", "pid": os.getpid(), "started_at": "2026-10-27T17:02:11Z"}


def test_same_tool_refusal_forwards_to_the_live_window(window, seeded, capsys, monkeypatch):
    _refusing_brain(monkeypatch, _own_holder())
    code, body, err = _run(["count", PLAN], capsys, window)
    assert code == 0 and err == ""
    assert body == {"ok": True, "verb": "count", "data": {"entity": PLAN, "count": 3}, "errors": [], "warnings": []}
    code, body, _ = _run(["--compact", "create", PLAN, "--set", "deliverable=from the CLI"], capsys, window)
    assert code == 0 and body["ok"] and body["data"]["deliverable"] == "from the CLI"
    assert seeded.storage.audit_tail(1)[0]["actor"] == "cli"
    code, body, _ = _run(["--actor", "robot", "get", PLAN, "42"], capsys, window)
    assert code == 1 and not body["ok"] and body["verb"] == "get"
    code, body, _ = _run(["--actor", "robot", "update", PLAN, "1", "--set", "status=Done"], capsys, window)
    assert code == 0 and seeded.storage.audit_tail(1)[0]["actor"] == "robot"
    code, body, _ = _run(["theme", "pink-noir"], capsys, window)  # the first verb that recolours a running window
    assert code == 0 and window.theme.key == "pink-noir" and window.badge_var.get() == "PINK NOIR"


def test_sister_tool_refusal_is_exit_3_and_never_reaches_the_server(window, capsys, monkeypatch):
    holder = {"tool": SISTER, "pid": 4321, "started_at": "2026-10-27T17:02:11Z", "db": "C:/somewhere/sister.db"}
    _refusing_brain(monkeypatch, holder)
    before = window.server.requests
    code, body, _ = _run(["count", PLAN], capsys, window)
    assert code == 3 and not body["ok"] and body["verb"] == "count"
    assert body["data"] == {"slot": "family", "holder": holder} and body["data"]["holder"]["tool"] == SISTER
    assert body["errors"][0].startswith(f"{SISTER} is running (pid 4321") and "automation" not in body["errors"][0]
    assert window.server.requests == before


def test_unknown_holder_is_exit_3(window, capsys, monkeypatch):
    _refusing_brain(monkeypatch, None)
    code, body, _ = _run(["status"], capsys, window)
    assert code == 3 and body["data"] == {"slot": "family", "holder": None} and "holder unknown" in body["errors"][0]


def test_wrong_pid_in_the_session_file_is_exit_3_with_the_hint(window, capsys, monkeypatch):
    holder = _own_holder() | {"pid": os.getpid() + 1}
    _refusing_brain(monkeypatch, holder)
    code, body, _ = _run(["count", PLAN], capsys, window)
    assert code == 3 and "no automation session" in body["errors"][0] and "--no-server" in body["errors"][0]
    assert body["data"]["holder"] == holder


def test_no_session_file_is_exit_3_with_the_hint(seeded, capsys, monkeypatch):
    _refusing_brain(monkeypatch, _own_holder())
    assert not session_path().exists()
    code, body, _ = _run(["count", PLAN], capsys)
    assert code == 3 and body["errors"][0].endswith("ASI_KLETZ_AUTOMATION=off")


def test_no_forward_is_exit_3_even_with_a_live_session(window, capsys, monkeypatch):
    _refusing_brain(monkeypatch, _own_holder())
    before = window.server.requests
    code, body, _ = _run(["--no-forward", "count", PLAN], capsys, window)
    assert code == 3 and "automation" not in body["errors"][0] and window.server.requests == before


def test_dead_server_with_a_file_left_is_exit_3_did_not_answer(capsys, monkeypatch):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    write_session(port=port, token="t" * 32, db=None, started_at="2026-10-27T17:02:11Z")
    _refusing_brain(monkeypatch, _own_holder())
    code, body, _ = _run(["count", PLAN], capsys)
    assert code == 3 and f"the automation session at http://127.0.0.1:{port} did not answer" in body["errors"][0]


def test_db_on_a_forwarded_call_warns_and_still_forwards(window, seeded, capsys, monkeypatch, tmp_path):
    _refusing_brain(monkeypatch, _own_holder())
    code, body, err = _run(["--db", str(tmp_path / "other.db"), "count", PLAN], capsys, window)
    assert code == 0 and body["data"]["count"] == 3
    assert err.startswith("warning: --db") and "other.db" in err and seeded.db_path in err
    code, body, err = _run(["--db", seeded.db_path, "count", PLAN], capsys, window)
    assert code == 0 and err == ""
