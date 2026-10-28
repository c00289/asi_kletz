"""The automation session file: how a CLI or an agent finds the window's local server.

A running window writes one flat JSON object beside ``prefs.json`` (``$ASI_KLETZ_SESSION``
overrides the path; the test suite points it at a temp folder): ``tool``, ``version``, ``pid``,
``started_at``, ``host``, ``port``, ``address``, ``token`` and ``db``. ``pid`` and ``started_at``
are the values the lock holder writes to ``primary.json``, so the two files can be matched.

Readers never trust the file alone: ``read_session`` drops it when the tool name is wrong or the
pid is dead (a crash leaves a stale file; the next window overwrites it), and ``probe`` asks
``GET /status`` and requires the answering pid to be the file's. Written from the family
convention (``ASI_FUSA_TOOLS.md``, "The automation session"), never shared with the sister tool.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..commands.base import Result
from ..prefs import prefs_path
from ..version import __version__

ENV_SESSION = "ASI_KLETZ_SESSION"
ENV_AUTOMATION = "ASI_KLETZ_AUTOMATION"
TOOL = "asi_kletz"
FILE_NAME = "session.json"
HOST = "127.0.0.1"
PROBE_TIMEOUT = 1.0
FORWARD_TIMEOUT = 60.0
SESSION_VIEW = ("pid", "port", "address", "started_at", "db")  # what `session` prints: never the token


class SessionUnreachable(Exception):
    """The session file named a server that did not answer, or answered with a transport error."""


def automation_enabled() -> bool:
    """``ASI_KLETZ_AUTOMATION=off`` is the only value that turns the server off."""
    return os.environ.get(ENV_AUTOMATION, "").strip().lower() != "off"


def session_path() -> Path:
    """``$ASI_KLETZ_SESSION``, else ``session.json`` beside the preferences file."""
    override = os.environ.get(ENV_SESSION)
    if override:
        return Path(override).expanduser()
    return prefs_path().with_name(FILE_NAME)


def write_session(port: int, token: str, db: str | None, started_at: str, host: str = HOST) -> Path:
    """Write the file atomically (temp file beside it, then ``os.replace``); ``0o600`` on POSIX."""
    file = session_path()
    data = {
        "tool": TOOL,
        "version": __version__,
        "pid": os.getpid(),
        "started_at": started_at,
        "host": host,
        "port": int(port),
        "address": f"http://{host}:{int(port)}",
        "token": token,
        "db": db,
    }
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_name(f"{file.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if os.name != "nt":
        os.chmod(temp, 0o600)
    os.replace(temp, file)
    return file


def _read_raw() -> dict[str, Any] | None:
    try:
        data = json.loads(session_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_session() -> dict[str, Any] | None:
    """The session, or ``None`` when the file is missing, corrupt, another tool's, or its pid is dead."""
    data = _read_raw()
    if data is None or data.get("tool") != TOOL:
        return None
    pid, port, token = data.get("pid"), data.get("port"), data.get("token")
    if not isinstance(pid, int) or not isinstance(port, int) or not isinstance(token, str) or not token:
        return None
    if not pid_alive(pid):
        return None
    data.setdefault("host", HOST)
    data.setdefault("address", f"http://{data['host']}:{port}")
    return data


def clear_session(pid: int | None = None) -> None:
    """Remove the file only when it names ``pid`` (this process by default): never another window's."""
    pid = os.getpid() if pid is None else pid
    data = _read_raw()
    if data is None or data.get("pid") != pid:
        return
    try:
        session_path().unlink()
    except OSError:
        pass


def pid_alive(pid: int) -> bool:
    """Whether a process with ``pid`` is still running (``STILL_ACTIVE`` on Windows, signal 0 elsewhere)."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        process_query_limited_information, still_active = 0x1000, 259
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists; it is just not ours
    return True


# -- talking to the server -------------------------------------------------------------------
def request(
    session: dict[str, Any], method: str, path: str, body: Any = None, timeout: float = PROBE_TIMEOUT
) -> Result:
    """One request to the session's server with its bearer token; the ``Result`` it answered.

    Raises ``SessionUnreachable`` on a connection error, a timeout, or a non-200 answer (401, 404,
    504, ...): those are the transport failing, not the command failing.
    """
    url = f"{session['address']}{path}"
    data = None if body is None else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {session['token']}")
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as answer:  # noqa: S310  (loopback http only)
            payload = json.loads(answer.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            errors = json.loads(exc.read().decode("utf-8")).get("errors") or []
            detail = f": {errors[0]}" if errors else ""
        except (ValueError, AttributeError, OSError):
            pass
        raise SessionUnreachable(f"HTTP {exc.code}{detail}") from None
    except (TimeoutError, urllib.error.URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise SessionUnreachable(str(reason)) from None
    if not isinstance(payload, dict):
        raise SessionUnreachable("the answer was not a JSON object")
    return Result(
        ok=bool(payload.get("ok")),
        data=payload.get("data"),
        errors=list(payload.get("errors") or []),
        warnings=list(payload.get("warnings") or []),
        verb=payload.get("verb"),
    )


def probe(session: dict[str, Any], timeout: float = PROBE_TIMEOUT) -> dict[str, Any] | None:
    """``GET /status``: its data when the server answers as the file's pid; ``None`` otherwise."""
    try:
        result = request(session, "GET", "/status", timeout=timeout)
    except SessionUnreachable:
        return None
    if not result.ok or not isinstance(result.data, dict) or result.data.get("pid") != session.get("pid"):
        return None
    return result.data


def forward(
    session: dict[str, Any],
    verb: str,
    args: dict[str, Any] | None,
    actor: str = "cli",
    timeout: float = FORWARD_TIMEOUT,
) -> Result:
    """``POST /execute`` and the command's ``Result``, untouched. Raises ``SessionUnreachable``."""
    payload = {"verb": verb, "args": dict(args or {}), "actor": actor}
    return request(session, "POST", "/execute", body=payload, timeout=timeout)


def quit_session(session: dict[str, Any], timeout: float = PROBE_TIMEOUT) -> Result:
    """``POST /quit``. Raises ``SessionUnreachable``."""
    return request(session, "POST", "/quit", body={}, timeout=timeout)


def public_view(session: dict[str, Any]) -> dict[str, Any]:
    """The session without its token, for anything that prints."""
    return {key: session.get(key) for key in SESSION_VIEW}
