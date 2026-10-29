"""A trace of the window's life, beside the preferences file: ``gui.log``.

The owner, 2026-10-29: the window "crashed for the first time", twice, and left nothing in the terminal
either time; the audit log showed only that the save being made had not landed. A window that ends must
say why. Every launch appends: the start (pid, version, server on or off), every ``close()`` with the
caller that asked for it (Ctrl+Q, the window's close box, the automation server's ``/quit``, or code), the
moment the main loop returns, and any exception that escapes it. ``faulthandler`` is enabled on the same
file, so a hard crash (an access violation inside Tk, an abort) writes the Python stack of every thread
there before the process dies. The file is kept under a megabyte: past that it rolls to ``gui.log.1``.
"""

from __future__ import annotations

import datetime as dt
import faulthandler
import inspect
import os
import sys
from pathlib import Path
from typing import IO

from ..prefs import prefs_path

FILE_NAME = "gui.log"
LIMIT = 1_000_000  # bytes; the log rolls to gui.log.1 above this at the next start
_handle: IO[str] | None = None


def log_path() -> Path:
    """``gui.log`` beside the preferences file (``$ASI_KLETZ_PREFS`` moves both)."""
    return prefs_path().with_name(FILE_NAME)


def start(version: str, *, server: bool) -> Path | None:
    """Open the log for this process, roll it when it is big, enable ``faulthandler`` on it, note the start.
    Returns the path, or None when the folder cannot be written (the window still opens)."""
    global _handle
    path = log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LIMIT:
            os.replace(path, path.with_name(FILE_NAME + ".1"))
        _handle = open(path, "a", encoding="utf-8")  # noqa: SIM115  (kept open for the process's life)
    except OSError:
        _handle = None
        return None
    faulthandler.enable(file=_handle, all_threads=True)
    note("start", pid=os.getpid(), version=version, server="on" if server else "off",
         python=sys.version.split()[0], argv=" ".join(sys.argv[1:]) or "-")
    return path


def note(event: str, **fields: object) -> None:
    """One line: the UTC time, the event, ``key=value`` pairs. Never raises."""
    if _handle is None:
        return
    stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    extra = " ".join(f"{k}={_flat(v)}" for k, v in fields.items())
    try:
        _handle.write(f"{stamp} {event}{(' ' + extra) if extra else ''}\n")
        _handle.flush()
    except (OSError, ValueError):
        pass


def caller(skip: int = 2, depth: int = 3) -> str:
    """Who asked: the ``depth`` frames above the function calling this, as ``name (file:line)`` joined by
    ``<``, innermost first; ``skip`` leaves out this function and its caller."""
    parts: list[str] = []
    for frame in inspect.stack()[skip:skip + depth]:
        parts.append(f"{frame.function} ({Path(frame.filename).name}:{frame.lineno})")
    return " < ".join(parts) or "?"


def stop() -> None:
    """Note the end and release the file; ``faulthandler`` stays on until the process ends."""
    global _handle
    note("end")
    if _handle is not None:
        try:
            faulthandler.disable()
            _handle.close()
        except (OSError, ValueError):
            pass
    _handle = None


def _flat(value: object) -> str:
    text = str(value).replace("\n", "\\n")
    return text if len(text) <= 300 else text[:297] + "..."
