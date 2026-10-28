# ASI Kletz — Plan: the Weekly Activity Tracker and sprints

**Status:** Phases 1 to 3 implemented 2026-10-28 (asi_kletz 0.8.0); phase 4's screens and dashboard strip
implemented the same day (0.8.1), its burndown and velocity diagrams and the sprint report still open; phase 5's
family tables carried by each release. Deviations recorded by the implementing
agent in the CHANGELOG entry: weeks start on Monday; People and Questions stay inside the Issues text; `sprint
close` always opens the next sprint.
**Written:** 2026-10-28
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.8.0 (after 0.7.4; schema version 1 → 2, two new entities; Kletz only, the
Dewey column of the version ladder stays empty as it did for 0.7.4)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md); this plan adds one row to
the plans table and one to the version ladder there, and no new convention section (nothing here is
shared with the sister tool).
**Source file:** `Roy's Brain/Roy's status.txt` (144 lines, last updated 10/28/2026), the engineer's
hand-kept weekly tracker, newest week at the top.

---

## 1. The ask

Asked by the owner on 2026-10-28, verbatim: "make a markdown proposal in kletz explaining a plan to
integrate the roy's status text file and to produce both a complete historical text file but also a
version for the current week … each sprint is 10 points lets make this an agile tool".

Read as five decisions:

1. **The status file comes into Kletz.** Today the tracker is a text file kept by hand next to the
   `Roy's Brain` workbook. After this plan the database holds the weeks, the sprints and the sprint
   items, and the text file is a *generated view* of them, exactly as the workbook, the diagrams and
   the documents are. The existing file is imported once, by a verb, and its format is the
   specification of the output: an import followed by a build must give the file back.
2. **Two text outputs, one source.** `tracker build history` writes the whole tracker, every sprint
   and every week, newest at the top, in the format of today's file. `tracker build week` writes the
   same header and timeline followed by the current week only, for the stand-up, the mentor
   meeting and the weekly mail. Both are `.txt`, both go to the output folder, both are
   regenerated on demand and never read back.
3. **A sprint is ten points.** Each sprint has a capacity of 10 points, two weeks long (Phase 3
   Sprint 1 runs 10/27 to 11/10 in the file). Every sprint item carries points; the tool sums
   them, warns when a sprint is over-committed, counts the points done at close, carries the rest
   into the next sprint and reports velocity. The number 10 is a default, in the schema and in
   `kletz.toml`, not a constant in code.
4. **Agile vocabulary, Kletz vocabulary.** Sprint, sprint item, points, sprint goal, carry-over,
   velocity and burndown are added; nothing of the Safety Plan changes. A sprint item may point at
   a Safety Plan deliverable (by row id) or at a Jira issue (by key) or at neither (a meeting, a
   question). The plan says *what* must be delivered across the lifecycle; the sprints say *when*,
   two weeks at a time.
5. **Jira stays live and read only; the week's report is the engineer's.** The "Jira issues" block
   of a week is rebuilt from `jira live` when the engineer builds with `--jira`, and the Jira
   status, priority and assignee of each item are then written into the week's text. That text is
   the engineer's status report, frozen when the week closes, not a Jira cache: it is never
   refreshed or reconciled, nothing is listed from it, and `jira live` still stores nothing. The
   note and the sprint target on each item are the engineer's own and live on the item. No write
   to Jira, in keeping with the owner's closure of the Hopper write side (2026-10-27).

Two of Kletz's constraints are touched:

- **One table becomes three.** "ASI Kletz holds exactly one thing, the Safety Plan" (README) is
  tested in `test_only_the_safety_plan_is_registered` and
  `test_database_still_has_exactly_one_table_after_generating`. The weeks and the sprints are the
  engineer's own data, kept nowhere else, so a view in memory (the JIRA Live Data answer) does not
  apply. This plan **retires the one-table rule** the way the 0.5.0 plan retired the screen count:
  entities are registered in `schema/definitions.py`, `ALL_ENTITIES` lists them in order, and the
  two tests assert that list, never a count. The Safety Plan keeps its 63 columns untouched; a
  sprint item refers to a deliverable by id, so the plan's sheet, screens, documents and diagrams
  are unchanged. The owner should confirm this retirement in the same breath as the plan.
- **No person is named inside the tool.** The file's byline, "Roy Mendoza, FSE", becomes
  `tracker_byline` in `kletz.toml` (machine-specific, git-ignored) and the title
  `tracker_title`; the code and the example config name a role. Names inside the data (a Jira
  assignee, a mentor in an outcome line) are data, as they already are on the JIRA Live Data
  screen.

## 2. What exists today (verified 2026-10-28)

| Fact | Where |
|---|---|
| The tracker is one text file: a title line, a byline with `Last updated 10/28/2026`, a `TIMELINE` block of three bullets, then sprint blocks framed by `=====` rules (`PHASE 3 - SPRINT 1 (10/27 - 11/10)   [in progress]`, `PHASE 2 - FINAL SPRINTS (10/12 - 10/27)   [closed 10/27]`), each holding `WEEK OF m/d - m/d` blocks, newest first, with the sections `Outcomes` (or `Outcomes so far`), `Miscellaneous issues` (sub-blocks per lifecycle phase, `People and cadence`, `Status questions`) and `Jira issues (...)`. | `../Roy's Brain/Roy's status.txt` |
| A Jira line in the file is three physical lines: `HWL-2554  Story  Perform Platform Safety Plan`, `Jira status: In Progress \| Priority: Un-Groomed \| Assignee: ...`, `Note: ...`, then `Sprint 1 target: ...`. Eight issues this week: six under epic HWL-1915 assigned to the engineer, two watched. The deliverable sub-blocks carry `Sprint 1 target:` lines of their own (four, on Safety Plan, ConOps, Activity Flow and the Preliminary Hazard List), one more sits under `People and cadence` (the Rod DeMay meeting), and there are two `Ask:` lines. | same file, lines 65–112 (Jira) and 31–60 (deliverables, people, questions) |
| The nine Phase 1 and Phase 2 deliverables the file reports on are rows 1–9 of the plan (`Safety Plan`, `SCOPE Definition Report`, `System Functions, Functional Architecture and its Interfaces`, `ConOps / Use Case specification`, `TOD/PRD document`, `Activity Flow`, `Preliminary Hazard List (...)`, `STPA step 2`, `HARA report with MPLr/PLr assignments`), matched by title. All 48 rows have `status` and `deadline` empty today. | `kletz.db`, `safety_plan` |
| A companion file, `Wheel Loader FSE onboarding, status 10/28`, carries DONE / WAITING / OPEN QUESTIONS and an appendix of the same eight tickets; its content is a subset of the tracker's current week. | `../Roy's Brain/Wheel Loader FSE onboarding, status.txt` |
| `register_entity(EntitySchema(...))` gives an entity a table (`ensure_schema` creates missing tables and columns), generic `list/get/create/update/delete/count`, JSON dump/load and a workbook sheet. `ALL_ENTITIES = (SAFETY_PLAN_ROW,)`. Field types: text, multiline, int, bool, date, url, enum (with a lookup). | `schema/definitions.py`, `schema/fields.py`, `storage/sqlite.py` |
| `test_only_the_safety_plan_is_registered`, `test_database_still_has_exactly_one_table_after_generating` and `test_json_dump_and_load_modes` (`schema_version == 1`, `set(payload["entities"]) == {PLAN}`) pin the one table. `SCHEMA_VERSION = 1`. | `tests/test_core.py`, `tests/test_generate.py`, `tests/test_transfer.py`, `version.py` |
| The Excel importer reads one sheet per registered entity by its `sheet` name and warns when a sheet is missing; the exporter writes one sheet per entity. Both already loop over the registry. | `io/importers.py`, `io/exporters.py` |
| `load_config` reads `CONFIG_TEXT_KEYS = ("doc_id", "project", "jira_live_jql")`, `CONFIG_BOOL_KEYS = ("jira_live_autofetch",)` and the `[[revision]]` list. No integer keys yet. | `brain.py` |
| A verb named `status` already exists (database, out_dir, lock, versions). The new verbs cannot take that name. | `commands/crud.py`, README |
| `jira live` returns `{jql, fetched_at, count, truncated, issues}` with `key, issue_type, summary, status, status_category, priority, assignee, reporter, ...` per issue; `--jql` is accepted. The window keeps the last fetch on `window.jira_live`. Nothing is stored. | `commands/jira.py`, `services/jira_service.py`, README "JIRA Live Data" |
| Documents are `Document(title, kind, **meta)` with `h1/h2/p/table/fields`, written as md/pdf/docx; diagrams are asi_escher `Diagram`s; both registered by `Spec`. `plan_queries` is the shared read side; `due_within` and `parse_deadline` already parse free-text dates. | `generate/base.py`, `generate/documents.py`, `generate/plan_queries.py` |
| Screens: `dashboard`, `jira_live`, `safety_plan`, `safety_plan_matrix`, `transfer`, registered in that order; the test asserts the list. The dashboard shows status tiles, phase counts, open deliverables and recent changes. | `gui/screens.py`, `gui/dashboard.py`, `tests/test_gui.py` |
| `[[revision]]` in `kletz.toml` is the precedent for small, deliberate, dated lists in config rather than in a table. | `kletz.example.toml`, README |
| `Roy's Brain.xlsx` carries `tasks`, `facts`, `links`, `JIRA`, `people` sheets and a copy of the Safety Plan sheet. None of it is read by Kletz; the `JIRA` sheet (6 rows) duplicates what `jira live` shows. | `../Roy's Brain/Roy's Brain.xlsx` |

## 3. Design

### 3.1 Vocabulary

| Term | Meaning in Kletz |
|---|---|
| Sprint | A dated interval of work, two weeks by default, with a capacity of 10 points, a lifecycle phase, a goal and a status (Planned, Active, Closed). Exactly one sprint is Active at a time. |
| Sprint item | One thing the sprint commits to: a deliverable of the plan, a Jira issue, or something else (a meeting, a question). Carries points, a target ("dated and baselined"), a note, a status (To Do, In Progress, Done, Carried) and, when carried, the sprint it came from. |
| Points | An integer 1 to 10 on an item, the sprint's capacity being 10. Null means not yet pointed; the tool says so instead of counting it as zero. |
| Week | One `WEEK OF` block of the tracker: a start date (Sunday, as in the file), the sprint it falls in, and its sections of text. Two weeks per sprint. |
| Week entry | One section of one week: `Outcomes`, `Issues`, `People`, `Questions`, `Jira`. Free text, kept verbatim. |
| Velocity | Points Done per Closed sprint; the average of the last three Closed sprints is the number the build prints. |
| Carry-over | At close, every item not Done is copied into the next sprint with status To Do and `carried_from` set; the original stays in the closed sprint as Carried. |

### 3.2 Entities

Three registrations in `schema/definitions.py`, after `SAFETY_PLAN_ROW`, in this order. Lookups
`sprint_status`, `item_status`, `item_kind`, `week_section`.

**`sprint`** (table `sprint`, sheet `Sprints`, label "Sprint"), `order_by=("number",)`:

| Field | Type | Notes |
|---|---|---|
| `number` | int, required | 1, 2, 3 … across the programme, never per phase (the file's "Phase 3 - Sprint 1" prints from `lifecycle_phase` + the sprint's `label`) |
| `label` | text | Printed name, e.g. `SPRINT 1` or `FINAL SPRINTS`; defaults to `SPRINT <number>` |
| `lifecycle_phase` | enum `lifecycle_phase` | The plan's own lookup |
| `start`, `end` | date | ISO in the database, `m/d` in the text |
| `capacity` | int | Default `brain.sprint_capacity` (10) |
| `goal` | multiline | One or two lines; prints under the sprint heading |
| `status` | enum `sprint_status` | Planned, Active, Closed |
| `closed_on` | date | Set by `sprint close`; prints as `[closed 10/27]` |

**`sprint_item`** (table `sprint_item`, sheet `Sprint Items`, label "Sprint Item"),
`order_by=("sprint", "order", "id")`:

| Field | Type | Notes |
|---|---|---|
| `sprint` | int, required | `sprint.number` |
| `order` | int | Print order inside the sprint |
| `kind` | enum `item_kind` | Deliverable, Jira, Meeting, Question, Other |
| `title` | text, required | For a Deliverable, filled from the plan row; for a Jira item, the summary as last seen |
| `plan_row` | int | `safety_plan.id` when `kind` is Deliverable |
| `jira_key` | text | `HWL-2554` when `kind` is Jira |
| `points` | int | 1–10 or empty (unpointed); `coerce` rejects 0 and anything above the sprint's capacity |
| `target` | text | The file's `Sprint 1 target:` line |
| `note` | multiline | The file's `Note:` line, the engineer's reading |
| `jira_line` | text | `In Progress \| Un-Groomed \| Roy Mendoza`, written only by `tracker build --jira` or by the importer; see 3.6 |
| `status` | enum `item_status` | To Do, In Progress, Done, Carried |
| `carried_from` | int | The sprint this item was carried out of |
| `done_on` | date | Set when status becomes Done |

**`week`** (table `week`, sheet `Weekly Status`, label "Week"), `order_by=("start",)`:

| Field | Type | Notes |
|---|---|---|
| `start` | date, required, unique | The Sunday; `WEEK OF 10/26 - 11/01` prints from it |
| `sprint` | int, required | `sprint.number` |
| `section` | enum `week_section` | Outcomes, Issues, People, Questions, Jira |
| `order` | int | Print order inside the section |
| `text` | multiline | The section's text, verbatim, including its own bullets and sub-headings |

So a week is several rows, one per section, which keeps the entity flat (one table, one sheet, one
form) and keeps every line of the engineer's prose exactly as typed. The alternative, one row per
week with five multiline columns, is in section 7.

Foreign keys are by value (`sprint.number`, `safety_plan.id`), checked by the verbs and the
builder, not by SQLite constraints: the storage layer creates tables from field specs and has no
constraint vocabulary, and adding one for this plan is a change to core code that registration
avoids. A dangling reference is a build warning, never a crash.

### 3.3 The file format is the specification

The importer and the builder share one module, `tracker/format.py`, that knows the grammar of the
file. It is small and strict:

```
<title>                                   kletz.toml tracker_title
<byline>. Newest week at the top. Last updated m/d/yyyy.
                                          kletz.toml tracker_byline; the date is the build date
TIMELINE                                  one bullet per sprint, oldest first, plus the scope line
- Phase 2 (HARA / Risk Assessment): final sprints 10/12 - 10/27/2026. Closed 10/27.
- Phase 3 (Functional Safety Concept): opened 10/27/2026. Sprint 1: 10/27 - 11/10.
- Scope: ...                              kletz.toml tracker_scope

=====================================================================
PHASE 3 - SPRINT 1 (10/27 - 11/10)   [in progress]        sprint.status Active
=====================================================================
                                          new in 0.8.0, one line, only when the sprint has points:
Sprint: 10 points capacity, 9 committed, 3 done, 7 to go, 13 days left; velocity 0 (no closed sprint)

WEEK OF 10/26 - 11/01   (...)             week.start; the parenthesis is the week's Outcomes-free lead, kept as text

Outcomes so far                           section Outcomes ("Outcomes so far" while the week is current, "Outcomes" once closed)
- ...

Miscellaneous issues                      section Issues: the deliverable sub-blocks, verbatim

  People and cadence                      section People (optional), printed indented under Issues
  Status questions (answered 10/28)       section Questions (optional), likewise

Jira issues (project HWL, open items I am assigned, reported or watching, as of 10/28)
                                          section Jira: built from sprint items of kind Jira, see 3.6
  HWL-2554  Story  Perform Platform Safety Plan                       item.jira_key, type, title
            Jira status: In Progress | Priority: Un-Groomed | Assignee: Roy Mendoza     item.jira_line
            Note: In progress, will be ready before November 10.      item.note
            Sprint 1 target: dates added to every deliverable; plan baselined.   item.target
            Points: 3                                                 new in 0.8.0, omitted when unpointed
```

Import rules (`tracker import <file>`):

- The `=====` framed headings create sprints: the phase from the words before the dash matched to
  the `lifecycle_phase` lookup by number or title, the label from the words after it, the dates
  from the parenthesis, `[in progress]` → Active, `[closed m/d]` → Closed with `closed_on`.
  Sprint numbers are assigned oldest first. The two in today's file become sprint 1 (Phase 2,
  `FINAL SPRINTS`, Closed 10/27) and sprint 2 (Phase 3, `SPRINT 1`, Active). The printed
  heading comes from the label, so the file still says `PHASE 3 - SPRINT 1`.
- `WEEK OF` headings create weeks under the sprint whose block they sit in; the sections are
  split on the five known headings and kept verbatim, the lead parenthesis included in the
  Outcomes row's first line. Unknown headings stay inside the section they follow.
- Each `HWL-nnnn` block in the Jira section becomes a sprint item of kind Jira in the sprint of
  that week, with `jira_line`, `note` and `target` from its three indented lines; a `Points:`
  line, when present, sets `points`. A key already present in that sprint is updated, not
  duplicated (the same ticket appears in several weeks).
- Each `Sprint 1 target:` line inside the Issues section becomes an item of kind Deliverable,
  matched to a plan row by its bullet's leading title (`Safety Plan (Word document): in work.` →
  row 1 by the text before the colon or parenthesis, normalised); an unmatched title becomes
  kind Other with a warning naming it. A `Sprint 1 target:` line inside the People section
  becomes an item of kind Meeting. The `Ask:` lines become items of kind Question.
- `TIMELINE` and the byline are read for the scope line and the last-updated date only; the
  sprints are the source of the timeline on output.
- Points are absent in today's file, so every imported item is unpointed; the build and the
  Sprint Board say `n items unpointed` until the engineer points them. The importer never
  invents a number.
- The verb is idempotent: a second import of the same file changes nothing and reports
  `unchanged`. Mode `replace` (the default for a first import into an empty tracker) and
  `merge` as JSON load has them.

Round trip: `tracker import` of today's file, then `tracker build history --as-of 2026-10-28`
without `--jira`, reproduces the file except for the generated sprint line and the `Points:`
lines, which are absent while nothing is pointed; the test diffs the two and expects the empty
diff. From then on the file in `Roy's Brain` is a build output, and the engineer edits the
database (window, CLI, or an agent through the automation server), never the text.

### 3.4 Verbs

The generic CRUD covers the three entities from the first line of this plan
(`asi-kletz create sprint --data '{"number": 3, ...}'`, `asi-kletz list week --where sprint=2`).
Two new verbs carry what CRUD cannot say:

```
asi-kletz tracker import "..\Roy's Brain\Roy's status.txt" [--mode replace|merge]
asi-kletz tracker build history [--out out] [--jira] [--as-of 2026-10-28]   # out/tracker_history.txt
asi-kletz tracker build week    [--out out] [--jira] [--as-of ...]          # out/tracker_week.txt
asi-kletz tracker add --section Outcomes --text "..." [--week 2026-10-26]   # append a line to the current week
asi-kletz sprint board [n]                      # items, points, capacity, days left; JSON for the screen
asi-kletz sprint start --phase 3 --start 2026-11-10 [--end ...] [--capacity 10] [--goal "..."]
asi-kletz sprint close [n]                      # Done counted, the rest carried, velocity recomputed
asi-kletz sprint point <item-id> <points>       # shorthand for update sprint_item
asi-kletz sprint carry <item-id> [--to n]       # move one item now, without closing
```

`commands/tracker.py` (`TrackerCommand`, verb `tracker`, actions `import | build | add`) and
`commands/sprint.py` (`SprintCommand`, verb `sprint`, actions `board | start | close | point | carry`),
positional `action` with choices as `jira` has, so a later action is a choice added, not a verb.
`tracker build` takes `kind` positional (`history | week`), `--out`, `--jira` (bool) and `--as-of`
(a date, default today, so a test can build the file of 10/28 next year). The services behind
them, `services/tracker_service.py` and `services/sprint_service.py`, hold the rules of 3.5 and
3.6; the verbs are a few lines each, like `jira`.

Every write goes through the entity services, so the audit log records it (`actor`, `entity`,
`id`) and the event bus refreshes the open screens. `tracker build` audits a `generate` entry and
publishes `generated`, like a document. `sprint close` publishes `sprint.closed` with the numbers
of 3.5 so the dashboard can show them without a query.

`--jira` on a build runs `jira live` with the JQL
`project = HWL AND key in (<the sprint's Jira keys>)`, one call, and updates `title` and
`jira_line` of those items before writing the file. Without `--jira` the lines print as last
seen. No Atlassian session is a warning (`Jira not fetched; lines as last seen`), never a failure:
the file still builds.

### 3.5 Agile rules

All in `services/sprint_service.py`, all read by the board, the builder and the dashboard through
`generate/sprint_queries.py` (the sibling of `plan_queries.py`, so the number on the screen is the
number in the text):

- **Capacity.** `committed = sum(points of items not Carried)`. Over capacity is a warning on
  `create`, `update`, `point` and `board` (`sprint 2 committed 12 of 10 points`), never a
  refusal: the engineer decides, the tool says. `unpointed = count(items with no points)` is
  always printed beside it.
- **Done.** `done = sum(points of items with status Done)`; an unpointed Done item counts as
  done work but as 0 points, and the board says `1 unpointed item done`.
- **Days left.** `end - as_of`, calendar days, never negative; `0 days left` past the end, and the
  board flags `overdue` when an Active sprint's end has passed.
- **Close.** `sprint close [n]` (default the Active one): every item not Done becomes Carried
  and a copy is created in the next sprint (created as Planned if it does not exist, dates
  following on from the closed one with the same length and capacity) with status To Do, the
  same points, `carried_from = n`. The closed sprint's `done` is frozen as its velocity. The
  next sprint becomes Active if it was Planned. One sprint Active at a time is enforced here and
  on `start`.
- **Velocity.** The mean `done` of the last three Closed sprints, one decimal; `no closed
  sprint` until there is one. Printed on the sprint line of the text, on the board and on the
  dashboard tile.
- **Burndown.** One diagram, `sprint_burndown [--param sprint=n]`, registered like the others:
  capacity on day 0 falling by each item's points on its `done_on`, the ideal line beside it.
  One more, `velocity`: a bar per Closed sprint. Both go in the new document `sprint_report`
  (kind report, "Sprint Report": goal, the board table, burndown, velocity, carried items) for
  the people who want a PDF rather than a text file.

### 3.6 Jira inside a week

The convention from the 0.5.0 plan holds: the JIRA Live Data window stores nothing, and
`jira live` still writes neither the database nor the audit log. What this plan adds is the
engineer's own record of a ticket in their report, which the hand-kept file already was:

- A Jira item's identity is its `jira_key`; its `title` and `jira_line` are the words the
  engineer last chose to publish, updated only by an explicit `tracker build --jira` or by the
  importer. There is no sync, no timer, no reconcile, no column on the Safety Plan.
- The week's Jira section is not stored as prose while the week is current: it is built from
  the sprint's items of kind Jira, in `order`, with the heading line
  `Jira issues (project HWL, open items I am assigned, reported or watching, as of m/d)`.
  Items whose `jira_line` says a Done category are grouped under `Closed this week` instead of
  dropped, so the history stays complete.
- When a sprint closes, each of its weeks gets its Jira section written as a `week` row of
  section Jira, verbatim from the last build, so the history of a closed sprint never changes
  when a ticket moves later. A current week has no Jira row; a closed one has.
- The epic grouping (`Epic HWL-1915 "MVP3 - PDP Phase 3 Closeout"`) and the `Watched, assigned
  to ...` sub-heading come from the items' `note` and `order`, not from Jira: the engineer
  arranges the section, the tool prints it.

### 3.7 Screens

Two screens, registered after `safety_plan_matrix` and before `transfer`; the list in
`gui/screens.py` grows to seven, `SCREENS` and `TITLES` in the test follow:

- **`sprint_board`, "Sprint Board"** (`gui/sprint_board_screen.py`). A sprint picker (the Active
  one first), the goal, a capacity bar (`committed / 10`, over capacity in the palette's warning
  colour, unpointed count beside it), days left and velocity in the toolbar; below, three
  columns To Do / In Progress / Done as lists of items (`[3] Perform Platform Safety Plan ·
  HWL-2554`), a click selecting the item into a form (kind, title, plan row or Jira key, points,
  target, note, status). Buttons: New item, Save, Delete, Point, Carry, Close sprint, Start
  sprint, Build week, Build history. Every button is a verb through `window.run`.
- **`tracker`, "Weekly Status"** (`gui/tracker_screen.py`). Week picker (current first), the
  five sections as `tk.Text` panes with Save per pane, a `Jira (built)` pane that is read-only
  while the week is current, `Build week` and `Build history` with Open and Open folder as the
  transfer screen has. No import button: the import is a one-off CLI act and the file is a
  build output from then on.
- **Dashboard.** One more tile row: `Sprint n · x/10 committed · y done · z days left ·
  velocity v`, a click opening the Sprint Board. Refreshed by the same event path.
- **File menu.** `Build current week (tracker)` and `Build tracker history` beside `Build
  Safety Plan document`.
- **Export / Import.** Nothing new: the workbook gains the three sheets automatically, and the
  document catalog gains `sprint_report`.

### 3.8 Configuration

```toml
# Weekly Activity Tracker (`asi-kletz tracker ...`). The byline names the person who keeps it and
# belongs in this git-ignored file, never in code or in the example.
tracker_title = "WHEEL LOADER FUNCTIONAL SAFETY ENGINEERING - WEEKLY ACTIVITY TRACKER"
tracker_byline = "FuSa Engineer"
tracker_scope = "Scope: platform functional safety for the Wheel Loader programme (project HWL)."

# Sprint defaults: capacity in points and length in days. A sprint stores its own values; these
# fill `sprint start` and the window's form.
sprint_capacity = 10
sprint_days = 14
```

`CONFIG_TEXT_KEYS` gains the three text keys; a new `CONFIG_INT_KEYS = ("sprint_capacity",
"sprint_days")` is copied only when the TOML value is an integer, like the boolean keys.
`Brain.sprint_capacity` and `Brain.sprint_days` expose them; `status` reports them.

### 3.9 Error handling

- Import: an unreadable file, a file without a `TIMELINE` line, or a sprint heading whose phase
  matches no lookup value is a `CommandError` naming the line number; nothing is written
  (one transaction). A week block whose dates do not fall inside its sprint is a warning and is
  imported anyway, dated as written.
- Build: no Active sprint → `tracker build week` fails with `no active sprint; run sprint start`;
  `history` builds whatever exists. An item whose `plan_row` or `sprint` points nowhere prints
  with `[missing]` and a warning. A locked output file falls back to a timestamped stem, as
  documents do.
- Close: closing a sprint that is not Active is a `CommandError`; closing with unpointed items
  is a warning that names them, and they are carried with no points.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Entities + rule retirement | `sprint`, `sprint_item`, `week` and their four lookups in `schema/definitions.py`; `ALL_ENTITIES` of four; `SCHEMA_VERSION = 2`; `CONFIG_INT_KEYS` and the tracker text keys in `load_config`; `test_only_the_safety_plan_is_registered` → `test_registered_entities_in_order`, `test_database_still_has_exactly_one_table_after_generating` → `..._has_exactly_the_registered_tables`, `test_json_dump_and_load_modes` on schema version 2 and the four-entity set. | `uv run pytest` passes; `asi-kletz create sprint`, `list sprint_item`, `export excel` (four sheets) and `import excel` of that workbook round-trip on a temporary database; a 0.7.4 `kletz.db` opens and gains the three tables with no data change. |
| 2. Format + import | `tracker/format.py` (parse and render, one grammar), `services/tracker_service.py` (`import_file`, `render_history`, `render_week`), `commands/tracker.py` with `import` and `build`. | `tracker import` of the real file creates 2 sprints, 3 weeks, 6 week rows (four sections for the 10/26 week, Outcomes only for the two Phase 2 weeks), 8 Jira items, 4 Deliverable items (rows 1, 4, 6 and 7 matched, a warning for any miss), 1 Meeting item, 2 Question items; `tracker build history --as-of 2026-10-28` diffs empty against the file; `tracker build week` holds the 10/26 week only. |
| 3. Sprint rules | `services/sprint_service.py`, `generate/sprint_queries.py`, `commands/sprint.py` (`board`, `start`, `close`, `point`, `carry`), `sprint.closed` event, `--jira` on the build. | Section 6 rule cases pass; closing sprint 2 on a copy carries the open items into sprint 3 with `carried_from = 2` and the history prints both; `--jira` on the replay gateway updates `jira_line` for a recorded key and warns for an unrecorded one. |
| 4. Screens + dashboard + diagrams | `gui/sprint_board_screen.py`, `gui/tracker_screen.py`, registration, the dashboard tile row, File menu entries; `sprint_burndown` and `velocity` diagrams; `sprint_report` document. | `test_gui.py` passes with the seven-entry list; manual check: point every item on the board, the bar reaches 9/10, Build week writes the file and Open opens it, close the sprint and the dashboard tile shows sprint 3; `document sprint_report` builds the triplet with two figures. |
| 5. Docs + family | README sections "Weekly Activity Tracker" and "Sprints", the one-table wording replaced everywhere it is normative ("holds exactly one thing", "Nothing else is stored", "Kletz still holds one table") by "entities are registered in `schema/definitions.py`; the list is the design, not a cap"; CHANGELOG 0.8.0; `kletz.example.toml`; `docs/plan.md`; `version.py` and `pyproject.toml` 0.8.0; `ASI_FUSA_TOOLS.md` plans table row and version ladder row (Dewey column empty). | `uv run pytest` and `uv run ruff check src tests` clean; `grep -n "one table" README.md` finds only history; the family tables carry 0.8.0. Tag left to the owner. |

Phases 1 to 3 are usable from the CLI and by an agent before any screen exists, which is the house
order (verb first, window second).

## 5. Files touched

```
src/asi_kletz/schema/definitions.py        sprint, sprint_item, week; lookups sprint_status, item_status, item_kind, week_section; ALL_ENTITIES of four
src/asi_kletz/version.py                   0.8.0; SCHEMA_VERSION = 2
src/asi_kletz/brain.py                     tracker_* text keys, CONFIG_INT_KEYS (sprint_capacity, sprint_days), Brain.sprint_capacity/sprint_days, Brain.tracker, Brain.sprints
src/asi_kletz/tracker/__init__.py          new package
src/asi_kletz/tracker/format.py            new: the file grammar, parse() and render(); shared by importer and builder
src/asi_kletz/services/tracker_service.py  new: import_file, add_line, render_history, render_week, freeze_jira_section
src/asi_kletz/services/sprint_service.py   new: board, start, close, point, carry, velocity, capacity warnings
src/asi_kletz/services/__init__.py         export the two
src/asi_kletz/commands/tracker.py          new: TrackerCommand (import | build | add), --out, --jira, --as-of, --mode
src/asi_kletz/commands/sprint.py           new: SprintCommand (board | start | close | point | carry)
src/asi_kletz/commands/__init__.py         import both so they register
src/asi_kletz/generate/sprint_queries.py   new: the read side the board, the builder, the dashboard and the diagrams share
src/asi_kletz/generate/diagrams.py         sprint_burndown (param sprint), velocity
src/asi_kletz/generate/documents.py        sprint_report
src/asi_kletz/gui/sprint_board_screen.py   new: SprintBoardScreen
src/asi_kletz/gui/tracker_screen.py        new: TrackerScreen
src/asi_kletz/gui/screens.py               register sprint_board and tracker after safety_plan_matrix
src/asi_kletz/gui/dashboard.py             the sprint tile row
src/asi_kletz/gui/main_window.py           File menu entries; sprint.closed in _on_event (plain refresh)
tests/test_tracker.py                      new: grammar, import of the real file (fixture copy under tests/fixtures/), round trip, week build, --jira on replay
tests/test_sprint.py                       new: capacity, unpointed, close and carry, one Active, velocity, days left, overdue
tests/test_core.py                         registered entities in order; config int keys
tests/test_generate.py                     registered tables; the two diagrams and sprint_report
tests/test_transfer.py                     schema_version 2, four entities in a dump, four sheets in the workbook
tests/test_gui.py                          SCREENS/TITLES of seven; board fill, point, close; tracker panes save; dashboard tile
tests/fixtures/tracker_2026-10-28.txt      a copy of the source file with the byline replaced by the role
kletz.example.toml, README.md, CHANGELOG.md, docs/plan.md
../asi_fusa_tools/ASI_FUSA_TOOLS.md        plans table row, version ladder row 0.8.0
```

No change to `storage/`, `repositories/`, `models/`, `io/` (the loops over the registry already do
the work), `gui/theme.py`, `gui/palettes.py`, `gui/entity_screen.py`, `gui/matrix_screen.py`,
`gui/jira_live_screen.py`, `gui/jira_comments_window.py`, `services/jira_service.py`, the
Safety Plan entity or its 63 columns, or `../asi_hopper`.

## 6. Tests

**Grammar (`tests/test_tracker.py`).** `parse(render(x)) == x` on a built tracker with two sprints,
three weeks, every section kind and every item kind; `render` of an empty tracker is the three
header lines and the TIMELINE scope line; a sprint heading with a phase outside the lookup raises
`CommandError` with its line number; a week outside its sprint's dates warns and imports.

**Import of the real file.** On `tests/fixtures/tracker_2026-10-28.txt`: the counts of phase 2's
"done when"; the four targeted deliverables matched to rows 1, 4, 6 and 7 by title; the Rod DeMay
meeting is a Meeting item; the two `Ask:` lines are Question items (`TOD/PRD document`, row 5, is
one of them, not a Deliverable item, since it carries no target); `HWL-2620` and `HWL-2652`
are Jira items with `Note: no FuSa impact`; a second import reports `unchanged` and the audit log
gains nothing; mode `merge` on a file with one extra week adds one week and touches nothing else.

**Round trip.** `tracker build history --as-of 2026-10-28` after the import equals the fixture
byte for byte once the generated sprint line is removed; `tracker build week` equals the fixture's
first 113 lines (header, timeline, the Phase 3 block through the end of its Jira section). With
every item pointed, the sprint line reads `Sprint: 10 points capacity, …` and each Jira item has a
`Points:` line.

**Rules (`tests/test_sprint.py`).** Committed, done, unpointed and days left on a seeded sprint;
points 0, 11 and `"three"` rejected by `coerce` with the field named; committed 12 of 10 is a
warning on `point` and on `board`, and the Result is still `ok`; `start` while another sprint is
Active fails; `close` carries two open items into a new sprint 3 (dates 11/10 to 11/24, capacity
10, status Active), sets `carried_from`, leaves the originals as Carried, freezes `done`; velocity
is `no closed sprint`, then the mean of three; closing with an unpointed item warns by title;
`close` of a Planned sprint fails.

**Jira (`tests/test_tracker.py`, replay gateway, skipped without the fixtures).** `build --jira`
with a sprint holding `HWL-2572` updates its `jira_line` from the recorded search and leaves an
unrecorded key as last seen with one warning; no session → one warning, the file builds; the
database has no table the registry did not declare and the audit log has one `generate` entry.

**Core, transfer, generate.** The registered-entities and registered-tables tests assert the
four-entry list; a dump carries `schema_version == 2` and the four entities; `export excel`
writes four sheets with the source headers and `import excel` reads them back; `import asi_kletz`
still imports none of the generator libraries; `sprint_burndown` needs `sprint`, `velocity` needs
nothing, `sprint_report` builds the triplet with two figures.

**GUI (`tests/test_gui.py`).** The seven screens in order; the board fills from `sprint board`,
pointing an item through the form calls `sprint point`, the capacity label reads `9 / 10`,
`Close sprint` calls `sprint close` and the picker moves to sprint 3; the tracker screen's
Outcomes pane saves through `update week`; the dashboard tile reads the Active sprint; a theme
pick keeps the selected sprint (held on the window, as `jira_live` is).

## 7. Rejected alternatives

- **Keeping the text file as the truth and parsing it on every build.** Then "integrate" means
  nothing: the tool would print back what it read, points and carry-over would have to be typed
  into the text by hand, and a typo would be a parse failure at build time rather than a form
  validation. The file is a fine format and a poor database.
- **One `week` row with five multiline columns.** Fewer rows, but a section's text would be an
  Excel cell of forty lines, the form would be five tall boxes, and the Jira section, which the
  tool builds, would sit beside prose the engineer types. One row per section keeps the sheet and
  the form honest.
- **Sprints in `kletz.toml` as `[[sprint]]`, like `[[revision]]`.** A revision is issued a few
  times a year by hand; a sprint is started and closed from the window every two weeks, carries
  items and a velocity, and must be listable by an agent. Config is for things the tool reads,
  not things it changes.
- **Points on the Safety Plan row.** Sprint points belong to a commitment, not to a deliverable:
  the same deliverable is worked in several sprints (the HARA report ran through Phase 2 and
  into Phase 3), and the plan's 63 columns are the controlled document's, not a backlog.
- **Fibonacci points (1, 2, 3, 5, 8).** Conventional, but with a 10-point sprint an 8 is nearly
  the whole sprint and a 13 is impossible; an integer 1 to 10 says the same with one rule fewer.
- **Storing a Jira snapshot table or re-syncing `jira_line` on every build.** The first is the
  cache the 0.5.0 plan refused; the second turns history into a moving target. One explicit
  `--jira` per build, and a frozen section at close, is what a hand-kept file does today.
- **Writing the two text files as asi_gutenberg documents.** The owner asked for text files, the
  format is fixed by the existing file, and Gutenberg's triplet is md/pdf/docx. `sprint_report`
  is there for whoever wants a PDF; the tracker is plain text by design.
- **Reading `Roy's Brain.xlsx` (`tasks`, `JIRA`, `people` sheets).** That workbook is the
  sister tool's domain (working knowledge) and the tracker text already holds what the sprint
  needs. Dewey's onboarding-ingest plan may take it; this plan does not touch it.
- **An `--autoclose` that closes a sprint on its end date.** A sprint is closed by a person
  after the review, not by the calendar; the board shows `overdue` instead.
- **A new verb named `status`.** Taken; `tracker` and `sprint` say what they do.

## 8. Open items

- Whether the owner retires the one-table rule for this (section 1). If not, the plan is
  reduced to phase 2's grammar used as a one-way renderer over a JSON file in `out/`, and the
  agile rules stay out; that is a different, smaller tool, and the owner should say so before
  phase 1 starts.
- Whether a week starts on Sunday (the file's `WEEK OF 10/26 - 11/01`) or Monday; the import
  takes the file's dates, and the `tracker add` default week is `as_of` rolled back to the last
  Sunday. One toml key, `week_starts = "sunday"`, if the owner wants Monday.
- Whether `sprint close` should also set the Safety Plan row's `status` to Done when a
  Deliverable item is Done. Tempting, and the plan rows have no status today; but the plan is
  the controlled document and a sprint is a commitment. Not in this plan; a later one can add
  `--update-plan`.
- Whether the companion `Wheel Loader FSE onboarding, status.txt` should be a third build kind
  (`tracker build onboarding`: DONE / WAITING / OPEN QUESTIONS from items of kind Meeting and
  Question). It is a subset of the week file; decide after a sprint of using the week file.
- Whether `tracker build --jira` should also pull comments for the sprint's keys into the note.
  No: the note is the engineer's reading, and comments have a window of their own.
- Whether the Sprint Board's three columns should be drag-and-drop. Tk can do it; a status
  combobox in the form does the same in less code. Start with the form.
- The 0.8.0 row in the version ladder leaves the Dewey column empty, as 0.7.4 did; if the owner
  wants Dewey's `tasks` sheet to become sprints too, that is a Dewey plan with the same
  vocabulary, shared as a convention, never as code.

*Written 2026-10-28.*
