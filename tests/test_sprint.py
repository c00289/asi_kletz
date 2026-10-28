"""The agile rules: eight points a sprint (the rule, fixed), ten business days, capacity as a warning on
commitment and a refusal on the row, close and carry, one active sprint, velocity, and the planner."""

from __future__ import annotations

import datetime as dt
import shutil

import pytest

from asi_kletz import Brain
from asi_kletz.automation.cli import build_parser
from asi_kletz.schema.definitions import CAPACITY_RULE, SPRINT_CAPACITY, SPRINT_DAYS
from tests.conftest import DB_0_8_4, SEED_HOLIDAYS

ITEM = "sprint_item"
AS_OF = "2026-10-28"


@pytest.fixture
def sprinted(brain):
    """Sprint 1, active, 10/27 to 11/10, with four items: 3 and 3 points open, one unpointed, one done at 2."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-10", "capacity": 8, "status": "Active",
    }).ok
    for order, (title, points, status) in enumerate([
        ("Safety Plan dated", 3, "To Do"), ("Activity Flow reviewed", 3, "In Progress"),
        ("ConOps located", None, "To Do"), ("Intro meeting", 2, "Done"),
    ], 1):
        assert brain.execute("create", entity=ITEM, data={
            "sprint": 1, "order": order, "kind": "Deliverable", "title": title, "points": points, "status": status,
        }).ok
    return brain


@pytest.fixture
def chained(brain):
    """The owner's chain: Sprint 1 closed (10/12 to 10/27, capacity 10 as history), Sprint 2 active (10/27 to 11/10)."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "lifecycle_phase": "2. HARA / Risk Assessment", "start": "2026-10-12",
        "end": "2026-10-27", "capacity": 10, "status": "Closed", "closed_on": "2026-10-27",
    }).ok
    assert brain.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-10", "status": "Active",
    }).ok
    return brain


def _items(brain, number):
    return brain.execute("list", entity=ITEM, filter=[f"sprint={number}"]).data


def _sprints(brain):
    return brain.execute("list", entity="sprint").data


def test_the_rule_is_fixed():
    assert SPRINT_CAPACITY == 8 and SPRINT_DAYS == 10
    assert "8 points" in CAPACITY_RULE and "Closed" in CAPACITY_RULE


def test_board_sums_points_and_counts_days(sprinted):
    board = sprinted.execute("sprint", action="board", as_of=AS_OF)
    assert board.ok, board.errors
    data = board.data
    assert (data["capacity"], data["committed"], data["done"], data["to_go"]) == (8, 8, 2, 6)
    assert data["unpointed"] == 1 and data["days_left"] == 13 and data["overdue"] is False and data["velocity"] is None
    assert data["warnings"] == ["sprint 1: 1 item(s) unpointed"] and len(data["items"]) == 4
    late = sprinted.execute("sprint", action="board", number=1, as_of="2026-11-12").data
    assert late["days_left"] == 0 and late["overdue"] is True
    assert not sprinted.execute("sprint", action="board", number=9).ok


def test_point_validates_and_warns_over_capacity(sprinted):
    third = _items(sprinted, 1)[2]
    assert not sprinted.execute("sprint", action="point", item=third["id"], points=9).ok
    assert not sprinted.execute("sprint", action="point", item=third["id"], points="three").ok
    over = sprinted.execute("sprint", action="point", item=third["id"], points=5)
    assert over.ok and over.data["points"] == 5 and over.warnings == ["sprint 1 committed 13 of 8 points"]
    cleared = sprinted.execute("sprint", action="point", item=third["id"], points=0)
    assert cleared.ok and cleared.data["points"] is None
    assert not sprinted.execute("sprint", action="point", item=third["id"]).ok
    assert not sprinted.execute("sprint", action="point", points=1).ok


def test_only_one_sprint_is_active(sprinted):
    refused = sprinted.execute("sprint", action="start", phase="3")
    assert not refused.ok and "sprint 1 is active" in refused.errors[0]


def test_close_counts_done_carries_the_rest_and_opens_the_next_sprint(sprinted):
    seen = []
    sprinted.events.subscribe("sprint.closed", lambda topic, event: seen.append(event))
    closed = sprinted.execute("sprint", action="close", as_of="2026-11-10", actor="me")
    assert closed.ok, closed.errors
    assert closed.data["done"] == 2 and closed.data["carried"] == 3 and closed.data["next"] == 2
    assert closed.data["velocity"] == 2.0 and closed.warnings == ["carried without points: ConOps located"]
    assert closed.data["sprint"]["status"] == "Closed" and closed.data["sprint"]["closed_on"] == "2026-11-10"
    nxt = _sprints(sprinted)[1]
    # the next sprint starts on the first business day after the closed one's end and runs ten business days
    assert (nxt["number"], nxt["label"], nxt["status"], nxt["start"], nxt["end"], nxt["capacity"]) == (
        2, "SPRINT 2", "Active", "2026-11-11", "2026-11-24", 8,
    )
    assert nxt["lifecycle_phase"] == _sprints(sprinted)[0]["lifecycle_phase"]
    assert [(i["title"], i["status"]) for i in _items(sprinted, 1)] == [
        ("Safety Plan dated", "Carried"), ("Activity Flow reviewed", "Carried"), ("ConOps located", "Carried"),
        ("Intro meeting", "Done"),
    ]
    carried = _items(sprinted, 2)
    assert [(i["title"], i["points"], i["status"], i["carried_from"]) for i in carried] == [
        ("Safety Plan dated", 3, "To Do", 1), ("Activity Flow reviewed", 3, "To Do", 1),
        ("ConOps located", None, "To Do", 1),
    ]
    assert seen and seen[0]["number"] == 1 and seen[0]["carried"] == 3 and seen[0]["actor"] == "me"
    assert sprinted.execute("sprint", action="board", as_of="2026-11-10").data["sprint"]["number"] == 2
    again = sprinted.execute("sprint", action="close", number=1)
    assert not again.ok and "not Active" in again.errors[0]


def test_velocity_is_the_mean_of_the_last_three_closed_sprints(sprinted):
    def close_with(number, done_points):
        for row in _items(sprinted, number):
            sprinted.execute("update", entity=ITEM, id=row["id"], set=["status=Done"])
        if done_points:
            assert sprinted.execute("create", entity=ITEM, data={
                "sprint": number, "title": f"extra {number}", "points": done_points, "status": "Done",
            }).ok
        closed = sprinted.execute("sprint", action="close", number=number, as_of="2026-11-10")
        assert closed.ok, closed.errors
        return closed.data["velocity"]

    assert close_with(1, 0) == 8.0  # 3 + 3 + 2
    assert close_with(2, 4) == 6.0  # (8 + 4) / 2
    assert close_with(3, 2) == 4.7  # (8 + 4 + 2) / 3
    assert close_with(4, 0) == 2.0  # the window slides: (4 + 2 + 0) / 3
    board = sprinted.execute("sprint", action="board", as_of="2026-11-10").data
    assert board["sprint"]["number"] == 5 and board["velocity"] == 2.0 and board["committed"] == 0


def test_start_opens_a_new_sprint_and_close_activates_the_planned_next_one(brain):
    assert not brain.execute("sprint", action="start", phase="99").ok
    started = brain.execute("sprint", action="start", phase="3", start="2026-10-27", goal="Clear the backlog")
    assert started.ok, started.errors
    row = started.data
    # ten business days from a Tuesday end on the Monday after next; capacity is the rule, not an option
    assert (row["number"], row["label"], row["status"], row["end"]) == (1, "SPRINT 1", "Active", "2026-11-09")
    assert row["capacity"] == 8
    assert row["lifecycle_phase"] == "3. Functional Safety Concept (FSC)" and row["goal"] == "Clear the backlog"
    assert not brain.execute("sprint", action="start", capacity=10).ok  # the option is gone
    assert brain.execute("create", entity="sprint", data={"number": 2, "status": "Planned", "label": "SPRINT 2"}).ok
    closed = brain.execute("sprint", action="close", as_of="2026-11-10")
    assert closed.ok and closed.data["next"] == 2
    second = brain.execute("list", entity="sprint", filter=["number=2"]).data[0]
    assert second["status"] == "Active" and second["start"] == "2026-11-10" and second["end"] == "2026-11-23"
    assert second["capacity"] == 8 and second["label"] == "SPRINT 2"
    refused = brain.execute("sprint", action="start", number=2)
    assert not refused.ok and "sprint 2 is active" in refused.errors[0]


def test_start_activates_a_planned_sprint_when_none_is_active(brain):
    assert brain.execute("create", entity="sprint", data={"number": 4, "status": "Planned"}).ok
    assert not brain.execute("sprint", action="start", number=9).ok
    activated = brain.execute("sprint", action="start", number=4, as_of="2026-11-10")
    assert activated.ok, activated.errors
    row = activated.data
    assert (row["status"], row["start"], row["end"], row["capacity"], row["label"]) == (
        "Active", "2026-11-10", "2026-11-23", 8, "SPRINT 4",
    )


def test_start_skips_holidays_in_the_default_end(brain):
    assert brain.execute("holiday", action="load", file=str(SEED_HOLIDAYS)).ok
    row = brain.execute("sprint", action="start", start="2026-11-09").data  # Veterans Day inside: one day more
    assert row["end"] == "2026-11-23"
    assert brain.execute("sprint", action="close", as_of="2026-11-23").data["next"] == 2
    second = brain.execute("list", entity="sprint", filter=["number=2"]).data[0]
    assert second["start"] == "2026-11-24" and second["end"] == "2026-12-09"  # Thanksgiving and the company Friday


def test_carry_moves_one_open_item_now(sprinted):
    first, _, third, done = _items(sprinted, 1)
    assert sprinted.execute("create", entity="sprint", data={"number": 2, "status": "Planned", "label": "SPRINT 2"}).ok
    moved = sprinted.execute("sprint", action="carry", item=first["id"])
    assert moved.ok and moved.data["sprint"] == 2 and moved.data["carried_from"] == 1 and moved.data["points"] == 3
    assert sprinted.execute("get", entity=ITEM, id=first["id"]).data["status"] == "Carried"
    assert not sprinted.execute("sprint", action="carry", item=done["id"]).ok
    assert sprinted.execute("create", entity="sprint", data={"number": 4, "status": "Planned"}).ok
    far = sprinted.execute("sprint", action="carry", item=third["id"], to=4)
    assert far.ok and far.data["sprint"] == 4
    assert not sprinted.execute("sprint", action="carry", item=third["id"], to=4).ok  # already Carried


def test_config_sets_the_days_and_warns_about_the_capacity_key(tmp_path, monkeypatch):
    from asi_kletz.brain import ENV_CONFIG, load_config

    config = tmp_path / "kletz.toml"
    config.write_text('sprint_capacity = 8\nsprint_days = 7\ntracker_byline = "Role"\n', encoding="utf-8")
    loaded = load_config(config)
    assert loaded["sprint_days"] == 7 and "sprint_capacity" not in loaded
    assert loaded["warnings"] == [f"sprint_capacity = 8 in kletz.toml is ignored: {CAPACITY_RULE}"]
    config.write_text('sprint_days = true\n', encoding="utf-8")
    assert "sprint_days" not in load_config(config) and "warnings" not in load_config(config)
    config.write_text('sprint_capacity = "10"\nsprint_days = 7\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "c.db") as b:
        assert b.sprint_capacity == 8 and b.sprint_days == 7
        status = b.execute("status").data
        assert status["sprint_capacity"] == 8 and status["sprint_days"] == 7
        assert status["config_warnings"] == [f"sprint_capacity = '10' in kletz.toml is ignored: {CAPACITY_RULE}"]
        row = b.execute("sprint", action="start", start="2026-10-27").data
        assert row["capacity"] == 8 and row["end"] == "2026-11-04"  # seven business days
        assert not b.execute("sprint", action="point", item=1, points=9).ok


# -- the capacity rule on the rows ------------------------------------------------------------------------


def test_a_sprint_that_is_not_closed_cannot_hold_another_capacity(chained):
    refused = chained.execute("update", entity="sprint", id=2, set=["capacity=10"])
    assert not refused.ok and refused.errors == [CAPACITY_RULE]
    assert chained.execute("update", entity="sprint", id=2, set=["capacity=8"]).ok
    assert chained.execute("update", entity="sprint", id=2, set=["goal=x"]).ok
    assert chained.execute("get", entity="sprint", id=2).data["capacity"] == 8
    history = chained.execute("update", entity="sprint", id=1, set=["capacity=9"])  # Closed: the past is history
    assert history.ok and history.data["capacity"] == 9
    refused = chained.execute("create", entity="sprint", data={"number": 3, "status": "Planned", "capacity": 10})
    assert not refused.ok and refused.errors == [CAPACITY_RULE]
    filled = chained.execute("create", entity="sprint", data={"number": 3, "status": "Planned"})
    assert filled.ok and filled.data["capacity"] == 8  # a create without a capacity gets the rule's
    closed = chained.execute("create", entity="sprint", data={"number": 0, "status": "Closed", "capacity": 12})
    assert closed.ok and closed.data["capacity"] == 12
    reopened = chained.execute("update", entity="sprint", id=closed.data["id"], set=["status=Planned"])
    assert reopened.ok  # the stored value stays until the next open normalises it
    assert chained.execute("sprint", action="board", number=0).data["capacity"] == 8  # the board reads the rule


def test_open_sets_every_sprint_that_is_not_closed_to_eight_once(tmp_path):
    """A database written before the rule: the active sprint at 10 becomes 8 the first time 0.10.0 opens it,
    audited once; the closed one keeps 10; the second open changes nothing and audits nothing."""
    db = tmp_path / "kletz.db"
    shutil.copyfile(DB_0_8_4, db)  # sprint 1, Closed, capacity 10
    with Brain(db) as brain:
        assert brain.migration["capacity_enforced"] == 0  # a Closed sprint is the past
        rows = [
            {"number": 2, "label": "SPRINT 2", "start": "2026-10-27", "end": "2026-11-10", "capacity": 10,
             "status": "Active"},
            {"number": 3, "label": "SPRINT 3", "capacity": 10, "status": "Planned"},
            {"number": 4, "label": "SPRINT 4", "status": "Planned"},
        ]
        summary = brain.service("sprint").load_rows(rows, "append")  # a file import bypasses the guard
        assert summary["inserted"] == 3
        assert [r["capacity"] for r in _sprints(brain)] == [10, 10, 10, None]
        assert brain.execute("sprint", action="board", number=2).data["capacity"] == 8  # read as the rule already
    with Brain(db) as brain:
        assert brain.migration["capacity_enforced"] == 3
        assert [(r["number"], r["capacity"]) for r in _sprints(brain)] == [(1, 10), (2, 8), (3, 8), (4, 8)]
        entry = brain.storage.audit_tail(1)[0]
        assert (entry["action"], entry["actor"], entry["entity"]) == ("enforce_capacity", "system", "sprint")
        assert entry["payload"] == {"count": 3, "ids": [2, 3, 4], "capacity": 8}
    with Brain(db) as brain:
        assert brain.migration["capacity_enforced"] == 0
        assert brain.storage.audit_tail(1)[0]["action"] == "enforce_capacity"  # the one entry, nothing after it
        assert [(r["number"], r["capacity"]) for r in _sprints(brain)] == [(1, 10), (2, 8), (3, 8), (4, 8)]


# -- the planner ------------------------------------------------------------------------------------------


def test_plan_extends_the_chain_three_years_on_business_days(chained):
    seen = []
    chained.events.subscribe("sprint.planned", lambda topic, event: seen.append(event))
    result = chained.execute("sprint", action="plan", actor="me")
    assert result.ok, result.errors
    data = result.data
    assert (data["added"], data["replanned"], data["days"], data["capacity"], data["holidays"]) == (79, 0, 10, 8, [])
    assert data["first"] == {"number": 3, "start": "2026-11-11", "end": "2026-11-24"}
    assert data["last"] == {"number": 81, "start": "2029-11-07", "end": "2029-11-20"} and data["until"] == "2029-11-10"
    rows = _sprints(chained)
    assert len(rows) == 81 and [r["status"] for r in rows[2:]] == ["Planned"] * 79
    assert all(r["capacity"] == 8 and r["label"] == f"SPRINT {r['number']}" for r in rows[2:])
    assert all(not r["lifecycle_phase"] and not r["goal"] for r in rows[2:])
    assert [(r["start"], r["end"]) for r in rows[2:6]] == [
        ("2026-11-11", "2026-11-24"), ("2026-11-25", "2026-12-08"), ("2026-12-09", "2026-12-22"),
        ("2026-12-23", "2027-01-05"),
    ]
    for previous, row in zip(rows[1:], rows[2:], strict=False):  # consecutive, no gaps, never a weekend
        start = dt.date.fromisoformat(row["start"])
        assert start > dt.date.fromisoformat(previous["end"]) and start.weekday() < 5
        assert (start - dt.date.fromisoformat(previous["end"])).days <= 3
    assert rows[0]["capacity"] == 10 and rows[1]["status"] == "Active"  # untouched
    assert seen[0]["added"] == 79 and seen[0]["actor"] == "me"
    again = chained.execute("sprint", action="plan")
    assert again.ok and again.data["added"] == 0 and again.data["first"] is None and len(_sprints(chained)) == 81


def test_plan_honours_the_holidays(chained):
    assert chained.execute("holiday", action="load", file=str(SEED_HOLIDAYS)).ok
    data = chained.execute("sprint", action="plan").data
    assert data["added"] == 75 and data["first"] == {"number": 3, "start": "2026-11-12", "end": "2026-11-25"}
    assert data["last"] == {"number": 77, "start": "2029-11-02", "end": "2029-11-16"}
    assert len(data["holidays"]) == 38 and data["holidays"][0] == "Veterans Day (2026-11-11)"  # the span, gaps too
    assert data["holidays"][-1] == "Veterans Day (2029-11-12)"
    rows = _sprints(chained)
    assert [(r["start"], r["end"]) for r in rows[2:6]] == [
        ("2026-11-12", "2026-11-25"), ("2026-11-30", "2026-12-11"), ("2026-12-14", "2026-12-29"),
        ("2026-12-30", "2027-01-13"),
    ]
    christmas = rows[4]
    assert christmas["goal"] == "Holidays: Christmas Eve (company, assumed) (12/24), Christmas Day (12/25)"
    assert (dt.date.fromisoformat(christmas["end"]) - dt.date.fromisoformat(christmas["start"])).days + 1 == 16
    assert rows[2]["goal"] is None  # Veterans Day is before Sprint 3, not inside it
    assert sum(1 for r in rows[2:] if r["goal"]) == 28


def test_plan_until_a_date_and_the_errors(chained):
    data = chained.execute("sprint", action="plan", until="2027-01-31").data
    assert data["added"] == 6 and data["last"]["number"] == 8 and data["last"]["end"] == "2027-02-02"
    assert chained.execute("sprint", action="plan", until="2027-01-31").data["added"] == 0
    more = chained.execute("sprint", action="plan", until="2027-03-01", days=5).data
    assert more["added"] == 4 and more["first"] == {"number": 9, "start": "2027-02-03", "end": "2027-02-09"}
    assert more["last"] == {"number": 12, "start": "2027-02-24", "end": "2027-03-02"}  # starts on or before the horizon
    assert not chained.execute("sprint", action="plan", days=0).ok
    assert not chained.execute("sprint", action="plan", years=0).ok
    assert not chained.execute("sprint", action="plan", until="someday").ok
    assert not chained.execute("sprint", action="plan", capacity=8).ok  # no such option


def test_plan_needs_a_sprint_to_continue_from(brain):
    refused = brain.execute("sprint", action="plan")
    assert not refused.ok and "no sprint to continue from" in refused.errors[0]
    assert brain.execute("create", entity="sprint", data={"number": 1, "status": "Planned"}).ok
    refused = brain.execute("sprint", action="plan")
    assert not refused.ok and "has no end date" in refused.errors[0]


def test_replan_moves_the_planned_sprints_after_a_holiday_becomes_real(chained):
    assert chained.execute("sprint", action="plan", until="2027-01-31").data["added"] == 6
    assert chained.execute("update", entity="sprint", id=4, set=["goal=Write the FSC"]).ok  # a human goal, kept
    assert chained.execute("create", entity="holiday", data={
        "date": "2026-11-11", "name": "Veterans Day", "status": "confirmed",
    }).ok
    assert chained.execute("create", entity="holiday", data={"date": "2026-12-25", "name": "Christmas Day"}).ok
    before = {r["number"]: (r["start"], r["end"]) for r in _sprints(chained)}
    data = chained.execute("sprint", action="plan", until="2027-01-31", replan=True).data
    assert data["replanned"] == 6 and data["added"] == 0
    assert data["holidays"] == ["Veterans Day (2026-11-11)", "Christmas Day (2026-12-25)"]
    rows = {r["number"]: r for r in _sprints(chained)}
    assert (rows[1]["start"], rows[1]["end"], rows[2]["start"], rows[2]["end"]) == (
        before[1] + before[2]
    )  # the closed and the active sprint never move
    assert (rows[3]["start"], rows[3]["end"]) == ("2026-11-12", "2026-11-25")
    assert before[3] == ("2026-11-11", "2026-11-24")
    assert rows[4]["goal"] == "Write the FSC" and (rows[4]["start"], rows[4]["end"]) == ("2026-11-26", "2026-12-09")
    assert (rows[5]["start"], rows[5]["end"], rows[5]["goal"]) == ("2026-12-10", "2026-12-23", None)
    assert (rows[6]["start"], rows[6]["end"]) == ("2026-12-24", "2027-01-07")
    assert rows[6]["goal"] == "Holidays: Christmas Day (12/25)"  # the sprint says why its dates stretched
    assert (rows[7]["start"], rows[8]["end"]) == ("2027-01-08", "2027-02-04") and rows[3]["goal"] is None
    # confirming Christmas Eve too: Sprint 6 now starts after both holidays, its goal line goes, 7 and 8 follow
    assert chained.execute("create", entity="holiday", data={"date": "2026-12-24", "name": "Christmas Eve"}).ok
    data = chained.execute("sprint", action="plan", until="2027-01-31", replan=True).data
    rows = {r["number"]: r for r in _sprints(chained)}
    assert data["replanned"] == 3
    assert (rows[6]["start"], rows[6]["end"], rows[6]["goal"]) == ("2026-12-28", "2027-01-08", None)
    assert rows[7]["start"] == "2027-01-11" and rows[5]["end"] == "2026-12-23"
    assert data["holidays"] == ["Veterans Day (2026-11-11)", "Christmas Eve (2026-12-24)", "Christmas Day (2026-12-25)"]
    assert chained.execute("sprint", action="plan", until="2027-01-31", replan=True).data["replanned"] == 0


def test_cli_has_the_three_verbs():
    verbs = build_parser()._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    assert {"tracker", "sprint", "holiday"} <= set(verbs)
    ns = build_parser().parse_args(["tracker", "build", "week", "--jira", "--as-of", "2026-10-28"])
    assert ns.what == "week" and ns.jira is True and ns.as_of == "2026-10-28"
    ns = build_parser().parse_args(["sprint", "point", "--item", "3", "--points", "5"])
    assert ns.item == 3 and ns.points == 5 and ns.number is None
    ns = build_parser().parse_args(["sprint", "plan", "--years", "2", "--replan", "--days", "10"])
    assert ns.years == 2 and ns.replan is True and ns.days == 10 and ns.until is None
    with pytest.raises(SystemExit):
        build_parser().parse_args(["sprint", "start", "--capacity", "8"])
    ns = build_parser().parse_args(["holiday", "load", "data/us-holidays-2026-2029.json"])
    assert ns.action == "load" and ns.file == "data/us-holidays-2026-2029.json"
