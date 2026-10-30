"""Control structures (0.24.0, docs/control-structure-plan.md phase 2, moved here from the sister tool): the
seven entities, the service rules, the factory and its builders, the draw.io reader, the `cs` verbs, the
export through asi_escher with the OCR gate, the transfers and the migration. Every structure here is
synthetic, with invented names; the owner's real structure never enters the repository."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from openpyxl import load_workbook

from asi_kletz import Brain
from asi_kletz.automation.cli import main
from asi_kletz.brain import ENV_CONTROL_STRUCTURES
from asi_kletz.errors import NotFound, ValidationError
from asi_kletz.schema import (
    FieldSpec,
    FieldType,
    default_registry,
    definitions,  # noqa: F401  (registers the entities)
)
from asi_kletz.schema.lists import lines_of, list_of
from asi_kletz.services.control_structure_service import PART_ENTITIES
from asi_kletz.stpa import ControlStructureFactory, read_dataset_folder, read_drawio
from asi_kletz.stpa.drawio_reader import group_algorithms, group_entries, parse_entry, render_entry, unwrap
from asi_kletz.stpa.factory import DEFAULT_FORMATS, FORMATS, TEMPLATE_BUILDER
from asi_kletz.version import SCHEMA_VERSION, __version__
from tests.conftest import CS_TABLES, DB_0_23_0, EMPTY_COUNTS, HARA_TABLES, STPA_TABLES

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_DATASETS = REPO_ROOT.parent / "asi_standards" / "control-structures" / "wheel-loader" / "datasets"
CS_ENTITIES = ("control_structure", *PART_ENTITIES)
PARTS = ("controllers", "algorithms", "process_model_entries", "edges", "signals", "notes")


def edge(key: str, order: int, kind: str, source: str, target: str) -> dict:
    return {"key": key, "order": order, "kind": kind, "source": source, "target": target}


def synthetic() -> dict:
    """An eight-box structure with neutral invented names: two humans and controllers above a
    vehicle controller, a sensor, an actuator, the controlled process, an external system and the
    environment; nine arrows, ten signals, one note."""
    return {
        "structure": {"name": "Demo Loader Control Structure", "system": "Demo loader", "source": "synthetic"},
        "controllers": [
            {"key": "remote_operator", "order": 1, "name": "Remote Operator", "kind": "human_controller",
             "responsibility": "Starts and stops the mission.\nWatches the site.",
             "process_model_title": "Operator process model"},
            {"key": "site_supervisor", "order": 2, "name": "Site Supervisor", "kind": "controller",
             "responsibility": "Assigns work areas and clears them for the machine to enter when the ground is safe."},
            {"key": "vehicle_controller", "order": 3, "name": "Vehicle Controller", "kind": "controller",
             "responsibility": "Turns a mission into drive and tool commands.",
             "process_model_title": "Vehicle process model"},
            {"key": "perception", "order": 4, "name": "Perception Stack", "kind": "sensor",
             "responsibility": "Detects obstacles and people."},
            {"key": "drive_actuators", "order": 5, "name": "Drive Actuators", "kind": "actuator",
             "responsibility": "Moves the machine."},
            {"key": "loader_machine", "order": 6, "name": "Loader Machine", "kind": "controlled_process"},
            {"key": "fleet_server", "order": 7, "name": "Fleet Server", "kind": "external_system",
             "responsibility": "Keeps the mission plan."},
            {"key": "work_site", "order": 8, "name": "Work Site", "kind": "environment"},
        ],
        "algorithms": [
            {"controller": "remote_operator", "order": 1, "code": "O1", "name": "Mission start / stop decision"},
            {"controller": "vehicle_controller", "order": 1, "code": "V1", "name": "Path following"},
            {"controller": "vehicle_controller", "order": 2, "code": "V2",
             "name": "Safe stop on a lost heartbeat or a detected person"},
        ],
        "process_model_entries": [
            {"controller": "remote_operator", "order": 1, "heading": "CA-01 Mission start",
             "control_actions": ["CA-01"], "variables": ["Mission state", "Site clearance"],
             "updated_by": ["FB-01"], "references": ["CA-01", "FB-01"]},
            {"controller": "vehicle_controller", "order": 1, "heading": "CA-20 Drive command",
             "control_actions": ["CA-20"], "variables": ["Machine state", "Obstacle list"],
             "updated_by": ["FB-10", "FB-11"], "references": ["CA-20", "FB-10", "FB-11"]},
        ],
        "edges": [
            edge("e1", 1, "control_action", "remote_operator", "vehicle_controller"),
            edge("e2", 2, "feedback", "vehicle_controller", "remote_operator"),
            edge("e3", 3, "control_action", "site_supervisor", "vehicle_controller"),
            edge("e4", 4, "control_action", "vehicle_controller", "drive_actuators"),
            edge("e5", 5, "control_action", "drive_actuators", "loader_machine"),
            edge("e6", 6, "feedback", "loader_machine", "vehicle_controller"),
            edge("e7", 7, "feedback", "perception", "vehicle_controller"),
            edge("e8", 8, "control_action", "fleet_server", "vehicle_controller"),
            edge("e9", 9, "control_action", "loader_machine", "work_site"),
        ],
        "signals": [
            {"edge": "e1", "order": 1, "signal_id": "CA-01", "name": "Mission start"},
            {"edge": "e1", "order": 2, "signal_id": "CA-02", "name": "Mission stop"},
            {"edge": "e2", "order": 1, "signal_id": "FB-01", "name": "Mission state"},
            {"edge": "e3", "order": 1, "signal_id": "CA-10", "name": "Work area clearance"},
            {"edge": "e4", "order": 1, "signal_id": "CA-20", "name": "Drive command"},
            {"edge": "e5", "order": 1, "signal_id": "CA-30", "name": "Torque"},
            {"edge": "e6", "order": 1, "signal_id": "FB-10", "name": "Machine state"},
            {"edge": "e7", "order": 1, "signal_id": "FB-11", "name": "Obstacle list"},
            {"edge": "e8", "order": 1, "signal_id": "CA-X1", "name": "Mission plan", "placeholder": True},
            {"edge": "e9", "order": 1, "signal_id": "CA-40", "name": "Material moved"},
        ],
        "notes": [{"order": 1, "text": "Stops within 2 s of any fault", "attached_to": "vehicle_controller"}],
    }


COUNTS = {"controllers": 8, "algorithms": 3, "process_model_entries": 2, "edges": 9, "signals": 10, "notes": 1}
UP_HILL = "edge e8: control action from fleet_server points up the hierarchy to vehicle_controller"
LOADED_UP_HILL = "cs_edge 8: " + UP_HILL  # the same warning when the dataset is loaded whole: the row is named


@pytest.fixture
def built(brain):
    row, warnings = brain.control_structures.create_from_dataset(synthetic(), "test")
    assert warnings == [LOADED_UP_HILL]
    return brain, row


def without_order(dataset: dict) -> dict:
    """The controllers by key without their ``order``: the layout decides the order of a drawn file."""
    out = dict(dataset)
    out["controllers"] = sorted(
        ({k: v for k, v in c.items() if k != "order"} for c in dataset["controllers"]), key=lambda c: c["key"],
    )
    return out


def competent_ocr(monkeypatch):
    """The OCR gate answers 'competent' without the engine: the suite runs on CI without one."""
    from asi_escher.ocr import OcrReport

    calls = []

    def fake(png_path, expected, timeout=0):
        calls.append((png_path, list(expected)))
        return OcrReport(
            png=str(png_path), expected=list(expected), available=True, language="test", found=list(expected),
        )

    monkeypatch.setattr("asi_escher.ocr.ocr_check", fake)
    return calls


# -- entities and the JSON lists ---------------------------------------------------------------
def test_the_seven_entities_are_registered_with_their_sheets():
    assert [s.name for s in default_registry][-22:-15] == list(CS_ENTITIES)  # six STPA and nine HARA entities follow
    sheets = [default_registry.get(e).sheet for e in CS_ENTITIES]
    assert sheets == ["CS structures", "CS controllers", "CS algorithms", "CS process model", "CS edges", "CS signals",
                      "CS notes"]
    entry = default_registry.get("cs_process_model_entry")
    assert [f.name for f in entry.fields if f.type is FieldType.JSON] == [
        "control_actions", "variables", "updated_by", "references",
    ]
    assert all(default_registry.get(e).fields[-1].name == "uid" for e in CS_ENTITIES)
    assert default_registry.get("cs_controller").field("kind").lookup == "cs_controller_kind"
    assert FORMATS == ("drawio", "png", "svg") and DEFAULT_FORMATS == ("drawio", "png")
    assert SCHEMA_VERSION == 12


def test_json_fields_hold_lists(brain, tmp_path):
    from asi_escher import DEFAULT_FORMATS as ESCHER_DEFAULT
    from asi_escher import FORMATS as ESCHER_FORMATS

    assert FORMATS == ESCHER_FORMATS and DEFAULT_FORMATS == ESCHER_DEFAULT  # one enumeration shared with escher
    # the one reading of a list (schema/lists.py): a list as it is, a JSON array parsed, text one item per line
    assert list_of(None) == [] and list_of("") == [] and list_of(["a", "b"]) == ["a", "b"]
    assert list_of('["a", "b"]') == ["a", "b"] and list_of("a\nb\n\n c ") == ["a", "b", "c"]
    with pytest.raises(ValueError, match="not a JSON array"):
        list_of("[1, 2")
    assert list_of('{"a": 1}') == ['{"a": 1}']  # not an array: one item per line
    with pytest.raises(ValueError, match="not a list"):
        list_of(3)
    assert lines_of(["a", "b"]) == "a\nb" and lines_of('["x"]') == "x" and lines_of(None) == ""
    spec = FieldSpec("items", FieldType.JSON)
    assert spec.default is None and spec.sql_type == "TEXT"
    # stored as a JSON array in a text column (never NULL on a create), read back as a list, in the Excel cell as
    # its JSON text; the guard of the entity parses one item per line
    brain.execute("create", entity="control_structure", data={"name": "S"})
    brain.execute("create", entity="cs_controller", data={"structure": "s", "name": "C"})
    row = brain.execute("create", entity="cs_process_model_entry",
                        data={"structure": "s", "controller": "c", "variables": "x\ny", "updated_by": ["FB-1"]}).data
    assert row["variables"] == ["x", "y"] and row["updated_by"] == ["FB-1"] and row["references"] == []
    stored = brain.storage.fetchone("SELECT variables, control_actions FROM cs_process_model_entries")
    assert stored == {"variables": '["x", "y"]', "control_actions": "[]"}
    refused = brain.execute("update", entity="cs_process_model_entry", id=row["id"], data={"variables": "[1, 2"})
    assert not refused.ok and "variables" in refused.errors[0] and "not a JSON array" in refused.errors[0]
    path = brain.execute("export", format="excel", out=str(tmp_path / "v.xlsx")).data["path"]
    ws = load_workbook(path)["CS process model"]
    headers = [c.value for c in ws[1]]
    assert ws.cell(row=2, column=headers.index("variables") + 1).value == '["x", "y"]'
    assert ws.cell(row=2, column=headers.index("control actions") + 1).value == "[]"


# -- the factory and the service rules -------------------------------------------------------
def test_the_factory_builds_the_synthetic_structure(built):
    brain, row = built
    assert row["slug"] == "demo_loader_control_structure" and row["status"] == "Draft" and row["revision"] == 1
    assert row["counts"] == COUNTS
    assert brain.control_structures.counts(row["slug"]) == COUNTS
    events = [e for e in brain.events.last(200) if e["topic"] == "cs.changed"]
    assert len(events) == 1 and events[0]["action"] == "new" and events[0]["structure"] == row["slug"]
    audit = [a for a in brain.storage.audit_tail(200) if a["action"] == "cs.new"]
    assert len(audit) == 1 and audit[0]["payload"]["signals"] == 10
    assert len([a for a in brain.storage.audit_tail(200) if a["action"] == "create"]) == 1 + sum(COUNTS.values())
    # the dataset comes back as it went in (the structure's fields plus what the service defaulted)
    data = brain.control_structures.dataset(row["slug"])
    assert data["structure"] == {**synthetic()["structure"], "slug": row["slug"], "description": None,
                                 "status": "Draft", "revision": 1}
    assert [c["key"] for c in data["controllers"]] == [c["key"] for c in synthetic()["controllers"]]
    assert data["signals"][8]["placeholder"] is True and data["signals"][0]["placeholder"] is False
    assert data["signals"][0]["kind"] == "control_action" and data["signals"][2]["kind"] == "feedback"
    assert data["process_model_entries"][1]["updated_by"] == ["FB-10", "FB-11"]
    # resolve by id, uid or slug
    service = brain.control_structures
    assert service.resolve(row["id"])["id"] == service.resolve(str(row["id"]))["id"] == row["id"]
    assert service.resolve(row["uid"])["id"] == service.resolve(row["slug"])["id"] == row["id"]
    with pytest.raises(NotFound):
        service.resolve("no_such_slug")


def test_rules_of_the_parts(built):
    brain, row = built
    slug = row["slug"]

    def refused(entity, data, match):
        with pytest.raises(ValidationError, match=match):
            brain.service(entity).create(data, "test")

    refused("cs_controller", {"structure": "nope", "name": "X"}, "no control structure has the slug")
    refused("cs_controller", {"structure": slug, "name": "X", "key": "perception"}, "already a controller")
    refused("cs_controller", {"structure": slug, "name": "X", "kind": "wizard"}, "kind: 'wizard' is not one of")
    refused("cs_algorithm", {"structure": slug, "controller": "ghost", "code": "G1"}, "no controller of structure")
    refused("cs_process_model_entry", {"structure": slug, "controller": "ghost"}, "no controller of structure")
    refused("cs_edge", {"structure": slug, "source": "perception", "target": "ghost"}, "target: no controller")
    refused("cs_edge", {"structure": slug, "source": "perception", "target": "work_site", "kind": "lateral"},
            "kind: 'lateral' is not one of")
    refused("cs_signal", {"structure": slug, "edge": "e99", "signal_id": "CA-99"}, "no edge of structure")
    refused("cs_signal", {"structure": slug, "edge": "e1", "signal_id": "FB-99", "kind": "feedback"},
            "does not match edge e1, which carries control_action")
    refused("cs_signal", {"structure": slug, "edge": "e3", "signal_id": "CA-01"}, "already carried by edge e1")
    refused("cs_note", {"structure": slug, "text": "x", "attached_to": "ghost"}, "attached_to: no controller")
    # defaults: a controller's key from its name, an edge's key the next free one, a signal's kind its edge's
    c = brain.execute("create", entity="cs_controller", data={"structure": slug, "name": "Radio Link"}).data
    assert c["key"] == "radio_link" and c["kind"] == "controller" and c["order"] == 9
    e = brain.execute("create", entity="cs_edge",
                      data={"structure": slug, "source": "radio_link", "target": "work_site"})
    assert e.ok and e.data["key"] == "e10" and e.data["kind"] == "control_action" and e.data["order"] == 10
    assert e.warnings == [  # order 9 to order 8
        "edge e10: control action from radio_link points up the hierarchy to work_site",
    ]
    s = brain.execute("create", entity="cs_signal", data={"structure": slug, "edge": "e10", "signal_id": "CA-50"})
    assert s.ok and s.data["kind"] == "control_action" and s.data["placeholder"] is False and s.data["order"] == 1
    # the direction rule is a warning on an edge, never a refusal
    fb = brain.execute("create", entity="cs_edge",
                       data={"structure": slug, "kind": "feedback", "source": "remote_operator", "target": "work_site"})
    assert fb.ok and fb.warnings == ["edge e11: feedback from remote_operator points down the hierarchy to work_site"]
    # an edge cannot change kind under its signals, nor its key, and a controller cannot change its key when used
    def error(verb, **args):
        return brain.execute(verb, **args).errors[0]

    assert "carries CA-50" in error("update", entity="cs_edge", id=e.data["id"], set=["kind=feedback"])
    assert "signals point at it" in error("update", entity="cs_edge", id=e.data["id"], set=["key=e77"])
    assert "other rows point at it" in error("update", entity="cs_controller", id=c["id"], set=["key=rl"])
    # the structure's slug is immutable while parts exist, and unique
    assert "parts point at it" in error("update", entity="control_structure", id=row["id"], set=["slug=x"])
    assert "already the slug" in error("create", entity="control_structure", data={"name": "Other", "slug": slug})
    # every part change publishes cs.changed with the structure's slug
    changed = [ev for ev in brain.events.last(20) if ev["topic"] == "cs.changed"]
    assert changed[-1] == {**changed[-1], "structure": slug, "entity": "cs_edge", "action": "create"}


def test_direction_is_a_warning_the_dataset_reports(brain):
    data = synthetic()
    data["edges"].append(edge("e10", 10, "feedback", "remote_operator", "work_site"))
    _, warnings = brain.control_structures.create_from_dataset(data, "test")
    assert warnings == [
        LOADED_UP_HILL, "cs_edge 10: edge e10: feedback from remote_operator points down the hierarchy to work_site",
    ]


def test_duplicate_signal_ids_in_a_file_are_warnings_and_validate_repeats_them(brain):
    data = synthetic()
    data["signals"].append({"edge": "e3", "order": 2, "signal_id": "CA-01", "name": "Mission start again"})
    row, warnings = brain.control_structures.create_from_dataset(data, "test")
    assert warnings == [LOADED_UP_HILL, "cs_signal 11: signal_id: 'CA-01' is already carried by edge e1"]
    assert row["counts"]["signals"] == 11
    report = brain.execute("cs", action="validate", target=row["slug"])
    assert report.ok and "signal CA-01 is carried by 2 edges: e1, e3" in report.warnings


def test_a_signal_shared_by_two_edges_from_one_controller_is_information(brain):
    """One feedback to two receivers (the owner's structure has two such) is legitimate: no warning when
    the file is loaded, no refusal when typed, ``info`` in the validate report; a twin on an edge from
    another controller stays a duplicate id."""
    data = synthetic()
    data["edges"].append(edge("e10", 10, "feedback", "perception", "site_supervisor"))
    data["signals"].append({"edge": "e10", "order": 1, "signal_id": "FB-11", "name": "Obstacle list"})
    row, warnings = brain.control_structures.create_from_dataset(data, "test")
    assert warnings == [LOADED_UP_HILL]  # no duplicate warning: e7 and e10 both leave perception
    report = brain.execute("cs", action="validate", target=row["slug"])
    assert report.ok and report.warnings == [UP_HILL]
    assert report.data["info"] == ["signal FB-11 is shared by 2 edges from perception: e7, e10"]
    # typed: the same, allowed
    brain.execute("create", entity="cs_edge", data={"structure": row["slug"], "key": "e11", "kind": "feedback",
                                                    "source": "perception", "target": "remote_operator"})
    typed = brain.execute("create", entity="cs_signal", data={"structure": row["slug"], "edge": "e11",
                                                              "signal_id": "FB-11", "name": "Obstacle list"})
    assert typed.ok and typed.warnings == []
    assert brain.execute("cs", action="validate", target=row["slug"]).data["info"] == [
        "signal FB-11 is shared by 3 edges from perception: e7, e10, e11"
    ]
    # from another controller: a refusal typed, a warning loaded, and validate says so
    refused = brain.execute("create", entity="cs_signal", data={"structure": row["slug"], "edge": "e2",
                                                                "signal_id": "FB-11", "name": "Obstacle list"})
    assert not refused.ok and "already carried by edge e10, e11, e7" in refused.errors[0]
    data["signals"].append({"edge": "e2", "order": 2, "signal_id": "FB-11", "name": "Obstacle list"})
    row2, warnings = brain.control_structures.create_from_dataset(data, "test", name="Other", slug="other")
    assert warnings == [LOADED_UP_HILL, "cs_signal 12: signal_id: 'FB-11' is already carried by edge e10, e7"]
    report = brain.execute("cs", action="validate", target="other")
    assert "signal FB-11 is carried by 3 edges: e2, e7, e10" in report.warnings and report.data["info"] == []


def test_delete_is_refused_without_cascade_and_cascades_with_it(built):
    brain, row = built
    slug = row["slug"]
    controller = brain.service("cs_controller").repo.list({"structure": slug, "key": "vehicle_controller"})[0]
    refused = brain.execute("delete", entity="cs_controller", id=controller["id"])
    assert not refused.ok and "2 cs_algorithm, 1 cs_process_model_entry, 7 cs_edge, 8 cs_signal" in refused.errors[0]
    assert brain.control_structures.counts(slug) == COUNTS  # nothing went
    gone = brain.execute("delete", entity="cs_controller", id=controller["id"], cascade=True)
    assert gone.ok
    assert brain.control_structures.counts(slug) == {
        "controllers": 7, "algorithms": 1, "process_model_entries": 1, "edges": 2, "signals": 2, "notes": 1,
    }
    note = brain.service("cs_note").repo.list({"structure": slug})[0]
    assert note["attached_to"] is None  # the note stays, detached
    cascade = [a for a in brain.storage.audit_tail(50) if a["action"] == "cs.cascade"]
    assert cascade[0]["payload"] == {"structure": slug, "key": "vehicle_controller", "cs_algorithm": 2,
                                     "cs_process_model_entry": 1, "cs_edge": 7, "cs_signal": 8}
    # an edge with signals, likewise
    edge = brain.service("cs_edge").repo.list({"structure": slug, "key": "e5"})[0]
    assert "carries 1 signal" in brain.execute("delete", entity="cs_edge", id=edge["id"]).errors[0]
    assert brain.execute("delete", entity="cs_edge", id=edge["id"], cascade=True).ok
    assert brain.control_structures.counts(slug)["signals"] == 1
    # the structure itself: `cs delete` and the generic verb agree
    assert "delete with --cascade" in brain.execute("cs", action="delete", target=slug).errors[0]
    assert "delete with --cascade" in brain.execute("delete", entity="control_structure", id=row["id"]).errors[0]
    result = brain.execute("cs", action="delete", target=slug, cascade=True)
    assert result.ok and result.data["deleted"] == {"control_structure": 1, "controllers": 7, "algorithms": 1,
                                                    "process_model_entries": 1, "edges": 1, "signals": 1, "notes": 1}
    assert all(brain.service(e).count() == 0 for e in CS_ENTITIES)
    assert brain.events.last(1)[0]["topic"] == "cs.changed" and brain.events.last(1)[0]["action"] == "delete"
    # an empty structure goes without cascade; a plan row never needs the flag
    empty = brain.execute("create", entity="control_structure", data={"name": "Empty"}).data
    assert brain.execute("delete", entity="control_structure", id=empty["id"]).ok
    plan = brain.execute("create", entity="safety_plan_row", data={"deliverable": "x"}).data
    assert brain.execute("delete", entity="safety_plan_row", id=plan["id"]).ok


def test_duplicate_is_a_deep_copy_under_a_new_slug(built):
    brain, row = built
    copy, warnings = brain.control_structures.duplicate(row["slug"], "Demo Loader Copy", actor="test")
    assert warnings == [LOADED_UP_HILL] and copy["slug"] == "demo_loader_copy" and copy["counts"] == COUNTS
    assert copy["status"] == "Draft" and copy["revision"] == 1 and copy["source"] == f"duplicate of {row['slug']}"
    a, b = brain.control_structures.dataset(row["slug"]), brain.control_structures.dataset(copy["slug"])
    assert {k: a[k] for k in PARTS} == {k: b[k] for k in PARTS}
    assert len({r["uid"] for r in brain.service("cs_signal").list()}) == 20  # fresh identities
    assert brain.execute("cs", action="duplicate", target=row["id"], name="Third", slug="t3").data["slug"] == "t3"
    assert "needs --name" in brain.execute("cs", action="duplicate", target=row["id"]).errors[0]
    # the clone builder is the same copy
    clone, _ = brain.factory.create("clone", "test", path=row["slug"], name="Fourth")
    assert clone["slug"] == "fourth" and clone["counts"] == COUNTS
    assert brain.execute("count", entity="control_structure").data["count"] == 4


def test_validate_reports_what_the_rows_broke(built):
    brain, row = built
    ok = brain.execute("cs", action="validate", target=row["slug"])
    assert ok.ok and ok.data["errors"] == [] and ok.warnings == [UP_HILL] and ok.data["counts"] == COUNTS
    # break rows behind the service's back (as a hand-edited workbook could) and read the report
    repo = brain.service("cs_signal").repo
    signal = repo.list({"structure": row["slug"], "signal_id": "FB-10"})[0]
    repo.update(signal["id"], {"kind": "control_action"})
    entry = brain.service("cs_process_model_entry").repo.list({"structure": row["slug"]})[0]
    brain.service("cs_process_model_entry").repo.update(entry["id"], {"updated_by": '["FB-77 Unknown"]'})
    note = brain.service("cs_note").repo.list({"structure": row["slug"]})[0]
    brain.service("cs_note").repo.update(note["id"], {"attached_to": "ghost"})
    bad = brain.execute("cs", action="validate", target=row["slug"])
    assert not bad.ok
    assert bad.errors == [
        "signal FB-10: kind 'control_action' does not match edge e6 (feedback)",
        f"note {note['id']}: attached to 'ghost', which does not exist",
    ]
    assert "process model entry 'CA-01 Mission start' names FB-77 in updated_by, which no edge carries" in bad.warnings


# -- the verbs -------------------------------------------------------------------------------
def test_every_cs_verb_answers_a_result(built, tmp_path, monkeypatch, capsys):
    brain, row = built
    competent_ocr(monkeypatch)
    listed = brain.execute("cs", action="list")
    assert listed.ok and [r["slug"] for r in listed.data] == [row["slug"]] and listed.data[0]["counts"] == COUNTS
    got = brain.execute("cs", action="get", target=row["slug"])
    assert got.ok and got.data["counts"] == COUNTS
    assert [c["key"] for c in got.data["parts"]["controllers"]][0] == "remote_operator"
    builders = brain.execute("cs", action="builders").data["builders"]
    assert [b["name"] for b in builders] == ["blank", TEMPLATE_BUILDER, "from_drawio", "from_datasets", "clone"]
    template = next(b for b in builders if b["name"] == TEMPLATE_BUILDER)
    assert template["available"] is False and "no datasets at" in template["reason"]
    assert all(b["available"] for b in builders if b["name"] != TEMPLATE_BUILDER)
    assert ControlStructureFactory.builders() == [b["name"] for b in builders]
    blank = brain.execute("cs", action="new", target="blank", name="Blank One", system="Nothing yet")
    assert blank.ok and blank.data["slug"] == "blank_one" and blank.data["source"] == "built by hand"
    assert blank.data["counts"] == dict.fromkeys(PARTS, 0)
    assert "needs --name" in brain.execute("cs", action="new", target="blank").errors[0]
    assert "unavailable" in brain.execute("cs", action="new", target=TEMPLATE_BUILDER).errors[0]
    assert "unknown builder" in brain.execute("cs", action="new", target="magic").errors[0]
    assert "needs a builder" in brain.execute("cs", action="new").errors[0]
    assert "needs a structure" in brain.execute("cs", action="get").errors[0]
    assert "not found" in brain.execute("cs", action="get", target="nope").errors[0]
    exported = brain.execute("cs", action="export", target=row["slug"], out=str(tmp_path / "out"))
    assert exported.ok and exported.data["ocr_verdict"] == "competent"
    # the command line prints the same Result; --format repeats; a bare --no-ocr is true
    code = main(["--db", brain.db_path, "cs", "export", row["slug"], "--out", str(tmp_path / "cli"),
                 "--format", "svg", "--format", "drawio", "--no-ocr"])
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and printed["ok"] and printed["data"]["formats"] == ["svg", "drawio"]
    assert printed["data"]["ocr_verdict"] == "ocr skipped" and sorted(printed["data"]["paths"]) == ["drawio", "svg"]
    assert (tmp_path / "cli" / f"{row['slug']}.svg").is_file()
    assert not (tmp_path / "cli" / f"{row['slug']}.png").exists()
    code = main(["--db", brain.db_path, "cs", "validate", row["slug"]])
    assert code == 0 and json.loads(capsys.readouterr().out)["warnings"] == [UP_HILL]
    assert "cs" in brain.status()["commands"]


def test_export_writes_drawio_and_png_by_default_through_the_ocr_gate(built, tmp_path, monkeypatch):
    brain, row = built
    calls = competent_ocr(monkeypatch)
    out = tmp_path / "exported"
    result = brain.execute("cs", action="export", target=row["id"], out=str(out))
    assert result.ok, result.errors
    data = result.data
    assert data["formats"] == ["drawio", "png"] and sorted(data["paths"]) == ["drawio", "png"]
    assert data["files"] == [str(out / f"{row['slug']}.drawio"), str(out / f"{row['slug']}.png")]
    assert all(Path(f).is_file() for f in data["files"]) and data["primary"].endswith(".png")
    assert data["nodes"] == 9 and data["edges"] == 9 and data["size"][0] > 100  # eight boxes and the note
    assert data["ocr_verdict"] == "competent" and data["ocr"]["competent"] and data["ocr"]["missing"] == []
    assert data["layout_issues"] == [] and result.warnings == []
    # the gate read the PNG that was written and expected every box title, code, title and signal id
    assert len(calls) == 1 and calls[0][0] == data["paths"]["png"]
    expected = calls[0][1]
    assert {"Remote Operator", "Work Site", "O1", "V2", "Operator process model", "CA-01", "FB-11"} <= set(expected)
    # the draw.io file is escher's, with its provenance comment, every controller a cell of its key
    text = Path(data["paths"]["drawio"]).read_text(encoding="utf-8")
    assert 'host="asi_escher"' in text and "Generated by asi_escher" in text
    assert all(f'id="{c["key"]}"' in text for c in synthetic()["controllers"])
    assert "CA-01 Mission start&lt;br&gt;CA-02 Mission stop" in text.replace("<br>", "&lt;br&gt;")
    # audited and published with the files and the verdict
    audit = [a for a in brain.storage.audit_tail(5) if a["action"] == "cs.export"]
    assert audit and audit[0]["payload"]["ocr_verdict"] == "competent" and audit[0]["entity_id"] == row["id"]
    event = [e for e in brain.events.last(5) if e["topic"] == "cs.exported"][0]
    assert event["structure"] == row["slug"] and sorted(event["paths"]) == ["drawio", "png"]
    # --all writes the three; a format outside the set is refused
    everything = brain.execute("cs", action="export", target=row["slug"], out=str(out), all=True)
    assert everything.ok and everything.data["formats"] == ["drawio", "png", "svg"]
    assert (out / f"{row['slug']}.svg").is_file()
    refused = brain.execute("cs", action="export", target=row["slug"], out=str(out), format=["pdf"])
    assert "format must be one of" in refused.errors[0]
    # without a --out the files go under the out folder
    default = brain.execute("cs", action="export", target=row["slug"], no_ocr=True)
    assert default.ok and default.data["out"] == str(Path(brain.out_dir) / "control_structures")


def test_an_unreadable_label_is_an_issue_and_a_warning(built, tmp_path, monkeypatch):
    from asi_escher.ocr import OcrReport

    brain, row = built

    def half_blind(png_path, expected, timeout=0):
        return OcrReport(png=str(png_path), expected=list(expected), available=True, language="test",
                         found=list(expected)[1:], missing=list(expected)[:1])

    monkeypatch.setattr("asi_escher.ocr.ocr_check", half_blind)
    result = brain.execute("cs", action="export", target=row["slug"], out=str(tmp_path))
    assert result.ok and result.data["ocr_verdict"].startswith("unreadable: ")
    assert result.data["layout_issues"] == [] and [i["kind"] for i in result.data["issues"]] == ["ocr"]
    assert result.warnings == [result.data["issues"][0]["message"]]

    def unavailable(png_path, expected, timeout=0):
        return OcrReport(png=str(png_path), expected=list(expected), error="no engine")

    monkeypatch.setattr("asi_escher.ocr.ocr_check", unavailable)
    result = brain.execute("cs", action="export", target=row["slug"], out=str(tmp_path))
    assert result.ok and result.data["ocr_verdict"] == "ocr unavailable: no engine"
    assert result.warnings == ["ocr unavailable: no engine"]


def test_the_real_ocr_engine_finds_the_synthetic_structure_competent(built, tmp_path):
    """The one test on the real engine (Windows.Media.Ocr through PowerShell); skipped where it is absent."""
    brain, row = built
    result = brain.execute("cs", action="export", target=row["slug"], out=str(tmp_path))
    assert result.ok, result.errors
    if not result.data["ocr"]["available"]:
        pytest.skip(result.data["ocr_verdict"])
    assert result.data["ocr_verdict"] == "competent", result.data["ocr"]["missing"]


# -- the draw.io reader and the round trip ---------------------------------------------------
def test_unwrap_undoes_a_greedy_word_wrap():
    import textwrap

    text = "Assigns work areas and clears them for the machine to enter when the ground is safe."
    assert unwrap(textwrap.wrap(text, 42)) == [text]
    lines = ["Starts and stops the mission.", "Watches the site."]  # explicit breaks stay breaks
    assert unwrap(lines) == lines
    assert unwrap(["V1 Path following", "V2 Safe stop on a lost heartbeat or a", "detected person"]) == [
        "V1 Path following", "V2 Safe stop on a lost heartbeat or a detected person",
    ]
    full = "x" * 38 + " CA-"  # 42 characters, broken after the hyphen the way textwrap breaks
    assert unwrap([full, "02 at the end"]) == [full + "02 at the end"]
    assert group_algorithms(["V1 Path following", "V2 Safe stop on a lost heartbeat or a", "detected person"]) == [
        "V1 Path following", "V2 Safe stop on a lost heartbeat or a detected person",
    ]
    lines = ["Vehicle process", "model", "- CA-20 Drive: Machine state;", "Obstacle list", "- CA-21 Stop"]
    assert group_entries(lines) == (
        "Vehicle process model", ["CA-20 Drive: Machine state; Obstacle list", "CA-21 Stop"],
    )
    assert group_entries(["Only a title"]) == ("Only a title", [])
    entry = {
        "heading": "CA-20 Drive command", "variables": ["Machine state", "Obstacle list"],
        "updated_by": ["FB-10", "FB-11"],
    }
    line = render_entry(entry)
    assert line == "CA-20 Drive command: Machine state; Obstacle list; updated by FB-10, FB-11"
    assert parse_entry(line) == {**entry, "control_actions": ["CA-20"], "references": ["CA-20", "FB-10", "FB-11"]}
    assert render_entry({"heading": "Only a heading"}) == "Only a heading"
    assert parse_entry("Only a heading")["variables"] == []


def test_round_trip_through_escher_yields_the_same_rows(built, tmp_path, monkeypatch):
    brain, row = built
    competent_ocr(monkeypatch)
    exported = brain.execute("cs", action="export", target=row["slug"], out=str(tmp_path))
    drawio = exported.data["paths"]["drawio"]
    read = read_drawio(drawio)
    assert read["structure"] == {"name": "Demo Loader Control Structure", "source": Path(drawio).name}
    assert read["warnings"] == []
    imported = brain.execute("cs", action="import", target=drawio, name="Round Trip")
    assert imported.ok and imported.data["counts"] == COUNTS
    assert all("hierarchy" in w for w in imported.warnings)  # the layout's order decides what points up
    before = brain.control_structures.dataset(row["slug"])
    after = brain.control_structures.dataset("round_trip")
    # the drawing orders the boxes by hierarchy, so `order` is the layout's; every other value is equal:
    # keys, names, kinds, responsibilities (their line breaks too), algorithms, process models, edges, signals
    assert without_order(before)["controllers"] == without_order(after)["controllers"]
    for key in ("algorithms", "process_model_entries", "edges", "signals", "notes"):
        assert before[key] == after[key], key
    assert after["structure"]["source"] == Path(drawio).name
    # the factory draws the import exactly as it drew the source
    a, b = brain.factory.to_diagram(row["slug"]).to_dict(), brain.factory.to_diagram("round_trip").to_dict()
    b["title"] = a["title"]
    for spec in (a, b):
        spec["nodes"].sort(key=lambda n: n["id"])  # the boxes are listed in their stored order
    assert a == b


def test_to_diagram_is_the_one_place_rows_become_a_drawing(built):
    brain, row = built
    d = brain.factory.to_diagram(row["slug"])
    assert d.kind == "control_structure" and d.title == row["name"]
    vehicle = d.nodes["vehicle_controller"]
    assert vehicle.kind == "controller"
    assert vehicle.algorithms == [
        ("V1", "Path following"), ("V2", "Safe stop on a lost heartbeat or a detected person"),
    ]
    assert vehicle.process_model == ("Vehicle process model",
                                     ["- CA-20 Drive command: Machine state; Obstacle list; updated by FB-10, FB-11"])
    assert d.nodes["loader_machine"].kind == "controlled_process" and d.nodes["loader_machine"].process_model is None
    assert d.nodes["note_1"].kind == "note" and d.nodes["note_1"].attached_to == "vehicle_controller"
    edges = [(e.src, e.dst, e.kind, e.signals) for e in d.edges]
    assert edges[0] == ("remote_operator", "vehicle_controller", "control_action",
                        ["CA-01 Mission start", "CA-02 Mission stop"])
    assert edges[1] == ("vehicle_controller", "remote_operator", "feedback", ["FB-01 Mission state"])
    assert len(edges) == 9


HAND_DRAWN = """<mxfile host="Electron" type="device"><diagram id="d1" name="Drawn Structure"><mxGraphModel><root>
<mxCell id="0"/><mxCell id="1" parent="0"/>
<mxCell id="box1" value="Operator" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1">
  <mxGeometry x="0" y="0" width="320" height="220" as="geometry"/></mxCell>
<mxCell id="box1r" value="Responsibility&lt;br&gt;Runs the show.&lt;br&gt;Keeps watch." style="text;html=1;" vertex="1"
  parent="1">
  <mxGeometry x="10" y="30" width="200" height="50" as="geometry"/></mxCell>
<mxCell id="box1a" value="O1 &#8212; Decide" style="rounded=0;" vertex="1" parent="1">
  <mxGeometry x="10" y="90" width="120" height="30" as="geometry"/></mxCell>
<mxCell id="box1p" value="PROCESS_MODEL" style="text;html=1;" vertex="1" parent="1">
  <mxGeometry x="10" y="130" width="300" height="80" as="geometry"/></mxCell>
<mxCell id="box2" value="Machine" style="shape=ext;double=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
  <mxGeometry x="0" y="320" width="320" height="100" as="geometry"/></mxCell>
<mxCell id="box3" value="Yard" style="rounded=0;dashed=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
  <mxGeometry x="0" y="500" width="320" height="60" as="geometry"/></mxCell>
<mxCell id="free" value="A free note" style="text;html=1;" vertex="1" parent="1">
  <mxGeometry x="420" y="330" width="100" height="40" as="geometry"/></mxCell>
<mxCell id="arrow1" value="CA-01 Start&lt;br&gt;CA-02 Stop&lt;br&gt;Not a signal" style="edgeStyle=orthogonalEdgeStyle;"
  edge="1" parent="1" source="box1" target="box2">
  <mxGeometry relative="1" as="geometry"/></mxCell>
<mxCell id="arrow2" value="FB-01 State&lt;br&gt;FB-WL-3 Map" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1"
  source="box2" target="box1">
  <mxGeometry relative="1" as="geometry"/></mxCell>
<mxCell id="arrow3" value="CA-40 Move" edge="1" parent="1" source="box2" target="box3">
  <mxGeometry relative="1" as="geometry"/></mxCell>
</root></mxGraphModel></diagram></mxfile>
""".replace("PROCESS_MODEL", "&lt;br&gt;".join([
    "Operator process model", "CA-01/02 Start and stop", "&#8226; Variables: Mission state; Site (north, south)",
    "&#8226; Updated by FB-01 State, FB-02 Map", "&#8226; Stale after 5 s",
]))


def test_the_reader_ports_the_hand_drawn_parser(tmp_path, brain):
    file = tmp_path / "drawn.drawio"
    file.write_text(HAND_DRAWN, encoding="utf-8")
    data = read_drawio(file, kinds={"Yard": "environment"})
    assert data["structure"] == {"name": "Drawn Structure", "source": "drawn.drawio"}
    assert [(c["key"], c["order"], c["kind"]) for c in data["controllers"]] == [
        ("operator", 1, "controller"), ("machine", 2, "controlled_process"), ("yard", 3, "environment"),
    ]
    assert data["controllers"][0]["responsibility"] == "Runs the show.\nKeeps watch."
    assert data["controllers"][0]["process_model_title"] == "Operator process model"
    assert data["algorithms"] == [{"controller": "operator", "order": 1, "code": "O1", "name": "Decide"}]
    assert data["process_model_entries"] == [{
        "controller": "operator", "heading": "CA-01/02 Start and stop", "order": 1,
        "variables": ["Mission state", "Site (north, south)", "Stale after 5 s"],
        "updated_by": ["FB-01 State", "FB-02 Map"],
        "control_actions": ["CA-01", "CA-02"], "references": ["CA-01", "CA-02", "FB-01", "FB-02"],
    }]
    assert [(e["key"], e["kind"], e["source"], e["target"]) for e in data["edges"]] == [
        ("arrow1", "control_action", "operator", "machine"), ("arrow2", "feedback", "machine", "operator"),
        ("arrow3", "control_action", "machine", "yard"),
    ]
    assert [(s["edge"], s["signal_id"], s["name"], s["placeholder"]) for s in data["signals"]] == [
        ("arrow1", "CA-01", "Start", False), ("arrow1", "CA-02", "Stop", False),
        ("arrow2", "FB-01", "State", False), ("arrow2", "FB-WL-3", "Map", True), ("arrow3", "CA-40", "Move", False),
    ]
    assert data["notes"] == [{"order": 1, "text": "A free note", "attached_to": "machine"}]
    assert data["warnings"] == ["edge arrow1: line 'Not a signal' is not a signal (CA-xx / FB-xx); skipped"]
    # the builder reads it, keeps the reader's warnings first, and the structure validates
    result = brain.execute("cs", action="new", target="from_drawio", **{"from": str(file)})
    assert result.ok and result.data["counts"] == {"controllers": 3, "algorithms": 1, "process_model_entries": 1,
                                                   "edges": 3, "signals": 5, "notes": 1}
    assert result.warnings[0] == data["warnings"][0]
    assert brain.execute("cs", action="validate", target=result.data["slug"]).ok
    with pytest.raises(NotFound, match="file not found"):
        read_drawio(tmp_path / "missing.drawio")
    (tmp_path / "x.drawio").write_text("<html/>", encoding="utf-8")
    with pytest.raises(NotFound, match="no <mxfile> root"):
        read_drawio(tmp_path / "x.drawio")


def write_envelope_folder(folder: Path, data: dict) -> Path:
    """The six JSON files as the owner's script writes them, from a plain dataset."""
    folder.mkdir(parents=True, exist_ok=True)
    keys = {c["key"]: c for c in data["controllers"]}
    files = {
        "controllers": [
            {"id": c["key"], "order": c["order"], "name": c["name"], "kind": c["kind"],
             "responsibility": c.get("responsibility", ""),
             "responsibility_lines": (c.get("responsibility") or "").split("\n"),
             "process_model_title": c.get("process_model_title", ""), "note": "", "cell_id": f"cell-{c['key']}"}
            for c in data["controllers"]
        ],
        "algorithms": [
            {"id": a["code"], "controller_id": a["controller"], "order": a["order"], "name": a["name"], "cell_id": "x"}
            for a in data["algorithms"]
        ],
        "process_model_entries": [
            {"id": f"{p['controller']}.pm.{p['order']:02d}", "controller_id": p["controller"], "heading": p["heading"],
             "control_actions": p["control_actions"], "variables": p["variables"], "updated_by": p["updated_by"],
             "items": [], "references": p["references"], "raw_lines": [p["heading"]], "cell_id": "y"}
            for p in data["process_model_entries"]
        ],
        "signals": [
            {"id": f"{s['signal_id']}@{s['edge']}", "signal_id": s["signal_id"], "kind": s.get("kind"),
             "name": s["name"], "source_id": None, "target_id": None, "edge_id": s["edge"],
             "placeholder": bool(s.get("placeholder")), "appears_on_edges": 1, "name_conflict": False}
            for s in data["signals"]
        ],
        "edges": [
            {"id": e["key"], "kind": e["kind"], "source_id": e["source"], "target_id": e["target"],
             "signal_ids": [s["signal_id"] for s in data["signals"] if s["edge"] == e["key"]], "label": ""}
            for e in data["edges"]
        ],
        "notes": [
            {"id": "note.1", "text": n["text"], "attached_to": n["attached_to"], "cell_id": "z"} for n in data["notes"]
        ],
    }
    assert set(keys)
    for entity, rows in files.items():
        (folder / f"{entity}.json").write_text(json.dumps({
            "schema_version": 1, "exported_at": "2026-10-29T00:00:00+00:00", "source": "synthetic.drawio",
            "entity": entity, "row_count": len(rows), "rows": rows,
        }, indent=2), encoding="utf-8")
    return folder


def test_from_datasets_and_the_template_builder_on_a_synthetic_folder(tmp_path, brain, monkeypatch):
    folder = write_envelope_folder(tmp_path / "shelf" / "wheel-loader" / "datasets", synthetic())
    data = read_dataset_folder(folder)
    assert data["structure"] == {"name": "datasets", "source": str(folder)} and data["warnings"] == []
    original = synthetic()
    for key in PARTS:
        wanted = [{**r} for r in original[key]]
        for r in wanted:
            r.setdefault("placeholder", False) if key == "signals" else None
            r.setdefault("kind", None) if key == "signals" else None
        if key == "signals":
            for r in wanted:
                r["kind"] = r["kind"] or next(e["kind"] for e in original["edges"] if e["key"] == r["edge"])
        if key == "controllers":
            for r in wanted:
                r.setdefault("responsibility", ""), r.setdefault("process_model_title", ""), r.setdefault("note", "")
        assert data[key] == wanted, key
    # `cs import <folder>` and the from_datasets builder
    imported = brain.execute("cs", action="import", target=str(folder), name="From Files")
    assert imported.ok and imported.data["counts"] == COUNTS and imported.data["source"] == str(folder)
    missing = brain.execute("cs", action="new", target="from_datasets", **{"from": str(tmp_path / "no")})
    assert "folder not found" in missing.errors[0]
    (tmp_path / "half").mkdir()
    shutil.copy(folder / "controllers.json", tmp_path / "half" / "controllers.json")
    assert "has no edges.json" in brain.execute("cs", action="import", target=str(tmp_path / "half")).errors[0]
    # the template builder: unavailable here, available once the shelf is pointed at (config or env)
    assert "unavailable" in brain.execute("cs", action="new", target=TEMPLATE_BUILDER).errors[0]
    monkeypatch.setenv(ENV_CONTROL_STRUCTURES, str(tmp_path / "shelf"))
    with Brain(tmp_path / "shelf.db") as other:
        assert other.control_structures_dir == str(tmp_path / "shelf")
        catalog = {b["name"]: b for b in other.factory.catalog()}
        assert catalog[TEMPLATE_BUILDER]["available"] is True
        made = other.execute("cs", action="new", target=TEMPLATE_BUILDER)
        assert made.ok and made.data["counts"] == COUNTS and made.warnings == [LOADED_UP_HILL]
        assert made.data["name"] == "Wheel Loader Master Control Structure" and made.data["source"] == str(folder)
        assert made.data["slug"] == "wheel_loader_master_control_structure"
        renamed = other.execute("cs", action="new", target=TEMPLATE_BUILDER, name="Second", system="Loader B")
        assert renamed.ok and renamed.data["slug"] == "second" and renamed.data["system"] == "Loader B"
        assert other.status()["control_structures_dir"] == str(tmp_path / "shelf")
    # through kletz.toml, resolved against the file
    config = tmp_path / "kletz.toml"
    config.write_text('db = "cfg.db"\ncontrol_structures_dir = "shelf"\n', encoding="utf-8")
    monkeypatch.delenv(ENV_CONTROL_STRUCTURES)
    monkeypatch.setenv("ASI_KLETZ_CONFIG", str(config))
    with Brain(tmp_path / "cfg.db") as other:
        assert Path(other.control_structures_dir) == (tmp_path / "shelf").resolve()
        assert other.execute("cs", action="builders").data["builders"][1]["available"] is True
    # without either: the sibling shelf beside the config file (or the working directory), never read here
    monkeypatch.setenv("ASI_KLETZ_CONFIG", str(tmp_path / "absent.toml"))
    with Brain(tmp_path / "bare.db") as other:
        assert Path(other.control_structures_dir).name == "control-structures"


# -- transfers and the migration -------------------------------------------------------------
def test_dump_load_and_workbook_carry_the_seven_entities(built, tmp_path):
    brain, row = built
    before = brain.control_structures.dataset(row["slug"])
    dump = tmp_path / "dump.json"
    dumped = brain.execute("dump", out=str(dump))
    assert dumped.ok and {k: dumped.data["entities"][k] for k in CS_ENTITIES} == {
        "control_structure": 1, "cs_controller": 8, "cs_algorithm": 3, "cs_process_model_entry": 2,
        "cs_edge": 9, "cs_signal": 10, "cs_note": 1,
    }
    payload = json.loads(dump.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["entities"]["cs_process_model_entry"][0]["variables"] == ["Mission state", "Site clearance"]
    with Brain(tmp_path / "loaded.db") as other:
        loaded = other.execute("load", path=str(dump), mode="replace")
        assert loaded.ok, loaded.errors
        assert other.control_structures.dataset(row["slug"]) == before
        assert other.service("cs_signal").get_by_uid(brain.service("cs_signal").list()[0]["uid"])
    workbook = brain.execute("export", format="excel", out=str(tmp_path / "cs.xlsx"))
    assert workbook.ok and workbook.data["entities"]["cs_signal"] == 10
    with Brain(tmp_path / "sheet.db") as other:
        imported = other.execute("import", format="excel", path=workbook.data["path"], mode="replace")
        assert imported.ok, imported.errors
        assert other.control_structures.dataset(row["slug"]) == before
        assert other.execute("cs", action="validate", target=row["slug"]).ok


def test_a_schema_10_database_opens_as_0_24_0_with_the_thirteen_tables_added(tmp_path):
    db = tmp_path / "kletz.db"
    shutil.copy(DB_0_23_0, db)
    con = sqlite3.connect(db)
    before = {
        name: [dict(zip([c[0] for c in cur.description], r, strict=True)) for r in cur.fetchall()]
        for name in ("safety_plan", "parameter")
        for cur in [con.execute(f'SELECT * FROM "{name}"')]
    }
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "control_structures" not in tables and len(before["safety_plan"]) == 3 and len(before["parameter"]) == 1
    with Brain(db) as b:
        # the seven control-structure tables and the six STPA tables after them, nothing altered, no row touched
        assert b.migration["created"] == [*CS_TABLES, *STPA_TABLES, *HARA_TABLES]
        assert b.migration["altered"] == {} and b.migration["uids_stamped"] == EMPTY_COUNTS
        migrations = b.storage.fetchall("SELECT app_version FROM schema_migrations ORDER BY version")
        versions = [m["app_version"] for m in migrations]
        assert versions == ["0.23.0", __version__] and b.status()["schema_version"] == SCHEMA_VERSION == 12
        assert b.execute("cs", action="list").data == [] and b.execute("stpa", action="list").data == []
        assert b.execute("list", entity="safety_plan_row").data[0]["deliverable"] == "Safety Plan"
        made = b.control_structures.create_from_dataset(synthetic(), "test")[0]
        assert made["counts"] == COUNTS
    con = sqlite3.connect(db)
    for name, rows in before.items():
        cur = con.execute(f'SELECT * FROM "{name}"')
        assert [dict(zip([c[0] for c in cur.description], r, strict=True)) for r in cur.fetchall()] == rows
    con.close()
    with Brain(db) as b:
        assert b.migration["created"] == [] and len(b.storage.fetchall("SELECT 1 FROM schema_migrations")) == 2


# -- the seven share one screen; the dashboard tiles the structure, not its parts ----------------
def test_the_parts_have_no_table_screen_and_one_tile(brain):
    from asi_kletz.gui.dashboard import STPA_TILES
    from asi_kletz.gui.screens import CONTROL_STRUCTURES_SCREEN, STPA_SCREEN, build_default_screens

    assert [t[0] for t in STPA_TILES] == ["control_structure", "stpa_analysis", "hara"]  # the wholes, not the parts
    assert [t[2] for t in STPA_TILES] == [CONTROL_STRUCTURES_SCREEN, STPA_SCREEN, "hara"]
    factory = build_default_screens(brain)
    keys = [key for key, _title in factory.items()]
    assert not any(key.startswith("entity:") or key.startswith("cs_") for key in keys)
    assert CONTROL_STRUCTURES_SCREEN in keys  # tests/test_control_structure_screen.py drives it


# -- local only: the owner's structure, counts and files, never its text ----------------------
@pytest.mark.skipif(not (PRIVATE_DATASETS / "controllers.json").is_file(), reason="the private datasets are not here")
def test_the_private_wheel_loader_datasets_load_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_CONTROL_STRUCTURES, str(PRIVATE_DATASETS.parent.parent))
    with Brain(tmp_path / "private.db") as b:
        made = b.execute("cs", action="new", target=TEMPLATE_BUILDER)
        assert made.ok, made.errors
        assert made.data["counts"] == {"controllers": 8, "algorithms": 30, "process_model_entries": 18,
                                       "edges": 21, "signals": 58, "notes": 1}
        report = b.execute("cs", action="validate", target=made.data["slug"])
        assert report.data["errors"] == []
        exported = b.execute("cs", action="export", target=made.data["slug"], out=str(tmp_path / "out"), no_ocr=True)
        assert exported.ok and len(exported.data["files"]) == 2
        assert all(Path(f).is_file() for f in exported.data["files"])
        back = read_drawio(exported.data["paths"]["drawio"])
        assert {k: len(back[k]) for k in PARTS} == {k: v for k, v in made.data["counts"].items()}
