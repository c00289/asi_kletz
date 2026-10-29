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

## [0.24.0] - 2026-10-29

STPA moves to Kletz. The owner, 2026-10-29: "control structures were supposed to go into Kletz and not Dewey";
asked where STPA should live: "move everything to Kletz". Everything the sister tool built for it the same day
(asi_dewey 0.9.0, control structures phase 2 of `docs/control-structure-plan.md`; 0.10.0, the screen, phase 3,
and the STPA step objects, phase D of `asi_hopper/docs/confluence-integration-plan.md`; 0.10.1, the reader on
the real page) is ported here whole, with the verbs' names and `Result` shapes unchanged so an agent's scripts
keep working with the same dialect; the sister tool loses it in a later release. Schema version 10 to 11.

### Added
- **Seven control-structure entities** (`schema/definitions.py`, from asi_dewey 0.9.0): `control_structure`
  (name, slug, system, description, source, status Draft / Reviewed / Baselined, revision) and its parts
  `cs_controller` (key, name, kind, responsibility, process_model_title, note), `cs_algorithm` (controller, code,
  name), `cs_process_model_entry` (controller, heading, control_actions, variables, updated_by, references),
  `cs_edge` (key, kind, source, target), `cs_signal` (edge, signal_id, kind, name, placeholder) and `cs_note`
  (text, attached_to); every part names its structure by slug and its parent by key; one sheet each (`CS
  structures` ... `CS notes`); lookups `cs_status`, `cs_controller_kind` (asi_escher's `CONTROL_NODE_KINDS`),
  `cs_edge_kind`.
- **Six STPA entities** (from asi_dewey 0.10.0): `stpa_analysis` (name, slug, system, status, `control_structure`,
  `source_kind` confluence / hand, `source_page_id`, `source_url`, `source_version`, `source_body_sha256`,
  `source_taken_at`, `source_bundle`, note) and its parts `stpa_loss`, `stpa_hazard` (parent, losses, retired),
  `stpa_uca` (controller, control_action, category, hazards, retired, duplicate_of, cs_controller, cs_signal),
  `stpa_scenario` (row, uca, counterpart, types, causal_factors, beliefs, constraints, retired) and
  `stpa_constraint`, every part with its `cite` and `note`; one sheet each (`STPA analyses` ... `STPA
  constraints`); lookups `stpa_status`, `stpa_source_kind`, `stpa_uca_category`. Every one of the thirteen ends
  with the hidden `uid`; the dump and the workbook carry them round trip.
- **`schema/lists.py`**: `list_of` (a list as it is, a JSON array parsed, any other text one item per line, blank
  the empty list) and `lines_of`; the lists of a row are JSON arrays in `FieldType.JSON` columns, never NULL on a
  create, parsed by the entity's rules on every write and on a file load, read back as lists. Kletz's JSON column
  of 0.19.0 (the people of a role) is untouched.
- **The rules** (`services/control_structure_service.py`, `services/stpa_service.py`, from asi_dewey 0.9.0 and
  0.10.0): one rule object per entity (`EntityRules`: `guard`, `on_load`, `before_delete`, `after_change`),
  attached to the plain `EntityService` by `Brain.service`, so they hold on every verb that writes a row. A part
  names a structure (an analysis) that exists and a parent that exists; keys and codes unique and immutable
  while rows point at them; a signal's kind matches its edge's; a duplicate signal id a refusal typed and a
  warning loaded, a signal shared by two edges leaving one controller information; direction a warning; a
  dotted hazard's parent; dangling codes warnings, never refusals; one analysis per (page id, version); the
  `source_*` moved only by `refresh`; a row with dependants deleted with `cascade` or refused. Events
  `cs.changed`, `stpa.changed`. `ControlStructureService` (`brain.control_structures`: `resolve`, `parts`,
  `dataset`, `create_from_dataset`, `duplicate`, `delete`, `validate` with `info`) and `StpaService`
  (`brain.stpa`: the same, plus `compare`, `apply_refresh`, `link_structure`).
- **`EntityService`** gained the hooks `before_delete(stored, cascade, actor)` and `after_change(action, row,
  actor)` and `delete(ref, actor, cascade=)`; the generic `delete` verb takes `--cascade`;
  `SqlRepository.delete_where`; the dispatcher checks a repeatable flag's choices item by item (`--format svg
  --format drawio`).
- **The factories** (`stpa/factory.py`, `stpa/stpa_factory.py`, `brain.factory` and `brain.stpa_factory`):
  `ControlStructureFactory` with the builders `blank`, `template:wheel_loader_master` (the owner's structure from
  the private shelf, listed as unavailable when absent), `from_drawio`, `from_datasets`, `clone`; `to_diagram`
  (the one place rows become an `asi_escher` drawing), `build_files` (escher with provenance and the OCR gate;
  no audit, for the preview) and `export` (audited `cs.export`, published `cs.exported`, the OCR verdict in the
  Result). `StpaFactory` with `blank`, `from_bundle` (the primary builder: a Hopper Confluence bundle, offline,
  hashed), `from_confluence` (a snapshot through **Kletz's own Confluence door**, `ConfluenceService.snapshot_page`,
  into `evidence_dir`, then `from_bundle`) and `clone`; `reread` for the refresh; `export` (the six-sheet
  workbook, the `stpa_report` document, the `stpa_trace` diagram; audited `stpa.export`, published
  `stpa.exported`). `stpa/drawio_reader.py` (escher's dialect and the hand-drawn one, standard library only)
  and `stpa/confluence_reader.py` (pure over asi_hopper's page anatomy, with the 0.10.1 fixes: merged controller
  cells, lone duplicate notes, unbolded codes, constraint lists and broken escapes, a code read twice) as they
  were.
- **The `cs` verb** (`commands/cs.py`): `list | get <id> | builders | new <builder> [--name --slug --system
  --from] | duplicate <id> --name | delete <id> [--cascade] | validate <id> | import <drawio-or-folder> | export
  <id> [--out] [--format ...] [--all] [--no-ocr]`. **The `stpa` verb** (`commands/stpa.py`): `list | get <id> |
  builders | new <builder> [--name --slug --system --from --page --out] | refresh <id> [--from] [--apply] |
  validate <id> | link <id> --structure <slug> [--apply] | export <id> [--out] [--format ...] [--all] | delete
  <id> [--cascade]`. Every answer a JSON `Result`, the shapes of the sister tool's.
- **Views**: the `stpa_report` document and the `stpa_trace` diagram in the catalogs, `--param analysis=<slug>`,
  built with Kletz's `(brain, params, ctx)` signature and `add_diagram`.
- **The screens** (`gui/control_structure_screen.py`, *Control structures*, `/screen {"show":
  "control_structures"}`; `gui/stpa_screen.py`, *STPA analyses*, `/screen {"show": "stpa"}`), registered before
  Export / Import: the three panes, the stacked tree with unique iids, the forms (the keys offered in a list,
  the lists one item per line through the new `ListWidget`), New from…, Duplicate, Delete asking then cascading,
  Import draw.io…, Validate, the Export… dialog (the folder remembered as `cs_export_dir` in the preferences,
  drawio and png by default, Select all / Select none, OCR on), the preview re-rendered off the Tk thread, Open
  in VS Code; the analyses with their parts as tabs, Refresh from Confluence on a worker thread. The
  **Dashboard** gains a tile row, *STPA*: the structures and the analyses, a click opening the screen.
- **`gui/background.py`**: `BackgroundFetch` moved out of the JIRA Live Data screen (which re-exports it) and
  given `call(window, name, fn, ...)` for work that is not a verb (the preview); `MainWindow.report(result,
  verb)` for a Result obtained off the Tk thread. The window ignores `cs.exported` as it ignores `jira.live`:
  no row changed, and the topic may arrive from the worker.
- **Configuration**: `control_structures_dir` in `kletz.toml` (a path resolved against the file; default
  `../asi_standards/control-structures`; `$ASI_KLETZ_CONTROL_STRUCTURES` overrides it; `Brain.control_structures_dir`;
  `status` reports it). `kletz.example.toml` names it.
- `docs/control-structure-plan.md`, the plan as the sister tool wrote it, with a status line saying it moved here
  and every phase shipped in 0.24.0; `tests/fixtures/kletz-0.23.0.db` (a schema-10 database for the migration
  test), `tests/fixtures/conveyor-gate-stpa.md` and `conveyor-gate-stpa-quirks.md` (the synthetic STPA pages).

### Changed
- **Schema version 11.** A 0.23.0 database opens with the thirteen tables created, nothing altered, no row touched;
  the fixture test counts them. `uv.lock` takes asi_kletz 0.24.0; asi_escher stays 0.2.1, asi_gutenberg 0.9.0 and
  asi_hopper 0.1.9, what the checkouts declare.
- Version 0.24.0 in `pyproject.toml`, `version.py` and the README; the README gains "What is in 0.24.0", "Control
  structures" and "STPA analyses" (the sister tool's wording, the names Kletz's), the configuration key and the
  CLI lines.

### Tests
- 424 to 480. `test_control_structures.py` (the seven entities and their sheets, the lists, the factory on the
  synthetic eight-box structure, every rule and refusal, the shared feedback as information, cascade delete,
  duplicate, validate, every `cs` verb and the command line, the export through the OCR gate with escher's
  `ocr_check` monkeypatched to competent, an unreadable label, the one real-engine test skipped without it, the
  draw.io reader on the hand-drawn dialect and the escher round trip, the datasets folder and the template
  builder through the environment and `kletz.toml`, dump / load and the workbook round trip, the schema-10
  migration, the local-only private smoke test on asi_standards' datasets, counts only, skipped where absent);
  `test_control_structure_screen.py` (the registration, the tile and `/screen`, `stack()`, the tree and the
  form, Save and New child through the verbs as `gui` with the preview re-rendered, Delete asking then cascading,
  New from…, Duplicate, Import draw.io…, Validate, the Export… dialog, a failed export, Open in VS Code);
  `test_stpa.py` (the reader on both synthetic pages, `from_bundle`, `blank`, `clone`, `from_confluence` on
  asi_hopper's replay fixtures through Kletz's door, every rule, cascade delete, `validate`, every `stpa` verb and
  the command line, `refresh` reported and applied, `link --structure`, the report and the trace with and
  without swimlanes, the export, dump / load and the workbook, the migration, the screen). The existing tests
  now count nineteen entities, nineteen sheets, eleven screens, `stpa_trace` and `stpa_report` in the catalogs.

## [0.23.0] - 2026-10-29

Phase B of the Confluence integration plan (`asi_hopper/docs/confluence-integration-plan.md`, "Kletz: Confluence
read only, through Hopper"; the plan numbered it 0.22.0, Phase A took that number). The owner, 2026-10-29: "when
we add confluence read only into kletz we should be able to associate objects with jama urls; obviously the next
candidate is replacing the google.com placeholder with a real url once known; but more importantly there may be
a way to tie in individual stpa objects to confluence." And right after: "i said jama but meant confluence." No
schema change (schema version stays 10): the plan row's `urls` list is the association, as 0.20.0 designed it.
Nothing writes to Confluence; no page text enters Kletz.

### Added
- **`services/confluence_service.py`**, `ConfluenceService`, the shape of `JiraService` (a non-interactive
  Hopper per call, asi_hopper imported inside the functions, `AuthRequired` surfacing as the login hint as it
  is, every other Hopper error prefixed `Confluence read failed:`): `search` (one CQL, `title ~ "<text>" AND type
  = page ORDER BY lastmodified DESC`, the text escaped, restricted to one space, never Rovo), `page` (the record,
  the body only when asked; a page URL accepted, the id read off `pageId=` or `/pages/<id>` with asi_hopper's
  `page_id_of`), `link` (the page fetched, its canonical URL appended to the row's `urls`, first with `first`,
  through `EntityService.update`: the guard, the audit's `update`, `entity.updated`; a page already on the row
  under any URL form refused), `evidence` (`hopper.evidence.snapshot_pages(PageSource(kind="pages", ids=...))`
  into the evidence folder; the manifest plus `rows`; one audit entry `confluence_evidence` with the folder, the
  page ids, the rows, the time and the versions; the event `plan.confluence_evidence`), `check` (every linked
  page's title, version and `updated`; `last_evidence` from the latest audit entry naming the page, the manifest
  read when its folder still exists; `moved` against it; a page that cannot be read keeps its line with `error`),
  `last_evidence`, `has_session` (the stored token read locally through `Hopper.session_store()`, never a
  connection, never an exception), `page_id`, `cql_literal`, `search_row`, `page_summary`.
- **`confluence` verb** (`commands/confluence.py`): `search <text> [--space KEY] [--limit n]`, `page <id-or-url>
  [--body]`, `link <row> <id-or-url> [--first]`, `evidence [--rows <id>...] [--comments] [--out DIR] [--name
  NAME]`, `check [--rows <id>...]`; every answer a JSON `Result`; the reads publish nothing.
- **`evidence_dir`** in `kletz.toml` (`Brain.evidence_dir`; a path resolved against the file, default `evidence/`
  beside the database) and **`[confluence] space`** (`Brain.confluence_space`, `ConfluenceService.space`; default
  `STPA`; a value that is not text is ignored with a warning `status` reports); `status` reports `evidence_dir`
  and `confluence_space`; `kletz.example.toml` shows both; `.gitignore` covers `evidence/`.
- **Find page** in the window (`gui/page_lookup.py:PageLookup`; `gui/widgets.py:UrlsWidget` with `find_page`,
  `insert_url`, `FIND_PAGE`; `gui/entity_screen.py:lookup_page`): a button beside Open on the Work product URLs
  box, greyed when `has_session()` says no; a title entry, a space drop-down (the configured default), Search,
  the hits (title, space, last modified), Insert appends the page URL as a line of the editor; the search is a
  `BackgroundFetch` of `confluence search` polled with `after`, never on the Tk thread; a refusal is one line in
  the status bar and the window; one window at a time, closed with the screen; no page body shown.
- **The dashboard's Work product links tiles** (`gui/dashboard.py`, `LINK_TILES`; `plan_queries.counts_by_link`):
  deliverables with a Confluence page among their URLs, with the placeholder still among them, with no URL at
  all; a click opens the plan.
- `WorkProductService.rows`, the public name of the row selection `audit` uses, so the evidence and the check read
  the same rows (`--rows`, ids or uids, an unknown one refused).
- Tests (`tests/test_confluence.py`, `tests/test_gui_confluence.py`): the verb on a temporary copy of Hopper's
  replay fixtures with index entries added for the CQL this verb sends (aliased to the recorded STPA space
  search; nothing recorded into asi_hopper): `search` (the rows and their fields, the limit, the escaped literal
  and the space a stub receives, pages only, the refusals), `page` by id and by both URL forms with and without
  the body, `link` through the guard (appended, `--first`, by uid, the audit's `update`, the event, the refusal
  of a page already on the row under either URL form, an unknown row, an unknown page, a URL naming no page,
  missing arguments), `evidence` (the bundle Hopper's own `EvidenceService.verify` accepts, the rows, the one
  audit entry and its payload, the event, no page text in the database, the default folder and name, the
  refusals and the warning), `check` without and with earlier evidence (the newest bundle wins, a moved version,
  a deleted folder, an unreadable page, a URL naming no page), `AuthRequired` as one line on every action and the
  install hint, the session probe, the configuration (the space, the folder, a bad value), the tile counts, the
  verb's signature and the three forms (Python, the wire format, the CLI end to end); the Find page window with
  the fetch monkeypatched (the search off the Tk thread, Insert appending, Save storing, another space typed, the
  same window on a second press, greyed without a session, a refusal as one line), the dashboard tiles and the
  click. `tests/conftest.py` stubs `has_session` to *no session* for the whole suite and keeps the real one as
  `REAL_HAS_SESSION` for its own test. 424 tests, 410 before.

### Changed
- README: *What is in 0.23.0*; a *Confluence (read only)* section beside JIRA Live Data (the verb table, the CLI
  lines, the window, the tiles); Standards and export (the per-row way after the bulk replacement, the CLI lines);
  the form's Find page; Requirements; Configuration (`evidence_dir`, `[confluence] space`); Quick start; Tests.
- `uv.lock`: asi-kletz 0.23.0; asi-escher 0.2.1 (the sibling moved on; nothing here uses what changed).

## [0.22.0] - 2026-10-29

Phase A of the Confluence integration plan (`asi_hopper/docs/confluence-integration-plan.md`, "Kletz: URLs that
know what they are"; the plan numbered it 0.21.0, a version 0.21.0 of the same day had taken). The owner,
2026-10-29: "when we add confluence read only into kletz we should be able to associate objects with jama urls;
obviously the next candidate is replacing the google.com placeholder with a real url once known; but more
importantly there may be a way to tie in individual stpa objects to confluence." And right after: "i said jama
but meant confluence." No schema change (schema version stays 10); nothing here reads Confluence or Jira.

### Added
- **URL kinds** (`schema/urls.py`): `URL_KINDS = ("confluence", "jira", "sharepoint", "placeholder", "other")`
  and `url_kind(url, hosts=None)`, decided from the host and the path, nothing fetched: `asirobots.atlassian.net`
  under `/wiki/` is `confluence`, the same host under `/browse/` or `/jira/` is `jira`, any `*.sharepoint.com` is
  `sharepoint`, `www.microsoft.com` (the 0.20.0 placeholder) is `placeholder`, anything else is `other`; `hosts`
  (the owner's extra kinds, name to host or list of hosts, `*.` for a domain) is looked at first. `kind_label`
  (`Confluence, asirobots.atlassian.net`; `placeholder` alone), `url_kinds` (each kind once, in order) and
  `jira_issue_key` (`HWL-2554` off `/browse/`, `/issues/` or `selectedIssue=`). The existing functions are
  untouched. Jama gets no host, no kind and no door: the owner's "jama" was a slip for Confluence.
- **`[urls] hosts`** in `kletz.toml` (`brain.load_config`, `Brain.url_hosts`), optional and not asked for: more
  kinds so a pasted Jama or DMS link is not mislabelled (`hosts = { jama = "jama.example.com", dms = [...] }`); a
  value that is not a host or a list of hosts is ignored with a warning `status` reports. `kletz.example.toml`
  shows the table, commented out.
- **`plan urls --audit [--rows <id>...]`** (`WorkProductService.audit`): no write; the findings on every row (or
  the ones named, id or uid, repeatable; an unknown one is refused), each `{id, uid, order, deliverable, code,
  finding, kinds, urls}`: `placeholder` (the placeholder is still a URL of the row), `no_confluence` (the Work
  Product Location names Confluence and no URL is a Confluence page), `jira_key` (a Jira URL names an issue other
  than the row's key). A JSON Result whose `data` is the list, `ok` with findings or without: findings are data,
  not errors.
- **`plan urls --replace <old-url> <new-url> [--check]`** (`WorkProductService.replace`, the shape of
  `fill_placeholder`): every row whose list contains the old URL gets the new one in the same position, one
  transaction, one audit entry (`urls_replace`: the two URLs, the ids changed, the ids refused), the event
  `plan.urls_replaced`; `--check` names the rows and writes nothing; a row that already carries the new URL
  elsewhere is left alone and named in a warning (a URL is never listed twice); both URLs must be absolute
  http(s) URLs and differ, else the verb refuses. The answer carries the new URL's `kind`.
- `Argument.nargs` (`commands/base.py`, `automation/cli.py`): a flag that takes exactly that many values at
  once, so the CLI reads `--replace <old> <new>` as the plan spells it; `schema` prints it.
- Tests (`tests/test_url_kinds.py`): every kind and the edge hosts, the host map and the owner's word winning,
  the labels, the issue key, the map read from `kletz.toml` with a bad value warned, the audit's three findings
  on the seeded database with `--rows`, the owner's map in the audit, the replacement in the three forms
  (Python, the wire format, the CLI) with its position kept, its one audit entry and event, a page that moves
  corrected once, the dry run, the refusal of a row that already has the new URL, every refusal, the Excel cell
  text with and without the map and the import still skipping the column, the form's link text. 410 tests, 397
  before.

### Changed
- The Excel export's **Work product** cell text is the first URL's kind and host (`io/exporters.py`,
  `kind_label`) instead of the bare host; the hyperlink is the first URL as before; the import skips the column
  as before.
- The form's link lines (`gui/widgets.py:UrlsWidget`, `link_text`) carry the kind as a prefix
  (`confluence: https://... (the link)`); the screen hands the widget the owner's host map (`hosts`).
- `plan urls` with none of `--placeholder`, `--audit` and `--replace` says so naming all three; the `plan` help
  names the two new verbs; `--check` covers both the placeholder and the replacement.
- README: *What is in 0.22.0*; Standards and export (the cell text, URL kinds, the two verbs, the CLI lines);
  the form's link lines; Configuration (`[urls] hosts`); Quick start.

## [0.21.0] - 2026-10-29

The owner, 2026-10-29, on the exported QF-17 Safety Plan: "Could we turn the name of the safety deliverable
into a clickable URL and highlight it blue instead of green so it pops?" And asi_gutenberg 0.8.0's abridged
headers, wired into the export.

### Added
- **The deliverable's link** (asi_gutenberg 0.9.0, asi_standards the same day): the QF-17 source writes every
  plan row's Safety Deliverables cell as `[<name>]({{ row_N_url }})`, and the fill writes it into the Word
  original as a real hyperlink to the row's first work product URL, Word's Hyperlink style (blue, underlined)
  over the theme's pale blue shading `#CFE2F3`, never the green mark; a row whose URL is unfilled keeps the plain
  name. Kletz supplies the URL as in 0.20.0; `row_N_url` is documented as the link (`StandardsService`).
- **The Excel deliverable cell** (`io/exporters.py`, `DELIVERABLE`): the Safety Deliverables cell of a row with
  a URL is a hyperlink to the first one, the Hyperlink style, its text the name as before, beside the Work
  product column; a row without a URL keeps a plain cell; the import reads the names back.
- **Abridged headers** (`StandardsService`, `ABRIDGED_HEADERS`): a standard's folder may hold
  `abridged-headers.json` (verbatim column heading -> short form); `Standard.abridged_headers` names it and
  `standards list` prints it; `export` passes it to `fill_docx(..., abridged_headers=mapping, pdf=True)`, so the
  Word pass that prints the PDF shows the verbatim header on the plan table's first page and the short forms on
  every later one. Each export carries `abridged` (the tables split, by first heading) and `pages` (Word's count
  when it printed, else the rendering's) and `abridged_headers` (the file). Without Word the issue
  `abridged headers need Word` is a warning ending "the Word file keeps the verbatim header on every page",
  beside the PDF's.
- Tests (`tests/test_standards_template.py`): `test_export_links_the_deliverable_and_passes_the_abridged_headers`
  (the synthetic original gaining a link to the first URL in the Hyperlink style and the blue shading, no green,
  the row without a URL plain, the mapping handed to the Word session, which is replaced, `abridged` and `pages`
  carried, the file named by `standards list`), `test_without_word_the_abridged_headers_are_a_warning`,
  `test_word_prints_the_linked_deliverable_with_the_mapping` (skipped without WINWORD); `tests/test_work_products.py`:
  `test_the_excel_deliverable_cell_links_to_the_first_url`. 397 tests, 393 before.

### Changed
- `uv.lock`: asi-gutenberg 0.9.0 (was 0.7.2 in the lock), asi-hopper 0.1.8 (the sibling moved on; nothing here
  uses what changed).
- README: *What is in 0.21.0*; Standards and export (`row_N_url` as the deliverable's link, Abridged headers).

## [0.20.0] - 2026-10-29

The owner, 2026-10-29: "use the outlook method please and also please add the ability to add url parameters to
each deliverable... each deliverable may have multiple url... make sure that the excel export includes links to
the work products wherever they may be... on multiple urls just go to first; list of urls is sequential while
lists of names are alphabetical... include links to work products in the tool too... use microsoft homepage as
placeholder url for all". And, the same day: a row with no Jira ticket must say *no ticket attached* in the
workbook instead of leaving the cell empty. Schema version 9 → 10: the `urls` column on `safety_plan_row`, added
on open; no row is edited.

### Added
- **`services/outlook_service.py`**, the Outlook method: `lookup(text)` asks the Outlook desktop on this machine
  through its COM automation (PowerShell, `New-Object -ComObject Outlook.Application`, the subprocess pattern of
  asi_gutenberg's `pdf_with_word`, with a timeout and nothing left running: an Outlook the call started is told to
  quit) for the exact hit (`Session.CreateRecipient(text).Resolve()`) and the Global Address List entries whose
  name contains the text (`AddressEntries`, up to 30), each with its `Name` and SMTP address
  (`GetExchangeUser().PrimarySmtpAddress`, else `PR_SMTP_ADDRESS`), and answers `{text, count, matches: [{name,
  email, text}]}`. The COM call is one function, `run_outlook`, that the tests monkeypatch; a machine without
  Outlook, a refused call or a timeout is one `OutlookUnavailable` line (`Outlook is not available on this machine
  ...`). `outlook_present()` says whether Outlook desktop is installed, for the one real test.
- **`people lookup <text> [--limit n]`** (`commands/people.py`): the same for an agent, a JSON Result with the
  matches; nothing stored, nothing without the call.
- **Look up in the window** (`gui/people_lookup.py:PeopleLookup`; `gui/widgets.py:PeopleWidget`, `append_line`;
  `gui/entity_screen.py:lookup_people`, `lookup_for_role`): a **Look up** button beside each role's box in the
  Document parameters pane and beside the People box of the Parameters screen (greyed for a parameter that is not
  a role) opens one small window: a name entry, Search, the matches in a list, Insert. The search is a
  `BackgroundFetch` of `people lookup` polled with `after` (the Jira screens' pattern), never on the Tk thread;
  Insert appends the chosen `Name <email>` to the editor that asked (the guard sorts on save); a refusal is one
  line in the status bar and the window, the editor untouched; a second press brings the same window back.
- **`urls` on `safety_plan_row`** (`schema/definitions.py`, after `jira_key`; `FieldType.JSON`; sheet header `Work
  product URLs`; `picker="urls"`): an ordered list of absolute http(s) URLs, the first the link. **`schema/urls.py`**:
  `parse_urls` (the API's array, its JSON text, the `https://a; https://b` text or one per line; every problem at
  once, naming the line: not an absolute http(s) URL, an empty entry, a URL twice, text that is not a JSON array;
  the order kept, never sorted), `urls_json`, `urls_of`, `first_url`, `urls_text` (`; `), `urls_lines` (one per
  line), `url_host`, `is_url`. `WORK_PRODUCT_HEADER`, `WORK_PRODUCT_URLS_HEADER`, `NO_TICKET`.
- **The urls rule** (`services/work_product_service.py:WorkProductService`; `Brain._plan_guard` runs the schedule's
  guard then this one): on every create and update `urls` is parsed, validated and stored as JSON in the order
  given; a Jira key reading `no ticket attached` is no key. `loaded` (`on_load` of the plan service) does the same
  for a dump's or a workbook's row, dropping a bad list with the messages as warnings so the row still loads.
- **`plan urls --placeholder <url> [--check]`** (`WorkProductService.fill_placeholder`): every row with no URL gets
  `[url]`, one transaction, one audit entry (`urls_placeholder`, with the ids), the event `plan.urls_placeholder`;
  a row that has any URL is left alone, so a second run changes nothing; `--check` names the rows and writes
  nothing; a placeholder that is not an absolute http(s) URL is refused.
- **The Excel export** (`io/exporters.py:sheet_columns`): the Safety Plan sheet gets, right after Jira key, a
  **Work product** column (the export's own, no field: a clickable hyperlink to the row's first URL, the cell
  text the URL's host, the Hyperlink style; empty for a row without one) and the **Work product URLs** column
  (the field, one URL per line); a row with no Jira ticket prints `no ticket attached` in its Jira key cell. The
  import (`io/importers.py`, `DERIVED_HEADERS`) skips the derived column without a warning and reads the list
  back in order and the no-ticket text as no key. The dump carries the array.
- **The standards** (`StandardsService.row_values`, `ROW_PARAM`): `row_N_url` (the first URL) and `row_N_urls`
  (all, joined by a line break) per plan row that has any; `plan parameters` and `plan export` fill them where a
  source names them (the asi_standards README's parameter table lists them; the QF-17 source is unchanged).
- **The form** (`gui/widgets.py:UrlsWidget`): the Work product URLs box, one URL per line, the links beside it as
  clickable text (`Link.TLabel`, the palette's primary) with the first marked `(the link)`, an **Open** button
  that launches the first in the browser (`webbrowser.open`), a click (left or right) on any line launching that
  one; the table column reads `https://a; https://b` and sorts by that text.
- Tests: `tests/test_work_products.py` (the pure functions and every refusal, the verbs in the three forms, the
  CLI, the no-ticket text, the standards' row parameters, the Excel columns, the hyperlink and the no-ticket cell
  with the import, the dump round trip, the placeholder verb and its dry run, the schema 9 database that gains the
  column); `tests/test_outlook.py` (the script, the parsing, the service and the verb with the COM call
  monkeypatched, every refusal as one line, the CLI, and one real lookup of the owner's name that runs only where
  Outlook desktop is installed and prints nothing); `tests/test_gui_links_and_lookup.py` (the URLs editor, its
  links and Open with `webbrowser.open` monkeypatched, the order kept on save, a bad line in the status bar; Look
  up on the pane and on the Parameters screen with the COM function monkeypatched: the search off the Tk thread,
  the pick inserted, a refusal as one line with the editor still usable, no search without a press).

### Changed
- The Safety Plan sheet has 72 columns (the two Work product columns before the hidden uid); the sheet-columns
  test tolerates the derived column in a regenerated workbook.
- `plan` help names `urls`; the standards service's docstring and `Standard.row_parameters` name the two new row
  parameters; the window's theme recipes define `Link.TLabel`.
- README: *What is in 0.20.0*; Standards and export (the row parameters, Work product URLs, the CLI lines, the
  Excel columns and the no-ticket text, Look up in the pane and on the Parameters screen); Quick start.

### Deviations from the brief
- The export's Jira status is not a column of the Safety Plan sheet (it is fetched at `plan export` time for a
  standard, never stored), so *no ticket attached* appears in the Jira key cell only; the sheet has no status
  cell to carry it.
- The pane's links live in the form's Work product URLs box (the selected deliverable's details), the one place
  the row is edited, rather than in the standards pane above it, so the links and the editor are the same lines.

## [0.19.0] - 2026-10-29

The owner, 2026-10-29: "each safety deliverable can have multiple authors, so for any safety case field,
instead of the parameter being a string it is now an array of human names sorted alphabetically; make all
updates necessary; also must include email alongside name." Schema version 8 → 9: the `people` column on
`parameter`, added on open; no row is edited and no email invented.

### Added
- **`FieldType.JSON`** (`schema/fields.py`): a structured value stored as JSON text; a list or a dict handed in
  is stored as JSON, a string is kept as typed so an entity's own text form reaches its guard; read back as the
  Python value (`SqlRepository._decode`, `json_value`), so the JSON API answers with an array; the workbook
  writes the JSON text (`json_text`) and the import reads it back.
- **`people` on `parameter`** (`schema/definitions.py`, between `value` and `note`; sheet header `People`;
  `picker="people"`): a role's people. **`ROLE_SLUGS`**: the 22 slugs of the author and reviewer flag headers.
- **`schema/people.py`**: `Person` (name, email; `text` is `Name <email>`, `rendered` is `Name (email)`),
  `is_role`, `parse_people` (the API's array, its JSON text, the `Name <email>; ...` text or one person per
  line; every problem reported at once, each message naming the role and the line: no name, no email, an email
  that is not one, an email in the name, an email listed twice, text that is not a JSON array), `sort_people`
  (by name, case-insensitive, the full name as typed; the email breaks a tie), `people_json` (the canonical
  storage text), `people_of`, `people_text` (`; `), `people_lines` (one per line), `render_people`
  (`Name (email), ...`).
- **The people rule** (`StandardsService.parameter_guard`, `_people_rule`): a role parameter's people are
  parsed, validated and stored sorted; saving people clears the `value` (a differing value sent with them is
  ignored with a warning); a value on a role that holds people is refused; people on a parameter that is not a
  role are refused; a value on a role with no people is kept with the warning *a legacy value with no email
  yet*. **`parameter_loaded`** (`EntityService.on_load`): a dump's or a workbook's people parsed the same way;
  a bad value is dropped with the messages as warnings, the row still loads.
- **The rendering** (`StandardsService.parameter_text`, `document_rows`, `document_values`): a role's people
  render inline, alphabetical, `Name (email)` joined by `, `, one mark in the Markdown and one green run in the
  filled Word original; a legacy value renders verbatim; a role with no one leaves the blank unfilled.
- **The role report** (`StandardsService.role_summary`, `role_warnings`; `Standard.role_parameters`,
  `role_parameters` in `to_dict`): per role its state (`people`, `legacy`, `empty`), the count and the names;
  `legacy_roles` and `empty_roles`; one warning line each. In `plan parameters --row <id>` (per standard, with
  the values) and in `standards for --row <id>`.
- **The window** (`gui/widgets.py:PeopleWidget`, `gui/entity_screen.py`): in the Document parameters box each
  role is a small text box, one person per line as `Name <email>`, with a caption (the count, `no email yet:
  complete each line as Name <email>`, `no one yet`); a legacy name is prefilled so it can be completed; Save
  parameters writes the lines through `create` / `update parameter` (`people`), the guard's error naming the
  role and the line in the status bar; a box left as it was built is not saved. On the Parameters screen the
  `people` field is a `PeopleWidget`; the name decides which editor is live (a role's name: the People box,
  the Value entry read-only; any other: the Value entry, the People box greyed); the table column shows
  `Ann Lee <ann@...>; Ben Ray <ben@...>` and sorts by that text (`cell_text`, `sort_value`). Nothing runs off
  the Tk thread; no new Treeview iids.
- Tests: `tests/test_people.py` (the pure functions, the verbs in the three forms, every refusal, the legacy
  fallback and the report, the CLI, the export in the Markdown and through a synthetic Word original, the dump
  and workbook round trips, the schema 8 database that gains the column); the pane and Parameters screen tests
  in `tests/test_gui.py`.

### Changed
- `plan parameters` and `standards for --row` warn once per standard about the roles still legacy and once
  about the roles with no one (so the live database, 17 placeholders, gives two lines, not seventeen).
- `standards list` lists `role_parameters` beside `document_parameters`.
- README: *What is in 0.19.0*; Standards and export (the two kinds of document parameter, the CLI lines, the
  Document parameters box and the Parameters screen).

### Deviations from the brief
- The storage is (a) a new `people` column, not a JSON array in `value`: the `value` keeps meaning "a plain
  string" for `vehicle_type` and for a role's legacy name, the API field is honest about its type, and a row
  is legacy exactly when it has a value and no people, so nothing has to guess whether a string is JSON.
- The Parameters screen keeps both widgets on the form and greys the one the name does not use, instead of
  swapping one widget for the other: the legacy name stays visible beside the box that replaces it.

## [0.18.1] - 2026-10-29

The owner, 2026-10-29: "kletz just crashed for the first time", then again while saving a pasted
parameter; both times the terminal showed nothing and the audit log only that the save had not landed.
Headless replays of the save (plain, multi-line, tab, emoji, long, surrogate, quoted strings) all survive.
Schema version unchanged (8).

### Added
- **`gui.log`, the window's trace** (`gui/trace.py`, `MainWindow.__init__` / `close`, `app.launch`): beside
  the preferences file, every start (pid, version, server on or off, the arguments), every `close()` with
  the three frames that asked for it, the main loop's return and any exception escaping it; Python's
  `faulthandler` is enabled on the same file (all threads), so an access violation or abort inside Tk
  leaves the Python stacks there. Rolls to `gui.log.1` above a megabyte. A folder that cannot be written
  is skipped silently: the window opens regardless.

## [0.18.0] - 2026-10-29

The owner, 2026-10-29: "what we know as sprint 3 is actually sprint 31, renumber appropriately, and then ensure that sprints always go Tuesday to Tuesday; this supersedes anything I said before; I also included a picture from systems engineering that is law for our sprints." The picture, a strip of seven sprints: 31 10/27 to 11/9, 32 11/10 to 11/23,
33 11/24 to 12/7, 34 12/8 to 12/21, 35 12/22 to 1/4, 36 1/5 to 1/18, 37 1/19 to 2/1 (2026 into 2027). So a
sprint is 14 calendar days from a Tuesday to the Monday 13 days later, the next starting the next day; a
holiday never moves, stretches or shortens one (35 runs straight through Christmas and New Year); capacity
stays 8, fixed. The sprint of 2026-10-27 to 2026-11-09 is the picture's Sprint 31, so every number in the
chain shifts by 29 (the owner said "sprint 3 is actually sprint 31"; the dates in the picture decide: what
was Sprint 2 is Sprint 31, what was Sprint 3 is Sprint 32). This replaces the rule of 2026-10-28 (10 business
days, holidays stretching the dates) everywhere it was written. Schema version unchanged (8).

### Added
- **`sprint align <n> --start <YYYY-MM-DD>`** (`services/sprint_service.py:align`): the migration of an existing
  chain onto the law. The sprint that starts on that Tuesday becomes sprint `n`, every other sprint shifts by
  the same offset, `SPRINT n` labels follow (a label without the number is kept), every sprint that is not
  Closed is re-dated onto the cadence (14 days per number from the anchor; a Closed sprint keeps its dates as
  history), every reference follows (`sprint_item.sprint`, `sprint_item.carried_from`, `week.sprint`, the
  Safety Plan rows' `sprint`), then the plan's schedule is recomputed (`sprint_start`, `sprint_end`, the
  deadlines). One transaction, one audit entry (`align`, with the mapping), one event (`sprint.aligned`);
  idempotent (a second run writes and audits nothing). `--check` returns the mapping and writes nothing.
  Refused when the date is not a Tuesday, when no sprint or more than one starts on it, when two sprints share
  a number or when a number would fall below 1. For the programme's database:
  `asi-kletz sprint align 31 --start 2026-10-27`.
- **The cadence guard** (`SprintService.guard`): a sprint created or updated with a start that is not a
  Tuesday, an end that is not the start plus 13 days (an empty end is filled), or a start that is not the day
  after the previous sprint on the cadence ends (14 days more per number between them) is refused with the
  law's text (`CADENCE_RULE`), for sprints starting on or after 2026-10-27; an older sprint is history. Dates
  are checked when they are written, so a database not yet aligned still opens, closes and edits.
- `SPRINT_LENGTH` (14), `SPRINT_WEEKDAY` (Tuesday), `CADENCE_NUMBER` (31), `CADENCE_START` (2026-10-27) and
  `CADENCE_RULE` in `schema/definitions.py`; `SPRINT_RULE` is the owner's words of 2026-10-29 and the picture,
  quoted by the `sprint` verb's help, the README and the roadmap document.

### Changed
- **Every sprint date is cadence arithmetic**, not business days: `sprint start` ends a sprint on the Monday
  13 days after its first day (`--start`, else the day after the previous sprint ends, else `--as-of`; a
  Tuesday or refused); `sprint close` opens the next sprint the day after the closed one's end; `sprint plan`
  adds sprints 14 days each from the last end and `--replan` puts the Planned sprints after the active one
  back on the cadence; the `Holidays:` goal line still names the holidays a planned sprint contains, as days
  off, never as a reason to move it. The plan's report says `length_days` (14) instead of `days`.
- **`sprint_days` is no setting**: removed from the config loader's integer keys and from `status`
  (`sprint_length_days`, 14, is reported instead); the key, when present in `kletz.toml`, is ignored with a
  warning naming the law, like `sprint_capacity`. `--days` is gone from `sprint plan`. `SPRINT_DAYS` and
  `Brain.sprint_days` are gone. `kletz.example.toml` says so.
- `tracker/business_days.py` stays for the burndown's working days and `holidays_within`; its docstring no
  longer describes a sprint. The sprint report says a holiday inside a sprint is a day off, not a stretch.
- README: the Sprints subsection carries the owner's words and the picture's seven sprints as a table, the
  alignment and the superseded rule; `sprint align` in the command list; the configuration keys.
  `docs/sprint-planner-plan.md` and `docs/weekly-tracker-plan.md` carry a dated note that their cadence is
  superseded (the history stands).

### Tests
- `test_sprint.py` re-aimed to the law: the cadence (`sprint plan` from the owner's chain produces exactly the
  picture's seven sprints and 79 fortnights in three years), the guard (Tuesday, 13 days, gapless, numbers and
  dates locked together, history before the anchor), holidays never moving a sprint, the config keys ignored,
  `--replan` on an old-style chain, `sprint align` on a seeded database with items, weeks and plan rows (the
  mapping, labels, dates, references, the audit entry and the event, idempotence, every refusal, the dry run),
  the CLI. The schedule, GUI, transfer, generate and tracker tests pin the Monday end (`2026-11-09`); the
  tracker's planner test aligns the imported file first. `test_business_days.py` keeps its arithmetic.

### Rehearsal
- On a copy of the programme's database (77 sprints, 1 to 77 under the old rule): `--check` reported the mapping
  and wrote nothing; the alignment renumbered 77 sprints to 30 to 106 (Sprint 30 Closed keeps 2026-10-12 to
  2026-10-27; 31 is 2026-10-27 to 2026-11-09; 32 to 37 are the picture), re-dated 75, carried 15 items, 5
  weeks and 48 plan rows, and the recompute moved `sprint_end` on 46 of 48 plan rows; the second run changed
  nothing. The fortnight chain is shorter than the business-day one it replaces: it now ends at Sprint 106
  on 2029-09-24, so `sprint plan` adds the fortnights to three years ahead when wanted.

## [0.17.0] - 2026-10-29

The owner, 2026-10-29, on the exported QF-17: "bring back the color formatting for parameters and make it
a nice green, not neon, not forest ... please include the prefix before the colon of the assigned Jira
ticket name stacked with a line break, with points at the top and the status at the bottom". Schema
version unchanged (8). The lock takes asi_gutenberg 0.7.2 (the green `mark_bg`).

### Added
- **`row_N_jira_key`** (`services/standards_service.py:row_values`, `ROW_PARAM`): the deliverable's Jira key,
  upper-cased, the part before a colon when one was typed; the QF-17 source (asi_standards, 2026-10-29,
  later the same day) stacks it over `row_N_status` in the Status column, the points staying at the top of
  the Expected Duration/Deadline cell beside. A row without a key leaves it unfilled, named with the status.

### Changed
- **The Word original is filled with marks** (`export`): `fill_docx(..., mark=True)`, so every filled value is
  shaded the theme's green in the exact Word file and in Word's print of it, as the Markdown rendering
  marks them; 0.16.0 wrote the Word file unmarked.
- The table header repeating on every page ("the sticky columns") is unchanged since 0.16.0; an export made
  from a window started before 0.16.0 does not have it, a relaunch does.

## [0.16.1] - 2026-10-29

The family's integration review of 2026-10-29. Schema version unchanged (8). The lock takes asi_gutenberg
0.7.1 and asi_escher 0.1.3.

### Fixed
- **An export whose Word print failed named a PDF that was gone** (`services/standards_service.py:export`,
  through asi_gutenberg 0.7.1): 0.16.0 promised that when Word cannot print, the PDF stays Gutenberg's
  rendering with a warning, but asi_gutenberg 0.7.0's `pdf_with_word` removed that rendering before asking
  Word, so a failed print (no Word on the machine, as on the CI runner; a COM failure) left `files.pdf` and
  `primary` pointing at a file that did not exist. asi_gutenberg 0.7.1 prints to a working name and replaces
  the target only once the print is there; the export's promise holds as written, and the extra role lines
  of a filled cell take the template's run formatting too (the same release).

### Tests
- `test_a_failed_print_keeps_gutenbergs_pdf`: Word made unreachable (the PowerShell call raises), the export
  answers `exact.pdf` false, the warning, and a PDF that exists.

## [0.16.0] - 2026-10-29

The owner, 2026-10-29, on the exported QF-17: "can we make it exactly like the template? I still want all the
columns to pop up in every page but otherwise we need to match the template exactly." Schema version
unchanged (8). The lock takes asi_gutenberg 0.7.0 (`fill_docx`) and asi_hopper 0.1.7.

### Changed
- **The export writes the Word original filled in place** (`services/standards_service.py:export`,
  `Standard.template`): a standard whose folder holds exactly one `.docx` under `source/` (the asi_standards
  layout: the controlled document preserved byte for byte) names it as its template, and `plan export`
  writes `<folder>.docx` as that original with the source's text put into its own runs by asi_gutenberg
  0.7.0's `fill_docx`: every style, header, footer, table, column width and page orientation the
  template's, every table's first row repeating at the top of each page it spans, a value changed only where
  the source changed it, no marks in the Word file (the Markdown keeps its `==marks==`, as before). The PDF
  is Word's own print of that file (`pdf_with_word`, Windows with Word); when Word cannot print, the PDF
  stays Gutenberg's rendering and a warning says so (`<folder>: pdf through Word failed: ...; the PDF is
  Gutenberg's rendering, not the template`). A folder without an original, or with more than one, exports
  as before. Each export entry carries `template` and `exact` (`{"docx": bool, "pdf": bool}`); `standards
  list` and `plan parameters` show the template path.
- The Safety Plan pane's export status says what was exact: `Exported ... (docx and pdf the template
  exactly); N parameter(s) still unfilled`.
- An export with an original takes longer (the 3.4 MB QF-17 reads twice and Word prints: about 15 s on the
  owner's machine) and runs on the Tk thread like the rest of the export; the window waits.

## [0.15.3] - 2026-10-29

A broken-windows sweep of the repository after the 0.15.x patches; no behaviour changes. Schema version
unchanged (8).

### Removed
- `EntitySchema.all_columns` and `SqlRepository.bulk_insert`: no caller in the source or the tests
  (the importers write through `EntityService.create`, one row at a time; the exporters read the
  schema's field names).

### Fixed
- README: the Configuration section listed five workbook sheets and left out `Parameters` (0.14.0);
  the layout tree lacked the `tracker/` package and the five services added since 0.8.0, and its
  `tests/` line named eleven of the seventeen test modules; "Adding an entity" still said
  `ALL_ENTITIES` lists "the four of 0.8.0" (six since 0.14.0).
- `docs/plan.md` said "0.7.3 delivered" while its section 8 recorded every release to 0.15.0.
- CHANGELOG: no compare links for 0.8.0 to 0.15.2, and `[Unreleased]` compared against 0.7.4.
- `uv.lock` recorded this package as 0.15.0 and the siblings as asi_hopper 0.1.5 and asi_escher
  0.1.1; it now takes 0.15.3, asi_hopper 0.1.6 and asi_escher 0.1.2 (what the siblings' `main`
  branches declare, which is what CI checks out). asi_gutenberg stays 0.6.0, its committed version.

## [0.15.2] - 2026-10-29

The owner, 2026-10-29: "we might have found a bug in the Jira ticketing system". The audit log: the Safety
Plan row (order 1, PDP phase 1, Concept Development) was saved at 13:50 with PDP phase 2 and lifecycle
phase "2. HARA / Risk Assessment", each exactly one step past its value, while a Jira ticket was being
attached; the plan out of phase order is what 0.15.1 fixed the painting of. Schema version unchanged (8).

### Fixed
- **The mouse wheel over a combobox picked its next value** (`gui/main_window.py`): Tk 8.6 binds
  `<MouseWheel>` on the `TCombobox` class to "select the next value", and the form scrolls on the same wheel
  (`ScrollableFrame` binds it on every widget while the pointer is over the form), so scrolling the form with
  the pointer passing over a PDP phase, lifecycle phase, status or Jira ticket box silently changed it, and
  the next Save stored it. The window drops that class binding (and the spinbox's) once at start: the wheel
  scrolls, a value changes only by a pick or a keystroke. A test wheels over the two phase boxes and the
  Jira picker and reads the form back unchanged.

## [0.15.1] - 2026-10-29

The owner, 2026-10-29, after attaching Jira tickets to several deliverables: "as I was flipping through
screens at some point the deliverables scroller got stuck and I could only see the first couple of rows",
with `_tkinter.TclError: Item pdp:2 already exists` from every stacked screen's `_populate`. Schema version
unchanged (8).

### Fixed
- **A plan out of phase order broke every stacked screen** (`gui/screens.py:stack`): the plan's first row
  had been saved under PDP phase 2 while rows 2-7 stayed under phase 1 and phase 2 opened again at row 8.
  `stack` opens a group line whenever the phase changes between consecutive rows, by design (the truth of
  the plan's order), but gave the second opening the same iid `pdp:2`; a Treeview item id must be unique,
  so the insert raised, the table kept the rows painted before it, and every refresh (a save, a navigation,
  the event poll) raised again. A group that opens again now takes the iid `pdp:2#2`, `phase:2:...#2` and so
  on (`#3` for a third opening); `is_group` still holds, the group tags and the stripe style unchanged, the
  Safety Plan table, the matrix and its frozen pane paint the whole plan, and a search on the matrix finds a
  deliverable under a reopened phase.

## [0.15.0] - 2026-10-29

The owner, 2026-10-29, on the exported QF-17: "the expected duration value has to change: right now we have
`{{ row_11_points }} points` / `2027-02-10` but it should be `11 points` / `2027-02-10`; and for status we are
getting `{{ row_11_status }}` but really we should be able to add a Jira ticket for each deliverable; every
work product needs to be linked to some Jira ticket, so for every work product allow the user to select a
Jira ticket." Schema version unchanged (8).

### Changed
- **The points the export prints** (`services/standards_service.py:row_values`, `plan parameters`): the
  owner's revision of the 2026-10-29 rule. `row_N_points` is the weight the schedule actually used for the
  row, as `generate/plan_schedule.py:weight_of` resolves it: the chosen `points` when set, else the row's
  `default_points`; only a row with neither (the scheduler fell back to the global floor) stays unfilled,
  with one warning naming the rows (`row(s) 4 have neither points nor a default: their points stay
  unfilled`). Before, a row without chosen points left the placeholder while the sprint end under it came
  from the scheduler weighing the row at its default; the two lines now agree. The Safety Plan pane's own
  line says which it is (`3 points (the panel's default, no points chosen)`).

### Added
- **A Jira ticket picker on every work product** (`gui/widgets.py:JiraPickerWidget`, `FieldSpec.picker`
  (`"jira"` on `jira_key`), `WidgetFactory.create` picking it, `gui/entity_screen.py`): a combobox whose list
  is the issues of the window's last JIRA Live Data fetch (`window.jira_live`), shown as `HWL-2554  Perform
  Platform Safety Plan`; typing filters the list on key or summary, case-insensitively; a pick stores the key
  alone; the entry stays free text, so a key not in the list can still be typed; a cleared box clears the
  key; the picked ticket's status shows beside the box, read from the fetched rows, nothing stored. The
  screen feeds every picker on build and on every refresh, so a fetch made on the live screen reaches it.
- **Load tickets** (`gui/ticket_loader.py:TicketLoader`): beside the picker; because a person pressed it,
  one `jira live` on the worker thread through the existing `BackgroundFetch` / `execute_quiet` path; a
  rejected session becomes one `jira login` (the browser opens) and the fetch runs again, once per press, as
  the live screen's Refresh does since 0.11.1; the Result lands on `window.jira_live`, so the live screen
  paints the same rows without a second fetch; a second press while one runs is ignored.
- **`plan tickets`** (`commands/plan.py`): every work product in plan order with its `jira_key`, and
  `missing`, the orders of the ones still without one; `plan export`'s warning keeps naming them.

### Deviations from the brief, and what it got wrong once it met the code
- **The fetch flow is a second instance, not the live screen's object.** The brief said "the same code path":
  the loader runs the same `BackgroundFetch` with the same `execute_quiet`, the same `jira live` and `jira
  login` verbs, the same one-sign-in rule and the same `window.jira_live`; the state machine itself (the
  fetch in flight, the poll, the login flag) is the loader's own, as the comments window already has its own,
  because the live screen's one is bound to its toolbar and its tests pin its attributes.
- **A list fed after a key was typed shows every issue**, not the issues matching the typed key: a key the
  fetch does not know would otherwise hide the whole list the person just loaded; typing narrows it again.
- **A Done row's points are printed too** (its own chosen points or default): the scheduler leaves a Done row
  alone, but the document is a plan table, and the owner's "11 points" is the deliverable's weight, finished
  or not.
- The brief's example said row 11 "has no chosen points" and a default of 8; the rule implemented reads any
  row the same way, the figures are the owner's database's.
- `uv lock` took asi_gutenberg 0.5.0 → 0.6.0, the sibling's current version (the one 0.14.1 already builds
  the standards with); the lock says 0.15.0 for the project.

### Tests
- 320 → 324: the printed points equal the schedule's weight column (chosen, default, neither
  with the warning; a Done row's own); `plan tickets`; the picker (an empty list before any fetch, the
  labels, filtering by summary and by key, a pick storing the key alone with its status, a free key, a
  cleared box, saving through the form and the table column); Load tickets running one `jira live` on the
  worker through the stubbed `execute_quiet`, a second press ignored, the list filled and shared with the live
  screen; a rejected session signing in once like Refresh, a second rejection offline with the rows kept.

## [0.14.1] - 2026-10-29

The owner, 2026-10-29: "the report was portrait; we should strive to make the Word product as close as
possible to the original." The QF-17 original is portrait with its plan table on landscape pages.

### Changed
- **The export no longer turns the whole document landscape** (`services/standards_service.py`): the
  standard's source carries its own page turns (asi_gutenberg 0.6.0 `section` blocks, `<!-- section:
  landscape -->` before the plan table and back after it), so the PDF and the Word file are portrait with
  the table on landscape pages, as the original. `LANDSCAPE` is gone.

## [0.14.0] - 2026-10-29

The owner, 2026-10-29: "in the safety plan window when you select a safety plan deliverable the bottom pane
gets populated with data about that deliverable; now in that screen the first item is a button that asks you
for a local folder to save a new version or view of the model in the form of that safety plan deliverable;
then following that please have all the parameters for the doc and then after that all content as is today;
obviously the export button makes it so that parameters reach Gutenberg and it makes us a file." And on the
values: "the expected duration/deadline should be a string `x points` where x is the chosen number of points
for the deliverable, not the default value, never the default value, then a line break and then the date we
expect the sprint to conclude; the status parameter is the status of Jira, forget about the status names
called out in the spreadsheet; this company ties deliverables to Jira tickets." Schema version 7 → 8.

### Added
- **`jira_key` on `safety_plan_row`** (`schema/definitions.py`): TEXT, after `status`, not a source column,
  visible and editable: the Jira ticket that tracks the deliverable; the table and the form show it (70
  fields, 69 visible, 64 editable, 63 source).
- **The `parameter` entity** (`name` required, `standard` empty for every standard, `value`, `note`; sheet
  `Parameters`; a name unique per standard, `StandardsService.parameter_guard`), sixth in `ALL_ENTITIES`, with
  the CRUD verbs, the dump, the workbook sheet and a **Parameters** screen after Holidays.
- **`standards_dir`** in `kletz.toml` (default `../asi_standards` beside the file; `$ASI_KLETZ_STANDARDS`;
  `Brain(standards_dir=)`; read when asked; in `status`, in `kletz.example.toml`, in the README).
- **`services/standards_service.py`**: `list` (every subfolder holding a Markdown source of its own name; the
  title from the front matter; the parameters through `asi_gutenberg.parameters`, split into document-level
  and row-level by `row_\d+_(points|sprint_end|status)`), `for_row` (a set `ref_<slug>` flag names a folder
  starting with the QMS id in slug form: `ref_qf_17` → `qf-17-...`, never `qf-170`), `document_values` (the
  `parameter` rows whose standard is empty or this one, the standard's own winning), `row_values`
  (`row_N_points` from `points` only, `row_N_sprint_end`, `row_N_status` from the Jira statuses),
  `jira_statuses` (one `JiraService.statuses` call; no session or a failed read is one warning naming the
  keys skipped; rows without a key are named once), `value_set` and `export` (`asi_gutenberg.from_markdown`
  then `build` with `theme={"orientation": "landscape"}`, `strict_params=False`, `mark_params=True`, `name`
  the folder; the files, the pages, the filled count, the unfilled names as data and as warnings; one audit
  entry `export`; the event `plan.exported`).
- **`JiraService.statuses(keys)`**: one `hopper.get(key)` per distinct key through one non-interactive Hopper.
- **Verbs**: `standards list` / `standards for --row <id>` (`commands/standards.py`); `plan export --row <id>
  [--out <dir>] [--standard <folder>]` and `plan parameters --row <id>` (`commands/plan.py`).
- **The standards pane** (`gui/entity_screen.py`, the stacked entity only): at the top of the details form,
  **Export document…** (enabled when the selected row has a standard; `filedialog.askdirectory` when the
  window is interactive, else the configuration's `out`; then `plan export`; the status bar names the files
  and the unfilled count) beside the row's standard or the "No standard for this deliverable" line; a
  **Document parameters** box with one entry per document-level parameter, prefilled from the `parameter`
  table, and **Save parameters** (`create` / `update parameter` through `window.run`); a line with the row's
  own values as the export fills them; then the form as before. Selecting another row refreshes it.

### Deviations from the brief, and what it got wrong once it met the code
- **A parameter saved from the pane is global** (`standard` empty) unless a row for that name already exists
  (global or the row's standard), which is then updated: the owner supplies the twenty-one values once and
  the roles are the same parameters in every standard; a per-standard value is still a `create parameter
  --set standard=<folder>` away and wins.
- **The pane shows the last fetched Jira status, not a stored one**: nothing from Jira is stored (the family
  rule); the status the last export of the session fetched is shown "as of the last export", and before any
  export the line says the status is fetched on export.
- **`plan parameters` reads Jira too** (one Hopper read per distinct key): the value set it prints is the one
  the export would fill, which the brief asked for, and that includes the status.
- **An absent folder** lists no standard and refuses the export naming the folder; the brief did not say.
- `standards_dir` was given an environment override (`$ASI_KLETZ_STANDARDS`) like the other paths, so the
  test suite never reads the real sibling repo.
- `uv lock` took asi_gutenberg 0.2.1 → 0.5.0, the sibling's current version, which the parameters need
  (`from_markdown`, `parameters`, `build(params=...)`).

### Tests
- 311 → 320: the folder scan and the match by QMS flag (`qf_17` names `qf-17-...`, never
  `qf-170` or `qp-17`); the parameter entity's uniqueness and names; the value set and the export on a tmp
  standard (`{{ vehicle_type }}`, `{{ fusa_engineer }}`, row 1 and row 2) with a stub Hopper: the
  document-level values from the table with the standard's own winning, row 1's points, sprint end and Jira
  status, row 2's status and points unfilled (a default of 3 never written), the `==value==` marks in the
  Markdown, the triplet, the audit entry and the event, one read per distinct key, a named and an unknown
  standard, a row without a standard; offline: one warning naming the keys, the status left unfilled; the
  default `out`; the GUI pane: disabled for a row without a standard, the standard and the two entries for
  row 1, Save parameters creating and updating rows, Export in non-interactive mode writing into `out` with
  the status line, the form below unchanged, New emptying the pane.

## [0.13.1] - 2026-10-29

The owner, 2026-10-29: "change the colour of the little widget that you pull up and down or side to
side to interact with a scroll bar."

### Changed
- **The scrollbar thumb** (`gui/theme.py`, the grid recipe): `TScrollbar` `background`, `lightcolor`
  and `darkcolor` are the palette's `primary_dim` (they were the panel colour, the same as the
  trough's neighbours, so the thumb was hard to find), and `active` maps to `primary`; the trough
  stays `bg`, the arrows as before. Implemented the same way in the sister tool: a convention, not
  shared code.

### Tests
- `test_scrollbar_thumb_is_the_primary`.

## [0.13.0] - 2026-10-28

Open question 1 of `docs/hidden-identity-plan.md`: a sprint item pointed at its plan row by id alone, so a
tracker dump loaded after a plan re-import that renumbered the rows pointed at the wrong deliverables. Schema
version 6 → 7. Continuous integration joins the repo.

### Added
- **`sprint_item.plan_uid`** (`schema/definitions.py`): TEXT, hidden, beside `plan_row`: the plan row's uid.
  The sprint service keeps the two in step (`SprintService.link_item`, the item's guard; `link_loaded`, its
  load hook; `EntityService.on_load` is new, and a guard may now return warnings): given `plan_row`,
  `plan_uid` follows; given `plan_uid`, `plan_row` is resolved from it; the uid wins when both are given and
  disagree, with a warning; by hand an unknown uid or id is refused, on a load an unknown uid leaves
  `plan_row` empty with a warning; clearing one clears both. The tracker import carries both from the matched
  row. On open, after the uid stamp and the capacity rule, `SprintService.fill_plan_uids` gives every item
  that has a `plan_row` and no `plan_uid` the row's uid, audited once (`link_plan_uids`, the count and the
  ids), reported in `migration["plan_uids_filled"]`.
- **The scheduler pins by uid** (`generate/plan_schedule.py`: `uid_map`, `plan_row_of`): an item's plan row
  is found by its `plan_uid` when the rows know it, else by `plan_row`; the pure functions take an optional
  uid map and the old call forms still work.
- **Continuous integration** (`.github/workflows/ci.yml`): on push to `main`, on tags `v*` and on pull
  requests; `windows-latest`; `actions/checkout@v4` of this repo into `asi_kletz/` and of `c00289/asi_escher`,
  `c00289/asi_gutenberg` and `c00289/asi_hopper` into sibling folders (their default branches), because the
  lock pins them as editable path sources; `astral-sh/setup-uv@v5` with the cache, `uv python install 3.13`,
  `uv sync`, `uv run ruff check src tests`, `uv run pytest -q`, every run step in `asi_kletz/`.
- `uv lock` run once: the lock said 0.7.4 for the project since the version bumps never touched it; it now
  matches `pyproject.toml`, and took asi_hopper 0.1.5, the sibling's current version (the sign-in of 0.11.1
  runs on it).

### Changed
- The board's form keeps showing `plan_row` as the handle; `plan_uid` has no widget and no column, like the
  uid. The workbook's Sprint Items sheet carries it hidden (17 columns, `uid` last); the JSON carries it.

### Deviations from the brief
- None in substance. One reading: the brief said "given `plan_uid`, resolve `plan_row` from it" without
  saying what an unknown uid does; by hand it is refused (a typo), on a load it empties `plan_row` with a
  warning (a stale number would point at the wrong deliverable, which is the very thing the uid prevents).
  And on a load the uid wins over a disagreeing id silently: a renumbered id in the file is the case the uid
  exists for, not something to warn about per row.
- **The `v0.12.0` tag annotation** carries the first line of the 0.11.4 CHANGELOG entry instead of 0.12.0's: the
  release script that writes the line had stopped early and the tag was cut from a stale file. Tags are never
  moved (the family rule); the GitHub release of v0.12.0 carries the right notes, and this entry is the record.

### Tests
- 308 → 311: the link on create and update (either way round, the uid winning with a warning,
  clearing both, the refusals), the scheduler committing by uid; items written before the column linked on
  open, audited once, nothing on the second open; the round trip: dump the items, replace-import the plan
  under new ids, load the items, every item points at the right deliverable and the schedule follows; an
  orphaned uid on load; the hidden-field list of `sprint_item`, the sheet's hidden column, the 0.8.4 fixture's
  altered columns.

## [0.12.0] - 2026-10-28

The last open items of `docs/weekly-tracker-plan.md` (the burndown and velocity diagrams and the sprint report
of phase 4) and the roadmap the owner asked for beside them. Schema version unchanged (6). The sprint rule
(10 business days, 8 points fixed, consecutive sprints, 1 point = one productive day) is quoted in the roadmap
document from `schema/definitions.py:SPRINT_RULE`, now the one place the owner's words live (the `sprint`
verb's help imports it).

### Added
- **Charts in the diagram catalog** (`generate/charts.py`): `Chart` (a title, the plain ``data`` the picture is
  drawn from, a ``draw(ax)``), rendered by matplotlib into PNG and SVG; `figures.render_diagram` dispatches on
  it (`dot` / `mmd` dropped with a warning, refused when nothing is left), `figures.add_diagram` renders it
  into `<out>/figures/` and embeds it as an asi_gutenberg `figure` block. `sprint_burndown` (param `sprint`,
  default the active sprint): the sprint's items that are not Carried, a Done item burning its points on its
  `done_on` (one without a date burns on day one, with a warning), the ideal line from `capacity_of` to zero
  over the business days, weekends and holidays as shaded gaps with the holiday named. `velocity`: one bar per
  Closed sprint (points done) and the three-sprint mean as a line (`VELOCITY_WINDOW`); empty with a warning
  until a sprint is Closed. `plan_roadmap`: `roadmap_data` runs the scheduler once and gives the rows in plan
  order with the sprints each occupies and finishes in, the columns from the active sprint to the last one any
  deliverable finishes in with their holidays, the total points, the completion sprint and date, the unreached
  rows and the scheduler's warnings; the chart draws one mark per occupied sprint, the finishing one darker, a
  star on a holiday-bearing sprint.
- **`Schedule.occupancy`** (`generate/plan_schedule.py`): the sprints a deliverable takes points from, its own
  items' sprints included, so the roadmap is drawn from the scheduler and nothing else.
- **`sprint_report`** (`generate/documents.py`, kind report, param `sprint`): the sprint's facts (`sq.board`),
  the goal, the board table in status order (To Do, In Progress, Done, Carried) with points and plan row, the
  generated sprint line, the burndown and velocity charts, the items carried out and in, the holidays inside the
  sprint. **`plan_roadmap`** (kind plan, "Safety Plan Roadmap"): purpose, the sprint rule verbatim, the totals
  (deliverables, done, scheduled, beyond the chain, points to schedule, completion), the roadmap chart, one
  table per lifecycle phase (deliverable, points, sprint, start, end, status), a "Not scheduled" section when
  the chain runs out, a holidays appendix naming each holiday's sprint.
- README rows for the three charts and the two documents; the tracker plan's Status says fully implemented.

### Fixed
- Deleting a sprint whose items still point at it crashed the recompute (`KeyError` on the vanished sprint);
  a fully committed deliverable whose last item's sprint is gone now pours like any other.

### Deviations from the brief, and what it got wrong once it met the code
- **Not Escher diagrams.** The brief asked for the burndown, the velocity and the roadmap "as an Escher
  diagram"; asi_escher's kinds are `activity`, `flowchart`, `state`, `bdd`, `ibd` and `req`, node-and-edge
  graphs with an automatic layout, with no chart, axis, bar or grid. A burndown drawn as a chain of day
  nodes would not be a burndown. The three are matplotlib charts (asi_escher's own plotting library, already
  a dependency) in the same catalog, built by the same verb, listed by the same screen, embedded by the same
  helper; they write PNG and SVG, not `dot` or `mmd`, and a document's result lists them under the figures it
  wrote rather than in `diagrams` (asi_gutenberg's list of its own diagram blocks).
- **The Generate screen has no `sprint` entry.** Its only parameter widget is the phase combobox; from the
  screen `sprint_burndown` and `sprint_report` take the active sprint. The CLI and an agent pass `--param
  sprint=n`.
- **A document's stem is its key**, so `document sprint_report --param sprint=1` overwrites
  `sprint_report.{md,pdf,docx}` of another sprint; the figures inside are per sprint
  (`figures/sprint_burndown_1.png`). A per-sprint document stem is a later change if the owner wants the
  reports kept side by side.
- `plan_roadmap` is both a diagram key and a document key (two catalogs, two stems: `plan_roadmap.png` and
  `plan_roadmap.{md,pdf,docx}` plus `figures/plan_roadmap.png`).

### Tests
- 303 → 308: the burndown's numbers (committed without the Carried item, nine business days around a
  Monday holiday, the burn on day one and on `done_on`, the ideal line, the gaps, the holiday), its files and
  formats, the sprint parameter forms; the velocity on no, one and two Closed sprints; the roadmap from the
  scheduler (occupied and finishing sprints, the holiday column, the totals and completion, the unreached row
  and the chain extended by `sprint plan`); the sprint report's triplet, figures, board order and carried
  items; the roadmap document's rule, phase tables, holidays appendix and "Not scheduled" section; the catalog
  lists.

## [0.11.4] - 2026-10-28

Open question 1 of `docs/plan-points-plan.md`, answered by the owner, 2026-10-28: a deliverable with a
sprint item in sprint n was pinned to n and the item's points also reduced n's free capacity, so a 7-point
deliverable with a 4-point item in its sprint finished a sprint late. The owner's rule: the item's points
are the part of the deliverable already committed. Schema version unchanged (6).

### Changed
- **The scheduler** (`generate/plan_schedule.py`): `own_items` (kind Deliverable, pointing at a plan row,
  not Carried), `committed_points` (their points per plan row, any sprint, any status but Carried; an
  unpointed item commits nothing) and `pins` over any sprint. The committed points come off the
  deliverable's weight; the remainder pours from the last sprint holding one of its items onward, as before;
  the items' points reduce their sprints' free capacity once, as any committed item's do; a remainder of 0
  finishes in that last sprint, Closed or not. `Schedule.committed`; `plan schedule` prints `committed`
  beside `weight`.
- The plan's open question 1 is struck through and answered; its change log says so.

### Deviations
- None from the brief. One reading the brief left open: a deliverable whose remainder is 0 and whose last
  item sits in a Closed sprint finishes in that Closed sprint (its dates become the deadline), the row
  itself staying whatever status it has; a Done row still keeps what it has.

### Tests
- 302 → 303: `test_own_items_are_the_committed_part_of_the_weight` (the 7-with-4 case, a fully committed
  deliverable, an unpointed item, two items in two sprints, an item in a Closed sprint, the pins and the
  committed points); `test_a_committed_item_pins_the_start` on an unpointed item; the end-to-end recompute
  test rewritten for the new dates.

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

[Unreleased]: https://example.invalid/asi-kletz/compare/v0.19.0...HEAD
[0.21.0]: https://example.invalid/asi-kletz/compare/v0.20.0...v0.21.0
[0.20.0]: https://example.invalid/asi-kletz/compare/v0.19.0...v0.20.0
[0.19.0]: https://example.invalid/asi-kletz/compare/v0.18.1...v0.19.0
[0.18.1]: https://example.invalid/asi-kletz/compare/v0.18.0...v0.18.1
[0.18.0]: https://example.invalid/asi-kletz/compare/v0.17.0...v0.18.0
[0.17.0]: https://example.invalid/asi-kletz/compare/v0.16.1...v0.17.0
[0.16.1]: https://example.invalid/asi-kletz/compare/v0.16.0...v0.16.1
[0.16.0]: https://example.invalid/asi-kletz/compare/v0.15.3...v0.16.0
[0.15.3]: https://example.invalid/asi-kletz/compare/v0.15.2...v0.15.3
[0.15.2]: https://example.invalid/asi-kletz/compare/v0.15.1...v0.15.2
[0.15.1]: https://example.invalid/asi-kletz/compare/v0.15.0...v0.15.1
[0.15.0]: https://example.invalid/asi-kletz/compare/v0.14.1...v0.15.0
[0.14.1]: https://example.invalid/asi-kletz/compare/v0.14.0...v0.14.1
[0.14.0]: https://example.invalid/asi-kletz/compare/v0.13.1...v0.14.0
[0.13.1]: https://example.invalid/asi-kletz/compare/v0.13.0...v0.13.1
[0.13.0]: https://example.invalid/asi-kletz/compare/v0.12.0...v0.13.0
[0.12.0]: https://example.invalid/asi-kletz/compare/v0.11.4...v0.12.0
[0.11.4]: https://example.invalid/asi-kletz/compare/v0.11.3...v0.11.4
[0.11.3]: https://example.invalid/asi-kletz/compare/v0.11.2...v0.11.3
[0.11.2]: https://example.invalid/asi-kletz/compare/v0.11.1...v0.11.2
[0.11.1]: https://example.invalid/asi-kletz/compare/v0.11.0...v0.11.1
[0.11.0]: https://example.invalid/asi-kletz/compare/v0.10.0...v0.11.0
[0.10.0]: https://example.invalid/asi-kletz/compare/v0.9.1...v0.10.0
[0.9.1]: https://example.invalid/asi-kletz/compare/v0.9.0...v0.9.1
[0.9.0]: https://example.invalid/asi-kletz/compare/v0.8.4...v0.9.0
[0.8.4]: https://example.invalid/asi-kletz/compare/v0.8.3...v0.8.4
[0.8.3]: https://example.invalid/asi-kletz/compare/v0.8.2...v0.8.3
[0.8.2]: https://example.invalid/asi-kletz/compare/v0.8.1...v0.8.2
[0.8.1]: https://example.invalid/asi-kletz/compare/v0.8.0...v0.8.1
[0.8.0]: https://example.invalid/asi-kletz/compare/v0.7.4...v0.8.0
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
