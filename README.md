# ASI Kletz

One of the [ASI FuSa tools](https://github.com/c00289/c00289/blob/main/README.md) by Roy Mendoza; the master README there lists every sibling.

A functional-safety (FuSa) safety-plan tool for the Wheel Loader programme, with a command
line and a tkinter desktop window on top. Version **0.13.0**, alpha. Named after Trevor Kletz,
who taught industry to ask of every line of a plan what could go wrong.

The idea, in one sentence: a database is the single source of truth, the Excel workbook is a
generated *view* of it, and everything a human can do through a front end an AI agent can do
through the same commands.

ASI Kletz holds the **Safety Plan**: one row per deliverable, with its lifecycle phase, where the
work product lives, which QMS documents it references, who authors, verifies, and reviews it, its
deadline and its status. Since 0.8.0 it also holds the engineer's **Weekly Activity Tracker**: the
sprints (ten points each), the sprint items and the weeks of the status text, and it writes that
text back out, whole or for the current week (see [Weekly Activity Tracker](#weekly-activity-tracker)).
Entities are registered in `schema/definitions.py`; the list is the design, not a cap.
Since 0.2.0 it also draws that plan with asi_escher and prints it with asi_gutenberg, from the
same database, through the same commands (see [Diagrams and documents](#diagrams-and-documents)).
Since 0.5.0 it also shows Jira, live and read only, without storing any of it (see
[JIRA Live Data](#jira-live-data)). Since 0.6.0 only one primary tool runs at a time (see
[One at a time](#one-at-a-time)). Since 0.7.0 a running window can be driven by an agent, or by
the CLI, through its local automation server (see [Automation](#automation)).

## What is in 0.13.0

**A sprint item points at its plan row by uid too** (`docs/hidden-identity-plan.md`, open question 1; schema
version 7). `sprint_item.plan_uid`, hidden, sits beside `plan_row`: given one, the sprint service sets the
other (the uid wins when both are given and disagree, with a warning; an unknown uid or id is refused by
hand); a JSON or workbook load of items keeps the file's `plan_uid` and re-resolves `plan_row` from it, so a
tracker dump survives a plan re-import that renumbered the rows (an item whose uid no row carries any more
is left without a row, with a warning, never with a stale number); the first time 0.13.0 opens a database it
fills `plan_uid` from `plan_row` on every item that has the one and not the other, audited once; the
scheduler pins and commits by uid; the tracker import carries both; the board's form keeps showing the row
id as the handle. **Continuous integration**: `.github/workflows/ci.yml` runs ruff and the full suite on
Windows (the GUI tests included) on every push to `main`, every `v*` tag and every pull request, with the
sibling tools checked out beside the repo; `uv.lock` is in step with `pyproject.toml` again.

## What is in 0.12.0

**The sprint charts, the sprint report and the roadmap** (the last open items of `docs/weekly-tracker-plan.md`,
plus the roadmap). Three charts join the diagram catalog (`generate/charts.py`, drawn with matplotlib, the
plotting library asi_escher brings, because asi_escher draws graphs and not charts): **`sprint_burndown`**
(`--param sprint=n`, default the active sprint: points remaining per business day from the sprint's items, a
Done item burning on its `done_on`, the ideal line from the capacity to zero, weekends and holidays as gaps),
**`velocity`** (one bar per Closed sprint, the three-sprint mean as a line) and **`plan_roadmap`** (the
deliverables in plan order against the sprint chain, one mark per sprint a deliverable occupies, the finishing
sprint emphasised, holidays marked on the sprint axis). Two documents join the document catalog:
**`sprint_report`** (one sprint: its facts and goal, the board table, the burndown and velocity, the carried
items, the holidays inside it) and **`plan_roadmap`** (for the tech lead and the team: the sprint rule, the
totals and the completion sprint and date, one table per lifecycle phase, the roadmap chart, the rows the
chain does not reach, a holidays appendix). Both the chart and the document read the scheduler
(`generate/plan_schedule.py`, which now also reports the sprints a deliverable occupies), never a second
computation. A chart writes PNG and SVG; `diagram` says so when asked for `dot` or `mmd`. No schema change.

## What is in 0.11.4

**A deliverable's own sprint items are the committed part of its weight** (open question 1 of
`docs/plan-points-plan.md`, answered by the owner on 2026-10-28). The scheduler subtracts from a
deliverable's points the points of its own sprint items (any sprint, any status but Carried; an
unpointed item subtracts nothing), pours the remainder from the last sprint holding one of its items
onward, and counts the items' points against their sprints' capacity once, as any committed item's; a
fully committed deliverable finishes where its last item is. A 7-point deliverable with a 4-point item
in Sprint 3 now finishes in Sprint 3, not a sprint late. `plan schedule` prints the committed points
beside the weight. No schema change.

## What is in 0.11.3

The **Safety Plan screen is one table again**: the owner's call of 2026-10-28, since the scrolling
block of 53 flag columns was redundant with the Safety Plan Matrix. The table shows the plan stacked
in one column (PDP phase > lifecycle phase > deliverable) and, beside it, every other non-flag field:
points, default points, sprint, sprint start, sprint end, location, reference, author, gate reviewer,
deadline, status; one vertical bar, one horizontal bar, no sash, no Columns box. The form below still
edits every field, flags included, and the Matrix keeps its frozen split for the flags. Nothing of the
data or the files changed.

## What is in 0.11.2

Two more calculated columns on the Safety Plan, right of Sprint: **Sprint start** and **Sprint end**,
the dates of the sprint in which the deliverable's last point lands, written by the same recompute as
Sprint and the deadline (schema version 6; a database from 0.11.x gains the columns and a first
recompute on open). Read-only in the form, carried by the workbook and the JSON, ignored by an import
like the other calculated fields.

## What is in 0.11.1

**Refresh signs you in.** When a Refresh on the JIRA Live Data screen meets a rejected Atlassian
session, the window no longer tells you to run a command: it clears the stale session, runs the
sign-in itself on the worker thread (the browser opens for your approval), and then fetches. One
sign-in per Refresh; a second rejection shows Offline as before, and the opt-in first-show fetch
never opens a browser. The same door on the command line is `asi-kletz jira login`. Needs
asi_hopper 0.1.5.

## What is in 0.11.0

**Points on the Safety Plan, and a calculated sprint and deadline** (`docs/plan-points-plan.md`, the owner's
ask of 2026-10-28; schema version 5). Three fields after the deliverable: **Points** (the weight in sprint
points, editable, a deliverable may span sprints), **Default points** (the estimation panel's consensus, set
by `plan weights load data/deliverable-points.json`, see [Where the defaults came from](#where-the-defaults-came-from))
and **Sprint** (calculated: the sprint in which the deliverable's last point lands); **Expected
Duration/Deadline** keeps its name and header but is calculated now, the end date of that sprint. The
scheduler (`generate/plan_schedule.py`, pure) walks the plan in plan order from the Active sprint, pours each
deliverable's weight (points, else the default, else `default_points` in `kletz.toml`, 2) into successive
sprints at 8 points each minus the sprint's committed items, never finishes a deliverable before the sprint
that holds its sprint item, leaves Done rows alone and gives Blocked, Alternative and Out-of-Scope rows
nothing; when the chain runs out the row has no deadline and the tool says so. The recompute runs after
every change that can move the answer (a plan row, a sprint, a sprint item, a close, a plan, a holiday load)
and once on open; `update --set deadline=` or `sprint=` is refused. `plan schedule` prints the table. The
form's Points entry shows the row's default greyed while empty and says `default 3` the moment the typed
value differs; Default points, Sprint and Deadline are read-only, copyable. The workbook carries the four
columns; the import takes points and defaults and recalculates the rest, warning once when a file disagrees.

## What is in 0.10.0

**The sprint planner, holidays and the capacity rule** (`docs/sprint-planner-plan.md`, the owner's rule of
2026-10-28, quoted in [Sprints](#sprints); schema version 4). A `holiday` entity (date, name, status
`assumed` / `confirmed`, note) with the CRUD verbs, a `Holidays` sheet, a **Holidays** screen after Weekly
Status and `holiday load <file>`, which upserts a JSON list by date and name;
`data/us-holidays-2026-2029.json` seeds it with 52 weekday holidays. `tracker/business_days.py` counts
business days (Monday to Friday, holidays skipped). **`sprint plan`** extends the chain with empty Planned
sprints to a horizon (`--until`, else three years after the last started sprint): each starts on the first
business day after the previous end and ends on its tenth business day, so a sprint with a holiday in it
spans one more calendar day and says so in its goal (`Holidays: Christmas Day (12/25)`); a second run adds
only what is missing; `--replan` moves the planned dates again when holidays become real, never a started
or closed sprint. **Capacity is the rule, 8, fixed**: `sprint_capacity` in `kletz.toml` is ignored with a
warning, `--capacity` is gone, a sprint that is not Closed cannot be created or edited with another value,
and the first time 0.10.0 opens a database it sets 8 on every such sprint, audited once; a Closed sprint
keeps its stored capacity as history. `sprint_days` now means business days (10). The tracker's
`TIMELINE` names the next planned sprint only and an empty planned sprint prints no block.

## What is in 0.9.1

The frozen left pane of the **Safety Plan** and of the **Safety Plan Matrix** opens as wide as the
longest row it holds (the stacked plan column, fitted by `fit_columns`), the owner's request of
2026-10-28; the 45% cap of 0.7.3 is gone. The one guard left is that the scrolling pane keeps
`RIGHT_MIN` (120 px) of the window, so the flags never vanish; the sash can still be dragged either
way. `gui/screens.py:FrozenPane._place_sash`. No schema change.

## What is in 0.9.0

**Every row has a hidden identity, and no table shows `id` or `order`** (`docs/hidden-identity-plan.md`,
the owner's ask of 2026-10-28; schema version 3). Each row of the four entities carries a `uid`, a
lowercase UUID4, assigned once when the row is created and never changed: it has no column on any
screen and no widget in any form, but every file the tool writes carries it (the JSON dump as a key,
the workbook as the last column of every sheet, headed `uid` and hidden) and every import honours it:
a row whose `uid` is already in the table is an update of that row, whatever its `id` in the file, so a
dump whose ids were renumbered merges as updates, not inserts, and a 0.8.x file without uids still
imports. A 0.8.x `kletz.db` opens as 0.9.0 with the column and a unique index added to every table and
every row stamped (`Storage.stamp_uids`, audited per table with the count), nothing else changed. The
integer `id` stays the handle: every command takes it, and now takes a uid in its place
(`get safety_plan_row 3f2504e0-...`); `update ... --set uid=...` is refused (`uid is immutable`).
On the screens the vestigial columns are gone: the Safety Plan table and the Safety Plan Matrix freeze
the stacked `plan` column alone, the dashboard's open deliverables lose `order` (they stay in plan
order), `order` stays a field of the form and the default sort, and the details frame names the
selected row (`Safety Plan Row details · row 2`), so the handle a command needs is on screen without a
column. The audit table keeps `entity_id`: it is the trace, not a vestige.

## What is in 0.8.4

The **Safety Plan table is stacked too**, the same way as the matrix in 0.8.3: its frozen columns
are `id`, `order` and the one stacked column (PDP phase, lifecycle phase indented under it, the
deliverable under that), while the three data columns stay on the table hidden, so a hidden cell
still answers and the form, the sort and the Columns box work as before. A phase row is a heading,
not a record: selecting it leaves the form alone. Sorting by any heading reorders the deliverables
and the stack follows that order; the stacked heading, on either side, is the way back to the
plan's own order. The stacking code is shared by the two screens (`gui/screens.py`). No schema change.

## What is in 0.8.3

The **Safety Plan Matrix is stacked**: the PDP phase, the safety lifecycle phase and the safety
deliverable were three frozen columns side by side and the screen was crowded; they are now one
column read top down, a PDP phase row, its lifecycle phase rows indented under it, their
deliverables indented under those, in the plan's own order. Group rows carry the theme's primary
and accent colours in the heading font and no flags; a click on one toggles nothing. The search
keeps every matching deliverable with the two group rows above it. `order` stays as the first
frozen column. No schema change.

## What is in 0.8.2

Two sprints, numbered across the programme, and nothing else: **Sprint 1** is 10/12 to 10/27 (Phase
2, closed 10/27) and **Sprint 2** is 10/27 to 11/10 (Phase 3, active). The period 10/12 to 10/27
was imported as `FINAL SPRINTS`, as if the HARA phase had had sprints of its own; the owner's rule
of 2026-10-28 is that one dated interval is one sprint, so the sprint rows, the week texts that
name the sprint and the tracker text now say `SPRINT 1` and `SPRINT 2`. The closed bullet of the
`TIMELINE` prints as `Sprint 1: 10/12 - 10/27/2026. Closed 10/27.`, the same shape as the open
and planned bullets. No schema change.

## What is in 0.8.1

The tracker in the window (phase 4 of `docs/weekly-tracker-plan.md`): a **sprint strip on the
Dashboard** (sprint, committed / capacity, done, to go, unpointed, days left, velocity; a click
opens the board), the **Sprint Board** screen (sprint picker, the capacity bar and the warnings,
three lanes To Do / In Progress / Done, a form for the selected item, Start, Close, Carry, Build
week / history) and the **Weekly Status** screen (week picker, the Note line, the Outcomes and
Issues panes saved per pane, the Jira section as it will print, New week, Build week / history,
Open). Both screens are registered after Safety Plan Matrix; File gains `Build current week
(tracker)` and `Build tracker history`. No diagram or report yet.

## What is in 0.8.0

The Weekly Activity Tracker and sprints, phases 1 to 3 of `docs/weekly-tracker-plan.md`: three new
entities (`sprint`, `sprint_item`, `week`; schema version 2), the `tracker` verb (`import` the
engineer's status text once, `build history` and `build week` to write it back, `add` a line), the
`sprint` verb (`board`, `start`, `close`, `point`, `carry`), the tracker and sprint keys in
`kletz.toml`. The file the engineer kept by hand is the specification: an import followed by a
history build gives it back line for line. The one-table rule is retired: the registered list is the
design. Phase 4, the screens, followed in 0.8.1.

## What is in 0.7.4

Everything of 0.7.3 plus two fixes to the JIRA Live Data window after the owner's report that the
sister tool "got stuck on jira live data": **the window never connects to Jira on its own**
(`jira_live_autofetch` now defaults to `false`; the first show paints `No fetch yet · press
Refresh` and waits) and **a fetch no longer freezes the window**: `jira live` and `jira comments`
run on a worker thread through `MainWindow.execute_quiet`, the Tk thread polls and paints the
Result, the Refresh button is disabled and the status line says `Fetching Jira … up to 2000
issues, this can take a minute` meanwhile. A theme pick or closing the window during a fetch
never waits for Jira; the late Result is dropped.

## What is in 0.7.3

Everything of 0.7.2 plus a **draggable split** on both Safety Plan screens: the pinned and the
scrolling tables are the two panes of a horizontal `ttk.PanedWindow`, the sash opens at the fitted
width of the pinned columns (since 0.9.1 in full, the longest row of the left pane; the scrolling pane keeps 120 px), and dragging it either way clips a
table without changing a column width. The rest is a broken-windows sweep (see the CHANGELOG):
stale "four screens" wording in the plan documents, the missing compare links, `session` in the
command list below, `uv.lock` no longer matched by the lock-file ignore pattern.

## What is in 0.7.2

Everything of 0.7.1 plus **frozen identity columns**: on the Safety Plan table `id`, `order`, the
PDP phase, the lifecycle phase and Safety Deliverables stay put while the other 59 columns scroll
sideways, and the Safety Plan Matrix pins its four identity columns the same way
(`gui/screens.py:FrozenPane`, two trees in lock-step). The JIRA Live Data filters sit in a
three-column grid that fits any window width.

## What is in 0.7.1

Everything of 0.7.0 plus **fitted columns**: every column of every table is as wide as the longest
string in its domain (heading, cells and, for an enum field, every value of its lookup), measured in
pixels with the real fonts after each fill (`gui/screens.py:fit_columns`); the 36 px flag columns
are gone.

## What is in 0.7.0

Everything of 0.6.0 plus the **local automation server**: the window serves JSON over
`127.0.0.1` on an ephemeral port, writes a session file saying where, and the CLI, refused by
the family lock while that window is open, forwards the command to it instead of exiting 3. So
`asi-kletz theme pink-noir` from another console recolours the open window, `asi-kletz update`
edits the row on screen, and an agent can `/execute` any verb, show a screen, poll the events
and quit the window. A theme badge joins the online indicator (which now shows the port) in the
status bar. Nothing else changed: one table, the registered screens, schema version 1.

## What is in 0.6.0

Everything of 0.5.0 plus the **family lock**: at most one process of Kletz or its sister tool
holds an open `Brain` at any moment, so the Safety Plan has exactly one writer and the audit log
never shows two front ends interleaving. A second start is refused with exit code 3 and a line
naming the holder, `--wait <seconds>` queues for the slot, the window offers Retry / Quit, and
`status` reports the locks. Nothing else changed: one table, the registered screens, schema
version 1.

## What is in 0.5.0

Everything of 0.4.0 plus the **JIRA Live Data** window right below the dashboard: one Refresh
button, a table of every issue of the project past and present with local filters, a
`[Comments]` button on every row that opens the ticket's comment history newest first, and the
`jira` verb (`live`, `comments`) behind both, through `asi_hopper`. Nothing from Jira is stored:
the last fetch lives on the window for the session, the database still has one table. The old
screen-count rule is retired: screens are registered in `gui/screens.py`; the list is the
design, not a cap.

## What is in 0.4.0

Everything of 0.3.0 plus **every column of the source sheet in the Safety Plan table**: `id`
first, then the 63 columns in source order, flags as narrow check-mark columns headed by the
source title, a `Columns` box that narrows the flags to one group without rebuilding the table,
and a `Sorted by` status line that names a clipped heading. Until 0.3.0 the table stopped at
`Work Product Location`: a cap on flag columns hid all 53 flags, DMS, JAMA and Sharepoint
first. The form, the matrix screen, the schema, the storage and the workbook round trip are
unchanged. Screens are registered in `gui/screens.py`; the list is the design, not a cap.

## What is in 0.3.0

Everything of 0.2.0 plus the family palette and a latching theme picker (see [Themes](#themes)).
The house default stays the original look, now named `cyan-neon`; `tron` still works as an alias.

## What is in 0.2.0

Everything of 0.1.0 plus diagrams and documents (see Diagrams and documents).

## What is in 0.1.0

- **One entity**, `safety_plan_row`, declared once in `asi_kletz/schema/definitions.py` and
  seeded from the `Safety Plan` sheet of the workbook: 63 columns, including the location,
  reference, author, verification, and reviewer flag groups. Three lookups: `pdp_phase`,
  `lifecycle_phase`, `plan_status`.
- **The window** (`asi-kletz gui` or `asi-kletz-gui`), navigation on the left, one screen at
  a time on the right. Screens are registered in `gui/screens.py`; the list is the design, not a
  cap (0.5.0 added JIRA Live Data second). The four of 0.1.0:
  - **Dashboard**: deliverable counts by status, deliverables per lifecycle phase, the open
    deliverables, recent changes.
  - **Safety Plan**: sortable, searchable table of every column of the source sheet in source
    order (flags as check-mark columns headed by the source title; a `Columns` box narrows the
    flags to one group; a clicked heading is named in the status bar) with a form below; flag
    groups rendered as checkbox grids; New / Save / Delete / Duplicate / Refresh. Since 0.11.0 the
    table and the form carry **Points** (editable: the row's default greyed as the placeholder while
    empty, a `default n` caption the moment the value differs, clearing returns to the default),
    **Default points** (the estimation panel's, read-only), **Sprint** and **Expected
    Duration/Deadline** (calculated, read-only: where the deliverable's last point lands and that
    sprint's end). Since 0.9.0 no
    table shows `id`, `order` or the hidden `uid`: the id is in the details frame's title
    (`Safety Plan Row details · row 2`) and the status bar, `order` is a field of the form and the
    default sort. Since 0.7.2 the identity column stays put while the rest scrolls sideways (since
    0.8.4 it is the plan stacked as PDP phase > safety lifecycle phase > safety deliverable in one
    column, `plan`): a Treeview cannot pin a column, so the table is two of them in lock-step
    (`gui/screens.py:FrozenPane`: one vertical bar, the selection, the striping and the sort
    shared; a heading on either side sorts). Since 0.7.3 the split between the two is a sash you
    can drag: it opens at the pinned columns' full fitted width, the longest row of the left pane
    (since 0.9.1; before, never past 45% of the window; the scrolling pane keeps 120 px), and
    dragging it never changes a column width.
  - **Safety Plan Matrix**: the plan stacked as PDP phase > safety lifecycle phase > safety
    deliverable (one column, indented, since 0.8.3; alone on the left since 0.9.0), one flag group
    as columns, click a flag cell to toggle it (location, reference, author, verification,
    reviewer); the frozen column stays put the same way while the flags scroll, and the search box
    still finds a row by its `order`.
  - Since 0.7.1 every column of every table (these two, the dashboard, JIRA Live Data) is as
    wide as the longest string in its domain: heading, cells and, for an enum field, every
    value of its lookup, measured in pixels with the real fonts after each fill, so nothing is
    clipped and the 36 px flag columns are gone.
  - **Export / Import**: workbook export and import with mode, JSON dump and load, result log.
  Ctrl+N new, Ctrl+S save, Ctrl+E export workbook, F5 refresh. The window only ever calls
  `Brain.execute` with actor `gui`, so the audit log records it like any other actor, and the
  event bus refreshes the open screen when the CLI or an agent changes data on the same Brain.
- **Themes** from a `ThemeFactory`: the 32 palettes of the family palette (dark grids with neon
  light lines, a geometric heading face and a monospace status line, or the same grid in
  daylight), plus `plain` for the native look. Since 0.3.0 the window has a picker that
  latches the choice; see [Themes](#themes).
- **SQLite storage** generated from the schema, with automatic column migration, a schema
  fingerprint table, and an **audit log** that records who did what.
- **One command path**: `list`, `get`, `create`, `update`, `delete`, `count`, `schema`,
  `status`, `dump`, `load`, `export`, `import`, `run`, `gui` (since 0.2.0 `diagram` and
  `document`, since 0.3.0 `theme`, since 0.5.0 `jira`, since 0.7.0 `session`). Every command returns a structured
  `Result` (`ok`, `data`, `errors`, `warnings`) that serialises to JSON.
- **JSON dump and load** with `replace`, `merge`, and `append` modes.
- **Excel export** that regenerates the workbook (one sheet, bold headers, frozen row,
  autofilter, dropdowns from lookups) and **Excel import** that reads the `Safety Plan` sheet
  back, ignoring any other sheet in the file, so the original workbook can seed the database.
- **Event bus** so the window refreshes live, and a **script runner** that replays a `.jsonl`
  of commands.
- Factories and registries everywhere: `SchemaRegistry`, `ModelFactory`, `StorageFactory`,
  `RepositoryFactory`, `CommandFactory`, `ExporterFactory`, `ImporterFactory`, `ScreenFactory`,
  `WidgetFactory`, `ThemeFactory`.

ASI Kletz is a sister of asi_gutenberg, asi_escher, asi_hopper and asi_dewey (see
[ASI_FUSA_TOOLS.md](../asi_fusa_tools/ASI_FUSA_TOOLS.md)). It uses the two generators and the Jira door as libraries and
shares no code, data, database, workbook, configuration, or environment variable with its sister
tool.

## Diagrams and documents

The database is the truth; a diagram or a document is a *view* of it, regenerated on demand and
never read back, exactly like the workbook. Two verbs, one catalog each:

```powershell
asi-kletz diagram                                    # catalog: key, title, description, params
asi-kletz diagram lifecycle_overview --out out       # out/lifecycle_overview.{png,svg,dot,mmd}
asi-kletz diagram phase_flow --param phase=3         # phase by number or by its full lookup value
asi-kletz diagram status_board --formats png,mmd --dpi 200
asi-kletz document                                   # catalog
asi-kletz document safety_plan --out out             # out/safety_plan.{md,pdf,docx} + out/figures/*.png
```

| Diagram | Draws |
|---|---|
| `lifecycle_overview` | the ten lifecycle phases in order with deliverable counts; a phase with a Blocked row is tinted like a decision, a phase with every row Done like a state |
| `phase_flow` | one phase as an activity diagram with Author, Verification and Reviewer lanes (`--param phase=<n>` required) |
| `status_board` | one state per plan status with its count and the conventional transitions (a convention, not data) |
| `pdp_map` | a SysML block definition diagram: the Safety Plan composed of the six PDP phases, each listing its lifecycle phases |
| `sprint_burndown` | a chart: points remaining per business day of one sprint (`--param sprint=n`, default the active one), a Done item burning on its `done_on`, the ideal line from the capacity to zero, weekends and holidays as gaps |
| `velocity` | a chart: one bar per Closed sprint (points done) and the three-sprint mean as a line |
| `plan_roadmap` | a chart: the deliverables in plan order against the sprint chain from the active sprint to the last one scheduled, one mark per sprint a deliverable occupies, the finishing sprint darker, a holiday-bearing sprint starred |

| Document | Kind | Contents |
|---|---|---|
| `safety_plan` | plan, "Platform Safety Plan" | purpose, scope, lifecycle overview with its diagram, one section per lifecycle phase with a **Deliverables** table, an **Ownership** table and the phase flow diagram, appendices for roles, QMS references and the status legend |
| `status_report` | report, "Safety Plan Status" | totals by status with the status board, blocked deliverables, deliverables due within 30 days (and open ones without a parsable date), lifecycle overview, the last 20 audit entries |
| `phase_checklist` | checklist, "Safety Plan Checklist" | one task list per phase, a deliverable ticked when Done, the PDP map, totals |
| `sprint_report` | report, "Sprint Report" (`--param sprint=n`, default the active one) | the sprint's facts and goal, the board table (To Do, In Progress, Done, Carried, with points), the burndown and velocity charts, the carried items, the holidays inside the sprint |
| `plan_roadmap` | plan, "Safety Plan Roadmap" | for the tech lead and the team: the sprint rule verbatim, the totals and the completion sprint and date, one table per lifecycle phase (deliverable, points, sprint, start, end, status), the roadmap chart, the rows the chain does not reach, a holidays appendix |

Every document is written as a Markdown / PDF / Word triplet that cannot disagree (the PDF and
the Word file are rendered from the Markdown). **The reviewed artefact is the PDF**: the result's
`primary` field points at it, the window's **Open** button opens it, the Word file is a
convenience for reviewers who mark up text and the Markdown is the source. A diagram's `primary`
is the PNG. Figures inside a document are asi_escher diagrams carried as `diagram` blocks and
rendered by asi_gutenberg into `<out>/figures/`; the result's `diagrams` list has one entry per
figure. A chart (`sprint_burndown`, `velocity`, `plan_roadmap`) is a matplotlib figure: asi_escher
draws node-and-edge diagrams only, so the charts render themselves (PNG and SVG; `dot` and `mmd` are
refused or dropped with a warning) and go into a document as `figure` blocks in the same
`<out>/figures/` folder, not in the `diagrams` list. Layout issues the diagram engine had to settle
for come back as `warnings`, never as a Python warning. Both verbs write an audit entry (`generate`)
and publish `generated` on the
event bus, so the dashboard's recent changes show who generated what.

Output goes to `--out`, else `$ASI_KLETZ_OUT`, else `out` in `kletz.toml`, else `out/` next to the
database (`status` reports `out_dir`). The output stem is the catalog key (`phase_flow_3` for a
phase), so a rebuild overwrites the previous files; a locked PDF or Word file falls back to a
timestamped stem and says so in `warnings`.

The Safety Plan document's control data lives in `kletz.toml`: `doc_id` (blank warns
`kletz.toml has no doc_id` but still builds, so a draft can be previewed before the id is
assigned), `project`, and `[[revision]]` entries that become the revision table in file order,
the last `rev` going on the cover. The revision history is deliberately explicit, never derived
from the audit log: the audit log records every edit by anyone, a revision is an issue of the
controlled document. With no entries the document carries one generated line and the warning
`kletz.toml has no revisions`. The author of a generated document is the actor who asked for it
(`cli`, `gui`, `python`, or whatever an agent passes); no person is named inside the tool.

In the window, generation lives on the **Export / Import** screen, in the third frame: pick a
diagram or a document, a phase when the diagram wants one, an output folder, then **Build
diagram**, **Build document**, **Open**, **Open folder**; results go to the same log as the
workbook and JSON actions. **File > Build Safety Plan document** runs `document safety_plan`
there directly. Screens are registered in `gui/screens.py`; the list is the design, not a cap.

Adding a view is a registration, not an edit to core code:

```python
from asi_kletz.generate import Param, Spec, register_diagram, register_document
from asi_kletz.generate import plan_queries as q

@register_diagram(Spec("my_view", "My view", "What it shows", params=(Param("phase", required=True),)))
def my_view(brain, params, ctx):           # -> asi_escher.Diagram; ctx carries actor, out_dir, warnings
    ...

@register_document(Spec("my_report", "My report", "What it says"))
def my_report(brain, params, ctx):         # -> asi_gutenberg.Document; figures via figures.add_diagram
    ...
```

Builders read the plan through `brain.service("safety_plan_row")` and the helpers in
`asi_kletz.generate.plan_queries` (`rows_by_phase`, `counts_by_status`, `counts_by_phase`,
`blocked`, `due_within`, `set_flags`, ...), which the dashboard uses too, so a number on the
screen and the same number in a report cannot drift. The generator libraries (and with them
matplotlib and reportlab) are imported lazily, inside the builders: `import asi_kletz`,
`asi-kletz list` and window start-up do not load them.

## Weekly Activity Tracker

The tracker is the engineer's weekly status text: a header, a `TIMELINE`, one block per sprint
framed by `=====` rules, one `WEEK OF` block per week with `Outcomes`, `Miscellaneous issues` and
`Jira issues` sections, newest at the top. Since 0.8.0 the database holds it and the text is a
generated view, like the workbook: the file is imported once, edited through the tool from then on,
and built back out on demand.

```powershell
asi-kletz tracker import "..\Roy's Brain\Roy's status.txt"   # once; replace into an empty tracker, merge after
asi-kletz tracker build history --out out                       # out/tracker_history.txt, every sprint and week
asi-kletz tracker build week --jira                             # out/tracker_week.txt, the current week only
asi-kletz tracker add "- Mentor meeting held."                  # appended to Outcomes of the current week
asi-kletz sprint board                                          # points, days left, velocity, warnings
asi-kletz sprint point --item 3 --points 3                      # 1 to the capacity; 0 clears
asi-kletz sprint close                                          # Done counted, the rest carried, the next sprint opened
asi-kletz holiday load data/us-holidays-2026-2029.json          # the calendar the planner skips (upsert by date + name)
asi-kletz sprint plan                                           # the chain three years ahead, ten business days each
asi-kletz sprint plan --replan --until 2028-12-31               # holidays became real: move the planned dates
asi-kletz list sprint_item --filter sprint=2                    # the generic CRUD covers the entities
```

Three entities, all with the generic `list / get / create / update / delete`, a workbook sheet and a
place in a dump: a **sprint** (number, label such as `SPRINT 1`, lifecycle phase, start, end,
capacity, goal, status Planned / Active / Closed), a **sprint item** (a Deliverable of the plan by
row id, a Jira issue by key, a Meeting, a Question or Other, with points, target, note, the Jira
status line as last published, status To Do / In Progress / Done / Carried) and a **week** (one row
per section of a `WEEK OF` block: Note, Outcomes, Issues, Jira; the prose verbatim). Weeks run
Monday to Sunday.

### Where the defaults came from

The default points per deliverable are the consensus of an estimation panel that ran on 2026-10-28:
three estimator agents each weighed all 48 deliverables independently (the whole plan, the Phase 2
tracker and the Sprint 2 commitments in front of them, never each other's answers), a fourth decided
per row (the median, moved off only for a better-grounded reason, with the reason written down). The
record is `docs/deliverable-points.md` (every row's three estimates, the consensus and the reason;
174 points in all, a little under 22 sprints of the FuSa engineer's productive days) and its machine
form is `data/deliverable-points.json` (`{id, order, deliverable, points}`), which
`asi-kletz plan weights load data/deliverable-points.json` writes into `default_points`, matching rows
by uid when the file carries one, else by id. Re-running the panel is a diff against that record, not a
replacement: a changed consensus is a new row in the record and a new load.

### Sprints

The owner's sprint rule, decided 2026-10-28 (`docs/sprint-planner-plan.md`), verbatim:

> - A sprint spans 10 business days. Monday to Friday count; weekends and holidays do not, so a sprint that
>   contains a holiday ends one calendar day later per holiday. Dates move as holidays become real; the cadence
>   does not.
> - Capacity is 8 points per sprint, company policy (8 productive days of the 10). Holidays never reduce points.
> - Sprints are consecutive with no gaps, numbered across the programme (SPRINT n); the chain continues from
>   Sprint 2 (2026-10-27 to 2026-11-10). We do not know the work yet: future sprints are empty, Planned, with no
>   lifecycle phase, and will be adjusted as dates become real.
>
> Every single sprint except the one in the past is 8 points; set this as a global value that is fixed.

So: a sprint is **8 points**, fixed (`SPRINT_CAPACITY` in `schema/definitions.py`; no setting and no
option sets it; a sprint that is not Closed cannot be created or edited with another value, the tool
sets 8 on every such sprint when it opens a database written before the rule, and a Closed sprint keeps
its stored capacity as history), and **10 business days** long (`sprint_days` in `kletz.toml`; Monday to
Friday, the `holiday` table skipped). Points are integers 1 to the capacity; an unpointed item is counted
and named, never taken as zero. Over-commitment is a warning on `point` and on the board, never a
refusal. `sprint start` opens a sprint on the day given (`--start`, else `--as-of`, else today) and
ends it on its tenth business day. `sprint close` freezes the sprint's Jira section into its newest
week, marks every open item Carried, copies it into the next sprint (the planned one, or a new one
opened Active on the first business day after the closed one's end) with `carried_from` set, and
records the close date; velocity is the mean of points done over the last three closed sprints. One
sprint is Active at a time. The built text carries a generated `Sprint:` line under the sprint heading
as soon as one item is pointed, and a `Points:` line under each pointed Jira item.

**The planner.** `holiday load data/us-holidays-2026-2029.json` seeds the calendar (US federal holidays
2026 to 2029 on their observed dates, plus the day after Thanksgiving and Christmas Eve marked
`(company, assumed)`; every row `assumed` until the company confirms it: `update holiday <ref> --set
status=confirmed`). `sprint plan [--until YYYY-MM-DD | --years 3] [--days 10]` continues the chain from
the highest-numbered sprint: the next starts on the first business day after its end and ends on its
tenth business day, `SPRINT n`, no lifecycle phase, capacity 8, Planned, the goal naming the holidays it
contains (`Holidays: Christmas Eve (company, assumed) (12/24), Christmas Day (12/25)`); sprints are
added while they start on or before the horizon; an existing sprint is never touched, so a second run
adds only what is missing. `sprint plan --replan` recomputes the dates of every Planned sprint after the
active one from the holiday table as it is now (run it after holidays become real), never a started or
closed sprint, and rewrites only a goal the planner wrote. The report says how many were added and
replanned, the first and last sprint, the horizon and the holidays honoured. The `TIMELINE` of the
tracker text names the next planned sprint only (`- Phase to be assigned: planned. Sprint 3: ...`), and a
planned sprint with no weeks and no items prints no `=====` block; the Sprint Board picker lists them
all, the active one first.

In the window, the **Dashboard** carries a sprint strip under the deliverable tiles (sprint,
committed / capacity, done, to go, unpointed, days left, velocity; the frame names the sprint, its
phase and its dates; a click opens the board). The **Sprint Board** screen shows one sprint: a
picker (the active sprint first; the choice survives a theme pick), the goal, a capacity bar with
the summary and the warnings, three lanes (To Do, In Progress, Done; carried items are counted in
the status bar, not shown), and a form for the selected item with New, Save, Delete and Carry to
next sprint; the toolbar has Start sprint, Close sprint (confirmed), Build week and Build history.
Saving the form with a points value over the capacity is a warning on the summary, as on the
command line. The **Weekly Status** screen shows one week: a picker (the current week first), the
Note line, the Outcomes and Issues panes with a Save each (Issues is stored without its two-space
indent and printed with it), the Jira section as the text will print it (read-only: the items are
edited on the board; a closed sprint's week shows its frozen text), New week (today's week, in the
active sprint), Build week, Build history, Open and Open folder. Every button is a verb.

A sprint item of kind Deliverable points at its plan row twice: `plan_row`, the id (the handle on the
board and in every command), and `plan_uid`, the row's hidden uid (since 0.13.0), kept in step by the tool;
a dump or a workbook of items carries both, and a load re-resolves the id from the uid, so the tracker
survives a plan re-import that renumbered the rows.

Jira stays read only. A week's Jira section is built from the sprint's Jira items; `tracker build
--jira` runs one `jira live` for their keys and rewrites each item's title, type and status line
first, and that is the only time a Jira fact is written: it is the engineer's report line, not a
cache, never refreshed on its own and never reconciled. No Atlassian session is a warning and the
file still builds. `tracker_title`, `tracker_byline` (the person who keeps it; it belongs in the
git-ignored `kletz.toml`, never in code), `tracker_scope` and `tracker_jira_scope` are the header
lines; the import says which of them the file carries and the config does not.

## JIRA Live Data

The second screen, right below the dashboard, shows Jira: **one Refresh button and a table of
every issue of the project, past and present**, with Key, Type, Summary, Status, Category,
Priority, Assignee, Reporter, Labels, Parent, Created, Updated, Due and Resolution, sortable on
any heading (keys numerically, dates on the full timestamp, blanks last), striped, done rows
dimmed, the summary taking the room that is left. A **Find** box (key or summary) and read-only
drop-downs for Status, Category, Type, Priority and Assignee narrow the table locally, on the
last fetch, so a filter never costs a Jira call; **Clear filters** restores the server's order.
Since 0.7.2 the filters sit in a three-column grid that fits any window width (find, status,
category / type, priority, assignee / Clear filters and the count) instead of one row that
clipped at the right edge.
Double-click or Enter opens the issue in the browser. The window never changes Jira and **never
stores what it shows**: the last fetch lives on the window object for the session (a theme pick
repaints it without a second round trip), nothing from Jira enters `kletz.db`, the workbook or a
dump; nothing from Jira enters a table of its own.

Since 0.7.4 the screen **never connects on its own**: its first show says `No fetch yet · press
Refresh` and does nothing else unless `kletz.toml` says `jira_live_autofetch = true`. And a
fetch **never freezes the window**: Refresh starts `jira live` on a worker thread (through
`MainWindow.execute_quiet`, `Brain.execute` and nothing else), the Tk thread polls it and paints
the Result when it lands; meanwhile the button is disabled, a second Refresh is ignored and the
status line says `Fetching Jira … up to 2000 issues, this can take a minute`. A theme pick or
closing the window mid-fetch waits for nothing; the late Result is dropped. Before 0.7.4 the fetch
ran on the Tk thread, so a 2,000-issue fetch at 50 a page, or a gateway wait, froze the window
for as long as it took.

The first column is **`[Comments]`**, a per-row button: a click there (or `c` on the focused
row) opens the ticket's comments in a window of its own, `<KEY> — Comments`, newest at the top
and oldest at the bottom, each with its author, its time and its `edited` time when that differs,
the body selectable for copying into a review. One window per ticket, several open side by side,
Refresh and Close (or F5 and Escape) in each; a theme pick or closing the main window closes
them all.

Both are fed by the `jira` verb through asi_hopper, read only:

```powershell
asi-kletz jira live                                       # house JQL or jira_live_jql, limit 2000
asi-kletz jira live --jql "project = HWL AND type = Bug"  # one-off JQL
asi-kletz jira live --limit 300                           # cap the fetch; `truncated` and a warning say so
asi-kletz --compact jira live | jq '.data.issues[] | .key'
asi-kletz jira comments HWL-2572                          # the comment history, newest first
```

`jira live` returns `{jql, fetched_at, count, truncated, issues}` with one row per issue
(`key`, `issue_type`, `summary`, `status`, `status_category`, `resolution`, `priority`,
`assignee`, `reporter`, `labels`, `components`, `parent_key`, `created`, `updated`, `due`,
`url`; strings or `null`, the two lists always lists) and publishes `jira.live` on the event bus:
that is the trace, nothing is audited, a read is not a change to the plan. `jira comments`
returns `{key, summary, url, status, fetched_at, count, comments: [{id, author, created,
updated, body}]}` and publishes nothing. The JQL is `--jql`, else `jira_live_jql` in
`kletz.toml`, else `project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC`; the window fetches only on Refresh
unless `jira_live_autofetch = true`, which makes the first show in a session fetch once (opt-in
since 0.7.4; it was the default before). A rejected Atlassian session on a Refresh you pressed
becomes a sign-in (since 0.11.1): the stored session is cleared, the browser opens for your
approval, the status line says `Signing in to Atlassian …`, and the fetch follows; one sign-in per
Refresh, a second rejection says `Offline` until the next Refresh, and the first-show fetch never
opens a browser. `asi-kletz jira login` does the same from the command line.

Kletz ships no `hopper.toml`: asi_hopper reads `$ASI_HOPPER_CONFIG`, else `./hopper.toml`. The
recommended setup is one `hopper.toml` in the `asi_hopper` folder, named by `ASI_HOPPER_CONFIG`
and shared by every tool, so one `asi-hopper auth login` serves all. The same window (key
`jira_live`, title `JIRA Live Data`, verbs, columns, filters, comments window) exists in the
sister tool under the same convention; shared as a convention, never as code.

## One at a time

Decided 2026-10-27 and enforced from 0.6.0: **at most one primary tool runs at a time**, and the
same tool never runs twice. "Runs" means holds an open `Brain`: the CLI for one command, the
window for its session, a Python caller between `Brain(...)` and `close()`. One process may hold
several `Brain` objects (the test suite does); the slot is released when the last one closes.

How it works, by the convention in `ASI_FUSA_TOOLS.md` that both primary tools implement on their own:

- Lock directory: `$ASI_PRIMARY_LOCK_DIR` if set, else `%LOCALAPPDATA%\asi\locks` on Windows
  (`$XDG_STATE_HOME/asi/locks` or `~/.local/state/asi/locks` elsewhere). Created on demand, never
  inside a repo or a OneDrive folder, and the one environment variable the primary tools share.
- `primary.lock` is the family slot (a primary tool is running); `db-<sha1>.lock` is the database
  slot (that database is open; `:memory:` takes none). Each is a non-blocking OS advisory lock on
  byte 0 that the OS drops when the process ends, so a crash never leaves a stale lock. Beside
  each, `primary.json` / `db-<sha1>.json` says who holds it (`tool`, `version`, `pid`,
  `started_at`, `db`, `cwd`, `host`, `user`); informational, the lock is the truth.
- Family slot first, then database slot; a failed database slot releases the family slot.

What you see:

```powershell
asi-kletz status            # while the window is open: exit code 3 and
# {"ok": false, "verb": "status", "data": {"slot": "family", "holder": {"tool": "asi_kletz", "pid": 4321, ...}},
#  "errors": ["asi_kletz is running (pid 4321, since 2026-10-27T17:02:11Z, db C:\...\kletz.db); only one
#              primary tool may run at a time. Close it, or retry with --wait."], "warnings": []}
asi-kletz --wait 30 status  # queues up to 30 s, polling every 250 ms, then refuses the same way
asi-kletz-gui --wait 30     # the window: after the wait, a Retry / Quit dialog with the holder line
```

Exit code 1 still means "the command ran and failed"; 3 means it never ran. There is no override
flag: pointing `ASI_PRIMARY_LOCK_DIR` at a private directory is the only escape, and it is what
the test suite does. Since 0.7.0 a refusal by a **Kletz window** with a live automation session
is not the end of it: the CLI forwards the command to that window (see Automation), and the
example above is what you see with `--no-forward`, or while the window was started with
`--no-server`. Data moves between Kletz and its sister tool sequentially through files (`dump`
in one, `load` in the other); an agent that drives both runs them one after the other with
`--wait`. The lock is per user and per machine; sharing a SQLite file over OneDrive was never
supported and this does not change it.

## Automation

Since 0.7.0 every window owns a **local automation server**: loopback HTTP, JSON in, a JSON
`Result` out, the same five keys the CLI prints. It is the way an agent, or the CLI from another
console, drives a *running* session, which the family lock otherwise forbids. The convention is
in `ASI_FUSA_TOOLS.md` ("The automation session") and both primary tools implement it on their
own; nothing is shared as code.

**The session file.** After it has bound, the window writes `%LOCALAPPDATA%\asi\kletz\session.json`
(beside `prefs.json`; `$XDG_STATE_HOME/asi/kletz/session.json` elsewhere; `ASI_KLETZ_SESSION`
names another file, and the test suite points it at a temporary one):

```json
{"tool": "asi_kletz", "version": "0.7.0", "pid": 18432, "started_at": "2026-10-27T17:02:11Z",
 "host": "127.0.0.1", "port": 51234, "address": "http://127.0.0.1:51234",
 "token": "3f9c…32 hex…", "db": "C:\\…\\kletz.db"}
```

`pid` and `started_at` are the values the lock holder writes to `primary.json`. The file is
removed when the window closes; a stale one from a crash is ignored by every reader (the pid is
dead) and overwritten by the next window.

**Endpoints.** Every request carries `Authorization: Bearer <token>`; a wrong or missing token
is 401 with `errors[0] == "bad token"`, and any request with an `Origin` header (a browser) is
403 whatever its token. The HTTP status is about transport; a failed command is 200 with
`ok: false`, exactly as the CLI prints it and exits 1.

| Method and path | Body | `Result.data` |
|---|---|---|
| `GET /status` | none | `tool`, `version`, `pid`, `db`, `screen` (the open key), `theme` (`key`, `title`), `started_at`, `uptime_s`, `port`, `requests`, `events_seq`, `lock` (`family`, `database`) |
| `POST /execute` | `{"verb": "list", "args": {"entity": "safety_plan_row"}, "actor": "agent"}` | the command's own `Result`, `verb` included; `actor` defaults to `agent`, never `gui`; `{"verb": "gui"}` is refused |
| `GET /screens` | none | `{"screens": [{"key", "title", "current"}, …]}` in navigation order |
| `POST /screen` | `{"show": "safety_plan_matrix"}` | `{"screen", "title"}`; an unknown key is `ok: false` |
| `GET /events?since=<n>&limit=<m>` | none | `{"since", "seq", "events"}`: the events after sequence `n` (default 0), at most `m` (default 200); every event carries `seq`; a warning when the history (500 events) no longer reaches back to `n` |
| `POST /quit` | none | `{"quit": true}`; the window closes 100 ms after answering |

Requests run on the window's own thread (the server thread never touches a widget or the
database), so a remote `update` refreshes the open screen, a remote `theme pink-noir` repaints
the window before the answer goes back, and the audit log says `agent` (or whatever actor was
sent). Remote commands never open a dialog: a remote `theme` while the open screen has unsaved
edits is refused with `theme change refused: the <screen> screen has unsaved edits` and the
preference is not latched. A window that does not get to a request within 60 s answers 504.

```powershell
$s = Get-Content $env:LOCALAPPDATA\asi\kletz\session.json | ConvertFrom-Json
$h = @{ Authorization = "Bearer $($s.token)" }
Invoke-RestMethod "$($s.address)/status" -Headers $h
Invoke-RestMethod "$($s.address)/execute" -Headers $h -Method Post -ContentType "application/json" `
  -Body '{"verb": "theme", "args": {"key": "pink-noir"}, "actor": "agent"}'
Invoke-RestMethod "$($s.address)/screen" -Headers $h -Method Post -ContentType "application/json" -Body '{"show": "transfer"}'
Invoke-RestMethod "$($s.address)/events?since=0" -Headers $h
```

**Forwarding.** `asi-kletz <verb>` opens its own `Brain`; while a window is open the family lock
refuses it. When the refusal names a **Kletz** window (`holder.tool == "asi_kletz"`, its pid the
session file's) and that session is alive (the pid runs and `GET /status` answers as that pid
within a second), the CLI posts the command to `/execute` and prints the window's `Result`
untouched, exit 0 or 1 by its `ok`; `--actor` travels with it. Nothing marks it as forwarded: an
agent learns one dialect. Exit 3 remains for a window of the sister tool (the family forbids one
tool driving the other), a dead or missing session (with the hint `no automation session; the
window may have been started with --no-server or ASI_KLETZ_AUTOMATION=off`), and a server that
does not answer (`the automation session at http://127.0.0.1:51234 did not answer`); it is never
exit 1, because the command did not run. `--no-forward` turns the branch off, and then `--wait`
queues for the slot as before. `--db` naming another database on a forwarded call is ignored
with a warning on stderr: the window has one database.

```powershell
asi-kletz theme pink-noir          # the open window turns pink, its badge says PINK NOIR; exit 0
asi-kletz update safety_plan_row 3 --set status=Done   # the row changes on screen; exit 0
asi-kletz --no-forward status      # exit 3, as 0.6.0
asi-kletz session                  # the session file, whether the pid is alive, whether /status answers
asi-kletz session --quit           # close the window (POST /quit), wait up to 5 s for the file to go
```

`session` is the one verb that opens no database, so it works while a window holds the lock; it
prints `path`, `present`, `alive`, `reachable`, `session` (`pid`, `port`, `address`,
`started_at`, `db`; never the token), `status` (the `/status` data) and `quit`. A missing session
is `ok: true` with everything false; `--quit` with no live session is `ok: false`.

**Off switch.** `asi-kletz-gui --no-server` (or `asi-kletz gui --no-server`) for one launch,
`ASI_KLETZ_AUTOMATION=off` for every launch: the window is fully usable, writes no session file,
the online indicator reads `◉ ONLINE` without a port, the About box says so, and the CLI gets
exit 3 with the hint above. A server that cannot bind is a status-bar warning, never a failed
launch.

**Security.** The socket is bound to `127.0.0.1`, so a request from another machine is
impossible by construction. The token is 128 bits from `secrets`, new on every launch, in a file
under the user's profile (readable by that account only; `0o600` elsewhere), so a process of a
*different* local user cannot drive the window, and a browser page cannot either (the `Origin`
refusal). A process of the *same* user is trusted: it can already open the database file, so the
token adds nothing against it and is not meant to. The server runs registered verbs through the
dispatcher and shows registered screens; there is no eval and no file path beyond what the verbs
accept. Every remote command carries its actor into the audit log. Not covered: a malicious
process of the same user, and a shared machine whose accounts share `%LOCALAPPDATA%` (they do
not, on Windows).

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- `openpyxl` (Excel views)
- `asi_escher` and `asi_gutenberg`, the sibling generators, declared as editable path sources
  (`../asi_escher`, `../asi_gutenberg`) in `pyproject.toml`; they bring matplotlib, Pillow,
  reportlab and python-docx
- `asi_hopper`, the sibling Jira door, declared the same way (`../asi_hopper`) and imported only
  when a `jira` verb runs; it brings `mcp` and `keyring`
- `pytest` for the test suite

## Install

```powershell
cd asi_kletz
uv sync
```

That creates `.venv` with the package installed in editable mode and the `asi-kletz` and
`asi-kletz-gui` commands on `.venv\Scripts`. Without uv: `python -m venv .venv` then
`.venv\Scripts\python -m pip install -e .` and `pip install pytest`.

## Configuration

`asi-kletz` looks for `kletz.toml` in the working directory (or at `$ASI_KLETZ_CONFIG`):

```toml
db = "kletz.db"
workbook = "../some folder/safety-plan.xlsx"
out = "../some folder/safety-plan-out"
doc_id = "ASI-FS-PLAN-001"
project = "WA485 Autonomous Wheel Loader"
jira_live_jql = "project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC"
jira_live_autofetch = false

[[revision]]
rev = "0.1"
date = "2026-10-27"
author = "FuSa Engineer"
description = "Initial draft"
```

Relative paths resolve against the config file, so the workbook and the generated views can go
into another folder, for example a shared one. The file is git-ignored because it is specific
to one machine; copy `kletz.example.toml` to start. Precedence for the paths is the explicit
argument (`--db`, `--out`), then the environment (`ASI_KLETZ_DB`, `ASI_KLETZ_WORKBOOK`,
`ASI_KLETZ_OUT`), then `kletz.toml`, then `kletz.db`, `kletz.xlsx` and `out/` next to the
database. `doc_id`, `project` and the `[[revision]]` entries are the Safety Plan document's
control data (see Diagrams and documents). `jira_live_jql` is the JQL the JIRA Live Data window
and `jira live` fetch when no `--jql` is given, and `jira_live_autofetch` (a TOML boolean, default
`false` since 0.7.4) whether the window fetches once when it is first shown instead of waiting
for Refresh; both are optional (see JIRA Live Data).

The export writes a workbook with one sheet per entity (`Safety Plan`, `Sprints`, `Sprint Items`,
`Weekly Status`, `Holidays`). Point `workbook` at a file of its own, never at a workbook that holds
other sheets you want to keep. `tracker_title`, `tracker_byline`, `tracker_scope`,
`tracker_jira_scope` (text) and `sprint_days` (an integer, business days) are the Weekly Activity
Tracker's settings (see Weekly Activity Tracker); all are optional. `default_points` (an integer,
default 2) is the floor a Safety Plan row weighs when it has neither its own points nor the estimation
panel's default. `sprint_capacity` is no setting
since 0.10.0: capacity is the rule (8, fixed), and the key, when present, is ignored with a warning
that `status` reports (`config_warnings`).

## Quick start

Seed the database from a workbook that has a `Safety Plan` sheet, look around, regenerate the
workbook:

```powershell
asi-kletz import excel "safety-plan.xlsx" --mode replace
asi-kletz status
asi-kletz list safety_plan_row --filter status=Blocked
asi-kletz create safety_plan_row --set deliverable="Safety Case" --set lifecycle_phase="8. Functional Safety Assessment"
asi-kletz update safety_plan_row 3 --data '{"status": "Done", "reviewer_pat": true}'
asi-kletz export excel --out "kletz.xlsx"
asi-kletz dump --out kletz.json
asi-kletz document safety_plan --out out
asi-kletz diagram phase_flow --param phase=8 --out out
asi-kletz jira live --limit 50
asi-kletz jira comments HWL-2572
```

Open the window on the same database (add `--theme plain` for the native look for this launch only):

```powershell
asi-kletz gui
```

While it is open, every `asi-kletz` command runs *in the window*: the family lock refuses the
CLI's own `Brain` and the CLI forwards the command to the window's automation server (see
[Automation](#automation)), so the screen you are looking at refreshes. `asi-kletz --no-forward
--wait 30 status` queues for the slot instead, exit code 3 when it stays taken.

The database and workbook locations come from `kletz.toml` (see Configuration). If the
workbook is open in Excel, the export writes a timestamped sibling and says so in `warnings`.

The entity name accepts the Python name, the table, the label, or the sheet name, so
`list "Safety Plan"` and `list safety_plan_row` are the same thing. `schema` prints the
entity, its fields, lookups, and the command signatures.

## Python API

```python
from asi_kletz import Brain

with Brain("kletz.db") as brain:
    result = brain.execute("create", entity="safety_plan_row",
                           data={"deliverable": "Write FSC", "lifecycle_phase": "3. Functional Safety Concept (FSC)"})
    print(result.ok, result.data["id"], result.warnings)

    # services are also available directly
    rows = brain.service("safety_plan_row").list(filters={"status": "Ongoing"}, order_by="order")

    # the wire format an agent would send
    brain.execute_dict({"verb": "get", "args": {"entity": "safety_plan_row", "id": 1}, "actor": "claude"})

    brain.events.subscribe("*", lambda topic, event: print(topic, event["entity"]))
```

Use the context manager (or call `close()`): a `Brain` holds the family slot from construction
to `close()`, and a forgotten one keeps every other primary tool out until the process exits.
`Brain(path, wait=30)` queues for the slot; when it stays taken, `Brain` raises
`asi_kletz.PrimaryToolBusy` with `slot` (`"family"` or `"database"`) and `holder` (the holder's
info, or `None`), and never opens the SQLite file. `brain.status()["locks"]` says what this
process holds.

**Identity.** A row has two names. The integer `id` is the handle: what `get`, `update` and
`delete` take, the audit log's `entity_id`, the tree iids and the status bar's
`Safety Plan Row 2 selected`. The `uid` (`schema/fields.py:uid_field`, the last field of every
entity, hidden) is the trace: a lowercase UUID4 assigned once by `EntityService.create`, never shown
on a screen, carried by every dump and workbook, matched first by every import (`load_rows`), and
refused by `update` (`uid is immutable`). Every command that takes an id takes a uid in its place
(`EntityService.resolve`: digits are an id, a uid is looked up, an unknown uid is `NotFound`), and
`list --filter uid=...` works as for any field. `Storage.stamp_uids` runs on every open, so a
database written before 0.9.0 gets its uids the first time 0.9.0 opens it (`brain.migration["uids_stamped"]`).

## Scripts

A script is one JSON object per line:

```jsonl
{"verb": "update", "args": {"entity": "safety_plan_row", "id": 7, "data": {"status": "Done"}}}
{"verb": "document", "args": {"name": "safety_plan"}, "actor": "claude"}
{"verb": "diagram", "args": {"name": "phase_flow", "param": {"phase": "8"}}}
{"verb": "export", "args": {"format": "excel"}}
```

The last three lines are the whole "publish the plan" routine: document, diagram, workbook.

Run it with `asi-kletz run steps.jsonl` (add `--stop-on-error true` to halt at the first failure).
A script is one `Brain`, hence one instance: the three publishing lines above take the slot once.
From separate CLI calls they are three short instances in a row. Add `--wait <seconds>` when a
window may be open.

## Themes

Every window is painted by a theme from `ThemeFactory`. The catalog is the **family palette**,
a convention shared by every primary tool in the ASI FuSa Tools (section "The family palette" in
[ASI_FUSA_TOOLS.md](../asi_fusa_tools/ASI_FUSA_TOOLS.md) is the authority): eight hue families (cyan, blue, violet,
pink, red, amber, gold, green) times four tones (`noir`, `neon`, `dusk`, `day`), 32 palettes
keyed `<family>-<tone>` and titled `<Family> <Tone>`, plus `plain` for the native look. `tron` is
an alias of `cyan-neon`. Each tool carries the catalog as plain data in `gui/palettes.py`, byte
for byte the same, and a test hashes it against the digest in the family file; nothing is
imported from the sister tool. Both tools open in **`cyan-neon`** (the original `tron` look) until
a theme is latched; each tool latches on its own, so they drift apart only when the owner says so.

Pick a theme in the window, with the **THEME** box at the foot of the navigation column or
`View > Theme`, or from the command line:

```powershell
asi-kletz theme              # the catalog, the latched key, the key in use, the preferences path
asi-kletz theme pink-noir    # latch Pink Noir; a window open in this process repaints at once
asi-kletz theme --list       # the same as no key
```

A pick **latches**: the window repaints at once (the open screen is rebuilt, so save first) and
the choice survives a restart until the next pick. It is a per-person, per-machine preference,
not a project setting, so it lives neither in `kletz.toml` nor in the database but in
`%LOCALAPPDATA%\asi\kletz\prefs.json` (`$XDG_STATE_HOME/asi/kletz/prefs.json` or
`~/.local/state/asi/kletz/prefs.json` elsewhere); `ASI_KLETZ_PREFS` names another file, and the
test suite points it at a temporary one. Each tool has its own file, so a pick in Kletz never
changes its sister. Precedence when the window opens: `--theme` on `asi-kletz gui` or
`asi-kletz-gui`, then `ASI_KLETZ_THEME`, then the latched preference, then `cyan-neon`. The
argument and the environment are one-off views and never write the preference; the picker
always shows the theme that is painting the window. A corrupt preferences file or an unknown
key in it is ignored with a warning in the status bar and overwritten by the next pick.

## Layout

```
src/asi_kletz/
  brain.py            Brain: wires everything, the in-process API, kletz.toml loading
  version.py          __version__ and SCHEMA_VERSION, the single source of truth
  errors.py           BrainError and the deliberate errors the dispatcher turns into Result.failure
  prefs.py            prefs.json: the per-person, per-machine preferences (the latched theme)
  locks.py            the family lock: SlotLock, PrimaryGuard, PrimaryToolBusy (one primary tool at a time)
  schema/             FieldSpec, EntitySchema, lookups, registry, definitions (the Safety Plan)
  models/             ModelFactory (dataclasses from schemas)
  storage/            Storage interface, SQLite backend, migrations, audit log, StorageFactory
  repositories/       SqlRepository, RepositoryFactory
  services/           EntityService (validated CRUD), TransferService (dump/load/export/import), JiraService (read only)
  commands/           Result, Command, CommandFactory, Dispatcher, built-in verbs
  io/                 JSON and Excel exporters and importers behind factories
  generate/           DiagramFactory, DocumentFactory, Spec, Param, the catalogs, plan_queries, figures
  automation/         CLI (with forwarding), EventBus, script runner, the local server (server.py), the session file (session.py)
  gui/                tkinter: MainWindow (owns the server), ScreenFactory, WidgetFactory, themes, the family palette, the screens, the comments window
tests/                pytest suite (schema, core, transfer, CLI, generate, theme, jira, locks, GUI, server, session)
```

## Tests

```powershell
.venv\Scripts\python -m pytest
```

Continuous integration (`.github/workflows/ci.yml`, since 0.13.0) runs `uv run ruff check src tests` and
`uv run pytest -q` on `windows-latest` (Tk is there, so the GUI tests run) on every push to `main`,
every `v*` tag and every pull request; the job checks this repo out into `asi_kletz/` and the three
sibling tools into sibling folders, because the lock pins them as editable path sources.

Tests never read the developer's `kletz.toml` or environment, so no test can touch a real
workbook. One test seeds a database from the workbook named in the repo's `kletz.toml` and
is skipped when there is none. `tests/fixtures/kletz-0.8.4.db` is a small database made with the
0.8.4 code (three plan rows, one sprint, no `uid` column); the open-and-stamp test copies it to a
temporary folder, never opens it in place, and checks that 0.9.0 adds the column and the index,
stamps every row, audits the counts and changes nothing else. The GUI tests drive real tkinter widgets with the window
withdrawn and are skipped when no display is available. pytest runs with `--capture=sys`
(see `pyproject.toml` for why). The generate tests run the real asi_escher and asi_gutenberg
(no mocks), check that importing `asi_kletz` loads neither matplotlib, reportlab nor asi_hopper,
and grep the source tree to make sure the sister tool is never mentioned, let alone imported.
The jira tests run the verb against asi_hopper's recorded fixtures (`../asi_hopper/tests/fixtures`,
replay gateway, no network, no session) and a stub Hopper, and are skipped when the fixtures are
not checked out; the GUI tests feed the live screen and the comments window from a stubbed
`execute_quiet` (answering on the worker thread, as the real one does, and holding on a
`threading.Event` when a test wants to look at a fetch in flight), so no test ever reaches Jira. The lock tests start real second processes: a Kletz
holder, a simulated sibling that takes `primary.lock` by the raw convention with no package
import, and a probe that reports whether a lock is held; every test points
`ASI_PRIMARY_LOCK_DIR` at its own folder, so the suite never collides with a running tool or with
the sister suite. The server tests drive a real window's automation server over `urllib` from a
helper thread while the test pumps the Tk loop, and the session tests exercise the CLI's
forwarding against a monkeypatched lock refusal; every test points `ASI_KLETZ_SESSION` at its
own file, so a developer's open window never receives test traffic.

## Adding an entity

The schema machinery is generic: an entity registered with `register_entity` gets a table,
commands, JSON, and a workbook sheet; `ALL_ENTITIES` in `schema/definitions.py` lists the four of
0.8.0 in order and the test suite asserts that list, never a count. End the fields with
`uid_field()` so the entity carries the hidden identity like the others (a test checks that every
registered entity does). It does not get a screen by
itself: screens are registered in `gui/screens.py`, asserted the same way. The list is the design,
not a cap.
