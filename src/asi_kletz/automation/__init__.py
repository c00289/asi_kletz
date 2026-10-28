"""Automation: CLI, event bus, script replay, and the local server a running window exposes.

``server.py`` is the loopback HTTP server the window owns (JSON ``Result`` answers, bearer
token, the main-thread handshake); ``session.py`` is the session file that tells a CLI or an
agent where it is, and the ``probe`` / ``forward`` calls the CLI uses to drive the window.
"""

from .events import EventBus

__all__ = ["EventBus"]
