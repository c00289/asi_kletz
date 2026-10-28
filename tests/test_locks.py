"""The family lock: one primary tool at a time, checked with real second processes.

Three kinds of helper process: a Kletz holder (a ``Brain`` kept open), a simulated sibling that
takes ``primary.lock`` by the raw convention with no package import at all, and a probe that
reports whether a lock is held. The sibling's tool name is passed in as an argument, so this file
never spells the sister tool's name in one piece either (see ``test_generate.py``).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from asi_kletz import Brain, PrimaryToolBusy
from asi_kletz.locks import ENV_LOCK_DIR, TOOL, db_slot_name, guard, lock_dir, resolve_db_key

SISTER = "asi_" + "dewey"

HOLDER = """
import os, sys, time
from asi_kletz import Brain
b = Brain(sys.argv[1])
print("ready", os.getpid(), flush=True)
if sys.argv[2] == "stdin":
    sys.stdin.readline()
else:
    time.sleep(float(sys.argv[2]))
b.close()
"""

# the raw convention, no asi_* import: a lock on byte 0 plus the info file beside it
SIBLING = """
import json, os, sys
directory, tool, db, stem = sys.argv[1:5]
os.makedirs(directory, exist_ok=True)
fd = os.open(os.path.join(directory, stem + ".lock"), os.O_RDWR | os.O_CREAT)
if os.fstat(fd).st_size == 0:
    os.write(fd, b"\\0")
os.lseek(fd, 0, 0)
if os.name == "nt":
    import msvcrt
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
info = {"tool": tool, "version": "9.9.9", "pid": os.getpid(), "started_at": "2026-10-27T17:02:11Z",
        "db": db or None, "cwd": os.getcwd(), "host": "sibling-host", "user": "sibling"}
with open(os.path.join(directory, stem + ".json"), "w", encoding="utf-8") as handle:
    json.dump(info, handle)
print("ready", os.getpid(), flush=True)
sys.stdin.readline()
"""

PROBE = """
import os, sys
path = sys.argv[1]
fd = os.open(path, os.O_RDWR | os.O_CREAT)
if os.fstat(fd).st_size == 0:
    os.write(fd, b"\\0")
os.lseek(fd, 0, 0)
try:
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError:
    print("busy")
else:
    print("free")
"""


def _start(code: str, *args: str) -> subprocess.Popen:
    """Start a helper and wait for its ``ready <pid>`` line.

    ``proc.held_pid`` is the pid the helper reports about itself: on Windows a venv's
    ``python.exe`` is a launcher whose child is the real interpreter, so ``proc.pid`` can differ.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", code, *args],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    line = proc.stdout.readline().split()
    if line[:1] != ["ready"]:
        proc.kill()  # a live child would block the read of its pipes below
        out, err = proc.communicate(timeout=10)
        raise RuntimeError(f"helper did not start: {line!r} {out!r} {err!r}")
    proc.held_pid = int(line[1])  # type: ignore[attr-defined]
    return proc


def _crash(proc: subprocess.Popen) -> None:
    """Kill the holder itself (not a launcher in front of it) and wait until it is gone."""
    os.kill(proc.held_pid, signal.SIGTERM)  # type: ignore[attr-defined]  TerminateProcess on Windows
    proc.wait(timeout=10)


def _release(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.stdin.write("\n")
            proc.stdin.close()
        except OSError:
            pass
    proc.wait(timeout=10)


def hold_brain(db: Path, hold: str = "stdin") -> subprocess.Popen:
    """A second Kletz process holding ``db`` open until a line on stdin (or for ``hold`` seconds)."""
    return _start(HOLDER, str(db), hold)


def hold_as_sibling(tool: str = SISTER, db: str = "", stem: str = "primary") -> subprocess.Popen:
    """A process that takes a slot the way the convention says, under another tool's name."""
    return _start(SIBLING, str(lock_dir()), tool, db, stem)


def is_locked(path: Path) -> bool:
    """Whether another process holds byte 0 of ``path`` (asked from a process of its own)."""
    out = subprocess.run([sys.executable, "-c", PROBE, str(path)], capture_output=True, text=True, check=True)
    return out.stdout.strip() == "busy"


@pytest.fixture
def holder(tmp_path):
    proc = hold_brain(tmp_path / "held.db")
    yield proc
    _release(proc)


@pytest.fixture
def sibling():
    proc = hold_as_sibling(db="C:/somewhere/sister.db")
    yield proc
    _release(proc)


# -- names and places --------------------------------------------------------------------
def test_lock_dir_is_the_env_override_during_tests(tmp_path):
    assert lock_dir() == tmp_path / "locks" and os.environ[ENV_LOCK_DIR] == str(tmp_path / "locks")
    assert guard.brains == 0  # nothing leaks between tests


def test_lock_dir_falls_back_to_the_per_user_state_folder(monkeypatch):
    monkeypatch.delenv(ENV_LOCK_DIR)
    path = lock_dir()
    assert path.parts[-2:] == ("asi", "locks")
    if os.name == "nt":
        assert path == Path(os.environ["LOCALAPPDATA"]) / "asi" / "locks"


def test_db_slot_name_is_the_sha1_of_the_resolved_path(tmp_path):
    name = db_slot_name(tmp_path / "a.db")
    assert name.startswith("db-") and len(name) == 3 + 40
    assert name == db_slot_name(str(tmp_path / "sub" / ".." / "a.db"))  # resolved, not literal
    if os.name == "nt":
        assert resolve_db_key(tmp_path / "A.DB") == resolve_db_key(tmp_path / "a.db")
    assert name != db_slot_name(tmp_path / "b.db")


# -- one process, many Brains --------------------------------------------------------------
def test_one_process_holds_the_family_slot_once_for_many_brains(tmp_path):
    primary = lock_dir() / "primary.lock"
    assert not primary.exists()
    a = Brain(tmp_path / "one.db")
    assert is_locked(primary) and guard.brains == 1
    b = Brain(":memory:")
    c = Brain(tmp_path / "one.db")  # the same file twice: one database slot, counted twice
    d = Brain(tmp_path / "two.db")
    assert guard.brains == 4
    status = a.status()
    assert status["locks"]["family"]["brains"] == 4 and status["locks"]["database"]["brains"] == 2
    assert b.status()["locks"]["database"] is None  # :memory: takes no database slot
    assert is_locked(lock_dir() / (db_slot_name(tmp_path / "one.db") + ".lock"))
    assert is_locked(lock_dir() / (db_slot_name(tmp_path / "two.db") + ".lock"))
    for brain in (a, b, d):
        brain.close()
    assert is_locked(primary) and guard.brains == 1  # c still holds everything
    assert is_locked(lock_dir() / (db_slot_name(tmp_path / "one.db") + ".lock"))
    assert not is_locked(lock_dir() / (db_slot_name(tmp_path / "two.db") + ".lock"))
    c.close()
    c.close()  # idempotent
    assert not is_locked(primary) and guard.brains == 0
    assert not (lock_dir() / "primary.json").exists()


def test_status_reports_the_locks_this_process_holds(brain, tmp_path):
    status = brain.status()
    assert status["lock_dir"] == str(tmp_path / "locks")
    family, database = status["locks"]["family"], status["locks"]["database"]
    assert family["pid"] == os.getpid() and family["tool"] == TOOL and family["brains"] == 1
    assert family["lock"] == str(tmp_path / "locks" / "primary.lock")
    assert database["lock"] == str(tmp_path / "locks" / (db_slot_name(brain.db_path) + ".lock"))
    assert database["db"] == brain.db_path and database["pid"] == os.getpid()
    for key in ("tool", "version", "pid", "started_at", "db", "cwd", "host", "user"):
        assert key in family
    holder = json.loads((tmp_path / "locks" / "primary.json").read_text(encoding="utf-8"))
    assert holder["pid"] == os.getpid() and holder["tool"] == TOOL and holder["started_at"].endswith("Z")
    assert brain.execute("status").data["locks"]["family"]["pid"] == os.getpid()


# -- a second process ----------------------------------------------------------------------
def test_second_process_of_the_same_tool_is_refused(holder, tmp_path):
    with pytest.raises(PrimaryToolBusy) as info:
        Brain(tmp_path / "other.db")
    exc = info.value
    assert exc.slot == "family" and exc.holder["tool"] == TOOL and exc.holder["pid"] == holder.held_pid
    assert exc.holder["db"] == str(tmp_path / "held.db")
    assert f"{TOOL} is running (pid {holder.held_pid}" in str(exc) and "--wait" in str(exc)
    assert not (tmp_path / "other.db").exists()  # a refused process never opens the SQLite file
    assert guard.brains == 0


def test_simulated_sibling_is_refused_with_its_holder(sibling, tmp_path):
    with pytest.raises(PrimaryToolBusy) as info:
        Brain(tmp_path / "mine.db")
    exc = info.value
    assert exc.slot == "family" and exc.holder["tool"] == SISTER and exc.holder["pid"] == sibling.held_pid
    expected = f"{SISTER} is running (pid {sibling.held_pid}, since 2026-10-27T17:02:11Z, db C:/somewhere/sister.db)"
    assert str(exc).startswith(expected)
    assert "only one primary tool may run at a time" in str(exc)
    _release(sibling)
    with Brain(tmp_path / "mine.db") as brain:  # the sibling has left: the slot is ours
        assert brain.status()["locks"]["family"]["pid"] == os.getpid()


def test_database_slot_refusal_releases_the_family_slot(tmp_path):
    db = tmp_path / "shared.db"
    proc = hold_as_sibling(tool=TOOL, db=str(db), stem=db_slot_name(db))  # a misconfigured sibling: only the db slot
    try:
        with pytest.raises(PrimaryToolBusy) as info:
            Brain(db)
        assert info.value.slot == "database" and info.value.holder["pid"] == proc.held_pid
        assert "has this database open" in str(info.value)
        assert not is_locked(lock_dir() / "primary.lock") and guard.brains == 0
        with Brain(tmp_path / "another.db") as brain:  # another database is fine
            assert brain.status()["locks"]["family"]["pid"] == os.getpid()
    finally:
        _release(proc)


def test_unreadable_holder_file_still_refuses(tmp_path):
    proc = hold_as_sibling()
    try:
        (lock_dir() / "primary.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(PrimaryToolBusy) as info:
            Brain(tmp_path / "x.db")
        assert info.value.holder is None and "holder unknown" in str(info.value)
    finally:
        _release(proc)


def test_crashed_holder_releases_the_slot(tmp_path):
    proc = hold_brain(tmp_path / "held.db")
    with pytest.raises(PrimaryToolBusy):
        Brain(tmp_path / "mine.db")
    _crash(proc)
    started = time.monotonic()
    with Brain(tmp_path / "mine.db", wait=5) as brain:  # wait only covers the kernel's teardown latency
        assert time.monotonic() - started < 5  # it came free at once, not at the deadline
        holder = json.loads((lock_dir() / "primary.json").read_text(encoding="utf-8"))
        assert holder["pid"] == os.getpid() and brain.status()["locks"]["family"]["pid"] == os.getpid()


def test_wait_queues_for_the_slot(tmp_path):
    proc = hold_brain(tmp_path / "held.db", hold="0.5")
    try:
        started = time.monotonic()
        with Brain(tmp_path / "mine.db", wait=5):
            elapsed = time.monotonic() - started
        assert 0.2 < elapsed < 5
    finally:
        _release(proc)
    proc = hold_brain(tmp_path / "held.db")
    try:
        started = time.monotonic()
        with pytest.raises(PrimaryToolBusy):
            Brain(tmp_path / "mine.db", wait=0.3)
        assert time.monotonic() - started >= 0.3
    finally:
        _release(proc)


def test_package_exports_primary_tool_busy():
    import asi_kletz
    from asi_kletz.errors import BrainError
    from asi_kletz.errors import PrimaryToolBusy as from_errors

    assert asi_kletz.PrimaryToolBusy is from_errors is PrimaryToolBusy
    assert issubclass(PrimaryToolBusy, BrainError)
