"""0.19.0, the owner, 2026-10-29: "each safety deliverable can have multiple authors, so for any safety case field,
instead of the parameter being a string it is now an array of human names sorted alphabetically; make all
updates necessary; also must include email alongside name."

The people of a role parameter: parsing and sorting, the verbs (the API's array, its JSON text and the CLI's
``Name <email>; ...`` text), the validation, the legacy fallback (a name with no email yet is kept, printed
verbatim and replaced the moment people are saved), the role report of ``plan parameters`` and ``standards
for``, the export rendering (inline, alphabetical, ``Name (email)``, in the Markdown and in the Word original),
the workbook and dump round trips, and the schema 8 to 9 migration."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from openpyxl import load_workbook

from asi_kletz import Brain
from asi_kletz.schema.definitions import ROLE_SLUGS
from asi_kletz.schema.people import (
    PeopleError,
    Person,
    is_role,
    parse_people,
    people_json,
    people_lines,
    people_text,
    render_people,
    sort_people,
)
from tests.conftest import PLAN
from tests.test_cli import run
from tests.test_standards import _stub, standards_dir
from tests.test_standards_template import _original

ANN = {"name": "Ann Lee", "email": "ann.lee@asirobots.com"}
BEN = {"name": "Ben Ray", "email": "ben.ray@asirobots.com"}
TEXT = "Ben Ray <ben.ray@asirobots.com>; Ann Lee <ann.lee@asirobots.com>"
LEGACY = "Roy does not know who this is as of 2026-10-29"


@pytest.fixture
def standards(tmp_path, monkeypatch):
    return standards_dir(tmp_path, monkeypatch)


# -- the pure functions -------------------------------------------------------------------------------------


def test_roles_are_the_author_and_reviewer_slugs():
    assert len(ROLE_SLUGS) == 22 and ROLE_SLUGS == tuple(sorted(ROLE_SLUGS))
    assert is_role("fusa_engineer") and is_role("tech_lead_functional_safety") and is_role("v_v_team")
    assert not is_role("vehicle_type") and not is_role("row_1_points") and not is_role(None)


def test_parse_people_reads_every_form_and_sorts_by_name():
    expected = [Person("Ann Lee", "ann.lee@asirobots.com"), Person("Ben Ray", "ben.ray@asirobots.com")]
    assert parse_people([BEN, ANN]) == expected  # the API's array
    assert parse_people(json.dumps([BEN, ANN])) == expected  # its JSON text
    assert parse_people(TEXT) == expected  # the CLI's text, `;` between people
    assert parse_people("Ben Ray <ben.ray@asirobots.com>\nAnn Lee <ann.lee@asirobots.com>\n") == expected  # lines
    assert parse_people(["Ben Ray <ben.ray@asirobots.com>", ANN]) == expected  # a mixed list
    assert parse_people("  Ben Ray  < ben.ray@asirobots.com >;; ") == [Person("Ben Ray", "ben.ray@asirobots.com")]
    assert parse_people(None) == [] and parse_people("") == [] and parse_people("[]") == []
    # case-insensitive by the full name as typed; the email breaks a tie; never by email
    people = parse_people("zed <z@x.io>; Ann <a@x.io>; ann b <ab@x.io>; Bob <b@x.io>; Ann <0@x.io>")
    assert [p.text for p in people] == [
        "Ann <0@x.io>", "Ann <a@x.io>", "ann b <ab@x.io>", "Bob <b@x.io>", "zed <z@x.io>",
    ]
    assert sort_people(reversed(people)) == people
    assert people_json(reversed(expected)) == json.dumps([ANN, BEN], separators=(", ", ": "))
    assert people_json([]) is None
    assert people_text([BEN, ANN]) == "Ann Lee <ann.lee@asirobots.com>; Ben Ray <ben.ray@asirobots.com>"
    assert people_lines([BEN, ANN]) == "Ann Lee <ann.lee@asirobots.com>\nBen Ray <ben.ray@asirobots.com>"
    assert render_people([BEN, ANN]) == "Ann Lee (ann.lee@asirobots.com), Ben Ray (ben.ray@asirobots.com)"
    assert render_people("not people") == "" and people_text(None) == ""


@pytest.mark.parametrize(("value", "message"), [
    ("Ben Ray", "fusa_engineer, line 1 ('Ben Ray'): no email; write Name <email>"),
    ("<ben@x.io>", "fusa_engineer, line 1 ('<ben@x.io>'): no name; write Name <email>"),
    ([{"email": "ben@x.io"}], "fusa_engineer, line 1 ('ben@x.io'): no name; write Name <email>"),
    ([{"name": "Ben Ray"}], "fusa_engineer, line 1 ('Ben Ray'): no email; write Name <email>"),
    ("Ben Ray <ben@x>", "fusa_engineer, line 1: 'ben@x' is not an email (local@domain.tld)"),
    ("Ben Ray <ben ray@x.io>", "fusa_engineer, line 1: 'ben ray@x.io' is not an email (local@domain.tld)"),
    ("Ben Ray <ben@x.io> <ben@x.io>", "fusa_engineer, line 1 ('Ben Ray <ben@x.io> <ben@x.io>'): the email goes in "
                                      "angle brackets, once; write Name <email>"),
    ("Ben ben@x.io <ben@x.io>", "fusa_engineer, line 1: the name 'Ben ben@x.io' holds an email; the email goes "
                                "after it, once, in angle brackets"),
    ("Ann <a@x.io>; Ben <A@X.IO>", "fusa_engineer: 'A@X.IO' is listed twice (lines 1 and 2)"),
    ("[oops", "fusa_engineer: not a JSON array of people: Expecting value: line 1 column 2 (char 1)"),
    ('{"name": "x"}', "fusa_engineer, line 1 ('{\"name\": \"x\"}'): no email; write Name <email>"),
    ("[{}]", "fusa_engineer, line 1: a person needs a name and an email"),
])
def test_parse_people_refuses_and_names_the_role_and_the_line(value, message):
    with pytest.raises(PeopleError) as info:
        parse_people(value, "fusa_engineer")
    assert info.value.errors == [message]


def test_parse_people_reports_every_problem_at_once():
    with pytest.raises(PeopleError) as info:
        parse_people("Ann Lee <ann@x.io>; Ben Ray; Cy <cy@x>; Dee <ann@x.io>", "pat")
    assert info.value.errors == [
        "pat, line 2 ('Ben Ray'): no email; write Name <email>",
        "pat, line 3: 'cy@x' is not an email (local@domain.tld)",
        "pat: 'ann@x.io' is listed twice (lines 1 and 4)",
    ]


# -- the verbs ------------------------------------------------------------------------------------------------


def test_a_role_parameter_holds_people_as_an_array(seeded):
    created = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": [BEN, ANN]})
    assert created.ok and created.warnings == [] and created.data["people"] == [ANN, BEN]  # sorted, an array
    assert created.data["value"] is None
    row_id = created.data["id"]
    assert seeded.execute("get", entity="parameter", id=row_id).data["people"] == [ANN, BEN]
    assert seeded.execute("list", entity="parameter").data[0]["people"] == [ANN, BEN]
    stored = seeded.storage.fetchone("SELECT people FROM parameter WHERE id = ?", (row_id,))["people"]
    assert json.loads(stored) == [ANN, BEN] and stored.startswith('[{"name": "Ann Lee"')  # JSON text in the column
    # the CLI's text form through --set; the JSON text too; an update replaces the whole list
    zed = {"name": "Zed Young", "email": "zed@asirobots.com"}
    updated = seeded.execute("update", entity="parameter", id=row_id, set=["people=Zed Young <zed@asirobots.com>"])
    assert updated.ok and updated.data["people"] == [zed]
    updated = seeded.execute("update", entity="parameter", id=row_id, set=[f"people={json.dumps([BEN, zed, ANN])}"])
    assert updated.ok and updated.data["people"] == [ANN, BEN, zed]
    # the audit entry carries the canonical text
    assert json.loads(seeded.storage.audit_tail(1)[0]["payload"]["people"]) == [ANN, BEN, zed]
    # people cleared: an empty text or an empty array; the value stays empty
    for empty in ("", "[]", []):
        cleared = seeded.execute("update", entity="parameter", id=row_id, data={"people": empty})
        assert cleared.ok and cleared.data["people"] is None and cleared.data["value"] is None
    # a standard's own row holds its own people, the name still unique per standard
    own = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "standard": "qf-17-test",
                                                             "people": TEXT})
    assert own.ok and own.data["people"] == [ANN, BEN]
    assert not seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": TEXT}).ok


def test_the_people_rule_refuses_what_it_must(seeded):
    bad = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": "Ben Ray"})
    assert not bad.ok and bad.errors == ["fusa_engineer, line 1 ('Ben Ray'): no email; write Name <email>"]
    bad = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": [{"name": "Ben Ray"}]})
    assert not bad.ok and bad.errors == ["fusa_engineer, line 1 ('Ben Ray'): no email; write Name <email>"]
    bad = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": "<ben@x.io>"})
    assert not bad.ok and bad.errors == ["fusa_engineer, line 1 ('<ben@x.io>'): no name; write Name <email>"]
    bad = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": "Ben <ben@x>"})
    assert not bad.ok and bad.errors == ["fusa_engineer, line 1: 'ben@x' is not an email (local@domain.tld)"]
    bad = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": [ANN, ANN]})
    assert not bad.ok and bad.errors == ["fusa_engineer: 'ann.lee@asirobots.com' is listed twice (lines 1 and 2)"]
    assert seeded.execute("count", entity="parameter").data["count"] == 0  # nothing landed
    # people on a parameter that is not a role
    bad = seeded.execute("create", entity="parameter", data={"name": "vehicle_type", "people": [ANN]})
    assert not bad.ok and bad.errors[0].startswith("vehicle_type is not a role: it holds a value, not people")
    assert "fusa_engineer" in bad.errors[0]
    # a value on a role that holds people
    assert seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": [ANN]}).ok
    bad = seeded.execute("update", entity="parameter", id=1, set=["value=Someone Else"])
    assert not bad.ok and bad.errors == [
        "fusa_engineer holds people: set people (Name <email>; ...) instead of a value, or clear them first"
    ]
    assert seeded.execute("get", entity="parameter", id=1).data["people"] == [ANN]
    # people and a value in one call: the people win, the value is ignored with a warning
    both = seeded.execute("update", entity="parameter", id=1, data={"value": "Someone Else", "people": [BEN]})
    assert both.ok and both.data["people"] == [BEN] and both.data["value"] is None
    assert both.warnings == ["fusa_engineer: the value 'Someone Else' is ignored; a role holds people"]


def test_a_legacy_name_with_no_email_is_kept_until_people_are_saved(seeded, standards, tmp_path, monkeypatch):
    """The live database of 2026-10-29 holds a placeholder or a bare name per role: it keeps loading and
    exporting verbatim, flagged, and is replaced the moment people are saved for that role."""
    legacy = seeded.execute("create", entity="parameter", data={"name": "tech_lead_functional_safety",
                                                                "value": "Ida Moss"})
    assert legacy.ok and legacy.data["value"] == "Ida Moss" and legacy.data["people"] is None
    assert legacy.warnings == ["tech_lead_functional_safety: a role holds people (Name <email>; ...); 'Ida Moss' "
                               "is kept as a legacy value with no email yet"]
    placeholder = seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "value": LEGACY})
    assert placeholder.ok and placeholder.data["value"] == LEGACY
    assert seeded.execute("create", entity="parameter", data={"name": "vehicle_type", "value": "Wheel Loader"}).ok
    _stub(seeded, monkeypatch, {})
    # plan parameters: the legacy string is the value, verbatim; the role report names the legacy roles
    preview = seeded.execute("plan", action="parameters", row=1)
    assert preview.ok, preview.errors
    [std] = preview.data["standards"]
    assert std["values"]["fusa_engineer"] == LEGACY and std["role_parameters"] == ["fusa_engineer"]
    assert std["roles"] == {"fusa_engineer": {"state": "legacy", "people": 0, "names": [], "legacy": LEGACY}}
    assert std["legacy_roles"] == ["fusa_engineer"] and std["empty_roles"] == []
    assert "qf-17-test: 1 role(s) with a legacy value with no email yet (printed verbatim): fusa_engineer" in (
        preview.warnings)
    # the export prints it verbatim, marked as a whole
    result = seeded.execute("plan", action="export", row=1, out=str(tmp_path / "out"))
    assert result.ok and f"Author: =={LEGACY}==" in Path(result.data["exports"][0]["files"]["md"]).read_text(
        encoding="utf-8")
    # people saved for the role replace it: the value goes, the people render
    assert seeded.execute("update", entity="parameter", id=placeholder.data["id"], data={"people": TEXT}).ok
    row = seeded.execute("get", entity="parameter", id=placeholder.data["id"]).data
    assert row["people"] == [ANN, BEN] and row["value"] is None
    preview = seeded.execute("plan", action="parameters", row=1)
    [std] = preview.data["standards"]
    assert std["values"]["fusa_engineer"] == "Ann Lee (ann.lee@asirobots.com), Ben Ray (ben.ray@asirobots.com)"
    assert std["roles"]["fusa_engineer"] == {"state": "people", "people": 2, "names": ["Ann Lee", "Ben Ray"],
                                             "legacy": None}
    assert std["legacy_roles"] == [] and not any("legacy" in w for w in preview.warnings)
    # a role with no one: the blank stays unfilled and the report says so (standards for too)
    assert seeded.execute("delete", entity="parameter", id=placeholder.data["id"]).ok
    preview = seeded.execute("plan", action="parameters", row=1)
    [std] = preview.data["standards"]
    assert "fusa_engineer" in std["unfilled"] and std["empty_roles"] == ["fusa_engineer"]
    assert std["roles"]["fusa_engineer"]["state"] == "empty"
    assert "qf-17-test: 1 role(s) with no one (left unfilled): fusa_engineer" in preview.warnings
    for_row = seeded.execute("standards", action="for", row=1)
    assert for_row.ok and for_row.data["standards"][0]["empty_roles"] == ["fusa_engineer"]
    assert for_row.data["standards"][0]["roles"]["fusa_engineer"]["people"] == 0
    assert for_row.warnings == ["qf-17-test: 1 role(s) with no one (left unfilled): fusa_engineer"]
    listed = seeded.execute("standards", action="list")
    assert listed.data["standards"][0]["role_parameters"] == ["fusa_engineer"]


def test_the_cli_sets_people_as_text_and_as_json(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    code, res = run(capsys, "--db", db, "create", "parameter", "--set", "name=fusa_engineer", "--set", f"people={TEXT}")
    assert code == 0 and res["ok"] and res["data"]["people"] == [ANN, BEN] and res["data"]["value"] is None
    data = json.dumps({"name": "tech_lead_functional_safety", "people": [BEN]})
    code, res = run(capsys, "--db", db, "create", "parameter", "--data", data)
    assert code == 0 and res["data"]["people"] == [BEN]
    code, res = run(capsys, "--db", db, "update", "parameter", "1", "--set", "people=Ben Ray")
    assert code == 1 and res["errors"] == ["fusa_engineer, line 1 ('Ben Ray'): no email; write Name <email>"]
    code, res = run(capsys, "--db", db, "--compact", "list", "parameter")
    assert code == 0 and [r["people"] for r in res["data"]] == [[ANN, BEN], [BEN]]
    code, res = run(capsys, "--db", db, "create", "parameter", "--set", "name=robot_chief", "--set", "value=Max Stone")
    assert code == 0 and res["data"]["value"] == "Max Stone" and res["warnings"][0].endswith("no email yet")


# -- the export ---------------------------------------------------------------------------------------------


def test_the_export_renders_people_inline_in_the_markdown_and_the_word_original(seeded, standards, tmp_path,
                                                                                 monkeypatch):
    import docx

    original = _original(standards / "qf-17-test" / "source" / "QF-17 test.docx")
    assert seeded.execute("create", entity="parameter", data={"name": "vehicle_type", "value": "Wheel Loader"}).ok
    assert seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": [BEN, ANN]}).ok
    _stub(seeded, monkeypatch, {})
    out = tmp_path / "out"
    result = seeded.execute("plan", action="export", row=1, out=str(out))
    assert result.ok, result.errors
    [built] = result.data["exports"]
    assert built["template"] == str(original) and "fusa_engineer" not in built["unfilled"]
    rendered = "Ann Lee (ann.lee@asirobots.com), Ben Ray (ben.ray@asirobots.com)"
    assert f"Author: =={rendered}==" in Path(built["files"]["md"]).read_text(encoding="utf-8")  # one mark
    word = docx.Document(built["files"]["docx"])
    author = word.paragraphs[1]
    assert author.text == f"Author: {rendered}" and author.runs[0].text == "Author: " and author.runs[0].bold
    assert [r.text for r in author.runs[1:] if r.text] == [rendered]  # the people are one filled run, shaded


# -- the files ----------------------------------------------------------------------------------------------


def test_people_round_trip_through_the_dump_and_the_workbook(seeded, tmp_path):
    assert seeded.execute("create", entity="parameter", data={"name": "fusa_engineer", "people": [BEN, ANN]}).ok
    assert seeded.execute("create", entity="parameter", data={"name": "robot_chief", "value": "Max Stone"}).ok
    assert seeded.execute("create", entity="parameter", data={"name": "vehicle_type", "value": "Wheel Loader"}).ok
    expected = [(r["name"], r["value"], r["people"]) for r in seeded.execute("list", entity="parameter").data]
    assert expected == [("fusa_engineer", None, [ANN, BEN]), ("robot_chief", "Max Stone", None),
                        ("vehicle_type", "Wheel Loader", None)]
    # the JSON dump carries the array; the load parses, validates and sorts it (no guard runs on a load)
    dump = tmp_path / "dump.json"
    assert seeded.execute("dump", out=str(dump), entity="parameter").ok
    payload = json.loads(dump.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 12 and payload["rows"][0]["people"] == [ANN, BEN]
    payload["rows"][0]["people"] = [BEN, ANN]  # unsorted in the file: sorted on the way in
    payload["rows"].append({"name": "pat", "people": [{"name": "No Email"}], "uid": None})  # bad: dropped, warned
    payload["rows"].append({"name": "dev_manager", "value": "Legacy Name", "people": [ANN], "uid": None})  # people win
    dump.write_text(json.dumps(payload), encoding="utf-8")
    with Brain(tmp_path / "re.db") as other:
        loaded = other.execute("load", path=str(dump), mode="replace")
        assert loaded.ok, loaded.errors
        rows = {r["name"]: r for r in other.execute("list", entity="parameter").data}
        assert [(rows[n]["value"], rows[n]["people"]) for n, _, _ in expected] == [(v, p) for _, v, p in expected]
        assert rows["pat"]["people"] is None and rows["pat"]["value"] is None
        assert rows["dev_manager"]["people"] == [ANN] and rows["dev_manager"]["value"] is None
        dropped = "pat, line 1 ('No Email'): no email; write Name <email>; people ignored"
        assert any(dropped in w for w in loaded.warnings)
    # the workbook's Parameters sheet carries the people as JSON text in a People column; the import reads it back
    exported = seeded.execute("export", format="excel", out=str(tmp_path / "view.xlsx"))
    assert exported.ok, exported.errors
    ws = load_workbook(exported.data["path"])["Parameters"]
    assert [c.value for c in ws[1]] == ["Name", "Standard", "Value", "People", "Note", "uid"]
    assert json.loads(ws["D2"].value) == [ANN, BEN] and ws["C2"].value is None and ws["C3"].value == "Max Stone"
    with Brain(tmp_path / "xl.db") as third:
        imported = third.execute("import", format="excel", path=exported.data["path"], entity="parameter",
                                 mode="replace")
        assert imported.ok, imported.errors
        rows = third.execute("list", entity="parameter").data
        assert [(r["name"], r["value"], r["people"]) for r in rows] == expected


# -- the migration ---------------------------------------------------------------------------------------------


def test_a_schema_8_database_gains_the_people_column_and_keeps_every_legacy_value(tmp_path, monkeypatch,
                                                                                  standards):
    """A 0.18.x database (no ``people`` column, a placeholder string per role) opens as 0.19.0: the column is
    added, no email is invented, every role is still filled verbatim and reported as legacy."""
    db = tmp_path / "kletz.db"
    with Brain(db) as before:
        for name, value in (("fusa_engineer", "Ann Lee"), ("tech_lead_functional_safety", LEGACY),
                            ("vehicle_type", "Wheel Loader")):
            before.service("parameter").repo.create({"name": name, "standard": "", "value": value, "uid": None})
        before.storage.stamp_uids(before.registry)
    conn = sqlite3.connect(db)
    conn.execute("ALTER TABLE parameter DROP COLUMN people")  # what a 0.18.x file looks like
    conn.commit()
    conn.close()
    with Brain(db) as after:
        assert after.migration["created"] == [] and after.migration["altered"] == {"parameter": ["people"]}
        rows = after.execute("list", entity="parameter").data
        assert [(r["name"], r["value"], r["people"]) for r in rows] == [
            ("fusa_engineer", "Ann Lee", None), ("tech_lead_functional_safety", LEGACY, None),
            ("vehicle_type", "Wheel Loader", None),
        ]
        assert after.execute("create", entity=PLAN, data={"order": 1, "deliverable": "Safety Plan", "ref_qf_17": 1}).ok
        preview = after.execute("plan", action="parameters", row=1)
        assert preview.ok and preview.data["standards"][0]["values"]["fusa_engineer"] == "Ann Lee"
        assert preview.data["standards"][0]["legacy_roles"] == ["fusa_engineer"]
        assert after.storage.audit_tail(1)[0]["action"] != "update"  # the migration edits no row
