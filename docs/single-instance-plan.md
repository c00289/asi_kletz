# ASI Kletz — Plan: one primary tool at a time (the family lock)

**Status:** Implemented 2026-10-27 (asi_kletz 0.6.0); deviations recorded in the CHANGELOG entry
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.6.0
**Re-targeted:** 2026-10-27, from 0.3.0, because 0.3.0 shipped the theme palette; 0.4.0 and 0.5.0 are window work (see the family version table).
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md), section "One primary tool at a time"
**Sister plan:** [asi_dewey/docs/single-instance-plan.md](../../asi_dewey/docs/single-instance-plan.md).
Same convention, implemented twice, never shared as code.

---

## 1. The rule

Two rules, decided by the owner on 2026-10-27, enforced in code:

1. **At most one primary tool runs at a time.** While any process of asi_kletz or asi_dewey is
   alive, no other process of either tool may start. Zero or one, never two.
2. **The same tool never runs twice.** Implied by rule 1, stated and enforced separately so a
   misconfigured family lock still protects the Safety Plan database.

"Runs" means **holds an open `Brain`**: the CLI for the length of one command, the window for the
session, a Python caller between `Brain(...)` and `close()`. The rule is about processes: one
process may open several `Brain` objects (the test suite does); the slot is released when the
last one closes.

For Kletz specifically this means the Safety Plan, the controlled document of the programme, has
exactly one writer at any moment, and the audit log can never show two front ends interleaving.

Consequences:

- `asi-kletz list` while the Kletz window is open is **refused** with exit code 3. The planned
  local automation server becomes the only way an agent drives a running window, and moves to
  the top of the "Planned" list.
- `asi-dewey …` while the Kletz window is open is refused the same way, and vice versa.
- Moving data between Kletz and Dewey happens **sequentially through files** (`dump` in one,
  `load` in the other), never by holding both open.
- The "publish the plan" routine (`document safety_plan`, `diagram`, `export excel`) runs inside
  one `Brain` when scripted, so it is one instance; from separate CLI calls it is three short
  instances in a row, each taking and releasing the slot.
- Scripts that call both tools use `--wait <seconds>` to queue for the slot instead of failing.

## 2. What exists today (verified 2026-10-27)

| Fact | Where |
|---|---|
| `Brain.__init__` opens storage; `Brain.close()` closes it; `__enter__`/`__exit__` wrap them. | `brain.py` |
| The CLI does `with Brain(ns.db) as brain:` around one command and returns 0 or 1. | `automation/cli.py` |
| The window does `with Brain(ns.db) as brain: launch(brain, …)`. | `gui/app.py` |
| Every deliberate error derives from `BrainError`; the dispatcher turns them into `Result.failure`. | `errors.py`, `commands/dispatcher.py` |
| Tests open several `Brain`s in one process at once. | `tests/test_transfer.py`, `tests/test_generate.py` |
| Tests are isolated from the developer's config and environment by an autouse fixture. | `tests/conftest.py` |
| The database has exactly one table; the window had exactly four screens when this was written (the screen-count rule was retired in 0.5.0: screens are registered in `gui/screens.py`, not counted); both are tested. | `tests/test_core.py`, `tests/test_gui.py` |

Nothing in Kletz knows that Dewey exists, and that stays true. A test greps the source tree for
`asi_dewey` and fails on a hit. The two implementations agree through the convention in
[ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md), not through an import.

## 3. Design

### 3.1 The convention (copied verbatim from ASI_FUSA_TOOLS.md; that file is the authority)

- **Lock directory**: `$ASI_PRIMARY_LOCK_DIR` if set; else `%LOCALAPPDATA%\asi\locks` on Windows;
  else `$XDG_STATE_HOME/asi/locks`; else `~/.local/state/asi/locks`. Created on demand. Never
  inside a repo, never inside OneDrive.
- **Family slot**: file `primary.lock`. Holding it means "a primary tool is running".
- **Database slot**: file `db-<sha1>.lock`, where `<sha1>` is the SHA-1 hex digest of the
  resolved absolute database path, lower-cased on Windows. Holding it means "this database is
  open". `:memory:` databases take no database slot.
- **Locking primitive**: an OS advisory lock on byte 0 of the file, non-blocking:
  `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` on Windows (the file is kept at least one byte long),
  `fcntl.flock(fd, LOCK_EX | LOCK_NB)` elsewhere. The OS releases it when the process ends, so
  a crash never leaves a stale lock.
- **Holder information**: beside each `.lock`, a `.json` with the same stem
  (`primary.json`, `db-<sha1>.json`) written best-effort by the holder after it acquires:
  `{"tool", "version", "pid", "started_at" (UTC ISO 8601), "db", "cwd", "host", "user"}`.
  It is informational; the lock is the truth. It is a separate file so a refused process can
  read it while the lock is held.
- **Order**: family slot first, then database slot. If the database slot fails, the family
  slot is released before reporting.
- **Refusal**: exit code **3** from a CLI, a JSON `Result` with `ok: false` on stdout whose
  `errors[0]` names the holder, and `data = {"slot": "family" | "database", "holder": {...} | null}`.
- **Waiting**: `--wait <seconds>` on every CLI and GUI entry point polls every 250 ms until the
  slot is free or the time is up, then refuses with exit code 3.
- **No override flag.** The only way around the rule is pointing `ASI_PRIMARY_LOCK_DIR` at a
  private directory, which is what test suites do. `ASI_PRIMARY_LOCK_DIR` is the one environment
  variable the primary tools deliberately share; it is a convention, not code.

### 3.2 New module: `asi_kletz/locks.py`

```python
class PrimaryToolBusy(BrainError):
    slot: str                 # "family" | "database"
    holder: dict | None       # parsed .json, or None if unreadable

def lock_dir() -> Path
def db_slot_name(db_path: str) -> str          # "db-<sha1>"
class SlotLock:                                # one OS lock + its info file
    def __init__(self, directory: Path, stem: str)
    def acquire(self, info: dict) -> None      # raises PrimaryToolBusy
    def release(self) -> None
    def read_holder(self) -> dict | None
class PrimaryGuard:                            # process-wide, reference counted
    def acquire(self, db_path: str, wait: float = 0.0) -> None
    def release(self, db_path: str) -> None
    def describe(self) -> dict                 # for status()
guard = PrimaryGuard()                         # the one instance per process
```

Written independently of Dewey's module from the same convention. `PrimaryGuard` keeps one
family `SlotLock` with a reference count across every open `Brain` in the process and one
database `SlotLock` per resolved path with its own count. First `Brain` acquires, last `close()`
releases. Thread-safe with a `threading.Lock`.

### 3.3 Brain

- `Brain.__init__(…, wait: float = 0.0)` calls `guard.acquire(self.db_path, wait)` **before**
  `StorageFactory.create`, so a refused process never opens the SQLite file.
- `Brain.close()` closes storage, then `guard.release(self.db_path)`. Idempotent.
- `Brain.status()` gains `"lock_dir"` and `"locks": {"family": {...}, "database": {...}}`.
- `asi_kletz.__init__` exports `PrimaryToolBusy`.

### 3.4 CLI

- Global flag `--wait SECONDS` (default 0) on `asi-kletz` and `asi-kletz-gui`.
- `main()` wraps `Brain(ns.db, wait=ns.wait)` in `try/except PrimaryToolBusy`; on refusal it
  prints `Result.failure(str(exc), data={"slot": exc.slot, "holder": exc.holder}, verb=ns.verb)`
  as JSON and returns **3**. Exit code 1 keeps meaning "the command ran and failed".
- Example message:
  `asi_dewey is running (pid 4321, since 2026-10-27T17:02:11Z, db C:\…\dewey.db); only one primary tool may run at a time. Close it, or retry with --wait.`

### 3.5 Window

- `gui/app.py` catches `PrimaryToolBusy` and shows a dialog with the holder line and **Retry** /
  **Quit**; Retry re-attempts once. With `interactive=False` it returns 3 without a dialog.
- The About box shows the lock directory. No screen is added (the window had four when this was
  written; since 0.5.0 screens are registered, not counted).

### 3.6 Scripts and agents

- A `.jsonl` script is one `Brain`, hence one instance.
- An agent that drives Kletz and Dewey runs them one after the other, with `--wait` when it
  cannot know whether a window is open. The README says so.

### 3.7 Configuration and ignore files

- No new key in `kletz.toml`; the lock directory is a family-wide environment variable so both
  tools always agree. `kletz.example.toml` gets a comment pointing at `ASI_PRIMARY_LOCK_DIR`.
- `.gitignore` gains `*.lock` and `*.lock.json` as a precaution.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Locks | `locks.py`; `Brain` acquires and releases; `status()` reports; `conftest.py` sets `ASI_PRIMARY_LOCK_DIR` to a per-test directory. | Existing suite passes unchanged (one table, the registered screens, which were four when this was written, no `asi_dewey` string); the two-process refusal test passes. |
| 2. Front ends | `--wait` on CLI and GUI; exit code 3; busy dialog; About box. | Refusal tests pass; manual check: open the window, run `asi-kletz status`, get exit 3 and the holder line. |
| 3. Interop | Simulated-sibling test (a subprocess that takes `primary.lock` by the raw convention and writes `primary.json` with `"tool": "asi_dewey"`) and crash-release test. | Both pass on Windows. |
| 4. Release | README section "One at a time", CHANGELOG `0.3.0`, `version.py` and `pyproject.toml` 0.3.0, `plan.md` sections 7 and 8, `kletz.example.toml` comment, `.gitignore`; automation server promoted to first in "Planned". | `uv run pytest` and `uv run ruff check src tests` clean; tag left to the owner. |

## 5. Files touched

```
pyproject.toml, src/asi_kletz/version.py   0.3.0
src/asi_kletz/locks.py                     new
src/asi_kletz/errors.py                    PrimaryToolBusy (or defined in locks.py and re-exported here)
src/asi_kletz/brain.py                     wait=, acquire before storage, release in close, status()
src/asi_kletz/__init__.py                  export PrimaryToolBusy
src/asi_kletz/automation/cli.py            --wait, exit 3
src/asi_kletz/gui/app.py                   --wait, busy dialog, exit 3
src/asi_kletz/gui/main_window.py           About box line
tests/conftest.py                          ASI_PRIMARY_LOCK_DIR -> tmp_path
tests/test_locks.py                        new
tests/test_cli.py, tests/test_gui.py       refusal cases
kletz.example.toml, .gitignore, README.md, CHANGELOG.md, docs/plan.md
```

No change to `schema/`, `storage/`, `repositories/`, `services/`, `commands/`, `io/`, or
`generate/`. One table, the screens as registered (four at the time), schema version 1.

## 6. Tests

- **Same process, many Brains**: several `Brain`s open at once including `:memory:`; the family
  slot is held once and released only after the last `close()`.
- **Second process, same tool**: a subprocess holding a Kletz `Brain` makes `Brain(other_db)`
  raise `PrimaryToolBusy` with `slot == "family"` and `holder["tool"] == "asi_kletz"`.
- **Simulated sibling**: a subprocess with no package import takes `primary.lock` by the raw
  convention and writes `primary.json` with `"tool": "asi_dewey"`; `Brain(...)` raises with that
  holder. This checks the convention, not Dewey's code, and keeps the no-`asi_dewey`-import rule.
- **Crash release**: kill the holder; `Brain(...)` succeeds immediately.
- **Wait**: holder exits after 0.5 s; `Brain(db, wait=5)` succeeds; `Brain(db, wait=0.2)` raises.
- **CLI**: exit 3 with a JSON `Result` carrying `data.slot` and `data.holder.pid`; `--wait`
  succeeds when the holder leaves in time.
- **GUI**: `launch` with `interactive=False` while a holder runs returns 3 and creates no window.
- **Status**: `status()["locks"]["family"]["pid"] == os.getpid()` while open.
- **Isolation**: the autouse fixture points `ASI_PRIMARY_LOCK_DIR` at `tmp_path`, so the Kletz
  and Dewey suites never collide, even when run at the same time.

## 7. Risks and decisions

| Risk | Decision |
|---|---|
| This does not fix uv or SQLite under OneDrive | Stated in section 1. Ownership, not sync. |
| Habit: CLI alongside the open window | Refused from 0.3.0; the automation server is next. |
| Agents running both tools in parallel | They serialise; briefs say "use `--wait`". |
| Lock files synced by OneDrive | Never: the lock directory is under `%LOCALAPPDATA%`. |
| Per-user, per-machine scope | Documented; sharing a SQLite file over OneDrive is already unsupported. |
| `msvcrt.locking` details | Real `os.open` descriptor; unlock before close; one-byte file; `EACCES`/`EDEADLOCK` means busy. |
| Thread safety | `PrimaryGuard` holds a `threading.Lock`. |
| A Python caller forgets `close()` | Slot held until exit, as intended; the README recommends the context manager. |
| Drift between the two implementations | Convention written once in ASI_FUSA_TOOLS.md, copied verbatim into both plans; simulated-sibling test in each suite. |

## 8. Open questions

None. Decided on 2026-10-27: the rule, the convention, exit code 3, `--wait`, no override flag.

## 9. Change log

- 2026-10-27 Draft 0.1: rule, verified starting point, convention, `locks.py`, Brain, CLI,
  window, scripts, phases, files, tests, risks.
