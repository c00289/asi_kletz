# Changelog

All notable changes to ASI Kletz are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Pre-1.0 releases may break anything.

## [Unreleased]

### Planned
- Approval mode: human confirms agent commands before they commit (behind `remote_guard`).
- `fill` / `submit` / `cancel` puppeting of the Safety Plan form; a `View > Automation` submenu;
  long polling on `/events`.
- Excel import diff preview; date picker widget.

## [0.11.3] - 2026-10-28

The owner, 2026-10-28: "the Safety Plan must not have the right pane because it is redundant with the
Safety Plan Matrix; remove the redundant right pane from the Safety Plan screen; make it like it never
happened." Schema version unchanged (6).

### Changed
- **The Safety Plan screen is one `ttk.Treeview`** (`gui/entity_screen.py`): no `FrozenPane`, no sash,
  no `Columns` selector (`ALL_COLUMNS`, `column_groups`, `columns_box`, `set_columns`, `_shown`,
  `FROZEN`, `IDENTITY` are gone). `columns` is every visible non-flag field minus the handles and,
  on a stacked entity, minus the three stacked fields; the stacked `plan` column comes first on the
  tree. A flag has no column on this screen: the Safety Plan Matrix is where the flags are read and
  toggled; the form's flag groups still edit them. The vertical and horizontal bars, the heading
  hint, the sort (and `plan` back to plan order), the stripe and the group tags are as before.
  `FrozenPane` stays in `gui/screens.py` for the Matrix.

### Tests
- The frozen-pane tests now run on the Matrix; the Safety Plan tests expect the twelve columns, no
  `pane`, no `columns_box`.

## [0.11.2] - 2026-10-28

The owner, 2026-10-28: "add the beginning of sprint and end of sprint to the right of the sprint
column." Schema version 5 → 6.

### Added
- **`sprint_start` and `sprint_end`** on `safety_plan_row`, DATE, calculated, right after `sprint`
  (`schema/definitions.py`): the dates of the sprint the deliverable finishes in. `Schedule.spans`
  carries them out of the pure scheduler; `PlanScheduleService.recompute` writes the four calculated
  fields together (`CALCULATED`), the guard refuses them by hand (`CALCULATED_RULE` reworded), the
  schedule table prints them, the form shows them read-only, the workbook and the JSON carry them
  (69 headers, `uid` last), the import ignores them with the one warning.

### Tests
- `test_sprint_start_and_end_follow_the_sprint`; the field counts (69 / 68 visible / 63 source), the
  table's columns, the read-only widgets.

## [0.11.1] - 2026-10-28

The owner, 2026-10-28, on the JIRA Live Data screen's "could not connect" (a rejected Atlassian
session, asi_hopper 0.1.5): "what if the refresh action included running the command so the user
doesn't have to; if the tool could open the browser window, bonus." Schema version unchanged (5).

### Added
- **`jira login`** (`services/jira_service.py:JiraService.login`, `commands/jira.py`): clears the
  stored Atlassian session (a rejected one keeps a stale client registration) and opens one
  interactive asi_hopper, whose OAuth flow opens the browser and waits for the approval; the
  account comes back. A failure is `Sign-in failed: <reason>`.
- **Refresh signs in on a rejected session** (`gui/jira_live_screen.py`): `fetch(user=True)` marks a
  person's Refresh; when its `jira live` fails with asi_hopper's "no Atlassian session" text,
  `_sign_in` runs `jira login` on the worker thread (`BackgroundFetch` now keeps its `args`, so the
  poll tells a login from a fetch), the status line says `Signing in to Atlassian … approve in the
  browser, the fetch follows`, and `_apply_login` starts the fetch again on success or shows
  `Sign-in failed: … · press Refresh`. One sign-in per Refresh (`_login_tried`, reset by a fetch
  that succeeds); the opt-in first-show fetch calls `fetch(user=False)` and never opens a browser,
  which keeps the family's "never connects on its own" rule.

### Tests
- `test_login_clears_the_session_then_signs_in_in_the_browser` (service, with a fake interactive
  Hopper), `test_refresh_on_a_rejected_session_signs_in_then_fetches`,
  `test_refresh_sign_in_failure_shows_the_reason_and_offers_refresh`,
  `test_a_second_rejection_in_the_same_refresh_is_offline_not_a_loop`,
  `test_the_first_show_fetch_never_signs_in`; `FakeRun` answers `login` and can fail `live` per call.

## [0.11.0] - 2026-10-28

Points on the Safety Plan, and a sprint and a deadline calculated from them: `docs/plan-points-plan.md`,
implemented in four commits, one per phase. The owner, 2026-10-28: "the safety plan row details screen must
have a space to put in the number of points in a sprint; this means that the expected duration and deadline
can now be updated with real data, becoming read only: the expected duration and deadline field is now a
calculated field; another calculated field would be sprint, which tells you which sprint this deadline belongs
to; when displaying the number of points switch to some default value enforced globally, and if the user adds
or removes points the GUI tells you there is a default number of points and what that is." Schema version
4 → 5. The sprint rule (10 business days, 8 points fixed, consecutive sprints) is honoured as in 0.10.0.

### Added
- **Three fields on `safety_plan_row`, after the deliverable** (`schema/definitions.py`): `points` (INT,
  `Points`, editable, a positive integer, empty means the default), `default_points` (INT, `Default points`,
  set by `plan weights load` only), `sprint` (INT, `Sprint`, calculated). `deadline` keeps its name and the
  owner's header `Expected Duration/Deadline` (the import maps by it) and is calculated: the end date of the
  sprint in which the deliverable's last point lands. `FieldSpec.calculated`, `readonly`, `source` and
  `default_from`; `FieldSpec.editable`; `EntitySchema.editable_fields`, `calculated_fields`, `source_fields`.
  `DEFAULT_POINTS = 2`, the floor; `default_points` in `kletz.toml` overrides it (`Brain.default_points`, in
  `status`, in `kletz.example.toml`).
- **The scheduler** (`generate/plan_schedule.py`, pure): `schedule(rows, sprints, items, floor)` walks the
  plan in plan order over the chain (the Active sprint, else the first Planned, and every later one that is
  not Closed), each sprint's free capacity being `capacity_of` minus the points of its committed items that
  are not Carried; weight is `points`, else `default_points`, else the floor; a Done row keeps what it has;
  Blocked, Alternative and Out-of-Scope get nothing; a deliverable with a sprint item (kind Deliverable,
  `plan_row`) in sprint n never finishes before n; the weight is poured into successive sprints and the
  finishing sprint's `end` is the deadline; when the chain runs out the row gets nothing and a warning names
  it (`row 12 "FTA/FMEA analysis" needs 8 more point(s): the sprint chain ends at Sprint 77; run sprint plan`).
- **The recompute** (`services/plan_schedule_service.py`): writes `sprint` and `deadline` where they changed,
  through the repository, one audit entry `schedule` with the count and the warnings, the event
  `plan.scheduled`; idempotent. It runs through `EntityService.after`, a new hook called once after a
  committed create, update, delete or `load_rows`, attached by `Brain.service` to the plan, sprint and
  sprint-item services; `sprint close`, `sprint plan` and `holiday load` run inside
  `PlanScheduleService.deferred()` and recompute once; `Brain.__init__` recomputes once on open
  (`migration["scheduled"]`). The recompute's writes fire no hook and a flag refuses re-entry.
- **The `plan` verb** (`commands/plan.py`): `plan schedule` recomputes and prints the table (id, order,
  deliverable, points, default, weight, source, sprint, deadline, status, warnings, unscheduled); `plan
  weights load <file>` sets `default_points` from a JSON list of `{id, order, deliverable, points[, uid]}`,
  matching by uid when the file has one, else by id, audited once as `weights`, reporting `set`,
  `unchanged`, `unmatched`, then recomputes.
- **The panel's record**: `docs/deliverable-points.md`, copied unchanged (three estimators, a fourth
  deciding; 174 points), and `data/deliverable-points.json`, its machine form (48 rows: id, order,
  deliverable, points). The README says where the defaults came from and that re-running the panel is a diff
  against the record.
- **The form** (`gui/widgets.py`, `gui/entity_screen.py`): `PointsWidget` shows the row's default greyed as
  a placeholder while empty (the row's `default_points`, else the floor), says `default 3` beside the entry
  the moment the typed value differs, and returns to the default when cleared (`points = None`);
  `ReadOnlyWidget` (an entry in state `readonly`, copyable) for Default points, Sprint and Deadline;
  `form_data` sends the editable fields only; `_hand_defaults` gives the Points entry the row's default on
  select and the floor on New. The table shows the four columns, fitted as usual; the Matrix is unchanged.

### Changed
- **`deadline` and `sprint` are refused by hand** (`PlanScheduleService.guard`, the plan service's guard):
  `update safety_plan_row n --set deadline=... / sprint=...` and a create carrying either answer `deadline
  and sprint are calculated from points and the sprint chain`; `--set default_points=` answers
  `default_points is set by plan weights load (the estimation panel's record)`; `points` must be a positive
  integer, empty clears it.
- **The files** (`services/entity_service.py:load_rows`): the workbook and the dump carry the four fields;
  the import takes `points` and `default_points`, strips `sprint` and `deadline` from every row that is not
  Done, recomputes, and warns once when a file value differed (`2 row(s) carried a sprint or deadline that
  differs from the calculated value; the file's values were ignored`); a Done row keeps the file's deadline,
  it is history (the owner's `Phase 1 exit`).
- **The owner's sheet test** (`test_source_workbook_columns_match_the_schema`) compares the sheet's headers
  with `source_fields` (the 63 columns of the source sheet: not the uid, not the three new fields) and drops
  a trailing `uid` header, which the sheet carries since the 0.9.x export wrote it hidden.
- The document's "Open deliverables without a date" paragraph no longer calls the deadline free text: such a
  row is one the sprint chain does not reach.
- The seeded test fixture writes row 1's `Phase 1 exit` through the repository, the way an import does;
  tests that wrote `deadline` as a free field write `work_product_location` or `gate_reviewer` instead.

### Deviations from the plan, and what the design got wrong once it met the code
- **A Done row keeps the file's deadline on import.** The brief said the import ignores `sprint` and
  `deadline` outright; a Done row has no calculated value (the scheduler leaves the past alone), so ignoring
  the file would erase the owner's `Phase 1 exit` on every import. The import keeps them on Done rows and
  strips them on the rest.
- **A create carries every field.** `coerce_row` fills the absent fields with `None` on a create, so a guard
  that refuses the presence of `deadline` refused every create; the guard refuses a value on a create and a
  presence on an update.
- **The committed item's points double count.** A deliverable's own sprint item (kind Deliverable, 4 points
  in Sprint 3) both pins the deliverable to Sprint 3 and takes 4 of its 8 points, so a 7-point deliverable
  pinned there finishes in Sprint 4. The brief asked for both rules; the plan's open question 1 records the
  alternative (subtract the item's points from the deliverable's weight) for the owner's call after the first
  schedule is read.
- **The owner's sheet carries the uid column.** The sheet regenerated by 0.9.x has the hidden `uid` last; the
  source-columns test drops it before comparing.
- **`form_data` moved into phase 1.** The form sent the calculated values and every save was refused the
  moment the guard existed; the editable-fields rule (phase 3 of the plan) shipped in the phase 1 commit, the
  widgets in phase 3.
- `generate/plan_schedule.py` and `services/plan_schedule_service.py` are the names the plan left open;
  `EntityService.after` is the hook the recompute needed (the plan allowed either the bus or a hook).

### Tests
- 285 → 298: the scheduler (plan order, a deliverable spanning two sprints, a committed item pinning
  the start, Done consuming nothing, the excluded statuses, capacity minus committed points, the chain running
  out, the weight sources, the chain's start); the recompute after a points change, an item, a close, a plan, a
  delete, with one audit entry per change and none when nothing moved; the refused `deadline`, `sprint`,
  `default_points` and non-positive points; `plan weights load` on the seeded fixture (3 set, 45 unmatched, a
  second load unchanged) and by uid before id; the files (67 headers, points and defaults kept, the one import
  warning, a Done row's history, the dump carrying everything); the form (placeholder, caption, clearing, the
  read-only fields, `form_data`, New, the Matrix unchanged); the 0.8.4 fixture opening with the three columns
  added and a first recompute that writes nothing.

## [0.10.0] - 2026-10-28

The sprint planner, holidays and the capacity rule: `docs/sprint-planner-plan.md`, implemented in four
commits, one per phase. The owner's rule, 2026-10-28: "A sprint spans 10 business days. Monday to Friday
count; weekends and holidays do not, so a sprint that contains a holiday ends one calendar day later per
holiday. Dates move as holidays become real; the cadence does not. Capacity is 8 points per sprint, company
policy (8 productive days of the 10). Holidays never reduce points. Sprints are consecutive with no gaps,
numbered across the programme (SPRINT n); the chain continues from Sprint 2 (2026-10-27 to 2026-11-10). We
do not know the work yet: future sprints are empty, Planned, with no lifecycle phase, and will be adjusted
as dates become real." And, the same day: "every single sprint except the one in the past is 8 points; set
this as a global value that is fixed." Schema version 3 → 4.

### Added
- **The `holiday` entity** (`schema/definitions.py`): `date` (required), `name` (required), `status`
  (`holiday_status`: `assumed` / `confirmed`), `note`, the hidden `uid`; sheet `Holidays`; `order_by` date;
  fifth and last in `ALL_ENTITIES`, so it has the CRUD verbs, a place in the dump and the workbook and, through
  the generic `EntityScreen`, a **Holidays** screen registered after Weekly Status (`gui/screens.py`; no stack,
  so no frozen column). **`holiday load <file>`** (`commands/holiday.py`, `services/holiday_service.py`) upserts
  a JSON list of `{date, name, status[, note]}` by date and name, the whole file validated before anything is
  written. **`data/us-holidays-2026-2029.json`**: 52 weekday holidays (US federal 2026 to 2029, observed dates,
  plus the day after Thanksgiving and Christmas Eve marked `(company, assumed)`), every row `assumed`, copied as
  given.
- **Business days** (`tracker/business_days.py`): `is_business_day`, `next_business_day`, `add_business_days`,
  `business_days_between`, `holidays_within`; pure functions over dates and a collection of holidays.
  `sprint_queries.holiday_dates` reads the table as `{date: name}`, any status; two holidays on one date are
  one day off with both names.
- **The planner** (`services/sprint_service.py:plan`, `sprint plan [--until | --years 3] [--days 10]
  [--replan]`): the next sprint starts on the first business day after the highest-numbered sprint's end and
  ends on its `days`th business day, `SPRINT n`, no lifecycle phase, capacity 8, Planned, the goal
  `Holidays: <name> (<m/d>), ...` when it contains holidays; sprints are added while they start on or before
  the horizon; an existing sprint is never touched; `--replan` recomputes the dates of the Planned sprints
  after the active one (after the last Closed one when none is active) from the holiday table, never a
  started or closed sprint, and rewrites a goal only when it is empty or a `Holidays:` line the planner
  wrote. The report: `added`, `replanned`, `first`, `last`, `until`, `days`, `capacity`, `holidays` (every
  holiday in the planned span). The event `sprint.planned`.
- **The capacity rule, enforced** (`schema/definitions.py:SPRINT_CAPACITY`, `CAPACITY_RULE`;
  `services/sprint_service.py:guard`, `enforce_capacity`; `services/entity_service.py:guard`;
  `generate/sprint_queries.py:capacity_of`; `brain.py`): 8 is a fixed global; a create of a sprint that is
  not Closed without a capacity gets it, a create or an update with another value is refused with the rule's
  text (`EntityService.guard`, a per-entity check `Brain.service` attaches to the `sprint` service); on open,
  after `ensure_schema` and `stamp_uids`, every sprint that is not Closed and differs is set to 8 in one
  transaction, audited once as `enforce_capacity` (actor `system`, the count and the ids) and reported in
  `brain.migration["capacity_enforced"]`; the board, the dashboard strip, `point` and the tracker's sprint
  line read `capacity_of`: 8 for any sprint that is not Closed, the stored value for a Closed one. The
  `capacity` field stays for that history (Sprint 1 keeps 10).
- `status` reports `config_warnings`; `load_config` records one for a `sprint_capacity` key.

### Changed
- **`sprint_capacity` is no setting and `--capacity` is gone** (`brain.py`, `commands/sprint.py`,
  `kletz.example.toml`): the key is ignored with a warning naming the rule, logged and in `status`; `sprint
  start` and `sprint plan` have no `--capacity`; a sprint is created with 8. Why: an option that is always 8
  is a trap, and the owner asked for a global value that is fixed.
- **`sprint_days` means business days, 10** (`schema/definitions.py:SPRINT_DAYS`, `brain.py`): `sprint
  start` ends a sprint on its `sprint_days`th business day over the holiday table (a `--start` or `--as-of`
  given is kept as the first day); `sprint close` opens the next sprint on the first business day after the
  closed one's end, `sprint_days` business days long, capacity 8, instead of on the closed one's end day
  with its calendar length and capacity (0.8.0); a Planned next sprint that already has dates (the planner's)
  keeps them. The `sprint` verb's help carries the rule verbatim.
- **The tracker text** (`tracker/format.py:render`, `timeline_sprints`, `has_content`, `timeline_bullet`):
  the `TIMELINE` prints the Closed and Active sprints as before and, of the Planned ones, those with weeks
  or items plus the next one, one bullet; a Planned sprint with no weeks and no items prints no `=====`
  block. This is a deviation from 0.8.0's "every sprint" rule: with seventy-odd planned sprints the text
  would have been mostly rules. A sprint without a lifecycle phase prints its bullet as
  `- Phase to be assigned: planned. Sprint 3: 11/12 - 11/25.`; the parser ignores a bullet it does not
  recognise, and such a sprint, having no block, lives in the database and is never re-created by an
  import. The `week` build, the Sprint Board picker (every sprint, the active one first) and the dashboard
  strip are unchanged.
- The real tracker file, imported, gives Sprint 2 capacity 8 (the rule, whatever the file said); the test
  fixtures of the board and the window carry 8 and 3 + 3 + 2 points.

### Deviations from the plan, and what the design got wrong once it met the code
- **The capacity addition** reached the implementing agent before phase 1 was committed, so it is in the plan
  (section 3.4) and in phase 2, not a phase of its own.
- **The horizon counts from the last started sprint.** "Three years from the last sprint's end" read
  literally made every run extend the chain by three more years (the last sprint was the one just planned);
  `years` counts from the end of the last Active or Closed sprint, so a second run with the same horizon
  adds nothing, which is what "idempotent" asked for.
- **The history did not skip empty sprints before.** The design said the history "still prints only
  sprints that have weeks or items"; `format.render` printed a block for every sprint. Both the TIMELINE
  rule and the block rule are new in this release.
- **The sample first start is a holiday.** The design expected the first planned sprint to start 2026-11-11;
  that is Veterans Day in the seed, so with the holidays loaded it starts 2026-11-12 (and 2026-11-11 without
  them). The tests pin both. Three years add 79 sprints without holidays and 75 with the seed.
- **The holidays honoured are the span's**, gaps included: a holiday between two sprints (Veterans Day moves
  a start without being inside any sprint) is honoured too, so the report lists it.
- **Two holidays on one date** (an observed Christmas on the company's Christmas Eve, twice in the seed) are
  one day off in the calendar with both names in the goal; the seed's 52 rows are 50 dates.
- **A planned sprint whose holidays fall in the gap before it** (Sprint 6 after Christmas Eve and Christmas
  Day are confirmed) has no `Holidays:` goal: the goal names the holidays a sprint contains, and the gap is
  what moved it.
- **The Holidays screen's frozen pane is empty** (no stack, no identity column); the sash sits at zero.
- `holiday_dates`, `capacity_of` and the `ref` of the `holiday` verb's file argument are names the plan left
  open; `EntityService.guard` is the hook the capacity rule needed and the plan did not foresee.

### Tests
- 264 → 285: the calendar (a plain week, a weekend, one holiday, a holiday on a Monday, the Christmas
  and New Year span); the seed loads 52 rows and loads again unchanged, the upsert by date and name, a bad
  file or row is an error; the five-entity lists and the 0.8.4 fixture gaining the `holiday` table; the
  planner (79 / 75 sprints, the first and last dates, the Christmas sprint's goal and span, `--until`,
  `--days 5`, a second run adds 0, `--replan` after a holiday becomes real with the active, the closed and a
  human goal untouched, the errors); the rule (`sprint start` ends 2026-11-09 from 2026-10-27 with capacity 8
  and no `--capacity`, `sprint_days = 7`, the config warning, the open-time step on a database written before
  the rule, the refused update and create, the board reading 8 whatever the row says); the TIMELINE naming
  the next planned sprint only and no block for an empty one, in the grammar and from a database; the
  Holidays screen in the navigation list after Weekly Status.

## [0.9.1] - 2026-10-28

The owner, 2026-10-28: "make it so that the left pane in Safety Plan and the left pane in Safety Plan
Matrix are both as wide as the longest row of each screen's left pane." Schema version unchanged (3).

### Changed
- **The frozen pane opens at its full fitted width** (`gui/screens.py:FrozenPane._place_sash`): the
  sash lands on `fitted_width()`, the sum of the left tree's fitted columns, which `fit_columns` sizes
  to the longest row (the stacked plan text) and the heading. `SASH_SHARE` (0.45, 0.7.3) is gone;
  `RIGHT_MIN = 120` px is the one cap, so the scrolling pane keeps room for its flags and bar; a
  split narrower than that leaves the sash at 1, never 0 (a weight-0 pane never grows back from 0).
  Dragging still clips a tree and never changes a column width.

### Tests
- `test_frozen_pane_split_is_draggable`: the sash arithmetic at 1000 px (the full fitted width),
  400 px (the reserve wins) and 100 px (the sash stays at 1).

## [0.9.0] - 2026-10-28

Every row has a hidden identity (`uid`), and no table shows `id` or `order`: `docs/hidden-identity-plan.md`,
implemented in four commits, one per phase. The owner, 2026-10-28: "it is obviously important that all
objects have some internal guid that is not visible but serves for traceability; then of course we want to
preserve the order of elements in a table; but the leftmost columns `order` and `id` are vestigial."
Schema version 2 → 3. Section 3.1 of the plan (the uid value, where a file carries it, how an import
matches it) is shared byte for byte with asi_dewey 0.9.0, because a Kletz dump or workbook is imported
into Dewey.

### Added
- **`uid` on every entity** (`schema/fields.py`: `UID`, `UID_PATTERN`, `new_uid`, `normalise_uid`,
  `is_uid`, `uid_field`; `schema/definitions.py`): the last field of `safety_plan_row`, `sprint`,
  `sprint_item` and `week`, `FieldType.TEXT`, header `uid`, `hidden=True`. The value is
  `str(uuid.uuid4())`; coercion accepts the canonical form, normalises another case or braces
  (`{3F25...}`, as Excel prints a GUID) and rejects anything else with the field named
  (`uid: 'not-a-uid' is not a uid`). `FieldSpec.hidden` (in `to_dict`, so the registry fingerprint
  moved) and `EntitySchema.visible_fields` (the tuple the window uses; `fields` stays the full one the
  storage and the transfers use).
- **Assigned once, immutable, unique, readable** (`services/entity_service.py`,
  `repositories/sql_repo.py`, `storage/sqlite.py`): `create` sets the uid when the row has none and keeps
  one handed in; `update` with the stored value is a no-op, with another value a
  `ValidationError("uid is immutable")`, with an empty one leaves the stored value alone (a form or a
  file that does not carry it); `CREATE UNIQUE INDEX IF NOT EXISTS ix_<table>_uid` after the column
  exists, so two rows cannot share a uid (the service reports the refusal as a failed `Result`);
  `SqlRepository.get_by_uid`, `EntityService.get_by_uid` and `EntityService.resolve(ref)` (an integer or
  digits is an id, a uid is looked up, an unknown uid is `NotFound`, anything else a `CommandError`).
- **Stamped on open** (`storage/base.py`, `storage/sqlite.py`, `brain.py`): `Storage.stamp_uids(registry)`
  gives every row whose uid is NULL or empty a fresh one, one `UPDATE ... WHERE id = ?` per row in one
  transaction, audited as `stamp_uids` (actor `system`) with the count per table; `Brain.__init__` calls
  it after `ensure_schema` and reports `migration["uids_stamped"]`. A 0.8.x `kletz.db` opens as 0.9.0
  with every row identified and nothing else changed, `updated_at` included. `SCHEMA_VERSION = 3`.
- **In every file** (`io/exporters.py`): the JSON dump carries `uid` as any key; the workbook writes it
  as the last column of every sheet, headed `uid`, with `column_dimensions[letter].hidden = True`, so the
  sheet reads as before and still round-trips; the import maps it by header like any field.
- **A uid where an id is expected** (`commands/crud.py`, `commands/base.py`, `automation/cli.py`): the
  `id` positional of `get`, `update` and `delete` is of type `ref` (a string on the command line); the
  service resolves it, `delete` answers with the resolved id, `list --filter uid=...` works as for any
  field, and the automation server's `/execute` runs the same verbs, so an agent passes a uid there too.
- `tests/fixtures/kletz-0.8.4.db`: a 0.8.4 database (three plan rows, one sprint, no uid column) made
  with the 0.8.4 code for the open-and-stamp test; `.gitignore` keeps it tracked under the `*.db` rule.

### Changed
- **`load_rows` matches by uid first** (`services/entity_service.py`, section 3.1): a row whose uid is in
  the table is an update of that row, whatever its id in the file, in every mode; otherwise a row whose
  id exists is an update by id (merge only, as before; the file's uid, when it has one, replaces the
  stored one, which is how a sibling's cached rows take this tool's uids); otherwise an insert that keeps
  the file's uid when present and the file's id in merge mode. A row without a uid (a 0.8.x file) keeps
  the stored uid on an update and is stamped on an insert. `replace` wipes first and keeps the file's
  uids. So `append` of a dump whose rows are already in the table updates them instead of doubling the
  plan; `append` of a file without uids inserts, as before.
- **No table shows `id` or `order`** (`gui/entity_screen.py`, `gui/matrix_screen.py`, `gui/dashboard.py`):
  the Safety Plan table's columns are the visible fields minus the handles (`HANDLES = ("id", "order")`),
  frozen `plan` alone (`FROZEN = (PLAN,)`; `IDENTITY = STACKED` for an entity without the stack); the
  matrix freezes `plan` alone (`FIXED = (PLAN,)`, `FIXED_WIDTHS = (360,)`; `SEARCHED` keeps `order`, so a
  typed number still finds the row); the dashboard's open deliverables are `deliverable`, `status`,
  `deadline`, still in plan order; the audit table keeps `entity_id`. The tree iids stay the ids, sorting
  by `plan` returns to plan order, the status bar still says `Safety Plan Row 2 selected`.
- **The form** shows every visible non-group field (`order` included, never `uid`;
  `WidgetFactory.create` refuses a hidden field) and the details frame names the selected row:
  `Safety Plan Row details · row 2` (`EntityScreen.details_title`), reset by New, Duplicate, Delete and
  a refresh that loses the selection.
- The `schema` command lists `hidden` on every field; the workbook's visible columns and their order,
  the JSON shape apart from the new key, the command vocabulary, the audit log, the events, the tracker
  text, the sprint rules, the family lock and the automation server's shape are unchanged.

### Deviations from the plan, and what the plan got wrong
- **Phase boundaries.** `load_rows` by uid (phase 2) and the hidden field's absence from the form and the
  table (phase 3) shipped in the phase 1 commit: once the field existed, the suite could not stay green
  without them (a dump appended onto itself hit the unique index; the form would have shown a uid
  entry). The commits are still one per phase; those two pieces are in the first.
- **`stamp_uids` audits only tables that had rows to stamp.** The plan says "audited once per table with
  the count"; with four entities, auditing zero counts would add four entries to the audit log at every
  launch of an already-stamped database, and the dashboard's "Recent changes" would open on them. On
  the fixture that is two entries (`safety_plan_row` 3, `sprint` 1), none for the empty tables, none on
  the second open; `brain.migration["uids_stamped"]` still reports every entity.
- **59 displayed columns, not 58.** Section 6 expects the Safety Plan's right tree to display 58 columns
  ("59 minus `order`"), but `order` was a frozen column in 0.8.4, never displayed on the right: the tree's
  columns go from 64 (`id` + 63) to 62 (63 visible minus `id` and `order`), and the displayed count stays
  59 (62 minus the three stacked fields). The test pins 62 columns, 59 displayed, `uid` nowhere.
- **The automation server has no row endpoints.** Section 3.1, phase 2 and the files-touched list name
  "the server's row endpoints"; the server (`automation/server.py`) has `/status`, `/execute`,
  `/screens`, `/screen`, `/events` and `/quit`, and rows are read and written through `/execute` with the
  verbs. The verbs resolve the ref, so the server is unchanged; `test_server.py` drives `get`, `update`
  and `delete` by uid through `/execute`.
- **The real workbook has no uid column.** `test_source_workbook_columns_match_the_schema` compared the
  owner's sheet with every field; it now compares with `visible_fields` (63), which is what the plan says
  the sheet's visible columns are. The owner's `kletz.xlsx` is not touched; the next `export` writes the
  hidden column.
- **`.gitignore`** gained `!tests/fixtures/kletz-*.db`, which the plan's file list does not mention: the
  `*.db` rule exists for the owner's runtime database and would otherwise refuse the fixture.
- **Service signatures.** `EntityService.get`, `update` and `delete` take the `ref` themselves (an int or a
  string) and `delete` returns the id; the plan put the resolution in the commands. Same behaviour, one
  place; `sprint_service` and the window keep passing integers.

### Tests
- 254 → 264 (phase 1: +5, phase 2: +3, phase 3: +2, plus the rewritten expectations): every entity ends
  with the hidden uid and the fingerprint moved; uid values, normalisation and coercion; the service
  assigns, keeps, protects and resolves; the 0.8.4 fixture opens with the column and the index on every
  table, every row stamped, two audit counts and nothing else changed, and stamps nothing the second
  time; the plan sheet has 64 headers, the last `uid`, hidden on every sheet; export → import on a fresh
  database keeps every uid; a dump with every id shifted by 100 merges as 3 updates and 0 inserts; a
  sibling's rows take the file's uids; a 0.8.x dump and a 0.8.x workbook still import and the new rows are
  stamped; `get`, `update`, `delete` by uid on the API, the CLI and through `/execute`, an unknown uid is
  `NotFound`, `list --filter uid=...`; no tree on any screen has a column named `id`, `order` or `uid`
  (one test walks every screen), the frozen pane holds `plan` alone, the matrix's `FIXED` is `(plan,)`,
  the dashboard's open table has three columns, the form has `order` and no `uid`, the details title
  names the selected row, and selecting, saving, duplicating and deleting work as in 0.8.4.

## [0.8.4] - 2026-10-28

The owner, 2026-10-28: "do the changes on the safety plan table too." Schema version unchanged (2).

### Changed
- **Safety Plan table stacked** (`gui/entity_screen.py`): on an entity that has `pdp_phase`,
  `lifecycle_phase` and `deliverable` the frozen columns are `id`, `order` and `plan`, the stacked
  column (`FROZEN`); the three fields stay on the right tree as hidden data columns (`tree.set`
  still answers, the Columns box never shows them), and the tree's columns are the data columns
  plus `plan`. `_populate` inserts the stack (group rows with blank data cells and the `pdp` /
  `phase` tags, deliverable rows with every data cell plus the indented, clipped deliverable) and
  styles it; selecting a group row leaves the form and `selected_id` alone; sorting by a heading
  reorders the deliverables and the stack follows (`stack` opens a group whenever the value
  changes); the `plan` heading, on either tree, sorts back to the plan's own order (status
  `Plan order`). An entity without the three fields keeps the old frozen set (`IDENTITY`).
- **Shared stacking** (`gui/screens.py`): `PLAN`, `PLAN_HEADER`, `STACKED`, `INDENT`, `PDP_TAG`,
  `PHASE_TAG`, `pdp_title`, `phase_title`, `stack`, `is_group` and `style_group_rows` moved out
  of `matrix_screen.py`, which imports them (and re-exports the names the tests use).

### Tests
- `test_safety_plan_group_rows_are_headings_not_records`; the table tests expect nine rows for
  three deliverables, the stacked column on the tree, 59 displayed columns as before, the group
  tags in front of the stripe on both trees, and the sort round trip through `plan`.

## [0.8.3] - 2026-10-28

The owner, 2026-10-28: "the safety plan matrix screens are a little crowded because we are doing
pdp phase, safety lifecycle phase and then the safety deliverables each as one column; instead
stack them." Schema version unchanged (2).

### Changed
- **Safety Plan Matrix stacked** (`gui/matrix_screen.py`): the frozen columns are `order` and one
  `plan` column (heading `PDP phase  ›  Safety lifecycle phase  ›  Safety deliverable`) instead of
  `order`, `pdp_phase`, `lifecycle_phase`, `deliverable`. `stack(rows)` turns the plan into lines
  `(iid, level, text, row)`: a PDP phase row (`pdp:<value>`, `PDP phase n`) whenever the value
  changes, a lifecycle phase row under it (`phase:<pdp>:<value>`, indented four spaces), the
  deliverable rows under that (indented eight, iid the row id). Missing phases print as
  `(no PDP phase)` / `(no lifecycle phase)` so every row has a place. Group rows have blank flag
  cells and the tags `pdp` (primary colour) and `phase` (accent colour) in the heading font, put
  in front of the stripe tag so colour and font come from the group and the background from the
  stripe; `FrozenPane.mirror` copies tags and their colours to the left tree as before. A click on
  a group row toggles nothing. The search filters deliverables and shows the group rows above
  every match. Column fitting, the frozen split, the sort and the scrolling are unchanged.

### Tests
- `test_matrix_stacks_pdp_phase_over_lifecycle_phase_over_deliverable`: the pure `stack` (order,
  a repeated phase, a row without phases) and the screen (iids, texts, blank flags, tags and
  colours on both trees, a click on a group row, the search). The two older matrix tests expect
  the new columns and nine rows for three deliverables.

## [0.8.2] - 2026-10-28

The owner's rule of 2026-10-28 on sprints: "the time from Oct 12 to 27 is a single sprint, part of
Phase 2; there is the sprint from the 12th to the 27th and now one from the 27th to Nov 10; these
are the only two sprints; there is no HARA sprint." Schema version unchanged (2).

### Changed
- **Sprint labels follow the programme-wide number.** Sprint 1 is 10/12 to 10/27 (Phase 2, Closed
  10/27); Sprint 2 is 10/27 to 11/10 (Phase 3, Active). The imported label `FINAL SPRINTS` is gone
  from the data (`update sprint`), from the week texts that name the sprint (the 10/26 Note,
  the 10/19 Outcomes, the `Sprint n target:` lines of the 10/26 Issues) and from the fixture; the
  generated `Sprint n target:` lines of the Jira items follow the label on their own.
- **The closed `TIMELINE` bullet** prints `Sprint 1: 10/12 - 10/27/2026. Closed 10/27.` (the
  label through `target_label`, then the dates), the same shape as the open and planned bullets,
  instead of the label in lower case before the dates.
- The grammar is unchanged: any label still parses, so an old file imports; the docstring example
  and the `sprint` entity description name `SPRINT 1` and `SPRINT 2`.

### Tests
- `test_tracker` builds and asserts the three sprints as `SPRINT 1` (closed), `SPRINT 2` (active),
  `SPRINT 3` (planned) and the closed bullet; the import test expects the renamed rows; the
  Weekly Status test expects the renamed Note line.

## [0.8.1] - 2026-10-28

The tracker in the window: phase 4 of `docs/weekly-tracker-plan.md`, asked by the owner on
2026-10-28 ("is this not going to be incorporated into the gui? can we see dashboard data for
where we are in sprint").

### Added
- **Dashboard**: a sprint strip under the deliverable tiles (`SPRINT`, `COMMITTED` as `n / capacity`,
  `DONE`, `TO GO`, `UNPOINTED`, `DAYS LEFT` or `overdue`, `VELOCITY`), the frame naming the active
  sprint, its phase and its dates, `No active sprint` otherwise; a click opens the Sprint Board. The
  numbers are `generate.sprint_queries.board`, the same as the verb and the tracker text.
- **Sprint Board** (`gui/sprint_board_screen.py`, key `sprint_board`, after Safety Plan Matrix): a
  sprint picker (the active one first; the pick is kept on the window as `sprint_number`, so a theme
  pick comes back to it), the goal line, a capacity bar with `committed / capacity · done · to go ·
  unpointed`, the dates, days left or overdue and the velocity, the board's warnings; three lanes
  (To Do, In Progress, Done) as tables fitted to their text, Carried items counted in the status bar;
  a form (kind, title, plan row, Jira key, points, target, note, status, order) with New, Save,
  Delete and Carry to next sprint; Start sprint, Close sprint (confirmed; the board moves to the
  next sprint), Build week and Build history in the toolbar. Every button is a verb through
  `window.run`.
- **Weekly Status** (`gui/tracker_screen.py`, key `tracker`, after the board): a week picker (the
  current week first; kept on the window as `week_start`), the Note line and the Outcomes and
  Issues panes each with a Save (`update` or `create` of the `week` row), the Jira section as the
  text prints it (read-only; a closed sprint's week shows its frozen text; a week that is not the
  sprint's newest says where the section prints), `is_dirty()` for the remote theme guard, New
  week (`tracker add` of today's Monday into the active sprint), Build week, Build history, Open and
  Open folder.
- File menu: `Build current week (tracker)` and `Build tracker history` (`MainWindow.build_tracker`),
  on the Weekly Status screen so the path shows in the status bar.
- Tests (`tests/test_gui.py`): the seven screens in order, the file menu, the dashboard strip before
  and after a sprint and across a close, the board's lanes, form, save over capacity, new item,
  carry, close and theme pick, the Weekly Status load, dirty flag, save, closed-sprint week, builds
  and Open, New week.

## [0.8.0] - 2026-10-28

The Weekly Activity Tracker and sprints: phases 1 to 3 of `docs/weekly-tracker-plan.md`, asked by the
owner on 2026-10-28 ("integrate Roy's status text file and produce both a complete historical text
file but also a version for the current week ... each sprint is 10 points, let's make this an agile
tool"). The screens (phase 4) and the family tables (phase 5) are still to come.

### Added
- Three entities in `schema/definitions.py` after the Safety Plan: `sprint` (number, label, lifecycle
  phase, start, end, capacity, goal, status Planned / Active / Closed, closed_on), `sprint_item`
  (sprint, order, kind Deliverable / Jira / Meeting / Question / Other, title, plan_row, jira_key,
  issue_type, heading, points, target, note, jira_line, status To Do / In Progress / Done / Carried,
  carried_from, done_on) and `week` (start, sprint, section Note / Outcomes / Issues / Jira, order,
  text), with the lookups `sprint_status`, `item_status`, `item_kind`, `week_section`. The generic
  CRUD, JSON dump / load and the workbook (sheets `Sprints`, `Sprint Items`, `Weekly Status`) cover
  them by registration. `SCHEMA_VERSION` is 2; a 0.7.x database gains the tables on open.
- `tracker/format.py`: the grammar of the status text, `parse` and `render`, one module for the
  importer and the builder. The engineer's file of 2026-10-28 (`tests/fixtures/tracker_2026-10-28.txt`,
  byline replaced by the role) is the specification: import then `build history --as-of 2026-10-28`
  gives it back byte for byte, and `build week` gives its first 112 lines.
- `services/tracker_service.py` and the `tracker` verb: `import <file> [--mode replace|merge]`
  (replace into an empty tracker, merge otherwise; a second import of the same file is `unchanged`
  and writes nothing), `build history|week [--out] [--jira] [--as-of]` (writes
  `tracker_history.txt` / `tracker_week.txt`, audits `generate`, publishes `generated`), `add <text>
  [--section Outcomes|Issues|Note] [--week] [--as-of]`. Jira items come from the `Jira issues`
  blocks (key, type, wrapped title, status line, note, target, points, the heading lines before a
  run of items); Deliverable, Meeting and Question items from the `Sprint n target:` and `Ask:`
  lines of the Issues text, a Deliverable matched to a Safety Plan row by title (exact, else unique
  prefix; no match is Other with a warning); the Issues text is stored without its two-space indent
  and printed with it. A Closed sprint's Jira section is stored verbatim as a `Jira` week row.
- `services/sprint_service.py`, `generate/sprint_queries.py` and the `sprint` verb: `board [n]
  [--as-of]` (capacity, committed, done, to go, unpointed, days left, overdue, velocity, warnings),
  `start [n] [--phase --start --end --capacity --goal --label --as-of]` (a new sprint, or the Planned
  one `n`; refused while one is Active), `close [n] [--as-of]` (freezes the Jira section into the
  newest week, marks open items Carried and copies them into the next sprint with `carried_from`,
  opens that sprint as Active following on in time, records `closed_on`, publishes `sprint.closed`),
  `point --item --points` (1 to the capacity, 0 clears; over-commitment is a warning), `carry --item
  [--to]`. Velocity is the mean of points done over the last three Closed sprints. The built text
  carries a generated `Sprint:` line once an item is pointed and `Points:` under each pointed item.
- `--jira` on a build: one `jira live` for the sprint's keys rewrites each item's `title`,
  `issue_type` and `jira_line` (`<status> | Priority: <p> | Assignee: <a>`); a key not returned, or
  no session, is a warning and the file still builds. Without the flag Jira is never called.
- `kletz.toml`: `tracker_title`, `tracker_byline`, `tracker_scope`, `tracker_jira_scope` (text) and
  `sprint_capacity` (10), `sprint_days` (14) (`CONFIG_INT_KEYS`, TOML integers only);
  `Brain.sprint_capacity`, `Brain.sprint_days`, `Brain.tracker`, `Brain.sprints`; `status` reports them.
- Tests: `tests/test_tracker.py` (grammar round trip, parse errors by line, year wrap, the import of
  the real file with its counts and matches, unchanged re-import and merge, the two builds against
  the fixture, points on the sprint line, `add`, `--jira` with a stubbed fetch and with none) and
  `tests/test_sprint.py` (board, point validation and warnings, one Active, close and carry, the
  velocity window, start, carry, config defaults, the CLI parser).

### Changed
- **The one-table rule is retired.** "ASI Kletz holds exactly one thing" becomes "entities are
  registered in `schema/definitions.py`; the list is the design, not a cap", the way the screen
  count was retired in 0.5.0. `test_only_the_safety_plan_is_registered` is
  `test_registered_entities_in_order`, `test_database_still_has_exactly_one_table_after_generating`
  is `test_database_has_exactly_the_registered_tables_after_generating`; `conftest.py` carries
  `ENTITIES`, `TABLES` and `SHEETS`; the dump, workbook and status assertions follow. The Safety
  Plan entity and its 63 columns are untouched.
- Deviations from the plan, recorded here as it allows: weeks start on **Monday** (the file's
  `WEEK OF 10/26 - 11/01` is a Monday), not Sunday; `People` and `Questions` are not sections of
  their own but sub-blocks kept verbatim inside `Issues` (a `Sprint n target:` under `People and
  cadence` is a Meeting item); `sprint close` always opens the next sprint, carried items or not, so
  `tracker build week` always has one; the `sprint_burndown` / `velocity` diagrams and the
  `sprint_report` document wait for phase 4 with the screens.

## [0.7.4] - 2026-10-28

The JIRA Live Data window no longer connects to Jira on its own, and a fetch no longer freezes
it. Asked by the owner on 2026-10-28 after the sister tool "ran but got stuck on jira live data":
"ensure for both tools that it does not connect automatically; ensure the timeout issue is
troubleshot and root-cause fixed". Same convention in both tools, implemented in each one's own code.

### Fixed
- The window froze for the whole of a live fetch. Root cause: `JiraLiveScreen.fetch` ran
  `jira live` synchronously on the Tk thread through `window.run_quiet`, and the house default
  is up to 2,000 issues at 50 a page, tens of seconds on a good link and minutes on a slow one,
  with any gateway wait on top (asi_hopper 0.1.4 already bounds its own waits so a call fails
  within a minute); `JiraCommentsWindow.fetch` had the same shape. Now `fetch` starts a
  `BackgroundFetch` (`gui/jira_live_screen.py`): a daemon thread that calls the new
  `MainWindow.execute_quiet(verb, **args)`, which is `Brain.execute(verb, args, actor="gui")` and
  nothing else, no status bar, no dialog, no widget. The Tk thread polls it every 100 ms with
  `after` and applies the Result on the Tk thread exactly as before (`window.jira_live`, the
  status bar's `Jira: n issues fetched` or `Error: ...`, `refresh()`), through the new
  `MainWindow.report_quiet(result)`, the status-bar half of `run_quiet`. While a fetch runs the
  Refresh button is disabled, the screen's status line says `Fetching Jira … up to 2000 issues,
  this can take a minute` (the comments window: `Fetching comments …`) and a second `fetch` is
  ignored, not queued (`fetch()` now returns `True` when it started one, `False` when ignored).
  Closing the window or rebuilding on a theme pick never joins or waits on the worker: the
  screen's `destroy` cancels its poll and the worker's Result is dropped when it lands
  (`winfo_exists()` is checked before applying). `run` and `run_quiet` call `execute_quiet` and
  then report, so every other caller is unchanged. The `jira.live` event is now published from
  the worker thread; `MainWindow._on_event` returns for that topic before any Tk call, and a
  comment there says why no other topic can arrive from a worker (`jira comments` publishes
  nothing, and nothing else runs off the Tk thread).
- The screen connected to Jira merely by being opened: `jira_live_autofetch` defaulted to true,
  so the first show started that synchronous fetch. The first show now paints
  `No fetch yet · press Refresh` and does nothing else unless the key is explicitly `true`
  (`on_show` compares with `is True`; a non-boolean value never counts).

### Changed
- The house JQL now fetches only the issues that involve the person running the tool, past and
  present: `project = HWL AND (assignee = currentUser() OR reporter = currentUser() OR watcher = currentUser()) ORDER BY updated DESC`
  (it was every issue of the project). `jira_live_jql` in `kletz.toml` still overrides it.
- `jira_live_autofetch` defaults to **false** (`services.jira_service.AUTOFETCH_DEFAULT`), in
  `brain.py`'s `load_config` docstring, `kletz.example.toml` (the key stays, as an opt-in), the
  README and `docs/jira-live-data-plan.md`.
- Tests: the JIRA screen tests stub `window.execute_quiet` instead of `window.run_quiet` (the
  `FakeRun` answers on the worker thread, passes any other verb to the real Brain, records the
  thread of each call and can hold on a `threading.Event`); the screen and the comments window
  have a test helper `wait_fetch(timeout=5.0)` that pumps `window.update()` until the fetch in
  flight is applied and returns the Result. New: the first show does not fetch by default and
  fetches once when the key is true; during a fetch the button is disabled and the status line
  says `Fetching Jira …`; a second fetch while one runs is ignored; the Result is applied on the
  Tk thread (the worker is not the main thread, `refresh()` ran on it afterwards); a screen
  destroyed mid-fetch by a theme pick, a comments window closed or rebuilt mid-fetch, and a main
  window closed mid-fetch raise nothing and wait for nothing; `run_quiet` still reports on the
  status bar; the comments window equivalents. The share-nothing tests still find no `asi_dewey`
  in `src`.

## [0.7.3] - 2026-10-28

The split between the pinned and the scrolling columns of the Safety Plan screens is draggable,
and a broken-windows sweep of the repository.

### Changed
- The two tables of `FrozenPane` are the panes of a horizontal `ttk.PanedWindow`
  (`FrozenPane.split`: `left` weight 0, `right` weight 1) instead of two grid cells, so the sash
  between them can be dragged either way. With Safety Deliverables fitted to its longest title the
  pinned side took most of a 1280 px window and left the scrolling side a sliver; now, after every
  `mirror()`, `place_sash()` puts the sash where the left tree shows its fitted columns but never
  past 45% of the split's width (`SASH_SHARE`; in an `after_idle`, so a mapped window has its
  geometry; a split not yet mapped, a screen built but not shown or a withdrawn test window,
  waits for its `<Map>`, because Tk clamps a sash set before the split has a size to 0 and a
  weight-0 pane never grows back from 0 on its own). Dragging clips a tree and never changes a
  column width. The vertical bar stays outside the split on the right, the horizontal
  bar under the right tree and follows the sash (`_align_xbar`). Both Safety Plan screens get it,
  nothing else changes for them: `screen.tree`, `pane.left`, the bars, the selection and the sort
  sync are as in 0.7.2. `fitted_width()` is the width of the pinned columns together.

### Fixed
- `.gitignore`: the family-lock pattern `*.lock` also matched `uv.lock`, the dependency lock that
  must stay tracked; `!uv.lock` says so. `out/`, the default folder of the generated views next to
  the database, is now ignored.
- `gui/transfer_screen.py`: the module docstring still explained the third frame by "the window
  has exactly four screens", a rule retired in 0.5.0.
- CHANGELOG: no compare links for 0.7.0, 0.7.1 and 0.7.2, and `[Unreleased]` compared against
  0.6.0; the 0.7.0 entry had two `### Changed` headings; a stray backtick split
  `gui/screens.py:fit_columns` in the 0.7.1 preamble.
- README: the command list lacked `session` (0.7.0); the layout tree lacked `errors.py` and
  `version.py`; the "What is in" sections stopped at 0.7.0 while the version line said 0.7.2.
- `docs/plan.md` said "0.7.0 delivered" with no delivery rows for the patch releases.
- The six plan documents stated their "today" as a live fact: "exactly four screens" (retired in
  0.5.0), "the automation server will then be the way" (it is, since 0.7.0), the 36 px flag
  columns (fitted since 0.7.1), the family document's version table with `asi_hopper` as an empty
  folder (a 0.1.3 gateway today); each now says when it was true and what replaced it.
  `escher-gutenberg-integration-plan.md` pointed at "section 3.7" for the screen rule; it is 3.8.

## [0.7.2] - 2026-10-28

The identity columns of the Safety Plan stay put while the rest scrolls sideways.

### Added
- Frozen identity columns on both Safety Plan screens. A `ttk.Treeview` cannot pin a column, so
  `gui/screens.py:FrozenPane(master, columns, frozen)` holds two in lock-step: `left` shows the
  frozen columns, `right` owns every column but displays the others, one vertical bar drives
  both (each tree's own scrolling and the wheel over either move the other), the horizontal bar
  drives `right` alone, the selection follows both ways, a left heading sorts through
  `pane.on_sort`, `set_display(names)` never shows a frozen column on the right, and `mirror()`
  rebuilds `left` from `right` after every fill or sort (the same iids in the same order, the
  frozen cells, the row tags and tag colours, the heading texts, the widths fitted with
  `fit_columns`, `stretch` off). The Safety Plan table freezes `id`, `order`, `pdp_phase`,
  `lifecycle_phase` and `deliverable` (`entity_screen.py:FROZEN`); the Safety Plan Matrix
  freezes its `FIXED` four, and a flag cell still toggles on the right, now resolved by column
  name because a `#n` index counts displayed columns. `screen.tree` is the right tree, so every
  table call, the `Columns` and `Flag group` selectors, Shift+wheel, the arrow keys and the
  heading hint work as before. The JIRA Live Data and dashboard tables are not frozen.

### Changed
- The JIRA Live Data filters are a three-column grid instead of one row that clipped at the
  right edge: find, status, category / type, priority, assignee / Clear filters and the count.

## [0.7.1] - 2026-10-27

Every table is as wide as the longest string in its domain. One helper,
`gui/screens.py:fit_columns`, measures each column's heading, cells and lookup values in pixels with the real
fonts after every fill; the same change is made, independently, in the sister tool.

### Changed
- Every table column fits its widest text, heading and lookup values included; the 36 px flag
  columns are gone. `fit_columns(tree, extra=None, *, min_width=40, max_width=600, padding=24)`
  sizes each column of a `ttk.Treeview` to the widest of its heading (the `Treeview.Heading`
  font), every cell it holds (the `Treeview` font) and `extra[column]`, plus the padding, clamped
  to the floor and the cap; `minwidth` equals the width and `stretch` is off on every fitted
  column, because Tk shrinks a stretchable column towards its minwidth whenever the fitted total
  exceeds the widget width (a correctly measured Summary collapsed to "Summa"). It
  runs after every fill on the Safety Plan table (an enum field's `extra` is every value of its
  lookup, the list `EnumWidget` offers, so `status` holds `Out-of-Scope` before any row says so;
  long cell text is still clipped at 70 characters and the column fits the clipped text), on the
  Safety Plan Matrix (`all` and each group: a flag column is as wide as its source column title),
  on JIRA Live Data (all 15 columns, `[Comments]` first; Summary no longer stretches) and on the
  three dashboard tables. The per-type widths of the screens are starting points only; an empty
  table keeps its heading-fitted widths. `FLAG_WIDTH` (`entity_screen.py`) and `ALL_WIDTH`
  (`matrix_screen.py`) are deleted; the tables get wider and scroll sideways as before
  (Shift+wheel, the arrow keys, the bar); the `Columns` and `Flag group` selectors still narrow
  the set and refit. Hovering a heading too narrow to show its text still names the column in
  the status bar, which now only happens after a user drags one narrow.

## [0.7.0] - 2026-10-27

The local automation server: JSON over localhost so an agent can puppet a running session. Since
0.6.0 the CLI is refused while a window is open; from 0.7.0 that refusal is forwarded to the
window's own server, so `asi-kletz theme pink-noir` from another console recolours the open
window, and `asi-kletz update ...` edits the row the engineer is looking at. The convention
(`ASI_FUSA_TOOLS.md`, "The automation session") is implemented here independently of the sister
tool, never shared as code. Still one table, the registered screens unchanged, schema version 1.
See `docs/automation-server-plan.md`.

### Added
- `automation/server.py`: `AutomationServer`, a `ThreadingHTTPServer` on `127.0.0.1` and an
  ephemeral port, served by a daemon thread the window owns. Six endpoints, every answer a
  `Result` as the CLI prints it with `--compact`: `GET /status` (tool, version, pid, db, screen,
  theme, started_at, uptime_s, port, requests, events_seq, lock), `POST /execute`
  (`{"verb", "args", "actor"}`, actor default `agent`, never `gui`; `{"verb": "gui"}` refused),
  `GET /screens`, `POST /screen {"show": key}`, `GET /events?since=<n>&limit=<m>`, `POST /quit`
  (the window closes 100 ms after answering). Bearer token (`secrets.token_hex(16)`, new per
  launch): 401 `bad token`; any `Origin` header: 403; wrong method 405, bad body 400, body over
  1 MiB 413, unknown path 404, window too slow 504, a job that raised 500. The HTTP status is
  about transport; a failed command is 200 with `ok: false`.
- The main-thread handshake: every request becomes a job on a `queue.SimpleQueue`; the window
  drains it every 50 ms on the Tk thread (an `after` job on the root, so it survives the
  `set_theme` rebuild); the handler waits on a `threading.Event` (60 s, `job_timeout`). The
  server thread never touches a widget, the window's state or the `Brain`.
- `automation/session.py`: the session file `%LOCALAPPDATA%\asi\kletz\session.json` beside
  `prefs.json` (`$ASI_KLETZ_SESSION` overrides; the suite points it at a temp folder) with
  `tool version pid started_at host port address token db`, written atomically after the bind
  (`0o600` on POSIX), removed in `close()`; `read_session()` ignores a missing, corrupt, foreign
  or dead-pid file; `pid_alive()` (`OpenProcess` + `STILL_ACTIVE` through ctypes on Windows,
  signal 0 elsewhere); `probe()` (`GET /status` must answer as the file's pid within 1 s);
  `forward()` (`POST /execute`); `SessionUnreachable`; `ASI_KLETZ_AUTOMATION=off`.
- `EventBus`: `seq` on every event (one counter per bus, from 1), `EventBus.seq`,
  `since(n, limit=200)` and `oldest_seq()`; `last(n)` unchanged. Polling is the protocol.
- CLI forwarding: a lock refusal whose holder says `asi_kletz` with the session file's pid, and
  whose session answers `/status`, is forwarded as `POST /execute`; the forwarded `Result` is
  printed untouched and the exit code is 0 or 1 by its `ok`, `--actor` travels with it. A
  holder of the sister tool, a dead or missing session (hint `no automation session; the window
  may have been started with --no-server or ASI_KLETZ_AUTOMATION=off`) or a server that does
  not answer (`the automation session at http://127.0.0.1:<port> did not answer`) is still exit
  3. Global `--no-forward` turns the branch off. `--db` naming another database on a forwarded
  call is ignored with a warning on stderr.
- The `session` verb (`commands/session.py`, flag `--quit`): the one verb that opens no
  `Brain`, so it works while a window holds the lock. Prints `path`, `present`, `alive`,
  `reachable`, `session` (`pid port address started_at db`, never the token), `status` (the
  `/status` data) and `quit`; `--quit` posts `/quit` and waits up to 5 s for the file to go;
  with no live session it is `ok: false`. Through `/execute` it reports the window's own session.
- Window: `MainWindow(..., server=True)` starts the server after the body is built and writes
  the session file (a failure to bind or write is a status-bar warning, never a failed launch);
  `close()` stops it and clears the file before `destroy()`; `online_var` reads
  `◉ ONLINE :51234` while the server is up; the **theme badge** (`badge_var`: the title
  upper-cased with any parenthetical dropped, `CYAN NEON`, `PINK DAY`, `PLAIN`) between the
  online indicator and the status text, in the mono font, `StatusMuted.TLabel`;
  `remote_guard(verb, args)`: a remote `theme <key>` is refused without a dialog while the open
  screen reports `is_dirty()` (`theme change refused: the <screen> screen has unsaved edits`;
  the preference is not latched); the About box names the session address or says the server is
  off. `--no-server` on `asi-kletz-gui` and on the `gui` verb.
- Remote recolour, proven: `/execute {"verb": "theme", "args": {"key": "pink-noir"}}` (or the
  forwarded `asi-kletz theme pink-noir`) repaints the open window and the badge before the
  `Result` goes back; `theme.changed` is the event, as before.
- Tests: `tests/test_server.py` (a real window over `urllib`: status, the byte-equal read verb,
  a write verb refreshing the open screen with actor `agent`, the main-thread assertion, a job
  that raises, `/events` since/limit/history warning, `/screen` and `/screens`, remote theme and
  the badge, the dirty refusal with `confirm` forbidden, `gui` refused, `document safety_plan`
  built on the Tk thread, 401/403/405/400/404, the 504 whose job still runs, `/quit`,
  `server=False` and `ASI_KLETZ_AUTOMATION=off`, `close()` removing the file and the port
  refusing, the stale-file rules, the `session` verb in process), `tests/test_session.py` (the
  file, `pid_alive` against a finished subprocess, probe/forward against a closed port, and the
  forwarding branch with a monkeypatched refusal: same-tool forwards with actor `cli`, sister
  tool exit 3 with no request reaching the server, unknown holder, wrong pid, no file,
  `--no-forward`, a dead server with the file left, `--db` warning), the badge and the online
  indicator surviving a repaint in `tests/test_gui.py`, `session` and `--no-forward` in
  `tests/test_cli.py`. `tests/conftest.py` points `ASI_KLETZ_SESSION` at a per-test file and
  clears `ASI_KLETZ_AUTOMATION`.

### Changed
- `asi-kletz <verb>` while the Kletz window is open now runs in the window (forwarded) instead
  of exit 3; exit 3 remains for the sister tool, a window without a server, and `--no-forward`.
- The family document is now `asi_fusa_tools/ASI_FUSA_TOOLS.md` (titled "ASI FuSa Tools"); the
  digest test, the `palettes.py` and `locks.py` docstrings, and every link follow it.
- README ("Automation", quick start, One at a time, layout, tests), `docs/plan.md` (sections 3,
  7, 8, 9), `kletz.example.toml` comment, `automation/__init__.py` docstring.
- The Safety Plan Matrix opens on `all`: every flag column at once as narrow check marks, in source
  order, so the window no longer looks as if the plan ended at DMS / JAMA / Sharepoint; a single group
  is still one pick away and gets its wide headings back.
- Both Safety Plan tables scroll sideways with Shift+wheel and the arrow keys, and hovering a clipped
  flag heading names the column in the status bar.

### Fixed
- JIRA Live Data never refreshed against the real site: a page of 100 issues with their descriptions
  rendered to Markdown is larger than the one-megabyte server-sent event Hopper's transport accepted.
  `jira live` now asks for `asi_hopper.LIST_FIELDS` only, 50 issues a page, and needs asi_hopper 0.1.1
  (configurable `gateway.max_event_mb`).

## [0.6.0] - 2026-10-27

One primary tool at a time: the family lock. While any process of Kletz or its sister tool holds
an open `Brain`, no other process of either may open one; the same tool never runs twice. The
convention (`ASI_FAMILY.md`, "One primary tool at a time") is implemented here independently and
checked against a simulated sibling, never shared as code. Still one table, the registered
screens unchanged, schema version 1. See `docs/single-instance-plan.md`.

### Added
- `locks.py`: `lock_dir()` (`$ASI_PRIMARY_LOCK_DIR`, else `%LOCALAPPDATA%\asi\locks`, else the
  XDG state folder; created on demand, never inside a repo or OneDrive), `db_slot_name()`
  (`db-<sha1>` of the resolved absolute path, lower-cased on Windows), `holder_info()`,
  `describe_holder()`, `SlotLock` (one non-blocking OS advisory lock on byte 0 via
  `msvcrt.locking` / `fcntl.flock`, the lock file kept one byte long, plus the `.json` holder
  file beside it: `tool version pid started_at db cwd host user`, written best-effort, removed
  on a clean release) and `PrimaryGuard` (`guard`, one per process, thread-safe,
  reference-counted: the family slot `primary.lock` is taken by the first `Brain` of the
  process and released after the last `close()`, one database slot per resolved path with its
  own count, `:memory:` takes none; family slot first, a failed database slot releases the
  family slot; `wait` polls every 250 ms). No override flag.
- `PrimaryToolBusy(BrainError)` with `slot` (`family` | `database`), `holder` (the parsed
  `.json`, or `None` when unreadable) and `lock_path`; exported from `asi_kletz` and reachable
  from `asi_kletz.errors`. Its message names the holder:
  `<tool> is running (pid 4321, since 2026-10-27T17:02:11Z, db ...); only one primary tool may
  run at a time. Close it, or retry with --wait.`
- `Brain(..., wait=0.0)` takes the slots before `StorageFactory.create`, so a refused process
  never opens the SQLite file; `close()` closes the storage then drops the hold, idempotent;
  `status()` reports `lock_dir` and `locks` (`family` and `database`: the holder info of this
  process plus `lock` and `brains`, the count of open Brains).
- CLI: global `--wait SECONDS` (default 0); a refusal prints a JSON `Result` with `ok: false`,
  `errors[0]` naming the holder and `data = {"slot", "holder"}`, and exits with **3**; exit 1
  keeps meaning "the command ran and failed".
- Window: `--wait SECONDS` on `asi-kletz-gui`; `app.open_brain` shows the busy dialog
  (`ask_retry`, the holder line with Retry / Quit; Retry re-attempts once) and `main` returns 3
  without a window when the slot stays taken or with `interactive=False`; the About box names
  the lock directory. The `gui` verb is refused by the CLI's own Brain, like every verb.
- `kletz.example.toml` says the lock directory is `ASI_PRIMARY_LOCK_DIR`, never a config key;
  `.gitignore` ignores `*.lock` and `*.lock.json` as a precaution.
- Tests: `tests/test_locks.py` (the lock directory and slot names; one process with four Brains
  holding `primary.lock` once, probed from a process of its own; `status`; a second Kletz
  process refused with its holder; a simulated sibling that takes `primary.lock` by the raw
  convention with no package import and writes `primary.json` under the sister tool's name; a
  database-slot refusal releasing the family slot; an unreadable holder file; a killed holder
  releasing the slot at once; `wait` succeeding and timing out; the exports), CLI exit 3 with
  `data.slot` and `data.holder.pid` and `--wait` succeeding in `tests/test_cli.py`, the window
  entry point returning 3 without a window, the Retry / Quit paths and the About box line in
  `tests/test_gui.py`. `tests/conftest.py` points `ASI_PRIMARY_LOCK_DIR` at a per-test folder,
  so the suite never collides with a running tool or with the sister suite.

### Changed
- `asi-kletz <verb>` while the Kletz window (or the sister tool) is open is refused with exit
  code 3 instead of sharing the database; scripts queue with `--wait`. Moving data between the
  two tools is `dump` in one, then `load` in the other, never both open at once.
- README ("One at a time", quick start, Python API, scripts, layout, tests), `docs/plan.md`
  (sections 7, 8, 9) and `docs/single-instance-plan.md` (re-targeted to 0.6.0) updated.

## [0.5.0] - 2026-10-27

The JIRA Live Data window and its comments view, fed by asi_hopper. Still one table: nothing from
Jira is stored, exported or dumped; the schema version stays 1. The old screen-count rule is
retired (the owner, 2026-10-27: "kletz can now have any number of screens; that rule was just
there to prevent an overzealous agent from adding screens"): screens are registered in
`gui/screens.py`; the list is the design, not a cap. See `docs/jira-live-data-plan.md`.

### Added
- `asi-hopper` as an editable path dependency (`../asi_hopper`, the same pattern as the two
  generators), imported lazily: `import asi_kletz`, `Brain(":memory:")` and window start-up never
  load it. Kletz ships no `hopper.toml`; asi_hopper reads `$ASI_HOPPER_CONFIG`, else `./hopper.toml`.
- The `jira` verb (`commands/jira.py`, read only): `jira live [--jql <jql>] [--limit <n>]` fetches
  a JQL (default `jira_live_jql` in `kletz.toml`, else `project = HWL ORDER BY updated DESC`; limit
  2000, one row more is probed so `truncated` is exact and a warning says so) and returns
  `{jql, fetched_at, count, truncated, issues}` with the family row convention, publishing
  `jira.live`; `jira comments <key>` returns `{key, summary, url, status, fetched_at, count,
  comments}` newest first and publishes nothing. Failures are Results: the install hint, Hopper's
  own login hint (`AuthRequired`), `Jira read failed: ...` for every other `HopperError`,
  `limit must be at least 1`, `jira comments needs an issue key`. Nothing is audited.
- `services/jira_service.py`: `JiraService` (`open_hopper`, `live_jql`, `live`, `comments`,
  `_guard`), `live_row`, `comment_row`, `LIVE_JQL`, `LIVE_LIMIT`, `LIVE_FIELDS`, `INSTALL_HINT`;
  `Brain.jira`.
- `kletz.toml`: `jira_live_jql` (text) and `jira_live_autofetch` (a TOML boolean; a string is
  ignored so the default `true` applies); `CONFIG_BOOL_KEYS` in `brain.py`.
- `gui/jira_live_screen.py`: the `JIRA Live Data` screen (key `jira_live`), registered right after
  the dashboard and second in the navigation list and in `View`: Refresh and a status line
  (`n issues · fetched hh:mm · <jql>`, `No fetch yet`, `Offline: ...`), a Find box on key or
  summary and read-only drop-downs for Status, Category, Type, Priority and Assignee (`(all)`,
  the values present, `(none)`), all local to the last fetch, `Clear filters`; a 15-column table
  with `[Comments]` first, sortable headings marked ▲/▼ (keys numerically, dates on the full
  timestamp, blanks last), stripes plus a `muted` tag on done rows; double-click or Enter opens
  the issue, `c` or a click on `[Comments]` opens its comments, a hand cursor over that column.
  The last fetch is `MainWindow.jira_live`, memory for the session, kept across a theme pick; a
  failed fetch after a good one keeps the rows. First show fetches once unless
  `jira_live_autofetch = false`.
- `gui/jira_comments_window.py`: `JiraCommentsWindow`, one Toplevel per ticket titled
  `<KEY> — Comments`, 640 x 520, newest first, each comment as `author · time` (`· edited time`
  when it differs) over a read-only, selectable `tk.Text` body, `No comments.` when empty;
  Refresh, Close, Escape, F5; a failed refresh keeps what is listed and says `Error: ...`.
  `MainWindow.open_comments` (one window per key, lifted when already open), `comment_windows`,
  cleared by `set_theme` as the Toplevels go down with the rest of the root's children.
- `MainWindow.run_quiet`: `run` without the dialog, sharing `_execute`; the status bar is where
  the Jira screens report. `_on_event` ignores `jira.live` like `theme.changed`: no database row
  changed, so no screen refreshes.
- Tests: `tests/test_jira.py` (the verb on asi_hopper's replay fixtures, limit and truncation,
  the unrecorded house JQL, the config key, the event, nothing written, a stub Hopper for the
  probe, null rows, `AuthRequired`, the install hint, comment ordering, the schema signature);
  `tests/test_gui.py` (the screen filled from a stubbed `run_quiet`: first show, autofetch off,
  refresh and failure, offline first fetch, sorting, every filter, muted rows and cells, open,
  rebuild on a theme pick, the event path; the comments column click routing, the window's
  ordering, refresh failure, empty history, close, theme pick, main-window close);
  `test_load_config_reads_the_jira_live_keys` in `tests/test_core.py`.

### Changed
- `build_default_screens` registers five screens in navigation order: Dashboard, JIRA Live Data,
  Safety Plan, Safety Plan Matrix, Export / Import; its docstring says registered, not counted.
  `test_exactly_four_screens` is now `test_registered_screens_in_order` and asserts the list and
  the navigation entries, never a count; the other `== SCREENS` assertions follow.
- The lazy-import test adds `asi_hopper` to the modules that must stay unloaded and the
  share-nothing test asserts `asi-hopper` in `pyproject.toml` beside the two generators.
- README (`JIRA Live Data` section, requirements, configuration, quick start, layout, tests,
  "Adding an entity"), `docs/plan.md` (sections 1, 3, 7, 8, 9) and `kletz.example.toml` updated;
  no screen-count wording remains outside the historical entries below and the two earlier
  plans, which keep theirs.

## [0.4.0] - 2026-10-27

Every column of the source workbook in the Safety Plan table. No schema, storage, transfer or
verb changes; the schema version stays 1; the matrix screen is untouched. Screens are
registered in `gui/screens.py`; the list is the design, not a cap.

### Changed
- `gui/entity_screen.py`: the flag-column cap (`MAX_FLAG_COLUMNS`) is gone; the table's columns
  are `id` followed by every schema field in source order, so the Safety Plan table has 64
  columns and `order`, `PDP Phases`, `Safety Lifecycle Phase` and `Safety Deliverables` stay
  leftmost.
- Flag columns are narrow (`FLAG_WIDTH = 36`), centred, not stretched, headed by the source
  title and filled with a check mark or blank; a long title clips, drag the heading separator
  to widen it for the session.
- A read-only `Columns` combobox in the toolbar (`All`, `Location`, `Reference`, `Author`,
  `Verification`, `Reviewer`) drives `displaycolumns`: a group shows the non-flag columns plus
  that group's flags, `All` shows everything. The tree is never rebuilt, so headings, widths,
  the sort and the selection survive. `All` is the default; the choice lives on the cached
  screen instance for the window session (a theme pick or a restart returns it to `All`) and is
  never written to `prefs.json` or `kletz.toml`.
- Sorting by a column writes `Sorted by <header>` to the status bar, so a clipped heading can
  still be named.
- The table's scrollbars are the attributes `xbar` and `ybar`; the layout is unchanged.
- Tests: the table columns, headings, widths and cell marks; the `Columns` selector, its
  survival across a refresh and a trip to the dashboard, and its reset on a theme pick; both
  scrollbars; the source workbook's header row equals the schema headers (skipped without the
  workbook).

### Fixed
- The Safety Plan table stopped at `Work Product Location`: with 53 flags the cap hid every
  flag column, DMS, JAMA and Sharepoint first. The form and the workbook always carried all 63.

## [0.3.0] - 2026-10-27

The family palette and a latching theme picker. Kletz and its sister tool offer the same 32
palettes under the same names and each latches its own choice, so a window that looks like
Kletz is Kletz. The window still has exactly four screens; the database still has exactly one
table; the schema version stays 1.

### Added
- `gui/palettes.py`: the family palette, 8 hue families × 4 tones = 32 palettes from
  `cyan-noir` to `green-day`, pure data, byte-identical in both tools. A test hashes the
  catalog against the digest in `ASI_FAMILY.md` ("The family palette", Appendix A) and a
  contrast test keeps every palette legible.
- `GridTheme` (the grid recipe with the palette as data) and one registered theme per palette;
  `ThemeFactory.alias`, `entries`, `resolve` (explicit key, `ASI_KLETZ_THEME`, latched
  preference, house default); `tron` is an alias of `cyan-neon`; `Theme.apply` is re-entrant.
- `asi_kletz.prefs`: `prefs_path`, `read_prefs`, `write_prefs`, `ASI_KLETZ_PREFS`. The
  per-person, per-machine `prefs.json` lives in `%LOCALAPPDATA%\asi\kletz` (XDG state folder
  elsewhere), is written atomically, and reads as empty when corrupt.
- Verb `theme`: no key lists the catalog, the latched key, the key in use and the preferences
  path; a key validates it, latches it and publishes `theme.changed`; an unknown key fails
  with exit 1.
- The window: a read-only THEME combobox at the foot of the navigation column and a
  `View > Theme` cascade (one submenu per family, Plain at the end) sharing one variable;
  `pick_theme` runs the verb, `set_theme` repaints by rebuilding the menu, body and open
  screen; `theme.changed` on the event bus repaints a window open in this process, whoever
  raised it. A latched theme is applied on launch; a corrupt file or an unknown key warns in
  the status bar.
- `kletz.example.toml` says where the theme preference lives and that `--theme` is one-off.
- CLI bool flags such as `--list` may stand alone as well as take `true` / `false`.

### Changed
- **The default theme is `cyan-neon`**, the former `tron` look under its catalog name: a Kletz
  that has never latched a theme opens exactly as before. `asi-kletz theme amber-neon` latches
  the complementary look, and only Kletz sees it.
- `TronTheme` is the `cyan-neon` class (the name still imports); the Tron palette is the
  catalog's `cyan-neon` row. The Treeview selected text colour comes from the palette instead
  of a literal white, so the `day` tones stay legible.
- `--theme` on `asi-kletz gui` and `asi-kletz-gui` is resolved through the precedence above
  and never writes the preference; help text updated.
- Tests never read or write the developer's theme latch: `ASI_KLETZ_PREFS` points at a
  temporary file and `ASI_KLETZ_THEME` is cleared for every test.

## [0.2.0] - 2026-10-27

ASI Kletz draws the Safety Plan with asi_escher and prints it with asi_gutenberg, from its own
database, through the one command path. Generated files are views like the workbook: regenerated
on demand, never read back. The window still has exactly four screens; the database still has
exactly one table; the schema version stays 1.

### Added
- Dependencies `asi-escher` and `asi-gutenberg` (0.2.0, with `diagram` blocks) as editable
  path sources declared in Kletz's own `pyproject.toml`.
- Output folder: `--out`, `ASI_KLETZ_OUT`, `out` in `kletz.toml` (relative to the file), or
  `out/` next to the database; `Brain.out_dir`, reported by `status`.
- Safety Plan document control in `kletz.toml`: `doc_id`, `project` and `[[revision]]` entries
  (`Brain.doc_id`, `Brain.project`, `Brain.revisions`, reported by `status`). The revision
  history is explicit, never derived from the audit log. `kletz.example.toml` documents them.
- Package `asi_kletz.generate`: `Spec`, `Param`, `BuildContext`, `DiagramFactory`,
  `DocumentFactory`, `register_diagram`, `register_document`; `plan_queries` (the read helpers
  the dashboard, diagrams and documents share); `figures` (asi_escher rendering with
  `LayoutWarning` captured and `LayoutIssue` turned into plain dicts).
- Diagrams `lifecycle_overview`, `phase_flow` (`--param phase=<n>` or the full lookup value),
  `status_board`, `pdp_map`.
- Documents `safety_plan` (plan; per-phase **Deliverables** and **Ownership** tables so nothing
  needs a landscape page; appendices for roles, references and statuses), `status_report`
  (report) and `phase_checklist` (checklist), each a Markdown / PDF / Word triplet whose figures
  are asi_escher diagrams rendered by asi_gutenberg into `<out>/figures/`. The reviewed artefact
  is the PDF.
- Verbs `diagram [name] [--out] [--formats] [--param k=v ...] [--dpi]` and
  `document [name] [--out] [--param k=v ...]`: no name lists the catalog; unknown names and bad
  params fail naming the known values; layout issues become `warnings`; a locked output falls
  back to a timestamped stem; results carry `primary` (PDF or PNG); both write the audit entry
  `generate` and publish `generated`.
- Export / Import screen: a third frame, "Diagrams and documents (generated views of the plan)",
  with diagram, document and phase comboboxes, an output folder, Build diagram, Build document,
  Open and Open folder. File > Build Safety Plan document.
- Tests: catalogs, every diagram, every document, `doc_id` and revisions from `kletz.toml`,
  per-phase table split, locked-PDF fallback, audit and event, out-dir precedence, CLI exit
  codes, lazy imports, the no-sister-tool grep, the transfer-screen frame, the menu entry.

### Changed
- The dashboard computes its numbers through `generate.plan_queries`, the same helpers the
  reports use, so the screen and the documents cannot drift. Numbers are unchanged.
- `status` reports `out_dir`, `doc_id`, `project` and `revisions`.
- Lint: long lines wrapped, the ambiguous alias `I` in `schema/definitions.py` renamed to `N`.

## [0.1.0] - 2026-10-27

First release. ASI Kletz was split from ASI Dewey 0.1.0 on this date: the same architecture,
command path, storage, transfer formats, window and themes, carrying exactly one entity and
four screens. The two tools share nothing at runtime: separate package, commands, environment
variables, configuration file, database, and workbook.

### Added
- Schema layer: `FieldSpec`, `FieldType` (text, multiline, int, bool, date, url, enum),
  `EntitySchema`, `SchemaRegistry`, soft `LookupRegistry`, and `flag_fields` for matrix columns.
- One built-in entity, `safety_plan_row` (63 columns), seeded from the `Safety Plan` sheet of
  the workbook. Lookups: `pdp_phase`, `lifecycle_phase`, `plan_status`.
- SQLite storage generated from the registry, with column auto-migration, a
  `schema_migrations` fingerprint table, and an `audit_log` (actor, action, entity, payload).
- Generic `SqlRepository` (get, list with filters/ordering/paging, count, create, update,
  delete, bulk insert) and `RepositoryFactory`.
- `EntityService` with validation, audit, events, and bulk `load_rows` in replace/merge/append modes.
- Command layer: `Result`, `Argument`, `Command`, `CommandFactory`, `Dispatcher`, and the
  verbs list, count, get, create, update, delete, schema, status, dump, load, export, import,
  run, gui.
- JSON exporter/importer (single-entity and combined envelopes) and Excel exporter/importer
  (header-driven column mapping, repeated headers handled, other sheets ignored, locked-file
  fallback).
- `Brain` facade (`execute`, `execute_dict`, `service`, `status`), `EventBus`, `.jsonl` script runner.
- CLI `asi-kletz` built from command signatures; prints a JSON `Result`; exit code 1 on failure.
- `asi_kletz.gui`: `MainWindow` (navigation list, status bar, File/View/Help menus, Ctrl+N,
  Ctrl+S, Ctrl+E, Ctrl+Q, F5), `ScreenFactory` fixed to four screens, `WidgetFactory`, and
  `ScrollableFrame`.
- Dashboard screen: deliverable tiles by status that open the plan, deliverables per lifecycle
  phase, open deliverables, recent audit entries.
- Safety Plan screen: sortable, searchable table; form built from the schema with flag groups
  rendered as checkbox grids; New / Save / Delete / Duplicate / Refresh; validation errors and
  lookup warnings surfaced in the status bar.
- Safety Plan Matrix screen: deliverables as rows, one flag group as columns, click a cell to
  toggle it (location, reference, author, verification, reviewer).
- Export / Import screen: workbook export and import with mode, JSON dump and load, result log.
- Event-driven refresh: the open screen refreshes after any command, from any actor.
- Themes: `Theme`, `TronTheme`, `ThemeFactory` (`ASI_KLETZ_THEME`); `tron` is the default,
  `plain` is the native look.
- `kletz.toml` (git-ignored; `kletz.example.toml` as a template) sets the database and
  workbook paths, relative to the file. `status` reports `config_path`.
- pytest suite covering schema coercion, CRUD, audit, events, transfer round trips, the CLI,
  and the GUI, including a test that the window has exactly the four screens and the database
  exactly the one table.

### Not carried over from ASI Dewey
- The eight working-knowledge entities (tasks, facts, machine functions, use cases, links,
  Jira tickets, QMS documents, people), their lookups, their sheets, and their screens.
- The one-screen-per-entity navigation and the Jira and task panels of the dashboard.

[Unreleased]: https://example.invalid/asi-kletz/compare/v0.7.4...HEAD
[0.7.4]: https://example.invalid/asi-kletz/compare/v0.7.3...v0.7.4
[0.7.3]: https://example.invalid/asi-kletz/compare/v0.7.2...v0.7.3
[0.7.2]: https://example.invalid/asi-kletz/compare/v0.7.1...v0.7.2
[0.7.1]: https://example.invalid/asi-kletz/compare/v0.7.0...v0.7.1
[0.7.0]: https://example.invalid/asi-kletz/compare/v0.6.0...v0.7.0
[0.6.0]: https://example.invalid/asi-kletz/compare/v0.5.0...v0.6.0
[0.5.0]: https://example.invalid/asi-kletz/compare/v0.4.0...v0.5.0
[0.4.0]: https://example.invalid/asi-kletz/compare/v0.3.0...v0.4.0
[0.3.0]: https://example.invalid/asi-kletz/compare/v0.2.0...v0.3.0
[0.2.0]: https://example.invalid/asi-kletz/compare/v0.1.0...v0.2.0
[0.1.0]: https://example.invalid/asi-kletz/releases/tag/v0.1.0
