"""The local automation server: loopback HTTP, JSON ``Result`` answers, owned by the window.

``AutomationServer`` binds ``127.0.0.1`` on an ephemeral port, serves on a daemon thread and
answers six endpoints: ``GET /status``, ``POST /execute``, ``GET /screens``, ``POST /screen``,
``GET /events?since=<n>&limit=<m>`` and ``POST /quit``. Every request carries
``Authorization: Bearer <token>`` (the token is in the session file, new per launch); a request
with an ``Origin`` header (a browser) is refused with 403 whatever its token.

**The main-thread handshake.** An HTTP handler runs on a server thread and may not touch a Tk
widget, the window's state or the ``Brain`` (SQLite connections are per thread). Every job is
queued; the window drains the queue on its own thread every 50 ms (``_pump``, an ``after`` job
on the root, so it survives ``set_theme`` destroying the children); the handler waits on a
``threading.Event`` with a timeout and answers 504 when the window did not get to it. ``on_main``
is the only door. What a job may call on the window: ``brain.execute``, ``show``,
``factory.items()``, ``current_key``, ``theme``, ``remote_guard``, and ``close`` through
``after``. Never ``run``, ``pick_theme``, ``notify_error``, ``confirm``, ``about``,
``export_workbook`` or ``build_safety_plan``: those may open a dialog, and a dialog would block
the Tk thread with a request waiting on it.

The HTTP status is about transport, not about the command: a failed command is 200 with
``ok: false``, exactly as the CLI prints it and exits 1.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import queue
import secrets
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from ..commands.base import Result
from ..errors import NotFound
from ..locks import guard
from ..version import __version__
from .session import HOST, TOOL

if TYPE_CHECKING:
    from ..gui.main_window import MainWindow

log = logging.getLogger("asi_kletz.automation.server")

JOB_TIMEOUT = 60.0
PUMP_MS = 50
QUIT_DELAY_MS = 100
MAX_BODY = 1024 * 1024
DEFAULT_ACTOR = "agent"
EVENTS_LIMIT = 200
ROUTES: dict[str, str] = {  # path -> the one method it accepts
    "/status": "GET",
    "/execute": "POST",
    "/screens": "GET",
    "/screen": "POST",
    "/events": "GET",
    "/quit": "POST",
}

_current: AutomationServer | None = None


def current() -> AutomationServer | None:
    """The server running in this process, if any: the ``session`` verb reports it without HTTP."""
    return _current


class _Job:
    __slots__ = ("done", "error", "fn", "result", "cancelled")

    def __init__(self, fn: Callable[[], Any]) -> None:
        self.fn = fn
        self.done = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None
        self.cancelled = False


class AutomationServer:
    """One per window. ``start`` binds and serves; ``stop`` (Tk thread only) shuts down."""

    def __init__(self, window: MainWindow, host: str = HOST, port: int = 0) -> None:
        self.window = window
        self.host = host
        self.port = port
        self.token = secrets.token_hex(16)
        self.started_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.requests = 0
        self.job_timeout = JOB_TIMEOUT
        self._started = time.monotonic()
        self._jobs: queue.SimpleQueue[_Job] = queue.SimpleQueue()
        self._pump_job: str | None = None
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._count_lock = threading.Lock()
        self._stopped = False

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def running(self) -> bool:
        return self._httpd is not None and not self._stopped

    # -- lifecycle (Tk thread) --------------------------------------------------------------
    def start(self) -> None:
        """Bind, start the daemon server thread, start the main-thread pump. Raises ``OSError``."""
        global _current
        server = self

        class Handler(_Handler):
            automation = server

        httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        httpd.daemon_threads = True
        self._httpd = httpd
        self.port = int(httpd.server_address[1])
        self._thread = threading.Thread(
            target=httpd.serve_forever, kwargs={"poll_interval": 0.1}, name="asi-kletz-automation", daemon=True
        )
        self._thread.start()
        self._stopped = False
        self._pump_job = self.window.after(PUMP_MS, self._pump)
        _current = self

    def stop(self) -> None:
        """Cancel the pump, shut the server down, fail every job still queued. Idempotent."""
        global _current
        if self._stopped and self._httpd is None:
            return
        self._stopped = True
        if self._pump_job is not None:
            try:
                self.window.after_cancel(self._pump_job)
            except Exception:  # noqa: BLE001  (the root may already be gone)
                pass
            self._pump_job = None
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        while True:  # a handler still waiting gets its 504 at once instead of a dead window
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                break
            job.cancelled = True
            job.done.set()
        if _current is self:
            _current = None

    # -- the handshake -------------------------------------------------------------------------
    def on_main(self, fn: Callable[[], Any], timeout: float | None = None) -> Any:
        """Run ``fn`` on the Tk thread and return its value; called on a server thread.

        Raises ``TimeoutError`` when the window did not drain the queue in time (the job is not
        cancelled: it still runs when the window gets to it, and its value is discarded).
        """
        job = _Job(fn)
        self._jobs.put(job)
        timeout = self.job_timeout if timeout is None else timeout
        if not job.done.wait(timeout):
            raise TimeoutError(f"the window did not answer within {timeout:.0f} s")
        if job.cancelled:
            raise TimeoutError("the window closed before answering")
        if job.error is not None:
            raise job.error
        return job.result

    def _pump(self) -> None:
        if self._stopped:
            return
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                break
            try:
                job.result = job.fn()
            except Exception as exc:  # noqa: BLE001  (the handler turns it into a Result.failure)
                job.error = exc
            job.done.set()
        if not self._stopped:
            self._pump_job = self.window.after(PUMP_MS, self._pump)

    def count_request(self) -> int:
        with self._count_lock:
            self.requests += 1
            return self.requests

    # -- what the endpoints compute, all on the Tk thread --------------------------------------
    def status_data(self) -> dict[str, Any]:
        window = self.window
        locks = guard.describe(window.brain.db_path)
        return {
            "tool": TOOL,
            "version": __version__,
            "pid": os.getpid(),
            "db": window.brain.db_path,
            "screen": window.current_key,
            "theme": {"key": window.theme.key, "title": window.theme.title},
            "started_at": self.started_at,
            "uptime_s": round(time.monotonic() - self._started, 3),
            "port": self.port,
            "requests": self.requests,
            "events_seq": window.brain.events.seq,
            "lock": {"family": locks["family"], "database": locks["database"]},
        }

    def execute(self, verb: str, args: dict[str, Any], actor: str) -> Result:
        refused = self.window.remote_guard(verb, args)
        if refused is not None:
            return refused
        return self.window.brain.execute(verb, args, actor=actor)

    def screens_data(self) -> dict[str, Any]:
        window = self.window
        return {
            "screens": [
                {"key": key, "title": title, "current": key == window.current_key}
                for key, title in window.factory.items()
            ]
        }

    def show_screen(self, key: str) -> Result:
        try:
            self.window.show(key)
        except NotFound as exc:
            return Result.failure(str(exc), verb="screen")
        return Result.success({"screen": key, "title": self.window.factory.title(key)}, verb="screen")

    def events_data(self, since: int, limit: int) -> Result:
        bus = self.window.brain.events
        events = bus.since(since, limit)
        warnings: list[str] = []
        oldest = bus.oldest_seq()
        dropped = (oldest - 1) if oldest is not None else bus.seq  # events that fell out of the history
        if since < dropped:
            warnings.append(
                f"events {since + 1}..{dropped} are no longer in the history (it keeps the last "
                f"{bus.history.maxlen}); start again from seq {dropped}"
            )
        return Result.success({"since": since, "seq": bus.seq, "events": events}, warnings=warnings, verb="events")

    def schedule_quit(self) -> Result:
        self.window.after(QUIT_DELAY_MS, self.window.close)
        return Result.success({"quit": True}, verb="quit")


class _Handler(BaseHTTPRequestHandler):
    automation: AutomationServer  # bound per server by ``AutomationServer.start``
    protocol_version = "HTTP/1.1"
    server_version = f"asi-kletz/{__version__}"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002  (the base signature)
        log.debug("%s " + format, self.address_string(), *args)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._handle("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._handle("DELETE")

    # -- plumbing ----------------------------------------------------------------------------
    def _answer(self, status: int, result: Result) -> None:
        body = result.to_json(indent=None).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _drain(self) -> None:
        """Read and drop a body we refused before looking at it, so the socket closes cleanly."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if 0 < length <= MAX_BODY:
            self.rfile.read(length)

    def _body(self) -> Any:
        """The JSON body, or ``None`` when there is none. Raises ``ValueError`` on bad JSON."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("bad Content-Length") from None
        if length <= 0:
            return None
        if length > MAX_BODY:
            raise _TooLarge(length)
        raw = self.rfile.read(length)
        if not raw.strip():
            return None
        return json.loads(raw.decode("utf-8"))

    def _authorised(self) -> bool:
        header = self.headers.get("Authorization") or ""
        scheme, _, token = header.partition(" ")
        return scheme.lower() == "bearer" and secrets.compare_digest(token.strip(), self.automation.token)

    def _handle(self, method: str) -> None:
        server = self.automation
        server.count_request()
        if self.headers.get("Origin") is not None:
            self._drain()
            self._answer(403, Result.failure("browser requests are refused"))
            return
        if not self._authorised():
            self._drain()
            self._answer(401, Result.failure("bad token"))
            return
        parts = urlsplit(self.path)
        path = parts.path.rstrip("/") or "/"
        expected = ROUTES.get(path)
        if expected is None:
            self._drain()
            self._answer(404, Result.failure(f"unknown path {path!r}; known: {', '.join(ROUTES)}"))
            return
        if method != expected:
            self._drain()
            self._answer(405, Result.failure(f"{path} takes {expected}, not {method}"))
            return
        try:
            body = self._body() if method == "POST" else None
        except _TooLarge as exc:
            self._answer(413, Result.failure(f"body of {exc.length} bytes is over the {MAX_BODY} byte limit"))
            return
        except (ValueError, UnicodeDecodeError) as exc:
            self._answer(400, Result.failure(f"body is not JSON: {exc}"))
            return
        if method == "POST" and body is not None and not isinstance(body, dict):
            self._answer(400, Result.failure("body must be a JSON object"))
            return
        try:
            status, result = self._route(path, body or {}, parse_qs(parts.query))
        except TimeoutError as exc:
            status, result = 504, Result.failure(str(exc))
        except Exception as exc:  # noqa: BLE001  (a job raised: the window's problem, reported honestly)
            log.exception("automation request %s %s failed", method, path)
            status, result = 500, Result.failure(f"{type(exc).__name__}: {exc}")
        self._answer(status, result)

    def _route(self, path: str, body: dict[str, Any], query: dict[str, list[str]]) -> tuple[int, Result]:
        server = self.automation
        if path == "/status":
            return 200, Result.success(server.on_main(server.status_data), verb="status")
        if path == "/execute":
            if "verb" not in body:
                return 200, Result.failure("payload must be an object with a 'verb' key")
            verb = str(body["verb"])
            args = body.get("args") or {}
            if not isinstance(args, dict):
                return 200, Result.failure("'args' must be an object", verb=verb)
            actor = str(body.get("actor") or DEFAULT_ACTOR)
            if verb == "gui":
                return 200, Result.failure("the window is already open", verb=verb)
            return 200, server.on_main(lambda: server.execute(verb, args, actor))
        if path == "/screens":
            return 200, Result.success(server.on_main(server.screens_data), verb="screens")
        if path == "/screen":
            key = body.get("show")
            if not isinstance(key, str) or not key:
                return 200, Result.failure("body needs a 'show' key naming the screen", verb="screen")
            return 200, server.on_main(lambda: server.show_screen(key))
        if path == "/events":
            try:
                since = int(query.get("since", ["0"])[0])
                limit = int(query.get("limit", [str(EVENTS_LIMIT)])[0])
            except ValueError:
                return 400, Result.failure("since and limit must be integers")
            return 200, server.on_main(lambda: server.events_data(since, limit))
        if path == "/quit":
            return 200, server.on_main(server.schedule_quit)
        return 404, Result.failure(f"unknown path {path!r}")


class _TooLarge(Exception):
    def __init__(self, length: int) -> None:
        self.length = length
        super().__init__(f"body too large: {length} bytes")
