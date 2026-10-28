# ASI Kletz — Plan: hidden identity (`uid`) and the end of the `id` / `order` columns

**Status:** Implemented 2026-10-28 (asi_kletz 0.9.0); deviations in the CHANGELOG entry
**Written:** 2026-10-28
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.9.0
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md). This plan adds one
convention section to the charter ("Identity: `id` and `uid`"), one row to the plans table and one to the
version ladder. The charter is edited by the owner's orchestrating agent once both tools have shipped,
never by the agent implementing this plan.
**Sister plan:** [asi_dewey/docs/hidden-identity-plan.md](../../asi_dewey/docs/hidden-identity-plan.md).
Same convention, implemented twice, never shared as code. The two implementations run in tandem; the
only thing they must agree on byte for byte is section 3.1 (the `uid` value and where a file carries it),
because a Kletz workbook or JSON dump is imported into Dewey.

---

## 1. The ask

The owner, 2026-10-28, on every table of both tools:

> it is obviously important that all objects have some internal guid that is not visible but serves for
> traceability; then of course we want to preserve the order of elements in a table; but the leftmost
> columns `order` and `id` are vestigial: `order` was there in case a sorting operation broke order and
> the id is just the order.

Agreed, with one correction the owner accepted: `order` is the position in the plan and `id` is the
insertion sequence; they coincide today only because the plan was imported in order, and `id` cannot be
renumbered when a row is inserted, duplicated or re-imported. So:

1. **Every row of every entity carries a `uid`**: assigned once on creation, never shown in a table or a
   form, never changed, carried by every file the tool writes (JSON, workbook) and honoured by every
   import. It is the pointer a document, a sibling or a later database uses to say "this row".
2. **No table shows `id` or `order`.** The `id` stays the short handle of the command vocabulary
   (`update safety_plan_row 2 ...`), the row iid of every tree, the audit log's `entity_id` and the status
   bar's "Safety Plan Row 2 selected". `order` stays a field of the plan, editable in the form, and the
   default sort; it just has no column.
3. **The order of the elements is preserved** by `order` (plan rows), `number` (sprints), `order` within a
   sprint (sprint items) and `start` + `order` (weeks), as today, and by the stack on the two Safety Plan
   screens (0.8.3, 0.8.4).

## 2. What exists today (verified 2026-10-28, asi_kletz 0.8.4)

| Fact | Where |
|---|---|
| Four entities (`safety_plan_row`, `sprint`, `sprint_item`, `week`); every table has `id INTEGER PRIMARY KEY AUTOINCREMENT`, the fields, `created_at`, `updated_at`. `ensure_schema` creates a missing table and adds a missing column with `ALTER TABLE … ADD COLUMN`, then records the registry fingerprint in `schema_migrations`. No data migration step exists. | `storage/sqlite.py:98-130`, `schema/definitions.py` |
| `FieldSpec(name, type, label, required, lookup, group, width, help)`; no notion of a hidden field. `coerce_row` rejects unknown fields and coerces every known one; `SYSTEM_FIELDS` are passed through. | `schema/fields.py:56-75`, `schema/entity.py:73-105` |
| `EntityService.create` coerces, inserts, audits `create` with the new `id`, publishes `entity.created`. `update` coerces partially and updates by `id`. | `services/entity_service.py:52-70` |
| `load_rows(rows, mode)`: `replace` wipes first; `merge` upserts **by `id`** (`repo.exists(id)` → update, else create keeping the id); `append` inserts fresh ids. The `id` key is stripped before coercion. | `services/entity_service.py:79-126` |
| JSON dump: `brain.service(name).list()` rows, so `id`, `created_at`, `updated_at` and every field. Workbook: one column per `schema.fields` entry headed `spec.header`, **no `id` column**; import maps columns by header text in order; `len(headers) == 63` for the plan is asserted. | `io/exporters.py:71-160`, `io/importers.py:101-150`, `tests/test_transfer.py:45`, `tests/test_schema.py:71` |
| Repository API: `get(id)`, `list(filters, order_by, limit, offset)`, `count`, `exists(id)`, `create(data, row_id=None)`, `update`, `delete`, `delete_all`, `bulk_insert(rows, keep_ids)`. `list --filter key=value` is generic over any field. | `repositories/sql_repo.py`, `commands/crud.py:14-41` |
| Tables in the window: **Safety Plan** (frozen `id`, `order`, `plan`; 59 scrolling columns; `cell_text` per column), **Safety Plan Matrix** (`FIXED = ("order", "plan")`), **Dashboard** (`OPEN_COLUMNS = ("order", "deliverable", "status", "deadline")`, `AUDIT_COLUMNS = (… "entity_id")`, `PHASE_COLUMNS`), **Sprint Board** lanes (`LANE_COLUMNS = ("points", "kind", "title", "ref")`), **JIRA Live Data** (the Jira key is its identity). The Weekly Status screen has pickers, no table. | `gui/entity_screen.py:FROZEN`, `gui/matrix_screen.py:FIXED`, `gui/dashboard.py:20-22`, `gui/sprint_board_screen.py:25` |
| The form shows every non-group field (`order` included) and the flag groups; `new`, `save`, `duplicate` (clears `order`), `delete` work on `selected_id`. | `gui/entity_screen.py:_build_form`, actions |
| Tests: 254 pass; the frozen-column tests pin `FROZEN_PLAN = ["id", "order", "plan"]`, 59 displayed columns and the nine-row stack; the transfer tests pin 63 workbook headers. | `tests/test_gui.py`, `tests/test_transfer.py` |

## 3. Design

### 3.1 The `uid` (shared with Dewey, byte for byte)

- **Field.** `uid`, `FieldType.TEXT`, header `uid`, `hidden=True`, the **last** field of every entity. Value:
  the canonical lowercase UUID4 with dashes, 36 characters (`str(uuid.uuid4())`). Validation on coercion:
  when present it must match `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`; a
  value in another case or with braces is normalised to the canonical form; anything else is a
  `ValidationError`.
- **Assigned once.** `EntityService.create` sets `uid` when the row has none. `update` with a `uid` that
  differs from the stored one is a `ValidationError("uid is immutable")`; the same value is a no-op.
  `duplicate` in the window makes a new row, so a new uid.
- **Unique.** `CREATE UNIQUE INDEX IF NOT EXISTS ix_<table>_uid ON <table>(uid)` after the column exists.
- **Stamped on open.** After `ensure_schema`, `Storage.stamp_uids(registry)` gives every row whose `uid`
  is NULL or empty a fresh value, one `UPDATE … WHERE id = ?` per row inside one transaction, audited once
  per table as `stamp_uids` with the count. A 0.8.x `kletz.db` therefore opens as 0.9.0 with every row
  identified and nothing else changed. `SCHEMA_VERSION = 3`.
- **In files.** JSON: the row dicts carry `uid` as they carry every field. Workbook: `uid` is the last
  column of every sheet, headed `uid`, written with `ws.column_dimensions[letter].hidden = True` so the
  sheet reads as before and still round-trips. The import maps it by header like any field.
- **On load.** `load_rows`: a row with a `uid` that exists in the table is an **update of that row**
  (whatever its `id` in the file); otherwise a row with an `id` that exists is an update by `id` (merge
  mode only, as today); otherwise an insert that keeps the file's `uid` when present (all modes) and the
  file's `id` in merge mode. `replace` wipes first and keeps the file's uids. So a Kletz dump imported into
  Dewey gives Dewey's cached plan rows Kletz's uids, and a later import of a newer dump updates them in
  place.
- **Readable.** `get <entity> <ref>`, `update`, `delete` accept a uid where an id is expected: a `ref`
  that is all digits is an id, a `ref` matching the uid pattern is resolved through `repo.get_by_uid`; an
  unknown uid is `NotFound`. `list --filter uid=…` works as it does for any field. The automation server's
  row endpoints take the same `ref`.

### 3.2 Hidden fields

`FieldSpec.hidden: bool = False`. A hidden field has no widget in the form, no column in any table, no
entry in `fit_columns` candidates, and no place in a diagram or document unless the generator asks for it
by name. It is written to and read from every file. `EntitySchema.visible_fields` is the tuple the window
uses; `fields` stays the full tuple the storage and the transfers use. Only `uid` is hidden in 0.9.0.

### 3.3 The tables

| Table | Today | 0.9.0 |
|---|---|---|
| Safety Plan (`gui/entity_screen.py`) | frozen `id`, `order`, `plan`; `columns = ["id"] + fields` | frozen `plan` alone (`FROZEN = (PLAN,)`); `columns = visible fields` (no `id`); `IDENTITY` (the frozen set of an entity without the stack) drops `id` and `order` too. The tree iids stay the ids. Sorting by `plan` returns to plan order as in 0.8.4. |
| Safety Plan Matrix (`gui/matrix_screen.py`) | `FIXED = ("order", "plan")` | `FIXED = (PLAN,)`; `FIXED_WIDTHS = (360,)`; `SEARCHED` keeps `order` so a typed number still finds the row. |
| Dashboard open deliverables (`gui/dashboard.py`) | `OPEN_COLUMNS = ("order", "deliverable", "status", "deadline")` | `("deliverable", "status", "deadline")`, rows still in plan order. The audit table keeps `entity_id`: it is the trace, not a vestige. |
| Sprint Board lanes | no id | unchanged |
| JIRA Live Data | the Jira key | unchanged |
| The form | every non-group field | every visible non-group field; `order` stays. The details frame's title gains the id: `Safety Plan Row details · row 2`, so the handle a command needs is on screen without a column. |

### 3.4 What does not change

The command vocabulary (`id` positional, now also a uid), the audit log, the events, the tracker text,
the sprint rules, the family lock, the automation server's shape, the workbook's visible columns and
their order, the JSON shape apart from the new key.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Schema + storage + service | `FieldSpec.hidden`, `EntitySchema.visible_fields`; `uid` as the last field of the four entities (`definitions.py`); `new_uid()` and `UID_PATTERN` in `schema/fields.py`; coercion and normalisation; `create` assigns, `update` refuses a change; `Storage.stamp_uids` + the unique index in `ensure_schema`; `Brain.__init__` calls `stamp_uids` after `ensure_schema`; `SCHEMA_VERSION = 3`; `repo.get_by_uid`. | `uv run pytest` passes; a copy of a 0.8.4 `kletz.db` opened by 0.9.0 has `uid` on every row of every table, the four unique indexes, one `stamp_uids` audit entry per table with a count, and no other change (diff of a JSON dump minus `uid`). |
| 2. Files + commands | JSON unchanged apart from the key; workbook `uid` last and hidden; `load_rows` matches by uid first (3.1); `get` / `update` / `delete` and the server's row endpoints resolve a uid `ref`. | Export → import on a fresh database gives the same uids; a dump with the ids shifted by 100 merges by uid as updates, not inserts; `get safety_plan_row <uid>` returns the row; `update … <uid> --set uid=…` fails with `uid is immutable`. |
| 3. Tables + form | 3.3: no `id`, no `order`, no hidden field on any table; `FROZEN = (PLAN,)`, `FIXED = (PLAN,)`, `OPEN_COLUMNS` without `order`; the details frame names the row id; `fit_columns` and the frozen pane unchanged otherwise. | `test_gui.py` passes with the new column sets; no tree in the window has a column named `id`, `order` or `uid` (one test walks every screen); the status bar still says `Safety Plan Row 2 selected`. |
| 4. Docs + version | README ("What is in 0.9.0", the Safety Plan and Matrix bullets, a short "Identity" paragraph under the Python API section: id is the handle, uid is the trace), CHANGELOG 0.9.0 with any deviation, `version.py` and `pyproject.toml` 0.9.0, `kletz.example.toml` untouched; commit, push, annotated tag `v0.9.0`, GitHub Release with the CHANGELOG section (charter, "Releases and tags"). **No edit to `asi_fusa_tools`.** | `uv run pytest` and `uv run ruff check src tests` clean; the tag and release exist; this plan's Status line says Implemented. |

## 5. Files touched

```
src/asi_kletz/schema/fields.py          FieldSpec.hidden, UID_PATTERN, new_uid, coercion of a uid
src/asi_kletz/schema/entity.py          visible_fields; the immutability check lives in the service
src/asi_kletz/schema/definitions.py     uid last on safety_plan_row, sprint, sprint_item, week
src/asi_kletz/version.py                0.9.0, SCHEMA_VERSION = 3
src/asi_kletz/storage/base.py           stamp_uids on the interface
src/asi_kletz/storage/sqlite.py         the unique index in ensure_schema; stamp_uids
src/asi_kletz/brain.py                  stamp_uids after ensure_schema; "uids_stamped" in the migration summary
src/asi_kletz/repositories/sql_repo.py  get_by_uid
src/asi_kletz/services/entity_service.py  create assigns; update refuses; load_rows by uid; resolve(ref)
src/asi_kletz/commands/crud.py          id positional accepts a uid (type "ref")
src/asi_kletz/automation/server.py      the row endpoints take the same ref
src/asi_kletz/io/exporters.py           workbook: uid last and hidden
src/asi_kletz/gui/entity_screen.py      FROZEN = (PLAN,); columns = visible fields; details title
src/asi_kletz/gui/matrix_screen.py      FIXED = (PLAN,)
src/asi_kletz/gui/dashboard.py          OPEN_COLUMNS without order
src/asi_kletz/gui/widgets.py            no widget for a hidden field (WidgetFactory.create raises; the form skips)
tests/test_schema.py, test_core.py, test_transfer.py, test_cli.py, test_server.py, test_gui.py
tests/fixtures/kletz-0.8.4.db           a small 0.8.4 database (three plan rows, one sprint) for the open-and-stamp test
README.md, CHANGELOG.md, pyproject.toml, docs/hidden-identity-plan.md (Status)
```

## 6. Tests

- **Schema.** Every registered entity ends with `uid`, hidden, TEXT; `visible_fields` excludes it; the
  registry fingerprint changes (so `schema_migrations` gains a row on open). Coercion: canonical uid
  accepted, upper case and braces normalised, `not-a-uid` rejected with the field named.
- **Storage.** A 0.8.4 fixture database opened by 0.9.0: the column and the unique index on every
  table, every row stamped, counts audited, nothing else changed. Opening it twice stamps nothing the
  second time. Two rows cannot share a uid (the index raises; the service reports it as an error, not a
  crash).
- **Service.** `create` without a uid gets one; `create` with a uid keeps it; `update` changing it fails;
  `get_by_uid`; `resolve("12")` and `resolve("<uid>")`.
- **Transfer.** The plan sheet has 64 headers, the last `uid`, and that column is hidden; export →
  import (replace) on an empty database keeps every uid; a JSON dump with every `id` shifted by 100 merges
  as 3 updates and 0 inserts; a dump without uids (a 0.8.x file) still imports and the new rows are
  stamped.
- **Commands and server.** `get`, `update`, `delete` by uid; an unknown uid is `NotFound`; `list
  --filter uid=…`.
- **Window.** No table on any screen has a column named `id`, `order` or `uid`; the Safety Plan's frozen
  pane holds `plan` alone and the right tree displays 58 columns (59 minus `order`, `uid` never); the
  matrix's `FIXED` is `(plan,)`; the dashboard's open table has three columns; the form has no `uid`
  widget and still has `order`; the details title names the selected row; selecting, saving,
  duplicating and deleting work as in 0.8.4.

## 7. Risks and decisions

- **Why not a GUID as the primary key.** The integer `id` is typed by people and agents all day; a
  36-character key would be hostile on the command line and in the status bar. Jira has an id and a key
  for the same reason. Decided: `id` handle, `uid` trace.
- **Why `uid` is in the workbook at all when it is hidden.** Without it a workbook edited in Excel and
  imported back cannot say which row it is, and ids are not in the sheet. Hidden column, present data.
- **`sprint_item.plan_row` points at a plan row by id.** Left as is in 0.9.0: it is a local reference
  inside one database. Open item below.
- **Dewey's cached plan rows.** They get Kletz's uids on the next import of a Kletz dump or workbook
  (3.1, on load). Until then Dewey's rows carry uids of their own; that is correct, they are different rows
  in a different database.
- **Tandem risk.** The two agents must not edit each other's repo or the charter. The orchestrating
  agent adds the charter section and the two table rows after both have tagged.

## 8. Open questions

- Should `sprint_item.plan_row` become `plan_uid` (a uid), so a tracker dump survives a plan re-import
  that renumbers ids? Probably yes, in the release after this one, with the tracker import matching
  deliverables by uid first and title second.
- Should Gutenberg documents print the uid of every row they cite, in a provenance appendix? Owner's call;
  the hidden rule says a document asks for it by name.

## 9. Change log

- 2026-10-28: written, decided; the sister plan written the same day.
- 2026-10-28: implemented as asi_kletz 0.9.0 in four commits (one per phase); every deviation and
  what the plan got wrong are in `CHANGELOG.md`, section `[0.9.0]`.
