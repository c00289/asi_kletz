"""Diagrams and documents: the real generators, no mocks (except the locked-PDF PermissionError)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from asi_kletz import Brain
from asi_kletz.automation.cli import main
from asi_kletz.brain import ENV_CONFIG, ENV_OUT
from asi_kletz.generate import BuildContext, DiagramFactory, DocumentFactory
from asi_kletz.generate import plan_queries as q
from tests.conftest import PLAN, REPO_ROOT, TABLES

DIAGRAMS = ["lifecycle_overview", "phase_flow", "status_board", "pdp_map", "stpa_trace", "sprint_burndown", "velocity",
            "plan_roadmap"]
DOCUMENTS = ["safety_plan", "status_report", "phase_checklist", "sprint_report", "plan_roadmap", "stpa_report"]
FENCE = {"png", "svg", "dot", "mmd"}


def _tables(markdown: str) -> list[tuple[str, list[list[str]]]]:
    """``(caption, rows)`` per pipe table, rows including the header, cells stripped."""
    blocks = re.split(r"\n\s*\n", markdown)
    out: list[tuple[str, list[list[str]]]] = []
    for index, block in enumerate(blocks):
        lines = [ln for ln in block.strip().splitlines() if ln.startswith("|")]
        if not lines or len(lines) != len(block.strip().splitlines()):
            continue
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
        rows = [r for i, r in enumerate(rows) if i != 1]  # drop the separator row
        following = blocks[index + 1].strip() if index + 1 < len(blocks) else ""
        caption = following if following.startswith("*Table") else ""
        out.append((caption, rows))
    return out


def _config_brain(tmp_path, monkeypatch, toml: str) -> Brain:
    config = tmp_path / "kletz.toml"
    config.write_text(toml, encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    return Brain(tmp_path / "cfg.db", workbook_path=tmp_path / "view.xlsx", out_dir=tmp_path / "out")


# -- catalogs ---------------------------------------------------------------------
def test_catalogs_list_every_key_with_title_description_and_params(brain):
    diagrams = brain.execute("diagram").data["diagrams"]
    documents = brain.execute("document").data["documents"]
    assert [d["key"] for d in diagrams] == DIAGRAMS
    assert [d["key"] for d in documents] == DOCUMENTS
    for entry in diagrams + documents:
        assert entry["title"] and entry["description"] and isinstance(entry["params"], list)
    phase_flow = next(d for d in diagrams if d["key"] == "phase_flow")
    assert phase_flow["params"][0]["name"] == "phase" and phase_flow["params"][0]["required"]
    assert phase_flow["params"][0]["lookup"] == "lifecycle_phase"
    assert DiagramFactory.keys() == DIAGRAMS and DocumentFactory.keys() == DOCUMENTS
    commands = brain.execute("status").data["commands"]
    assert "diagram" in commands and "document" in commands


def test_unknown_names_and_bad_params_fail_naming_the_known_values(brain):
    unknown = brain.execute("diagram", name="dragon")
    assert not unknown.ok and "lifecycle_overview" in unknown.errors[0]
    unknown = brain.execute("document", name="dragon")
    assert not unknown.ok and "safety_plan" in unknown.errors[0]
    bad = brain.execute("diagram", name="lifecycle_overview", param=["colour=red"])
    assert not bad.ok and "colour" in bad.errors[0] and "no parameters" in bad.errors[0]
    bad = brain.execute("diagram", name="phase_flow", param=["phase=42"])
    assert not bad.ok and "1. Concept Development" in bad.errors[0]
    bad = brain.execute("diagram", name="lifecycle_overview", formats="png,gif")
    assert not bad.ok and "gif" in bad.errors[0]


# -- diagrams ---------------------------------------------------------------------
def test_lifecycle_overview_on_empty_database(brain, tmp_path):
    result = brain.execute("diagram", name="lifecycle_overview")
    assert result.ok, result.errors
    data = result.data
    assert data["nodes"] == 10 and data["edges"] == 9 and data["issues"] == [] and result.warnings == []
    assert set(data["paths"]) == FENCE and all(Path(p).is_file() for p in data["paths"].values())
    assert data["primary"].endswith("lifecycle_overview.png") and Path(data["primary"]).parent == tmp_path / "out"
    assert data["kind"] == "diagram" and data["title"] == "Lifecycle overview"


def test_phase_flow_param_forms_and_empty_phase(seeded, tmp_path):
    missing = seeded.execute("diagram", name="phase_flow")
    assert not missing.ok and "phase" in missing.errors[0]
    by_number = seeded.execute("diagram", name="phase_flow", param=["phase=1"], out=str(tmp_path / "a"))
    by_name = seeded.execute(
        "diagram", name="phase_flow", param={"phase": "1. Concept Development"}, out=str(tmp_path / "b")
    )
    assert by_number.ok and by_name.ok, by_number.errors + by_name.errors
    dot_a = Path(by_number.data["paths"]["dot"]).read_text(encoding="utf-8")
    dot_b = Path(by_name.data["paths"]["dot"]).read_text(encoding="utf-8")
    assert dot_a == dot_b and "Verify" in dot_a and "Review" in dot_a
    assert by_number.data["params"] == by_name.data["params"] == {"phase": "1"}
    assert Path(by_number.data["primary"]).name == Path(by_name.data["primary"]).name == "phase_flow_1.png"
    empty = seeded.execute("diagram", name="phase_flow", param=["phase=10"], formats="dot")
    assert empty.ok and empty.data["nodes"] == 2 and empty.data["edges"] == 1
    assert any("no deliverables" in w for w in empty.warnings)
    assert list(empty.data["paths"]) == ["dot"] and empty.data["primary"].endswith(".dot")


def test_status_board_has_six_states_with_matching_counts(seeded):
    diagram = DiagramFactory.build("status_board", seeded, {}, BuildContext(seeded))
    states = [n for n in diagram.nodes.values() if n.kind == "state"]
    assert len(states) == 6
    counts = q.counts_by_status(seeded)
    for node in states:
        status, count = node.label.split("\n")
        assert counts[status] == int(count)
    assert counts["Done"] == 1 and counts["Ongoing"] == 1 and counts["Pending"] == 1 and counts["total"] == 3
    result = seeded.execute("diagram", name="status_board")
    assert result.ok and result.data["nodes"] == 7  # six states plus the start node


def test_pdp_map_and_lifecycle_overview_on_seeded_data(seeded):
    pdp = seeded.execute("diagram", name="pdp_map", formats="png,mmd")
    assert pdp.ok and pdp.data["nodes"] == 7 and pdp.data["edges"] == 6 and pdp.data["issues"] == []
    overview = DiagramFactory.build("lifecycle_overview", seeded, {}, BuildContext(seeded))
    done_phase = overview.nodes["phase_1_concept_development"]
    assert "1 deliverables, 1 done" in done_phase.label and done_phase.fill  # all Done: tinted
    assert overview.nodes["phase_10_decommissioning"].fill is None


def test_layout_issues_become_warnings_not_python_warnings(brain, recwarn):
    import warnings

    from asi_escher import Diagram, LayoutWarning

    from asi_kletz.generate.figures import build_diagram, issue_to_dict

    d = Diagram("Dense", "flowchart")
    for i in range(6):
        d.action(f"n{i}", f"Step {i} with a fairly long label")
    for i in range(6):
        for j in range(6):
            if i != j:
                d.edge(f"n{i}", f"n{j}", f"edge {i}{j}")
    with warnings.catch_warnings():
        warnings.simplefilter("error", LayoutWarning)
        summary = build_diagram(d, brain.out_dir, formats=("dot",))
    for issue in summary["issues"]:
        assert isinstance(issue, dict) and {"kind", "message", "edge", "node"} <= set(issue)
    fake = type("Issue", (), {"kind": "k", "message": "m", "edge": ("a", "b"), "node": None})()
    assert issue_to_dict(fake) == {"kind": "k", "message": "m", "edge": ["a", "b"], "node": None}


# -- documents ----------------------------------------------------------------------
def test_safety_plan_document_on_seeded_database(seeded, tmp_path):
    result = seeded.execute("document", name="safety_plan", actor="agent")
    assert result.ok, result.errors
    data = result.data
    assert set(data["paths"]) == {"md", "pdf", "docx"} and all(Path(p).is_file() for p in data["paths"].values())
    assert data["primary"].endswith(".pdf") and data["primary"] == data["paths"]["pdf"]
    assert data["issues"] == [] and data["pages"] > 1
    md = Path(data["paths"]["md"]).read_text(encoding="utf-8")
    assert "author: agent" in md and "# Platform Safety Plan" in md
    phases_with_rows = [p for p, rows in q.rows_by_phase(seeded).items() if rows]
    assert len(phases_with_rows) == 3
    headings = re.findall(r"^## \d+ Phase (\d+): (.*)$", md, flags=re.M)
    assert len(headings) == 10  # every lifecycle phase has a section
    for phase in phases_with_rows:
        number = q.phase_number(phase)
        assert sum(1 for h in headings if h[0] == number) == 1
        assert f"](figures/phase_flow_{number}.png)" in md
    figures = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md)
    assert len(figures) == 1 + len(phases_with_rows) and figures[0] == "figures/lifecycle_overview.png"
    for relative in figures:
        assert (tmp_path / "out" / relative).is_file()
    assert [d["name"] for d in data["diagrams"]] == [Path(f).stem for f in figures]
    assert all(Path(d["png"]).is_file() and d["issues"] == [] for d in data["diagrams"])
    assert all(Path(d["png"]).parent == tmp_path / "out" / "figures" for d in data["diagrams"])  # rendered by Gutenberg
    assert data["stats"]["figures"] == len(figures)
    assert "## A Roles" in md and "## B QMS and reference legend" in md and "## C Status legend" in md
    assert "FuSa Engineer" in md and "QF-17" in md and "PAT" in md
    assert "kletz.toml has no doc_id" in result.warnings and "kletz.toml has no revisions" in result.warnings


def test_doc_id_from_config_and_warning_without(tmp_path, monkeypatch):
    with _config_brain(tmp_path, monkeypatch, 'doc_id = "ASI-FS-PLAN-001"\nproject = "Wheel Loader"\n') as brain:
        assert brain.doc_id == "ASI-FS-PLAN-001" and brain.project == "Wheel Loader"
        status = brain.execute("status").data
        assert status["doc_id"] == "ASI-FS-PLAN-001" and status["project"] == "Wheel Loader"
        assert status["revisions"] == []
        result = brain.execute("document", name="safety_plan")
        assert result.ok, result.errors
        md = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
        assert "doc_id: ASI-FS-PLAN-001" in md.split("---")[1] and "| Document ID | ASI-FS-PLAN-001 |" in md
        assert "project: Wheel Loader" in md
        assert "kletz.toml has no doc_id" not in result.warnings
        for name in ("status_report", "phase_checklist"):
            other = brain.execute("document", name=name)
            assert other.ok, other.errors
            other_md = Path(other.data["paths"]["md"]).read_text(encoding="utf-8")
            assert "status of ASI-FS-PLAN-001" in other_md and "doc_id:" not in other_md.split("---")[1]
    with _config_brain(tmp_path, monkeypatch, 'db = "cfg.db"\n') as brain:
        assert brain.doc_id == "" and brain.project == ""
        result = brain.execute("document", name="safety_plan")
        assert result.ok and "kletz.toml has no doc_id" in result.warnings


def test_revisions_come_from_config_in_file_order(tmp_path, monkeypatch):
    toml = (
        'doc_id = "ASI-FS-PLAN-001"\n'
        '[[revision]]\nrev = "0.1"\ndate = "2026-10-01"\nauthor = "FuSa Engineer"\ndescription = "Initial draft"\n'
        '[[revision]]\nrev = "0.2"\ndate = "2026-10-27"\nauthor = "FuSa Engineer"\ndescription = "Review comments"\n'
    )
    with _config_brain(tmp_path, monkeypatch, toml) as brain:
        assert [r["rev"] for r in brain.revisions] == ["0.1", "0.2"]
        result = brain.execute("document", name="safety_plan")
        assert result.ok and "kletz.toml has no revisions" not in result.warnings
        md = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
        assert "revision: 0.2" in md.split("---")[1] and "| Revision | 0.2 |" in md
        history = next(rows for caption, rows in _tables(md) if rows[0] == ["Rev", "Date", "Author", "Description"])
        assert history[1:] == [
            ["0.1", "2026-10-01", "FuSa Engineer", "Initial draft"],
            ["0.2", "2026-10-27", "FuSa Engineer", "Review comments"],
        ]
    with _config_brain(tmp_path, monkeypatch, 'doc_id = "X"\n') as brain:
        result = brain.execute("document", name="safety_plan", actor="me")
        assert result.ok and "kletz.toml has no revisions" in result.warnings
        md = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
        history = next(rows for caption, rows in _tables(md) if rows[0] == ["Rev", "Date", "Author", "Description"])
        assert len(history) == 2 and history[1][0] == "0.1"
        assert history[1][2] == "me" and history[1][3] == "Generated draft"
        assert "revision: 0.1" in md.split("---")[1]


def test_per_phase_tables_split_into_deliverables_and_ownership(seeded):
    result = seeded.execute("document", name="safety_plan")
    assert result.ok, result.errors
    md = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
    tables = _tables(md)
    deliverables = {re.search(r"phase (\d+)", c).group(1): rows for c, rows in tables if "Deliverables of phase" in c}
    ownership = {re.search(r"phase (\d+)", c).group(1): rows for c, rows in tables if "Ownership of phase" in c}
    assert set(deliverables) == set(ownership) == {"1", "2", "3"}
    for number in deliverables:
        left, right = deliverables[number], ownership[number]
        assert left[0] == ["Deliverable", "PDP", "Location", "Reference", "Deadline", "Status"]
        assert right[0] == ["Deliverable", "Author", "Verification", "Reviewer"]
        assert [r[0] for r in left[1:]] == [r[0] for r in right[1:]]
    for caption, rows in tables:
        if "of phase" in caption:
            assert all(len(r) <= 6 for r in rows), caption
    phase1 = ownership["1"][1]
    assert phase1[0] == "Safety Plan" and "FuSa Engineer" in phase1[1]
    assert "Level U3" in phase1[2] and "Tech Lead - Functional Safety" in phase1[3]
    assert deliverables["1"][1][2] == "DMS" and deliverables["1"][1][3] == "QF-17" and deliverables["1"][1][5] == "Done"


def test_phase_checklist_ticks_done_rows(seeded):
    result = seeded.execute("document", name="phase_checklist")
    assert result.ok, result.errors
    md = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
    assert "- [x] Safety Plan (Done)" in md
    assert "- [ ] Hazard Analysis and Risk Assessment (Ongoing)" in md
    assert "- [ ] Functional Safety Concept (Pending)" in md
    assert "](figures/pdp_map.png)" in md and "| Total | 3 |" in md


def test_status_report_sections(seeded):
    # the deadline is calculated since 0.11.0: these dates are written the way the tool writes them
    seeded.execute("update", entity=PLAN, id=2, data={"status": "Blocked"})
    seeded.service(PLAN).repo.update(2, {"deadline": "2026-11-05"})
    seeded.service(PLAN).repo.update(3, {"deadline": "31/12/2099"})
    result = seeded.execute("document", name="status_report")
    assert result.ok, result.errors
    md = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
    assert "## 3 Blocked deliverables" in md and "Hazard Analysis and Risk Assessment" in md
    assert "](figures/status_board.png)" in md and "](figures/lifecycle_overview.png)" in md
    assert "## 6 Recent changes" in md and "| update |" in md
    due, undated = q.due_within(q.all_rows(seeded), 30, today=__import__("datetime").date(2026, 10, 27))
    assert [r["id"] for r, _ in due] == [2] and [r["id"] for r in undated] == []
    assert q.parse_deadline("Phase 1 exit") is None and str(q.parse_deadline("31/12/2099")) == "2099-12-31"


def test_locked_pdf_falls_back_to_timestamped_stem(seeded, monkeypatch):
    import asi_gutenberg.pipeline as pipeline

    real = pipeline.render_pdf
    calls: list[str] = []

    def locked_once(doc, path, **kwargs):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("locked")
        return real(doc, path, **kwargs)

    monkeypatch.setattr(pipeline, "render_pdf", locked_once)
    result = seeded.execute("document", name="phase_checklist")
    assert result.ok, result.errors
    stem = Path(result.data["primary"]).stem
    assert stem.startswith("phase_checklist_") and stem != "phase_checklist"
    assert any("locked" in w for w in result.warnings) and len(calls) == 2
    assert Path(result.data["paths"]["md"]).stem == stem and Path(result.data["paths"]["docx"]).is_file()


def test_generate_writes_audit_entry_and_publishes_event(seeded):
    seen: list[tuple[str, dict]] = []
    seeded.events.subscribe("generated", lambda topic, event: seen.append((topic, event)))
    result = seeded.execute("diagram", name="status_board", formats="dot", actor="agent")
    assert result.ok
    entry = seeded.storage.audit_tail(1)[0]
    assert entry["action"] == "generate" and entry["actor"] == "agent" and entry["entity"] == "diagram"
    assert entry["payload"]["name"] == "status_board" and entry["payload"]["primary"].endswith(".dot")
    assert len(seen) == 1 and seen[0][0] == "generated"
    assert seen[0][1]["kind"] == "diagram" and seen[0][1]["name"] == "status_board" and seen[0][1]["actor"] == "agent"
    assert seeded.execute("status").data["recent_events"][-1]["topic"] == "generated"


def test_out_dir_precedence(tmp_path, monkeypatch):
    db = tmp_path / "p.db"
    with Brain(db) as brain:
        assert Path(brain.out_dir) == tmp_path / "out"  # default: out/ next to the database
    with _config_brain(tmp_path, monkeypatch, 'out = "views/plan"\n') as brain:
        pass  # explicit argument wins; the fixture passed out_dir
    monkeypatch.setenv(ENV_CONFIG, str(tmp_path / "kletz.toml"))
    with Brain(db) as brain:
        assert Path(brain.out_dir) == (tmp_path / "views" / "plan").resolve()  # kletz.toml, relative to the file
        assert brain.execute("status").data["out_dir"] == brain.out_dir
    monkeypatch.setenv(ENV_OUT, str(tmp_path / "env-out"))
    with Brain(db) as brain:
        assert Path(brain.out_dir) == tmp_path / "env-out"  # environment beats kletz.toml
        result = brain.execute("diagram", name="status_board", formats="mmd", out=str(tmp_path / "arg-out"))
        assert result.ok and Path(result.data["primary"]).parent == tmp_path / "arg-out"  # --out beats everything
        result = brain.execute("diagram", name="status_board", formats="mmd")
        assert result.ok and Path(result.data["primary"]).parent == tmp_path / "env-out"
    with Brain(db, out_dir=tmp_path / "explicit") as brain:
        assert Path(brain.out_dir) == tmp_path / "explicit"


def test_cli_exit_codes_for_generate_verbs(tmp_path, capsys):
    db = str(tmp_path / "cli.db")

    def run(*argv):
        code = main(["--db", db, "--compact", *argv])
        return code, json.loads(capsys.readouterr().out)

    code, res = run("diagram")
    assert code == 0 and [d["key"] for d in res["data"]["diagrams"]] == DIAGRAMS
    code, res = run("diagram", "nope")
    assert code == 1 and not res["ok"]
    code, res = run("diagram", "phase_flow")
    assert code == 1 and "phase" in res["errors"][0]
    code, res = run("diagram", "phase_flow", "--param", "phase=2", "--formats", "dot,mmd", "--out", str(tmp_path / "o"))
    assert code == 0 and set(res["data"]["paths"]) == {"dot", "mmd"} and res["data"]["params"] == {"phase": "2"}
    code, res = run("document")
    assert code == 0 and [d["key"] for d in res["data"]["documents"]] == DOCUMENTS
    code, res = run("document", "phase_checklist", "--out", str(tmp_path / "o"))
    assert code == 0 and re.search(r"phase_checklist_\d{8}-\d{6}\.pdf$", res["data"]["primary"])
    assert (tmp_path / "o" / "figures" / "pdp_map.png").is_file()
    code, res = run("document", "phase_checklist", "--param", "x=1")
    assert code == 1 and "no parameters" in res["errors"][0]


def test_plan_queries_helpers(seeded):
    rows = q.all_rows(seeded)
    assert [r["order"] for r in rows] == [1, 2, 3]
    assert q.resolve_phase(seeded, "3") == q.resolve_phase(seeded, "3.") == "3. Functional Safety Concept (FSC)"
    assert q.phase_number("10. Decommissioning") == "10" and q.phase_title("10. Decommissioning") == "Decommissioning"
    assert q.set_flags(rows[0], "location") == ["DMS"]
    assert q.set_flags(rows[0], "reviewer") == ["Tech Lead - Functional Safety"]
    assert q.summarise(["a", "b", "c", "d", "e"]) == "a, b, c +2" and q.summarise(["a"]) == "a"
    assert q.describe(rows[2], "work_product_location", "location") == "DMS"
    assert [r["id"] for r in q.open_rows(rows)] == [2, 3] and q.blocked(rows) == []
    by_phase = q.rows_by_phase(seeded, rows)
    assert list(by_phase) == list(seeded.lookups["lifecycle_phase"]) and len(by_phase["10. Decommissioning"]) == 0
    record = q.counts_by_phase(seeded, rows)[0]
    assert record["deliverables"] == 1 and record["done"] == 1 and record["Done"] == 1 and record["Pending"] == 0


# -- independence and laziness ----------------------------------------------------------------
def test_importing_asi_kletz_does_not_import_the_generators():
    code = (
        "import sys, asi_kletz, asi_kletz.brain, asi_kletz.commands, asi_kletz.generate\n"
        "b = asi_kletz.Brain(':memory:'); b.execute('diagram'); b.execute('document')\n"
        "b.execute('schema', entity='jira'); b.close()\n"
        "print(sorted(m.split('.')[0] for m in sys.modules if m.split('.')[0] in "
        "{'matplotlib', 'reportlab', 'docx', 'asi_escher', 'asi_gutenberg', 'PIL', 'asi_hopper'}))\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "[]", proc.stdout + proc.stderr


def test_source_tree_never_mentions_the_sister_tool():
    """Kletz is copied from its sister and then diverges: no import, no shared file, no symlink."""
    forbidden = "asi_" + "dewey"
    hits = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "src").rglob("*")
        if path.is_file() and path.suffix in {".py", ".toml", ".txt", ".md"}
        and forbidden in path.read_text(encoding="utf-8")
    ]
    assert hits == []
    assert not any(p.is_symlink() for p in (REPO_ROOT / "src").rglob("*"))
    for key in ("asi-escher", "asi-gutenberg", "asi-hopper"):
        assert key in (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_database_has_exactly_the_registered_tables_after_generating(seeded):
    assert seeded.execute("document", name="phase_checklist").ok
    tables = seeded.storage.fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    names = {t["name"] for t in tables} - {"schema_migrations", "audit_log"}
    assert names == TABLES


# -- charts and the sprint documents (0.12.0) ----------------------------------------------------------------
ITEM = "sprint_item"


def _sprinted(brain):
    """Sprint 1 closed (8 points done), Sprint 2 active with four items, Sprint 3 planned; a Monday holiday inside 2."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "start": "2026-10-12", "end": "2026-10-27", "capacity": 10,
        "status": "Closed", "closed_on": "2026-10-27",
    }).ok
    assert brain.execute("create", entity=ITEM, data={
        "sprint": 1, "kind": "Other", "title": "Phase 2 wrap-up", "points": 8, "status": "Done",
        "done_on": "2026-10-20",
    }).ok
    assert brain.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-09", "status": "Active", "goal": "Clear the Phase 2 backlog",
    }).ok
    for order, data in enumerate([
        {"kind": "Deliverable", "plan_row": 2, "title": "HARA", "points": 3, "status": "Done", "done_on": "2026-10-29"},
        {"kind": "Deliverable", "plan_row": 3, "title": "FSC", "points": 3, "status": "To Do"},
        {"kind": "Meeting", "title": "Intro meeting", "points": 2, "status": "Done"},
        {"kind": "Other", "title": "Old item", "points": 5, "status": "Carried"},
    ], 1):
        assert brain.execute("create", entity=ITEM, data={"sprint": 2, "order": order, **data}).ok
    assert brain.execute("create", entity="sprint", data={
        "number": 3, "label": "SPRINT 3", "start": "2026-11-10", "end": "2026-11-23", "status": "Planned",
    }).ok
    assert brain.execute("create", entity="holiday", data={"date": "2026-11-02", "name": "Test holiday"}).ok
    return brain


def test_sprint_burndown_chart_from_the_items(seeded, tmp_path):
    _sprinted(seeded)
    chart = DiagramFactory.build("sprint_burndown", seeded, {}, BuildContext(seeded))  # the active sprint
    assert chart.kind == "chart"
    data = chart.data
    assert (data["sprint"], data["capacity"], data["committed"], data["items"]) == (2, 8, 8, 3)  # the Carried 5 is out
    assert len(data["business_days"]) == 9 and data["business_days"][0] == "2026-10-27"  # the holiday took a day
    assert data["remaining"][0] == 6 and data["remaining"][2] == 3 and data["remaining"][-1] == 3  # day one, 10/29
    assert data["ideal"][0] == 8 and data["ideal"][-1] == 0 and len(data["ideal"]) == 9
    assert data["holidays"] == [("2026-11-02", "Test holiday")] and data["undated_done"] == 1
    assert "2026-11-02" in data["gaps"] and "2026-10-31" in data["gaps"] and "2026-10-28" not in data["gaps"]
    result = seeded.execute("diagram", name="sprint_burndown", formats="png,svg")
    assert result.ok, result.errors
    assert set(result.data["paths"]) == {"png", "svg"} and all(Path(p).is_file() for p in result.data["paths"].values())
    assert result.data["primary"].endswith("sprint_burndown_2.png") and result.data["nodes"] == 0
    assert any("without done_on" in w for w in result.warnings)
    first = seeded.execute("diagram", name="sprint_burndown", param=["sprint=1"], formats="png")
    assert first.ok and first.data["primary"].endswith("sprint_burndown_1.png")
    assert first.data["params"] == {"sprint": "1"}
    assert not seeded.execute("diagram", name="sprint_burndown", param=["sprint=9"]).ok
    assert not seeded.execute("diagram", name="sprint_burndown", param=["sprint=two"]).ok
    graph_only = seeded.execute("diagram", name="sprint_burndown", formats="dot")
    assert not graph_only.ok and "writes png, svg only" in graph_only.errors[0]
    mixed = seeded.execute("diagram", name="sprint_burndown", formats="png,dot,mmd")
    assert mixed.ok and list(mixed.data["paths"]) == ["png"]
    assert any("dot, mmd not written" in w for w in mixed.warnings)
    assert not seeded.execute("diagram", name="sprint_burndown", param=["phase=1"]).ok  # not its parameter


def test_velocity_chart_bars_and_mean(seeded):
    empty = seeded.execute("diagram", name="velocity", formats="png")
    assert empty.ok and any("no Closed sprint" in w for w in empty.warnings) and empty.data["nodes"] == 0
    assert DiagramFactory.build("velocity", seeded, {}, BuildContext(seeded)).data["sprints"] == []
    _sprinted(seeded)
    data = DiagramFactory.build("velocity", seeded, {}, BuildContext(seeded)).data
    assert data["sprints"] == [1] and data["done"] == [8] and data["mean"] == [8.0] and data["capacity"] == [10]
    assert seeded.execute("sprint", action="close", as_of="2026-11-09").ok  # 3 + 2 done; the rest carried into 3
    data = DiagramFactory.build("velocity", seeded, {}, BuildContext(seeded)).data
    assert data["sprints"] == [1, 2] and data["done"] == [8, 5] and data["mean"] == [8.0, 6.5]
    assert data["labels"] == ["SPRINT 1", "SPRINT 2"] and data["capacity"] == [10, 8]
    result = seeded.execute("diagram", name="velocity", formats="png,svg")
    assert result.ok and result.warnings == [] and Path(result.data["primary"]).name == "velocity.png"


def test_plan_roadmap_chart_from_the_scheduler(seeded):
    from tests.conftest import SEED_WEIGHTS

    _sprinted(seeded)
    assert seeded.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS)).ok
    chart = DiagramFactory.build("plan_roadmap", seeded, {}, BuildContext(seeded))
    data = chart.data
    assert [c["number"] for c in data["columns"]] == [2]  # both open rows finish where their items are
    assert data["columns"][0]["holidays"] == ["Test holiday"]
    rows = {r["id"]: r for r in data["rows"]}
    assert rows[1]["status"] == "Done" and rows[1]["occupied"] == [] and rows[1]["sprint"] is None
    assert (rows[2]["weight"], rows[2]["committed"], rows[2]["sprint"], rows[2]["occupied"]) == (3, 3, 2, [2])
    assert (rows[3]["weight"], rows[3]["committed"], rows[3]["sprint"], rows[3]["occupied"]) == (2, 3, 2, [2])
    assert (rows[2]["start"], rows[2]["end"], rows[2]["deadline"]) == ("2026-10-27", "2026-11-09", "2026-11-09")
    assert data["total_points"] == 5 and data["completion"] == {"sprint": 2, "date": "2026-11-09"}
    assert data["unscheduled"] == [] and data["warnings"] == []
    # 12 points on row 3: 9 left after its item, Sprint 2 is full, Sprint 3 holds 8, the chain ends
    assert seeded.execute("update", entity=PLAN, id=3, set=["points=12"]).ok
    data = DiagramFactory.build("plan_roadmap", seeded, {}, BuildContext(seeded)).data
    assert [c["number"] for c in data["columns"]] == [2] and data["unscheduled"] == [3]
    assert data["rows"][2]["sprint"] is None and data["rows"][2]["occupied"] == [2, 3]
    assert data["total_points"] == 15 and "run sprint plan" in data["warnings"][0]
    result = seeded.execute("diagram", name="plan_roadmap", formats="png")
    assert result.ok and Path(result.data["primary"]).name == "plan_roadmap.png"
    assert any("run sprint plan" in w for w in result.warnings)
    assert seeded.execute("sprint", action="plan", until="2026-12-31").ok  # the chain reaches it now
    data = DiagramFactory.build("plan_roadmap", seeded, {}, BuildContext(seeded)).data
    assert data["unscheduled"] == [] and data["rows"][2]["sprint"] == 4 and data["rows"][2]["occupied"] == [2, 3, 4]
    assert [c["number"] for c in data["columns"]] == [2, 3, 4]


def test_sprint_report_document(seeded, tmp_path):
    _sprinted(seeded)
    result = seeded.execute("document", name="sprint_report")
    assert result.ok, result.errors
    data = result.data
    assert data["params"] == {"sprint": "2"} and data["title"] == "Sprint Report: SPRINT 2"
    assert set(data["paths"]) == {"md", "pdf", "docx"} and all(Path(p).is_file() for p in data["paths"].values())
    out = Path(data["out_dir"])
    assert (out / "figures" / "sprint_burndown_2.png").is_file() and (out / "figures" / "velocity.png").is_file()
    text = Path(data["paths"]["md"]).read_text(encoding="utf-8")
    for needle in ("Clear the Phase 2 backlog", "figures/sprint_burndown_2.png", "figures/velocity.png",
                   "Carried out of SPRINT 2", "Old item", "Test holiday", "Intro meeting", "8 points"):
        assert needle in text, needle
    tables = dict(_tables(text))
    board = next(rows for caption, rows in tables.items() if "board" in caption)
    assert [r[0] for r in board[1:]] == ["To Do", "Done", "Done", "Carried"]  # status order, then order
    assert any("without done_on" in w for w in result.warnings)
    first = seeded.execute("document", name="sprint_report", param=["sprint=1"])
    assert first.ok and first.data["params"] == {"sprint": "1"} and "No item was carried" in Path(
        first.data["paths"]["md"]).read_text(encoding="utf-8")
    assert not seeded.execute("document", name="sprint_report", param=["sprint=9"]).ok
    assert seeded.execute("delete", entity="sprint", id=2).ok and seeded.execute("delete", entity="sprint", id=3).ok
    assert not seeded.execute("document", name="sprint_report").ok  # no active sprint and none named


def test_plan_roadmap_document(seeded):
    from tests.conftest import SEED_WEIGHTS

    _sprinted(seeded)
    assert seeded.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS)).ok
    result = seeded.execute("document", name="plan_roadmap")
    assert result.ok, result.errors
    text = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
    assert result.data["title"] == "Safety Plan Roadmap"
    assert (Path(result.data["out_dir"]) / "figures" / "plan_roadmap.png").is_file()
    for needle in ("a sprint is 14 calendar days, Tuesday to the Monday 13", "figures/plan_roadmap.png",
                   "Phase 1: Concept Development",
                   "Phase 3: Functional Safety Concept", "Sprint 2 (2026-11-09)", "Test holiday", "5"):
        assert needle in text, needle
    assert "Not scheduled" not in text
    tables = dict(_tables(text))
    phase_three = next(rows for caption, rows in tables.items() if "Phase 3" in caption)
    assert phase_three[0] == ["Deliverable", "Points", "Sprint", "Start", "End", "Status"]
    assert phase_three[1][1:] == ["2", "2", "2026-10-27", "2026-11-09", "Pending"]
    assert seeded.execute("update", entity=PLAN, id=3, set=["points=12"]).ok
    result = seeded.execute("document", name="plan_roadmap")
    text = Path(result.data["paths"]["md"]).read_text(encoding="utf-8")
    assert "Not scheduled" in text and "Functional Safety Concept" in text.split("Not scheduled")[1]
    assert any("run sprint plan" in w for w in result.warnings)
