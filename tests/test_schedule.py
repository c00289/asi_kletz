"""Points on the Safety Plan: the pure scheduler, the recompute and its triggers, the refused fields, the weights."""

from __future__ import annotations

import json

import pytest

from asi_kletz.generate.plan_schedule import chain, free_capacity, pins, schedule, weight_of
from asi_kletz.schema.definitions import CALCULATED_RULE, DEFAULTS_RULE
from tests.conftest import PLAN, REPO_ROOT, SEED_WEIGHTS

ITEM = "sprint_item"


def _sprint(number, status="Planned", end=None, capacity=None):
    return {"id": number, "number": number, "status": status, "end": end or f"2027-01-{number:02d}",
            "capacity": capacity}


def _row(row_id, status="Pending", points=None, default=None, deliverable=None):
    return {"id": row_id, "order": row_id, "status": status, "points": points, "default_points": default,
            "deliverable": deliverable or f"Deliverable {row_id}", "sprint": None, "deadline": None}


SPRINTS = [_sprint(1, "Closed", "2026-10-27", 10), _sprint(2, "Active", "2026-11-09"), _sprint(3), _sprint(4),
           _sprint(5)]


# -- the scheduler, pure -------------------------------------------------------------------------------


def test_weights_and_the_chain():
    assert weight_of(_row(1, points=5, default=3), 2) == (5, "points")
    assert weight_of(_row(1, default=3), 2) == (3, "default")
    assert weight_of(_row(1), 2) == (2, "floor")
    assert [s["number"] for s in chain(SPRINTS)] == [2, 3, 4, 5]  # from the Active one, Closed never
    assert [s["number"] for s in chain([_sprint(1, "Closed"), _sprint(3), _sprint(2)])] == [2, 3]  # the first Planned
    assert chain([_sprint(1, "Closed")]) == []
    assert free_capacity(_sprint(2, "Active"), [{"sprint": 2, "points": 5, "status": "To Do"}]) == 3
    assert free_capacity(_sprint(2, "Active"), [{"sprint": 2, "points": 5, "status": "Carried"}]) == 8
    assert free_capacity(_sprint(1, "Closed", capacity=10), []) == 10  # history keeps its capacity
    assert pins([{"kind": "Deliverable", "plan_row": 7, "sprint": 3}, {"kind": "Jira", "plan_row": 7, "sprint": 4},
                 {"kind": "Deliverable", "plan_row": 7, "sprint": 1}], {2, 3, 4}) == {7: 3}


def test_plan_order_fills_the_first_sprint_first():
    rows = [_row(1, points=3), _row(2, points=3), _row(3, points=2), _row(4, points=1)]
    result = schedule(rows, SPRINTS, [], 2)
    assert result.assignments == {1: (2, "2026-11-09"), 2: (2, "2026-11-09"), 3: (2, "2026-11-09"),
                                  4: (3, "2027-01-03")}
    assert result.weights == {1: 3, 2: 3, 3: 2, 4: 1} and result.warnings == []
    assert result.sources == {1: "points", 2: "points", 3: "points", 4: "points"}


def test_a_deliverable_spans_sprints_and_ends_in_the_last_one():
    result = schedule([_row(1, points=10), _row(2, points=5)], SPRINTS, [], 2)
    assert result.assignments[1] == (3, "2027-01-03")  # 8 in Sprint 2, 2 in Sprint 3
    assert result.spans[1][1] == result.assignments[1][1] == "2027-01-03"  # the sprint's own end is the deadline
    assert result.assignments[2] == (3, "2027-01-03")  # 5 of the 6 left in Sprint 3


def test_a_committed_item_pins_the_start():
    items = [{"kind": "Deliverable", "plan_row": 2, "sprint": 4, "points": None, "status": "To Do"}]
    result = schedule([_row(1, points=2), _row(2, points=2), _row(3, points=2)], SPRINTS, items, 2)
    assert result.assignments == {1: (2, "2026-11-09"), 2: (4, "2027-01-04"), 3: (2, "2026-11-09")}
    assert result.committed == {1: 0, 2: 0, 3: 0}  # an unpointed item pins and commits nothing


def test_own_items_are_the_committed_part_of_the_weight():
    """The owner's rule (0.11.4): the item's points are the part of the deliverable already committed."""
    from asi_kletz.generate.plan_schedule import committed_points, own_items, pins

    items = [
        {"kind": "Deliverable", "plan_row": 1, "sprint": 3, "points": 4, "status": "To Do"},
        {"kind": "Deliverable", "plan_row": 2, "sprint": 4, "points": 4, "status": "In Progress"},
        {"kind": "Deliverable", "plan_row": 3, "sprint": 2, "points": 3, "status": "Done"},
        {"kind": "Deliverable", "plan_row": 3, "sprint": 3, "points": 1, "status": "To Do"},
        {"kind": "Deliverable", "plan_row": 4, "sprint": 1, "points": 2, "status": "Carried"},  # a trace: ignored
        {"kind": "Jira", "plan_row": 4, "sprint": 2, "points": 5, "status": "To Do"},  # not a deliverable's own
        {"kind": "Deliverable", "plan_row": 5, "sprint": 1, "points": 6, "status": "Done"},  # a Closed sprint
    ]
    assert [i["plan_row"] for i in own_items(items)] == [1, 2, 3, 3, 5]
    assert committed_points(items) == {1: 4, 2: 4, 3: 4, 5: 6}
    assert pins(items) == {1: 3, 2: 4, 3: 3, 5: 1} and pins(items, {2, 3, 4, 5}) == {1: 3, 2: 4, 3: 3}
    # Sprint 2 is full (3 + 5 committed), Sprint 3 has 3 free (8 minus 4 minus 1), Sprint 4 has 4 (8 minus 4)
    rows = [_row(1, points=7), _row(2, points=4), _row(3, points=10), _row(5, points=6)]
    result = schedule(rows, SPRINTS, items, 2)
    assert result.committed == {1: 4, 2: 4, 3: 4, 5: 6}
    assert result.assignments[1] == (3, "2027-01-03")  # 7 with a 4-point item: the 3 left fit Sprint 3, done there
    assert result.assignments[2] == (4, "2027-01-04")  # fully committed: it finishes where its item is
    assert result.assignments[3] == (5, "2027-01-05")  # two items, two sprints: 6 left from Sprint 3 on (4 + 2)
    assert result.assignments[5] == (1, "2026-10-27")  # fully committed in a Closed sprint: finishes there
    assert result.warnings == []


def test_done_keeps_its_own_and_the_excluded_get_nothing():
    rows = [_row(1, "Done", points=8), _row(2, "Blocked", points=8), _row(3, "Alternative"), _row(4, "Out-of-Scope"),
            _row(5, "Ongoing", points=8)]
    result = schedule(rows, SPRINTS, [], 2)
    assert 1 not in result.assignments and result.sources[1] == "done"
    assert result.assignments[2] == (None, None) and result.sources[2] == "excluded"
    assert result.assignments[3] == (None, None) and result.assignments[4] == (None, None)
    assert result.assignments[5] == (2, "2026-11-09")  # the Done and the Blocked consumed nothing


def test_committed_points_reduce_the_capacity():
    items = [{"sprint": 2, "points": 5, "status": "In Progress"}, {"sprint": 2, "points": 3, "status": "Carried"}]
    result = schedule([_row(1, points=3), _row(2, points=1)], SPRINTS, items, 2)
    assert result.assignments == {1: (2, "2026-11-09"), 2: (3, "2027-01-03")}  # 3 free in Sprint 2


def test_the_chain_running_out_is_a_warning_not_a_date():
    result = schedule([_row(1, points=40, deliverable="FTA/FMEA analysis for each SGs")], SPRINTS, [], 2)
    assert result.assignments == {1: (None, None)}  # four sprints of 8 hold 32 of the 40
    assert result.warnings == [
        'row 1 "FTA/FMEA analysis for each SGs" needs 8 more point(s): the sprint chain ends at Sprint 5; '
        "run sprint plan"
    ]
    empty = schedule([_row(1, points=1)], [_sprint(1, "Closed")], [], 2)
    assert empty.assignments == {1: (None, None)} and "no Active or Planned sprint" in empty.warnings[0]


# -- the recompute and its triggers ---------------------------------------------------------------------


@pytest.fixture
def planned(seeded):
    """The seeded plan (rows 1 Done, 2 Ongoing, 3 Pending) over Sprint 2 active and Sprints 3 and 4 planned."""
    assert seeded.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "start": "2026-10-12", "end": "2026-10-27", "capacity": 10,
        "status": "Closed",
    }).ok
    assert seeded.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "start": "2026-10-27", "end": "2026-11-09", "status": "Active",
    }).ok
    for number, (start, end) in ((3, ("2026-11-10", "2026-11-23")), (4, ("2026-11-24", "2026-12-07"))):
        assert seeded.execute("create", entity="sprint", data={
            "number": number, "label": f"SPRINT {number}", "start": start, "end": end, "status": "Planned",
        }).ok
    return seeded


def _plan(brain):
    return {r["id"]: (r.get("points"), r.get("default_points"), r.get("sprint"), r.get("deadline")) for r in
            brain.execute("list", entity=PLAN).data}


def _spans(brain):
    """``sprint_start`` and ``sprint_end`` beside ``sprint`` (0.11.2): the sprint's own dates, or Nones."""
    return {r["id"]: (r.get("sprint"), r.get("sprint_start"), r.get("sprint_end")) for r in
            brain.execute("list", entity=PLAN).data}


def test_sprint_start_and_end_follow_the_sprint(planned):
    sprints = {s["number"]: s for s in planned.execute("list", entity="sprint").data}
    for row_id, (number, start, end) in _spans(planned).items():
        if number is None:
            assert (start, end) == (None, None)
        else:
            assert (start, end) == (sprints[number]["start"], sprints[number]["end"])
            assert end == _plan(planned)[row_id][3]  # the deadline is the sprint's end
    assert planned.execute("update", entity=PLAN, id=2, set=["points=7"]).ok  # row 3 moves to Sprint 3
    assert _spans(planned)[3] == (3, sprints[3]["start"], sprints[3]["end"])
    for field in ("sprint_start=2026-01-01", "sprint_end=2026-01-02"):
        refused = planned.execute("update", entity=PLAN, id=2, set=[field])
        assert not refused.ok and refused.errors == [CALCULATED_RULE]


def test_every_write_recomputes_and_the_rows_carry_the_answer(planned):
    # the floor (2) for rows 2 and 3, row 1 Done keeps "Phase 1 exit": both fit Sprint 2
    assert _plan(planned) == {1: (None, None, None, "Phase 1 exit"), 2: (None, None, 2, "2026-11-09"),
                              3: (None, None, 2, "2026-11-09")}
    assert planned.execute("update", entity=PLAN, id=2, set=["points=7"]).ok  # 7 + 2 > 8: row 3 moves
    assert _plan(planned)[2] == (7, None, 2, "2026-11-09") and _plan(planned)[3] == (None, None, 3, "2026-11-23")
    tail = planned.storage.audit_tail(2)
    assert [t["action"] for t in tail] == ["schedule", "update"] and tail[0]["payload"]["count"] == 1
    assert planned.events.last(1)[0]["topic"] == "plan.scheduled"
    # a committed item in Sprint 3 pins row 2 there, and its points leave less room
    assert planned.execute("create", entity=ITEM, data={
        "sprint": 3, "kind": "Deliverable", "plan_row": 2, "title": "Hazard analysis", "points": 4, "status": "To Do",
    }).ok
    # the item's 4 points are the committed part of the 7 (0.11.4): the 3 left fit Sprint 3 beside the item
    assert _plan(planned)[2][2:] == (3, "2026-11-23") and _plan(planned)[3][2:] == (2, "2026-11-09")
    # closing Sprint 2 moves everything after it: Sprint 3 has one point left after row 2, row 3 spills into 4
    closed = planned.execute("sprint", action="close", as_of="2026-11-09")
    assert closed.ok, closed.errors
    assert _plan(planned)[2][2:] == (3, "2026-11-23") and _plan(planned)[3][2:] == (4, "2026-12-07")
    # the planner's new sprints and a replan recompute too; a second recompute changes nothing
    assert planned.execute("sprint", action="plan", until="2027-01-31").ok
    before = len(planned.storage.audit_tail(50))
    assert planned.execute("plan", action="schedule").data["changed"] == 0
    assert len(planned.storage.audit_tail(50)) == before
    # the chain runs out for a 30-point row: no sprint, no deadline, a warning in the Result
    assert planned.execute("update", entity=PLAN, id=3, set=["points=90"]).ok
    result = planned.execute("plan", action="schedule")
    assert result.ok and _plan(planned)[3][2:] == (None, None) and result.data["unscheduled"] == [3]
    assert result.warnings and "run sprint plan" in result.warnings[0]
    table = result.data["rows"]
    assert [(r["id"], r["weight"], r["committed"], r["source"], r["sprint"]) for r in table] == [
        (1, 0, 0, "done", None), (2, 7, 4, "points", 3), (3, 90, 0, "points", None),
    ]
    # the recompute only touches rows whose answer moved: a delete of the item frees Sprint 3
    item = planned.execute("list", entity=ITEM, filter=["plan_row=2"]).data[0]
    assert planned.execute("delete", entity=ITEM, id=item["id"]).ok
    assert _plan(planned)[2][2:] == (3, "2026-11-23")  # 7 points: Sprint 2 is Closed now, Sprint 3 is the first


def test_the_calculated_fields_and_the_default_are_refused_by_hand(planned):
    for field in ("deadline=2026-12-31", "sprint=4"):
        refused = planned.execute("update", entity=PLAN, id=2, set=[field])
        assert not refused.ok and refused.errors == [CALCULATED_RULE]
    refused = planned.execute("update", entity=PLAN, id=2, set=["default_points=3"])
    assert not refused.ok and refused.errors == [DEFAULTS_RULE]
    refused = planned.execute("create", entity=PLAN, data={"deliverable": "x", "deadline": "soon"})
    assert not refused.ok and refused.errors == [CALCULATED_RULE]
    for bad in ("0", "-1", "two"):
        assert not planned.execute("update", entity=PLAN, id=2, set=[f"points={bad}"]).ok
    assert planned.execute("update", entity=PLAN, id=2, set=["points="]).ok  # empty clears: back to the default
    assert _plan(planned)[2][0] is None
    created = planned.execute("create", entity=PLAN, data={"deliverable": "new", "points": 3, "order": 4})
    assert created.ok and created.data["sprint"] is None  # the create's own Result predates the recompute
    assert _plan(planned)[created.data["id"]] == (3, None, 2, "2026-11-09")


def test_weights_load_sets_the_defaults_from_the_panels_record(planned):
    assert SEED_WEIGHTS.is_file() and (REPO_ROOT / "docs" / "deliverable-points.md").is_file()
    record = json.loads(SEED_WEIGHTS.read_text(encoding="utf-8"))
    assert len(record) == 48 and sum(r["points"] for r in record) == 174
    assert [sorted(r) for r in record[:1]] == [["deliverable", "id", "order", "points"]]
    assert [r["id"] for r in record] == list(range(1, 49)) and [r["order"] for r in record] == list(range(1, 49))
    loaded = planned.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS), actor="me")
    assert loaded.ok, loaded.errors
    assert (loaded.data["set"], loaded.data["unchanged"], len(loaded.data["unmatched"])) == (3, 0, 45)
    assert loaded.data["unmatched"][:2] == ["4", "5"] and loaded.data["rows"] == 48
    assert _plan(planned) == {1: (None, 5, None, "Phase 1 exit"), 2: (None, 3, 2, "2026-11-09"),
                              3: (None, 2, 2, "2026-11-09")}  # 3 + 2 fit Sprint 2; row 1 is Done
    assert "weights" in [t["action"] for t in planned.storage.audit_tail(3)]
    again = planned.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS))
    assert again.ok and (again.data["set"], again.data["unchanged"]) == (0, 3)
    assert planned.execute("update", entity=PLAN, id=2, set=["points=7"]).ok
    assert _plan(planned)[3][2:] == (3, "2026-11-23")  # 7 + 2 > 8: the default-weighted row moves out
    table = planned.execute("plan", action="schedule").data["rows"]
    assert [(r["weight"], r["source"]) for r in table] == [(0, "done"), (7, "points"), (2, "default")]
    assert not planned.execute("plan", action="weights").ok
    assert not planned.execute("plan", action="weights", what="load", file=str(REPO_ROOT / "nope.json")).ok


def test_weights_load_matches_by_uid_before_id(planned, tmp_path):
    rows = planned.execute("list", entity=PLAN).data
    file = tmp_path / "w.json"
    file.write_text(json.dumps([
        {"id": 99, "uid": rows[2]["uid"], "points": 4},  # the uid wins over a wrong id
        {"id": 1, "points": 7},
        {"id": 2, "points": "x"},
    ]), encoding="utf-8")
    assert "is not an integer" in planned.execute("plan", action="weights", what="load", file=str(file)).errors[0]
    file.write_text(json.dumps([{"id": 99, "uid": rows[2]["uid"], "points": 4}, {"id": 1, "points": 7},
                                {"uid": "00000000-0000-4000-8000-000000000000", "points": 1}]), encoding="utf-8")
    loaded = planned.execute("plan", action="weights", what="load", file=str(file))
    assert loaded.ok and loaded.data["set"] == 2
    assert loaded.data["unmatched"] == ["00000000-0000-4000-8000-000000000000"]
    assert _plan(planned)[3][1] == 4 and _plan(planned)[1][1] == 7
    file.write_text(json.dumps([{"id": 1, "points": 0}]), encoding="utf-8")
    assert "positive integer" in planned.execute("plan", action="weights", what="load", file=str(file)).errors[0]
