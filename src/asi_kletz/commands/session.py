"""The ``session`` verb: the automation session of a running window, and ``--quit`` to close it.

The one verb the CLI runs without opening a ``Brain``: it touches no database and must work
while a window holds the family lock. ``report()`` is the whole of it, so the CLI short-circuits
to it before ``Brain(...)``; registered like every other verb, it is also in ``schema``, in
``--help``, callable from Python and through ``/execute`` (where it reports the window's own
session without going through HTTP, which would stall the Tk thread it runs on).

The token is never in the printed data: it is in the file, for anyone who can read the file.
"""

from __future__ import annotations

import os
import time
from typing import Any

from .base import Argument, Command, Context, Result
from .factory import register_command

QUIT_WAIT = 5.0
QUIT_POLL = 0.1


@register_command
class SessionCommand(Command):
    verb = "session"
    help = (
        "Report the automation session of a running window (the session file, whether its pid is alive, "
        "whether /status answers); --quit closes that window. Opens no database."
    )
    arguments = (
        Argument(
            "quit",
            "POST /quit to the live session, then wait up to 5 s for its session file to go",
            flag=True,
            type="bool",
            default=False,
        ),
    )

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        return self.report(quit=bool(args.get("quit")))

    @staticmethod
    def report(quit: bool = False) -> Result:
        from ..automation import server as server_module
        from ..automation.session import (
            SessionUnreachable,
            probe,
            public_view,
            quit_session,
            read_session,
            session_path,
        )

        path = session_path()
        session = read_session()
        own = server_module.current()  # this process is the window: no HTTP to itself
        own = own if own is not None and session is not None and session.get("pid") == os.getpid() else None
        status: dict[str, Any] | None
        if session is None:
            status = None
        elif own is not None:
            status = own.status_data()
        else:
            status = probe(session)
        data: dict[str, Any] = {
            "path": str(path),
            "present": path.exists(),
            "alive": session is not None,
            "reachable": status is not None,
            "session": public_view(session) if session is not None else None,
            "status": status,
            "quit": False,
        }
        if not quit:
            return Result.success(data, verb="session")
        if session is None or status is None:
            return Result.failure("no live automation session to quit", data=data, verb="session")
        if own is not None:
            own.schedule_quit()  # the window closes 100 ms later; waiting here would block its own thread
            data["quit"] = True
            return Result.success(data, warnings=["this window is closing"], verb="session")
        try:
            answer = quit_session(session)
        except SessionUnreachable as exc:
            return Result.failure(f"the automation session at {session['address']} did not answer ({exc})",
                                  data=data, verb="session")
        if not answer.ok:
            return Result.failure(*answer.errors, data=data, verb="session")
        data["quit"] = True
        deadline = time.monotonic() + QUIT_WAIT
        while path.exists() and time.monotonic() < deadline:
            time.sleep(QUIT_POLL)
        warnings = [] if not path.exists() else [f"the session file is still there after {QUIT_WAIT:.0f} s"]
        data["present"] = path.exists()
        return Result.success(data, warnings=warnings, verb="session")
