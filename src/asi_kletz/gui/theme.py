"""Themes: a palette plus the ttk styles and tk option defaults that paint the window.

The house default is ``cyan-neon``, the original look: near-black panels, neon cyan lines, orange
for the active element, a geometric heading face and a monospace status line. The family palette
in ``palettes.py`` registers 31 more (eight hue families, four tones each) under
``<family>-<tone>``; ``tron`` is an alias of ``cyan-neon`` and ``plain`` leaves the native
look alone. Themes are registered in ``ThemeFactory`` and picked by key, the same way screens,
widgets, and commands are. ``apply`` may be called again on the same root: the window repaints
by applying another theme and rebuilding its children.
"""

from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import ttk
from typing import ClassVar, NamedTuple

from ..errors import NotFound

ENV_THEME = "ASI_KLETZ_THEME"
DEFAULT_THEME = "cyan-neon"
NAMED_FONTS = ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkFixedFont")

FontSpec = tuple[str, int] | tuple[str, int, str]


@dataclass(frozen=True)
class Palette:
    """Named colours. Screens never hard-code a colour; they ask the palette."""

    bg: str  # window background
    panel: str  # navigation, status bar, tiles
    field: str  # entries, text areas, tables
    grid: str  # borders, grid lines, sashes
    stripe: str  # alternate table rows
    primary: str  # the neon
    primary_dim: str  # the neon, further away
    accent: str  # the other neon, for the active element
    text: str
    muted: str
    on_primary: str  # text drawn over a primary or accent fill
    selection: str  # selected table row


@dataclass(frozen=True)
class NativeLook:
    """What the platform painted before any theme touched the root; restored on every ``apply``."""

    ttk_theme: str
    background: str
    fonts: dict[str, tuple[str, int]]


def native_look(root: tk.Tk) -> NativeLook:
    """Record the platform ttk theme, root background and named fonts once per root."""
    look = getattr(root, "_native_look", None)
    if look is None:
        fonts: dict[str, tuple[str, int]] = {}
        for name in NAMED_FONTS:
            try:
                font = tkfont.nametofont(name, root)
                fonts[name] = (str(font.cget("family")), int(font.cget("size")))
            except tk.TclError:
                pass
        look = NativeLook(ttk.Style(root).theme_use(), str(root.cget("background")), fonts)
        root._native_look = look  # type: ignore[attr-defined]
    return look


class Theme:
    """Base theme: picks fonts, paints nothing. Subclasses override ``paint``."""

    key: ClassVar[str] = "plain"
    title: ClassVar[str] = "Plain (native)"
    family: ClassVar[str] = ""  # set on catalog themes; empty means "not a palette"
    tone: ClassVar[str] = ""
    palette: ClassVar[Palette] = Palette(
        bg="#f0f0f0", panel="#f0f0f0", field="#ffffff", grid="#c8c8c8", stripe="#f6f6f6",
        primary="#1a5fb4", primary_dim="#3b7dd8", accent="#c64600", text="#1e1e1e",
        muted="#666666", on_primary="#ffffff", selection="#cce4ff",
    )
    heading_families: ClassVar[tuple[str, ...]] = ("Segoe UI Semibold", "Segoe UI")
    ui_families: ClassVar[tuple[str, ...]] = ("Segoe UI",)
    mono_families: ClassVar[tuple[str, ...]] = ("Cascadia Mono", "Consolas", "Courier New")
    ttk_base: ClassVar[str | None] = None  # None: keep whatever ttk picked for the platform

    def __init__(self) -> None:
        self.ui: FontSpec = ("TkDefaultFont", 10)
        self.heading: FontSpec = ("TkDefaultFont", 10, "bold")
        self.display: FontSpec = ("TkDefaultFont", 20, "bold")
        self.mono: FontSpec = ("TkFixedFont", 9)

    # -- fonts ------------------------------------------------------------
    @staticmethod
    def pick(candidates: tuple[str, ...], available: set[str], fallback: str) -> str:
        return next((c for c in candidates if c in available), fallback)

    def choose_fonts(self, root: tk.Misc) -> None:
        available = set(tkfont.families(root))
        ui = self.pick(self.ui_families, available, "TkDefaultFont")
        heading = self.pick(self.heading_families, available, ui)
        mono = self.pick(self.mono_families, available, "TkFixedFont")
        self.ui = (ui, 10)
        self.heading = (heading, 10, "bold")
        self.display = (heading, 22, "bold")
        self.mono = (mono, 9)

    # -- entry point ------------------------------------------------------
    def apply(self, root: tk.Tk) -> None:
        """Paint the root. Re-entrant: every call starts from the native look recorded on the first."""
        native = native_look(root)
        style = ttk.Style(root)
        root.option_clear()
        root.configure(background=native.background)
        for name, (family, size) in native.fonts.items():
            try:
                tkfont.nametofont(name, root).configure(family=family, size=size)
            except tk.TclError:
                pass
        base = self.ttk_base or native.ttk_theme
        if base in style.theme_names():
            style.theme_use(base)
        self.choose_fonts(root)
        self.paint(root, style)

    def paint(self, root: tk.Tk, style: ttk.Style) -> None:
        """Configure styles and option defaults. The plain theme only names its label styles."""
        style.configure("Muted.TLabel", foreground=self.palette.muted)
        style.configure("Title.TLabel", font=self.display, foreground=self.palette.primary)
        style.configure("Subtitle.TLabel", font=self.heading, foreground=self.palette.muted)
        style.configure("Tile.TFrame", relief="groove", borderwidth=1)
        style.configure("TileHover.TFrame", relief="groove", borderwidth=1)
        style.configure("TileCount.TLabel", font=self.display, foreground=self.palette.primary)
        style.configure("TileName.TLabel", foreground=self.palette.muted)
        style.configure("Rule.TFrame", background=self.palette.grid)
        style.configure("Nav.TFrame")
        style.configure("Nav.TLabel")
        style.configure("Status.TFrame", relief="sunken")
        style.configure("Status.TLabel", font=self.mono)
        style.configure("StatusMuted.TLabel", font=self.mono, foreground=self.palette.muted)

    # -- helpers used by screens ------------------------------------------
    def stripe(self, tree: ttk.Treeview) -> None:
        """Alternate row backgrounds; call after a table has been filled."""
        tree.tag_configure("odd", background=self.palette.stripe)
        tree.tag_configure("even", background=self.palette.field)
        for index, iid in enumerate(tree.get_children()):
            tree.item(iid, tags=("odd" if index % 2 else "even",))


class GridTheme(Theme):
    """The grid. Dark or light panels, light lines in one hue, the accent hue for whatever is live.

    One subclass per catalog entry is registered at import time with ``palette`` set from
    ``palettes.CATALOG``; the recipe below is the same for every tone.
    """

    key = "cyan-neon"
    title = "Cyan Neon"
    family = "cyan"
    tone = "neon"
    palette = Palette(
        bg="#040e10", panel="#081b1f", field="#0b2328", grid="#114550", stripe="#0e2a2f",
        primary="#1ad9ff", primary_dim="#0d88a0", accent="#ff851a", text="#c9f0f7",
        muted="#609da9", on_primary="#03171c", selection="#125a68",
    )
    heading_families = ("Orbitron", "Bahnschrift SemiBold", "Bahnschrift", "Agency FB", "Segoe UI Semibold")
    ui_families = ("Bahnschrift", "Segoe UI")
    mono_families = ("Cascadia Mono", "Consolas", "OCR A Extended", "Courier New")
    ttk_base = "clam"

    def choose_fonts(self, root: tk.Misc) -> None:
        super().choose_fonts(root)
        family = self.ui[0]
        for name, size in (("TkDefaultFont", 10), ("TkTextFont", 10), ("TkMenuFont", 10), ("TkHeadingFont", 10)):
            try:
                tkfont.nametofont(name, root).configure(family=family, size=size)
            except tk.TclError:
                pass
        try:
            tkfont.nametofont("TkFixedFont", root).configure(family=self.mono[0], size=self.mono[1])
        except tk.TclError:
            pass

    def paint(self, root: tk.Tk, style: ttk.Style) -> None:
        p = self.palette
        root.configure(background=p.bg)

        # tk (non-ttk) widgets take their defaults from the option database
        for pattern, value in (
            ("*Listbox.background", p.panel), ("*Listbox.foreground", p.text),
            ("*Listbox.selectBackground", p.primary), ("*Listbox.selectForeground", p.on_primary),
            ("*Listbox.highlightThickness", 0), ("*Listbox.borderWidth", 0), ("*Listbox.font", self.ui),
            ("*Text.background", p.field), ("*Text.foreground", p.text), ("*Text.insertBackground", p.primary),
            ("*Text.selectBackground", p.selection), ("*Text.selectForeground", p.text),
            ("*Text.highlightThickness", 1), ("*Text.highlightBackground", p.grid), ("*Text.highlightColor", p.primary),
            ("*Text.borderWidth", 0), ("*Text.font", self.mono),
            ("*Canvas.background", p.bg), ("*Canvas.highlightThickness", 0),
            ("*Menu.background", p.panel), ("*Menu.foreground", p.text), ("*Menu.activeBackground", p.primary),
            ("*Menu.activeForeground", p.on_primary), ("*Menu.borderWidth", 0), ("*Menu.activeBorderWidth", 0),
            ("*Menu.relief", "flat"), ("*Menu.font", self.ui),
            ("*TCombobox*Listbox.background", p.field), ("*TCombobox*Listbox.foreground", p.text),
            ("*TCombobox*Listbox.selectBackground", p.primary), ("*TCombobox*Listbox.selectForeground", p.on_primary),
            ("*TCombobox*Listbox.font", self.ui),
        ):
            root.option_add(pattern, value)

        style.configure(
            ".", background=p.bg, foreground=p.text, fieldbackground=p.field, bordercolor=p.grid,
            lightcolor=p.bg, darkcolor=p.bg, troughcolor=p.panel, selectbackground=p.selection,
            selectforeground=p.text, insertcolor=p.primary, focuscolor=p.primary, font=self.ui,
        )
        style.configure("TFrame", background=p.bg)
        style.configure("Nav.TFrame", background=p.panel)
        style.configure("Status.TFrame", background=p.panel, relief="flat")
        style.configure("Rule.TFrame", background=p.primary_dim)
        style.configure("Tile.TFrame", background=p.panel, bordercolor=p.grid, relief="solid", borderwidth=1)
        style.configure("TileHover.TFrame", background=p.panel, bordercolor=p.accent, relief="solid", borderwidth=1)

        style.configure("TLabel", background=p.bg, foreground=p.text)
        style.configure("Nav.TLabel", background=p.panel, foreground=p.text)
        style.configure("Muted.TLabel", foreground=p.muted)
        style.configure("Title.TLabel", background=p.panel, foreground=p.primary, font=self.display)
        style.configure("Subtitle.TLabel", background=p.panel, foreground=p.muted, font=self.mono)
        style.configure("Status.TLabel", background=p.panel, foreground=p.primary, font=self.mono)
        style.configure("StatusMuted.TLabel", background=p.panel, foreground=p.muted, font=self.mono)
        style.configure("TileCount.TLabel", background=p.panel, foreground=p.primary, font=self.display)
        style.configure("TileName.TLabel", background=p.panel, foreground=p.muted, font=self.mono)

        style.configure("TLabelframe", background=p.bg, bordercolor=p.grid, relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=p.bg, foreground=p.primary, font=self.heading)

        style.configure(
            "TButton", background=p.panel, foreground=p.primary, bordercolor=p.primary_dim,
            lightcolor=p.panel, darkcolor=p.panel, relief="flat", padding=(12, 4), font=self.heading,
        )
        style.map(
            "TButton",
            background=[("pressed", p.accent), ("active", p.primary)],
            foreground=[("pressed", p.on_primary), ("active", p.on_primary)],
            bordercolor=[("pressed", p.accent), ("active", p.primary)],
            lightcolor=[("pressed", p.accent), ("active", p.primary)],
            darkcolor=[("pressed", p.accent), ("active", p.primary)],
        )

        for kind in ("TEntry", "TCombobox"):
            style.configure(
                kind, fieldbackground=p.field, foreground=p.text, bordercolor=p.grid,
                lightcolor=p.field, darkcolor=p.field, insertcolor=p.primary, padding=4,
                arrowcolor=p.primary, background=p.panel, selectbackground=p.selection,
            )
            style.map(
                kind,
                bordercolor=[("focus", p.primary)], lightcolor=[("focus", p.primary)], darkcolor=[("focus", p.primary)],
                fieldbackground=[("readonly", p.field), ("disabled", p.panel)],
                foreground=[("readonly", p.text), ("disabled", p.muted)],
                arrowcolor=[("active", p.accent)],
            )

        style.configure(
            "TCheckbutton", background=p.bg, foreground=p.text, indicatorbackground=p.field,
            indicatorforeground=p.primary, indicatormargin=(2, 2, 6, 2), padding=2,
        )
        style.map(
            "TCheckbutton",
            background=[("active", p.bg)],
            indicatorbackground=[("selected", p.field), ("active", p.panel)],
            indicatorforeground=[("selected", p.primary)],
            foreground=[("active", p.primary)],
        )

        style.configure(
            "Treeview", background=p.field, fieldbackground=p.field, foreground=p.text,
            bordercolor=p.grid, lightcolor=p.field, darkcolor=p.field, rowheight=24, font=self.ui,
        )
        style.map("Treeview", background=[("selected", p.selection)], foreground=[("selected", p.text)])
        style.configure(
            "Treeview.Heading", background=p.panel, foreground=p.primary, bordercolor=p.grid,
            lightcolor=p.panel, darkcolor=p.panel, relief="flat", font=self.heading, padding=(6, 4),
        )
        style.map("Treeview.Heading", background=[("active", p.grid)], foreground=[("active", p.accent)])

        # the thumb (the slider a person drags) is the live element: the dimmed primary at rest, the neon
        # under the pointer; the trough stays the background (owner, 2026-10-29)
        style.configure(
            "TScrollbar", background=p.primary_dim, troughcolor=p.bg, bordercolor=p.bg,
            lightcolor=p.primary_dim, darkcolor=p.primary_dim, arrowcolor=p.primary_dim, arrowsize=12,
        )
        style.map("TScrollbar", background=[("active", p.primary)], arrowcolor=[("active", p.primary)])

        style.configure("TPanedwindow", background=p.bg)
        style.configure("Sash", sashthickness=4, gripcount=0, background=p.grid)


class ThemeEntry(NamedTuple):
    """One palette theme as the picker and the ``theme`` verb list it."""

    key: str
    title: str
    family: str
    tone: str
    palette: Palette


class ThemeFactory:
    """Key -> theme class. ``create`` instantiates; ``resolve`` applies the precedence of a launch."""

    _registry: ClassVar[dict[str, type[Theme]]] = {}
    _aliases: ClassVar[dict[str, str]] = {}

    @classmethod
    def register(cls, theme: type[Theme]) -> type[Theme]:
        cls._registry[theme.key] = theme
        return theme

    @classmethod
    def alias(cls, key: str, target: str) -> None:
        """``key`` resolves to the class registered as ``target``; it is listed in ``keys`` but not ``entries``."""
        if target not in cls._registry:
            raise NotFound(f"cannot alias {key!r}: unknown theme {target!r}")
        cls._aliases[key] = target

    @classmethod
    def keys(cls) -> list[str]:
        return [*cls._registry, *cls._aliases]

    @classmethod
    def canonical(cls, key: str) -> str:
        """The registered key behind an alias; other keys come back unchanged."""
        return cls._aliases.get(key, key)

    @classmethod
    def known(cls, key: str | None) -> bool:
        return bool(key) and cls.canonical(str(key)) in cls._registry

    @classmethod
    def entries(cls) -> list[ThemeEntry]:
        """The palette themes in catalog order: aliases and ``plain`` excluded."""
        return [
            ThemeEntry(theme.key, theme.title, theme.family, theme.tone, theme.palette)
            for theme in cls._registry.values()
            if theme.family
        ]

    @classmethod
    def default_key(cls) -> str:
        """The house default, used when nothing is latched and nothing overrides."""
        return DEFAULT_THEME

    @classmethod
    def resolve(cls, explicit: str | None = None) -> str:
        """``explicit`` argument, else ``$ASI_KLETZ_THEME``, else the latched preference, else the house default.

        An explicit or environment key is returned as given (``create`` rejects an unknown one);
        a latched key that is no longer known falls through to the default.
        """
        from ..prefs import read_prefs

        for candidate in (explicit, os.environ.get(ENV_THEME)):
            if candidate:
                return cls.canonical(candidate) if cls.known(candidate) else candidate
        latched = read_prefs().get("theme")
        if cls.known(latched):
            return cls.canonical(str(latched))
        return cls.default_key()

    @classmethod
    def create(cls, key: str | None = None) -> Theme:
        key = cls.canonical(key or cls.resolve())
        try:
            return cls._registry[key]()
        except KeyError:
            known = ", ".join(cls.keys())
            raise NotFound(f"unknown theme {key!r}; known: {known}") from None


class GridBanner(tk.Canvas):
    """A strip of receding grid lines with a title on it. Pure decoration, redrawn on resize."""

    def __init__(self, master: tk.Misc, theme: Theme, title: str, subtitle: str = "", height: int = 88) -> None:
        super().__init__(master, height=height, highlightthickness=0, background=theme.palette.bg)
        self.theme = theme
        self.banner_title = title
        self.banner_subtitle = subtitle
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self) -> None:
        self.delete("all")
        p = self.theme.palette
        w, h = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        horizon = int(h * 0.52)  # room above for the display-size title
        # horizontal lines bunch up toward the horizon
        for step in range(1, 9):
            y = horizon + int((h - horizon) * (step / 8) ** 1.7)
            self.create_line(0, y, w, y, fill=p.grid)
        # vertical lines fan out from a vanishing point above the horizon
        vanish_x, vanish_y = w // 2, horizon - h
        for x in range(-w, 2 * w, max(w // 16, 40)):
            self.create_line(vanish_x, vanish_y, x, h, fill=p.grid)
        self.create_line(0, horizon, w, horizon, fill=p.primary_dim)
        self.create_rectangle(0, 0, w, horizon, fill=p.bg, outline="")
        self.create_text(12, horizon - 6, text=self.banner_title, anchor="sw", fill=p.primary, font=self.theme.display)
        if self.banner_subtitle:
            self.create_text(
                w - 12, horizon - 8, text=self.banner_subtitle, anchor="se", fill=p.muted, font=self.theme.mono
            )


# -- registration ---------------------------------------------------------
# ``palettes`` imports ``Palette`` from this module, so it can only be imported once that
# class exists: one GridTheme subclass per catalog entry, the ``tron`` alias, then ``plain``.
from .palettes import CATALOG  # noqa: E402

for _key, _entry in CATALOG.items():
    ThemeFactory.register(type(
        f"{_key}Theme", (GridTheme,),
        {"key": _key, "title": _entry.title, "family": _entry.family, "tone": _entry.tone, "palette": _entry.palette},
    ))
ThemeFactory.alias("tron", "cyan-neon")
ThemeFactory.register(Theme)

TronTheme = ThemeFactory._registry["cyan-neon"]  # the former name of the cyan-neon class
