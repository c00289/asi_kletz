from __future__ import annotations

import datetime as dt

import pytest

from asi_kletz.errors import NotFound, ValidationError
from asi_kletz.schema import (
    UID,
    UID_PATTERN,
    EntitySchema,
    FieldSpec,
    FieldType,
    SchemaRegistry,
    coerce,
    default_lookups,
    default_registry,
    definitions,
    flag_fields,
    is_uid,
    new_uid,
    normalise_uid,
    uid_field,
)
from tests.conftest import ENTITIES, PLAN

FINGERPRINT_0_8_4 = "d3365e8a31d20795"  # what tests/fixtures/kletz-0.8.4.db recorded in schema_migrations


def spec(kind, **kw):
    return FieldSpec("f", kind, **kw)


def test_coerce_int_bool_date():
    assert coerce(spec(FieldType.INT), "3") == (3, None)
    assert coerce(spec(FieldType.INT), 3.0) == (3, None)
    with pytest.raises(ValueError):
        coerce(spec(FieldType.INT), "three")
    assert coerce(spec(FieldType.BOOL), None) == (False, None)
    assert coerce(spec(FieldType.BOOL), "x") == (True, None)
    assert coerce(spec(FieldType.BOOL), 0) == (False, None)
    assert coerce(spec(FieldType.DATE), 46314) == ("2026-10-19", None)
    assert coerce(spec(FieldType.DATE), "10/23/2026") == ("2026-10-23", None)
    assert coerce(spec(FieldType.DATE), dt.datetime(2026, 1, 2, 3, 4)) == ("2026-01-02", None)
    with pytest.raises(ValueError):
        coerce(spec(FieldType.DATE), "someday")


def test_coerce_text_and_enum_warning():
    assert coerce(spec(FieldType.TEXT), "  a\xa0b  ") == ("a b", None)
    assert coerce(spec(FieldType.MULTILINE), "a\nb ") == ("a\nb", None)
    with pytest.raises(ValueError):
        coerce(spec(FieldType.TEXT, required=True), "   ")
    value, warning = coerce(spec(FieldType.ENUM, lookup="plan_status"), "weird", default_lookups)
    assert value == "weird" and "not in lookup" in warning
    assert coerce(spec(FieldType.ENUM, lookup="plan_status"), "Done", default_lookups) == ("Done", None)


def test_schema_validation_collects_all_errors():
    schema = default_registry.get(PLAN)
    with pytest.raises(ValidationError) as info:
        schema.coerce_row({"deliverable": "", "order": "nope", "bogus": 1})
    messages = " | ".join(info.value.errors)
    assert "required" in messages and "not an integer" in messages and "unknown field" in messages


def test_registry_aliases_and_fingerprint():
    assert default_registry.get("Safety Plan").table == "safety_plan"
    assert default_registry.get("safety_plan").name == PLAN
    assert default_registry.get("Safety Plan Row").name == PLAN
    with pytest.raises(NotFound):
        default_registry.get("unicorns")
    assert default_registry.fingerprint() == default_registry.fingerprint()
    assert default_registry.names() == [PLAN, "sprint", "sprint_item", "week", "holiday", "parameter"]
    assert set(default_lookups) == {
        "pdp_phase", "lifecycle_phase", "plan_status", "sprint_status", "item_status", "item_kind", "week_section",
        "holiday_status",
    }


def test_safety_plan_matrix_fields_are_unique_and_grouped():
    schema = default_registry.get(PLAN)
    names = schema.field_names
    # 63 of the sheet, 3 + 2 calculated, jira_key, urls (0.20.0), uid
    assert len(names) == len(set(names)) == 71 and names[-1] == UID
    assert len(schema.visible_fields) == 70 and len(schema.source_fields) == 63
    assert names[-4:] == ("status", "jira_key", "urls", UID) and schema.field("jira_key").editable
    assert schema.field("urls").editable and schema.field("urls").picker == "urls"
    assert names[3:7] == ("deliverable", "points", "default_points", "sprint")
    assert [f.name for f in schema.calculated_fields] == ["sprint", "sprint_start", "sprint_end", "deadline"]
    assert not schema.field("default_points").editable and schema.field("points").default_from == "default_points"
    assert [f.name for f in schema.visible_fields if not f.editable] == [
        "default_points", "sprint", "sprint_start", "sprint_end", "deadline",
    ]
    assert len(schema.editable_fields) == 65 and schema.field("deadline").header == "Expected Duration/Deadline"
    groups = schema.groups()
    assert len(groups["reference"]) == 23 and len(groups["author"]) == 18 and len(groups["reviewer"]) == 8
    assert "author_tech_lead_functional_safety" in names and "reviewer_tech_lead_functional_safety" in names
    assert schema.field("author_v_v_team").header == "V&V Team"


def test_entity_schema_rejects_duplicates_and_system_names():
    with pytest.raises(ValueError):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("a"), FieldSpec("a")))
    with pytest.raises(ValueError):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("id"),))
    with pytest.raises(ValueError):
        EntitySchema("x", "xs", "X", "x", (FieldSpec("a"),), order_by=("nope",))


def test_custom_registry_is_independent():
    reg = SchemaRegistry()
    fields = (FieldSpec("name"), *flag_fields("g", "g", ["A B"]))
    reg.register(EntitySchema("widget", "widgets", "Widget", "widgets", fields))
    assert reg.get("widgets").field("g_a_b").type is FieldType.BOOL
    assert PLAN not in reg


# -- the hidden identity (0.9.0) ---------------------------------------------------------------------


def test_every_entity_ends_with_the_hidden_uid():
    """Section 3.1 of docs/hidden-identity-plan.md: ``uid``, TEXT, header ``uid``, hidden, last on every entity."""
    assert default_registry.names() == ENTITIES
    for schema in default_registry:
        last = schema.fields[-1]
        assert last.name == UID and last.type is FieldType.TEXT and last.header == UID and last.hidden
        assert last == uid_field() and not last.required and last.group is None
        assert [f.name for f in schema.visible_fields] == [f.name for f in schema.fields if not f.hidden]
        assert not any(f.hidden for f in schema.visible_fields)
        assert schema.to_dict()["fields"][-1] == {
            "name": UID, "type": "text", "header": UID, "required": False, "lookup": None, "group": None,
            "help": "Hidden identity: assigned once, never changed.", "hidden": True, "calculated": False,
            "readonly": False, "source": True,
        }
    assert definitions.ALL_ENTITIES[0].fields[-1].name == UID
    hidden = [f.name for f in default_registry.get("sprint_item").fields if f.hidden]
    assert hidden == ["plan_uid", UID]  # 0.13.0: the plan row's uid beside its id, hidden like the uid
    assert FieldSpec("x").hidden is False and "hidden" in FieldSpec("x").to_dict()
    # the fingerprint moved, so a 0.8.4 database gains a schema_migrations row when 0.9.0 opens it
    assert default_registry.fingerprint() != FINGERPRINT_0_8_4


def test_uid_values_are_canonical_uuid4s():
    uid = new_uid()
    assert len(uid) == 36 and uid == uid.lower() and UID_PATTERN.fullmatch(uid) and is_uid(uid)
    assert len({new_uid() for _ in range(50)}) == 50
    canonical = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    assert normalise_uid(canonical) == canonical
    assert normalise_uid("3F2504E0-4F89-41D3-9A0C-0305E82C3301") == canonical  # another case
    assert normalise_uid("{3F2504E0-4F89-41D3-9A0C-0305E82C3301}") == canonical  # braces, as Excel prints a GUID
    assert normalise_uid(" {" + canonical + "} ") == canonical
    for bad in ("not-a-uid", "3f2504e04f8941d39a0c0305e82c3301", "3f2504e0-4f89-11d3-9a0c-0305e82c3301", "", 12):
        assert normalise_uid(bad) is None and not is_uid(bad)


def test_uid_coercion_accepts_normalises_and_rejects():
    spec = uid_field()
    canonical = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    assert coerce(spec, canonical) == (canonical, None)
    assert coerce(spec, "{3F2504E0-4F89-41D3-9A0C-0305E82C3301}") == (canonical, None)
    assert coerce(spec, None) == (None, None) and coerce(spec, "") == (None, None)  # absent: assigned on create
    with pytest.raises(ValueError, match="^uid: 'not-a-uid' is not a uid"):
        coerce(spec, "not-a-uid")
    schema = default_registry.get(PLAN)
    with pytest.raises(ValidationError) as info:
        schema.coerce_row({"deliverable": "d", UID: "not-a-uid"})
    assert info.value.errors == ["uid: 'not-a-uid' is not a uid (a lowercase UUID4 with dashes)"]
    clean, _ = schema.coerce_row({"deliverable": "d", UID: canonical.upper()})
    assert clean[UID] == canonical
