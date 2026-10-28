from __future__ import annotations

import json

import pytest
from openpyxl import load_workbook

from asi_kletz import Brain
from tests.conftest import ENTITIES, PLAN, SHEETS, WORKBOOK


def test_json_dump_and_load_modes(seeded, tmp_path):
    out = tmp_path / "dump.json"
    dumped = seeded.execute("dump", out=str(out))
    assert dumped.ok and dumped.data["entities"] == {PLAN: 3, "sprint": 0, "sprint_item": 0, "week": 0}
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 3 and list(payload["entities"]) == ENTITIES

    uids = {r["id"]: r["uid"] for r in payload["entities"][PLAN]}
    assert len(uids) == 3 and all(uids.values())  # the dump carries the hidden identity like any field
    with Brain(tmp_path / "other.db") as other:
        loaded = other.execute("load", path=str(out), mode="replace")
        assert loaded.ok, loaded.errors
        assert other.execute("count", entity=PLAN).data["count"] == 3
        assert {r["id"]: r["uid"] for r in other.execute("list", entity=PLAN).data} == uids  # replace keeps them
        # merge updates the rows the uids name; so does append: a row that exists is never inserted twice
        assert other.execute("load", path=str(out), mode="merge").data["entities"][PLAN]["updated"] == 3
        assert other.execute("count", entity=PLAN).data["count"] == 3
        appended = other.execute("load", path=str(out), mode="append").data["entities"][PLAN]
        assert appended["updated"] == 3 and appended["inserted"] == 0
        assert other.execute("count", entity=PLAN).data["count"] == 3
        # a 0.8.x dump has no uids: append makes new rows with new ids, and stamps them
        for row in payload["entities"][PLAN]:
            del row["uid"]
        old = tmp_path / "dump-0.8.json"
        old.write_text(json.dumps(payload), encoding="utf-8")
        assert other.execute("load", path=str(old), mode="append").data["entities"][PLAN]["inserted"] == 3
        rows = other.execute("list", entity=PLAN, order_by="id").data
        assert [r["id"] for r in rows] == [1, 2, 3, 4, 5, 6] and len({r["uid"] for r in rows}) == 6
        assert all(r["uid"] for r in rows)

    single = tmp_path / "plan.json"
    assert seeded.execute("dump", entity=PLAN, out=str(single)).ok
    assert json.loads(single.read_text(encoding="utf-8"))["entity"] == PLAN


def test_excel_export_and_reimport(seeded, tmp_path):
    exported = seeded.execute("export", format="excel")
    assert exported.ok, exported.errors
    path = exported.data["path"]
    wb = load_workbook(path)
    assert wb.sheetnames == SHEETS
    ws = wb["Safety Plan"]
    headers = [c.value for c in ws[1]]
    assert headers[:4] == ["order", "PDP Phases", "Safety Lifecycle Phase", "Safety Deliverables"]
    assert headers.count("Tech Lead - Functional Safety") == 2 and len(headers) == 64 and headers[-1] == "uid"
    assert ws.freeze_panes == "A2"
    assert ws["D2"].value == "Safety Plan" and ws["F2"].value == 1  # deliverable, DMS flag
    assert ws.data_validations.dataValidation  # dropdowns from the lookups

    with Brain(tmp_path / "re.db") as other:
        result = other.execute("import", format="excel", path=path, mode="replace")
        assert result.ok, result.errors
        rows = other.execute("list", entity=PLAN).data
        assert [r["order"] for r in rows] == [1, 2, 3]
        row = rows[0]
        assert row["deliverable"] == "Safety Plan" and row["loc_dms"] and row["reviewer_tech_lead_functional_safety"]
        assert row["author_tech_lead_functional_safety"] is False and row["status"] == "Done"


def test_locked_workbook_falls_back_to_sibling(seeded, tmp_path, monkeypatch):
    import asi_kletz.io.exporters as ex

    calls = []

    def fake_save(path):
        calls.append(path)
        if len(calls) == 1:
            raise PermissionError("locked")
        path.write_bytes(b"ok")

    path, warning = ex._save_with_fallback(fake_save, tmp_path / "view.xlsx", ".xlsx")
    assert path != tmp_path / "view.xlsx" and path.suffix == ".xlsx" and "locked" in warning


def test_run_script(seeded, tmp_path):
    script = tmp_path / "steps.jsonl"
    script.write_text(
        '# comment\n'
        '{"verb": "create", "args": {"entity": "safety_plan_row", "data": {"deliverable": "from script"}}}\n'
        '{"verb": "count", "args": {"entity": "safety_plan_row"}}\n'
        '{"verb": "get", "args": {"entity": "safety_plan_row", "id": 999}}\n',
        encoding="utf-8",
    )
    result = seeded.execute("run", path=str(script))
    assert not result.ok and result.data["steps"] == 3 and result.data["failed"] == [3]
    assert result.data["results"][1]["data"]["count"] == 4
    assert seeded.storage.audit_tail(3)[-1]["actor"] == "python"
    stop = seeded.execute("run", path=str(script), stop_on_error=True)
    assert stop.data["steps"] == 3


@pytest.mark.skipif(not WORKBOOK.is_file(), reason="real workbook not present")
def test_seed_from_real_workbook(tmp_path):
    with Brain(tmp_path / "seed.db") as b:
        result = b.execute("import", format="excel", path=str(WORKBOOK), mode="replace")
        assert result.ok, result.errors
        counts = b.execute("status").data["entities"]
        assert list(counts) == ENTITIES and counts[PLAN] >= 48
        plan = b.execute("list", entity=PLAN, filter=["order=1"]).data[0]
        assert plan["lifecycle_phase"] == "1. Concept Development" and plan["ref_qf_17"] is True
        out = b.execute("export", format="excel", out=str(tmp_path / "regen.xlsx"))
        assert out.ok and out.data["entities"][PLAN] == counts[PLAN]
        assert load_workbook(out.data["path"]).sheetnames == SHEETS


@pytest.mark.skipif(not WORKBOOK.is_file(), reason="real workbook not present")
def test_source_workbook_columns_match_the_schema():
    """The table shows the sheet's columns in source order by construction, not by coincidence."""
    from asi_kletz.schema import default_registry

    ws = load_workbook(WORKBOOK, read_only=True)["Safety Plan"]
    headers = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    while headers and headers[-1] is None:
        headers.pop()
    assert headers == [f.header for f in default_registry.get(PLAN).visible_fields]  # the source sheet has no uid
    assert len(headers) == 63
