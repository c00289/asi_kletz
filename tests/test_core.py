from __future__ import annotations

from asi_kletz import Brain, __version__
from tests.conftest import ENTITIES, PLAN, TABLES


def test_crud_round_trip(brain):
    data = {"deliverable": "Safety Plan", "status": "Pending", "order": "7"}
    created = brain.execute("create", entity=PLAN, data=data)
    assert created.ok, created.errors
    row = created.data
    assert row["id"] == 1 and row["order"] == 7 and row["created_at"]

    got = brain.execute("get", entity="Safety Plan", id=1)
    assert got.ok and got.data["deliverable"] == "Safety Plan"

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
    brain.execute("update", entity=PLAN, id=1, data={"deadline": "b"}, actor="human")
    brain.execute("delete", entity=PLAN, id=1)
    tail = brain.storage.audit_tail(10)
    assert [t["action"] for t in tail] == ["delete", "update", "create"]
    assert [t["actor"] for t in tail] == ["python", "human", "ai"]
    assert seen == ["entity.created", "entity.updated", "entity.deleted"]


def test_schema_and_status_commands(seeded):
    status = seeded.execute("status").data
    assert status["app_version"] == __version__
    assert status["entities"] == {PLAN: 3, "sprint": 0, "sprint_item": 0, "week": 0} and "create" in status["commands"]
    full = seeded.execute("schema").data
    assert [e["name"] for e in full["entities"]] == ENTITIES
    assert set(full["lookups"]) == {
        "pdp_phase", "lifecycle_phase", "plan_status", "sprint_status", "item_status", "item_kind", "week_section",
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
        assert b.migration["created"] == []


def test_registered_entities_in_order(brain):
    """The registered list, never a count: an entity is added by registration (the one-table rule retired in 0.8.0)."""
    assert brain.registry.names() == ENTITIES
    assert {r["name"] for r in brain.storage.fetchall("SELECT name FROM sqlite_master WHERE type='table'")} == (
        TABLES | {"schema_migrations", "audit_log", "sqlite_sequence"}
    )


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
