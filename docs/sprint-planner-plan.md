# ASI Kletz — Plan: the sprint planner, holidays and business days

**Status:** Implemented 2026-10-28 (asi_kletz 0.10.0); deviations in the CHANGELOG entry
**Written:** 2026-10-28
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.10.0 (after 0.9.1; one new entity, `holiday`; Kletz only, nothing shared with
the sister tool)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md); this plan adds one row to the
plans table and one to the version ladder there, edited by the owner's orchestrating agent after the tag, never
by the agent implementing this plan. No new convention section: holidays and sprints are Kletz's alone.
**Sister plan:** none. The Weekly Activity Tracker and its sprints are [weekly-tracker-plan.md](weekly-tracker-plan.md).

---

## 1. The ask

The owner's sprint rule, decided 2026-10-28, quoted verbatim here, in the README and in the verb's help, and
honoured everywhere:

> - A sprint spans 10 business days. Monday to Friday count; weekends and holidays do not, so a sprint that
>   contains a holiday ends one calendar day later per holiday. Dates move as holidays become real; the cadence
>   does not.
> - Capacity is 8 points per sprint, company policy (8 productive days of the 10). Holidays never reduce points.
> - Sprints are consecutive with no gaps, numbered across the programme (SPRINT n); the chain continues from
>   Sprint 2 (2026-10-27 to 2026-11-10). We do not know the work yet: future sprints are empty, Planned, with no
>   lifecycle phase, and will be adjusted as dates become real.

The owner's addition, the same day: "every single sprint except the one in the past is 8 points; set this as
a global value that is fixed." So capacity is not a default any more, it is the rule, and the tool enforces it.

So the tool needs to know the holidays, to count business days, to extend the sprint chain to a horizon on
demand, to move the planned dates again when a holiday becomes real without touching a sprint that has
started or closed, and to hold every sprint that is not in the past at 8 points.

## 2. What exists today (verified 2026-10-28, asi_kletz 0.9.1)

| Fact | Where |
|---|---|
| Four entities; a `sprint` has `number`, `label`, `lifecycle_phase`, `start`, `end`, `capacity`, `goal`, `status` (Planned / Active / Closed), `closed_on`, `uid`. `SPRINT_CAPACITY = 10`, `SPRINT_DAYS = 14`; `Brain.sprint_capacity` and `Brain.sprint_days` come from `sprint_capacity` / `sprint_days` in `kletz.toml`, else these. | `schema/definitions.py:90-120`, `brain.py:38,172-174` |
| `sprint start` opens a sprint: the default end is `start + timedelta(days=sprint_days)`, calendar days, so a sprint that starts on a Tuesday ends on a Tuesday two weeks on and shares its end day with the next start. `sprint close` activates the next Planned sprint, giving it `start = closed.end` and `end = start + sprint_days` when it has no dates, or creates the next one with the closed sprint's capacity and calendar length. | `services/sprint_service.py:33-72,148-172` |
| The tracker text: `TrackerService.tracker` turns every sprint row into a `Sprint` model (a row without a lifecycle phase gets `phase_number = str(number)` and an empty title), and `format.render` prints one `TIMELINE` bullet and one `=====` block per sprint, Planned and empty included. A Planned sprint without a phase would print `- Phase 3 (): planned. Sprint 3: ...`. The parser reads sprints from the blocks only and ignores a timeline bullet it does not recognise. | `services/tracker_service.py:190-226`, `tracker/format.py:404-416,466-490,202-216` |
| The Sprint Board picker lists every sprint (`sprint_label`: `n · LABEL · status`), the active one first through `current_number`; the dashboard strip shows the active sprint. | `gui/sprint_board_screen.py:31-33,140-176` |
| Screens are registered in `build_default_screens` (Dashboard, JIRA Live Data, Safety Plan, Safety Plan Matrix, Sprint Board, Weekly Status, Export / Import); `EntityScreen` is generic: an entity without the stack has no frozen column (`IDENTITY = STACKED`, 0.9.0) and its columns are the visible fields minus `id` and `order`. | `gui/screens.py:390-415`, `gui/entity_screen.py:34-45` |
| Verbs with actions (`tracker import|build|add`) take `action` with `choices` and a positional `what`; a new verb is registered with `@register_command`. | `commands/tracker.py`, `commands/factory.py` |
| Tests: 264 pass; `test_sprint.py` pins capacity 10, `end = start + 14 days` and the close-opens-next dates; `test_tracker.py` renders a built tracker with a Planned sprint that has no weeks and expects its bullet and its block; `conftest.py` lists `ENTITIES`, `TABLES`, `SHEETS`; `test_gui.py` lists `SCREENS` and `TITLES`. | `tests/` |
| No business-day arithmetic exists anywhere; `days_left` on the board counts calendar days. | `generate/sprint_queries.py:95-98` |

## 3. Design

### 3.1 The `holiday` entity (schema version 3 → 4)

`holiday`, table `holiday`, label `Holiday`, sheet `Holidays`, registered after `week` so it is last in
`ALL_ENTITIES`, in the dump and in the workbook. Fields: `date` (DATE, required), `name` (TEXT, required),
`status` (ENUM `holiday_status`: `assumed` / `confirmed`), `note` (MULTILINE), then the hidden `uid` like every
entity. `order_by = ("date", "id")`. It gets the CRUD verbs, the JSON dump, the workbook sheet and, through
the generic `EntityScreen`, a **Holidays** screen registered after Weekly Status (no stack, so no frozen
column; the form has the four fields; the details title names the row).

`holiday load <file>`: a new `holiday` verb whose `load` action reads a JSON list of `{"date", "name",
"status"}` (`note` optional) and upserts by `date` + `name`: a matching row is updated with the fields the
file carries (`unchanged` when nothing differs), a missing one is created. The seed file
`data/us-holidays-2026-2029.json` is committed as given (52 weekday rows: US federal holidays 2026 to 2029 on
their observed dates, plus the day after Thanksgiving and Christmas Eve marked `(company, assumed)`; every row
`assumed`); it is read, never regenerated. The report: `path`, `inserted`, `updated`, `unchanged`, `rows`.

### 3.2 Business days

One pure module, `tracker/business_days.py` (no Tk, no storage; the holidays are passed in as dates, any
status counts):

- `is_business_day(day, holidays)`: Monday to Friday and not a holiday.
- `next_business_day(day, holidays)`: the first business day strictly after `day`.
- `add_business_days(start, n, holidays)`: the date reached by moving `n` business days forward from
  `start`, counting business days only; `n = 0` is `start` itself (when `start` is a business day). A sprint
  that starts on a business day ends on `add_business_days(start, 9)`, its tenth business day.
- `business_days_between(start, end, holidays)`: the number of business days in `[start, end]`, inclusive.
- `holidays_within(start, end, holidays)`: the holiday dates in `[start, end]`, sorted.

`holiday_dates(brain)` in `generate/sprint_queries.py` reads the table into `{date: name}` for the callers.

### 3.3 The planner

`sprint plan [--until YYYY-MM-DD | --years 3] [--days 10] [--replan]` in `SprintService.plan` (no
`--capacity`: capacity is the rule of 3.4):

- The chain continues from the highest-numbered sprint (it must have an `end`; an empty table is a
  `CommandError`: run `sprint start` first). The next sprint starts on the first business day after that
  end and ends on its `--days`th business day (holidays skipped, so the calendar span grows), label
  `SPRINT <number>`, no lifecycle phase, capacity `--capacity`, status `Planned`, `goal` empty unless the
  sprint contains holidays, then `Holidays: <name> (<m/d>), ...`, so the board and the text say why the dates
  stretched; capacity 8 (3.4). Sprints are added while their start is on or before the horizon (`--until`,
  else `--years` years after the last sprint's end), so the last planned sprint may end after it.
- Idempotent: an existing sprint is never touched; a second run adds the sprints missing up to the horizon,
  none when the chain already reaches it.
- `--replan` recomputes `start`, `end` and the holidays line of every Planned sprint after the active one
  (after the last Closed one when none is active; every Planned one when the table holds nothing else), in
  chain order from the anchor's `end`, with `--days` business days each, from the holiday table as it is now.
  Active and Closed sprints are never touched; a Planned sprint's goal is only rewritten when it is empty or
  is a `Holidays:` line the planner wrote. Then the horizon is filled as above.
- The report: `added`, `replanned`, `first` and `last` (`number`, `start`, `end`), `until`, `days`, `capacity`,
  `holidays` (the holidays honoured inside the planned sprints, `name (date)`).

### 3.4 Capacity is the rule; days are business days

**Capacity.** `SPRINT_CAPACITY = 8` is a fixed global in `schema/definitions.py`, with the owner's words in
the comment. The `sprint_capacity` key of `kletz.toml` is gone: when present it is ignored and
`load_config` records a warning naming the rule, which `Brain` logs and `status` reports
(`config_warnings`); `kletz.example.toml` and the README's Configuration section drop it. `sprint start`
and `sprint plan` have no `--capacity` option; a sprint is created with `capacity = 8`. Every sprint that
is not Closed has capacity 8, enforced by the tool:

- On open, after `ensure_schema` and `stamp_uids`, `SprintService.enforce_capacity` sets `capacity = 8` on
  every sprint whose status is not Closed and whose capacity differs, in one transaction, audited once
  (`enforce_capacity`, actor `system`, the count) when it changed anything; `brain.migration["capacity_enforced"]`
  carries the count. The owner's active Sprint 2, stored at 10, becomes 8 the first time 0.10.0 opens the
  database. A Closed sprint keeps its stored capacity as history (Sprint 1 stays 10).
- `sprint_queries.capacity_of(sprint)` is 8 for any sprint that is not Closed and the stored value for a
  Closed one; `board`, the dashboard strip, `point` and the tracker's sprint line read it, whatever the row
  says.
- `create sprint` and `update sprint n --set capacity=...` on a sprint that is not Closed with a capacity
  other than 8 are refused with the rule's text (`EntityService.guard`, a per-entity check `Brain` attaches
  to the `sprint` service; `SprintService.guard` is the check). A dump or workbook import bypasses the
  service (`load_rows` writes through the repository) and the open-time step normalises what it brought.
- The `capacity` field stays on the entity for that history.

**Days.** `SPRINT_DAYS` 14 → 10, where `sprint_days` now means **business days**, in `schema/definitions.py`,
`brain.py` (the `sprint_days` config key), the `sprint` verb's help and `kletz.example.toml`. `sprint
start`'s default end is `add_business_days(start, sprint_days - 1)` over the holiday table; a `--start` or
`--as-of` given explicitly is kept as the first day. `sprint close` opens the next sprint on the first
business day after the closed one's end, `sprint_days` business days long, capacity 8; a Planned next sprint
that already has dates (the planner's) keeps them. A deliberate change, recorded in the CHANGELOG.

### 3.5 The tracker text

`format.render`: the `TIMELINE` prints the Closed and Active sprints as today and, of the Planned ones, those
that have weeks or items plus the **next** Planned sprint (the earliest by start and number), one bullet;
the `=====` blocks print only sprints that are Closed or Active or have weeks or items, so planned empty
sprints add no block. A sprint without a lifecycle phase prints its bullet as
`- Phase to be assigned: planned. Sprint 3: 11/12 - 11/25.` (the parser ignores a bullet it does not
recognise; a planned sprint without a block is not re-created by an import, it lives in the database). The
`week` build is unchanged. The Sprint Board picker lists every sprint, the active one first, as today; the
dashboard strip is unchanged.

### 3.6 What does not change

The sprint rules of 0.8.0 apart from the dates and the capacity default (points as a warning, one active
sprint, close and carry, velocity), the tracker grammar, the family lock, the automation server, the hidden
identity, the Safety Plan.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Holidays + business days | `tracker/business_days.py`; the `holiday` entity and the `holiday_status` lookup; `SCHEMA_VERSION = 4`; the `holiday` verb (`load`); `data/us-holidays-2026-2029.json`; the Holidays screen registered after Weekly Status; `holiday_dates` in `sprint_queries`. | `pytest` green: the calendar cases of section 6, `holiday load` of the seed gives 52 rows and a second load 52 unchanged, the five-entity lists, the screen in the navigation list. |
| 2. The planner + the capacity rule | `SprintService.plan` and `sprint plan` with `--until`, `--years`, `--days`, `--replan`; `SPRINT_CAPACITY = 8` fixed, `sprint_capacity` ignored with a warning, `--capacity` gone from `sprint start`, `enforce_capacity` on open, `capacity_of`, the guard on `create` / `update sprint`; `SPRINT_DAYS = 10`; `sprint start` and `sprint close` on business days; `kletz.example.toml`. | The planner and capacity cases of section 6; `sprint start --start 2026-10-27` ends 2026-11-09 with capacity 8; closing a sprint opens the next on the following business day. |
| 3. The tracker text | `format.render` with the TIMELINE and block rule; the phase-less bullet; the tests of `test_tracker.py` that built a Planned sprint without weeks. | The TIMELINE cases of section 6; the real-file import and build round trip unchanged. |
| 4. Docs + version | README (the owner's rule verbatim in a "Sprints" subsection, the planner's usage, "What is in 0.10.0"), CHANGELOG `[0.10.0] - 2026-10-28` with every deviation, `docs/plan.md` delivery row, this plan's Status, `version.py` and `pyproject.toml` 0.10.0; commit, push, tag `v0.10.0`, GitHub Release with the CHANGELOG section. **No edit to `asi_fusa_tools`.** | `pytest` and `ruff check src tests` clean; the tag and the release exist. |

## 5. Files touched

```
src/asi_kletz/tracker/business_days.py     is_business_day, next_business_day, add_business_days, business_days_between, holidays_within
src/asi_kletz/schema/definitions.py        holiday entity, holiday_status lookup, SPRINT_CAPACITY = 8 fixed, SPRINT_DAYS 10
src/asi_kletz/version.py                   0.10.0, SCHEMA_VERSION = 4
src/asi_kletz/brain.py                     sprint_capacity ignored with a warning (config_warnings, status); enforce_capacity on open; sprint_days in business days
src/asi_kletz/generate/sprint_queries.py   HOLIDAY, holiday_dates, capacity_of
src/asi_kletz/services/entity_service.py   guard: a per-entity check on create and update
src/asi_kletz/services/sprint_service.py   plan, replan, enforce_capacity, guard; start and close on business days; no --capacity
src/asi_kletz/services/holiday_service.py  load (upsert by date + name)
src/asi_kletz/services/__init__.py         HolidayService
src/asi_kletz/commands/sprint.py           plan action, --until --years --days --replan; --capacity gone; the rule in the help
src/asi_kletz/commands/holiday.py          the holiday verb
src/asi_kletz/commands/__init__.py         registration
src/asi_kletz/tracker/format.py            render: the TIMELINE and block rule; the phase-less bullet
src/asi_kletz/gui/screens.py               the Holidays screen
data/us-holidays-2026-2029.json            the seed, copied as given
kletz.example.toml                         sprint_capacity = 8, sprint_days = 10 (business days)
tests/test_business_days.py, test_sprint.py, test_tracker.py, test_schema.py, test_core.py, test_transfer.py, test_gui.py, conftest.py
README.md, CHANGELOG.md, docs/plan.md, pyproject.toml, docs/sprint-planner-plan.md (Status)
```

## 6. Tests

- **Business days.** A plain week (Monday + 4 business days is Friday; + 5 is the next Monday); a weekend
  (Saturday is not a business day, the next business day after Friday is Monday); one holiday (a Wednesday
  holiday pushes the tenth business day one calendar day); a holiday on a Monday (the next business day after
  Friday is Tuesday); the Christmas and New Year span (2026-12-24, 12-25, 2027-01-01 from the seed: a sprint
  starting 2026-12-21 ends 2027-01-06, 17 calendar days); `business_days_between` on the same cases;
  `holidays_within` sorted and inclusive.
- **Holidays.** `holiday load` of the seed inserts 52 rows, a second load updates 0 and leaves 52 unchanged, a
  changed status is an update, a new name on a known date is an insert; a bad file and a bad row are errors in
  the Result, not a crash; `ALL_ENTITIES` ends with `holiday`, the dump has five entities, the workbook five
  sheets, `holiday_status` is a lookup, the 0.8.4 fixture opens with the `holiday` table created.
- **Planner.** From Sprint 1 (Closed, 2026-10-12 to 10-27) and Sprint 2 (Active, 2026-10-27 to 11-10):
  without holidays, three years add 79 sprints, the first starting 2026-11-11 (the day after the chain's
  end) and ending 11-24, the last (81) 2029-11-07 to 11-20, every one Planned, `SPRINT n`, capacity 8, no
  phase, ten business days; with the seed loaded three years add 75, the first starts 2026-11-12 (2026-11-11
  is Veterans Day), Sprint 4 starts 11-30 (Thanksgiving and the company Friday pushed it), the sprint over
  Christmas (5, 12-14 to 12-29) carries `Holidays: Christmas Eve (company, assumed) (12/24), Christmas Day
  (12/25)` and spans 16 calendar days, 32 holidays are honoured; a second run adds 0; `--until 2027-01-31`
  adds the six sprints whose start is on or before it; `--replan` moves a planned sprint after a holiday is
  added inside it and leaves the active and the closed sprints untouched, a human goal untouched; an empty
  table is an error.
- **Capacity and days.** `sprint start --start 2026-10-27` ends 2026-11-09 with capacity 8 and has no
  `--capacity`; `sprint_days = 7` in `kletz.toml` ends 2026-11-04; `sprint_capacity = 8` in `kletz.toml` is
  ignored with a warning naming the rule (`load_config`, `status`); closing the sprint on 2026-11-10 opens
  Sprint 2 on 2026-11-11 to 2026-11-24 with capacity 8. The open-time step: a database with an Active sprint
  at 10 and a Closed one at 10 opens with the Active one at 8, the Closed one at 10, one `enforce_capacity`
  audit entry with count 1, `migration["capacity_enforced"] == 1`; the second open changes nothing and audits
  nothing. `update sprint n --set capacity=10` on a Planned or Active sprint is refused with the rule's text,
  `capacity=8` is accepted, a Closed sprint's capacity may be edited; `create sprint` with capacity 10 and
  status Planned is refused. The board reads 8 for a Planned sprint whose row says 10 and the stored value for
  a Closed one; `point` refuses 9 on a Planned sprint.
- **Tracker text.** Three planned empty sprints after the active one: one `planned.` bullet, the next sprint's,
  no `=====` block for any of them; a planned sprint with a week keeps its block; a sprint without a phase
  prints the phase-less bullet; the real file still round-trips.
- **Window.** The Holidays screen is in the navigation list after Weekly Status, shows the loaded rows,
  has no frozen column and no `id` / `order` / `uid` column.

## 7. Risks and decisions

- **Why business days, not calendar days, in `sprint_days`.** The owner's cadence is ten working days;
  a calendar length would drift at every holiday. The config key keeps its name, its meaning changes, and the
  CHANGELOG says so.
- **Why the planner refuses an empty table.** The chain continues from a real sprint; inventing a first
  sprint from today would silently decide the programme's start. `sprint start` is the explicit way.
- **Why capacity is enforced, not defaulted.** The owner's addition: "every single sprint except the one in
  the past is 8 points; set this as a global value that is fixed." A default can be edited around; a rule
  cannot, so the tool sets it on open, refuses an edit on a sprint that is not Closed, and reads the global
  rather than the row for any such sprint. Closed sprints are the past and keep their stored capacity as
  history (Sprint 1 stays 10). `--capacity` and `sprint_capacity` go away for the same reason: an option
  that is always 8 is a trap.
- **Why the TIMELINE prints one planned sprint.** Seventy-odd `planned.` bullets would bury the two that
  matter; the next one is what the reader needs to know.
- **A holiday on the sample date.** The design's expected first start, 2026-11-11, is Veterans Day in the
  seed; the rule says a sprint starts on a business day, so with the holidays loaded it is 2026-11-12. The
  test pins both.
- **The sash of a screen without a frozen column.** The generic screen gives the Holidays table an empty
  left tree; the frozen pane places its sash at the fitted width, zero, which is right.

## 8. Open questions

- Should `days_left` on the board count business days too? Left as calendar days in 0.10.0; the owner reads
  it as "days until the end date".
- Should confirming a holiday (`status = confirmed`) trigger a replan by itself? Not in 0.10.0: `sprint plan
  --replan` is explicit and reported.
- A `confirmed` holiday that is removed again: `--replan` handles it; nothing warns that dates moved back.

## 9. Change log

- 2026-10-28: written, decided; the owner's capacity addition folded in the same day (section 3.4).
- 2026-10-28: implemented as asi_kletz 0.10.0 in four commits (one per phase); every deviation and what the
  design got wrong once it met the code are in `CHANGELOG.md`, section `[0.10.0]`.
