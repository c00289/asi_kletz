# ASI Kletz — Plan: the JIRA Live Data window

**Status:** Implemented 2026-10-27 (asi_kletz 0.5.0); deviations recorded by the implementing agent in the CHANGELOG entry
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.5.0 (after the 0.4.0 all-columns change, before the family lock at 0.6.0; adds the `asi_hopper` dependency)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md); this plan adds a short table "The JIRA Live
Data window" there.
**Sister plan:** [asi_dewey/docs/jira-live-data-plan.md](../../asi_dewey/docs/jira-live-data-plan.md).
Same window convention, implemented twice, never shared as code.

---

## 1. The ask

Asked by the owner on 2026-10-27, verbatim: "a brand new window common to both tools right below
the dashboard called JIRA Live Data with only a refresh button and a big beautiful table of all
issues past and present with their status and include filtering by common sense fields".

Read as six decisions (the sixth added by the owner after reviewing the first draft):

1. **A new window, common to both tools.** Kletz and Dewey get the same screen under the same
   key, title, verb, columns and filters, so what the owner learns in one tool holds in the other.
   Common means the same convention, implemented twice; never a shared package.
2. **Right below the dashboard.** The screen is the second entry in the navigation list and in
   `View`, in both tools.
3. **Only a refresh button.** One action. No edit, no sync into the database, no timer. The
   window shows Jira; it never changes Jira and never stores what it shows.
4. **A big beautiful table of all issues past and present with their status.** The whole
   project, closed issues included, with status and status category visible, sortable on any
   column, striped, done rows dimmed, the summary column taking the room that is left.
5. **Filtering by common sense fields.** A text box on key and summary, and drop-downs for
   Status, Category, Type, Priority and Assignee, applied locally to the last fetch so a filter
   never costs a Jira call.
6. **A Comments button on every row, and a comments view.** Added by the owner on 2026-10-27
   after the first review: "include a column with a clickable button in the table for each line
   item where every line item is a jira ticket, and if you click on comment, which is the
   clickable comment button, then you get a subsidiary screen that shows the comments history
   with newest at the top and oldest at the bottom." The button is a cell of the table, the
   subsidiary screen is a window of its own per ticket, and it is fed by a verb like everything
   else (section 3.10).

Kletz has no Jira side today: no `asi_hopper` dependency, no `jira` verb, no service. This plan
adds the dependency, a `jira` verb carrying `live` and `comments`, and a service with only what
those two need. Two of Kletz's own constraints are touched by it, and one is not:

- **Still one table.** The live data is a view over Hopper held in memory. Nothing is stored,
  exported or dumped; `safety_plan_row` stays the only entity and the schema version stays 1.
- **Screens are registered, not counted.** The owner asked for a window, and a window in Kletz
  is a screen. The "exactly four screens" rule is **retired as of this plan**; the owner's words,
  2026-10-27: "kletz can now have any number of screens; that rule was just there to prevent an
  overzealous agent from adding screens." From here on a screen is added by registration in
  `gui/screens.py` like a verb, an exporter or a diagram, and the registered list is the design,
  not a cap. `SCREENS` and `TITLES` list the five of this plan in order;
  `test_exactly_four_screens` becomes `test_registered_screens_in_order` and asserts that list,
  never a count. Two earlier plans state the old rule: the theme plan says "Kletz's own
  constraints hold: **still one table, still four screens**. The picker is a control in the
  navigation column and a menu cascade, not a fifth screen" (`theme-palette-plan.md`, section
  1), and the lock plan says "The About box shows the lock directory. Still four screens; no
  screen is added." (`single-instance-plan.md`, section 3). Both were true when written and stay
  as written; this plan supersedes the rule. The lock plan has since been re-targeted to 0.6.0,
  after this one, without rewording, so its phase 1 "Existing suite passes unchanged (one table,
  four screens ...)" is to be read as "one table, the registered screens" when it is implemented.
- **Share nothing with Dewey.** No `asi_dewey` string anywhere in `src/`; `asi_hopper` is
  consumed the way `asi_escher` and `asi_gutenberg` are, as a library, and imported lazily so
  `import asi_kletz` does not load it.

## 2. What exists today (verified 2026-10-27)

| Fact | Where |
|---|---|
| `dependencies = ["asi-escher", "asi-gutenberg", "openpyxl>=3.1"]` with `[tool.uv.sources]` editable path entries for the two generators (`../asi_escher`, `../asi_gutenberg`). No `asi-hopper`. | `pyproject.toml` |
| `commands/__init__.py` imports `crud, generate, gui, theme, transfer` so they register; there is no `commands/jira.py`. `services/__init__.py` exports `EntityService` and `TransferService`; there is no `services/jira_service.py`. `Brain.__init__` wires `self.transfer` and `self.dispatcher`; there is no `self.jira`. | `commands/__init__.py`, `services/__init__.py`, `brain.py` |
| `Dispatcher.execute` turns `BrainError` (so `CommandError`) and `ValueError` into `Result.failure`; any other exception is logged and becomes `Result.failure("<Type>: <message>")`. No exception reaches the window. | `commands/dispatcher.py`, `errors.py` |
| The CLI types arguments through `_TYPES = {"str", "path", "int", "json", "kv", "bool"}`, so an `Argument(type="int")` is parsed as an integer. `Argument`, `Command`, `Result` and `register_command` are byte-identical to Dewey's. | `automation/cli.py`, `commands/base.py` |
| `load_config` reads the path keys (`db`, `workbook`, `out`), `CONFIG_TEXT_KEYS = ("doc_id", "project")`, and the `[[revision]]` list. No boolean keys yet. | `brain.py` |
| `MainWindow.run(verb, **args)` calls `brain.execute(verb, args, actor="gui")`; a failure goes to `notify_error` (status bar `Error: ...` plus a dialog when `interactive`); warnings go to the status bar as `Warning: ...`. | `gui/main_window.py` |
| `_on_event`: `theme.changed` repaints the window (when the canonical key differs); every other topic schedules `current.refresh()` after 50 ms, coalesced through `_refresh_job`. F5 calls `current.refresh()`. `set_theme` destroys every child, clears `_screens`, rebuilds menu and body, and shows the previous key again: a screen's own state does not survive a theme pick. | `gui/main_window.py` |
| The navigation `Listbox` and the `View` menu are built from `factory.items()` in registration order; `show(key)` creates a screen on first use and calls `on_show()`, whose default is `refresh()`. The File menu has "Build Safety Plan document". | `gui/main_window.py`, `gui/screens.py` |
| `build_default_screens` registers `dashboard`, `safety_plan`, `safety_plan_matrix`, `transfer`, with a docstring saying the list is fixed on purpose and that a registered entity never gets a screen. | `gui/screens.py` |
| `tests/test_gui.py`: `SCREENS` and `TITLES` lists of four; `test_exactly_four_screens` asserts both lists and `window.nav.size() == 4`; `test_amber_neon_is_default_and_paints_ttk`, `test_transfer_screen_builds_diagrams_and_documents`, `test_theme_picker_lists_the_catalog_then_plain` and `test_pick_theme_repaints_and_latches` repeat `== SCREENS` or `nav.size() == 4`. | `tests/test_gui.py` |
| `test_source_tree_never_mentions_the_sister_tool` greps `src/` for the sister's name and asserts `asi-escher` and `asi-gutenberg` are in `pyproject.toml`; `test_importing_asi_kletz_does_not_import_the_generators` runs a subprocess and asserts none of `matplotlib, reportlab, docx, asi_escher, asi_gutenberg, PIL` is in `sys.modules`; `test_database_still_has_exactly_one_table_after_generating` lists `sqlite_master` and expects `{"safety_plan"}`; `test_only_the_safety_plan_is_registered`. | `tests/test_generate.py`, `tests/test_core.py` |
| `tests/conftest.py` exposes `REPO_ROOT` and `PLAN`, isolates `ASI_KLETZ_CONFIG`, prefs and theme per test; `seeded` has three plan rows. | `tests/conftest.py` |
| The dashboard shows deliverable tiles, phase counts, open deliverables and recent changes; nothing about Jira. | `gui/dashboard.py` |
| `Theme.stripe(tree)` configures the `odd` and `even` tags and **replaces** each item's tag tuple. `Palette` has a `muted` slot; `Muted.TLabel` is styled with it; `Treeview` selected foreground is `palette.text`. `theme.ui` and `theme.mono` are the two font tuples. | `gui/theme.py` |
| `EntityScreen` is the house table: a `Treeview` with both scrollbars in a grid, heading click to `sort_by(column)` (toggles direction on the same column), `search_var.trace_add("write", ...)` to repopulate on every keystroke, a `count_var` label at the right of the toolbar, `cell_text` truncating at 70 characters. `UrlWidget.open` uses `webbrowser.open`. The transfer screen logs a path instead of opening it when the window is not interactive. | `gui/entity_screen.py`, `gui/widgets.py`, `gui/transfer_screen.py` |
| "Four screens" is stated in the README (the 0.1.0 list, the generation paragraph "The window still has four screens and no others", the layout tree, and "Adding an entity"), in `docs/plan.md` (sections 1, 3 and the 0.1.0 to 0.3.0 rows of section 8), and in the CHANGELOG entries for 0.1.0 to 0.3.0 and the planned lock. | `README.md`, `docs/plan.md`, `CHANGELOG.md` |
| Hopper: `Hopper.search(jql, *, fields=None, all_pages=True, limit=None)` calls `IssueService.search(max_results=100, ...)`; with `limit`, it returns `records[:limit]` as soon as `len(records) >= limit`, so exactly `limit` rows cannot be told from more than `limit`; `MAX_PAGES = 200`. `IssueRecord` carries key, id, project, project_name, issue_type, summary, status, status_category, resolution, priority, assignee, assignee_id, reporter, reporter_id, labels, components, parent (`IssueRef`), created, updated, due, url, description, links, comments, custom, raw. `to_row()` names the type `type` and the parent `parent` and joins labels with `;`. `AuthRequired` and `NotRecorded` are `GatewayError`s, which are `HopperError`s. `Hopper(interactive=False)` reads `$ASI_HOPPER_CONFIG`, else `./hopper.toml`; the replay gateway is selected by `ASI_HOPPER_GATEWAY=replay` and `ASI_HOPPER_FIXTURES`. | `../asi_hopper/src/asi_hopper/hopper.py`, `services/issues.py`, `model/records.py`, `errors.py`, `config.py` |
| Replay matching: `canonical_args` drops `cloudId` and `None` values; a search call is `{jql, fields (the 16 defaults), maxResults 100, responseContentFormat "markdown"}`; `limit` and `all_pages` never reach the gateway. `index.json` **does** list `searchJiraIssuesUsingJql` for the JQL `assignee = currentUser() AND statusCategory != Done ORDER BY status ASC, updated DESC` at `maxResults` 50 and 100, file `searchJiraIssuesUsingJql_open.json`, three issues (HWL-2572, HWL-2575, HWL-2620), `pageInfo.hasNextPage` false. There is no fixture for the house default JQL of this plan. Dewey's `tests/test_jira.py` already drives this fixture through the same environment variables. | `../asi_hopper/tests/fixtures/index.json`, `gateway/replay.py`, `gateway/base.py`, `gateway/api.py` |
| The older integration plan gives Kletz `jira_key` / `jira_status` columns, `jira reconcile` and `jira link`, and a Jira column on the matrix screen; none of it is implemented, and it would add columns to the one table. | `../asi_hopper/docs/integration-plan.md` |
| `Comment` is a frozen dataclass: `id, author, author_id, created, updated, body`. `IssueRecord.comments` is filled only when the call asks for the `comment` field: `JiraApi.get_issue(key, comments=True)` appends `comment` to the 16 defaults; `search` never asks, so a search row's `comments` is `()` and no comment count exists without a per-issue call. Bodies arrive as Markdown (`responseContentFormat: "markdown"`) or as ADF that `adf_to_markdown` renders to Markdown; either way `body` is a Markdown string. | `../asi_hopper/src/asi_hopper/model/records.py`, `model/normalise.py`, `adf/convert.py`, `gateway/api.py` |
| `index.json` lists `getJiraIssue` for HWL-2575 with the 16 defaults plus `comment`, so `hopper.get("HWL-2575", comments=True)` replays; that file's `comment` block is `{"comments": [], "total": 0}`: the path is recorded, the history is empty. | `../asi_hopper/tests/fixtures/index.json`, `getJiraIssue_HWL-2575.json` |
| `Theme.paint` sets `root.configure(background=p.bg)` and option-database defaults for `Listbox`, `Text`, `Canvas`, `Menu` and the combobox list only; nothing for `Toplevel` or `Frame`. A `tk.Toplevel` whose master is the root is in `root.winfo_children()`, so the `set_theme` loop destroys it with the rest. `ScrollableFrame` (canvas, inner frame, wheel binding) lives in `gui/screens.py`. | `gui/theme.py`, `gui/main_window.py`, `gui/screens.py` |
| `ttk.Treeview` tags style items (whole rows), never single cells; `identify_column(x)` and `identify_row(y)` map a click to a cell. Windows in the test suite are `withdraw()`n and never mapped, so `bbox` and `identify_*` return empty there. | Tk `ttk::treeview` manual; `tests/test_gui.py` |
| The family document (then `ASI_FAMILY.md`, now `ASI_FUSA_TOOLS.md`) had, when this was written, a version table at 0.2.0 for both primary tools with `asi_hopper` described as an empty folder (today a 0.1.3 gateway), a plans table of five rows (one saying Kletz keeps "its fixed four screens", the lock plans targeted at 0.3.0), and the palette section with its `| Item | Convention |` table. | `../asi_fusa_tools/ASI_FUSA_TOOLS.md` |
| `docs/all-columns-plan.md` (0.4.0, draft) keeps four screens and says in its open items that "The `JIRA Live Data` window (0.5.0) makes five screens; this plan keeps four and changes no screen list, so the two plans do not collide." `docs/single-instance-plan.md` is re-targeted to 0.6.0 and still says four screens in four places. `docs/automation-server-plan.md` (0.7.0, draft) already counts "four today, five after 0.5.0's JIRA Live Data". | `docs/all-columns-plan.md`, `docs/single-instance-plan.md`, `docs/automation-server-plan.md` |

## 3. Design

### 3.1 The convention (the same in both tools)

| Item | Convention |
|---|---|
| Screen | key `jira_live`, title `JIRA Live Data`, module `gui/jira_live_screen.py`, class `JiraLiveScreen`, registered immediately after `dashboard` |
| Verbs | `jira live [--jql <jql>] [--limit <n>]` and `jira comments <key>`; the windows never call Hopper themselves |
| JQL default | `--jql`, else `jira_live_jql` in `<tool>.toml`, else `project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC` ("all issues past and present") |
| Limit default | 2000; a longer result is cut and reported as a `Result` warning with `truncated: true` |
| toml keys | `jira_live_jql` (text), `jira_live_autofetch` (bool, default `true` at 0.5.0; **`false` since 0.7.4**, see section 8) |
| Columns | Comments (the per-row button), Key, Type, Summary, Status, Category, Priority, Assignee, Reporter, Labels, Parent, Created, Updated, Due, Resolution |
| Filters | text on key or summary; Status, Category, Type, Priority, Assignee; all local, never a re-query |
| Comments view | `gui/jira_comments_window.py`, `JiraCommentsWindow(tk.Toplevel)`, one per ticket, title `<KEY> — Comments`, newest first, fed by `jira comments` |
| Event | `jira.live` with `jql`, `count`, `truncated`, `fetched_at`, `actor`; `jira comments` publishes nothing; neither writes the database or the audit log |
| Storage | none: the last fetch lives on the window object for the life of the process |

The authority is the table "The JIRA Live Data window" that phase 5 adds to the family
document. Each tool carries its own copy of the verb, the service method and the screen; the
agreement is the convention and this plan, never an import.

### 3.2 The `jira live` action

A new verb, with two actions, `live` here and `comments` in section 3.10:

```
asi-kletz jira live                                       # house JQL or jira_live_jql, limit 2000
asi-kletz jira live --jql "project = HWL AND type = Bug"  # one-off JQL
asi-kletz jira live --limit 300                           # cap the fetch; truncated is reported
asi-kletz --compact jira live | jq '.data.issues[] | .key'
asi-kletz jira comments HWL-2572                          # the comment history, newest first
```

New `commands/jira.py`, `JiraCommand`, verb `jira`, help "Jira through asi_hopper, read only:
live <jql> fetch for the JIRA Live Data window, comments <key> for its comments view.", arguments
`Argument("action", "live | comments", required=True, choices=("live", "comments"))`,
`Argument("key", "Issue key for `comments`, e.g. HWL-2572")`,
`Argument("jql", f"JQL for `live` (default: jira_live_jql in kletz.toml, else: {LIVE_JQL})", flag=True)`,
`Argument("limit", "For `live`: most issues to fetch (default 2000)", flag=True, type="int", default=LIVE_LIMIT)`.
`action` is positional with choices so the verb reads the same as Dewey's and so a later action
(the older plan's `reconcile`, if the owner ever wants it) is an added choice, not a new verb.
The `live` branch is a few lines: call `ctx.brain.jira.live(args.get("jql"), int(args.get("limit") or LIVE_LIMIT))`,
publish the event, return `Result.success(data, warnings)` where the one possible warning is
`fetch truncated at <limit> issues; narrow the JQL or raise --limit`. `commands/__init__.py` adds
`jira` to its import line so the verb registers and appears in `schema` and `--help`.

Result data:

```json
{"jql": "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC",
 "fetched_at": "2026-10-27T18:04:11+00:00",
 "count": 2,
 "truncated": false,
 "issues": [
   {"key": "HWL-2572", "issue_type": "Story",
    "summary": "STPA Step 1 – Losses, Hazards & System Boundary – Peer Review",
    "status": "In Progress", "status_category": "indeterminate", "resolution": null,
    "priority": "Un-Groomed", "assignee": "...", "reporter": "...",
    "labels": [], "components": [], "parent_key": "HWL-1915",
    "created": "2026-10-20T09:12:40.000-0600", "updated": "2026-10-27T11:18:59.416-0600",
    "due": null, "url": "https://asirobots.atlassian.net/browse/HWL-2572"},
   "..."]}
```

Every row value is a string or `null` except `labels` and `components`, which are lists (possibly
empty). Dates and times are passed through as Jira returns them; the screen shortens them for
display, the Result does not. `fetched_at` is UTC ISO 8601 to the second, the same format the
event bus stamps on `ts`.

Failures, all `Result.failure` with exit code 1 on the CLI:

| Condition | Message |
|---|---|
| `asi_hopper` not importable | `asi_hopper is not installed: run `uv add --editable ../asi_hopper` in asi_kletz` (`INSTALL_HINT`) |
| no Atlassian session (`AuthRequired`) | Hopper's own text: `no Atlassian session for this account; run `asi-hopper auth login` once` |
| any other `HopperError` (network, server, unrecorded fixture) | `Jira read failed: <hopper message>` |
| `--limit` below 1 | `limit must be at least 1` |

After the fetch the command publishes
`ctx.brain.events.publish("jira.live", jql=jql, count=n, truncated=bool, fetched_at=ts, actor=ctx.actor)`.
Nothing is audited: the audit log records changes to the Safety Plan and a read is not one; the
event is the trace, and it shows in `status()["recent_events"]`.

### 3.3 `JiraService.live`

New `services/jira_service.py`, the smallest service that serves the verb; it carries only what
`live` and `comments` (section 3.10) need and nothing of the sister tool's cache logic:

```python
LIVE_JQL = "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC"
LIVE_LIMIT = 2000
LIVE_FIELDS = ("key", "issue_type", "summary", "status", "status_category", "resolution", "priority",
               "assignee", "reporter", "labels", "components", "parent_key", "created", "updated", "due", "url")
INSTALL_HINT = "asi_hopper is not installed: run `uv add --editable ../asi_hopper` in asi_kletz"


def live_row(record: Any) -> dict[str, Any]:
    """An asi_hopper IssueRecord -> the row of the JIRA Live Data convention (section 3.1)."""
    return {
        "key": record.key, "issue_type": record.issue_type, "summary": record.summary,
        "status": record.status, "status_category": record.status_category,
        "resolution": record.resolution, "priority": record.priority,
        "assignee": record.assignee, "reporter": record.reporter,
        "labels": list(record.labels), "components": list(record.components),
        "parent_key": record.parent.key if record.parent else None,
        "created": record.created, "updated": record.updated, "due": record.due, "url": record.url,
    }


class JiraService:
    """A read-only door to Jira for the JIRA Live Data window. Never writes to the database."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    def open_hopper(self) -> Any:
        """A read-only, non-interactive Hopper. A missing session is reported, never a browser."""
        try:
            from asi_hopper import Hopper
        except ImportError:
            raise CommandError(INSTALL_HINT) from None
        return Hopper(interactive=False)

    def live_jql(self, override: str | None = None) -> str:
        return override or self.brain.config.get("jira_live_jql") or LIVE_JQL

    def live(self, jql: str | None = None, limit: int = LIVE_LIMIT, *, hopper: Any = None) -> dict[str, Any]:
        """Fetch ``jql`` live and return the convention's dict. Nothing is written anywhere."""
        if limit < 1:
            raise CommandError("limit must be at least 1")
        jql = self.live_jql(jql)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            records = self._guard(lambda: hopper.search(jql, all_pages=True, limit=limit + 1))
        finally:
            if own:
                hopper.close()
        issues = [live_row(r) for r in records[:limit]]
        return {
            "jql": jql,
            "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "count": len(issues),
            "truncated": len(records) > limit,
            "issues": issues,
        }

    @staticmethod
    def _guard(call: Any) -> Any:
        from asi_hopper.errors import AuthRequired, HopperError

        try:
            return call()
        except AuthRequired as exc:
            raise CommandError(str(exc)) from None
        except HopperError as exc:
            raise CommandError(f"Jira read failed: {exc}") from None
```

`Brain.__init__` gains `self.jira = JiraService(self)` next to `self.transfer`, and
`services/__init__.py` exports `JiraService`. Both imports of `asi_hopper` are inside functions,
so `import asi_kletz` and `Brain(":memory:")` never load it: the same rule the generators follow,
checked by the same subprocess test (section 6).

Why `live_row` and not `IssueRecord.to_row()`: the convention keeps `labels` and `components` as
lists, names the type `issue_type` and the parent `parent_key` (one vocabulary in both tools), and
adds `reporter`, `resolution` and `components`, which `to_row` lacks. `to_row` stays Hopper's CSV
shape.

Why `limit + 1`: Hopper's `limit` returns exactly `limit` rows whether the query had `limit` or
`limit + 5000` matches. Asking for one more makes the extra row the signal: `truncated` is true
exactly when it arrives, and it is dropped. The cost is nothing (pages are 100 issues; `2001`
needs the same 21 calls as `2000`). With the default limit a full fetch is at most 21 calls, well
under Hopper's own `MAX_PAGES` ceiling of 200.

`hopper=` stays a keyword for tests and for a caller that already holds a Hopper; the window never
passes it.

**The dependency.** Phase 1 runs `uv add --editable ..\asi_hopper` in the repo, which adds
`asi-hopper` to `dependencies` and `asi-hopper = { path = "../asi_hopper", editable = true }` to
`[tool.uv.sources]`, the same pattern as `asi-escher` and `asi-gutenberg`, and updates `uv.lock`.
Kletz ships no `hopper.toml`: Hopper reads `$ASI_HOPPER_CONFIG` (recommended: one `hopper.toml`
in the `asi_hopper` folder, shared by every tool, so one `asi-hopper auth login` serves all), else
`./hopper.toml`. The README says so beside the `jira live` examples.

### 3.4 Configuration

Two keys in `kletz.toml`, both optional:

```toml
# JQL the JIRA Live Data window and `asi-kletz jira live` fetch (default: every HWL issue, newest
# change first). The result is a view held in memory; nothing from Jira is stored in kletz.db.
jira_live_jql = "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC"

# Opt-in (default false since 0.7.4): fetch once when the JIRA Live Data window is first shown
# in a session. Off, the window says "No fetch yet · press Refresh" and waits.
jira_live_autofetch = false
```

`brain.py`: `CONFIG_TEXT_KEYS = ("doc_id", "project", "jira_live_jql")` and a new
`CONFIG_BOOL_KEYS = ("jira_live_autofetch",)` that `load_config` copies only when the TOML value is
a boolean (a string `"false"` is ignored with the key left absent, so the default applies; TOML
has a real boolean type and the example file shows it). Precedence for the JQL: `--jql`, then
`jira_live_jql`, then `LIVE_JQL`. Precedence for autofetch: the toml key, else the default, which
was `true` at 0.5.0 and is `false` since 0.7.4 (`services.jira_service.AUTOFETCH_DEFAULT`; section
8 says why); there is no argument and no environment variable, because it is a project habit, not
a one-off. `doc_id`, `project` and `[[revision]]` are untouched.

### 3.5 The screen

`gui/jira_live_screen.py`, `class JiraLiveScreen(Screen)`, registered in `build_default_screens`
right after the dashboard, the way every screen is added from now on:

```python
factory.register("dashboard", "Dashboard", DashboardScreen)
factory.register("jira_live", "JIRA Live Data", JiraLiveScreen)
factory.register("safety_plan", "Safety Plan", lambda master, window: EntityScreen(master, window, plan))
factory.register("safety_plan_matrix", "Safety Plan Matrix", SafetyPlanMatrixScreen)
factory.register("transfer", "Export / Import", TransferScreen)
```

The docstring becomes "The screens of the window, in navigation order: Dashboard, JIRA Live
Data, Safety Plan, Safety Plan Matrix, Export / Import. A screen is added by registration here;
the list is the design, not a cap. Registering another entity still gives it a table, commands,
JSON and a workbook sheet, never a screen by itself." The module docstring of `screens.py` drops
"the four built-in screens" for "the built-in screens". Navigation order: Dashboard, JIRA Live
Data, Safety Plan, Safety Plan Matrix, Export / Import. The File menu, including "Build Safety
Plan document", is unchanged.

Widget tree:

```
JiraLiveScreen (ttk.Frame, padding 8)
├── toolbar (ttk.Frame)                         pack x, pady (0, 6)
│   ├── Refresh (ttk.Button) -> fetch()         side left
│   └── status_var label (Muted.TLabel)         side left, padx 12: "n issues · fetched hh:mm · <jql>"
├── filter_row (ttk.Frame)                      pack x, pady (0, 6)
│   ├── "Find" label + Entry(filter_var, 28)    side left; key or summary, case-insensitive substring
│   ├── for field in (status, status_category, issue_type, priority, assignee):
│   │     caption label + Combobox(readonly, filters[field], width 16)   side left
│   ├── "Clear filters" (ttk.Button) -> clear_filters()                   side left, padx 8
│   └── count_var label (Muted.TLabel)          side right: "shown of count issues"
└── table (ttk.Frame)                           pack both, expand
    ├── tree (ttk.Treeview, show="headings", selectmode="browse", 15 columns, Comments first)  grid 0,0 nsew
    ├── ybar (ttk.Scrollbar vertical)           grid 0,1 ns
    └── xbar (ttk.Scrollbar horizontal)         grid 1,0 ew
```

Captions over the comboboxes are Status, Category, Type, Priority, Assignee. The combobox state
is `readonly` so a filter is always one of the listed values and never free text.

Columns, in order (`COLUMNS` in the module; the heading text is the convention's column name):

| Column id | Heading | Width | Stretch | Cell |
|---|---|---|---|---|
| `comments` | Comments | 90 | no | `[Comments]` on every row: the per-row button, section 3.10 |
| `key` | Key | 90 | no | as is |
| `issue_type` | Type | 90 | no | as is |
| `summary` | Summary | 420 | **yes** | truncated at 90 characters with `…` |
| `status` | Status | 130 | no | as is |
| `status_category` | Category | 110 | no | as is |
| `priority` | Priority | 100 | no | as is |
| `assignee` | Assignee | 150 | no | as is |
| `reporter` | Reporter | 150 | no | as is |
| `labels` | Labels | 160 | no | `", ".join(labels)` |
| `parent_key` | Parent | 90 | no | as is |
| `created` | Created | 100 | no | first 10 characters (`YYYY-MM-DD`) |
| `updated` | Updated | 100 | no | first 10 characters |
| `due` | Due | 100 | no | first 10 characters |
| `resolution` | Resolution | 110 | no | as is |

`None` shows as an empty cell. Each row's `iid` is its issue key, so a selection maps back to the
row dict without a lookup table.

**Sorting.** Every heading but Comments has `command=lambda c=column: self.sort_by(c)`; the same column
toggles ascending/descending, a new column starts ascending; the sorted heading carries a trailing
`▲` or `▼`. Sort values come from the row dict, not from the cell text, so dates sort on the full
timestamp and `key` sorts numerically: `("HWL", 2620)` after `("HWL", 999)`. `None` sorts last in
both directions. Default order is the server's (the JQL's `ORDER BY`), reached again by `Clear
filters`.

**Stripes and the muted tag.** After every fill: `self.window.theme.stripe(self.tree)`, then, for
each row whose `status_category == "done"`, `tree.item(iid, tags=(*tree.item(iid, "tags"), "muted"))`.
The order matters because `stripe` replaces the tag tuple. The screen configures
`tree.tag_configure("muted", foreground=self.window.theme.palette.muted)` once in `build`; the
stripe tags set only `background` and `muted` sets only `foreground`, so the two never compete and
a done row is dim on its stripe. The screen reads `self.window.theme` for both, like every other
screen, and because a theme pick rebuilds the screen it always reads the palette that is painting
the window.

**Opening an issue.** `<Double-1>` outside the Comments column and `<Return>` on the tree call
`open_selected()`: the focused row's `url` goes to `webbrowser.open` when the window is
interactive; when it is not (tests) the status bar shows `Open: <url>` instead, the transfer
screen's convention. A click in the Comments column and the `c` key open the comments view
(section 3.10).

**Read only.** No form, no edit, no context menu. The buttons that touch Jira are Refresh and the
`[Comments]` cells, and both only read. Nothing on this screen reaches `safety_plan_row`, so the
one table is not even read by it.

### 3.6 Local filtering

`_populate()` runs on every keystroke in the text box (`filter_var.trace_add("write", ...)`), on
every `<<ComboboxSelected>>`, on `Clear filters`, on `sort_by`, and after a fetch. It never calls
the verb.

```
rows   = issues of the last good fetch (or [] when there is none)
needle = filter_var.get().strip().casefold()
if needle:
    rows = [r for r in rows if needle in (r["key"] or "").casefold()
                             or needle in (r["summary"] or "").casefold()]
for field, var in filters.items():                 # status, status_category, issue_type, priority, assignee
    choice = var.get()
    if choice == "(all)": continue
    want = None if choice == "(none)" else choice
    rows = [r for r in rows if r[field] == want]
rows = sorted(rows, key=sort_value, reverse=desc) if sort_column else rows
fill the tree, stripe, mute; count_var = f"{len(rows)} of {len(issues)} issues"
```

Combobox values are rebuilt after every fetch: `["(all)", *values]` where `values` are the
distinct non-null strings present, sorted case-insensitively, plus `(none)` at the end when any
row has `null` there. Category lists its values in the fixed order `new`, `indeterminate`, `done`
(only those present). A selection that is still present after a refetch is kept; one that is gone
resets to `(all)`. `Clear filters` sets the text box to `""`, every combobox to `(all)`, and the
sort to none.

### 3.7 Fetch, show, refresh, rebuild

**Where the last fetch lives: on the window object.** `MainWindow.__init__` sets
`self.jira_live: Result | None = None`. The screen keeps nothing of its own but widgets. Reasons:
`set_theme` destroys and recreates every screen, so a per-screen cache would make a theme pick
cost a Jira round trip and lose a 2000-row fetch; the window outlives screens and is the natural
"this session" scope the brief asks for ("does not auto-fetch on first show if a fetch already
happened this session"); and one attribute is enough because the Result carries everything the
screen needs, including the error text of a failed fetch. It is memory, not storage: it is gone
when the window closes, and it is never read by `dump`, `export` or `status`.

**`fetch()`** (the Refresh button):

```python
def fetch(self) -> Result:
    self.window.set_status("Fetching Jira …")
    self.update_idletasks()
    result = self.window.run_quiet("jira", action="live")
    if result.ok or self.window.jira_live is None:
        self.window.jira_live = result          # a failure after a success keeps the old rows
    self.refresh()
    return result
```

`run_quiet` is `run` without the dialog: same `brain.execute(verb, args, actor="gui")`, same
`Error: ...` / `Warning: ...` lines in the status bar, no `messagebox`. It is a four-line sibling
of `run` in `MainWindow`, and `run` and `run_quiet` share one private `_execute`. The fetch goes
through the command path like every other window action, so the actor is `gui`, the `jira.live`
event is published, and an agent reading `status()["recent_events"]` sees that the window
fetched. A missing session on a machine without a browser session must never be a modal dialog
in the engineer's face on first show, which is why the live screen uses the quiet form for the
button too: the status bar is where this screen reports, every time.

> **Superseded 2026-10-28 (0.7.4).** The synchronous `fetch()` above froze the window for the
> whole fetch (2,000 issues at 50 a page, plus any gateway wait). `fetch()` now starts a
> `BackgroundFetch`, a daemon thread calling `MainWindow.execute_quiet` (the `Brain.execute` half
> of `run_quiet`, no widget), the Tk thread polls it with `after(100)` and `_apply` does what the
> code above did, through `MainWindow.report_quiet` (the status-bar half). Meanwhile the Refresh
> button is disabled, a second `fetch()` is ignored, and a screen destroyed mid-fetch cancels its
> poll and drops the Result. `on_show` repaints first and fetches only when the key is explicitly
> `true`. The comments window has the same shape. See the 0.7.4 CHANGELOG entry.

**`refresh()`** repaints from `self.window.jira_live` and never fetches:

| `window.jira_live` | Toolbar status label | Table |
|---|---|---|
| `None` (never tried) | `No fetch yet · press Refresh` | empty |
| failed Result | `Offline: <first error> · press Refresh` | empty |
| ok Result | `{count} issues · fetched {hh:mm local} · {jql}`, plus ` · truncated at {limit}` when truncated | filled, filtered, sorted |

`fetched hh:mm` is `fetched_at` parsed and converted to local time. The status line is the
screen's own label; the window status bar is for errors, warnings and `Open:` lines.

**`on_show()`**:

```python
def on_show(self) -> None:
    if self.window.jira_live is None and self.brain.config.get("jira_live_autofetch", True):
        self.fetch()
    else:
        self.refresh()
```

First show in a session with autofetch on: one fetch. Any later show, a show after a failed
first fetch, or autofetch off: a repaint with the status line saying what the table holds. An
engineer offline sees an empty table, `Offline: no Atlassian session ...` in the toolbar label and
`Error: ...` in the status bar, and no dialog.

**Rebuild on a theme pick.** `set_theme` recreates the screen; `on_show` runs on the new
instance, finds `window.jira_live` set, and repaints from it. No refetch, and the muted tag
and stripes are configured again from the new palette. Filters and sort are reset by the rebuild
(the widgets are new); the rows are not.

**Event routing.** `_on_event` gains one line next to the `theme.changed` branch:
`if topic == "jira.live": return`. No database row changed, so no screen needs a refresh; the
screen that ran the verb has already painted its Result, and a dashboard or Safety Plan screen
that happens to be open must not re-read the database because somebody looked at Jira.
`theme.changed` and `jira.live` are then the two topics the generic refresh ignores, and the
docstring of `main_window.py` says so.

**F5.** The window's F5 still calls `current.refresh()`, which on this screen is the repaint.
Fetching is the button, as asked; whether F5 should also fetch is an open item.

### 3.8 Error handling, end to end

| Condition | Caught by | Result | Window |
|---|---|---|---|
| `asi_hopper` not installed | `open_hopper` → `CommandError(INSTALL_HINT)` | failure | status bar `Error: asi_hopper is not installed ...`; rows left as they were |
| No session (`AuthRequired`) | `_guard` | failure with Hopper's login hint | status bar `Error: no Atlassian session ...; run asi-hopper auth login once`; rows left |
| Network, server, unrecorded fixture (`HopperError`) | `_guard` → `Jira read failed: ...` | failure | same |
| Unexpected exception in Hopper or normalisation | `Dispatcher.execute` | failure `<Type>: <message>` | same |
| More than `limit` issues | `live` | success, `truncated: true`, one warning | rows shown; status bar `Warning: fetch truncated at 2000 issues; ...`; toolbar label ends `· truncated at 2000` |
| Empty result (JQL matches nothing) | — | success, `count: 0` | empty table; label `0 issues · fetched ...` |

### 3.9 What this plan takes from the older hopper integration plan

From `../asi_hopper/docs/integration-plan.md` this plan keeps the dependency pattern (section 1,
`uv add --editable ..\asi_hopper`, no `hopper.toml` of Kletz's own), `Hopper(interactive=False)`,
the `AuthRequired` wording rule (surface the login instruction, nothing else), and the surface
rule (`Hopper`, `IssueRecord`, the two error classes; nothing from `asi_hopper.gateway`). It
leaves for later, in that plan, everything in its Kletz section: the `jira_key` / `jira_status`
columns, `jira reconcile`, `jira link`, the matrix column, and the evidence snapshots. Those add
columns to the one table and a write path; this plan adds neither. Hopper itself is not changed:
`search` and `IssueRecord` already give everything the window needs.

### 3.10 Comments: the column, the verb, the window

**The column.** `comments` is the **first** column, before Key: with fourteen data columns the
last one sits behind the horizontal scrollbar at most window widths, and a button that has to be
scrolled to is not a button. Every cell reads `[Comments]`, nothing else: a count would need the
`comment` field, which search never fetches (section 2), and asking for it on every page would
drag every body of every issue through each fetch and change the recorded search call. The
heading has no sort command. The cursor becomes `hand2` while the pointer is over that column
(a `<Motion>` handler asking `identify_column`), which is the one per-cell visual Tk allows: a
Treeview tag styles the whole item, so an accent-foreground "link" tag would colour the entire
row and is not used. `<Button-1>` on the tree runs `_on_click`:

```python
def _on_click(self, event: tk.Event) -> str | None:
    if self.tree.identify_column(event.x) != "#1":
        return None                              # any other column: normal selection
    key = self.tree.identify_row(event.y)
    if key:
        self.window.open_comments(key)
    return "break"
```

`<Double-1>` keeps opening the URL except in that column; `<Return>` keeps opening the URL; `c`
on the tree opens the comments of the focused row. This is the Tk-native per-row button: the
widget has no cell widgets, so the cell is text and the click is routed by position.

**The verb.** `jira comments <key>`, the second action of the new `jira` verb beside `live`
(`choices=("live", "comments")`), with the positional `key` of section 3.2. Result data:

```json
{"key": "HWL-2572", "summary": "STPA Step 1 – ...", "url": "https://.../browse/HWL-2572",
 "status": "In Progress", "fetched_at": "2026-10-27T18:04:11+00:00", "count": 2,
 "comments": [
   {"id": "10452", "author": "...", "created": "2026-10-26T15:02:11.000-0600",
    "updated": "2026-10-26T15:40:00.000-0600", "body": "Reviewed the loss list; L3 needs ..."},
   {"id": "10431", "author": "...", "created": "2026-10-21T09:12:40.000-0600",
    "updated": "2026-10-21T09:12:40.000-0600", "body": "Draft attached."}]}
```

Newest first by `created`, ties by `id`, both descending. Failures mirror `live`: `INSTALL_HINT`,
Hopper's `AuthRequired` text, `Jira read failed: <message>` for every other `HopperError`, which
includes an unknown key (`issue HWL-1 not found or not visible to this account`); a missing key
is `jira comments needs an issue key, e.g. HWL-2572`.

`JiraService.comments(key, *, hopper=None) -> dict`, beside `live` in `services/jira_service.py`:

```python
def comment_row(comment: Any) -> dict[str, Any]:
    return {"id": comment.id, "author": comment.author, "created": comment.created,
            "updated": comment.updated, "body": comment.body or ""}


def comments(self, key: str, *, hopper: Any = None) -> dict[str, Any]:
    key = (key or "").strip().upper()
    if not key:
        raise CommandError("jira comments needs an issue key, e.g. HWL-2572")
    own = hopper is None
    hopper = hopper or self.open_hopper()
    try:
        record = self._guard(lambda: hopper.get(key, comments=True))
    finally:
        if own:
            hopper.close()
    items = sorted((comment_row(c) for c in record.comments),
                   key=lambda c: (c["created"] or "", c["id"] or ""), reverse=True)
    return {"key": record.key, "summary": record.summary, "url": record.url, "status": record.status,
            "fetched_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "count": len(items), "comments": items}
```

`author_id` is dropped from the row; `author` (the display name Jira shows) is kept, because a
history without its authors is not a history. Nothing here touches `safety_plan_row`.

**Publishing.** `jira comments` publishes nothing, and the rule that says so is the one that
makes `jira live` publish: a verb publishes when it changes something a front end holds.
`create` and `update` change rows, `theme` changes the paint, `live` changes the session's live
table (`window.jira_live`). A comments lookup changes nothing anyone holds; it is a `get` with a
different shape, and `get` publishes nothing today. The window that asked gets its Result back
directly.

**The window.** `gui/jira_comments_window.py`, `class JiraCommentsWindow(tk.Toplevel)`, master
the main window, one per ticket, non-modal, title `<KEY> — Comments`, 640 x 520, resizable.
`Theme.paint` paints the root's background and the option database only (section 2), so the
window sets `self.configure(background=self.window.theme.palette.bg)` itself; its ttk children
take the styles and its `tk.Text` bodies take the `*Text.*` option entries, so nothing else is
painted by hand.

```
JiraCommentsWindow (tk.Toplevel)
├── header (ttk.Frame, padding (10, 8))
│   ├── "<KEY>  <summary>" (Title.TLabel)   and   "<status>" (Muted.TLabel)
│   └── url (TLabel, foreground palette.accent, cursor hand2, <Button-1> -> webbrowser.open)
├── toolbar (ttk.Frame)
│   ├── Refresh (ttk.Button) -> fetch()     Close (ttk.Button) -> close()
│   └── status_var label (Muted.TLabel): "n comments · fetched hh:mm" or "Error: ..."
└── body (ScrollableFrame from gui/screens.py), one block per comment, newest at the top:
    ├── meta (Muted.TLabel): "<author> · <created>" + " · edited <updated>" when updated != created
    ├── text (tk.Text, wrap word, state disabled after insert, height min(lines, 12), padx 6)
    └── rule (Rule.TFrame, height 1)
```

Bodies are `tk.Text`, not wrapped `Label`s: bodies are long, carry newlines and Markdown, and an
engineer copies lines out of them into a review; a `Label` is not selectable and its `wraplength`
is a fixed pixel width. `state="disabled"` after the insert makes it read-only; the `*Text.*`
option entries give it the field colours and the monospace font. Timestamps show as
`YYYY-MM-DD HH:MM` (the first 16 characters, `T` replaced by a space), no zone conversion: a
comment's time is Jira's. Empty history: one `Muted.TLabel` reading `No comments.`. `<Escape>`
closes, `<F5>` refreshes.

`fetch()` runs `self.window.run_quiet("jira", action="comments", key=self.key)`: a success rebuilds
the body and sets the status line; a failure sets `Error: <first error>` in the window's own
status line, leaves whatever was listed in place, and leaves the window open so the engineer can
sign in and press Refresh. `run_quiet` also writes the `Error:` line to the main status bar,
which is right: that bar is the one place every error of the tool lands. `open_comments(key)` on
`MainWindow` is the only place the window is constructed:

```python
def open_comments(self, key: str) -> JiraCommentsWindow:
    win = self.comment_windows.get(key)
    if win is not None and win.winfo_exists():
        win.lift()
        win.focus_set()
        return win
    win = self.comment_windows[key] = JiraCommentsWindow(self, key)
    win.fetch()
    return win
```

`self.comment_windows: dict[str, JiraCommentsWindow]` starts empty in `__init__`; the window's
`close()` pops its key and destroys it. All comment windows close with the main window
(`destroy()` on the root takes every Toplevel with it). On a theme pick they are **destroyed,
not repainted**: the `set_theme` loop over `winfo_children()` already destroys them because a
Toplevel is a child of the root, and `set_theme` clears `comment_windows` in the same breath.
Reason: it is the rebuild rule every screen follows, the content is one `jira comments` away,
and repainting a `tk.Text` and each label by hand is the per-widget repaint the theme plan
rejected.

Why a Toplevel and not a screen in the navigation column: a comments view belongs to one ticket,
several can be open side by side while the table is still in use, and the nav list is for the
tool's own screens, not for one row of one of them. (The retired count rule is not the reason;
a per-ticket window would be a Toplevel even with that rule gone, as it is in Dewey.)

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Verb + service + dependency | `uv add --editable ..\asi_hopper`; `services/jira_service.py` (`LIVE_JQL`, `LIVE_LIMIT`, `INSTALL_HINT`, `live_row`, `JiraService` with `open_hopper`, `live_jql`, `live`, `_guard`); `Brain.jira`; `commands/jira.py` with `live` and `--limit`; `jira.live` event; `jira_live_jql` and `jira_live_autofetch` in `load_config`. | New `tests/test_jira.py` passes on the replay gateway; `asi-kletz jira live --jql "<OPEN_JQL>"` prints 3 issues; the share-nothing and one-table tests pass with `asi_hopper` added to their sets; `import asi_kletz` does not import `asi_hopper`. |
| 2. Screen | `gui/jira_live_screen.py`; registration after `dashboard` (docstrings: registered, not counted); `MainWindow.jira_live`, `run_quiet`, the `jira.live` early return in `_on_event`; `SCREENS`, `TITLES`, `test_registered_screens_in_order` and the other `== SCREENS` assertions (the `nav.size() == 4` counts go). | `tests/test_gui.py` passes with the five-entry list; manual check: open the window, JIRA Live Data is second in the nav and in View, Refresh fills the table, filters narrow it per keystroke, a done row is dim, double-click opens the browser, pick a theme and the rows are still there, the Safety Plan screens are unchanged. |
| 3. Comments | `comment_row`, `JiraService.comments`; action `comments` and the `key` argument on the verb; the `[Comments]` column, `_on_click`, the `hand2` cursor, the `c` key; `gui/jira_comments_window.py`; `MainWindow.comment_windows`, `open_comments`, the clearing in `set_theme`. | Comments cases of section 6 pass on replay, the stub and the window; manual check: click `[Comments]` on a ticket with a history, newest at the top, click it again and the same window comes to the front, pick a theme and the window closes, click again and it comes back. |
| 4. Docs | README: section "JIRA Live Data" (window, verbs `live` and `comments`, the comments window, `hopper.toml` note) and every "exactly four screens" wording replaced by "screens are registered in `gui/screens.py`; the list is the design, not a cap" (the 0.1.0 list, the generation paragraph, the layout tree, "Adding an entity"); CHANGELOG 0.5.0 entry naming the new screen, the comments window, the retired count rule and the new dependency; `docs/plan.md` sections 7, 8 and 9 (and the "four screens" wording in sections 1 and 3); `kletz.example.toml` keys; `version.py` and `pyproject.toml` 0.5.0. | `uv run pytest` and `uv run ruff check src tests` clean; README examples run; `grep -i "four screens"` in README, CHANGELOG's new entry and `docs/plan.md` sections 1 and 3 finds nothing (historical CHANGELOG entries and the two earlier plans keep their wording). |
| 5. Family | `ASI_FUSA_TOOLS.md`: version table 0.5.0 for both tools, plans table rows for the two `jira-live-data-plan.md` files, the Kletz escher-gutenberg row's "fixed four screens" left as history, and the one-table section "The JIRA Live Data window" (key, title, verbs, JQL default, toml keys, comments view), written once and shared with the Dewey plan's phase 5. | The sister's phase 5 finds the section present and adds nothing; `diff` of the two plans shows only the differences listed in section 1 of each. Tag left to the owner. |

## 5. Files touched

```
pyproject.toml, uv.lock                    asi-hopper dependency + editable path source; version 0.5.0
src/asi_kletz/services/jira_service.py     new: LIVE_JQL, LIVE_LIMIT, LIVE_FIELDS, INSTALL_HINT, live_row, comment_row, JiraService (open_hopper, live_jql, live, comments, _guard)
src/asi_kletz/services/__init__.py         export JiraService
src/asi_kletz/commands/jira.py             new: JiraCommand, verb `jira`, actions `live` and `comments`, key, --jql, --limit (int), jira.live event
src/asi_kletz/commands/__init__.py         import the new module so it registers
src/asi_kletz/brain.py                     Brain.jira; CONFIG_TEXT_KEYS + jira_live_jql; CONFIG_BOOL_KEYS = (jira_live_autofetch,)
src/asi_kletz/gui/jira_live_screen.py      new: JiraLiveScreen (toolbar, filter row, 15-column table with the [Comments] column)
src/asi_kletz/gui/jira_comments_window.py  new: JiraCommentsWindow (one Toplevel per ticket, newest first)
src/asi_kletz/gui/screens.py               register jira_live right after dashboard; docstrings: registered, not counted
src/asi_kletz/gui/main_window.py           jira_live and comment_windows attributes, run_quiet (+ shared _execute), open_comments, jira.live early return, docstring
tests/test_jira.py                         new: live on replay, limit/truncated, default JQL unrecorded, config key, event, no write, stub cases; comments: replay (empty history), stub ordering, unknown key
tests/test_gui.py                          SCREENS/TITLES of five entries, test_registered_screens_in_order; fill from a stubbed run, sort, filters, muted, status, rebuild, no write; Comments click, the comments window
tests/test_generate.py                     asi_hopper joins the lazy-import set and the pyproject assertion; one table after jira live
tests/test_core.py                         load_config reads jira_live_jql and jira_live_autofetch
kletz.example.toml, README.md, CHANGELOG.md, docs/plan.md
../asi_fusa_tools/ASI_FUSA_TOOLS.md                           version table, plans table, section "The JIRA Live Data window"
src/asi_kletz/version.py                   0.5.0
```

No change to `schema/`, `storage/`, `repositories/`, `models/`, `io/`, `generate/`, `prefs.py`,
`gui/theme.py`, `gui/palettes.py`, `gui/dashboard.py`, `gui/entity_screen.py`,
`gui/matrix_screen.py`, `gui/transfer_screen.py`, or `../asi_hopper`. One table, schema version 1;
no new column or lookup. `docs/theme-palette-plan.md` and `docs/single-instance-plan.md` are not
edited; section 1 records that this plan supersedes their screen count.

## 6. Tests

**Verb and service (`tests/test_jira.py`, new)**, built like Dewey's: `HOPPER_FIXTURES =
REPO_ROOT.parent / "asi_hopper" / "tests" / "fixtures"`, `pytestmark` skips the module when the
fixtures are not checked out, an autouse fixture deletes `ASI_HOPPER_CONFIG` and sets
`ASI_HOPPER_GATEWAY=replay` and `ASI_HOPPER_FIXTURES`, and `OPEN_JQL` is the recorded query. The
fixture index **does** carry a recorded `searchJiraIssuesUsingJql` for `OPEN_JQL` (three issues,
one page), so the verb is tested end to end against the replay gateway; the house default JQL
has no fixture, which is itself a case. A stub Hopper is used only where the fixture cannot reach
(exactly-at-limit behaviour and null-heavy rows).

- `jira live --jql OPEN_JQL`: `ok`; `data["count"] == 3`; keys `["HWL-2572", "HWL-2575", "HWL-2620"]`
  in server order; `truncated is False`; `jql == OPEN_JQL`; `fetched_at` parses as an aware UTC
  datetime; every row has exactly the 16 keys of `LIVE_FIELDS`; `labels` and `components` are
  lists; HWL-2572's `parent_key == "HWL-1915"`, `status_category == "indeterminate"`,
  `issue_type == "Story"`; HWL-2620's `labels == ["VAT", "e-stop", "safety", "test-failure"]`.
- `--limit 2`: `count == 2`, `truncated is True`, keys are the first two, and `result.warnings[0]`
  contains `truncated at 2`. `--limit 3`: `count == 3`, `truncated is False`, no warning (the
  `limit + 1` probe asks for four, gets three). `--limit 0`: `not ok`, error names `limit`.
- No fixture for the house JQL: `jira live` with no `--jql` is `not ok` and its error starts with
  `Jira read failed:` (the `NotRecorded` path); the database is untouched.
- Config: with `ASI_KLETZ_CONFIG` pointing at a temp toml holding `jira_live_jql = "<OPEN_JQL>"`,
  `jira live` without `--jql` succeeds with 3 issues and `data["jql"] == OPEN_JQL`;
  `brain.jira.live_jql() == LIVE_JQL` when the key is absent; `brain.config["jira_live_autofetch"]`
  is `False` when the file says `jira_live_autofetch = false` and absent when the file says
  `jira_live_autofetch = "false"` (in `tests/test_core.py` next to the other `load_config` cases,
  with `doc_id` and `[[revision]]` still read as before).
- Nothing written, one table: after a successful `jira live`, `count safety_plan_row` is
  unchanged, `audit_tail(10)` has no new entry, `sqlite_master` still lists only `safety_plan`
  (plus `schema_migrations` and `audit_log`), and `events.last(1)[0]` is `{"topic": "jira.live",
  "count": 3, "truncated": False, "jql": OPEN_JQL, "actor": "python", "fetched_at": ...}`.
- Service with a stub (no fixture needed): `monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)`
  where `stub.search(jql, *, all_pages, limit)` records its arguments and returns `limit` or
  fewer `IssueRecord`-shaped objects (a small frozen dataclass in the test with the attributes
  `live_row` reads, `parent` either `None` or an object with `.key`). Assert `search` was called
  with `all_pages=True, limit=limit + 1`; a stub returning exactly `limit + 1` records gives
  `truncated is True` and `count == limit`; a record with every optional attribute `None` and
  empty tuples maps to `null`s and `[]`s; `stub.close()` is called when the service opened the
  Hopper and not when one was passed in.
- `AuthRequired` from the stub's `search` becomes `not ok` with the login hint in `errors[0]`;
  `ImportError` from a monkeypatched `open_hopper` becomes `not ok` with `INSTALL_HINT`.
- `jira sync` and `jira dance` fail (unknown choice); `schema` for `jira` lists `live` as the
  only action choice and `limit` with `type == "int"` and `default == 2000`; `"jira"` is in
  `default_command_factory.verbs()` and in `asi-kletz --help`.

**Share nothing and one table (`tests/test_generate.py`, `tests/test_core.py`)**

- `test_importing_asi_kletz_does_not_import_the_generators` adds `asi_hopper` to the module set
  it asserts absent, and its subprocess also runs `b.execute("schema", entity="jira")` so the verb
  module is imported without the library behind it.
- `test_source_tree_never_mentions_the_sister_tool` asserts `asi-hopper` is in `pyproject.toml`
  beside `asi-escher` and `asi-gutenberg`; the grep for the sister's name still finds nothing.
- `test_only_the_safety_plan_is_registered` is unchanged and still passes: no entity was added.

**Window (`tests/test_gui.py`)**, real `MainWindow` on the `seeded` brain, `interactive=False`.
`SCREENS = ["dashboard", "jira_live", "safety_plan", "safety_plan_matrix", "transfer"]`,
`TITLES = ["Dashboard", "JIRA Live Data", "Safety Plan", "Safety Plan Matrix", "Export / Import"]`,
`test_exactly_four_screens` becomes `test_registered_screens_in_order`, asserting
`[k for k, _ in window.factory.items()] == SCREENS`, the titles, and that the nav list has one
entry per registered screen in that order (never a bare count); the four other `== SCREENS` /
`nav.size() == 4` assertions follow the same shape. The screen is filled from a stubbed
`run_quiet` (`monkeypatch.setattr(window, "run_quiet", fake)` returning `Result.success(SAMPLE)`),
where `SAMPLE` holds five hand-written rows covering two statuses, all three categories, two
types, two priorities, two assignees, one null assignee, one null due date, labels, a parent, and
keys `HWL-9`, `HWL-10`, `HWL-100`, `HWL-2`, `HWL-33`. No replay gateway is needed in the GUI tests
and no network is ever touched.

- Order: `[k for k, _ in window.factory.items()] == SCREENS`; `window.factory.title("jira_live") == "JIRA Live Data"`;
  the second `View` menu entry is `JIRA Live Data`; `window.nav.get(1).strip() == "JIRA LIVE DATA"`;
  `window.nav.size() == len(SCREENS)`.
- First show fetches once: with the stub counting calls, `window.show("jira_live")` calls it
  once; `window.show("dashboard")` then `window.show("jira_live")` does not call it again;
  `window.jira_live.data is SAMPLE`; 5 rows in the tree; the toolbar label matches
  `r"^5 issues · fetched \d\d:\d\d · project = HWL"`; `count_var` is `5 of 5 issues`.
- Autofetch off: `monkeypatch.setitem(seeded.config, "jira_live_autofetch", False)`, show the
  screen, the stub is not called, the tree is empty, the label is `No fetch yet · press Refresh`;
  `screen.fetch()` then fills it.
- Refresh button: `screen.fetch()` calls the stub again and repaints; a stub that now returns
  `Result.failure("no Atlassian session for this account; run `asi-hopper auth login` once")`
  leaves the 5 rows in place, keeps `window.jira_live.ok`, and puts `Error: no Atlassian
  session` in `window.status_text()`. On a fresh window whose first fetch fails the same way:
  empty tree, label starts `Offline:`, `window.jira_live` is the failed Result, and a second
  `show` does not fetch again.
- Sorting: `screen.sort_by("key")` orders iids `HWL-2, HWL-9, HWL-10, HWL-33, HWL-100` (numeric,
  not lexical); a second `sort_by("key")` reverses it; `sort_by("due")` puts the null due last in
  both directions; the sorted heading text ends with `▲` then `▼`.
- Each filter: `filter_var.set("hwl-1")` leaves `HWL-10` and `HWL-100` (case-insensitive, key);
  `filter_var.set("brake")` matches on summary only; `filters["status"].set("Done")` then
  `_populate()` shows the done rows only and `count_var` reads `2 of 5 issues`;
  `filters["status_category"]` values are `["(all)", "new", "indeterminate", "done"]`;
  `filters["assignee"]` values end with `(none)` and selecting it shows the unassigned row;
  `filters["issue_type"]` and `filters["priority"]` each narrow to their rows; two filters
  combine with AND; `clear_filters()` restores 5 rows, every combobox to `(all)`, and the server
  order.
- Muted: every row with `status_category == "done"` has `"muted"` in `tree.item(iid, "tags")`
  together with its `odd`/`even` stripe tag, and no other row does;
  `tree.tag_configure("muted", "foreground") == window.theme.palette.muted` (cyan-neon's
  `#a98260` by default).
- Cells: `tree.set("HWL-9", "labels") == "safety, VAT"`, `tree.set("HWL-9", "created")` is 10
  characters, `tree.set("HWL-33", "assignee") == ""` for the null assignee.
- Open: `tree.focus("HWL-9"); screen.open_selected()` puts `Open: https://...HWL-9` in the status
  bar (not interactive, so no browser); with nothing focused the status bar says
  `Select an issue first`.
- Rebuild keeps the rows: `window.pick_theme("pink-noir")` with the screen current; afterwards
  `window.current_key == "jira_live"`, the stub was not called again, the tree has 5 rows,
  `tree.tag_configure("muted", "foreground") == "#955073"` (pink-noir's `muted`), and
  `[k for k, _ in window.factory.items()] == SCREENS` still.
- Event path: `seeded.events.publish("jira.live", count=0, jql="x", truncated=False,
  fetched_at="", actor="agent")` while the dashboard is current does not schedule a refresh
  (`window._refresh_job is None` right after); `entity.created` still does.
- Nothing written: after every case above `seeded.execute("count", entity=PLAN).data["count"] == 3`
  and the last audit entry is still the seed's; the Safety Plan screen still shows its three rows.

**Comments: the verb (`tests/test_jira.py`)**. The recorded `getJiraIssue_HWL-2575.json` is
keyed with the `comment` field, so the `comments=True` path replays end to end; its history is
empty, so ordering and the row mapping are tested with a stub.

- `jira comments HWL-2575` on replay: `ok`; `data["key"] == "HWL-2575"`; `summary` starts with
  `STPA Step 4`; `url` ends with `/browse/HWL-2575`; `status` is a non-empty string; `count == 0`;
  `comments == []`; `fetched_at` parses as aware UTC. `jira comments hwl-2575` (lower case) gives
  the same answer. `jira comments HWL-1`: `not ok`, error starts with `Jira read failed:`.
  `jira comments` with no key: `not ok`, error names the key. Nothing written, no audit entry,
  `sqlite_master` still lists only `safety_plan`, and `events.last(1)` is the same before and
  after the call (no event).
- Stub: `open_hopper` returns a stub whose `get(key, *, comments)` asserts `comments is True`
  and returns a record with three `Comment`-shaped objects created `2026-10-01`, `2026-10-03`,
  `2026-10-02` (ids `c1`, `c3`, `c2`), one of them with `updated` later than `created` and one
  with `body=None`: the Result lists ids `["c3", "c2", "c1"]`, keeps `updated` as given, maps
  the `None` body to `""`, and has no `author_id` key. `AuthRequired` from the stub's `get`
  gives the login hint; `stub.close()` is called when the service opened the Hopper.
- `schema` for `jira` lists `live` and `comments` as the action choices and `key` as a
  positional argument.

**Comments: the window (`tests/test_gui.py`)**, with the `run_quiet` stub branching on
`action`: `live` returns `SAMPLE`, `comments` returns `COMMENTS` (three comments for `HWL-9`,
newest first as the verb would send them, one of them edited) and counts its calls per action.

- Click dispatch: the test windows are withdrawn and never mapped, so `bbox` and `identify_*`
  return empty and `event_generate` cannot land in a cell; the test monkeypatches
  `screen.tree.identify_column` to return `"#1"` and `identify_row` to return `"HWL-9"`, then
  calls `screen._on_click(SimpleNamespace(x=5, y=5))`: `"HWL-9"` is in `window.comment_windows`
  and the handler returned `"break"`. With `identify_column` returning `"#3"` nothing opens and
  the handler returns `None`. `tree.focus("HWL-9"); screen._on_key_c(None)` opens it too.
- The window: `win = window.open_comments("HWL-9")`; `win.title() == "HWL-9 — Comments"`;
  `win.cget("background") == window.theme.palette.bg`; the meta labels in `win.body.inner`, in
  order, start with the newest comment's author and `2026-10-26 15:02`, and the edited one ends
  with `· edited 2026-10-26 15:40`; the three `tk.Text` bodies are `disabled` and hold the
  bodies; `win.status_var.get()` matches `r"^3 comments · fetched \d\d:\d\d$"`.
- Second open: `window.open_comments("HWL-9") is win` and `len(window.comment_windows) == 1`;
  `open_comments("HWL-10")` makes two.
- Refresh: `win.fetch()` adds one `comments` call to the stub's count and the body still lists
  three. A stub now failing with `Result.failure("no Atlassian session ...")`: `win.fetch()`
  leaves the three blocks, `win.status_var.get().startswith("Error: no Atlassian session")`,
  `win.winfo_exists()`, and `window.status_text()` starts with `Error:`.
- Empty: a stub returning `count: 0, comments: []` for `HWL-2` shows one label `No comments.`.
- Close: `win.close()` removes the key from `comment_windows` and `win.winfo_exists()` is false.
  Theme pick with one open: after `window.pick_theme("pink-noir")`, `window.comment_windows == {}`
  and the old window's `<Destroy>` flag is set. Main-window close: open one, bind a `<Destroy>`
  flag on it, `window.close()`; the flag is set (this case uses its own window from `_open`,
  since it ends the window).
- Nothing written: `count safety_plan_row` is still 3 after every case, and
  `[k for k, _ in window.factory.items()] == SCREENS` (a Toplevel is not a screen).

**Replay end to end once (`tests/test_jira.py`, GUI-free)**: `brain.execute("jira", action="live",
jql=OPEN_JQL, actor="gui")` and `brain.execute("jira", action="comments", key="HWL-2575",
actor="gui")` are what the windows send; asserting them here keeps the window tests free of the
fixture and the fixture tests free of Tk.

## 7. Rejected alternatives

- **Storing the live rows in a table.** Kletz holds exactly one table, the Safety Plan, and
  "nothing else is stored, shown, or exported" is the tool's defining property, tested in two
  places. "All issues past and present" is thousands of rows that Jira owns; a second table
  would break the rule for data the tool must never edit. Memory on the window object is enough
  for a view.
- **Server-side filtering per keystroke.** Every keystroke would be a JQL call: rate limit,
  latency, and a table that flickers. One fetch, then local filters, is instant and offline-safe.
- **A shared `asi_jira_screen` package.** The family rule: primary tools share conventions, not
  code. The twin plans and the family table are the agreement; a test in each repo guards the
  key, title and position. The share-nothing test would also fail on any import from the sister.
- **Auto-refresh on a timer.** The owner asked for a refresh button only. A timer would also
  fetch while the engineer is typing a filter and would burn the rate limit while the window
  sits in the background.
- **Putting the table inside the dashboard or Export / Import to avoid a new screen.** The
  owner asked for a window "right below the dashboard"; a frame inside another screen is neither
  below it nor a window, and the count rule it would have served is retired.
- **Implementing the older plan's `reconcile` / `link` at the same time.** They add two columns
  to the one table and a write path (`--apply`); the owner asked to look at Jira, not to link the
  plan to it. They stay in `../asi_hopper/docs/integration-plan.md` for a decision of their own.
- **Reusing `EntityScreen` with a fake schema.** It carries a form, create/update/delete and
  `by_id` on integer ids; the live screen needs none of that and keys rows by issue key. A
  dedicated, read-only screen is smaller than the subclass would be.
- **Caching the fetch on the screen instance.** Lost on every theme pick (`set_theme` recreates
  screens), so a repaint would refetch. The window object outlives screens; see section 3.7.
- **`IssueRecord.to_row()` as the row.** It joins labels with `;`, calls the type `type` and the
  parent `parent`, and lacks reporter, resolution and components. The convention row keeps one
  vocabulary in both tools and lists as lists.
- **A real `ttk.Button` per row, overlaid on the Treeview.** Buttons placed with `place()` over
  cell bboxes must follow every scroll, sort, filter and resize, and `bbox` is empty for rows
  not on screen; the text cell with position-routed clicks costs nothing and never drifts.
- **An accent "link" tag on the Comments cell.** Treeview tags style the item, so the whole row
  would turn accent; the cell reads `[Comments]` and the cursor does the signalling.
- **Requesting the `comment` field in the live search to show a count.** Every page would carry
  every body of every issue, the fetch would be many times heavier, and the recorded search
  fixture would no longer match. A count is a per-issue call; the window shows the history.
- **A nav screen with a Back button for comments.** One ticket per view, several open at once,
  and the nav list is for the tool's own screens; a Toplevel per ticket does all three.
- **Publishing a `jira.comments` event.** Nothing anyone holds changes; see section 3.10.

## 8. Open items

- 2026-10-28 (0.7.4): `jira_live_autofetch` now defaults to `false` and the fetch runs on a worker
  thread. The owner reported that the sister tool "ran but got stuck on jira live data" and asked
  that neither tool connect automatically and that the freeze be root-cause fixed: the first
  show started a synchronous `jira live` on the Tk thread, so merely opening the screen froze the
  window for a 2,000-issue fetch or a gateway wait. Sections 3.4 and 3.7 carry the notes; the
  rest of this plan describes the 0.5.0 shape.
- Whether F5 on the live screen should fetch as well as repaint. Cheap either way; decide after
  using the button for a week.
- When the automation server lands (0.7.0), whether a `jira live` run by an agent should push its
  rows into an open window. Today the event carries counts only and the window ignores it; the
  verb's Result belongs to its caller. If wanted, the event would carry the rows or the window
  would re-run the verb on `jira.live` from another actor.
- Comment bodies are shown as the Markdown text Hopper gives (ADF is already rendered to
  Markdown by `adf_to_markdown`); bold, lists and links appear as their Markdown marks. A later
  plan may render Markdown into the `tk.Text` with tags; plain text first.
- Whether the Safety Plan screen should one day carry the same `[Comments]` cell beside a
  `jira_key` column. That follows the `jira_key` open item below, not this plan.
- Whether the toolbar should show the Jira site name next to the count, from `hopper.status()`.
  Not now: that is a second call and the status bar already shows the database.
- The family document's version table still says 0.2.0 for both primary tools and calls
  `asi_hopper` an empty folder; phase 5 updates the versions and the `asi_hopper` row should be
  corrected in the same edit if the 0.3.0 and 0.4.0 plans have not already done it.
- This plan assumes 0.4.0 (`all-columns-plan.md`, every Safety Plan column on the screen) has
  landed, but nothing in it depends on that: registration after `dashboard` is positional and
  the Safety Plan screen is untouched either way.
- Whether a later Kletz 0.x should take the older plan's `jira_key` column so a deliverable can
  name its Jira issue. Out of scope here; it would be the first Jira fact stored in the one table
  and deserves its own decision.

*Written 2026-10-27.*
