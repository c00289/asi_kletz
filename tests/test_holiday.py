"""The holiday entity and ``holiday load``: the seed file, the upsert by date and name, the errors."""

from __future__ import annotations

import datetime as dt
import json

from asi_kletz.generate import sprint_queries as q
from asi_kletz.schema import FieldType, default_lookups, default_registry
from tests.conftest import ENTITIES, SEED_HOLIDAYS

HOLIDAY = "holiday"


def test_holiday_is_the_fifth_entity():
    schema = default_registry.get(HOLIDAY)
    assert ENTITIES[-1] == HOLIDAY and default_registry.names()[-1] == HOLIDAY
    assert [f.name for f in schema.fields] == ["date", "name", "status", "note", "uid"]
    assert schema.field("date").type is FieldType.DATE and schema.field("date").required
    assert schema.field("name").required and schema.field("status").lookup == "holiday_status"
    assert default_lookups["holiday_status"] == ("assumed", "confirmed")
    assert schema.sheet == "Holidays" and schema.label == "Holiday" and schema.order_by == ("date", "id")


def test_the_seed_loads_52_weekday_holidays_and_loads_again_unchanged(brain):
    loaded = brain.execute("holiday", action="load", file=str(SEED_HOLIDAYS), actor="me")
    assert loaded.ok, loaded.errors
    assert loaded.data == {
        "path": str(SEED_HOLIDAYS), "rows": 52, "inserted": 52, "updated": 0, "unchanged": 0, "holidays": 52,
    }
    rows = brain.execute("list", entity=HOLIDAY).data
    assert len(rows) == 52 and rows[0]["date"] == "2026-01-01" and rows[0]["name"] == "New Year's Day"
    assert rows[-1]["date"] == "2029-12-25" and all(r["status"] == "assumed" for r in rows)
    assert all(dt.date.fromisoformat(r["date"]).weekday() < 5 for r in rows)  # observed dates, never a weekend
    assert sum(1 for r in rows if "(company, assumed)" in r["name"]) == 8  # Thanksgiving Friday, Christmas Eve, 4 years
    assert brain.storage.audit_tail(1)[0]["actor"] == "me"
    again = brain.execute("holiday", action="load", file=str(SEED_HOLIDAYS))
    assert again.ok and (again.data["inserted"], again.data["updated"], again.data["unchanged"]) == (0, 0, 52)
    assert brain.execute("count", entity=HOLIDAY).data["count"] == 52
    dates = q.holiday_dates(brain)
    assert len(dates) == 50 and dates[dt.date(2026, 11, 11)] == "Veterans Day"  # two observed days land on company days
    assert dates[dt.date(2027, 12, 24)] == "Christmas Day / Christmas Eve (company, assumed)"
    assert sum(" / " in name for name in dates.values()) == 2
    assert dates[dt.date(2026, 11, 27)] == "Day after Thanksgiving (company, assumed)"


def test_load_upserts_by_date_and_name(brain, tmp_path):
    file = tmp_path / "h.json"
    file.write_text(json.dumps([
        {"date": "2026-11-11", "name": "Veterans Day", "status": "assumed"},
        {"date": "12/25/2026", "name": "Christmas Day", "status": "assumed", "note": "observed"},
    ]), encoding="utf-8")
    assert brain.execute("holiday", action="load", file=str(file)).data["inserted"] == 2
    file.write_text(json.dumps({"holidays": [
        {"date": "2026-11-11", "name": "Veterans Day", "status": "confirmed"},  # a changed status is an update
        {"date": "2026-12-25", "name": "Christmas Day", "status": "assumed", "note": "observed"},  # unchanged
        {"date": "2026-12-25", "name": "Company closure", "status": "assumed"},  # a new name on a known date
    ]}), encoding="utf-8")
    result = brain.execute("holiday", action="load", file=str(file))
    assert result.ok and (result.data["inserted"], result.data["updated"], result.data["unchanged"]) == (1, 1, 1)
    rows = brain.execute("list", entity=HOLIDAY).data
    assert [(r["date"], r["name"], r["status"]) for r in rows] == [
        ("2026-11-11", "Veterans Day", "confirmed"), ("2026-12-25", "Christmas Day", "assumed"),
        ("2026-12-25", "Company closure", "assumed"),
    ]
    assert rows[1]["note"] == "observed"


def test_a_bad_file_or_a_bad_row_is_an_error_not_a_crash(brain, tmp_path):
    missing = brain.execute("holiday", action="load", file=str(tmp_path / "none.json"))
    assert not missing.ok and "no such file" in missing.errors[0]
    assert not brain.execute("holiday", action="load").ok
    file = tmp_path / "h.json"
    file.write_text('{"not": "a list"}', encoding="utf-8")
    assert "must hold a JSON list" in brain.execute("holiday", action="load", file=str(file)).errors[0]
    file.write_text("not json", encoding="utf-8")
    assert "is not JSON" in brain.execute("holiday", action="load", file=str(file)).errors[0]
    file.write_text(json.dumps([{"date": "2026-11-11", "name": "Veterans Day"}, {"name": "no date"}]), encoding="utf-8")
    bad = brain.execute("holiday", action="load", file=str(file))
    assert not bad.ok and "holiday 2 needs a date and a name" in bad.errors[0]
    assert brain.execute("count", entity=HOLIDAY).data["count"] == 0  # nothing written before the bad row
    file.write_text(json.dumps([{"date": "someday", "name": "x"}]), encoding="utf-8")
    bad = brain.execute("holiday", action="load", file=str(file))
    assert not bad.ok and "holiday 1: date:" in bad.errors[0]
    file.write_text(json.dumps([{"date": "2026-11-11", "name": "x", "status": "maybe"}]), encoding="utf-8")
    warned = brain.execute("holiday", action="load", file=str(file))
    assert warned.ok and brain.execute("list", entity=HOLIDAY).data[0]["status"] == "maybe"  # a lookup only warns
