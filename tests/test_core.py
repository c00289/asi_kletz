from __future__ import annotations

import shutil
import sqlite3

import pytest

from asi_kletz import Brain, __version__
from asi_kletz.errors import CommandError, NotFound, ValidationError
from asi_kletz.schema import UID, UID_PATTERN
from tests.conftest import DB_0_8_4, ENTITIES, PLAN, TABLES, TABLES_0_8_4


def test_crud_round_trip(brain):
    data = {"deliverable": "Safety Plan", "status": "Pending", "order": "7"}
    created = brain.execute("create", entity=PLAN, data=data)
    assert created.ok, created.errors
    row = created.data
    assert row["id"] == 1 and row["order"] == 7 and row["created_at"]
    assert UID_PATTERN.fullmatch(row[UID])  # the hidden identity, assigned on create

    got = brain.execute("get", entity="Safety Plan", id=1)
    assert got.ok and got.data["deliverable"] == "Safety Plan" and got.data[UID] == row[UID]

    updated = brain.execute("update", entity=PLAN, id=1, set=["status=Done"])
    assert updated.ok and updated.data["status"] == "Done"
    assert updated.data["updated_at"] >= row["updated_at"]

    listed = brain.execute("list", entity=PLAN, filter=["order=7"])
    assert listed.ok and len(listed.data) == 1

    assert brain.execute("count", entity=PLAN).data["count"] == 1
    assert brain.execute("delete", entity=PLAN, id=1).ok
    assert brain.execute("count", entity=PLAN).data["count"] == 0
    missing = brain.execute("get", entity=PLAN, id=1)
    assert not missing.ok and "not found" in missing.errors[0]


def test_validation_and_unknowns_come_back_as_results(brain):
    bad = brain.execute("create", entity=PLAN, data={"order": "banana"})
    assert not bad.ok and any("required" in e for e in bad.errors) and any("integer" in e for e in bad.errors)
    assert not brain.execute("create", entity="dragon", data={}).ok
    assert not brain.execute("fly", entity=PLAN).ok
    assert not brain.execute("get", entity=PLAN).ok  # missing id
    assert not brain.execute("list", entity=PLAN, bogus=1).ok
    weird = brain.execute("create", entity=PLAN, data={"deliverable": "x", "status": "mystery"})
    assert weird.ok and weird.warnings and "lookup" in weird.warnings[0]


def test_ordering_filters_and_bools(seeded):
    rows = seeded.execute("list", entity=PLAN, order_by="-order").data
    assert [r["order"] for r in rows] == [3, 2, 1]
    plan = seeded.execute("list", entity=PLAN, filter=["loc_dms=1"]).data
    assert len(plan) == 1 and plan[0]["loc_dms"] is True and plan[0]["loc_jama"] is False
    assert [r["order"] for r in seeded.execute("list", entity=PLAN, filter=["loc_jama=true"]).data] == [2]
    assert seeded.execute("list", entity=PLAN, filter=["loc_sharepoint=true"]).data == []
    assert [r["order"] for r in seeded.execute("list", entity=PLAN, filter=["status=Done"]).data] == [1]


def test_audit_log_and_events(brain):
    seen = []
    brain.events.subscribe("*", lambda topic, event: seen.append(topic))
    brain.execute("create", entity=PLAN, data={"deliverable": "a"}, actor="ai")
    brain.execute("update", entity=PLAN, id=1, data={"work_product_location": "b"}, actor="human")
    brain.execute("delete", entity=PLAN, id=1)
    tail = brain.storage.audit_tail(10)
    assert [t["action"] for t in tail] == ["delete", "update", "create"]
    assert [t["actor"] for t in tail] == ["python", "human", "ai"]
    assert seen == ["entity.created", "entity.updated", "entity.deleted"]


def test_schema_and_status_commands(seeded):
    status = seeded.execute("status").data
    assert status["app_version"] == __version__
    assert status["entities"] == {PLAN: 3, "sprint": 0, "sprint_item": 0, "week": 0, "holiday": 0, "parameter": 0}
    assert "create" in status["commands"]
    full = seeded.execute("schema").data
    assert [e["name"] for e in full["entities"]] == ENTITIES
    assert set(full["lookups"]) == {
        "pdp_phase", "lifecycle_phase", "plan_status", "sprint_status", "item_status", "item_kind", "week_section",
        "holiday_status",
    }
    assert full["commands"]
    one = seeded.execute("schema", entity="Safety Plan").data
    assert one["name"] == PLAN and one["lookups"]["plan_status"][-1] == "Done"


def test_execute_dict_wire_format(brain):
    payload = {"verb": "create", "args": {"entity": PLAN, "data": {"deliverable": "w"}}, "actor": "bot"}
    result = brain.execute_dict(payload)
    assert result.ok and result.verb == "create"
    assert brain.storage.audit_tail(1)[0]["actor"] == "bot"
    assert not brain.execute_dict({"nope": 1}).ok
    assert result.to_json(indent=None).startswith('{"ok": true')


def test_models_factory(brain):
    Row = brain.models.build(PLAN)
    row = Row(deliverable="n")
    assert row.to_dict()["deliverable"] == "n" and row.id is None
    assert Row().loc_dms is False and Row.__schema__.name == PLAN


def test_reopen_keeps_data_and_migrates(tmp_path):
    db = tmp_path / "persist.db"
    with Brain(db) as b:
        b.execute("create", entity=PLAN, data={"deliverable": "keep"})
    with Brain(db) as b:
        assert b.execute("count", entity=PLAN).data["count"] == 1
        assert b.migration["created"] == [] and b.migration["altered"] == {}
        assert b.migration["uids_stamped"] == dict.fromkeys(ENTITIES, 0)  # 0.9.0 wrote them on create


def test_registered_entities_in_order(brain):
    """The registered list, never a count: an entity is added by registration (the one-table rule retired in 0.8.0)."""
    assert brain.registry.names() == ENTITIES
    assert {r["name"] for r in brain.storage.fetchall("SELECT name FROM sqlite_master WHERE type='table'")} == (
        TABLES | {"schema_migrations", "audit_log", "sqlite_sequence"}
    )
    assert {r["name"] for r in brain.storage.fetchall("SELECT name FROM sqlite_master WHERE type='index'")} >= {
        f"ix_{table}_uid" for table in TABLES
    }


def test_load_config_reads_the_jira_live_keys(tmp_path):
    from asi_kletz.brain import load_config

    config = tmp_path / "kletz.toml"
    config.write_text(
        'doc_id = "ASI-FS-PLAN-001"\njira_live_jql = " project = HWL AND type = Bug "\njira_live_autofetch = false\n'
        '[[revision]]\nrev = "0.1"\ndate = "2026-10-27"\nauthor = "FuSa Engineer"\ndescription = "Initial draft"\n',
        encoding="utf-8",
    )
    loaded = load_config(config)
    assert loaded["jira_live_jql"] == "project = HWL AND type = Bug" and loaded["jira_live_autofetch"] is False
    assert loaded["doc_id"] == "ASI-FS-PLAN-001" and [r["rev"] for r in loaded["revisions"]] == ["0.1"]
    config.write_text('jira_live_autofetch = "false"\n', encoding="utf-8")  # a string is not a boolean
    loaded = load_config(config)
    assert "jira_live_autofetch" not in loaded and "jira_live_jql" not in loaded
    config.write_text("jira_live_autofetch = true\n", encoding="utf-8")
    assert load_config(config)["jira_live_autofetch"] is True


# -- the hidden identity (0.9.0): assigned once, immutable, unique, readable -------------------------


def test_service_assigns_keeps_and_protects_the_uid(brain):
    service = brain.service(PLAN)
    row, _ = service.create({"deliverable": "one"})
    assert UID_PATTERN.fullmatch(row[UID]) and service.get_by_uid(row[UID]) == row
    given = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    kept, _ = service.create({"deliverable": "two", UID: "{3F2504E0-4F89-41D3-9A0C-0305E82C3301}"})
    assert kept[UID] == given and service.get_by_uid(given)["id"] == 2  # a uid handed in is kept, normalised
    # resolve: digits are an id, a uid is looked up, anything else is a bad argument
    assert service.resolve(2) == 2 and service.resolve("12") == 12 and service.resolve(given) == 2
    assert service.resolve(given.upper()) == 2 and service.get(given)["deliverable"] == "two"
    with pytest.raises(NotFound):
        service.resolve("00000000-0000-4000-8000-000000000000")
    with pytest.raises(NotFound):
        service.get_by_uid("not-a-uid")
    with pytest.raises(CommandError):
        service.resolve("seven")
    # update: the same uid is a no-op, another one is refused, an empty one leaves the stored value alone
    same, _ = service.update(2, {"gate_reviewer": "x", UID: given.upper()})
    assert same[UID] == given and same["gate_reviewer"] == "x"
    assert brain.storage.audit_tail(1)[0]["payload"] == {"gate_reviewer": "x"}  # the no-op uid is not audited
    with pytest.raises(ValidationError, match="uid is immutable"):
        service.update(2, {UID: row[UID]})
    with pytest.raises(ValidationError, match="uid is immutable"):
        service.update(given, {UID: "00000000-0000-4000-8000-000000000000"})
    blank, _ = service.update(given, {UID: None, "gate_reviewer": "y"})
    assert blank[UID] == given and blank["gate_reviewer"] == "y"
    assert service.get(2)[UID] == given
    # through the command path: a refused change is a failed Result, not a crash
    refused = brain.execute("update", entity=PLAN, id=2, set=[f"{UID}={row[UID]}"])
    assert not refused.ok and refused.errors == ["uid is immutable"]
    # two rows cannot share a uid: the unique index refuses, the service reports an error
    clash = brain.execute("create", entity=PLAN, data={"deliverable": "three", UID: given})
    assert not clash.ok and "UNIQUE" in clash.errors[0] and brain.execute("count", entity=PLAN).data["count"] == 2
    # delete by uid returns the id, and a uid of a deleted row is gone
    assert service.delete(given) == 2
    with pytest.raises(NotFound):
        service.get(given)
    assert brain.execute("list", entity=PLAN, filter=[f"{UID}={row[UID]}"]).data[0]["id"] == 1


def _raw_rows(path) -> dict[str, list[dict]]:
    """Every table's rows straight from SQLite, without the package, so a stamp cannot hide a change."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return {
            table: [dict(r) for r in conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
            for table in sorted(TABLES_0_8_4 | {"audit_log", "schema_migrations"})
        }
    finally:
        conn.close()


def _indexes(path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    finally:
        conn.close()


def test_a_0_8_4_database_opens_as_0_9_0_with_every_row_stamped(tmp_path):
    """The fixture has three plan rows and one sprint and no ``uid`` column; 0.9.0 adds the column and the
    unique index to every table, stamps every row, audits the counts, and changes nothing else."""
    db = tmp_path / "kletz.db"
    shutil.copyfile(DB_0_8_4, db)
    before = _raw_rows(db)
    assert len(before["safety_plan"]) == 3 and len(before["sprint"]) == 1 and UID not in before["safety_plan"][0]
    assert len(before["schema_migrations"]) == 1 and not any(n.startswith("ix_") for n in _indexes(db))

    with Brain(db) as brain:
        assert brain.migration["created"] == ["holiday", "parameter"]  # 0.10.0 and 0.14.0; the four of 0.8.4 altered
        altered = {table: [UID] for table in TABLES_0_8_4}
        altered["safety_plan"] = ["points", "default_points", "sprint", "sprint_start", "sprint_end", "jira_key", UID]
        altered["sprint_item"] = ["plan_uid", UID]  # 0.13.0: the plan row's uid beside its id
        assert brain.migration["plan_uids_filled"] == 0  # the fixture has no item
        assert brain.migration["altered"] == altered
        assert brain.migration["scheduled"] == 0  # Sprint 1 is Closed: no chain, nothing to write
        assert brain.migration["uids_stamped"] == {
            PLAN: 3, "sprint": 1, "sprint_item": 0, "week": 0, "holiday": 0, "parameter": 0,
        }
        assert brain.execute("count", entity=PLAN).data["count"] == 3
        stamped = brain.storage.audit_tail(10)
        assert [(t["action"], t["actor"], t["entity"], t["payload"]) for t in stamped[:2]] == [
            ("stamp_uids", "system", "sprint", {"count": 1}),
            ("stamp_uids", "system", PLAN, {"count": 3}),
        ]
        assert stamped[2]["action"] == "create"  # the fixture's own history, untouched below it
    after = _raw_rows(db)
    assert _indexes(db) >= {f"ix_{table}_uid" for table in TABLES}
    uids = []
    for table in TABLES_0_8_4:
        for old, stamped_row in zip(before[table], after[table], strict=True):
            new = dict(stamped_row)
            uid = new.pop(UID)
            added = ("points", "default_points", "sprint", "sprint_start", "sprint_end", "jira_key")  # 0.11+, empty
            for column in added:
                if table == "safety_plan":
                    assert new.pop(column) is None
            assert UID_PATTERN.fullmatch(uid) and new == old  # stamped, and nothing else changed (updated_at too)
            uids.append(uid)
    assert len(uids) == len(set(uids)) == 4
    assert after["audit_log"][: len(before["audit_log"])] == before["audit_log"]
    assert len(after["audit_log"]) == len(before["audit_log"]) + 2
    assert len(after["schema_migrations"]) == 2 and after["schema_migrations"][1]["app_version"] == __version__

    with Brain(db) as brain:  # the second open stamps nothing and audits nothing
        assert brain.migration["altered"] == {} and brain.migration["uids_stamped"] == dict.fromkeys(ENTITIES, 0)
        assert {r[UID] for r in brain.execute("list", entity=PLAN).data} < set(uids)
    again = _raw_rows(db)
    assert again == after


def test_commands_take_a_uid_where_an_id_is_expected(seeded):
    rows = seeded.execute("list", entity=PLAN).data
    uid = rows[1]["uid"]
    got = seeded.execute("get", entity=PLAN, id=uid)
    assert got.ok and got.data["id"] == 2 and got.data["deliverable"] == "Hazard Analysis and Risk Assessment"
    assert seeded.execute("get", entity=PLAN, id="{" + uid.upper() + "}").data["id"] == 2
    assert seeded.execute("get", entity=PLAN, id="2").data == got.data
    updated = seeded.execute("update", entity=PLAN, id=uid, set=["status=Blocked"])
    assert updated.ok and updated.data["id"] == 2 and updated.data["status"] == "Blocked"
    assert seeded.storage.audit_tail(1)[0]["entity_id"] == 2  # the audit log keeps the id, the trace of the handle
    refused = seeded.execute("update", entity=PLAN, id=uid, set=["uid=00000000-0000-4000-8000-000000000000"])
    assert not refused.ok and refused.errors == ["uid is immutable"]
    assert seeded.execute("list", entity=PLAN, filter=[f"uid={uid}"]).data[0]["id"] == 2
    assert seeded.execute("list", entity=PLAN, filter=["uid=00000000-0000-4000-8000-000000000000"]).data == []
    missing = seeded.execute("get", entity=PLAN, id="00000000-0000-4000-8000-000000000000")
    assert not missing.ok and "not found" in missing.errors[0]
    neither = seeded.execute("delete", entity=PLAN, id="row-two")
    assert not neither.ok and "neither an id nor a uid" in neither.errors[0]
    deleted = seeded.execute("delete", entity=PLAN, id=uid)
    assert deleted.ok and deleted.data == {"entity": PLAN, "deleted": 2}
    assert seeded.execute("count", entity=PLAN).data["count"] == 2
    signature = next(c for c in seeded.dispatcher.factory.signatures() if c["verb"] == "get")
    assert [a["type"] for a in signature["arguments"]] == ["str", "ref"]
