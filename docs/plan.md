# ASI Kletz — Plan

**Status:** 0.24.3 delivered
**Started:** 2026-10-27
**Owner:** FuSa engineer

---

## 1. Vision

ASI Kletz is a Python desktop application and FuSa (functional safety) API in one package,
for one artefact: the platform **Safety Plan**.

- A **custom tkinter GUI** gives a human engineer the screens registered in `gui/screens.py`
  to maintain the safety plan: a dashboard, a live read-only view of Jira (0.5.0), the plan as
  a table and form, the plan as a flag matrix, and export/import. The list is the design, not
  a cap: a screen is added by registration, like a verb or a diagram.
- A **database** is the single source of truth. Every screen reads from it and writes to it.
- The Excel workbook **`kletz.xlsx` is a generated view of the model**, not the model itself.
  At any moment the user (or an automation) can regenerate it from the database.
- The table can be **dumped to JSON** (and loaded back) for portability, diffing, versioning,
  and feeding AI tools.
- A **robust automation command layer** lets a human engineer, an AI agent, or both at the same
  time "puppet" the tool. Everything the GUI can do, a command can do.
- The **factory design pattern** is used as much as possible: models, repositories, screens,
  widgets, themes, exporters, importers, and commands are all created through registries and
  factories.

The tool was split from ASI Dewey on 2026-10-27 and deliberately holds nothing else. Working
knowledge (tasks, facts, people, links, tickets, QMS references, machine functions, use cases)
lives in Dewey; the two tools do not share a database, workbook, configuration, or environment
variable.

---

## 2. Domain model

One entity, seeded from the `Safety Plan` sheet of the workbook. Column labels are the exact
workbook headers so the sheet round-trips.

| Entity | Source sheet | Fields | Notes |
|---|---|---|---|
| `SafetyPlanRow` | Safety Plan | order, pdp_phase, lifecycle_phase, deliverable, work_product_location, location flags (3), work_product_reference, reference flags (23), author, author flags (17), verification flags (3), gate_reviewer, reviewer flags (7), deadline, status | 63 columns; the table shows all of them, the matrix one flag group at a time |

Lookups: `pdp_phase` (1 to 6), `lifecycle_phase` (the ten safety lifecycle phases),
`plan_status` (Pending, Ongoing, Blocked, Alternative, Out-of-Scope, Done). Lookups are soft:
a value outside the list loads with a warning.

Design rules:

- The entity gets a surrogate primary key `id` plus `created_at` / `updated_at`.
- `order` is user-controlled display ordering, not a key.
- The entity is declared once, in `schema/definitions.py`, and everything else (table, form,
  sheet, JSON shape, command arguments) is derived from that declaration by factories.

---

## 3. Architecture

Layered, with every layer talking to the one below it through an interface, and every concrete
implementation produced by a factory.

```
+----------------------------------------------------------------+
|  Front ends                                                    |
|   tkinter GUI (screens)     CLI     automation server (in the GUI)|
+----------------------------------------------------------------+
|  Command layer  (single entry point: Command objects)          |
|   CommandFactory -> Dispatcher -> Result                        |
+----------------------------------------------------------------+
|  Service layer  (EntityService, TransferService, JiraService)  |
+----------------------------------------------------------------+
|  Repository layer  (RepositoryFactory -> SqlRepository)        |
+----------------------------------------------------------------+
|  Storage: SQLite (default)   |  Exporters/Importers            |
|                              |   Excel, JSON                    |
+----------------------------------------------------------------+
```

- **One command path.** The GUI and the CLI build the same commands and hand them to the same
  dispatcher. There is no GUI-only logic.
- **Schema-driven factories.** `ModelFactory`, `RepositoryFactory`, `StorageFactory`,
  `CommandFactory`, `ExporterFactory`, `ImporterFactory`, `WidgetFactory`, `ThemeFactory`,
  and `ScreenFactory`.
- **Registered screens.** `build_default_screens` registers Dashboard, JIRA Live Data, Safety
  Plan, Safety Plan Matrix and Export / Import, in that order. A screen is added by registration
  there; the list is the design, not a cap (the old screen-count rule was retired on
  2026-10-27 by [jira-live-data-plan.md](jira-live-data-plan.md)). Registering another entity
  gives it a table, commands, JSON and a sheet, never a screen by itself. The test suite asserts
  the registered list in order, never a count.
- **Jira is a view, never data.** `JiraService` reads through `asi_hopper` (imported lazily) and
  the JIRA Live Data screen holds the last fetch in memory on the window; nothing from Jira is
  stored, exported or dumped, so the database keeps its one table.

---

## 4. Database

- **SQLite** file next to the application (`kletz.db`), one table for the plan plus
  `schema_migrations` and `audit_log`.
- Schema is generated from the entity declaration; new columns are added automatically.
- Every write is wrapped in a transaction and logged to `audit_log` with the actor (`gui`,
  `cli`, `python`, `script`, or whatever an agent passes).

---

## 5. Excel generation (the workbook as a view)

- `ExcelExporter` writes one sheet, `Safety Plan`, with the workbook's own headers: bold,
  frozen top row, autofilter, dropdowns for the three lookup columns.
- Export is **full regeneration**, never in-place patching. If the target file is locked,
  export writes to a timestamped sibling and reports that.
- `ExcelImporter` reads the `Safety Plan` sheet from any workbook and ignores every other
  sheet, so the original multi-sheet workbook can seed the database without being touched.
- Because the export holds only one sheet, `workbook` in `kletz.toml` must point at a file of
  its own.

---

## 6. JSON dump and load

- `dump` writes an envelope `{"schema_version", "app_version", "exported_at", "entities": {...}}`
  or, with `--entity`, `{"entity", "rows"}`.
- `load` reads the same shape back. Modes: `replace`, `merge` (upsert by id), `append`.

---

## 7. Automation

- **In-process API**: `Brain.execute` and `Brain.execute_dict`.
- **CLI**: `asi-kletz <verb> ...`, JSON `Result` on stdout, exit code 1 on failure, 3 when the
  family lock refused it (the command never ran); `--wait <seconds>` queues for the slot.
- **Script files**: `asi-kletz run steps.jsonl`.
- **Event bus**: every state change is published; the open screen refreshes. `theme.changed`
  repaints instead and `jira.live` refreshes nothing (no database row changed).
- **Jira, read only** (0.5.0): the `jira` verb (`live [--jql] [--limit]`, `comments <key>`)
  through `asi_hopper` feeds the JIRA Live Data window and its comments view; `jira live`
  publishes `jira.live`, nothing is audited or stored; `jira_live_jql` and `jira_live_autofetch`
  in `kletz.toml`. See [jira-live-data-plan.md](jira-live-data-plan.md).
- **One primary tool at a time** (decided 2026-10-27, delivered in 0.6.0): only one process of
  Kletz or its sister tool holds an open `Brain` at any moment, enforced by the family lock of
  [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md) implemented in `locks.py` (`PrimaryGuard`, `SlotLock`,
  `PrimaryToolBusy`); the CLI is refused with exit code 3 while the window is open, `--wait`
  queues for the slot, the window offers Retry / Quit, `status` reports the locks. See
  [single-instance-plan.md](single-instance-plan.md).
- **The local automation server** (delivered in 0.7.0): the window owns a loopback HTTP server
  (`automation/server.py`, `127.0.0.1`, ephemeral port, bearer token, every answer a `Result`)
  with `GET /status`, `POST /execute` (the wire format), `GET /screens`, `POST /screen`,
  `GET /events?since=<n>` (`seq` on every event) and `POST /quit`; requests reach the Tk thread
  through the main-thread handshake (`on_main`), never a dialog. The session file
  (`automation/session.py`, `%LOCALAPPDATA%\asi\kletz\session.json`, `$ASI_KLETZ_SESSION`) says
  where it is; a CLI refused by a Kletz window with a live session is **forwarded** to it (exit
  0 or 1 by the forwarded `Result`; the sister tool, a dead session or `--no-forward` stay exit
  3); the `session` verb reports or `--quit`s it without opening a `Brain`; `ASI_KLETZ_AUTOMATION=off`
  and `--no-server` turn it off. `remote_guard` refuses a remote `theme` on a dirty screen. See
  [automation-server-plan.md](automation-server-plan.md).
- Later: approval mode (behind `remote_guard`), `fill` / `submit` / `cancel` puppeting, a
  `View > Automation` submenu, long polling on `/events`.

---

## 8. Delivery

| Phase | Content | Status |
|---|---|---|
| 0.1.0 | Split from Dewey: core, transfer, CLI, four screens, themes, tests, seed from the workbook | done 2026-10-27 |
| 0.2.0 | Diagrams (asi_escher) and documents (asi_gutenberg) from the database: `diagram` and `document` verbs with catalogs, `out` / `doc_id` / `project` / `[[revision]]` in `kletz.toml`, the generation frame on the Export / Import screen, four screens still; see [escher-gutenberg-integration-plan.md](escher-gutenberg-integration-plan.md) | done 2026-10-27 |
| 0.3.0 | The family palette and the latching theme picker: `gui/palettes.py` (32 palettes, digest-checked against `ASI_FUSA_TOOLS.md`), `GridTheme`, `prefs.py`, the `theme` verb, the picker in the navigation column and `View > Theme`, default `cyan-neon`, four screens still; see [theme-palette-plan.md](theme-palette-plan.md) | done 2026-10-27 |
| 0.4.0 | Every Safety Plan column in the table: the flag-column cap removed, `id` then the 63 fields in source order, narrow check-mark flag columns headed by the source title, a `Columns` selector over `displaycolumns`, `Sorted by` in the status bar, both scrollbars as attributes; matrix, schema and transfer untouched; see [all-columns-plan.md](all-columns-plan.md) | done 2026-10-27 |
| 0.5.0 | The JIRA Live Data window and its comments view: the `asi-hopper` dependency, the `jira` verb (`live`, `comments`), `JiraService`, `jira_live_jql` / `jira_live_autofetch` in `kletz.toml`, `gui/jira_live_screen.py` registered right after the dashboard, `gui/jira_comments_window.py`, `MainWindow.run_quiet` / `open_comments`; nothing from Jira stored; the four-screen rule retired, screens registered not counted; see [jira-live-data-plan.md](jira-live-data-plan.md) | done 2026-10-27 |
| 0.6.0 | One primary tool at a time: the family lock in `locks.py` (`primary.lock`, `db-<sha1>.lock`, holder `.json`, `ASI_PRIMARY_LOCK_DIR`), `PrimaryToolBusy`, `Brain(wait=)`, `--wait` on the CLI and the window, exit code 3, the Retry / Quit dialog, lock details in `status` and the About box, the simulated-sibling and crash-release tests; one table, the registered screens unchanged; see [single-instance-plan.md](single-instance-plan.md) | done 2026-10-27 |
| 0.7.0 | The local automation server: `automation/server.py` (loopback HTTP, bearer token, the main-thread handshake, `/status` `/execute` `/screens` `/screen` `/events` `/quit`), `automation/session.py` (the session file, `pid_alive`, `probe`, `forward`), `seq` on every event, CLI forwarding to a live Kletz window with `--no-forward`, the `session` verb, the theme badge and the port in the online indicator, `remote_guard`, `--no-server` and `ASI_KLETZ_AUTOMATION=off`; one table, the registered screens unchanged; see [automation-server-plan.md](automation-server-plan.md) | done 2026-10-27 |
| 0.7.1 to 0.7.3 | Window polish: every column fitted to its text (`fit_columns`, 0.7.1); the identity columns of both Safety Plan screens frozen on the left (`FrozenPane`, 0.7.2) behind a draggable sash that opens at their fitted width but never past 45% of the window (0.7.3); the JIRA Live Data filter grid; the broken-windows sweep of the documents (0.7.3) | done 2026-10-28 |
| 0.8.0 | The Weekly Activity Tracker and sprints, phases 1 to 3 of `docs/weekly-tracker-plan.md`: entities `sprint`, `sprint_item`, `week` (schema version 2), `tracker/format.py` (the file grammar, parse and render), `TrackerService` and the `tracker` verb (import, build history / week, add), `SprintService`, `generate/sprint_queries.py` and the `sprint` verb (board, start, close, point, carry), the tracker and sprint keys in `kletz.toml`; the one-table rule retired. Screens, diagrams and the family tables are phases 4 and 5. | done 2026-10-28 (CLI and automation server; no screen yet) |
| 0.8.1 | The tracker in the window: the Dashboard's sprint strip, the Sprint Board and Weekly Status screens (`gui/sprint_board_screen.py`, `gui/tracker_screen.py`, registered after Safety Plan Matrix), the two File menu entries; phase 4 of `docs/weekly-tracker-plan.md` without the diagrams and the report. | done 2026-10-28 |
| 0.9.0 | The hidden identity: every row of every entity carries a `uid` (schema version 3), stamped on open, carried by every file, matched first by every import, accepted wherever an id is; no table shows `id` or `order`; see [hidden-identity-plan.md](hidden-identity-plan.md) | done 2026-10-28 |
| 0.10.0 | The sprint planner: the `holiday` entity and `holiday load` (schema version 4, `data/us-holidays-2026-2029.json`), `tracker/business_days.py`, `sprint plan` / `--replan`, the owner's rule (10 business days, 8 points fixed and enforced, consecutive sprints), the TIMELINE naming the next planned sprint only, the Holidays screen; see [sprint-planner-plan.md](sprint-planner-plan.md) | done 2026-10-28 |
| 0.11.0 | Points on the Safety Plan (schema version 5): `points`, the estimation panel's `default_points` (`plan weights load data/deliverable-points.json`, the record in `docs/deliverable-points.md`), the calculated `sprint` and `deadline` (`generate/plan_schedule.py`, recomputed after every change that can move them, refused by hand), the `plan` verb, the Points entry with the default as its placeholder; see [plan-points-plan.md](plan-points-plan.md) | done 2026-10-28 |
| 0.12.0 | The tracker plan's last items and the roadmap: `sprint_burndown`, `velocity` and `plan_roadmap` charts (matplotlib figures in the diagram catalog, `generate/charts.py`), the `sprint_report` and `plan_roadmap` documents, built from the scheduler's output | done 2026-10-28 |
| 0.13.0 | Sprint items point at plan rows by uid too (`sprint_item.plan_uid`, hidden, schema version 7; filled on open; the uid wins; a file's uid re-resolves the id; the scheduler pins by uid; see [hidden-identity-plan.md](hidden-identity-plan.md) open question 1), continuous integration (`.github/workflows/ci.yml`), the lock in step with the version | done 2026-10-28 |
| 0.14.0 | Standards and export (schema version 8): `jira_key` on the plan row, the `parameter` entity and screen, `standards_dir`, `services/standards_service.py`, the `standards` verb, `plan export` / `plan parameters` through asi_gutenberg's parameters, the standards pane at the top of the Safety Plan's details | done 2026-10-29 |
| 0.15.0 | The exported points are the weight the schedule used (chosen, else the default; neither stays unfilled); a Jira ticket picker on every work product (`JiraPickerWidget`, `FieldSpec.picker`, Load tickets through the live screen's fetch path, `TicketLoader`); `plan tickets` | done 2026-10-29 |
| 0.15.1 to 0.15.3 | A plan out of phase order paints whole (`pdp:2#2`, 0.15.1); the mouse wheel over a combobox never picks a value (0.15.2); the broken-windows sweep (0.15.3) | done 2026-10-29 |
| 0.16.0, 0.16.1 | The export writes the Word original filled in place (asi_gutenberg 0.7.0 `fill_docx`, `Standard.template`, `exact`), the PDF Word's own print; a failed print keeps Gutenberg's PDF (0.16.1) | done 2026-10-29 |
| 0.17.0 | The Word original filled with green marks; `row_N_jira_key` stacked over the status | done 2026-10-29 |
| 0.18.0, 0.18.1 | Sprints on the owner's law (Tuesday to Monday, 14 days, Sprint 31 = 2026-10-27, 8 points): the cadence guard, `sprint plan` in fortnights, `sprint align`; `sprint_days` ignored; `gui.log` and `faulthandler` (0.18.1) | done 2026-10-29 |
| 0.19.0 | The people of a role: `parameter.people` (schema version 9), `schema/people.py`, the two editors one person per line | done 2026-10-29 |
| 0.20.0 | Work product URLs per deliverable (`safety_plan_row.urls`, schema version 10), `schema/urls.py`, the Outlook Look up (`people lookup`), `plan urls --placeholder`, the Work product columns of the export | done 2026-10-29 |
| 0.21.0 | The deliverable's name a hyperlink in the exported QF-17 and the Excel sheet; `abridged-headers.json` wired into the Word print | done 2026-10-29 |
| 0.22.0 | URL kinds (`schema/urls.py:url_kind`, `[urls] hosts`), `plan urls --audit` and `--replace`; Phase A of asi_hopper's Confluence integration plan | done 2026-10-29 |
| 0.23.0 | Confluence read only through Hopper: the `confluence` verb (search, page, link, evidence, check), `evidence_dir`, `[confluence] space`, the Find page window, the Work product links tiles; Phase B | done 2026-10-29 |
| 0.24.0 | STPA moves to Kletz (schema version 11): the thirteen control-structure and STPA entities, the rules, the two factories (`stpa/`), the `cs` and `stpa` verbs, the two screens, the STPA tiles, `control_structures_dir`; see [control-structure-plan.md](control-structure-plan.md) | done 2026-10-29 |
| 0.24.1 | The end-of-day sweep: two uncalled functions gone, `lists.typed_items` shared by the people and URL readers, the documents put straight | done 2026-10-29 |
| 0.24.2 | The lock follows the siblings: asi_escher 0.2.2 and asi_gutenberg 0.9.1 (the family sweep's pass two); no code change | done 2026-10-29 |
| 0.24.3 | The people in the fixtures, the tests and the examples are invented (the house rule: no real person in a public repository; the owner's decision of 2026-10-29); no code change | done 2026-10-29 |
| later | Approval mode, form puppeting, import diff preview, date picker | planned |

---

## 9. Change log

- 2026-10-29 0.24.1: the status line (0.15.3 to 0.24.1) and the section 8 rows for 0.15.1 to 0.24.1, which the day's releases had not added.
- 2026-10-29 0.24.2: the status line and the section 8 row for 0.24.2, the lock on the siblings.
- 2026-10-29 0.24.3: the status line and the section 8 row for 0.24.3, the invented people.
- 2026-10-28 0.8.1: the section 8 row for the tracker screens and the dashboard strip.
- 2026-10-28 0.10.0: the section 8 rows for the hidden identity (0.9.0) and the sprint planner (0.10.0).
- 2026-10-28 0.11.0: the section 8 row for the points and the calculated sprint and deadline.
- 2026-10-28 0.12.0: the section 8 row for the charts, the sprint report and the roadmap.
- 2026-10-28 0.13.0: the section 8 row for plan_uid and continuous integration.
- 2026-10-29 0.14.0: the section 8 row for the standards and the export.
- 2026-10-29 0.15.0: the section 8 row for the points rule and the Jira ticket picker.
- 2026-10-29 0.15.3: the status line, which had said "0.7.3 delivered" since the 0.7.3 sweep while section 8 went on to 0.15.0.
- 2026-10-28 0.8.0: the section 8 row for the Weekly Activity Tracker and sprints (phases 1 to 3); section 4's "one table" is history as of this version, the registered list is the design.
- 2026-10-28 0.7.3: status line and the section 8 row for the three patch releases (fitted columns, frozen identity columns, the draggable split, the sweep).
- 2026-10-27 0.7: section 3 (the automation server lives in the GUI front end), section 7 (the server, the session file, forwarding, the `session` verb delivered) and section 8 row for the automation server (0.7.0); approval mode and form puppeting are the next row.
- 2026-10-27 0.6: section 7 (exit code 3, `--wait`, the family lock delivered) and section 8 row for the family lock (0.6.0); the automation server becomes the next row (0.7.0).
- 2026-10-27 0.5: sections 1 and 3 (screens registered, not counted; Jira a view, never data), section 7 (the `jira` verb), section 8 row for the JIRA Live Data window (0.5.0); the family lock moves to 0.6.0.
- 2026-10-27 0.4: section 2 note (the table shows every column) and section 8 row for the all-columns table (0.4.0).
- 2026-10-27 0.3: section 8 row for the family palette and the theme picker (0.3.0); the family lock moves to the next row.
- 2026-10-27 0.2: section 8 row for the asi_escher / asi_gutenberg integration.
- 2026-10-27 0.1: written at the split from ASI Dewey.
