"""The standards (asi_standards) and the export of a Safety Plan row into one: the folder scan, the match by
QMS reference flag, the parameter entity, the value set (points chosen, never the default; the sprint end;
the Jira status through a stub Hopper) and the asi_gutenberg build with its marks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from asi_kletz.errors import CommandError
from asi_kletz.services.standards_service import folder_names, qms_slug
from tests.conftest import PLAN, SEED_WEIGHTS

SOURCE = """---
title: "{{ vehicle_type }} Safety Plan (test)"
kind: plan
doc_id: QF-17
---
# {{ vehicle_type }} Safety Plan (test)

Author: {{ fusa_engineer }}

| Deliverable | Expected Duration/Deadline | Status |
| :--- | :--- | :--- |
| Safety Plan | {{ row_1_points }} points<br>{{ row_1_sprint_end }} | {{ row_1_status }} |
| HARA | {{ row_2_points }} points<br>{{ row_2_sprint_end }} | {{ row_2_status }} |
"""


class StubHopper:
    """``get(key)`` answers a status per key; a failure is raised on the first read."""

    def __init__(self, statuses: dict[str, str], fail: Exception | None = None) -> None:
        self.statuses = statuses
        self.fail = fail
        self.calls: list[str] = []
        self.closed = False

    def get(self, key: str, *, comments: bool = False) -> SimpleNamespace:
        self.calls.append(key)
        if self.fail is not None:
            raise self.fail
        return SimpleNamespace(key=key, status=self.statuses[key], summary=key)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def standards(tmp_path, monkeypatch):
    """A standards directory with one standard, ``qf-17-test``, and a folder that is not one."""
    root = tmp_path / "standards"
    (root / "qf-17-test").mkdir(parents=True)
    (root / "qf-17-test" / "qf-17-test.md").write_text(SOURCE, encoding="utf-8")
    (root / "notes").mkdir()
    (root / "notes" / "other.md").write_text("# not a standard\n", encoding="utf-8")
    monkeypatch.setenv("ASI_KLETZ_STANDARDS", str(root))
    return root


def _stub(brain, monkeypatch, statuses, fail=None) -> StubHopper:
    stub = StubHopper(statuses, fail)
    monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)
    return stub


def test_standards_list_reads_the_folder(seeded, standards):
    assert seeded.standards_dir == str(standards)
    result = seeded.execute("standards", action="list")
    assert result.ok, result.errors
    assert result.data["standards_dir"] == str(standards)
    [std] = result.data["standards"]
    assert std["folder"] == "qf-17-test" and std["title"] == "{{ vehicle_type }} Safety Plan (test)"
    assert std["document_parameters"] == ["fusa_engineer", "vehicle_type"] and std["row_parameters"] == 6
    assert std["parameters"] == 8 and Path(std["path"]).name == "qf-17-test.md"
    assert qms_slug("ref_qf_17") == "qf_17" and folder_names("qf-17-safety-plan", "qf_17")
    assert folder_names("QF-17", "qf_17") and not folder_names("qf-170-x", "qf_17")
    assert not folder_names("qp-17", "qf_17")


def test_a_row_has_the_standards_its_qms_flags_name(seeded, standards):
    with_flag = seeded.execute("standards", action="for", row=1)  # ref_qf_17 is set on the seeded row 1
    assert with_flag.ok and [s["folder"] for s in with_flag.data["standards"]] == ["qf-17-test"]
    without = seeded.execute("standards", action="for", row=3)
    assert without.ok and without.data["standards"] == [] and without.data["order"] == 3
    assert not seeded.execute("standards", action="for").ok
    assert not seeded.execute("standards", action="for", row=99).ok
    assert seeded.execute("update", entity=PLAN, id=3, set=["ref_qf_17=1"]).ok
    assert [s["folder"] for s in seeded.execute("standards", action="for", row=3).data["standards"]] == ["qf-17-test"]


def test_no_standards_dir_lists_nothing(seeded, tmp_path, monkeypatch):
    monkeypatch.setenv("ASI_KLETZ_STANDARDS", str(tmp_path / "nowhere"))
    assert seeded.execute("standards", action="list").data["standards"] == []
    refused = seeded.execute("plan", action="export", row=1, out=str(tmp_path / "out"))
    assert not refused.ok and "No standard for this deliverable" in refused.errors[0]


def test_parameter_rows_are_unique_per_standard(seeded):
    assert seeded.execute("create", entity="parameter", data={"name": "vehicle_type", "value": "Wheel Loader"}).ok
    again = seeded.execute("create", entity="parameter", data={"name": "vehicle_type", "value": "x"})
    assert not again.ok and "already exists for every standard" in again.errors[0]
    own = seeded.execute("create", entity="parameter", data={
        "name": "vehicle_type", "standard": "qf-17-test", "value": "Loader",
    })
    assert own.ok and own.data["standard"] == "qf-17-test"
    assert not seeded.execute("create", entity="parameter", data={"name": "Vehicle Type", "value": "x"}).ok
    assert not seeded.execute("create", entity="parameter", data={"value": "x"}).ok  # a name is required
    assert seeded.execute("update", entity="parameter", id=own.data["id"], set=["value=Dozer"]).ok


def test_export_fills_the_document_and_the_row_values(seeded, standards, tmp_path, monkeypatch):
    assert seeded.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS)).ok  # defaults: never used
    assert seeded.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "start": "2026-10-27", "end": "2026-11-09", "status": "Active",
    }).ok
    for data in (
        {"name": "vehicle_type", "value": "Wheel Loader"},
        {"name": "fusa_engineer", "value": "the FuSa engineer"},
        {"name": "fusa_engineer", "standard": "qf-17-test", "value": "the contractor"},  # the standard's own wins
    ):
        assert seeded.execute("create", entity="parameter", data=data).ok
    assert seeded.execute("update", entity=PLAN, id=1, set=["status=Ongoing", "jira_key=hwl-2554", "points=5"]).ok
    assert seeded.execute("update", entity=PLAN, id=2, set=["ref_qf_17=1"]).ok  # a default of 3, no points chosen
    stub = _stub(seeded, monkeypatch, {"HWL-2554": "In Progress"})
    preview = seeded.execute("plan", action="parameters", row=1)
    assert preview.ok, preview.errors
    [std] = preview.data["standards"]
    assert std["values"] == {
        "vehicle_type": "Wheel Loader", "fusa_engineer": "the contractor",
        "row_1_points": "5", "row_1_sprint_end": "2026-11-09", "row_1_status": "In Progress",
        "row_2_points": "3", "row_2_sprint_end": "2026-11-09",  # row 2: the panel's default, the weight used
    }
    assert std["filled"] == 7 and std["unfilled"] == ["row_2_status"]
    assert preview.data["statuses"] == {"HWL-2554": "In Progress"} and stub.calls == ["HWL-2554"] and stub.closed
    assert any("row(s) 2, 3 have no Jira key" in w for w in preview.warnings)

    out = tmp_path / "out"
    result = seeded.execute("plan", action="export", row=1, out=str(out), actor="me")
    assert result.ok, result.errors
    [built] = result.data["exports"]
    assert built["standard"] == "qf-17-test" and built["filled"] == 7
    assert built["unfilled"] == ["row_2_status"]
    assert set(built["files"]) == {"md", "pdf", "docx"} and all(Path(p).is_file() for p in built["files"].values())
    assert Path(built["primary"]).name == "qf-17-test.pdf" and built["pages"]
    text = Path(built["files"]["md"]).read_text(encoding="utf-8")
    for mark in ("==Wheel Loader==", "==the contractor==", "==5== points", "==2026-11-09==", "==In Progress==",
                 "==3== points"):
        assert mark in text, mark
    assert "{{ row_2_points }}" not in text and "{{ row_2_status }}" in text  # the default is the weight used
    assert any("unfilled parameter row_2_status" in w for w in result.warnings)
    entry = seeded.storage.audit_tail(1)[0]
    assert entry["action"] == "export" and entry["actor"] == "me" and entry["payload"]["standards"] == ["qf-17-test"]
    assert seeded.events.last(1)[0]["topic"] == "plan.exported"
    assert stub.calls == ["HWL-2554", "HWL-2554"]  # one read per distinct key per call, not per row

    # a named standard; an unknown one; a row without a standard
    assert seeded.execute("plan", action="export", row=1, out=str(out), standard="qf-17-test").ok
    assert not seeded.execute("plan", action="export", row=1, out=str(out), standard="qf-99").ok
    assert not seeded.execute("plan", action="export", row=3, out=str(out)).ok
    assert not seeded.execute("plan", action="export", out=str(out)).ok  # needs --row


def test_export_offline_leaves_the_status_unfilled_with_one_warning(seeded, standards, tmp_path, monkeypatch):
    from asi_hopper.errors import AuthRequired

    assert seeded.execute("update", entity=PLAN, id=1, set=["jira_key=HWL-2554"]).ok
    stub = _stub(seeded, monkeypatch, {}, fail=AuthRequired("no Atlassian session"))
    result = seeded.execute("plan", action="export", row=1, out=str(tmp_path / "out"))
    assert result.ok, result.errors
    assert stub.calls == ["HWL-2554"]
    assert sum("Jira statuses skipped" in w for w in result.warnings) == 1
    assert any("no Atlassian session" in w and "HWL-2554" in w for w in result.warnings)
    [built] = result.data["exports"]
    assert "row_1_status" in built["unfilled"] and "{{ row_1_status }}" in Path(built["files"]["md"]).read_text(
        encoding="utf-8")


def test_export_default_out_is_the_config_out(seeded, standards):
    result = seeded.execute("plan", action="export", row=1)
    assert result.ok and result.data["out_dir"] == seeded.out_dir
    assert Path(seeded.out_dir, "qf-17-test.pdf").is_file()
    with pytest.raises(CommandError):
        seeded.standards.value_set(3)


def test_the_points_printed_are_the_weight_the_schedule_used(seeded, standards, tmp_path):
    """The owner's revision, 2026-10-29: `{{ row_11_points }} points` over a sprint end the scheduler computed
    at the default is wrong; the two lines must agree. Chosen points, else the default, else unfilled."""
    assert seeded.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "start": "2026-10-27", "end": "2026-11-09", "status": "Active",
    }).ok
    assert seeded.execute("update", entity=PLAN, id=2, set=["ref_qf_17=1", "points=5"]).ok  # chosen
    assert seeded.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS)).ok  # row 3: default 2
    assert seeded.execute("create", entity=PLAN, data={"deliverable": "Neither", "order": 4}).ok  # the floor
    schedule = {r["order"]: r for r in seeded.execute("plan", action="schedule").data["rows"]}
    assert (schedule[2]["weight"], schedule[2]["source"]) == (5, "points")
    assert (schedule[3]["weight"], schedule[3]["source"]) == (2, "default")
    assert (schedule[4]["weight"], schedule[4]["source"]) == (2, "floor")
    preview = seeded.execute("plan", action="parameters", row=2)
    values = preview.data["standards"][0]["values"]
    assert values["row_2_points"] == "5" and "row_4_points" not in values
    full = seeded.standards.row_values(seeded.execute("list", entity=PLAN).data, {}, [])
    assert full["row_3_points"] == "2" and "row_4_points" not in full
    assert full["row_1_points"] == "5"  # row 1 is Done: its own default, still printed
    assert any("row(s) 4 have neither points nor a default" in w for w in preview.warnings)
    for order in (2, 3):  # what the export prints equals the schedule's weight column
        assert full[f"row_{order}_points"] == str(schedule[order]["weight"])
    tickets = seeded.execute("plan", action="tickets").data
    assert tickets["count"] == 4 and tickets["with_ticket"] == 0 and tickets["missing"] == [1, 2, 3, 4]
    assert seeded.execute("update", entity=PLAN, id=2, set=["jira_key=hwl-9"]).ok
    tickets = seeded.execute("plan", action="tickets").data
    assert tickets["missing"] == [1, 3, 4] and tickets["with_ticket"] == 1
    assert [(r["order"], r["jira_key"], r["missing"]) for r in tickets["rows"]][1] == (2, "HWL-9", False)
