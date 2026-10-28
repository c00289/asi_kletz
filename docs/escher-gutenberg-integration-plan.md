# ASI Kletz — Plan: integrate asi_escher (diagrams) and asi_gutenberg (documents)

**Status:** Implemented 2026-10-27 (asi_kletz 0.2.0); deviations recorded in section 9. The "exactly four
screens" rule this plan keeps (sections 1, 3.8, 6) was retired in 0.5.0 by [jira-live-data-plan.md](jira-live-data-plan.md):
screens are registered in `gui/screens.py`, not counted, and `test_exactly_four_screens` is now
`test_registered_screens_in_order`.
**Written:** 2026-10-27
**Owner:** FuSa engineer
**Target version:** asi_kletz 0.2.0
**Family context:** [ASI_FUSA_TOOLS.md](../../asi_fusa_tools/ASI_FUSA_TOOLS.md) (the ontology this plan implements)
**Sister plan:** [asi_dewey/docs/escher-gutenberg-integration-plan.md](../../asi_dewey/docs/escher-gutenberg-integration-plan.md).
Same shape, copied on purpose, never imported: Kletz and Dewey share no code at runtime.
**Prerequisite:** [asi_gutenberg/docs/escher-integration-plan.md](../../asi_gutenberg/docs/escher-integration-plan.md)
for phase 4 only.

---

## 1. Goal

ASI Kletz holds one artefact, the platform **Safety Plan**. After this plan it can **draw that plan
with asi_escher and print it with asi_gutenberg**, from its own database, through the one command
path:

```powershell
asi-kletz diagram                                   # catalog
asi-kletz diagram phase_flow --param phase=3 --out out
asi-kletz document safety_plan --out out            # out/safety_plan.{md,pdf,docx} with figures
```

and the same two verbs from the window, from a `.jsonl` script, and from an agent.

The Safety Plan document is the point of this tool. Today the workbook is the only human-facing
output; after this plan the controlled document that goes to review comes out of the same database,
with its lifecycle diagram and one flow diagram per phase, as a Markdown / PDF / Word triplet.

Principles carried over from [plan.md](plan.md), unchanged:

- **The database is the truth; files are views.** Regenerated on demand, never read back.
- **One command path.** The window calls `Brain.execute` with actor `gui` and nothing else.
- **Fixed screens.** The window has exactly four screens, and the test suite says so. This plan
  keeps it that way (section 3.8); the rule itself was retired in 0.5.0, see the status line.
- **Nothing shared with Dewey.** Separate package, verbs, variables, config, database, output.

Out of scope: any entity beyond `safety_plan_row`, editing diagrams in the window, importing a
document back, and screens beyond the four.

## 2. What exists today (verified 2026-10-27)

Kletz 0.1.0 is Dewey 0.1.0 with one entity and four screens; the command layer, exporters,
`Brain`, config loading, event bus, audit log, and dispatcher are identical apart from names. The
facts that matter:

| In Kletz | Relevant fact |
|---|---|
| `commands/factory.py` | `@register_command` adds a verb; CLI and `schema` output follow. |
| `commands/base.py` | `Argument(type="kv")` and `parse_kv` give `--param k=v`. |
| `commands/dispatcher.py` | Exceptions in `run` become `Result.failure`. |
| `brain.py` | `CONFIG_KEYS = ("db", "workbook")`; `ASI_KLETZ_DB`, `ASI_KLETZ_WORKBOOK`, `kletz.toml`. |
| `schema/definitions.py` | `safety_plan_row` with 63 columns; flag groups `location`, `reference`, `author`, `verification`, `reviewer`; lookups `pdp_phase`, `lifecycle_phase`, `plan_status`. |
| `gui/screens.py` | `build_default_screens` registers `dashboard`, `safety_plan`, `safety_plan_matrix`, `transfer`; `tests/test_gui.py::test_exactly_four_screens` asserts the keys and titles. |
| `gui/transfer_screen.py` | Two `LabelFrame`s (workbook, JSON) and a log; the natural home for a third frame. |
| `gui/main_window.py` | `MainWindow.run(verb, **args)`; `interactive` guards dialogs. |

Generator facts are the same as in the Dewey plan, section 2: `asi_escher.build` returns paths and
`LayoutIssue` objects and emits a `LayoutWarning`; `asi_gutenberg.build` writes the triplet and
resolves figure paths against `out_dir`; the two palettes already match.

## 3. Design

### 3.1 Dependencies

```powershell
cd asi_kletz
uv add --editable ../asi_escher
uv add --editable ../asi_gutenberg
```

Both sources declared in Kletz's own `pyproject.toml` (uv does not inherit a path dependency's
`tool.uv.sources`). Heavy imports (matplotlib, reportlab, python-docx) stay lazy inside builders and
commands so `asi-kletz list` and window start-up are unchanged.

### 3.2 Output folder

| Source | Key |
|---|---|
| explicit argument | `--out` |
| environment | `ASI_KLETZ_OUT` |
| `kletz.toml` | `out = "../some folder/safety-plan-out"` (relative to the file) |
| default | `out/` next to `kletz.db` |

`Brain.out_dir`, `status()["out_dir"]`, `CONFIG_KEYS = ("db", "workbook", "out")`,
`kletz.example.toml` updated, test fixture clears `ASI_KLETZ_OUT`.

### 3.3 New package: `asi_kletz/generate/`

Same layout as Dewey's, written independently:

```
src/asi_kletz/generate/
  __init__.py       DiagramFactory, DocumentFactory, register_diagram, register_document, Spec, Param
  base.py           Spec, Param, check_params
  diagrams.py       built-in diagram builders (3.4)
  documents.py      built-in document builders (3.5)
  figures.py        build_diagram() wrapper: LayoutWarning captured, LayoutIssue -> dict, paths back
  plan_queries.py   the read-side helpers both diagrams and documents need (3.6)
```

Builders are `(brain, params) -> asi_escher.Diagram` and `(brain, params) -> asi_gutenberg.Document`,
registered with a `Spec(key, title, description, params)`. They read only through
`brain.service("safety_plan_row").list(...)` and `brain.lookups`.

### 3.4 Diagram catalog (first cut)

| Key | Escher kind | Built from | Params |
|---|---|---|---|
| `lifecycle_overview` | `flowchart`, LR | One `process` node per `lifecycle_phase` lookup value in order, chained; label `"<phase>\n<n> deliverables, <done> done"`; a phase with a Blocked row takes the decision tint; a phase with every row Done takes the state tint. | none |
| `phase_flow` | `activity` with lanes `Author`, `Verification`, `Reviewer` | Rows of one phase by `order`: Author-lane `action` (deliverable, author, status stereotype); Verification-lane `action` when any `verify_*` flag is set (the set flag names); Reviewer-lane `action` from `gate_reviewer` or the set `reviewer_*` flags; `start` → … → `end`; a `note` on rows with `work_product_location` naming the location. | `phase` (required): lookup value or its leading number |
| `status_board` | `state` | One `state` per `plan_status` value labelled with its count; the conventional transitions Pending → Ongoing → Done, Ongoing → Blocked → Ongoing, Pending → Alternative, Pending → Out-of-Scope; `start` → Pending. The transitions are a convention, not data, and the spec description says so. | none |
| `pdp_map` | `bdd`, frame `bdd [Package] Safety Plan` | One block per `pdp_phase` (1 to 6) with a compartment listing the lifecycle phases that have rows in it, and a composition edge from a `Safety Plan` root block. | none |

### 3.5 Document catalog (first cut)

| Key | Gutenberg kind | Sections | Figures |
|---|---|---|---|
| `safety_plan` | `plan`, title "Platform Safety Plan" | Purpose; Scope (the ten lifecycle phases and the six PDP phases as `fields`); Lifecycle overview (table phase / count / Pending / Ongoing / Blocked / Alternative / Out-of-Scope / Done); one `h1` per lifecycle phase with **two** portrait tables per phase, "Deliverables" (Deliverable, PDP, Location, Reference, Deadline, Status) and "Ownership" (Deliverable, Author, Verification, Reviewer), so nothing needs a landscape page; appendix A Roles (the 17 author roles and 7 reviewer roles, from the flag definitions); appendix B QMS and reference legend (the 23 reference flags); appendix C Status legend. | `lifecycle_overview`, then `phase_flow` under each phase that has rows |
| `status_report` | `report`, title "Safety Plan Status" | Totals by status (`fields`); Blocked deliverables (table with deadline and author); Due (rows whose `deadline` parses as a date within 30 days, best effort, free text otherwise); Recent changes (last 20 audit entries). | `status_board`, `lifecycle_overview` |
| `phase_checklist` | `checklist`, title "Safety Plan Checklist" | One `h1` per phase, a task list of its deliverables with `checked = (status == "Done")`; a closing `fields` table of totals. | `pdp_map` |

Metadata: `date` = today, `author` = the actor, `status` = Draft. The **Safety Plan document id
lives in `kletz.toml`** (decided 2026-10-27), as a new `doc_id` key, with an optional `project`
key beside it:

```toml
db = "kletz.db"
workbook = "../some folder/safety-plan.xlsx"
out = "../some folder/safety-plan-out"
doc_id = "ASI-FS-PLAN-001"
project = "WA485 Autonomous Wheel Loader"

[[revision]]
rev = "0.1"
date = "2026-10-27"
author = "FuSa Engineer"
description = "Initial draft"
```

`Brain.doc_id`, `Brain.project`, and `Brain.revisions` hold the values (blank or empty when
absent); `status` reports them; `kletz.example.toml` documents them.

The **revision history is explicit** (decided 2026-10-27): the `[[revision]]` entries in
`kletz.toml`, in file order, become the document's revision table, and the last entry's `rev` is
the document revision on the cover. It is not derived from the audit log. The audit log records
every edit by anyone, including agents; a revision is a deliberate issue of the controlled document
by a person, and document control wants the two kept apart. With no entries the builder writes a
single line (`0.1`, today, the actor, "Generated draft") and the warning `kletz.toml has no
revisions`. Because `kletz.toml` is git-ignored, the engineer who issues the plan keeps the file;
`kletz.example.toml` carries the first entry as a template. `safety_plan` puts `doc_id` on the cover and in the document
control table; `status_report` and `phase_checklist` reference it in their Purpose paragraph
("status of ASI-FS-PLAN-001") but carry no id of their own. When `doc_id` is blank the
`safety_plan` build still succeeds and adds the warning `kletz.toml has no doc_id`, so a draft can be
previewed before the id is assigned. The output stem is the catalog key, so a rebuild overwrites
the previous triplet.

**The reviewed artefact is the PDF** (decided 2026-10-27). The Word file is a convenience for
reviewers who want to mark up text; the Markdown is the source. The window's **Open** button,
the `document` result's `primary` field, and the README all point at the `.pdf`.

Until the Gutenberg plan lands, document builders pre-render figures into `<out>/figures/` through
`figures.py` and call `doc.figure("figures/<key>.png", caption)`. After it lands they call
`doc.diagram(builder(brain, params), caption)` and Gutenberg renders.

### 3.6 Shared read helpers

The dashboard already computes counts by status and per phase. Those queries move to
`generate/plan_queries.py` (`rows_by_phase`, `counts_by_status`, `blocked`, `due_within`,
`set_flags(row, group)`), and the dashboard screen calls them too, so a number on the screen and
the same number in the report cannot drift.

### 3.7 Commands

`commands/generate.py`:

```
diagram  [name] [--out <dir>] [--formats png,svg,dot,mmd] [--param k=v ...] [--dpi 160]
document [name] [--out <dir>] [--param k=v ...]
```

Behaviour identical to the Dewey plan, section 3.6: no name lists the catalog; issues become
`warnings`; unknown names and bad params are `Result.failure` with the known values listed; a locked
PDF falls back to a timestamped stem; both verbs write an audit entry (`generate`) and publish
`generated` on the event bus; `status` lists them. One addition: the `document` result carries
`"primary": "<path to the .pdf>"` beside `paths`, because the PDF is the reviewed artefact; the
`diagram` result's `primary` is the PNG.

### 3.8 Window: four screens, still

The screen list is a property of the tool and `test_exactly_four_screens` guards it. Generation
therefore lives **inside the Export / Import screen** as a third `LabelFrame`,
**"Diagrams and documents (generated views of the plan)"**, under the JSON frame and above the log:

- a `Combobox` of diagram keys and a `Combobox` of document keys (titles shown, keys sent);
- a `phase` `Combobox` fed from the `lifecycle_phase` lookup, enabled only when the selected
  diagram declares that param;
- an output folder entry with Browse, defaulting to `brain.out_dir`;
- **Build diagram**, **Build document**, **Open** (opens the result's `primary` file: the PDF for
  a document, the PNG for a diagram), **Open folder**;
- results go to the existing log through the existing `_report`.

The screen title stays "Export / Import". The File menu gets **Build Safety Plan document**, which
runs `document safety_plan` directly and shows the transfer screen so the log is visible.

If a fifth screen is ever wanted, it is a deliberate change to `build_default_screens`, the test,
the README sentence "four screens and no others", and `plan.md` section 3. Not this plan.

### 3.9 Scripts and agents

```jsonl
{"verb": "document", "args": {"name": "safety_plan"}, "actor": "claude"}
{"verb": "diagram", "args": {"name": "phase_flow", "param": {"phase": "8"}}}
{"verb": "export", "args": {"format": "excel"}}
```

The three lines above are the whole "publish the plan" routine: document, diagram, workbook.

## 4. Delivery phases

| Phase | Content | Done when |
|---|---|---|
| 1. Wiring | Dependencies locked; `out` config/env/`Brain.out_dir`; `generate/` with factories, `figures.py`, `plan_queries.py`; `lifecycle_overview`; `diagram` verb with catalog listing. | `asi-kletz diagram lifecycle_overview` writes four files from the seeded test database. |
| 2. Diagrams | `phase_flow`, `status_board`, `pdp_map`; dashboard switched to `plan_queries`. | All four render without issues on the seeded database; dashboard numbers unchanged. |
| 3. Documents | `document` verb; `safety_plan`, `status_report`, `phase_checklist` with pre-rendered figures. | Triplets written; `safety_plan` has one section per phase with rows and a figure under each. |
| 4. Gutenberg diagram blocks | Switch to `doc.diagram(...)` once asi_gutenberg 0.2.0 exists. | No placeholder in any PDF; `figures/` produced by Gutenberg. |
| 5. Window | Third frame on Export / Import; File menu entry; GUI tests. | `test_exactly_four_screens` still passes; builds run with the window withdrawn. |
| 6. Release | README "Diagrams and documents", CHANGELOG `0.2.0`, `version.py`, `kletz.example.toml`, `plan.md` section 8 row, tag `v0.2.0`. | `uv run pytest` and `uv run ruff check src tests` clean. |

## 5. Files touched

```
pyproject.toml, uv.lock               dependencies, sources, version
kletz.example.toml                    out, doc_id, project
src/asi_kletz/version.py              0.2.0
src/asi_kletz/brain.py                ENV_OUT, CONFIG_KEYS, out_dir, doc_id, project, revisions, status()
src/asi_kletz/generate/               new package
src/asi_kletz/commands/generate.py    diagram, document
src/asi_kletz/commands/__init__.py    import generate
src/asi_kletz/gui/transfer_screen.py  third frame
src/asi_kletz/gui/dashboard.py        use plan_queries
src/asi_kletz/gui/main_window.py      File > Build Safety Plan document
tests/test_generate.py                new
tests/test_gui.py                     transfer-screen build cases; four-screen test untouched
tests/conftest.py                     clear ASI_KLETZ_OUT
README.md, CHANGELOG.md, docs/plan.md
```

No change to `schema/`, `storage/`, `repositories/`, `services/`; schema version stays 1; the
database still has exactly one table (the existing test keeps checking).

## 6. Tests

Real generators, no mocks.

- Catalogs list every key with title, description, params; `status()["commands"]` has both verbs.
- `lifecycle_overview` on an empty database: ten nodes, nine edges, no issues, four files.
- `phase_flow`: missing `phase` fails naming the param; `"1"` and `"1. Concept Development"` give
  identical `dot` output; a phase with no rows yields `start` → `end` and a warning.
- `status_board`: six states, counts match `counts_by_status`.
- `safety_plan` on the seeded database: three files, one `h1` per phase that has rows, the Markdown
  references PNGs that exist under `out/figures`, `issues == []`, `data["primary"]` ends in `.pdf`.
- `doc_id`: with a `kletz.toml` naming `doc_id = "ASI-FS-PLAN-001"` the Markdown front matter
  contains that id; without one the build succeeds with the warning `kletz.toml has no doc_id`.
- Revisions: two `[[revision]]` entries appear in the revision table in file order and the cover
  shows the last `rev`; with none, one generated line and the warning `kletz.toml has no revisions`.
- Per-phase tables: every phase section has a "Deliverables" table and an "Ownership" table with
  the same deliverables in the same order; no table has more than six columns.
- `phase_checklist`: a Done row renders `- [x]`, others `- [ ]`.
- Locked PDF fallback, audit entry `generate`, event `generated`, out-dir precedence, CLI exit
  codes: as in the Dewey plan, section 6.
- Importing `asi_kletz` does not import `matplotlib` or `reportlab`.
- GUI (skipped without a display): `factory.items()` still has exactly four entries; on the transfer
  screen, selecting `lifecycle_overview` and pressing Build diagram logs `[ok] diagram`; the phase
  combobox is disabled for diagrams without that param and enabled for `phase_flow`.

## 7. Risks and decisions

| Risk | Decision |
|---|---|
| Transitive path source not inherited by uv | Declare both sources in Kletz. |
| Copying Dewey's `generate/` package instead of writing it | It is copied, like the rest of Kletz was, and then diverges; no import, no shared file, no symlink. A test greps the source tree for `asi_dewey` and fails on a hit. |
| `deadline` is free text (`"Expected Duration/Deadline"`) | `due_within` parses ISO dates and `dd/mm/yyyy`, best effort; unparsable rows go to a "no date" table rather than being dropped. |
| 23 reference flags and 17 author roles crowd a node | Labels carry the set flags only, truncated to three plus `+n`; the full list is in the document's appendices. |
| A fifth screen would be simpler than a third frame | Rejected: the four-screen property is documented and tested; revisit only with a deliberate change (section 3.8). |
| Document metadata (project, doc id) has no home in a one-entity tool | `doc_id` and `project` keys in `kletz.toml` (decided 2026-10-27); the id belongs to Kletz because Kletz owns the plan. Blank `doc_id` warns, never fails. |
| Which of the three outputs is "the" Safety Plan | The PDF (decided 2026-10-27). Results carry `primary`, the window opens it, the README says so. |
| Revision history: audit log or explicit list | Explicit `[[revision]]` entries in `kletz.toml` (decided 2026-10-27). Audit is evidence of edits; a revision is an issue of the document. |
| Nine-column per-phase table does not fit portrait | Split into "Deliverables" and "Ownership" tables (decided 2026-10-27). No landscape support is asked of Gutenberg. |

## 8. Open questions

None. Every question raised in Draft 0.1 was decided on 2026-10-27 and recorded in section 3.5
and the table in section 7. This plan is ready to implement.

## 9. Change log

- 2026-10-27 Implemented as asi_kletz 0.2.0, all six phases (phase 4 against asi_gutenberg
  0.2.0). Deviations from the text above, each for a reason found in the code:
  - Builders are `(brain, params, ctx)`; the `ctx` (`BuildContext`) carries the actor (the
    document author), the output folder and the warnings a builder raises (`kletz.toml has no
    doc_id`, an empty phase). `(brain, params)` had no way to say any of that.
  - `phase_flow` puts the status in the action label (`[Done]`) because asi_escher draws
    stereotypes only on block-like nodes; the stereotype is still set for DOT and `to_dict`.
  - `set_flags(row, group, schema=None)` takes the schema (defaults to the built-in entity).
  - The output stem of a parametrised diagram is `<key>_<param>` (`phase_flow_3`), with the
    phase normalised to its number, so one phase cannot overwrite another and the verb and the
    document share a stem; a document's stem is its key, as written.
  - The `document` result carries Gutenberg's `diagrams` list (one entry per rendered figure)
    rather than a Kletz-side `figures` list, since Gutenberg renders them (phase 4).
  - `safety_plan` has a section for every lifecycle phase (an empty one says so); the
    Deliverables / Ownership tables and the `phase_flow` figure appear under phases with rows.
  - `status_report`: the "no date" table lists open deliverables only; Done and Out-of-Scope
    rows have no due date to report.
  - The audit entry `generate` uses the entity column for the kind (`diagram` / `document`).
  - The window fills its catalog comboboxes through `run("diagram")` / `run("document")`, the
    command path, rather than importing the factories.
  - `v0.2.0` is not tagged yet; the release is committed, the tag is the owner's call.

- 2026-10-27 Draft 0.3: last two questions decided. Revision history is an explicit
  `[[revision]]` list in `kletz.toml`, never the audit log; the per-phase table is split into
  "Deliverables" and "Ownership" instead of asking for landscape pages. No open questions remain.
- 2026-10-27 Draft 0.2: two decisions by the owner. The Safety Plan document id lives in
  `kletz.toml` (`doc_id`, with optional `project`); the reviewed artefact is the PDF (`primary` in
  results, **Open** shows it). Open questions reduced accordingly.
- 2026-10-27 Draft 0.1: goal, verified starting point, dependencies, output folder, `generate/`
  package, diagram and document catalogs, shared read helpers, verbs, four-screen window change,
  phases, files, tests, risks, open questions.
