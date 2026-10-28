# ASI Kletz — Plan: points on the Safety Plan, calculated sprint and deadline

**Status:** Implemented 2026-10-28 (asi_kletz 0.11.0); deviations in the CHANGELOG entry
**Written:** 2026-10-28
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.11.0 (after 0.10.0; three new fields on `safety_plan_row`, one new verb; Kletz
only, nothing shared with the sister tool)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md); this plan adds one row to the
plans table and one to the version ladder there, edited by the owner's orchestrating agent after the tag, never
by the agent implementing this plan. No new convention section.
**Sister plans:** [sprint-planner-plan.md](sprint-planner-plan.md) (the sprint chain, holidays, the capacity
rule), [weekly-tracker-plan.md](weekly-tracker-plan.md) (sprints and sprint items).
**The panel's record:** [deliverable-points.md](deliverable-points.md), the estimation panel's consensus per
deliverable, copied unchanged; `data/deliverable-points.json` is its machine form.

---

## 1. The ask

The owner, 2026-10-28, their words:

> the safety plan row details screen must have a space to put in the number of points in a sprint; this means
> that the expected duration and deadline can now be updated with real data, becoming read only: the expected
> duration and deadline field is now a calculated field; another calculated field would be sprint, which tells
> you which sprint this deadline belongs to; when displaying the number of points switch to some default value
> enforced globally, and if the user adds or removes points the GUI tells you there is a default number of
> points and what that is.

The default per deliverable comes from an estimation panel that already ran: three estimator agents each
weighed all 48 deliverables independently, a fourth decided the consensus per row (174 points in all).

The sprint rule (owner, 2026-10-28), honoured here and quoted wherever sprints are explained: a sprint spans
10 business days (weekends and holidays excluded, so holidays stretch dates); capacity is 8 points per sprint,
company policy, a fixed global (`SPRINT_CAPACITY`), only a Closed sprint keeps another number as history;
sprints are consecutive, numbered across the programme.

## 2. What exists today (verified 2026-10-28, asi_kletz 0.10.0)

| Fact | Where |
|---|---|
| `safety_plan_row` has 66 visible fields and the hidden `uid`; `deadline` is `FieldSpec("deadline", T, "Expected Duration/Deadline")`, free text from the owner's sheet (`Phase 1 exit`, dates in several formats); `parse_deadline` reads a date out of it best-effort for the document's "Due within 30 days" table. | `schema/definitions.py:67-84`, `generate/plan_queries.py:131-165`, `generate/documents.py:210-231` |
| `FieldSpec(name, type, label, required, lookup, group, width, help, hidden)`; `hidden` (0.9.0) is the only visibility flag. The form shows every visible non-group field through `WidgetFactory`; `form_data` sends every widget's value; `EntryWidget` is a plain `ttk.Entry`. | `schema/fields.py`, `gui/entity_screen.py:_build_form,form_data`, `gui/widgets.py` |
| `EntityService.guard` (0.10.0): one per-entity check, run after coercion, before the write, on create and update; `Brain.service` attaches the sprint's. No hook runs after a write. `load_rows` writes through the repository and runs no guard. | `services/entity_service.py`, `brain.py:service` |
| The event bus is synchronous; the window refreshes the open screen on any topic but `theme.changed` and `jira.live`. | `automation/events.py`, `gui/main_window.py:_on_event` |
| The sprint chain: `q.sprints` (by number), `q.active_sprint`, `q.capacity_of` (8 unless Closed), `q.items(brain, number)`, `q.committed(items)` (points of items not Carried). A sprint item of kind Deliverable carries `plan_row` (the plan row's id); the tracker import sets it by matching titles. | `generate/sprint_queries.py`, `services/tracker_service.py:_target_row` |
| `sprint close` and `sprint plan` write sprints through the entity service; `holiday load` writes holidays. The planner's dates move only through `sprint plan --replan`. | `services/sprint_service.py`, `services/holiday_service.py` |
| The workbook writes every field (hidden ones hidden); the import maps columns by header text in order; `test_source_workbook_columns_match_the_schema` compares the owner's sheet headers with `visible_fields` (63 since 0.9.0). The owner's sheet has the deadline column and nothing of points. | `io/exporters.py`, `io/importers.py:map_columns`, `tests/test_transfer.py` |
| `CONFIG_INT_KEYS = ("sprint_days",)`; `Brain.sprint_days`; `status` reports the sprint settings. | `brain.py` |
| Tests: 285 pass; several write `deadline` directly as a free field (`test_core`, `test_gui`, `test_generate`, `test_transfer`); the seeded fixture's row 1 has `deadline = "Phase 1 exit"` and status Done. | `tests/` |

## 3. Design

### 3.1 The fields

On `safety_plan_row`, visible, right after `deliverable` so the stack and the form read naturally:

| Field | Type | Header | Flags | Meaning |
|---|---|---|---|---|
| `points` | INT | `Points` | `source=False` | The weight of the deliverable in sprint points, editable, any positive integer; a deliverable may span sprints. Empty means "the default". |
| `default_points` | INT | `Default points` | `source=False`, `readonly=True` | The panel's consensus. Set only by `plan weights load`; read-only in the form; `update --set default_points=` is refused. |
| `sprint` | INT | `Sprint` | `source=False`, `calculated=True` | The number of the sprint in which the deliverable's last point lands. |
| `deadline` | TEXT | `Expected Duration/Deadline` | `calculated=True` | Keeps its name and the owner's header (the import maps by it); its value is now the ISO date of that sprint's `end`. |

`FieldSpec` gains `calculated` (computed by the tool: read-only in the form and the table, refused on
create and update, stripped by the import with a warning), `readonly` (read-only in the form, refused on
create and update, accepted by the import) and `source` (`True` by default: a column of the owner's sheet).
`FieldSpec.editable` is `not hidden and not calculated and not readonly`; `EntitySchema.editable_fields`,
`calculated_fields`, `source_fields` (visible and source) are the tuples the form, the services and the
workbook test use. `points` also carries `default_from="default_points"`, the field whose value the form
shows as its placeholder. The global floor for a row with neither points nor a default is `default_points`
in `kletz.toml` (an integer, default 2; `Brain.default_points`, in `status`), documented in the README's
Configuration section and in `kletz.example.toml`.

### 3.2 The scheduler

One pure module, `generate/plan_schedule.py`: `schedule(rows, sprints, items, floor) -> Schedule` with
`Schedule.assignments: {row id: (sprint number | None, deadline | None)}`, `Schedule.sources: {row id:
"points" | "default" | "floor" | "done" | "excluded"}`, `Schedule.warnings`. Rows come in plan order
(`order`, `id`), sprints by number, items as stored.

- Weight: `points` if set, else `default_points`, else the floor.
- A row with status Done keeps what it has (not in `assignments`; no capacity consumed). Blocked, Alternative
  and Out-of-Scope get `(None, None)`. Every other row is scheduled.
- The chain: the Active sprint (else the first Planned one) and every sprint after it by number that is not
  Closed. Each has a free capacity of `capacity_of(sprint)` minus the points of that sprint's committed items
  that are not Carried (`q.committed`).
- A deliverable that has a sprint item of kind Deliverable with `plan_row` = its id in sprint n never
  finishes before n: its first sprint is the later of the first sprint with free capacity and n.
- Its weight is poured into successive sprints as capacity allows (a full sprint is skipped); the sprint it
  finishes in is its `sprint` and that sprint's `end` its `deadline`.
- When the chain runs out before the weight is placed, the row gets `(None, None)` and a warning names it
  (`row 12 "FTA/FMEA analysis" needs 10 more points: the sprint chain ends at Sprint 77; run sprint plan`).

### 3.3 Recompute

`services/plan_schedule_service.py:PlanScheduleService.recompute(actor="system")` reads the rows, the
sprints and the items, runs the scheduler with `Brain.default_points`, writes `sprint` and `deadline`
through the repository on the rows where they changed (no coercion of calculated fields, no guard), in one
transaction, audited once as `schedule` (the count and the warnings) when anything changed, and publishes
`plan.scheduled` (the count), which refreshes the open screen. It returns `{changed, rows, warnings,
unscheduled}` and is idempotent: a second run changes nothing and audits nothing.

It runs after every change that can move the answer: `EntityService.after`, a new hook called once after a
committed create, update, delete or `load_rows`, is attached by `Brain.service` on `safety_plan_row`,
`sprint` and `sprint_item`; `sprint close`, `sprint plan` and `holiday load` run their writes inside
`PlanScheduleService.deferred()`, which holds the hook and recomputes once at the end; `Brain.__init__` runs
it once after `ensure_schema`, `stamp_uids` and `enforce_capacity` (`migration["scheduled"]`). The
recompute's own writes go through the repository, so no hook fires, and a `_running` flag refuses re-entry.

`EntityService.guard` on `safety_plan_row` (`PlanScheduleService.guard`): `deadline` or `sprint` in a
create or an update is refused with `deadline and sprint are calculated from points and the sprint chain`;
`default_points` with `default_points is set by plan weights load`; `points` must be a positive integer
(empty clears it). The form never sends a read-only field (`form_data` sends `editable_fields` only).

### 3.4 The `plan` verb

- `plan schedule`: recompute now and print the table, one row per deliverable in plan order: `id`,
  `order`, `deliverable`, `points`, `default_points`, `weight`, `source`, `sprint`, `deadline`, `status`;
  plus `changed`, `warnings`.
- `plan weights load <file>`: set `default_points` from a JSON list of `{"id", "order", "deliverable",
  "points"[, "uid"]}`, matching rows by `uid` when the file has one, else by `id`; written through the
  repository, audited once as `weights` with the counts; the report says `set`, `unchanged`, `unmatched`
  (the file rows with no row); then one recompute. The seed is `data/deliverable-points.json`, derived from
  the panel's `consensus.json` (id, order, deliverable, points; 48 rows, 174 points); the record itself is
  `docs/deliverable-points.md`, copied unchanged. Re-running the panel is a diff against that record.

### 3.5 The form and the table

- **Points** (`gui/widgets.py:PointsWidget`): an entry that shows the row's default greyed as a placeholder
  while empty (the row's `default_points`, else the floor); the moment the typed value differs from the
  default a caption beside it says `default 3` (the row's number); clearing the entry returns to the default
  (`get()` is `None`). `EntityScreen._load` hands the widget the row's default before the value.
- **Default points, Sprint, Expected Duration/Deadline** (`ReadOnlyWidget`): an entry in state `readonly`,
  so the value can be selected and copied, never typed into. `WidgetFactory.create` picks it for a
  `calculated` or `readonly` field, `PointsWidget` for a field with `default_from`.
- The table shows all four as columns, fitted as usual; the Matrix is unchanged (flags only).

### 3.6 Files

- The workbook carries the four columns (`points`, `default_points`, `sprint` after `deliverable`;
  `deadline` where it was). The owner's source sheet has only the deadline column:
  `test_source_workbook_columns_match_the_schema` compares its headers with `source_fields` (the fields
  flagged `source`, visible), which is the owner's 63 columns.
- The import accepts `points` and `default_points`; it strips `sprint` and `deadline` from every row of
  `safety_plan_row` and, after the load's recompute, adds one warning naming how many rows carried a value
  that differs from the calculated one (`3 row(s) carried a deadline or sprint that differs from the
  calculated value; the file's values were ignored`). The JSON dump carries everything.

### 3.7 What does not change

The sprint chain and its rules, the tracker text, the Matrix, the dashboard (its open table keeps
`deliverable`, `status`, `deadline`), the documents (the "Due within 30 days" table now reads calculated
dates; its "free text" sentence goes), the hidden identity, the family lock, the automation server.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Schema + scheduler + recompute | `FieldSpec.calculated/readonly/source/default_from`; the three fields and `deadline` calculated; `SCHEMA_VERSION = 5`; `generate/plan_schedule.py`; `PlanScheduleService` (recompute, deferred, guard, weights); `EntityService.after`; the hooks in `Brain`, `sprint close`, `sprint plan`, `holiday load`; the `plan` verb; `default_points` in `kletz.toml`; `docs/deliverable-points.md` and `data/deliverable-points.json`. | The scheduler cases and the recompute triggers of section 6 pass; `plan weights load data/deliverable-points.json` on the seeded fixture sets 3 and reports 45 unmatched; the 0.8.4 fixture opens. |
| 2. Files | `source_fields` in the workbook test; the import stripping `sprint` and `deadline` with the one warning; the tests that wrote `deadline` directly moved to another field. | The transfer cases of section 6 pass. |
| 3. The form and the table | `PointsWidget`, `ReadOnlyWidget`, `form_data` on `editable_fields`, `_load` handing the default; the GUI tests on the new column sets. | The form cases of section 6 pass. |
| 4. Docs + version | README (the Safety Plan section, "Where the defaults came from", Configuration `default_points`, "What is in 0.11.0"), CHANGELOG `[0.11.0] - 2026-10-28`, `docs/plan.md` row, this plan's Status, `version.py` and `pyproject.toml` 0.11.0; commit, push, tag `v0.11.0`, GitHub Release. **No edit to `asi_fusa_tools`.** | `pytest` and `ruff check src tests` clean; the tag and the release exist. |

## 5. Files touched

```
src/asi_kletz/schema/fields.py              calculated, readonly, source, default_from; editable
src/asi_kletz/schema/entity.py              editable_fields, calculated_fields, source_fields
src/asi_kletz/schema/definitions.py         points, default_points, sprint after deliverable; deadline calculated
src/asi_kletz/version.py                    0.11.0, SCHEMA_VERSION = 5
src/asi_kletz/generate/plan_schedule.py     the scheduler, pure
src/asi_kletz/services/plan_schedule_service.py  recompute, deferred, guard, load_weights
src/asi_kletz/services/entity_service.py    after hook; load_rows strips calculated fields and warns
src/asi_kletz/services/sprint_service.py    close and plan inside deferred()
src/asi_kletz/services/holiday_service.py   load inside deferred()
src/asi_kletz/services/__init__.py          PlanScheduleService
src/asi_kletz/commands/plan.py              the plan verb (schedule, weights load)
src/asi_kletz/commands/__init__.py          registration
src/asi_kletz/brain.py                      default_points config key; the schedule service, hooks, the first recompute
src/asi_kletz/generate/documents.py         the "free text" sentence
src/asi_kletz/gui/widgets.py                PointsWidget, ReadOnlyWidget; the factory's choice
src/asi_kletz/gui/entity_screen.py          form_data on editable fields; _load hands the default
data/deliverable-points.json                the panel's consensus as {id, order, deliverable, points}
docs/deliverable-points.md                  the panel's record, unchanged
kletz.example.toml                          default_points = 2
tests/test_schedule.py, test_core.py, test_schema.py, test_transfer.py, test_gui.py, test_generate.py, test_sprint.py, conftest.py
README.md, CHANGELOG.md, docs/plan.md, pyproject.toml, docs/plan-points-plan.md (Status)
```

## 6. Tests

- **Scheduler (pure).** Plan order fills the first sprint first; a 10-point deliverable spans two sprints and
  its deadline is the second one's end; a committed item in sprint 3 pins a 2-point deliverable there; a Done
  row keeps its deadline and consumes nothing; Blocked, Alternative and Out-of-Scope get nothing; a sprint
  with 5 committed points leaves 3; the chain running out gives no sprint, no deadline and a warning naming
  the row; the weight sources (`points`, `default`, `floor`); the Active sprint is the first of the chain,
  the first Planned when none is active.
- **Recompute.** A points change moves the deadline (and audits `schedule` once); closing a sprint moves the
  deadlines after it; `update --set deadline=` and `--set sprint=` are refused with the rule's text;
  `--set default_points=` is refused; `--set points=0` and `points=-1` are refused; the recompute's own
  writes trigger nothing (one audit entry per change); a second recompute changes nothing.
- **Weights.** `plan weights load data/deliverable-points.json` on the seeded fixture (ids 1 to 3) sets 3
  defaults, reports 45 unmatched and recomputes; a second load reports 3 unchanged; a file row with a uid
  matches by uid before id; the seed has 48 rows and 174 points; the record file exists.
- **Files.** The plan sheet has 67 headers (`Points`, `Default points`, `Sprint` after `Safety Deliverables`,
  `uid` last and hidden); export then import keeps points and defaults; an import whose rows carry a
  deadline or sprint that differs from the calculated value warns once and keeps the calculated value; the
  owner's sheet matches `source_fields` (63).
- **Form.** The Points entry shows `3` greyed while empty for a row whose default is 3 and the floor when
  the row has none; typing `5` shows the caption `default 3`; typing `3` shows no caption; clearing returns
  to the placeholder and saves `points = None`; Default points, Sprint and Deadline widgets are read-only and
  copyable; `form_data` never carries them; the table has the four columns; the Matrix is unchanged.
- **Fixture.** The 0.8.4 database opens: uids stamped, the capacity rule, the three new columns on
  `safety_plan`, one recompute (no chain: no row scheduled, a warning per open row).

## 7. Risks and decisions

- **Why `deadline` keeps its name and header.** The owner's workbook has the column under that header and
  the import maps by header; renaming it would orphan the sheet. The header reads as before; the value is a
  date now.
- **Why `default_points` is refused on update but accepted by the import.** The panel's record is the
  source of defaults; a hand edit would drift from it unnoticed. A workbook or dump that carries defaults is
  a copy of the record (the export wrote it), so the import keeps them.
- **Why the recompute runs synchronously in the hooks.** The answer must be right the moment a command
  returns (the window reads it on refresh; an agent reads it in the `Result` of the next `get`). The plan is
  48 rows and the chain 77 sprints; one pass is milliseconds.
- **Committed items that are the deliverable's own work count against capacity and pin the row.** The brief
  says so; it can double count a deliverable's own sprint item against its weight. Open question below.
- **Done rows keep a free-text deadline** (`Phase 1 exit`): history, like a Closed sprint's capacity.

## 8. Open questions

- Should a Deliverable sprint item's points be subtracted from the deliverable's remaining weight instead of
  from the sprint's capacity (no double count)? Owner's call after the first schedule is read.
- Should the dashboard's open table show `sprint`? Not in 0.11.0.
- Should `plan schedule --as-of` schedule from a date rather than from the Active sprint? Not in 0.11.0.

## 9. Change log

- 2026-10-28: written, decided.
- 2026-10-28: implemented as asi_kletz 0.11.0 in four commits (one per phase); every deviation and what the
  design got wrong once it met the code are in `CHANGELOG.md`, section `[0.11.0]`.
