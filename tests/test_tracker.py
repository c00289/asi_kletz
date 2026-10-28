"""The Weekly Activity Tracker: the grammar, the import of the real file, the round trip, the two builds, Jira.

The fixture is the engineer's tracker of 2026-10-28 with the byline replaced by the role. It is the
specification: an import followed by a history build must give it back, line for line.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from asi_kletz import Brain
from asi_kletz.brain import ENV_CONFIG
from asi_kletz.errors import CommandError
from asi_kletz.tracker import Item, ParseError, Sprint, Tracker, Week, parse, render
from asi_kletz.tracker import format as fmt
from tests.conftest import PLAN, REPO_ROOT, TABLES

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "tracker_2026-10-28.txt"
AS_OF = "2026-10-28"
BYLINE = "FuSa Engineer"
SCOPE = "platform functional safety for the Wheel Loader programme (project HWL)."
PLAN_ROWS = [
    "Safety Plan", "SCOPE Definition Report", "System Functions, Functional Architecture and its Interfaces",
    "ConOps / Use Case specification", "TOD/PRD document", "Activity Flow",
    "Preliminary Hazard List (STPA Step 1 outputs -losses, hazards, constraints)", "STPA step 2",
    "HARA report with MPLr/PLr assignments",
]
HEADER = "Title\nR. Newest week at the top. Last updated 10/28/2026.\n\nTIMELINE\n\n"
JIRA_KEYS = ["HWL-2554", "HWL-2553", "HWL-2572", "HWL-2573", "HWL-2574", "HWL-2575", "HWL-2620", "HWL-2652"]


@pytest.fixture
def configured(tmp_path, monkeypatch):
    """A Brain whose kletz.toml carries the byline and scope of the fixture, with the nine Phase 1 and 2 plan rows."""
    config = tmp_path / "kletz.toml"
    config.write_text(f'tracker_byline = "{BYLINE}"\ntracker_scope = "{SCOPE}"\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "t.db", workbook_path=tmp_path / "v.xlsx", out_dir=tmp_path / "out") as b:
        for order, deliverable in enumerate(PLAN_ROWS, 1):
            phase = "1. Concept Development" if order <= 7 else "2. HARA / Risk Assessment"
            row = {"order": order, "lifecycle_phase": phase, "deliverable": deliverable}
            b.execute("create", entity=PLAN, data=row)
        yield b


@pytest.fixture
def imported(configured):
    result = configured.execute("tracker", action="import", what=str(FIXTURE))
    assert result.ok, result.errors
    return configured


def _read(result) -> str:
    assert result.ok, result.errors
    return Path(result.data["path"]).read_text(encoding="utf-8")


# -- grammar ------------------------------------------------------------------------------------
def _built_tracker() -> Tracker:
    day = dt.date(2026, 11, 10)
    closed = Sprint("2", "HARA / Risk Assessment", "FINAL SPRINTS", dt.date(2026, 10, 12), dt.date(2026, 10, 27),
                    "Closed", closed_on=dt.date(2026, 10, 27), number=1)
    closed.weeks.append(Week(dt.date(2026, 10, 19), outcomes="- Done a thing.\n- Done another."))
    frozen = "Jira issues (project HWL, as of 10/18)\n\n  HWL-1  Bug    Old\n            Note: gone"
    closed.weeks.append(Week(dt.date(2026, 10, 12), outcomes="- Started.", jira_frozen=frozen))
    active = Sprint("3", "Functional Safety Concept (FSC)", "SPRINT 1", dt.date(2026, 10, 27), day, "Active",
                    goal="Clear the Phase 2 backlog", number=2)
    issues = "Phase 1 - Concept Development\n- Safety Plan: in work. Sprint 1 target: dated.\n  wrapped line"
    active.weeks.append(Week(dt.date(2026, 10, 26), note="Phase 3 opened 10/27", outcomes="- Opened.", issues=issues))
    active.weeks.append(Week(dt.date(2026, 11, 2), outcomes="- Week two."))
    active.items = [
        Item("HWL-2554", "Story", "Perform Platform Safety Plan", "In Progress | Priority: High | Assignee: X",
             note="Ready soon.", target="dated and baselined.", points=3,
             heading="Epic HWL-1915 \"Closeout\"\n(two lines)"),
        Item("HWL-2620", "Bug", "Control room E-stop has no actuator guard; confirm guard\ntest case (01-006)",
             "To Do | Priority: High | Assignee: Y", note="no FuSa impact\nsecond note line",
             target="followed to closure.", heading="Watched"),
        Item("HWL-2652", "Task", "Review L0 test dependencies", None, heading="Watched"),
    ]
    planned = Sprint("3", "Functional Safety Concept (FSC)", "SPRINT 2", day, dt.date(2026, 11, 24), "Planned",
                     number=3)
    return Tracker("TITLE", "Role", "the scope", "project HWL, mine", sprints=[closed, active, planned])


def test_render_then_parse_then_render_is_stable():
    tracker = _built_tracker()
    text = render(tracker, dt.date(2026, 11, 3))
    again = parse(text)
    assert render(again, dt.date(2026, 11, 3)) == text
    assert [s.label for s in again.sprints] == ["SPRINT 2", "SPRINT 1", "FINAL SPRINTS"]  # file order: newest first
    active = again.sprints[1]
    assert active.goal == "Clear the Phase 2 backlog" and active.status == "Active"
    assert [i.key for i in active.items] == ["HWL-2554", "HWL-2620", "HWL-2652"]
    assert active.items[1].title.count("\n") == 1 and active.items[1].note == "no FuSa impact\nsecond note line"
    # a heading prints once per run of items, so after a parse only the first item of the run carries it
    assert active.items[0].points == 3 and active.items[1].heading == "Watched" and active.items[2].heading is None
    week = next(w for w in active.weeks if w.start == dt.date(2026, 10, 26))
    assert week.note == "Phase 3 opened 10/27" and week.issues.startswith("Phase 1 - Concept Development")
    assert [(t.title, t.target) for t in week.targets] == [("Safety Plan", "dated. wrapped line")]
    frozen = next(w for w in again.sprints[2].weeks if w.start == dt.date(2026, 10, 12))
    assert frozen.jira_frozen.startswith("Jira issues (project HWL, as of 10/18)")
    assert "- Phase 3 (Functional Safety Concept): planned. Sprint 2: 11/10 - 11/24." in text
    assert "- Phase 3 (Functional Safety Concept): opened 10/27/2026. Sprint 1: 10/27 - 11/10." in text
    assert "Outcomes so far\n- Week two." in text and "Outcomes\n- Opened." in text  # the current week, then history


def test_render_week_only_holds_the_active_sprint_and_its_current_week():
    text = render(_built_tracker(), dt.date(2026, 11, 3), current_only=True)
    assert "PHASE 3 - SPRINT 1" in text and "FINAL SPRINTS" not in text.split("TIMELINE")[1].split("=====")[1]
    assert text.count("WEEK OF") == 1 and "WEEK OF 11/02 - 11/08" in text and "HWL-2554" in text


def test_empty_tracker_renders_the_header_only():
    header = "T\nR. Newest week at the top. Last updated 10/28/2026.\n\nTIMELINE\n"
    assert render(Tracker("T", "R"), dt.date(2026, 10, 28)) == header


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("Title\nno byline here\n", "line 2"),
        ("Title\nR. Newest week at the top. Last updated 10/28/2026.\n\nnothing\n", "no TIMELINE"),
        (HEADER + fmt.RULE + "\nPHASE X\n" + fmt.RULE + "\n", "line 7"),
        (HEADER + fmt.RULE + "\nPHASE 3 - SPRINT 1 (10/27 - 11/10)   [paused]\n" + fmt.RULE + "\n",
         "unknown sprint status"),
        (HEADER + fmt.RULE + "\nPHASE 3 - SPRINT 1 (10/27 - 11/10)   [in progress]\n" + fmt.RULE
         + "\n\nWEEK OF 10/26 - 11/01\n\nstray text\n", "line 12"),
    ],
)
def test_parse_errors_name_the_line(text, message):
    with pytest.raises(ParseError, match=message):
        parse(text)


def test_year_wraps_at_new_year():
    text = (HEADER.replace("10/28/2026", "01/05/2027") + fmt.RULE
            + "\nPHASE 3 - SPRINT 5 (12/22 - 01/05)   [in progress]\n" + fmt.RULE
            + "\n\nWEEK OF 01/03 - 01/09\n\nOutcomes\n- x\n")
    sprint = parse(text).sprints[0]
    assert (sprint.start, sprint.end) == (dt.date(2026, 12, 22), dt.date(2027, 1, 5))
    assert sprint.weeks[0].start == dt.date(2027, 1, 3)


# -- import of the real file ------------------------------------------------------------------
def test_import_the_real_file(imported):
    brain = imported
    sprints = brain.execute("list", entity="sprint").data
    assert [(s["number"], s["label"], s["status"], s["start"], s["end"], s["closed_on"]) for s in sprints] == [
        (1, "FINAL SPRINTS", "Closed", "2026-10-12", "2026-10-27", "2026-10-27"),
        (2, "SPRINT 1", "Active", "2026-10-27", "2026-11-10", None),
    ]
    assert sprints[1]["lifecycle_phase"] == "3. Functional Safety Concept (FSC)" and sprints[1]["capacity"] == 10
    items = brain.execute("list", entity="sprint_item").data
    assert all(i["sprint"] == 2 and i["status"] == "To Do" and i["points"] is None for i in items)
    assert [i["jira_key"] for i in items if i["kind"] == "Jira"] == JIRA_KEYS
    assert [i["plan_row"] for i in items if i["kind"] == "Deliverable"] == [1, 4, 6, 7]
    assert [i["title"] for i in items if i["kind"] == "Meeting"] == ["Introduction meeting with Rod DeMay"]
    assert [i["note"] for i in items if i["kind"] == "Question"] == [
        "System Functions, Functional Architecture and its Interfaces", "TOD/PRD document",
    ]
    bug = next(i for i in items if i["jira_key"] == "HWL-2620")
    assert bug["issue_type"] == "Bug" and bug["title"].count("\n") == 1 and bug["note"] == "no FuSa impact"
    assert bug["heading"] == "Watched, assigned to Matt Whale" and bug["target"] == "followed to closure."
    first = next(i for i in items if i["jira_key"] == "HWL-2554")
    assert first["heading"].startswith('Epic HWL-1915 "MVP3 - PDP Phase 3 Closeout"') and "\n" in first["heading"]
    assert first["jira_line"] == "In Progress | Priority: Un-Groomed | Assignee: Roy Mendoza"
    weeks = brain.execute("list", entity="week").data
    assert [(w["start"], w["sprint"], w["section"]) for w in weeks] == [
        ("2026-10-12", 1, "Outcomes"), ("2026-10-19", 1, "Outcomes"),
        ("2026-10-26", 2, "Note"), ("2026-10-26", 2, "Outcomes"), ("2026-10-26", 2, "Issues"),
    ]
    assert weeks[2]["text"] == "Phase 2 closed 10/27; Phase 3 Sprint 1 opened 10/27"
    assert weeks[4]["text"].startswith("Platform Safety Plan deliverables, where each stands (10/28)")
    assert brain.storage.audit_tail(1)[0]["action"] == "load:replace"


def test_second_import_is_unchanged_and_merge_adds_only_what_is_new(imported, tmp_path):
    before = imported.storage.audit_tail(50)
    again = imported.execute("tracker", action="import", what=str(FIXTURE))
    assert again.ok and again.data["unchanged"] is True and again.data["mode"] == "merge"
    assert imported.storage.audit_tail(50) == before
    extra = FIXTURE.read_text(encoding="utf-8").replace(
        "WEEK OF 10/26 - 11/01", "WEEK OF 11/02 - 11/08\n\nOutcomes so far\n- A new week.\n\nWEEK OF 10/26 - 11/01", 1
    )
    (tmp_path / "next.txt").write_text(extra, encoding="utf-8")
    merged = imported.execute("tracker", action="import", what=str(tmp_path / "next.txt"))
    assert merged.ok and merged.data["entities"]["week"] == {"created": 1, "updated": 0, "unchanged": 5}
    assert merged.data["entities"]["sprint"]["created"] == 0 and merged.data["entities"]["sprint_item"]["created"] == 0


def test_import_reports_what_kletz_toml_should_carry(brain):
    result = brain.execute("tracker", action="import", what=str(FIXTURE))
    assert result.ok and any("tracker_scope" in w for w in result.warnings)
    assert all(i["kind"] != "Deliverable" for i in brain.execute("list", entity="sprint_item").data)  # no plan rows
    assert sum("imported as Other" in w for w in result.warnings) == 4
    assert not brain.execute("tracker", action="import", what=str(brain.db_path) + ".missing").ok


# -- round trip --------------------------------------------------------------------------------
def test_history_build_gives_the_file_back(imported):
    result = imported.execute("tracker", action="build", what="history", as_of=AS_OF)
    text = _read(result)
    assert text == FIXTURE.read_text(encoding="utf-8")
    assert Path(result.data["path"]).read_bytes() == FIXTURE.read_bytes()  # LF endings, whatever the platform
    tail = imported.storage.audit_tail(1)[0]
    assert tail["action"] == "generate" and tail["payload"]["name"] == "tracker_history"


def test_week_build_is_the_current_week_of_the_active_sprint(imported):
    result = imported.execute("tracker", action="build", what="week", as_of=AS_OF)
    text = _read(result)
    assert text == "\n".join(FIXTURE.read_text(encoding="utf-8").splitlines()[:112]) + "\n"
    assert result.data["sprint"] == 2 and result.data["week"] == "2026-10-26"
    assert result.data["path"].endswith("tracker_week.txt")
    assert text.count("WEEK OF") == 1 and "FINAL SPRINTS" not in text.split("TIMELINE")[1].split(fmt.RULE)[1]


def test_build_without_an_active_sprint_or_week_fails_cleanly(configured):
    assert not configured.execute("tracker", action="build", what="week").ok
    history = configured.execute("tracker", action="build", what="history", as_of=AS_OF)
    assert history.ok and _read(history).endswith("TIMELINE\n- Scope: " + SCOPE + "\n")
    assert not configured.execute("tracker", action="build", what="monthly").ok


def test_points_show_on_the_sprint_line_and_under_the_item(imported):
    items = imported.execute("list", entity="sprint_item", filter=["jira_key=HWL-2554"]).data
    pointed = imported.execute("sprint", action="point", item=items[0]["id"], points=3)
    assert pointed.ok and pointed.data["points"] == 3 and any("unpointed" in w for w in pointed.warnings)
    text = _read(imported.execute("tracker", action="build", what="week", as_of=AS_OF))
    lines = text.splitlines()
    # the imported Phase 2 sprint is closed with nothing done, so the velocity is 0, honestly
    assert lines[11] == (
        "Sprint: 3 of 10 points committed, 0 done, 3 to go, 14 unpointed, 13 days left; velocity 0 points per sprint."
    )
    detail = "            Sprint 1 target: dates added to every deliverable; plan baselined.\n            Points: 3\n"
    assert detail in text


def test_add_appends_to_the_current_week_and_opens_a_new_one(imported):
    added = imported.execute("tracker", action="add", what="- Mentor meeting held.", as_of=AS_OF)
    assert added.ok and added.data["section"] == "Outcomes" and added.data["text"].endswith("\n- Mentor meeting held.")
    text = _read(imported.execute("tracker", action="build", what="week", as_of=AS_OF))
    assert "- Mentor meeting held.\n\nMiscellaneous issues" in text
    later = imported.execute("tracker", action="add", what="- New week.", as_of="2026-11-04", section="Issues")
    assert later.ok and later.data["start"] == "2026-11-02" and later.data["sprint"] == 2  # weeks start on Monday
    text = _read(imported.execute("tracker", action="build", what="week", as_of="2026-11-04"))
    assert "WEEK OF 11/02 - 11/08" in text and "Miscellaneous issues\n\n  - New week." in text and "HWL-2554" in text
    assert not imported.execute("tracker", action="add", what="   ").ok
    assert not imported.execute("tracker", action="add", what="x", section="Jira").ok


# -- jira -------------------------------------------------------------------------------------------
def test_build_with_jira_refreshes_the_lines_from_a_live_fetch(imported, monkeypatch):
    calls: list[tuple[str, int]] = []

    def fake_live(jql, limit=2000, **kwargs):
        calls.append((jql, limit))
        return {"jql": jql, "fetched_at": "now", "count": 1, "truncated": False, "issues": [
            {"key": "HWL-2554", "issue_type": "Story", "summary": "Perform Platform Safety Plan", "status": "Done",
             "priority": "High", "assignee": "FuSa Engineer"},
        ]}

    monkeypatch.setattr(imported.jira, "live", fake_live)
    result = imported.execute("tracker", action="build", what="history", as_of=AS_OF, jira=True)
    assert result.ok and result.data["jira_refreshed"] is True
    assert calls and calls[0][0].startswith("key in (HWL-2553, HWL-2554") and calls[0][1] == 9
    assert sum("not returned by Jira" in w for w in result.warnings) == 7
    text = _read(result)
    assert "            Jira status: Done | Priority: High | Assignee: FuSa Engineer" in text
    row = imported.execute("list", entity="sprint_item", filter=["jira_key=HWL-2554"]).data[0]
    assert row["jira_line"].startswith("Done |") and row["issue_type"] == "Story"


def test_build_with_jira_and_no_jira_still_builds(imported, monkeypatch):
    def refuse(*args, **kwargs):
        raise CommandError("no Atlassian session for this account; run `asi-hopper auth login` once")

    monkeypatch.setattr(imported.jira, "live", refuse)
    result = imported.execute("tracker", action="build", what="history", as_of=AS_OF, jira=True)
    assert result.ok and any("Jira not fetched" in w for w in result.warnings)
    assert _read(result) == FIXTURE.read_text(encoding="utf-8")


def test_jira_live_is_never_called_without_the_flag(imported, monkeypatch):
    monkeypatch.setattr(imported.jira, "live", lambda *a, **k: pytest.fail("jira live was called"))
    assert imported.execute("tracker", action="build", what="history", as_of=AS_OF).ok


# -- the one-table rule is retired --------------------------------------------------------------------
def test_tracker_tables_are_the_registered_ones_and_the_plan_is_untouched(imported):
    tables = imported.storage.fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    assert {t["name"] for t in tables} - {"schema_migrations", "audit_log"} == TABLES
    assert imported.execute("count", entity=PLAN).data["count"] == len(PLAN_ROWS)
    assert all(r["status"] is None for r in imported.execute("list", entity=PLAN).data)
