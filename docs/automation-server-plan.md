# ASI Kletz — Plan: the local automation server

**Status:** Implemented 2026-10-27 (asi_kletz 0.7.0); deviations recorded in the CHANGELOG entry
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.7.0 (after the family lock, 0.6.0; section 3.10 says what still works without it)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md), sections "One primary tool at a time" and
"The family palette"; phase 5 of this plan lands there
**Sister plan:** [asi_dewey/docs/automation-server-plan.md](../../asi_dewey/docs/automation-server-plan.md).
Same convention, implemented twice, never shared as code.

---

## 1. The ask

Asked by the owner on 2026-10-27:

1. **An automation server for Kletz and Dewey.** The lock plan and the theme plan both defer
   to it as "the way an agent drives a running window", and nothing describes it yet. It is
   the most-referenced missing piece.
2. **Keep the CHANGELOG's promise.** Both repos already list, under "Planned": a local
   automation server (JSON over localhost) so an agent can puppet a running session, which
   after the lock is the only way to drive a running window; `screen` puppeting commands; and
   an approval mode. This plan delivers the server and the first puppeting commands. Approval
   mode is out of scope and is the next plan (section 8).
3. **Fold in the theme plan's two open items**: a one-word theme badge in the status bar next
   to the online indicator, and the remotely recoloured window. `theme` is the first verb that
   recolours a running window remotely; `theme.changed` is already the event it raises.

Kletz's own constraints hold: **still one table, no new screen**. The server is a thread owned
by the window and two endpoints that show and list the screens already there; `SCREENS` in
`tests/test_gui.py` is not touched by this plan (five since 0.5.0's JIRA Live Data window; the
list is the design, not a cap). A test still greps the source tree for `asi_dewey` and fails on a hit.

## 2. What exists today (verified 2026-10-27)

| Fact | Where |
|---|---|
| `automation/` holds the CLI, the `EventBus`, and the script runner. Its docstring says "The local server comes in a later phase." Nothing named server or puppet exists in the package. | `automation/__init__.py` |
| `EventBus.publish(topic, **payload)` appends `{"topic", "ts", ...payload}` to a `deque(maxlen=500)` and calls the topic's handlers then the `*` handlers, synchronously, on the publishing thread. `last(n)` is the only read. There is no sequence number. Byte-identical to Dewey's. | `automation/events.py` (committed) |
| `cli.py` builds an argparse parser from the command signatures, opens `with Brain(ns.db) as brain:`, runs `brain.execute(ns.verb, args, actor=ns.actor)`, prints `result.to_json()`, and returns 0 when `ok` else 1. Global flags today: `--db`, `--actor` (default `cli`), `--compact`, `--version`. | `automation/cli.py` (uncommitted: the bare-bool-flag change) |
| `Result` has five keys, in this order: `ok`, `verb`, `data`, `errors`, `warnings`; `to_json(indent)` uses `ensure_ascii=False, default=str`. `Context(brain, actor="python")`. `Command.signature()` feeds `schema` and `--help`. The shape is the same as Dewey's and asi_hopper's, so an agent learns one dialect. | `commands/base.py` (committed) |
| `Dispatcher.execute(verb, args, actor)` never lets an exception escape; `execute_dict({"verb", "args", "actor"})` is "the wire format". | `commands/dispatcher.py` (committed) |
| `Brain.execute(verb, args=None, *, actor="python", **kwargs)`; `Brain.events` is the bus; `Brain.status()` returns `app_version`, `schema_version`, `database`, `workbook_path`, `out_dir`, `config_path`, `entities`, `commands`, `recent_audit`, `recent_events`. The lock plan adds `lock_dir` and `locks` in 0.6.0. | `brain.py` (committed) |
| Verbs today: `list`, `count`, `get`, `create`, `update`, `delete`, `schema`, `status`, `dump`, `load`, `export`, `import`, `run`, `diagram`, `document`, `gui`, `theme`. No `jira` verb and no hopper dependency until 0.5.0. | `commands/*.py`, `pyproject.toml` |
| `MainWindow(brain, factory=None, interactive=True, theme=None)` is a `tk.Tk`. `run(verb, **args)` calls `brain.execute(..., actor="gui")` and on failure `notify_error` (a dialog when interactive). `confirm()` is a dialog when interactive, `True` otherwise. `show(key)` creates a screen on first use, packs it, selects the nav row, retitles the window, calls `on_show()`. `close()` unsubscribes, cancels the pending refresh, destroys the root. | `gui/main_window.py` (uncommitted) |
| The status bar is built in `_build_body`: a `Status.TLabel` with the literal text `◉ ONLINE`, the `status_var` label, and the database path in `StatusMuted.TLabel` on the right. There is no theme badge. | `gui/main_window.py` |
| `_on_event` handles `theme.changed` by calling `set_theme(key)` when `ThemeFactory.known(key)` and `ThemeFactory.canonical(key) != self.theme.key` (no dirty check; the dirty check lives in `pick_theme`, before the verb runs); every other topic schedules `self.after(50, self._refresh_after_event)`, coalesced through `_refresh_job`. `set_theme` rebuilds menu, body and status bar and re-shows the current screen. | `gui/main_window.py` |
| No screen implements `is_dirty()` today; `pick_theme` looks it up with `getattr(self.current, "is_dirty", None)`. | `grep is_dirty src/` |
| `pick_theme(key)` asks `confirm()` when the screen is dirty, then `run("theme", key=key)`; the verb validates through `ThemeFactory.create`, writes the preference and publishes `theme.changed` with the canonical key, which repaints. | `gui/main_window.py`, `commands/theme.py` (uncommitted) |
| `gui/app.py`: `launch(brain, interactive=True, theme=None)` builds the window and calls `mainloop()`; `main()` parses `--db`, `--theme`, `--version`, resolves the theme, opens `with Brain(ns.db)`. The `gui` verb has one argument, `theme`. | `gui/app.py`, `commands/gui.py` (uncommitted) |
| `prefs_path()` is `$ASI_KLETZ_PREFS`, else `%LOCALAPPDATA%\asi\kletz\prefs.json`, else `$XDG_STATE_HOME/asi/kletz/prefs.json`, else `~/.local/state/asi/kletz/prefs.json`; `prefs_problem()` explains a corrupt file; writes go to a `.<pid>.tmp` beside it and `os.replace`. | `prefs.py` (uncommitted, new in 0.3.0) |
| Screens, fixed by `build_default_screens`, in nav order: `dashboard`, `safety_plan`, `safety_plan_matrix`, `transfer`. `ScreenFactory.items()` gives `(key, title)` pairs; `MainWindow.current_key` is the open one. `test_exactly_four_screens` asserts the list. | `gui/screens.py` (committed), `tests/test_gui.py` |
| The lock plan (0.6.0): lock dir `%LOCALAPPDATA%\asi\locks`, `primary.json` holder with `tool`, `version`, `pid`, `started_at`, `db`, `cwd`, `host`, `user`; CLI refusal exit code 3 with `data = {"slot", "holder"}`; `--wait <seconds>`; no override flag; `PrimaryToolBusy(BrainError)` raised by `Brain.__init__`. | `docs/single-instance-plan.md`, `ASI_FUSA_TOOLS.md` |
| `docs/plan.md` section 7 "Automation" lists the in-process API, the CLI, script files, the event bus, the family lock, and then: "Later: local automation server (after 0.3.0 the only way to drive a running window), approval mode, GUI puppeting commands." Section 3's front-end box says "(automation server later)". There is no sketch of endpoints; this plan is the first. | `docs/plan.md` |
| `tests/test_gui.py` builds real `MainWindow(seeded, interactive=False)` windows (skipped without a display), polls with `window.update()` for up to 2 s, and tears down with `close()`, `del`, `gc.collect()`. `tests/conftest.py` isolates config, `ASI_KLETZ_PREFS` and `ASI_KLETZ_THEME`; `PLAN = "safety_plan_row"`. | `tests/test_gui.py`, `tests/conftest.py` (uncommitted) |
| Tests read events by `events.last(1)[0]["topic"]` and by named keys, never by whole-dict equality, so an added `seq` key breaks nothing. | `tests/test_cli.py`, `tests/test_gui.py` |

Working-tree note: `main_window.py`, `app.py`, `cli.py`, `commands/gui.py`, `commands/theme.py`,
`prefs.py`, `gui/theme.py`, `gui/palettes.py` and the three test files above are the uncommitted
0.3.0 work; `events.py`, `base.py`, `dispatcher.py`, `brain.py`, `screens.py` are at HEAD.

## 3. Design

### 3.1 The convention (what both tools agree on; the family document is the authority)

- **Transport**: HTTP/1.1, JSON bodies and JSON `Result` answers, bound to `127.0.0.1` on an
  ephemeral port, served by the standard library's `http.server.ThreadingHTTPServer` on a daemon
  thread owned by the window. No third-party dependency. No TLS (loopback only).
- **Session file**: `%LOCALAPPDATA%\asi\kletz\session.json`, the same folder as `prefs.json`
  (XDG state folder elsewhere); override `$ASI_KLETZ_SESSION` (a full file path; the test suite
  points it at `tmp_path`). Written after the server has bound, removed in `close()`, ignored by
  every reader when its `pid` is not alive.
- **Authentication**: every request carries `Authorization: Bearer <token>`; the token is in the
  session file. Wrong or missing token: 401 with a `Result` whose `errors[0]` is `bad token`.
- **Endpoints** (section 3.4): `GET /status`, `POST /execute`, `GET /screens`, `POST /screen`,
  `GET /events?since=<n>`, `POST /quit`.
- **Wire format**: `/execute` takes `{"verb", "args", "actor"}` (the dispatcher's `execute_dict`
  payload) and answers the command's `Result` JSON exactly as the CLI prints it with `--compact`.
- **Exit codes and forwarding** (section 3.6): the CLI forwards to the server only when the lock
  refusal names a window of the **same tool** whose session is alive; exit 0 or 1 by the forwarded
  `Result`; a window of the other tool is still exit 3; `--no-forward` disables forwarding.
- **Off switch**: `ASI_KLETZ_AUTOMATION=off`, or `--no-server` for one launch.

### 3.2 The session file: `automation/session.py`

```python
ENV_SESSION = "ASI_KLETZ_SESSION"
TOOL = "asi_kletz"

def session_path() -> Path                      # $ASI_KLETZ_SESSION, else beside prefs.json
def write_session(port: int, token: str, db: str, started_at: str) -> Path   # atomic, 0o600 on POSIX
def read_session() -> dict | None               # None when missing, corrupt, wrong tool, or pid dead
def clear_session(pid: int = os.getpid()) -> None   # removes the file only if it names this pid
def pid_alive(pid: int) -> bool                 # os.kill(pid, 0) on POSIX; OpenProcess + GetExitCodeProcess
                                                #   == STILL_ACTIVE through ctypes on Windows
def probe(session: dict, timeout: float = 1.0) -> dict | None   # GET /status; None when unreachable
                                                #   or when the answering pid differs from the file
```

Contents, one flat JSON object:

```json
{"tool": "asi_kletz", "version": "0.7.0", "pid": 18432, "started_at": "2026-10-27T17:02:11+00:00",
 "host": "127.0.0.1", "port": 51234, "address": "http://127.0.0.1:51234",
 "token": "3f9c…32 hex…", "db": "C:\\…\\kletz.db"}
```

`pid` and `started_at` are the same values the lock holder writes to `primary.json`, so the two
files can be matched. `read_session()` returns `None` unless `tool == "asi_kletz"` and the pid is
alive; a stale file from a crash is therefore harmless and is overwritten by the next window.
`probe()` is the liveness check readers use before trusting the file: it must answer and its
`pid` must equal the file's. Written independently of Dewey's module from the same convention.

### 3.3 The server: `automation/server.py`

```python
class AutomationServer:
    def __init__(self, window: MainWindow, host: str = "127.0.0.1", port: int = 0) -> None
    token: str                 # secrets.token_hex(16), per launch
    port: int                  # the bound ephemeral port
    started_at: str            # UTC ISO 8601
    requests: int              # served so far, for /status
    def start(self) -> None    # bind, start the daemon thread, start the main-thread pump
    def stop(self) -> None     # Tk thread only: cancel the pump, httpd.shutdown(), server_close()
    def on_main(self, fn: Callable[[], T], timeout: float = 60.0) -> T   # server thread -> Tk thread
```

**The main-thread handshake.** The HTTP handler runs on a server thread and may not touch a Tk
widget or the window's state. Every job is queued; the window drains the queue on its own thread
every 50 ms; the handler waits on a `threading.Event` with a timeout:

```python
class _Job:
    def __init__(self, fn):
        self.fn, self.done, self.result, self.error = fn, threading.Event(), None, None

def on_main(self, fn, timeout=60.0):            # called on the server thread
    job = _Job(fn)
    self._jobs.put(job)                         # queue.SimpleQueue, thread-safe
    if not job.done.wait(timeout):
        raise TimeoutError(f"the window did not answer within {timeout:.0f} s")
    if job.error is not None:
        raise job.error
    return job.result

def _pump(self):                                # Tk thread, rescheduled with after(50)
    while True:
        try:
            job = self._jobs.get_nowait()
        except queue.Empty:
            break
        try:
            job.result = job.fn()
        except Exception as exc:                # the handler turns it into a Result.failure
            job.error = exc
        job.done.set()
    self._pump_job = self.window.after(50, self._pump)
```

Only `queue` and `threading.Event` cross the thread boundary; the server thread never calls
`after`, never reads `window.current`, never touches `Brain` (SQLite connections are per thread;
all database work stays on the thread that opened it). A job that times out is not cancelled:
it still runs when the window gets to it, and its `Result` is discarded; the handler answers
504. `on_main` is the only door, and the whole design hangs on it, which is why the test in
section 6 asserts `threading.current_thread() is threading.main_thread()` inside a job.

**Handler.** One `BaseHTTPRequestHandler` subclass with `do_GET` and `do_POST`:

1. Refuse any request carrying an `Origin` header with 403 (a browser page never gets in, token
   or not). Refuse a missing or wrong bearer token with 401 before reading the body.
2. Route by path; 404 for anything else; 405 for the wrong method; 400 for a body that is not a
   JSON object; 413 for a body over 1 MiB.
3. Produce a `Result` and answer 200 with `Content-Type: application/json; charset=utf-8` and
   `result.to_json(indent=None)`. The HTTP status is about transport, not about the command:
   a failed command is 200 with `ok: false`, the same as the CLI printing it and exiting 1.
4. 504 with a `Result.failure` when `on_main` times out; 500 with a `Result.failure` naming the
   exception type if a job raises (the dispatcher already never raises for a command, so this
   covers `window.show` of a broken screen and little else).

`log_message` is routed to `logging.getLogger("asi_kletz.automation.server")` at DEBUG so the
console stays quiet.

**What the server may call on the window.** `brain.execute`, `show`, `factory.items()`,
`current_key`, `theme`, `remote_guard` (section 3.7), and `close` through `after`. Never `run`,
`pick_theme`, `notify_error`, `confirm`, `about`, `export_workbook` or `build_safety_plan`: those
may open a dialog, and a dialog would block the Tk thread with a request waiting on it. This list
is the invariant that keeps the server from ever blocking. (`document safety_plan` through
`/execute` is fine: it is a command, and runs without a dialog.)

### 3.4 Endpoints

| Method and path | Body | `Result.data` |
|---|---|---|
| `GET /status` | none | `{"tool": "asi_kletz", "version", "pid", "db", "screen": "<current key>", "theme": {"key", "title"}, "started_at", "uptime_s", "port", "requests", "events_seq": <latest seq>, "lock": <brain.status()["locks"] or null before 0.6.0>}` |
| `POST /execute` | `{"verb": "list", "args": {"entity": "safety_plan_row"}, "actor": "agent"}` | whatever the command returns; the whole `Result` is the command's, `verb` included |
| `GET /screens` | none | `{"screens": [{"key": "dashboard", "title": "Dashboard", "current": true}, …]}` in nav order |
| `POST /screen` | `{"show": "safety_plan_matrix"}` | `{"screen": "safety_plan_matrix", "title": "Safety Plan Matrix"}`; unknown key: `ok: false`, the `NotFound` message from `ScreenFactory.create` |
| `GET /events?since=<n>&limit=<m>` | none | `{"since": n, "seq": <latest>, "events": [...]}`; events after sequence `n` (default 0), at most `m` (default 200); a `warnings` entry when history no longer reaches back to `n` |
| `POST /quit` | none | `{"quit": true}`; the window closes 100 ms after the answer is sent |

`/execute` runs `window.brain.execute(verb, args, actor=actor)` on the Tk thread with the actor
the agent sent (default `agent`, never `gui`); the audit log and the events record it as such.
Because the window's own `_on_event` is subscribed to `*`, the open screen refreshes 50 ms later
exactly as it does for the in-process `seeded.execute(...)` case the GUI tests already cover.
`/execute` is the whole command vocabulary, `gui` excepted: the server refuses `{"verb": "gui"}`
with `ok: false` ("the window is already open") rather than nest a second `mainloop`. The
"publish the plan" routine (`document safety_plan`, `diagram`, `export excel`) therefore runs
against an open window as three `/execute` calls, or as one forwarded `run steps.jsonl`.

`/events` needs a sequence number, which the bus does not have. `EventBus.publish` gains
`"seq": <int>` (one counter per bus, starting at 1) on every event, `EventBus.seq` (the latest),
and `EventBus.since(n, limit=200) -> list[dict]`. `last(n)` is unchanged. Polling is the
protocol: an agent remembers the `seq` it has seen and asks for what follows; nothing is pushed.

### 3.5 The window

- `MainWindow.__init__(…, server: bool = True)`. After `_build_body`, `_bind_keys` and the event
  subscription, when `server` is true and `ASI_KLETZ_AUTOMATION` is not `off`, the window
  creates `AutomationServer(self)`, starts it, writes the session file, and sets the online
  indicator. Any failure to bind or to write the file is a status-bar warning, never a failed
  launch; the window then runs without a server exactly as `--no-server` would.
- `close()` stops the server and clears the session file **before** `destroy()`, in that order,
  so a request in flight gets its 504 rather than a crash, and so the CLI stops forwarding the
  moment the window is gone.
- The status bar: `self.online_var` replaces the literal; it reads `◉ ONLINE :51234` while the
  server is up and `◉ ONLINE` otherwise. Between it and the status text a new label,
  `self.badge_var`, the **theme badge**: the theme title upper-cased with any parenthetical
  dropped (`AMBER NEON`, `PINK DAY`, `PLAIN`), in `self.theme.mono`, style `StatusMuted.TLabel`.
  Both labels are built in `_build_body` from `self.theme` and `self.server`, so the rebuild in
  `set_theme` is what updates the badge; `set_theme` also re-sets `online_var` because the
  server survives the rebuild (it is owned by the window, not by any widget).
- `set_theme` and the server: the pump is an `after` job on the root, not on a child, so
  destroying the children in `set_theme` leaves it running; `_cancel_refresh` keeps its current
  meaning and does not touch the pump.
- The About box gains the session address.
- No new screen and no new menu. The View > Automation submenu is an open item (section 8).

### 3.6 The CLI: forwarding and the `session` verb

`automation/cli.py`, in `main()`:

```python
try:
    with Brain(ns.db, wait=ns.wait) as brain:            # 0.6.0 signature
        result = brain.execute(ns.verb, args, actor=ns.actor)
except PrimaryToolBusy as exc:
    session = None if ns.no_forward else read_session()
    holder = exc.holder or {}
    if session and holder.get("tool") == TOOL and holder.get("pid") == session["pid"] and probe(session):
        result = forward(session, ns.verb, args, actor=ns.actor)   # POST /execute, 60 s timeout
    else:
        refusal = Result.failure(str(exc) + hint(session, holder), verb=ns.verb,
                                 data={"slot": exc.slot, "holder": exc.holder})
        print(refusal.to_json(...)); return 3
print(result.to_json(...)); return 0 if result.ok else 1
```

Rules, stated plainly:

- **Forward only to a window of the same tool.** The holder must say `asi_kletz` and its pid must
  be the session file's pid. A Dewey window is exit 3 as the family lock says; forwarding across
  tools would let one tool drive the other's window, which is the one thing the family forbids.
- **Forward only to a live session.** `read_session()` already drops a dead pid; `probe()` then
  requires `GET /status` to answer with that pid within 1 s. A window started with `--no-server`
  (no file) or one whose server failed to bind is exit 3 with the hint
  `no automation session; the window may have been started with --no-server or
  ASI_KLETZ_AUTOMATION=off`.
- **The forwarded `Result` is printed untouched** and the exit code is 0 or 1 by its `ok`, as if
  the command had run locally. Nothing marks it as forwarded: an agent learns one dialect. `--actor`
  travels with the request, so the audit log in the window says `cli` (or whatever was given).
- **`--no-forward`** (new global flag, default off) turns the branch off; with it the behaviour is
  exactly the lock plan's: exit 3, and `--wait` queues for the slot. Without it, a live session is
  used at once and `--wait` is not consulted (there is nothing to wait for).
- **A transport failure while forwarding** (connection refused, timeout) is exit 3 with the
  lock refusal plus `the automation session at http://127.0.0.1:51234 did not answer`: the
  session is treated as dead. It is never exit 1, because the command did not run.
- `--db` on a forwarded call is ignored with a warning printed to stderr when it names a
  different database from the session's: the window has one database and the agent asked for
  another; the lock would have refused that too.

**The `session` verb.** `commands/session.py`, `SessionCommand`, verb `session`, one flag
argument `quit` (bool). It is the one verb the CLI runs **without opening a `Brain`**, because it
touches no database and must work while a window holds the lock:

```
asi-kletz session           # the session file, whether the pid is alive, whether /status answers
asi-kletz session --quit    # POST /quit to the live session, then wait up to 5 s for the file to go
```

`main()` short-circuits `session` before `Brain(...)`: it calls `SessionCommand.report(quit=…)`
directly and prints its `Result`. Result data:

```json
{"path": "C:\\…\\asi\\kletz\\session.json", "present": true, "alive": true, "reachable": true,
 "session": {"pid": 18432, "port": 51234, "address": "http://127.0.0.1:51234", "started_at": "…", "db": "…"},
 "status": {…the /status data…}, "quit": false}
```

The token is **not** in the printed data (it is in the file for anyone who can read the file;
printing it to a console or a log is a leak for nothing). `present: false` is `ok: true` with
`alive: false, reachable: false`: a missing session is a fact, not an error. `--quit` with no live
session is `ok: false`. The verb is registered like every other verb, so it is in `schema`,
`--help`, and callable in-process (from Python or through `/execute`, where it reports the
window's own session).

### 3.7 Remote `theme`: the first verb that recolours a running window

Nothing new is needed for the recolour itself: `/execute {"verb": "theme", "args": {"key":
"pink-noir"}, "actor": "agent"}` runs the verb on the Tk thread, the verb publishes
`theme.changed`, `_on_event` calls `set_theme`, and the window is repainted before the `Result`
goes back. This plan proves it with a test and documents it as the first remote verb.

**Dirty screens.** `pick_theme` asks `confirm()` before dropping unsaved edits; the server may
never open a dialog. Decision: **remote picks never prompt**. They apply when the open screen is
clean, and are refused when it is dirty:

- `MainWindow.remote_guard(verb, args) -> Result | None`, called by the `/execute` handler on the
  Tk thread before `brain.execute`. Today it knows one rule: when `verb == "theme"` and `args`
  carry a key and `self.current` exposes `is_dirty()` returning true, it returns
  `Result.failure(f"theme change refused: the {self.current_key} screen has unsaved edits",
  verb="theme")` with `warnings = ["save or discard the edits, then retry"]`. The verb does not
  run, so the preference is not latched either: the window and the latch stay in step.
- Everything else passes (`None`). The hook is the single place for future rules of the same
  kind ("this remote verb would destroy what the engineer is typing") and is not a permission
  system: approval mode, when it comes, is a different thing and gets its own plan.
- Today no screen implements `is_dirty()`, so in practice remote `theme` always applies until a
  screen gains the method; the test monkeypatches one in, as the theme tests already do.

### 3.8 Puppeting: `/screens` and `/screen`

`GET /screens` lists `window.factory.items()` with `current` set on `window.current_key`.
`POST /screen {"show": key}` calls `window.show(key)` on the Tk thread and answers with the key
and title; the nav row, the title bar and `on_show()` behave exactly as a click does. That is
the whole puppeting surface for 0.7.0: show a screen, see which is shown. The `fill`, `submit`
and `cancel` puppeting that the CHANGELOG's "screen puppeting commands" line could be read to
include is not in this plan (section 8).

Both are endpoints rather than verbs because they are not commands on the database: a `screen`
verb in the CLI would have nothing to act on without a window, and the family rule "everything
the window can do, a command can do" is about data, which `/execute` already covers.

### 3.9 Security

- **Loopback and token.** The socket is bound to `127.0.0.1`, so a request from another machine
  is impossible by construction. The token is 128 bits from `secrets`, new on every launch,
  stored in a file under the user's profile (`%LOCALAPPDATA%` is readable only by that Windows
  account; on POSIX the file is written `0o600`), so another local process **of a different user**
  cannot read it and therefore cannot drive the window. A process of the **same user** is trusted:
  it can already open the database file directly, so the token adds nothing against it and is not
  meant to. What the token protects against is a different local account, and the stray web page
  or local service that guesses the port.
- **No browser.** Requests with an `Origin` header are refused (403), so a web page open in the
  engineer's browser cannot reach the server even with the token.
- **No remote code.** The server executes registered verbs through the dispatcher and shows
  registered screens; there is no eval, no file path outside what the verbs already accept.
- **Audit.** Every forwarded or remote command carries its actor into the audit log, which for
  the Safety Plan, the controlled document of the programme, is the point; `/status` reports
  `requests`; the events history shows what changed.
- Not covered, and said so in the README: a malicious process of the same user, and a shared
  machine where accounts share `%LOCALAPPDATA%` (they do not, on Windows).

### 3.10 Configuration, environment, dependencies

- `ASI_KLETZ_AUTOMATION=off` (new; any other value, or unset, means on). `--no-server` on
  `asi-kletz-gui` and as a bool flag on the `gui` verb, for one launch. Both leave the window
  fully usable; the CLI then gets exit 3 with the hint of section 3.6.
- `ASI_KLETZ_SESSION` (new; file path override). `tests/conftest.py` sets it to
  `tmp_path / "session.json"` and clears `ASI_KLETZ_AUTOMATION`, so no test reads or writes a
  real session and a developer's open window never receives test traffic.
- No new key in `kletz.toml`; the server is per launch, not per project. `kletz.example.toml`
  gets a two-line comment naming the session file and the off switch.
- No new dependency: `http.server`, `urllib.request`, `secrets`, `threading`, `queue`, `ctypes`.
- **Assumes 0.6.0 (the family lock) has landed.** If it has not: the server, the session file,
  the badge, the puppeting endpoints and `session` all work and are tested on their own; the
  forwarding branch in `main()` is simply unreachable, because without the lock the CLI opens
  its own `Brain` beside the window as it does today (and the window does not refresh, which is
  the problem the lock and this plan together remove). Phase 2's forwarding tests
  `importorskip` the lock module and are skipped until it exists.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Session + server | `automation/session.py`; `automation/server.py` with the handshake, the handler, `/status`, `/execute`, `/events`, `/quit`; `EventBus.seq`/`since`; `MainWindow` starts and stops it, `server=` argument, `--no-server`, `ASI_KLETZ_AUTOMATION`; online indicator shows the port; `conftest.py` isolation. | `tests/test_server.py` passes: status, read verb, write verb refreshes the open screen, events since, bad token 401, Origin 403, timeout 504, main-thread assertion, `--no-server` writes no file, `close` removes it. Existing suite unchanged (one table, `SCREENS` unchanged, no `asi_dewey` string). |
| 2. CLI | `--no-forward`; the forwarding branch; `forward()` and `probe()` in `session.py`; the `session` verb and its short-circuit; hints. | `tests/test_session.py` and the `test_cli.py` cases pass: forward on same-tool refusal, exit 3 on other-tool refusal, exit 3 on dead pid, exit 3 with `--no-forward`, `session` and `session --quit`; skipped cleanly when 0.6.0 is absent. |
| 3. Theme badge, remote recolour, puppeting | The badge in the status bar; `remote_guard`; `/screens` and `/screen`; About box line. | GUI tests: badge text follows `set_theme`; remote `theme` via POST changes `window.theme.key` and the badge; dirty screen refuses without a dialog; `/screen` shows a screen and `/screens` marks it. Manual check: open the window, `asi-kletz theme pink-day` from another console, the window turns light and the badge says `PINK DAY`. |
| 4. Docs | README section "Automation" (the server, the session file, forwarding, `session`, the off switch, security); CHANGELOG 0.7.0; `docs/plan.md` sections 3 (front-end box), 7 and 8 (row 0.7.0) and 9; `kletz.example.toml` comment; `version.py` and `pyproject.toml` 0.7.0. | `uv run pytest` and `uv run ruff check src tests` clean; tag left to the owner. |
| 5. Family | Version table row 0.7.0; plans table rows for both automation plans; a new section "The automation session" with the convention table of section 3.1 (session file, endpoints, exit codes, forwarding rule, off switch); in `asi_fusa_tools/ASI_FUSA_TOOLS.md`. | The sister plan's phase 5 finds the section already there and only checks it; `diff` of the two plans shows only names and repo facts. |

## 5. Files touched

```
src/asi_kletz/automation/session.py        new: session_path, write/read/clear_session, pid_alive, probe, forward, ENV_SESSION
src/asi_kletz/automation/server.py         new: AutomationServer, the handshake, the handler, the six endpoints
src/asi_kletz/automation/events.py         seq on every event, EventBus.seq, since(n, limit)
src/asi_kletz/automation/cli.py            --no-forward, the forwarding branch, the session short-circuit, hints
src/asi_kletz/automation/__init__.py       docstring: the server is here now
src/asi_kletz/commands/session.py          new: SessionCommand (verb `session`, flag --quit)
src/asi_kletz/commands/__init__.py         import the new module so it registers
src/asi_kletz/commands/gui.py              --no-server flag passed to launch
src/asi_kletz/gui/app.py                   --no-server; launch(..., server=)
src/asi_kletz/gui/main_window.py           server start/stop, session file, online_var, badge_var, remote_guard, About line
tests/conftest.py                          ASI_KLETZ_SESSION -> tmp_path, ASI_KLETZ_AUTOMATION cleared
tests/test_server.py                       new: the server against a real MainWindow over urllib
tests/test_session.py                      new: session file, verb, forwarding with a monkeypatched refusal
tests/test_cli.py, tests/test_gui.py       --no-forward and session cases; badge and indicator cases
kletz.example.toml, README.md, CHANGELOG.md, docs/plan.md
../asi_fusa_tools/ASI_FUSA_TOOLS.md       version table, plans table, "The automation session"
pyproject.toml, src/asi_kletz/version.py   0.7.0
```

No change to `schema/`, `storage/`, `repositories/`, `services/`, `io/`, `generate/`,
`commands/base.py`, `commands/dispatcher.py`, `brain.py`, `prefs.py`, `gui/theme.py`,
`gui/palettes.py`, `gui/screens.py`, or any screen module. No new screen; one table; schema
version 1.

## 6. Tests

**Server (`tests/test_server.py`)**, real `MainWindow(seeded, interactive=False)` as in
`test_gui.py`, requests through `urllib.request` with the bearer token read from
`session_path()`, polling `window.update()` for answers because the Tk thread is the test thread:

- `GET /status`: 200, `ok`, `data.tool == "asi_kletz"`, `data.pid == os.getpid()`,
  `data.screen == "dashboard"`, `data.theme.key == "cyan-neon"`, `data.port` equals the session
  file's, `data.events_seq` is an int.
- Read verb: `POST /execute {"verb": "count", "args": {"entity": "safety_plan_row"}, "actor":
  "agent"}` answers `{"ok": true, "verb": "count", "data": {"count": 3}, "errors": [],
  "warnings": []}`, byte-equal to `seeded.execute("count", entity=PLAN).to_json(indent=None)`.
- Write verb refreshes the open screen: show `safety_plan`, POST an `update` setting row 3 to
  `Done`, the tree shows `Done` for that row within 2 s; the audit tail's actor is `agent`;
  `events.last(1)[0]["topic"]` is `entity.updated` and carries `seq`.
- Main thread: a job posted through `on_main` records `threading.current_thread()` and it is the
  main thread; the handler thread is not.
- `GET /events?since=0` lists everything with increasing `seq`; `since=<latest>` is empty;
  `since=<latest-1>` has one; `limit=1` caps; a `since` older than the history start yields a
  warning.
- `POST /screen {"show": "safety_plan_matrix"}`: `window.current_key == "safety_plan_matrix"`;
  `GET /screens` marks it `current` and lists exactly `SCREENS` in order; an unknown key is 200
  with `ok: false` and `unknown screen` in `errors[0]`.
- Remote recolour: `POST /execute {"verb": "theme", "args": {"key": "pink-noir"}}` →
  `window.theme.key == "pink-noir"`, `window.badge_var.get() == "PINK NOIR"`,
  `window.online_var.get()` still ends with the port, the prefs file says `pink-noir`,
  `window.nav.size()` is still `len(SCREENS)`.
- Dirty refusal: monkeypatch `is_dirty` to true on the open screen and `confirm` to a function
  that fails the test if called; POST `theme green-day` → `ok: false`, `refused` in `errors[0]`,
  `window.theme.key` unchanged, prefs unchanged, no dialog.
- `{"verb": "gui"}` is refused with `ok: false`.
- `{"verb": "document", "args": {"name": "safety_plan", "out": "<tmp>"}}` through the server
  builds the document on the Tk thread and the transfer screen's log, when open, shows it: the
  publish routine works against an open window.
- Bad token → 401 with `errors[0] == "bad token"`; no token → 401; an `Origin` header → 403;
  `GET /execute` → 405; `POST /execute` with `[1, 2]` → 400; `/nope` → 404.
- Timeout: monkeypatch the handler's timeout to 0.2 s and post a job while the test does not
  call `window.update()` → 504 with `ok: false`; after `update()` the job still ran.
- `POST /quit` answers `{"quit": true}`; within 2 s of updates the window is destroyed and
  `session_path()` is gone.
- `MainWindow(seeded, interactive=False, server=False)` and `ASI_KLETZ_AUTOMATION=off`: no
  server attribute, no session file, `online_var` is exactly `◉ ONLINE`.
- `close()` removes the session file and the port refuses connections afterwards.

**Session and forwarding (`tests/test_session.py`)**

- `read_session()` is `None` for a missing file, a corrupt file, `tool: "asi_dewey"` (the string
  appears only in this test, as the lock plan's simulated-sibling test already allows), and a
  dead pid (a pid taken from a finished `subprocess`); it is the dict for a live file.
- `write_session` then `clear_session(other_pid)` leaves the file; `clear_session()` removes it.
- `pid_alive(os.getpid())` is true; for the finished subprocess it is false.
- Forwarding (`pytest.importorskip("asi_kletz.locks")`): a real window with its server is open;
  monkeypatch `asi_kletz.brain.Brain` so construction raises `PrimaryToolBusy(slot="family",
  holder={"tool": "asi_kletz", "pid": os.getpid()})`; `main(["count", "safety_plan_row"])`
  prints the forwarded `Result` and returns 0; the window's audit tail actor is `cli`;
  `main(["--actor", "robot", "get", "safety_plan_row", "42"])` returns 1 with `ok: false`.
- Holder naming the sister tool → 3, `data.holder.tool` is that name, no request reaches the
  server (`requests` unchanged).
- Session file with a wrong pid → 3 with the `no automation session` hint; `--no-forward` → 3
  even with a live session; server stopped but file left in place (simulated) → 3 with
  `did not answer`.
- `--db other.db` on a forwarded call prints a warning on stderr and still forwards.

**Verb (`tests/test_cli.py`)**

- `asi-kletz session` with no window: exit 0, `present: false`, `alive: false`,
  `reachable: false`; no database is created (the verb opens no `Brain`).
- With a window open in the test process: `present`, `alive`, `reachable` all true, `session.pid`
  is `os.getpid()`, `status.screen` is the open screen, and `"token"` is not in the output.
- `session --quit` closes the window and returns 0; a second `session --quit` is exit 1.
- `session` appears in `schema` and in the parser (`test_parser_covers_every_verb`).

**Window (`tests/test_gui.py`)**

- `window.badge_var.get() == "CYAN NEON"` on open; `"PLAIN"` after `pick_theme("plain")`;
  `"GOLD DAY"` after `pick_theme("gold-day")`; the badge label's font is the mono font and its
  style is `StatusMuted.TLabel`; the status bar packs online indicator, badge, status text in
  that order.
- `window.online_var.get() == f"◉ ONLINE :{window.server.port}"` and the port is in the session
  file; after `set_theme` the same server object is still `window.server` and the pump is alive
  (a job posted after the rebuild is answered).
- `test_exactly_four_screens` (or its five-screen successor) is unchanged and still passes with
  the server running.

## 7. Rejected alternatives

- **WebSockets or asyncio.** Tk owns the only event loop in the process and the standard library
  has no WebSocket server; polling `/events` with a sequence number gives an agent the same
  information with no second loop and no dependency.
- **Named pipes or a Unix socket.** Not cross-platform in one code path, and harder for an agent
  whose tools speak HTTP; loopback HTTP with a token is as private and far easier to call.
- **A server in the CLI process instead of the window.** The window holds the lock and the Tk
  thread; only it can show a screen or repaint, and only its `Brain` may touch the database while
  the lock is held.
- **Forwarding across tools.** `asi-dewey …` reaching a Kletz window would make one tool a
  client of the other; the family lock exists to keep them apart. Exit 3, as the lock says.
- **Running commands off the Tk thread.** SQLite connections are per thread, the window reads
  `Brain` state during refresh, and `theme.changed` rebuilds widgets; one thread for all of it,
  through `on_main`, is the only arrangement with no races.
- **Prompting on a remote `theme` when the screen is dirty.** A dialog on the Tk thread blocks
  every request behind it; refusing with a `Result` is honest and instant, and the agent can
  retry after the engineer saves.
- **A `screen` CLI verb for puppeting.** Without a window there is nothing to show; `/screen` and
  `/screens` are the honest shape, and the data vocabulary stays in `/execute`.
- **An "Automation" screen.** Kletz adds screens only when the owner asks for one; the
  status-bar port and `session` say what a screen would say.
- **Printing the token from `session`.** It would end up in logs and transcripts; the file is
  the one place it lives.

## 8. Open items

- **Approval mode** is the next plan: a human confirms agent commands before they commit.
  It will sit behind `remote_guard` (which is a safety hook, not a permission system) and needs
  a queue, a visible list in the window, and a `pending` state in the `Result`; none of that
  belongs here.
- `fill`, `submit`, `cancel` puppeting of the Safety Plan form. Needs a per-screen contract for
  widgets; after approval mode, if still wanted.
- A `View > Automation` submenu with "Copy session address" and "Show events…". The status-bar
  port, `session`, and `/events` cover the need for now; decide after using it.
- Whether `/events` should offer long polling (`wait=<seconds>`) to spare agents a tight loop.
  Cheap to add on the server thread with a `threading.Condition`; add if an agent asks.
- The family document moved to `asi_fusa_tools/ASI_FUSA_TOOLS.md` on 2026-10-27, so phase 5
  lands there; the digest test's path already follows the move.

*Written 2026-10-27.*
