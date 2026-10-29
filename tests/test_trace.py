"""The window's trace (0.18.1): gui.log beside the preferences says how every window started and ended."""

from __future__ import annotations

import faulthandler
from pathlib import Path

import pytest

from asi_kletz.gui import trace
from asi_kletz.version import __version__


def _log(tmp_path: Path) -> str:
    return (tmp_path / "gui.log").read_text(encoding="utf-8")


@pytest.fixture
def window(seeded):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(seeded, interactive=False, server=False)
    yield win
    win.close()


def test_the_log_sits_beside_the_preferences_and_records_start_and_close(window, tmp_path):
    """The conftest points ``$ASI_KLETZ_PREFS`` at tmp_path, so the log lands there too."""
    assert trace.log_path() == tmp_path / "gui.log" and faulthandler.is_enabled()
    text = _log(tmp_path)
    assert "start pid=" in text and f"version={__version__}" in text and "server=off" in text
    window.close()
    lines = _log(tmp_path).splitlines()
    close = next(line for line in lines if " close via=" in line)
    assert "test_the_log_sits_beside_the_preferences" in close  # the caller that asked, by name and line
    assert "(test_trace.py:" in close and lines[-1].endswith("destroyed")
    window.close()  # idempotent: no second close line
    assert sum(1 for line in _log(tmp_path).splitlines() if " close via=" in line) == 1


def test_launch_notes_the_main_loop_returning_and_ends_the_trace(seeded, tmp_path, monkeypatch):
    from asi_kletz.gui import app
    from asi_kletz.gui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "mainloop", lambda self: self.close())  # a window that closes at once
    app.launch(seeded, interactive=False, server=False)
    text = _log(tmp_path)
    assert "mainloop returned closed=True" in text and text.rstrip().endswith("end")
    assert trace._handle is None  # released; a later window starts a new one


def test_an_exception_escaping_the_main_loop_is_noted_then_raised(seeded, tmp_path, monkeypatch):
    from asi_kletz.gui import app
    from asi_kletz.gui.main_window import MainWindow

    def boom(self):
        self.close()
        raise RuntimeError("tk went away")

    monkeypatch.setattr(MainWindow, "mainloop", boom)
    with pytest.raises(RuntimeError, match="tk went away"):
        app.launch(seeded, interactive=False, server=False)
    text = _log(tmp_path)
    assert "exception kind=RuntimeError text=tk went away" in text and "mainloop returned" in text


def test_a_folder_that_cannot_be_written_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("ASI_KLETZ_PREFS", str(tmp_path / "nowhere" / "prefs.json"))
    (tmp_path / "nowhere").write_text("a file where the folder should be", encoding="utf-8")
    assert trace.start("0.0.0", server=False) is None
    trace.note("ignored")  # never raises
    trace.stop()


def test_a_big_log_rolls_over(tmp_path, monkeypatch):
    monkeypatch.setenv("ASI_KLETZ_PREFS", str(tmp_path / "p" / "prefs.json"))
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "gui.log").write_text("x" * (trace.LIMIT + 1), encoding="utf-8")
    assert trace.start("0.0.0", server=True) == tmp_path / "p" / "gui.log"
    trace.stop()
    assert (tmp_path / "p" / "gui.log.1").stat().st_size == trace.LIMIT + 1
    assert "start pid=" in (tmp_path / "p" / "gui.log").read_text(encoding="utf-8")
