"""The family palette, the theme factory, the precedence of a launch, and the preferences file."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from asi_kletz.errors import NotFound
from asi_kletz.gui import palettes
from asi_kletz.gui.palettes import CATALOG, CATALOG_DIGEST, FAMILIES, TONES
from asi_kletz.gui.theme import DEFAULT_THEME, ENV_THEME, GridTheme, Palette, Theme, ThemeFactory, TronTheme
from asi_kletz.prefs import ENV_PREFS, prefs_path, read_prefs, write_prefs

REPO_ROOT = Path(__file__).resolve().parent.parent
FAMILY_FILE = Path(__file__).resolve().parents[2] / "asi_fusa_tools" / "ASI_FUSA_TOOLS.md"
SLOTS = ("bg", "panel", "field", "grid", "stripe", "primary", "primary_dim", "accent", "text", "muted",
         "on_primary", "selection")
HEX = re.compile(r"^#[0-9a-f]{6}$")


def catalog_digest() -> str:
    table = {key: {slot: getattr(entry.palette, slot) for slot in SLOTS} for key, entry in CATALOG.items()}
    return hashlib.sha1(json.dumps(table, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()


# -- the catalog ---------------------------------------------------------------
def test_catalog_has_eight_families_times_four_tones_in_order():
    assert len(FAMILIES) == 8 and len(TONES) == 4 and len(CATALOG) == 32
    assert list(CATALOG) == [f"{family}-{tone}" for family in FAMILIES for tone in TONES]
    for key, entry in CATALOG.items():
        family, tone = key.split("-")
        assert (entry.family, entry.tone) == (family, tone)
        assert entry.title == f"{family.title()} {tone.title()}"
        assert isinstance(entry.palette, Palette)
        for slot in SLOTS:
            assert HEX.match(getattr(entry.palette, slot)), (key, slot)
    assert len({entry.palette.primary for entry in CATALOG.values()}) == 32


def test_catalog_digest_matches_the_family_convention():
    assert catalog_digest() == CATALOG_DIGEST == "befcfc0c8dca5479620badf1d23e2448db757910"
    if FAMILY_FILE.exists():  # the authority; absent when the repo is tested on its own
        text = FAMILY_FILE.read_text(encoding="utf-8")
        assert text.splitlines()[0] == "# ASI FuSa Tools"  # the charter, not a stale copy under the old name
        assert CATALOG_DIGEST in text


def _luminance(colour: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


STRICT = (("text", "bg"), ("text", "field"), ("primary", "panel"), ("primary", "bg"),
          ("on_primary", "primary"), ("on_primary", "accent"))
RELAXED = (("muted", "bg"), ("muted", "panel"), ("accent", "panel"), ("text", "selection"), ("primary_dim", "bg"))


@pytest.mark.parametrize("key", list(CATALOG))
def test_every_palette_holds_the_contrast_floors(key):
    palette = CATALOG[key].palette
    for fg, bg in STRICT:
        assert contrast(getattr(palette, fg), getattr(palette, bg)) >= 4.5, (key, fg, bg)
    for fg, bg in RELAXED:
        assert contrast(getattr(palette, fg), getattr(palette, bg)) >= 3.0, (key, fg, bg)


def test_palettes_module_is_pure_data():
    tree = ast.parse(Path(palettes.__file__).read_text(encoding="utf-8"))
    imports = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    names = sorted((node.module, tuple(alias.name for alias in node.names)) for node in imports)
    assert names == [("theme", ("Palette",)), ("typing", ("NamedTuple",))]
    assert all(node.level == 1 for node in imports if node.module == "theme")  # a relative import, never a sister
    forbidden = "asi_" + "dewey"
    assert forbidden not in Path(palettes.__file__).read_text(encoding="utf-8")


# -- the factory ---------------------------------------------------------------
def test_factory_registers_catalog_alias_and_plain():
    keys = ThemeFactory.keys()
    assert len(keys) == 34 and set(keys) == set(CATALOG) | {"tron", "plain"}
    tron = ThemeFactory.create("tron")
    assert isinstance(tron, TronTheme) and isinstance(tron, GridTheme) and tron.key == "cyan-neon"
    assert type(tron) is type(ThemeFactory.create("cyan-neon"))
    assert isinstance(ThemeFactory.create("plain"), Theme) and not isinstance(ThemeFactory.create("plain"), GridTheme)
    entries = ThemeFactory.entries()
    assert [e.key for e in entries] == list(CATALOG) and "tron" not in {e.key for e in entries}
    assert entries[0].title == "Cyan Noir" and entries[0].palette.primary == "#12c0e2"
    assert ThemeFactory.create("amber-neon").palette.primary == "#ff851a"
    with pytest.raises(NotFound):
        ThemeFactory.create("neon-pink")
    assert ThemeFactory.default_key() == DEFAULT_THEME == "cyan-neon"


def test_resolve_precedence(monkeypatch):
    assert ThemeFactory.resolve(None) == "cyan-neon"
    write_prefs(theme="pink-noir")
    assert ThemeFactory.resolve(None) == "pink-noir"
    assert ThemeFactory.resolve("plain") == "plain"
    monkeypatch.setenv(ENV_THEME, "green-day")
    assert ThemeFactory.resolve(None) == "green-day"
    assert ThemeFactory.resolve("plain") == "plain"
    assert ThemeFactory.resolve("tron") == "cyan-neon"
    monkeypatch.delenv(ENV_THEME)
    write_prefs(theme="sepia")
    assert ThemeFactory.resolve(None) == "cyan-neon"
    assert ThemeFactory.resolve("bogus") == "bogus"  # an explicit key is handed on; create() rejects it


# -- prefs ---------------------------------------------------------------------
def test_prefs_round_trip(tmp_path, monkeypatch):
    file = tmp_path / "deep" / "er" / "prefs.json"
    monkeypatch.setenv(ENV_PREFS, str(file))
    assert prefs_path() == file
    assert read_prefs() == {}
    assert write_prefs(theme="red-dusk") == file and file.is_file()
    data = json.loads(file.read_text(encoding="utf-8"))
    assert data["theme"] == "red-dusk" and data["tool"] == "asi_kletz" and data["version"] and data["updated_at"]
    write_prefs(other=1)
    assert read_prefs()["theme"] == "red-dusk" and read_prefs()["other"] == 1
    assert not list(file.parent.glob("*.tmp"))
    file.write_text("{not json", encoding="utf-8")
    assert read_prefs() == {}
    write_prefs(theme="gold-day")
    assert read_prefs()["theme"] == "gold-day"
