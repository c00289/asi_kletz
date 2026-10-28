"""The family lock: one primary tool at a time.

While any process of a primary tool holds an open ``Brain``, no other process of any primary
tool may open one. The rule is enforced by two OS advisory locks in a directory the primary
tools share by convention (``ASI_FUSA_TOOLS.md``, "One primary tool at a time"); nothing here
imports or names the sister tool, the two implementations agree through the files alone.

- Lock directory: ``$ASI_PRIMARY_LOCK_DIR`` if set; else ``%LOCALAPPDATA%\\asi\\locks`` on
  Windows; else ``$XDG_STATE_HOME/asi/locks``; else ``~/.local/state/asi/locks``. Created on
  demand; never inside a repo or a synced folder.
- Family slot ``primary.lock``: held while a primary tool is running.
- Database slot ``db-<sha1>.lock``: held while that database is open (``<sha1>`` of the resolved
  absolute path, lower-cased on Windows); ``:memory:`` takes none.
- Primitive: a non-blocking lock on byte 0 (``msvcrt.locking`` on Windows, ``fcntl.flock``
  elsewhere). The OS drops it when the process ends, so a crash never leaves a stale lock.
- Holder info: ``primary.json`` / ``db-<sha1>.json`` beside the lock, written best-effort by the
  holder after it acquires. Informational; the lock is the truth.
- Order: family slot first, then database slot; a failed database slot releases the family slot.
- No override: pointing ``ASI_PRIMARY_LOCK_DIR`` at a private directory is the only escape, and
  it is what the test suite does.

One process may hold several ``Brain`` objects: ``PrimaryGuard`` counts them and takes each slot
once, on the first ``Brain``, and releases it after the last ``close()``.
"""

from __future__ import annotations

import datetime as dt
import getpass
import hashlib
import json
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any

from .errors import BrainError
from .version import __version__

TOOL = "asi_kletz"
ENV_LOCK_DIR = "ASI_PRIMARY_LOCK_DIR"
FAMILY_STEM = "primary"
MEMORY_DB = ":memory:"
POLL_SECONDS = 0.25
FAMILY_SLOT = "family"
DATABASE_SLOT = "database"
HOLDER_FIELDS = ("tool", "version", "pid", "started_at", "db", "cwd", "host", "user")


class PrimaryToolBusy(BrainError):
    """Another process holds the slot. ``slot`` says which; ``holder`` is its info file, if readable."""

    def __init__(self, slot: str, holder: dict[str, Any] | None, lock_path: Path | None = None) -> None:
        self.slot = slot
        self.holder = holder
        self.lock_path = lock_path
        super().__init__(describe_holder(slot, holder))


def describe_holder(slot: str, holder: dict[str, Any] | None) -> str:
    """One line naming the holder, for the CLI error, the busy dialog and the status bar."""
    if holder is None:
        who = "another primary tool is running (holder unknown: no readable info file beside the lock)"
    else:
        tool = str(holder.get("tool") or "a primary tool")
        details = []
        if holder.get("pid") is not None:
            details.append(f"pid {holder['pid']}")
        if holder.get("started_at"):
            details.append(f"since {holder['started_at']}")
        if holder.get("db"):
            details.append(f"db {holder['db']}")
        inside = ", ".join(details)
        verb = "is running" if slot == FAMILY_SLOT else "has this database open"
        who = f"{tool} {verb} ({inside})" if inside else f"{tool} {verb}"
    rule = "only one primary tool may run at a time" if slot == FAMILY_SLOT else "a database has one process at a time"
    return f"{who}; {rule}. Close it, or retry with --wait."


def _state_home() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"])
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"])
    return Path.home() / ".local" / "state"


def lock_dir() -> Path:
    """The directory of the lock files: ``$ASI_PRIMARY_LOCK_DIR`` or the per-user state folder."""
    override = os.environ.get(ENV_LOCK_DIR)
    if override:
        return Path(override).expanduser()
    return _state_home() / "asi" / "locks"


def resolve_db_key(db_path: str | Path) -> str:
    """The resolved absolute path the database slot is named after, lower-cased on Windows."""
    text = str(Path(db_path).expanduser().resolve())
    return text.lower() if os.name == "nt" else text


def db_slot_name(db_path: str | Path) -> str:
    """``db-<sha1>`` for the database at ``db_path``."""
    return "db-" + hashlib.sha1(resolve_db_key(db_path).encode("utf-8")).hexdigest()


def holder_info(db_path: str | None) -> dict[str, Any]:
    """What this process writes beside a lock it holds."""
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001  (no account name is not an error)
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return {
        "tool": TOOL,
        "version": __version__,
        "pid": os.getpid(),
        "started_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "db": None if db_path in (None, MEMORY_DB) else str(db_path),
        "cwd": os.getcwd(),
        "host": socket.gethostname(),
        "user": user,
    }


# -- the primitive --------------------------------------------------------------------------
if os.name == "nt":
    import msvcrt

    def _lock_byte(fd: int) -> bool:
        """Take byte 0 without blocking; ``False`` when another process holds it."""
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:  # EACCES or EDEADLOCK: busy
            return False
        return True

    def _unlock_byte(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass

else:
    import fcntl

    def _lock_byte(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock_byte(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


class SlotLock:
    """One lock file plus its info file. ``acquire`` is non-blocking; ``release`` is idempotent."""

    def __init__(self, directory: Path, stem: str) -> None:
        self.directory = Path(directory)
        self.stem = stem
        self.lock_path = self.directory / f"{stem}.lock"
        self.info_path = self.directory / f"{stem}.json"
        self._fd: int | None = None
        self.info: dict[str, Any] | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self, info: dict[str, Any], slot: str) -> None:
        """Take the lock or raise ``PrimaryToolBusy`` naming the holder. Never blocks."""
        if self._fd is not None:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if os.fstat(fd).st_size == 0:  # the locked region must exist: keep the file one byte long
                try:
                    os.write(fd, b"\0")
                except OSError:
                    pass  # another process may already hold byte 0; the lock attempt below says so
            if not _lock_byte(fd):
                raise PrimaryToolBusy(slot, self.read_holder(), self.lock_path)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        self.info = dict(info)
        self._write_info(self.info)

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        _unlock_byte(fd)
        os.close(fd)
        self.info = None
        try:
            self.info_path.unlink()
        except OSError:
            pass  # informational: the lock is already gone

    def read_holder(self) -> dict[str, Any] | None:
        """The holder's info file, or ``None`` when it is missing or unreadable."""
        try:
            data = json.loads(self.info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _write_info(self, info: dict[str, Any]) -> None:
        """Best effort: a refused process reads this while the lock is held."""
        try:
            temp = self.info_path.with_name(f"{self.stem}.{os.getpid()}.tmp")
            temp.write_text(json.dumps(info, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(temp, self.info_path)
        except OSError:
            pass


# -- the process-wide guard --------------------------------------------------------------------
class PrimaryGuard:
    """Reference-counted slots for every open ``Brain`` of this process. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._family: SlotLock | None = None
        self._family_count = 0
        self._databases: dict[str, tuple[SlotLock, int]] = {}

    # -- public -------------------------------------------------------------------------
    def acquire(self, db_path: str | None, wait: float = 0.0) -> None:
        """Take the family slot, then the database slot, polling every 250 ms for up to ``wait`` s."""
        deadline = time.monotonic() + max(0.0, float(wait or 0.0))
        while True:
            try:
                with self._lock:
                    self._acquire_now(db_path)
                return
            except PrimaryToolBusy:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(POLL_SECONDS, remaining))

    def release(self, db_path: str | None) -> None:
        """Drop one reference; the slots go when the last ``Brain`` closes. Idempotent per Brain."""
        with self._lock:
            key = self._db_key(db_path)
            if key is not None and key in self._databases:
                slot, count = self._databases[key]
                if count <= 1:
                    slot.release()
                    del self._databases[key]
                else:
                    self._databases[key] = (slot, count - 1)
            if self._family_count > 0:
                self._family_count -= 1
                if self._family_count == 0 and self._family is not None:
                    self._family.release()
                    self._family = None

    def describe(self, db_path: str | None = None) -> dict[str, Any]:
        """What this process holds, for ``Brain.status()``: ``lock_dir``, ``family``, ``database``."""
        with self._lock:
            family = self._slot_view(self._family, self._family_count)
            key = self._db_key(db_path)
            entry = self._databases.get(key) if key is not None else None
            database = self._slot_view(entry[0], entry[1]) if entry else None
            return {"lock_dir": str(lock_dir()), FAMILY_SLOT: family, DATABASE_SLOT: database}

    @property
    def brains(self) -> int:
        """How many open ``Brain`` objects this process holds."""
        with self._lock:
            return self._family_count

    # -- internals -----------------------------------------------------------------------
    @staticmethod
    def _db_key(db_path: str | None) -> str | None:
        if db_path is None or db_path == MEMORY_DB:
            return None
        return resolve_db_key(db_path)

    @staticmethod
    def _slot_view(slot: SlotLock | None, count: int) -> dict[str, Any] | None:
        if slot is None or not slot.held:
            return None
        view = dict(slot.info or {})
        view["lock"] = str(slot.lock_path)
        view["brains"] = count
        return view

    def _acquire_now(self, db_path: str | None) -> None:
        """Called under ``_lock``: family slot first, then the database slot; all or nothing."""
        directory = lock_dir()
        info = holder_info(db_path)
        took_family = False
        if self._family_count == 0:
            family = SlotLock(directory, FAMILY_STEM)
            family.acquire(info, FAMILY_SLOT)  # raises PrimaryToolBusy
            self._family = family
            took_family = True
        key = self._db_key(db_path)
        if key is not None:
            if key in self._databases:
                slot, count = self._databases[key]
                self._databases[key] = (slot, count + 1)
            else:
                slot = SlotLock(directory, db_slot_name(db_path or ""))
                try:
                    slot.acquire(info, DATABASE_SLOT)
                except PrimaryToolBusy:
                    if took_family and self._family is not None:
                        self._family.release()
                        self._family = None
                    raise
                self._databases[key] = (slot, 1)
        self._family_count += 1


guard = PrimaryGuard()
