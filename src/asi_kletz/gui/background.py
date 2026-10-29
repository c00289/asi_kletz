"""BackgroundFetch: one piece of work on a daemon thread, polled from the Tk thread with ``after``.

The family's pattern for anything that takes seconds: the thread touches no widget, whoever
started it polls ``done`` with ``after`` and reports on the Tk thread, nobody joins the thread, so
a window closed mid-work never waits. The Jira fetches, the comments window, the Find page and the
Outlook look-up run ``BackgroundFetch(window, verb, **args)``, which is ``window.execute_quiet``
(``Brain.execute`` as ``gui`` and nothing else). Since 0.24.0 the Control structures screen runs
escher's export (seconds) and the OCR gate (three to five seconds) the same way, and
``BackgroundFetch.call(window, name, fn, *args)`` runs any callable whose answer is a ``Result`` or
any value, for the preview that needs no verb.

The one thing a verb may publish from the worker is a topic ``MainWindow._on_event`` returns on
before any Tk call (``jira.live``, ``cs.exported``); no verb run here changes a database row.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..commands import Result

if TYPE_CHECKING:
    from .main_window import MainWindow

POLL_MS = 100  # how often the Tk thread looks at a running fetch
WAIT_FETCH_TIMEOUT = 5.0  # `wait_fetch`, the test helper: pump the loop at most this long


class BackgroundFetch:
    """One ``window.execute_quiet(verb, **args)`` on a daemon thread; ``result`` is set when it is done."""

    def __init__(self, window: MainWindow, verb: str, **args: Any) -> None:
        self.verb = verb
        self.args = dict(args)
        self.result: Result | None = None
        self.value: Any = None  # what ``call`` computed, when the work was a callable
        self.thread = threading.Thread(
            target=self._run, args=(lambda: window.execute_quiet(verb, **self.args),), daemon=True,
            name=f"asi-kletz {verb} {args.get('action', '')}".rstrip(),
        )

    @classmethod
    def call(cls, window: MainWindow, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> BackgroundFetch:
        """A fetch that runs ``fn(*args, **kwargs)`` instead of a verb; ``value`` is its answer and
        ``result`` a success carrying it, or a failure naming the exception."""
        fetch = cls.__new__(cls)
        fetch.verb = name
        fetch.args = dict(kwargs)
        fetch.result = None
        fetch.value = None
        fetch.thread = threading.Thread(
            target=fetch._run, args=(lambda: fn(*args, **kwargs),), daemon=True, name=f"asi-kletz {name}",
        )
        return fetch

    def start(self) -> BackgroundFetch:
        self.thread.start()
        return self

    @property
    def done(self) -> bool:
        return self.result is not None

    def _run(self, work: Callable[[], Any]) -> None:
        try:
            answer = work()
        except Exception as exc:  # the API answers with a Result, but the poll must end whatever happens
            answer = Result.failure(f"{type(exc).__name__}: {exc}", verb=self.verb)
        if isinstance(answer, Result):
            result = answer
        else:
            self.value = answer
            result = Result.success(answer, verb=self.verb)
        self.result = result  # the last write: `done` flips only once everything else is in place
