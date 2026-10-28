"""tkinter front end. Every action goes through ``Brain.execute`` with actor ``gui``.

Import this package lazily: it pulls in tkinter, which the API and CLI never need.
"""

from .app import launch
from .theme import Theme, ThemeFactory, TronTheme

__all__ = ["launch", "Theme", "ThemeFactory", "TronTheme"]
