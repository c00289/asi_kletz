"""Per-person, per-machine preferences: today the latched theme, later anything else of that kind.

A preference is not a project setting (``kletz.toml`` holds paths and document control and is
read-only to the program) and not data (the database is the Safety Plan). It lives in one flat
JSON object in a file of Kletz's own, never inside a repo or a synced folder:

- ``$ASI_KLETZ_PREFS`` if set (a full file path; the test suite points it at a temp folder);
- else ``%LOCALAPPDATA%\\asi\\kletz\\prefs.json`` on Windows;
- else ``$XDG_STATE_HOME/asi/kletz/prefs.json``;
- else ``~/.local/state/asi/kletz/prefs.json``.

``asi`` is the same base folder the family lock uses; ``kletz`` is this tool's own, so no
sister tool ever reads or writes this file. A missing, unreadable or corrupt file reads as
``{}`` and is replaced by the next write; the program never fails because of a preference.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from .version import __version__

ENV_PREFS = "ASI_KLETZ_PREFS"
TOOL = "asi_kletz"
FILE_NAME = "prefs.json"


def _state_home() -> Path:
    """``%LOCALAPPDATA%`` on Windows, else ``$XDG_STATE_HOME``, else ``~/.local/state``."""
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"])
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"])
    return Path.home() / ".local" / "state"


def prefs_path() -> Path:
    """Where the preferences live: ``$ASI_KLETZ_PREFS`` or the per-user state folder."""
    override = os.environ.get(ENV_PREFS)
    if override:
        return Path(override).expanduser()
    return _state_home() / "asi" / "kletz" / FILE_NAME


def prefs_problem(path: Path | None = None) -> str | None:
    """Why the file cannot be used, or ``None``: a missing file is not a problem, a corrupt one is."""
    file = path or prefs_path()
    if not file.exists():
        return None
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return f"preferences file {file} is unreadable ({exc}); it will be replaced by the next pick"
    if not isinstance(data, dict):
        return f"preferences file {file} does not hold a JSON object; it will be replaced by the next pick"
    return None


def read_prefs() -> dict[str, Any]:
    """The preferences as a dict; ``{}`` when the file is missing, unreadable or not a JSON object."""
    file = prefs_path()
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(data) if isinstance(data, dict) else {}


def write_prefs(**changes: Any) -> Path:
    """Merge ``changes`` into the file and write it atomically (temp file beside it, then ``os.replace``)."""
    file = prefs_path()
    data = read_prefs()
    data.update(changes)
    data["tool"] = TOOL
    data["version"] = __version__
    data["updated_at"] = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(f"{file.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, file)
    return file
