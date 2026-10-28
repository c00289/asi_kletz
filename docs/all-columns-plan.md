# ASI Kletz — Plan: every Safety Plan column in the table

**Status:** Implemented 2026-10-27 (asi_kletz 0.4.0); deviations recorded by the implementing agent in the CHANGELOG entry.
Since then: the 36 px flag columns of section 3 were replaced by widths fitted to the heading (0.7.1,
`fit_columns`), the hover hint of section 8 landed in 0.7.0, and the screen-count rule was retired in 0.5.0.
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.4.0 (after the family palette 0.3.0, before the JIRA Live Data
window 0.5.0; see the version ladder in the family document)
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md).
**Sister plan:** [asi_dewey/docs/prune-windows-plan.md](../../asi_dewey/docs/prune-windows-plan.md).
The 0.4.0 pair: Kletz shows every Safety Plan column, Dewey stops showing the Safety Plan at all.

---

## 1. The ask

Asked by the owner on 2026-10-27:

1. The safety plan windows in Kletz must include **all columns from the source workbook**.
2. "It felt like in one window we stopped at the column for DMS/JAMA/Sharepoint": the Safety
   Plan table ends at `Work Product Location`, and the next three source columns (DMS, JAMA,
   Sharepoint) are nowhere in it.
3. Nothing about the data changes: one table, 63 fields, the same workbook round trip, the same
   screens (four at the time; the screen-count rule was retired in 0.5.0: screens are registered in `gui/screens.py`, not counted).

## 2. What exists today (verified 2026-10-27)

| Fact | Where |
|---|---|
| `kletz.xlsx` has one sheet, `Safety Plan`, with 63 header cells in row 1, from `order` to `Status (Pending/ Ongoing/ Blocked/ Alternative/Out-of-Scope/ Done)`. Read with openpyxl on 2026-10-27; the full list is in section 3.1. | `kletz.xlsx` |
| `safety_plan_row` declares 63 fields in the same order as the sheet, with `label` equal to the source header (flag fields through `flag_fields(group, prefix, headers)`). 53 are `BOOL` (`is_flag`), 10 are not: `order`, `pdp_phase`, `lifecycle_phase`, `deliverable`, `work_product_location`, `work_product_reference`, `author`, `gate_reviewer`, `deadline`, `status`. Groups in field order: `''` (8), `location` (3), `reference` (23), `author` (18: the text field plus 17 flags), `verification` (3), `reviewer` (8: the text field plus 7 flags). | `schema/definitions.py` lines 37-82; `schema/entity.py` lines 63-67, 125-130; `schema/fields.py` lines 74-77, 88-89 |
| **The cause.** `gui/entity_screen.py` has `MAX_FLAG_COLUMNS = 8`; `build()` sets `self.columns = ["id"] + [f.name for f in fields if not f.is_flag or len(flags) <= MAX_FLAG_COLUMNS]`. With 53 flags the condition is false for every flag, so the Safety Plan table has **11 columns**: `id`, `order`, `PDP Phases`, `Safety Lifecycle Phase`, `Safety Deliverables`, `Work Product Location`, `Work Product Reference`, `Author`, `Gate Reviewer`, `Expected Duration/Deadline`, `Status (...)`. DMS, JAMA and Sharepoint, which follow `Work Product Location` in the source, are the first columns to vanish; that is what the owner saw. | `gui/entity_screen.py` lines 16, 42-45 |
| The same screen already renders a `BOOL` cell as a check mark or blank (`cell_text`), already gives a flag column `width=50`, and already has **both scrollbars**: `ybar` vertical and `xbar` horizontal, gridded under the tree at row 1 (local variables, not attributes). Column widths: `id` / INT 60, flag 50, MULTILINE / URL 320, DATE 100, else 180; only MULTILINE columns stretch. | `gui/entity_screen.py` lines 20-26, 64-89 |
| The table and the form sit in a vertical `ttk.PanedWindow` (weights 3 and 2). The form shows **every field**: ungrouped fields as label + widget rows, then one `LabelFrame` per group with flags three per row and the group's text fields full width. So the edit form already shows all 63; only the table is short. | `gui/entity_screen.py` lines 61-62, 93-137 |
| `_populate()` fills `values=[cell_text(...) for c in self.columns]` per row and calls `theme.stripe()`; `sort_by(column)` sorts on the raw value (a bool sorts as 0/1); the heading click of every column calls `sort_by`. | `gui/entity_screen.py` lines 74-77, 156-183 |
| The matrix screen (`safety_plan_matrix`) shows `FIXED = ("order", "pdp_phase", "lifecycle_phase", "deliverable")` plus the flags of **one** group chosen in a read-only `Flag group` combobox (default `location`, the first group); it never shows `work_product_location`, `work_product_reference`, `author`, `gate_reviewer`, `deadline`, `status`. Flag columns are `max(60, min(len(header) * 7, 200))` wide, centred, not stretched; it has both scrollbars and the window does not grow when the reference group (23 columns, up to 4600 px) is selected. | `gui/matrix_screen.py` lines 14-16, 28-34, 46-67 |
| Screens are fixed at four: `dashboard`, `safety_plan`, `safety_plan_matrix`, `transfer`; the test suite asserts the list and `nav.size() == 4`. | `gui/screens.py` lines 96-113; `tests/test_gui.py` lines 13-14, 44-47 |
| Export and import carry all 63 columns: `ExcelExporter` writes one header per `schema.fields` entry (`spec.header`) and `1`/`0` per flag; `ExcelImporter.map_columns` maps headers to fields **in order**, so the two `Tech Lead - Functional Safety` headers (author, reviewer) map to their own fields; `JsonExporter` dumps full rows. `test_excel_export_and_reimport` asserts `len(headers) == 63`, the duplicate header count of 2, and `loc_dms` / `reviewer_tech_lead_functional_safety` survive the round trip. | `io/exporters.py` lines 112-158; `io/importers.py` lines 102-115, 136-150; `tests/test_transfer.py` lines 34-55 |
| `tests/test_gui.py::test_safety_plan_form_has_groups` line 115 asserts `"loc_dms" not in screen.columns` with the comment "too many flags for the table; the matrix screen shows them". It documents the cap. | `tests/test_gui.py` lines 112-117 |
| The `seeded` fixture creates three rows; row 1 has `loc_dms`, `ref_qf_17`, `author_fusa_engineer`, `verify_level_u3_refer_section_3_2`, `reviewer_tech_lead_functional_safety` set; row 2 has `loc_jama`, `ref_qp_11`, `author_asi_stpa_practitioners`. | `tests/conftest.py` lines 36-54 |
| `ttk.Treeview` supports `displaycolumns` (a subset of `columns`, in any order, or `#all`); hidden columns keep their values and headings, `tree.set(iid, col)` still reads them. `ttk.Treeview` has no frozen (pinned) columns. | Tk 8.6 `ttk::treeview` manual |
| `Muted.TLabel` and `theme.stripe()` exist in every theme; the toolbar already holds `Search`, the five buttons and a right-aligned count label. | `gui/theme.py` lines 131, 146, 225; `gui/entity_screen.py` lines 47-59 |
| Docs: README "Four screens" bullet (lines 32-44) describes the Safety Plan screen as "sortable, searchable table of deliverables with a form below; flag groups rendered as checkbox grids"; `docs/plan.md` section 2 says "flag groups drive the matrix screen"; section 8 is a `Phase / Content / Status` table whose `next` row is the family lock; section 9 is the change log. | `README.md`, `docs/plan.md` lines 34-45, 135-152 |
| Versions: `version.py` and `pyproject.toml` say 0.3.0; `CHANGELOG.md` has `[0.3.0]` and an `[Unreleased]` block ("Planned: the family lock", now 0.6.0 on the ladder). The family document's version table says 0.2.0 for both primary tools; its plans table lists five plans. | `src/asi_kletz/version.py`, `pyproject.toml`, `CHANGELOG.md` lines 7-18, the family document (now `../asi_fusa_tools/ASI_FUSA_TOOLS.md`) lines 7-13, 216-224 |

## 3. Design

### 3.1 The source columns and the fields (the mapping)

All 63 source columns exist as fields, in source order. `id` is the surrogate key and has no
source column; it is the first table column. Flag fields are named `<prefix>_<slug(header)>`.

| # | Source column | Field | Group |
|---|---|---|---|
| 1 | order | `order` | |
| 2 | PDP Phases | `pdp_phase` | |
| 3 | Safety Lifecycle Phase | `lifecycle_phase` | |
| 4 | Safety Deliverables | `deliverable` | |
| 5 | Work Product Location | `work_product_location` | |
| 6-8 | DMS, JAMA, Sharepoint | `loc_dms`, `loc_jama`, `loc_sharepoint` | location |
| 9 | Work Product Reference | `work_product_reference` | |
| 10-32 | Foundational RA, PDP/QF, PDP-16, PDP-17, Platform FSC, Platform TSC, QF-12, QF-17, QF-18, QF-19, QF-FSA Report, QF-Safety Case, QM/QP-Risk Assessment Plan, QM-Production Plan, QM-Validation Plan, QP-06, QP-11, QP-12, QP-31, QP-32, QP-FSA, Scope Definition, Supplier | `ref_foundational_ra` ... `ref_supplier` (23) | reference |
| 33 | Author | `author` | author |
| 34-50 | Dev Manager, Electronics Engineer (Mechanical and Electrical), Embedded Software Engineer, FuSa Engineer, Mechatronics Software Engineer, Mechatronics Systems Engineer, Product Manager, Production Team, Reliability Engineer, Respective Robot Team Member, Robot Chief, System Architect, Tech Lead - Occupational Safety, V&V Team, Independent Reviewer, ASI STPA Practitioners, Tech Lead - Functional Safety | `author_dev_manager` ... `author_tech_lead_functional_safety` (17) | author |
| 51-53 | Level U3 (refer section 3.2), QP-06 Review Process, Scope Definition Review | `verify_level_u3_refer_section_3_2`, `verify_qp_06_review_process`, `verify_scope_definition_review` | verification |
| 54 | Gate Reviewer | `gate_reviewer` | reviewer |
| 55-61 | Tech Lead - Functional Safety, Tech Lead - Occupational Safety, Tech Lead - Respective Area, Tech Lead - Safety and Compliance, Tech Lead - Systems, PAT, Technical Training Team | `reviewer_tech_lead_functional_safety` ... `reviewer_technical_training_team` (7) | reviewer |
| 62 | Expected Duration/Deadline | `deadline` | |
| 63 | Status (Pending/ Ongoing/ Blocked/ Alternative/Out-of-Scope/ Done) | `status` | |

Source order and field order agree position by position (checked header against
`[f.header for f in schema.fields]` on 2026-10-27). The schema is not touched.

### 3.2 What each window shows today, and after

| Window | Today | After 0.4.0 |
|---|---|---|
| Safety Plan, table | 11 columns: `id` + the 10 non-flag fields; no flag column at all | 64 columns: `id` + all 63 fields in source order; a `Columns` selector narrows the flags to one group |
| Safety Plan, form | all 63 fields (ungrouped rows, then five group boxes) | unchanged |
| Safety Plan Matrix | `order`, `pdp_phase`, `lifecycle_phase`, `deliverable` + one flag group (3 to 23 columns), click to toggle | unchanged |
| Dashboard, Export / Import | no row columns | unchanged |

The two Safety Plan screens stay distinct on purpose: the table is the full sheet with a form
to edit a row; the matrix is the fast flag editor for one group at a time.

### 3.3 The cap goes; flag columns are narrow

In `gui/entity_screen.py`:

- `MAX_FLAG_COLUMNS` is deleted. `self.columns = ["id"] + [f.name for f in self.schema.fields]`,
  always. `id` first, then source order, so `order`, `pdp_phase`, `lifecycle_phase` and
  `deliverable` are the leftmost data columns and a row is recognisable before any scrolling.
  `ttk.Treeview` cannot freeze columns, so this ordering is the only "pin" available; a note in
  the README says so.
- `FLAG_WIDTH = 36`. A flag column is `width=36, minwidth=36, stretch=False, anchor="center"`,
  headed by `spec.header` (the source title) and filled by `cell_text` with a check mark or
  blank, as today. A 36 px heading clips a long title such as `Electronics Engineer (Mechanical
  and Electrical)`; the user can drag the heading separator to widen it for the session, and
  the status bar names the full column when a heading is clicked to sort (`Sorted by <header>`,
  one line added to `sort_by`). Non-flag columns keep today's widths and stretch rule.
- The two scrollbars become `self.ybar` and `self.xbar` so a test can see them; their layout is
  unchanged (row 0 col 1, row 1 col 0). With 53 x 36 px plus the ten non-flag widths the tree
  is about 3,400 px wide at 1280 px of window: the horizontal bar is the way across it, the
  vertical bar the way down it. The holder is the same `grid` layout the matrix screen uses,
  which already carries a 4,600 px reference group without growing the window (the toplevel has
  an explicit geometry and does not follow a child's requested width). The form below sits in
  the other pane of the vertical `PanedWindow` and is not affected by the table's width.
- The cell text of a flag stays the single check mark; `TRUNCATE` applies to text columns only.

Nothing changes for an entity with few or no flags: the generic screen still derives its columns
from the schema, and Kletz has exactly one entity.

### 3.4 The `Columns` selector

A read-only `ttk.Combobox` in the toolbar, after the `Search` entry and before the buttons,
captioned `Columns`, built only when the schema has at least one flag group:

- Values: `All`, then one entry per flag group in field order, title-cased from the group key:
  `Location`, `Reference`, `Author`, `Verification`, `Reviewer`. `self.columns_var` holds the
  current title; `self.column_groups: dict[str, str]` maps title to group key.
- `set_columns(choice: str) -> None`: `All` sets `self.tree["displaycolumns"] = "#all"`; a group
  sets it to `[c for c in self.columns if c == "id" or not field(c).is_flag or field(c).group == group]`,
  which is every non-flag column (the 10 of them plus `id`, in place) and the chosen group's
  flags. The tree is never rebuilt: `columns`, headings, widths, sort state and the selection
  survive; `tree.set(iid, hidden_column)` still works for the form and the tests.
- `<<ComboboxSelected>>` calls `set_columns(self.columns_var.get())`; the count label is
  unchanged (rows, not columns).
- Default `All`. The choice lives on the screen instance, which `MainWindow` caches in
  `_screens`, so it survives navigating away and back; it is not written to `prefs.json` or
  `kletz.toml`. A theme pick rebuilds every screen (`set_theme`) and the selector returns to
  `All`; a restart returns it to `All`. That is "remembered for the window session only".
- The matrix screen keeps its own `Flag group` combobox; the two selectors share nothing.

### 3.5 Export, import, storage

No change. `export` already writes the 63 headers and `import` already reads them back in
order; the JSON dump carries full rows. This plan touches no schema, no storage, no table, no
verb. Still one table, still four screens today (the screen-count rule is retired in 0.5.0 by
`jira-live-data-plan.md`; screens are then registered, not counted), `SCHEMA_VERSION` stays 1.

### 3.6 Documentation wording

- `README.md`: version 0.4.0 in line 4; a "What is in 0.4.0" section; the Safety Plan bullet in
  "Four screens" becomes "sortable, searchable table of every column of the source sheet in
  source order (`id` first; flags as narrow check-mark columns; a `Columns` box narrows the flags
  to one group; scroll sideways, the Treeview cannot pin columns) with a form below; flag groups
  rendered as checkbox grids; New / Save / Delete / Duplicate / Refresh".
- `docs/plan.md`: section 2 note becomes "63 columns; the table shows all of them, the matrix
  one flag group at a time"; section 8 gains a `0.4.0` row before `next`; section 9 gains a
  dated line.
- `CHANGELOG.md`: a `[0.4.0] - <date>` entry with `Changed` (the cap removed, narrow flag
  columns, the `Columns` selector, `Sorted by` status line, `xbar` / `ybar` attributes) and
  `Fixed` (the Safety Plan table stopped at `Work Product Location`). While there, the
  `[Unreleased]` heading "Planned: the family lock" gains "(0.6.0)" to match the ladder; the
  single-instance plan carries its own retarget.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Table | `MAX_FLAG_COLUMNS` removed; `FLAG_WIDTH = 36`, centred flag columns headed by the source title; `self.xbar` / `self.ybar`; `Sorted by` status line; `tests/test_gui.py` line 115 flipped and the new column tests of section 6. | `uv run pytest` and `uv run ruff check src tests` clean; `screen.columns` has 64 entries; opening the Safety Plan screen on the seeded database shows a check mark under `DMS` for row 1 and under `JAMA` for row 2. |
| 2. Columns selector | `columns_var`, `column_groups`, `set_columns`, the combobox in the toolbar; `displaycolumns` tests. | Choosing `Location` leaves 14 visible columns; `All` restores 64; the choice survives a trip to the dashboard and back; the matrix screen's selector is untouched. |
| 3. Docs | README "What is in 0.4.0" and the Safety Plan bullet; CHANGELOG `[0.4.0]` and the Unreleased heading; `docs/plan.md` sections 2, 8, 9; `version.py` and `pyproject.toml` 0.4.0. | `asi-kletz-gui --version` prints 0.4.0; the window title and the nav brand say 0.4.0; the README no longer implies the table hides columns. |
| 4. Family | Family document: version table row for `asi_kletz` reads 0.4.0; plans table gains this plan and the sister plan. | The family file names both 0.4.0 plans; `tests/test_theme.py` still finds the palette digest in it; tag left to the owner. |

## 5. Files touched

```
src/asi_kletz/gui/entity_screen.py         cap removed; FLAG_WIDTH; xbar/ybar attributes; Columns selector; set_columns; Sorted by
tests/test_gui.py                          line 115 flipped; new table, selector and scrollbar tests (section 6)
tests/test_transfer.py                     new: source workbook headers equal the schema headers (skipped without the workbook)
README.md                                  "What is in 0.4.0"; the Safety Plan screen bullet; version
CHANGELOG.md                               [0.4.0] entry (Changed / Fixed); Unreleased heading gains 0.6.0
docs/plan.md                               section 2 (note), section 8 (0.4.0 row), section 9 (change log)
src/asi_kletz/version.py, pyproject.toml   0.4.0
../asi_fusa_tools/ASI_FUSA_TOOLS.md                           version table (0.4.0), plans table (both 0.4.0 plans)
```

Not touched: `schema/` (`SCHEMA_VERSION` stays 1), `storage/`, `repositories/`, `services/`,
`commands/`, `io/`, `generate/`, `gui/matrix_screen.py`, `gui/screens.py` (the screen list, four then),
`gui/main_window.py`, `gui/dashboard.py`, `gui/transfer_screen.py`, `gui/widgets.py`,
`gui/theme.py`, `gui/palettes.py`, `prefs.py`, `kletz.example.toml`, `kletz.xlsx`,
`tests/test_schema.py`, `tests/conftest.py`, `uv.lock`. Dewey's `gui/entity_screen.py` keeps
its cap: it is Dewey's call, and after the sister plan no Dewey entity with flags has a screen.

## 6. Tests

**`tests/test_gui.py`**

- `test_safety_plan_form_has_groups` (line 112): line 115 becomes
  `assert "loc_dms" in screen.columns and "reviewer_pat" in screen.columns`; the rest stays.
- New `test_safety_plan_table_shows_every_column(window, seeded)`:
  - `schema = seeded.registry.get(PLAN)`;
    `screen.columns == ["id"] + [f.name for f in schema.fields]` and `len(screen.columns) == 64`;
    `list(screen.tree["columns"]) == screen.columns`.
  - `screen.columns[1:5] == ["order", "pdp_phase", "lifecycle_phase", "deliverable"]`.
  - `screen.tree.heading("loc_dms", "text") == "DMS"`;
    `screen.tree.heading("author_electronics_engineer_mechanical_and_electrical", "text") ==
    "Electronics Engineer (Mechanical and Electrical)"`;
    `screen.tree.heading("status", "text")` is the long status header.
  - `screen.tree.column("loc_dms", "width") == 36`, `("loc_dms", "anchor") == "center"`,
    `("loc_dms", "stretch") == 0`; `screen.tree.column("deliverable", "width") == 320` and
    `("deliverable", "stretch") == 1`; `screen.tree.column("order", "width") == 60`.
  - `screen.tree.set("1", "loc_dms") == "✓"`, `screen.tree.set("1", "loc_jama") == ""`,
    `screen.tree.set("2", "loc_jama") == "✓"`, `screen.tree.set("1",
    "reviewer_tech_lead_functional_safety") == "✓"`, `screen.tree.set("1",
    "author_tech_lead_functional_safety") == ""` (the duplicate header maps to two fields).
  - `screen.sort_by("loc_dms", desc=True)`; the first child is `"1"`; `window.status_text()`
    contains `Sorted by DMS`.
  - `from asi_kletz.gui import entity_screen; not hasattr(entity_screen, "MAX_FLAG_COLUMNS")`.
- New `test_columns_selector_narrows_the_flags(window, seeded)`:
  - `screen.columns_var.get() == "All"`; `str(screen.columns_box.cget("state")) == "readonly"`;
    `list(screen.columns_box.cget("values")) == ["All", "Location", "Reference", "Author",
    "Verification", "Reviewer"]`; `screen.tree["displaycolumns"] == ("#all",)`.
  - `screen.set_columns("Location")`: `list(screen.tree["displaycolumns"]) == ["id", "order",
    "pdp_phase", "lifecycle_phase", "deliverable", "work_product_location", "loc_dms",
    "loc_jama", "loc_sharepoint", "work_product_reference", "author", "gate_reviewer",
    "deadline", "status"]` (14); `len(screen.tree["columns"]) == 64` (nothing rebuilt);
    `screen.tree.set("1", "reviewer_pat") == ""` still readable while hidden.
  - `screen.set_columns("Reviewer")`: `displaycolumns` has 18 entries, ends with
    `reviewer_technical_training_team`, `deadline`, `status`, and contains no `loc_` column.
  - The selection survives a refresh and navigation: `screen.select(2)`;
    `seeded.execute("update", entity=PLAN, id=2, data={"deadline": "x"}, actor="agent")`;
    after the 2 s poll loop the tree has 3 rows, `displaycolumns` is still the reviewer set
    and `screen.selected_id == 2`; `window.show("dashboard"); window.show("safety_plan")`:
    `screen.columns_var.get() == "Reviewer"`.
  - `screen.set_columns("All")` restores `("#all",)`; `screen.columns_var.get() == "All"`.
  - After `window.pick_theme("pink-noir")` the rebuilt screen (`window.show("safety_plan")`)
    reads `All` again: session memory, not a latch; `read_prefs()` has no `columns` key.
- New `test_safety_plan_table_scrolls_both_ways(window)`:
  `isinstance(screen.xbar, ttk.Scrollbar) and str(screen.xbar.cget("orient")) == "horizontal"`;
  `screen.xbar.grid_info()["row"] == 1 and screen.xbar.grid_info()["column"] == 0`;
  `str(screen.ybar.cget("orient")) == "vertical"`; `screen.tree.cget("xscrollcommand")` and
  `screen.tree.cget("yscrollcommand")` are non-empty; `window.update_idletasks()` then
  `screen.tree.xview() != (0.0, 1.0)` (the tree is wider than its viewport) and
  `window.winfo_width() <= 1280` (the window did not grow); `screen.form.winfo_height() > 0`.
- Unchanged and must still pass: `test_exactly_four_screens`,
  `test_entity_screen_create_update_delete`, `test_entity_screen_validation_shows_error`,
  `test_search_sort_and_select` (the search still matches on row values, not columns),
  `test_matrix_toggle_and_group_switch` (the matrix is untouched),
  `test_event_bus_refreshes_open_screen`, `test_cyan_neon_is_default_and_paints_ttk` (the first
  row still carries the `even` stripe tag with 64 columns), every theme test.

**`tests/test_transfer.py`**

- New `test_source_workbook_columns_match_the_schema()`, skipped when `WORKBOOK` is absent like
  `test_seed_from_real_workbook`: the header row of sheet `Safety Plan` equals
  `[f.header for f in default_registry.get(PLAN).fields]`, so the table's column order is the
  source order by construction, not by coincidence.
- `test_excel_export_and_reimport`: unchanged (63 headers, duplicate header count 2, flags
  round-trip).

**`tests/test_schema.py`**: unchanged; `test_safety_plan_matrix_fields_are_unique_and_grouped`
(63 names, group sizes) is the schema-side anchor of section 3.1.

## 7. Rejected alternatives

- **Raise the cap instead of removing it** (say 64). Hides the rule in a number; the next
  flag added to the sheet would silently empty the table again. The owner's ask is "all columns".
- **Widen flag columns to their header** (the matrix's `len(header) * 7` rule). Fifty-three
  columns at up to 200 px is 10,000 px; the sheet would be unreadable without the selector, and
  the selector would become mandatory. Narrow columns keep a whole group in view.
- **Abbreviated headings** ("Elec. Eng.") to fit 36 px. The ask is the source column title;
  an abbreviation table is one more thing to keep in step with the sheet. Dragging a separator
  and the `Sorted by` status line cover the clipped titles.
- **Rebuild the tree on every `Columns` choice** (as the matrix does with `columns`). Loses
  sort state and selection, and the test would have to re-fill; `displaycolumns` is what Tk
  provides for exactly this.
- **Latch the `Columns` choice in `prefs.json`.** The theme latch exists because a theme is
  always needed; a column filter is a working-session view, and `All` as the default is the
  safe state after a restart. Open item if the owner misses it.
- **Merge the matrix into the table** (click a check mark to toggle). Two screens with two
  jobs stay clearer: the table edits a row through its form and the save path, the matrix flips
  one flag per click through `update`. Toggling on single click in a 64-column table would also
  fight row selection.
- **Freeze the first columns.** `ttk.Treeview` has no frozen columns; two side-by-side trees
  with synchronised scrolling would double the selection and sort logic. Column order and the
  selector are the substitute.
- **Fix the cap in Dewey too.** Dewey's entity screen is Dewey's; after the sister plan no
  Dewey entity with flags has a screen, so the cap there is moot.

## 8. Open items

- Whether the 36 px headings need a hover hint (a `<Motion>` binding writing the header of the
  column under the pointer to the status bar). Cheap; decide after seeing the table. Done in
  0.7.0; the 36 px width itself went in 0.7.1, when every column was fitted to its text.
- Whether `Columns` should offer "No flags" (today's 11-column view) as a seventh entry for
  people who only edit the text fields. Easy to add; wait for the ask.
- Whether the matrix screen should also gain the ten non-flag columns, or a `Columns` box of
  its own. Not now: the matrix is the one-group flag editor and already has a group selector.
- Whether the selector choice should latch in `prefs.json` alongside the theme. Not now.
- The `JIRA Live Data` window (0.5.0) makes five screens; this plan keeps four and changes no
  screen list, so the two plans do not collide.

*Written 2026-10-27.*
