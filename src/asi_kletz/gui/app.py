"""Entry point for the desktop window: ``asi-kletz-gui`` or ``python -m asi_kletz gui``."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from ..version import __version__

if TYPE_CHECKING:
    from ..brain import Brain
    from ..locks import PrimaryToolBusy

EXIT_BUSY = 3  # another primary tool holds the family lock


def launch(brain: Brain, interactive: bool = True, theme: str | None = None, server: bool = True) -> None:
    """Open the main window on an existing Brain and block until it is closed.

    ``server=False`` (``--no-server``) opens it without the local automation server; so does
    ``ASI_KLETZ_AUTOMATION=off``.
    """
    from .main_window import MainWindow

    window = MainWindow(brain, interactive=interactive, theme=theme, server=server)
    window.mainloop()


def ask_retry(exc: PrimaryToolBusy) -> bool:
    """The busy dialog: the holder line with Retry / Quit. ``True`` means try once more."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        return bool(messagebox.askretrycancel("ASI Kletz is busy", str(exc), parent=root))
    finally:
        root.destroy()


def open_brain(db: str | None, wait: float, interactive: bool) -> Brain | None:
    """A Brain on ``db``, or ``None`` after a refusal the person did not retry (or could not see)."""
    from ..brain import Brain
    from ..locks import PrimaryToolBusy

    for attempt in (1, 2):  # Retry re-attempts once; a second refusal is final
        try:
            return Brain(db, wait=wait)
        except PrimaryToolBusy as exc:
            if attempt == 2 or not interactive or not ask_retry(exc):
                print(str(exc), file=sys.stderr)
                return None
    return None


def main(argv: list[str] | None = None, *, interactive: bool = True) -> int:
    parser = argparse.ArgumentParser(prog="asi-kletz-gui", description="ASI Kletz desktop window.")
    parser.add_argument("--db", help="SQLite file (default: $ASI_KLETZ_DB or ./kletz.db)")
    parser.add_argument(
        "--theme",
        help="Theme key for this launch only (see `asi-kletz theme`): a palette such as pink-noir or plain; "
        "also $ASI_KLETZ_THEME. Default: the latched preference, else cyan-neon",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Queue for the family lock this long (polling every 250 ms) before the busy dialog; "
        "exit code 3 when the slot stays taken",
    )
    parser.add_argument(
        "--no-server",
        action="store_true",
        help="Open the window without the local automation server for this launch (no session file; "
        "the CLI is then refused with exit code 3 while the window is open). Also ASI_KLETZ_AUTOMATION=off",
    )
    parser.add_argument("--version", action="version", version=f"asi-kletz-gui {__version__}")
    ns = parser.parse_args(argv)
    from .theme import ThemeFactory

    brain = open_brain(ns.db, ns.wait, interactive)
    if brain is None:
        return EXIT_BUSY
    with brain:
        launch(brain, interactive=interactive, theme=ThemeFactory.resolve(ns.theme), server=not ns.no_server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
