# ASI Kletz — Plan: the family palette and a latching theme picker

**Status:** Implemented 2026-10-27 (asi_kletz 0.3.0); house default revised to `cyan-neon` the same
day after the first manual check (sections 1.5, 3.2, 7)
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.3.0 (independent of the family lock; either can land first)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md); this plan adds a section "The family palette" there
**Sister plan:** [asi_dewey/docs/theme-palette-plan.md](../../asi_dewey/docs/theme-palette-plan.md).
Same palette catalog, implemented twice, never shared as code.

---

## 1. The ask

Decided by the owner on 2026-10-27:

1. Both primary tools keep the bold Tron look, but they must **not look the same**: a window
   that looks like Kletz must be Kletz. Today both tools paint the identical cyan-and-orange
   `tron` theme, which is the confusion this plan removes.
2. **One shared palette catalog.** Kletz and Dewey offer the same 32 palettes under the same
   names, so a colour the owner learns in one tool means the same thing in the other.
   The catalog includes a **pink family** that runs from near-black to light.
3. **A drop-down in the window.** It always shows a selection, because a theme is always
   needed. Picking a theme repaints the window at once and **latches**: the choice survives a
   restart and holds until the owner picks another.
4. **Each tool latches on its own.** A pick in Kletz never changes Dewey; otherwise the two
   would drift back to looking alike.
5. **One house default.** Before any pick is ever made, both tools open in `cyan-neon` (today's
   `tron`); the latch, not the default, is what tells them apart. Revised 2026-10-27 after the
   first manual check: the draft said Kletz opens in `amber-neon`, and the owner wants the
   original look on first run in both tools.

Kletz's own constraints hold: **still one table, still four screens**. The picker is a control
in the navigation column and a menu cascade, not a fifth screen; `build_default_screens` and the
test that asserts the four keys are untouched. (Written before 0.5.0: the screen-count rule was retired in 0.5.0: screens are registered in `gui/screens.py`, not counted; this
plan added none and the sentence stands as history.)

## 2. What exists today (verified 2026-10-27)

The tree before this plan: `tron` was the default theme and the window had four screens. Since
then the default is `cyan-neon` with `tron` an alias of it (this plan), and screens are registered,
not counted (0.5.0).

| Fact | Where |
|---|---|
| `Palette` has 12 named slots; screens never hard-code a colour. `Theme` (key `plain`) and `TronTheme` (key `tron`) are the two registrations in `ThemeFactory`. | `gui/theme.py` |
| `ThemeFactory.default_key()` is `$ASI_KLETZ_THEME` or `tron`; `create()` raises `NotFound` for an unknown key. | `gui/theme.py` |
| `Theme.apply(root)` chooses fonts, sets the ttk base (`clam` for tron), then `paint()`s styles and the tk option database. It runs once, in `MainWindow.__init__`. | `gui/theme.py`, `gui/main_window.py` |
| `MainWindow` builds a menu (File has "Build Safety Plan document"), a paned body (nav `Listbox`, content frame), and a status bar; screens are cached in `_screens` and created on first `show()`. | `gui/main_window.py` |
| Screens read `self.window.theme` at build time: `GridBanner` on the dashboard, `theme.ui` for the nav list, `theme.stripe()` after filling a table. | `gui/dashboard.py`, `gui/entity_screen.py`, `gui/matrix_screen.py` |
| The four screens are `dashboard`, `safety_plan`, `safety_plan_matrix`, `transfer`; generation lives inside `transfer`. | `gui/screens.py`, `tests/test_gui.py` |
| `--theme` on `asi-kletz-gui`, `--theme` on the `gui` verb, and `$ASI_KLETZ_THEME` pick a theme for one launch. Nothing persists a choice. | `gui/app.py`, `commands/gui.py` |
| `kletz.toml` holds project paths and document control (`db`, `workbook`, `out`, `doc_id`, `project`, `[[revision]]`), is git-ignored, and is read with `tomllib`; the standard library cannot write TOML. | `brain.py` |
| The event bus publishes `entity.*`; the window subscribes to `*` and refreshes the open screen. | `automation/events.py`, `gui/main_window.py` |
| Tests build real `MainWindow`s (skipped without a display), assert `tron` is the default, `clam` is in use, and `TButton` foreground equals `palette.primary`. A test asserts no module imports `asi_dewey`. | `tests/test_gui.py`, `tests/test_generate.py` |
| Kletz's `gui/theme.py` is byte-identical to Dewey's except for the environment variable name. | `diff` against `../asi_dewey` |

## 3. Design

### 3.1 The family palette (the convention)

The catalog is **8 hue families × 4 tones = 32 palettes**, plus `plain` (native look) which is
a theme but not a palette. Every palette fills the same 12 slots of `Palette`, so no screen
changes.

**Hue families**, in catalog order: Cyan, Blue, Violet, Pink, Red, Amber, Gold, Green. Each
has one accent hue that stays with it through every tone (amber carries cyan, cyan carries
orange, pink carries cyan, gold carries blue, green carries magenta, and so on), so the "live
element" colour is predictable inside a family.

**Tones**, darkest first. The names are deliberately plain and professional:

| Tone | Surfaces | Primary | Reads as |
|---|---|---|---|
| `noir` | near-black, tinted toward the hue | deep and saturated, held back from full neon | the grid at night with the lights low |
| `neon` | near-black | full neon (today's `tron` recipe) | the classic look |
| `dusk` | charcoal panels | softened neon | the same grid, less glare |
| `day` | pale tint, white fields | saturated ink | the grid in daylight; dark lines on light |

Key = `<family>-<tone>`, title = `<Family> <Tone>`: `pink-noir` is "Pink Noir", `pink-day` is
"Pink Day". The pink family is therefore the requested run from near-black to light:
`pink-noir` → `pink-neon` → `pink-dusk` → `pink-day`.

Compatibility: `tron` stays registered as an **alias** of `cyan-neon` (same class, listed once
in the picker under its new name), so `--theme tron` and `ASI_KLETZ_THEME=tron` keep working.
`plain` is unchanged.

**How the values were derived** (so the catalog can be regenerated, not so it is regenerated
at run time): each slot has a hue, a saturation, and a nominal lightness per tone; the
lightness of every *foreground* slot was then stepped away from its surface until the WCAG
contrast floor in section 6 held with a 4% margin. That is why blue and violet primaries sit
lighter than cyan or green: equal lightness is not equal luminance. The result is **data**, and
the data is the convention. Appendix A is the full table; both repos carry it byte for byte.

**Where the convention lives.** The authority is a new section "The family palette" in
[ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md) holding Appendix A and the catalog digest. Each repo has
its own `gui/palettes.py` with the same table as plain data (no imports beyond `Palette`), and
a test that hashes its catalog and compares it with the digest written in the family file. If
one tool edits its catalog its own test fails until the family file, and therefore the sibling,
is updated. Same idea as the lock: agreement through a convention and a test, never an import.
The existing share-nothing test keeps passing because `palettes.py` imports nothing from Dewey.

Catalog digest, SHA-1 of `json.dumps({key: {slot: hex}}, sort_keys=True, separators=(",", ":"))`
over the 32 palettes in Appendix A: **`befcfc0c8dca5479620badf1d23e2448db757910`**.

### 3.2 House defaults

| Tool | Default when nothing is latched | Why |
|---|---|---|
| asi_kletz | `cyan-neon` | the original look; revised 2026-10-27 from `amber-neon` after the first manual check |
| asi_dewey | `cyan-neon` | it is today's `tron`; nothing changes for a Dewey user until they pick |

`DEFAULT_THEME = "cyan-neon"` in `gui/theme.py`. Nothing changes for a Kletz user who never
picks. The owner may latch anything in either tool; the two latches are independent, which is
what keeps the tools apart once a choice is made.

### 3.3 Where the latched choice lives

A theme is a **per-person, per-machine preference**, not a project setting: it does not belong
in `kletz.toml` (project paths and document control, hand-edited, possibly in a synced folder,
and the standard library cannot write TOML back), and not in the database (the database is the
Safety Plan; a `dump` must not carry someone's colour choice).

New module `asi_kletz/prefs.py`:

- **File**: `$ASI_KLETZ_PREFS` if set (a full file path; the test suite points it at `tmp_path`);
  else `%LOCALAPPDATA%\asi\kletz\prefs.json` on Windows; else `$XDG_STATE_HOME/asi/kletz/prefs.json`;
  else `~/.local/state/asi/kletz/prefs.json`. The `asi` parent is the same base the family lock
  uses for `asi\locks`; `kletz` is Kletz's own folder, so the two tools never read each other's
  file.
- **Contents**: `{"theme": "pink-noir", "tool": "asi_kletz", "version": "0.3.0", "updated_at": "<UTC ISO 8601>"}`.
  One flat JSON object; other preferences can join later.
- **API**: `read_prefs() -> dict` (missing or unreadable file: `{}`), `write_prefs(**changes) -> Path`
  (merge, write to a temp file beside it, `os.replace`), `prefs_path() -> Path`.
- **Robustness**: a corrupt file or an unknown theme key in it is ignored with a warning in the
  status bar on the next launch, and overwritten by the next pick. The window never fails to
  open because of a preference.

**Precedence when the window opens**: `--theme` argument → `$ASI_KLETZ_THEME` → latched
preference → house default. The argument and the environment are one-off views and do **not**
write the preference; only a pick does, in the window or through the verb below. The combobox
shows whatever actually painted the window, so an override is visible, and picking anything
latches it.

### 3.4 The `theme` verb

Everything the window can do, a command can do, so the latch is a command:

```
asi-kletz theme                 # list the catalog, the latched key, the resolved key, the prefs path
asi-kletz theme pink-noir       # latch pink-noir; repaints a window open in this process
asi-kletz theme --list          # same as no key (for scripts that like explicit flags)
```

`commands/theme.py`, `ThemeCommand`, verb `theme`, arguments `key` (positional, optional) and
`list` (bool flag). With a key: `ThemeFactory.create(key)` validates (unknown → `NotFound` →
`Result.failure`, exit 1), `write_prefs(theme=key)`, then
`ctx.brain.events.publish("theme.changed", theme=key, actor=ctx.actor)`. Result data in both
forms:

```json
{"theme": "pink-noir", "latched": "pink-noir", "default": "cyan-neon", "prefs": "C:\\…\\asi\\kletz\\prefs.json",
 "themes": [{"key": "cyan-noir", "title": "Cyan Noir", "family": "cyan", "tone": "noir",
             "primary": "#12c0e2", "accent": "#ec7813"}, "…"]}
```

`theme` in Result data is the resolved key for this process (override, else latched, else
default). The verb is registered through `register_command` like every other verb and appears
in `schema` and `--help` for free. After the family lock lands, `asi-kletz theme x` while a
window is open is refused with exit 3 like any CLI call; the automation server (0.7.0) is the
way to recolour a running window, forwarding that call, and `theme.changed` is the event it raises.

### 3.5 The window: picker, live repaint, menu

**The picker.** A read-only `ttk.Combobox` at the foot of the navigation column, under a small
monospace caption `THEME`, listing the 32 titles in catalog order and then `Plain (native)`.
`state="readonly"` means it can never be blank or typed into; its value is always the title of
the theme that is painting the window. Selecting an entry calls `MainWindow.pick_theme(key)`.

**The menu.** `View > Theme` is a cascade of eight family submenus, each with four radio
items (Noir, Neon, Dusk, Day), plus `Plain (native)` at the end; the radio variable is the same
`StringVar` the combobox uses. Keyboard users and the picker stay in step because both only
ever call `pick_theme`. The File menu, including "Build Safety Plan document", is unchanged.

**`pick_theme(key)`** runs `self.run("theme", key=key)`. The verb writes the preference and
publishes `theme.changed`; the window's event handler sees that topic and calls
`set_theme(key)` instead of refreshing the screen. A failed verb leaves the window as it was and
`set_theme` is never reached; the combobox is re-synced from `self.theme` so it cannot show a
theme that is not painted.

**`set_theme(key)`** repaints by **rebuilding**, not by patching widgets:

```python
def set_theme(self, key: str) -> None:
    self._cancel_refresh()
    current = self.current_key
    self.theme = ThemeFactory.create(key)
    self.theme.apply(self)                 # fonts, ttk base, styles, option database
    for child in self.winfo_children():     # menu, paned body, rule, status bar
        child.destroy()
    self._screens.clear()
    self.current = None
    self._build_menu()
    self._build_body()                      # includes the picker, now showing `key`
    self.show(current or "dashboard")
    self.set_status(f"Theme: {self.theme.title}")
```

Why rebuild: ttk styles do change live, but tk widgets (`Listbox`, `Text`, `Canvas` banners,
`Menu`) read the option database only when created, stripes are tags set after filling, and
`GridBanner` draws with the colours it was given. Recreating the body gets every one of them
right with zero per-screen repaint code and zero new bugs in the screens. Cost: the
current screen is rebuilt and refreshed from the database, so an unsaved form edit on the
Safety Plan screen is lost and the generation log on Export / Import is cleared. `pick_theme`
asks `confirm()` first when the current screen exposes `is_dirty()` and it returns true; screens
without that method are rebuilt without asking. Key bindings live on the root (`bind_all`) and
are not rebuilt.

**`Theme.apply` becomes re-entrant** (section 3.6), which is the only precondition for calling
it a second time on the same root.

### 3.6 Theme module changes

- `Palette` and its 12 slots: unchanged.
- `TronTheme` is renamed `GridTheme`: the dark/light grid recipe with `palette` as a class
  attribute, exactly today's `paint`. `TronTheme` remains as a name for the `cyan-neon` class so
  imports keep working.
- `gui/palettes.py`: `FAMILIES`, `TONES`, and `CATALOG: dict[str, PaletteEntry]` where
  `PaletteEntry = (title, family, tone, Palette)`. Pure data; the test asserts the module has no
  `import` other than `Palette` and typing.
- `theme.py` registers one `GridTheme` subclass per catalog entry at import time
  (`type(f"{key}Theme", (GridTheme,), {"key": key, "title": title, "palette": palette})`),
  then `ThemeFactory.alias("tron", "cyan-neon")`, then `Theme` (plain).
- `ThemeFactory` gains `alias()`, `entries()` (key, title, family, tone, palette, in catalog
  order, aliases excluded), and `resolve(explicit: str | None) -> str` implementing the
  precedence of section 3.3; `default_key()` keeps its name and now means "house default".
- **Re-entrant `apply`**: on first call it records the platform ttk theme and the families and
  sizes of the named fonts (`TkDefaultFont`, `TkTextFont`, `TkMenuFont`, `TkHeadingFont`,
  `TkFixedFont`) on the root; every call starts with `root.option_clear()` and restores those
  fonts, then `plain` restores the platform ttk theme while a `GridTheme` selects `clam`. A
  `GridTheme` paints every style it ever touches, so switching between two grid palettes is
  complete; `plain` after a grid palette is complete because the platform theme carries its own
  style table and the option database was cleared.
- `day` tones use the same `paint` with a light palette; `Treeview` selected foreground, today
  the literal `"#ffffff"`, becomes `p.text` so it stays legible on the light `selection` colour.
  That is the one literal colour left in the module and it goes.

After this phase, `gui/theme.py` and `gui/palettes.py` differ from Dewey's only in the two
environment variable names and the default key, as `gui/theme.py` does today.

### 3.7 Configuration, environment, ignore files

- New environment variable `ASI_KLETZ_PREFS` (file path override), documented beside
  `ASI_KLETZ_THEME` in the README. No new key in `kletz.toml`; `kletz.example.toml` gets a
  two-line comment saying where the theme preference lives and that `--theme` is a one-off.
- `tests/conftest.py` sets `ASI_KLETZ_PREFS` to `tmp_path / "prefs.json"` and clears
  `ASI_KLETZ_THEME` in the autouse fixture, so no test reads or writes the developer's latch.
- `.gitignore`: nothing new; the preference file is never inside a repo.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Catalog | `gui/palettes.py` with the 32 entries of Appendix A; `GridTheme`, registration loop, `tron` alias, `entries()`, re-entrant `apply`, `Treeview` literal removed; default `cyan-neon`; the digest and contrast tests. | GUI tests pass with the default assertion changed to `cyan-neon`; `ThemeFactory.keys()` has 34 keys (32 + `tron` + `plain`); digest equals section 3.1; the four-screen test unchanged. |
| 2. Latch | `prefs.py`; `ThemeFactory.resolve`; `theme` verb; `app.py` and `commands/gui.py` pass the explicit key through `resolve`. | CLI tests: list, latch, unknown key; `MainWindow(seeded)` with a latched prefs file opens in that theme; `--theme` wins over the latch and does not write it. |
| 3. Picker | Combobox and caption in the nav column; `View > Theme` cascade; `pick_theme`, `set_theme`, `theme.changed` handling; dirty-form confirm. | GUI tests of section 6 pass; manual check: pick Pink Noir, quit, reopen, still Pink Noir; pick Plain, every widget native; pick Amber Day, light; Dewey open afterwards is still its own colour. |
| 4. Family | Section "The family palette" in `ASI_FUSA_TOOLS.md` with Appendix A and the digest (once, shared with the Dewey plan's phase 4); README "Themes" rewritten; CHANGELOG 0.3.0 entry naming the default change; `plan.md` sections 8 and 9; `kletz.example.toml` comment; `version.py` and `pyproject.toml` 0.3.0 if the lock has not already bumped them. | `uv run pytest` and `uv run ruff check src tests` clean; `diff` of `gui/palettes.py` against `../asi_dewey` is empty; tag left to the owner. |

## 5. Files touched

```
src/asi_kletz/gui/palettes.py              new: the 32-entry catalog, pure data
src/asi_kletz/gui/theme.py                 GridTheme, registration loop, alias, entries, resolve, re-entrant apply, default cyan-neon
src/asi_kletz/prefs.py                     new: read_prefs, write_prefs, prefs_path, ENV_PREFS
src/asi_kletz/commands/theme.py            new: ThemeCommand (verb `theme`)
src/asi_kletz/commands/__init__.py         import the new module so it registers
src/asi_kletz/commands/gui.py              help text; key passes through ThemeFactory.resolve
src/asi_kletz/gui/app.py                   help text; key passes through ThemeFactory.resolve
src/asi_kletz/gui/main_window.py           picker, View > Theme, pick_theme, set_theme, theme.changed
tests/conftest.py                          ASI_KLETZ_PREFS -> tmp_path, ASI_KLETZ_THEME cleared
tests/test_theme.py                        new: catalog, digest, contrast, prefs, verb
tests/test_gui.py                          picker and repaint cases; default assertion by key (cyan-neon)
kletz.example.toml, README.md, CHANGELOG.md, docs/plan.md
../asi_fusa_tools/ASI_FUSA_TOOLS.md                           section "The family palette" (Appendix A + digest)
pyproject.toml, src/asi_kletz/version.py   0.3.0
```

No change to `schema/`, `storage/`, `repositories/`, `services/`, `io/`, `generate/`, or any
screen module. One table, the screens as registered (four at the time), schema version 1.

## 6. Tests

**Catalog (`tests/test_theme.py`)**

- 32 entries, keys `<family>-<tone>` over exactly the 8 families and 4 tones, in catalog order;
  32 distinct `primary` values; every slot a 7-character lower-case hex string.
- Digest of the catalog equals the literal in section 3.1 (and in `ASI_FUSA_TOOLS.md`).
- Contrast floors on every palette, computed by the WCAG 2 relative-luminance formula in the
  test itself: `text/bg`, `text/field`, `primary/panel`, `primary/bg`, `on_primary/primary`,
  `on_primary/accent` ≥ 4.5; `muted/bg`, `muted/panel`, `accent/panel`, `text/selection`,
  `primary_dim/bg` ≥ 3.0. (Appendix A passes; this keeps a hand edit from quietly breaking it.)
- `palettes.py` source contains no import other than `Palette` and typing names, and the
  share-nothing test in `test_generate.py` still finds no `asi_dewey` anywhere.
- `ThemeFactory.keys()` ⊇ 32 keys + `tron` + `plain`; `create("tron")` is the `cyan-neon`
  class; `entries()` lists no alias; `create("neon-pink")` raises `NotFound`.
- `resolve(None)` with no env and no prefs is `cyan-neon`; with prefs `{"theme": "pink-noir"}`
  is `pink-noir`; with `ASI_KLETZ_THEME=green-day` is `green-day`; `resolve("plain")` is
  `plain` regardless; a prefs file naming an unknown key resolves to the default.

**Prefs**

- `read_prefs()` on a missing file is `{}`; `write_prefs(theme="red-dusk")` creates parent
  folders and the file; a second call merges; a corrupt file reads as `{}` and is replaced by
  the next write; `prefs_path()` honours `ASI_KLETZ_PREFS`.

**Verb (`tests/test_cli.py`)**

- `asi-kletz theme` exits 0 with 32 `themes`, `latched: null`, `theme: "cyan-neon"`.
- `asi-kletz theme pink-noir` exits 0, writes the prefs file, and the next `theme` reports
  `latched: "pink-noir"`; `asi-kletz theme nope` exits 1 with `ok: false`.
- The event history after a latch ends with `theme.changed` carrying `theme` and `actor`.

**Window (`tests/test_gui.py`)**

- Default: `window.theme.key == "cyan-neon"`, `clam` in use, `TButton` foreground equals
  `palette.primary` (`#1ad9ff`); `[k for k, _ in window.factory.items()] == SCREENS` still.
- Picker: `window.theme_var.get() == "Cyan Neon"`; the combobox is read-only and its values
  are the 32 titles then `Plain (native)`.
- Pick: `window.pick_theme("pink-noir")` → `window.theme.key == "pink-noir"`,
  `style.lookup("TButton", "foreground") == "#ec1380"`, the prefs file says `pink-noir`, the
  current screen key is unchanged, the status line says `Theme: Pink Noir`, the nav list box
  background equals the new `panel`.
- Pick plain then pick back: after `pick_theme("plain")` the ttk theme is the platform one and
  `option_get("background", "Listbox")` is empty; after `pick_theme("gold-day")` it is `clam`
  again and `Treeview` selected foreground equals `palette.text`.
- Latch on open: write prefs `{"theme": "violet-dusk"}`, `MainWindow(seeded)` opens in
  `violet-dusk`; `MainWindow(seeded, theme="plain")` opens plain and leaves the prefs file as
  it was.
- Unknown latched key: prefs `{"theme": "sepia"}` → opens in `cyan-neon`, status line warns.
- Event path: `seeded.execute("theme", key="green-neon", actor="agent")` on an open window
  repaints it to `green-neon` within the usual 2 s poll loop.
- Repaint keeps the Export / Import screen working: after `pick_theme("blue-dusk")` with
  `transfer` open, `screen.build_diagram(out=tmp_path)` still succeeds.

## 7. Rejected alternatives

- **One shared `theme` latch for both tools.** It would make them look alike again after any
  pick, which is the problem being solved. Each tool has its own `prefs.json`.
- **Storing the theme in `kletz.toml`.** Project setting and document control, hand-edited, no
  TOML writer in the standard library, may live in OneDrive. A `theme` key there was also
  dropped to avoid a second place to look when "my theme did not apply".
- **Storing the theme in the database.** The one table is the Safety Plan; a preference would
  need a second table and would travel in `dump` files.
- **A fifth screen for settings.** Kletz had exactly four screens by design when this was
  written; a combobox in the nav column and a menu cascade are controls, not screens, whatever
  the count.
- **Live per-widget repaint.** Every screen would need a `retheme()` for its tk widgets, tags,
  and banners; the rebuild gets the same result for free and cannot miss a widget.
- **Restarting the Tk root to repaint.** Works, but Tcl teardown on Windows is the fragile
  part of this code base (see the `gc.collect()` notes in `test_gui.py`); rebuilding children
  avoids it.
- **A shared `asi_palette` package.** Breaks the family rule that primary tools share
  conventions, not code; the digest test gives the same guarantee without an import.
- **Keeping `tron` as Kletz's default.** Rejected in the draft (a fresh Kletz and a fresh Dewey
  would be twins), then reversed on 2026-10-27 after the first manual check: the owner wants the
  original look on first run in both tools, and the independent latches keep them apart.

## 8. Open items

- Whether the status bar should carry a one-word theme badge next to `◉ ONLINE`. Cheap; decide
  after seeing the picker in the nav column.
- Whether the cover of the generated Safety Plan document should ever take colour from the
  theme. No: generated documents are controlled deliverables and stay theme-independent.
- After the automation server exists, `theme` becomes the first verb that recolours a running
  window remotely; nothing here needs to change for that.

## Appendix A. The family palette (32 entries, identical in both repos)

Slot order: `bg panel field grid stripe primary primary_dim accent text muted on_primary selection`.

| Key | Title | bg | panel | field | grid | stripe | primary | primary_dim | accent | text | muted | on_primary | selection |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `cyan-noir` | Cyan Noir | `#03090a` | `#061113` | `#0b191c` | `#14363d` | `#0d1f23` | `#12c0e2` | `#0f758a` | `#ec7813` | `#b3d4db` | `#508a95` | `#051214` | `#17464f` |
| `cyan-neon` | Cyan Neon | `#040e10` | `#081b1f` | `#0b2328` | `#114550` | `#0e2a2f` | `#1ad9ff` | `#0d88a0` | `#ff851a` | `#c9f0f7` | `#609da9` | `#03171c` | `#125a68` |
| `cyan-dusk` | Cyan Dusk | `#152123` | `#1d2d30` | `#243538` | `#365c63` | `#2a3d41` | `#55d7f1` | `#2d9db4` | `#f19e55` | `#dfeaec` | `#8babb1` | `#0a2429` | `#326b76` |
| `cyan-day` | Cyan Day | `#f2f9fb` | `#e1f1f4` | `#ffffff` | `#b3d4db` | `#edf6f7` | `#0b7286` | `#2b98ad` | `#b35909` | `#152528` | `#627e84` | `#fafcfc` | `#c2e8f0` |
| `blue-noir` | Blue Noir | `#03050a` | `#060b13` | `#0b111c` | `#14233d` | `#0d1523` | `#3277ee` | `#1657c8` | `#ecb613` | `#b3c2db` | `#506a95` | `#050b14` | `#172c4f` |
| `blue-neon` | Blue Neon | `#040910` | `#08101f` | `#0b1628` | `#112850` | `#0e1a2f` | `#2977ff` | `#1157d0` | `#ffc61a` | `#c9daf7` | `#607ba9` | `#030c1c` | `#123268` |
| `blue-dusk` | Blue Dusk | `#151a23` | `#1d2430` | `#242b38` | `#364663` | `#2a3241` | `#558ef1` | `#3066c2` | `#f1ca55` | `#dfe4ec` | `#8b99b1` | `#0a1529` | `#324b76` |
| `blue-day` | Blue Day | `#f2f5fb` | `#e1e8f4` | `#ffffff` | `#b3c2db` | `#edf1f7` | `#0f4fbd` | `#3b71ce` | `#8d6b07` | `#151c28` | `#626e84` | `#fafbfc` | `#c2d3f0` |
| `violet-noir` | Violet Noir | `#06030a` | `#0c0613` | `#130b1c` | `#27143d` | `#170d23` | `#9d53f1` | `#7d20e6` | `#ecc813` | `#c6b3db` | `#725197` | `#0c0514` | `#31174f` |
| `violet-neon` | Violet Neon | `#0a0410` | `#12081f` | `#190b28` | `#2e1150` | `#1d0e2f` | `#a14fff` | `#7e1ded` | `#ffd91a` | `#dfc9f7` | `#8260a9` | `#0e031c` | `#3a1268` |
| `violet-dusk` | Violet Dusk | `#1c1523` | `#261d30` | `#2d2438` | `#4b3663` | `#352a41` | `#ab6df3` | `#8543d0` | `#f1d755` | `#e5dfec` | `#9d8bb1` | `#180a29` | `#523276` |
| `violet-day` | Violet Day | `#f6f2fb` | `#eae1f4` | `#ffffff` | `#c6b3db` | `#f2edf7` | `#600fbd` | `#803bce` | `#836e07` | `#1e1528` | `#726284` | `#fbfafc` | `#d7c2f0` |
| `pink-noir` | Pink Noir | `#0a0306` | `#13060d` | `#1c0b13` | `#3d1429` | `#230d18` | `#ec1380` | `#b51465` | `#13daec` | `#dbb3c7` | `#955073` | `#14050d` | `#4f1733` |
| `pink-neon` | Pink Neon | `#10040a` | `#1f0813` | `#280b1a` | `#501130` | `#2f0e1f` | `#ff1a8c` | `#b80f63` | `#1aecff` | `#f7c9e0` | `#a96085` | `#1c030f` | `#68123d` |
| `pink-dusk` | Pink Dusk | `#23151c` | `#301d26` | `#38242e` | `#63364d` | `#412a36` | `#f155a3` | `#ba2e74` | `#55e4f1` | `#ecdfe6` | `#b18b9e` | `#290a1a` | `#763254` |
| `pink-day` | Pink Day | `#fbf2f6` | `#f4e1eb` | `#ffffff` | `#dbb3c7` | `#f7edf2` | `#bd0f66` | `#ce3b85` | `#077d88` | `#28151f` | `#846273` | `#fcfafb` | `#f0c2d9` |
| `red-noir` | Red Noir | `#0a0304` | `#130608` | `#1c0b0d` | `#3d141a` | `#230d10` | `#ed2641` | `#ba152b` | `#13c8ec` | `#dbb3b9` | `#95505a` | `#140507` | `#4f171e` |
| `red-neon` | Red Neon | `#100406` | `#1f080b` | `#280b0f` | `#501119` | `#2f0e12` | `#ff1a38` | `#bd0f26` | `#1ad9ff` | `#f7c9d0` | `#a9606a` | `#1c0306` | `#68121e` |
| `red-dusk` | Red Dusk | `#231517` | `#301d1f` | `#382426` | `#63363c` | `#412a2d` | `#f1556a` | `#c03043` | `#55d7f1` | `#ecdfe1` | `#b18b90` | `#290a0e` | `#76323b` |
| `red-day` | Red Day | `#fbf2f3` | `#f4e1e4` | `#ffffff` | `#dbb3b9` | `#f7edef` | `#bd0f26` | `#ce3b4f` | `#087a91` | `#281518` | `#846266` | `#fcfafa` | `#f0c2c8` |
| `amber-noir` | Amber Noir | `#0a0603` | `#130c06` | `#1c130b` | `#3d2714` | `#23170d` | `#e27312` | `#934d10` | `#13c8ec` | `#dbc6b3` | `#957050` | `#140c05` | `#4f3117` |
| `amber-neon` | Amber Neon | `#100a04` | `#1f1208` | `#28190b` | `#502e11` | `#2f1d0e` | `#ff851a` | `#a0520d` | `#1ad9ff` | `#f7dfc9` | `#a98260` | `#1c0e03` | `#683a12` |
| `amber-dusk` | Amber Dusk | `#231c15` | `#30261d` | `#382d24` | `#634b36` | `#41352a` | `#f19e55` | `#b46c2d` | `#55d7f1` | `#ece5df` | `#b19d8b` | `#29180a` | `#765232` |
| `amber-day` | Amber Day | `#fbf6f2` | `#f4eae1` | `#ffffff` | `#dbc6b3` | `#f7f2ed` | `#a0520d` | `#c87832` | `#087c94` | `#281e15` | `#847262` | `#fcfbfa` | `#f0d7c2` |
| `gold-noir` | Gold Noir | `#0a0803` | `#131106` | `#1c180b` | `#3d3514` | `#231f0d` | `#e2b912` | `#8a710f` | `#397cef` | `#dbd3b3` | `#958750` | `#141105` | `#4f4417` |
| `gold-neon` | Gold Neon | `#100e04` | `#1f1a08` | `#28220b` | `#504311` | `#2f290e` | `#ffd11a` | `#a0830d` | `#337eff` | `#f7eec9` | `#a99b60` | `#1c1703` | `#685712` |
| `gold-dusk` | Gold Dusk | `#232015` | `#302c1d` | `#383424` | `#635a36` | `#413d2a` | `#f1d255` | `#b4992d` | `#558ef1` | `#ece9df` | `#b1aa8b` | `#29230a` | `#766832` |
| `gold-day` | Gold Day | `#fbf9f2` | `#f4f0e1` | `#ffffff` | `#dbd3b3` | `#f7f5ed` | `#7f680a` | `#a58c29` | `#0b51cb` | `#282415` | `#847d62` | `#fcfcfa` | `#f0e7c2` |
| `green-noir` | Green Noir | `#030a06` | `#06130c` | `#0b1c12` | `#143d25` | `#0d2316` | `#12e269` | `#0f8a42` | `#ec13b6` | `#b3dbc4` | `#50956d` | `#05140b` | `#174f2e` |
| `green-neon` | Green Neon | `#041009` | `#081f11` | `#0b2817` | `#11502b` | `#0e2f1c` | `#1aff79` | `#0da04a` | `#ff1ac6` | `#c9f7dd` | `#60a97e` | `#031c0d` | `#126836` |
| `green-dusk` | Green Dusk | `#15231b` | `#1d3025` | `#24382c` | `#366349` | `#2a4134` | `#55f196` | `#2db465` | `#f155ca` | `#dfece4` | `#8bb19b` | `#0a2917` | `#32764f` |
| `green-day` | Green Day | `#f2fbf5` | `#e1f4e9` | `#ffffff` | `#b3dbc4` | `#edf7f1` | `#0a7b39` | `#28a15b` | `#cb0b9b` | `#15281d` | `#628470` | `#fafcfb` | `#c2f0d5` |

Aliases: `tron` → `cyan-neon`. Not a palette: `plain` (native look, unchanged).
Digest over the 32 rows: `befcfc0c8dca5479620badf1d23e2448db757910`.

*Written 2026-10-27.*
