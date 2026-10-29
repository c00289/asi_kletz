"""The agile rules: eight points a sprint (the rule, fixed), fourteen days Tuesday to Monday (the law of
2026-10-29), capacity as a warning on commitment and a refusal on the row, close and carry, one active sprint,
velocity, the planner and the alignment of an older chain."""

from __future__ import annotations

import datetime as dt
import shutil

import pytest

from asi_kletz import Brain
from asi_kletz.automation.cli import build_parser
from asi_kletz.schema.definitions import (
    CADENCE_NUMBER,
    CADENCE_RULE,
    CADENCE_START,
    CAPACITY_RULE,
    SPRINT_CAPACITY,
    SPRINT_LENGTH,
    SPRINT_RULE,
)
from tests.conftest import DB_0_8_4, PLAN, SEED_HOLIDAYS

ITEM = "sprint_item"
AS_OF = "2026-10-28"
# the picture from systems engineering, 2026-10-29: seven sprints, the law
PICTURE = [
    (31, "2026-10-27", "2026-11-09"), (32, "2026-11-10", "2026-11-23"), (33, "2026-11-24", "2026-12-07"),
    (34, "2026-12-08", "2026-12-21"), (35, "2026-12-22", "2027-01-04"), (36, "2027-01-05", "2027-01-18"),
    (37, "2027-01-19", "2027-02-01"),
]


@pytest.fixture
def sprinted(brain):
    """Sprint 1, active, 10/27 to 11/09, with four items: 3 and 3 points open, one unpointed, one done at 2."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-09", "capacity": 8, "status": "Active",
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
    """The owner's chain: Sprint 1 closed (10/12 to 10/27, capacity 10 as history), Sprint 2 active (10/27 to 11/09)."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "lifecycle_phase": "2. HARA / Risk Assessment", "start": "2026-10-12",
        "end": "2026-10-27", "capacity": 10, "status": "Closed", "closed_on": "2026-10-27",
    }).ok
    assert brain.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-09", "status": "Active",
    }).ok
    return brain


# a chain written under the rule of 2026-10-28 (10 business days, holidays stretching the dates): what Roy's
# database held on 2026-10-29, numbered 1 to 5, and what `sprint align` is for
OLD_CHAIN = [
    {"number": 1, "label": "SPRINT 1", "lifecycle_phase": "2. HARA / Risk Assessment", "start": "2026-10-12",
     "end": "2026-10-27", "capacity": 10, "status": "Closed", "closed_on": "2026-10-27"},
    {"number": 2, "label": "SPRINT 2", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
     "start": "2026-10-27", "end": "2026-11-09", "capacity": 8, "status": "Active"},
    {"number": 3, "label": "SPRINT 3", "start": "2026-11-10", "end": "2026-11-24", "capacity": 8, "status": "Planned",
     "goal": "Holidays: Veterans Day (11/11)"},
    {"number": 4, "label": "SPRINT 4", "start": "2026-11-25", "end": "2026-12-10", "capacity": 8, "status": "Planned",
     "goal": "Write the FSC"},
    {"number": 5, "label": "SPRINT 5", "start": "2026-12-11", "end": "2026-12-28", "capacity": 8, "status": "Planned"},
]


@pytest.fixture
def old_style(seeded):
    """The old chain loaded as a dump loads it (past the guard), with items, weeks and the seeded plan rows."""
    assert seeded.service("sprint").load_rows(OLD_CHAIN, "append")["inserted"] == 5
    for order, (title, points, status, extra) in enumerate([
        ("HARA", 3, "Done", {"kind": "Deliverable", "plan_row": 2, "carried_from": 1}),
        ("FSC", 3, "To Do", {"kind": "Deliverable", "plan_row": 3}),
        ("Intro meeting", 2, "Done", {"kind": "Meeting"}),
    ], 1):
        assert seeded.execute("create", entity=ITEM, data={
            "sprint": 2, "order": order, "title": title, "points": points, "status": status, **extra,
        }).ok
    for start, number in (("2026-10-12", 1), ("2026-10-19", 1), ("2026-10-26", 2)):
        assert seeded.execute("create", entity="week", data={
            "start": start, "sprint": number, "section": "Outcomes", "order": 1, "text": "- x",
        }).ok
    return seeded


def _items(brain, number):
    return brain.execute("list", entity=ITEM, filter=[f"sprint={number}"]).data


def _sprints(brain):
    return brain.execute("list", entity="sprint").data


def _dates(brain):
    return [(r["number"], r["label"], r["start"], r["end"], r["status"]) for r in _sprints(brain)]


def test_the_rule_is_fixed():
    assert SPRINT_CAPACITY == 8 and SPRINT_LENGTH == 14
    assert "8 points" in CAPACITY_RULE and "Closed" in CAPACITY_RULE
    assert CADENCE_NUMBER == 31 and CADENCE_START == dt.date(2026, 10, 27) and CADENCE_START.weekday() == 1
    assert "Tuesday" in CADENCE_RULE and "2026-10-27 to 2026-11-09" in CADENCE_RULE
    assert "what we know as sprint 3 is actually sprint 31" in SPRINT_RULE and "Tuesday to Tuesday" in SPRINT_RULE
    assert "Sprint 35 12/22 to 1/4" in SPRINT_RULE and "superseded" in SPRINT_RULE


def test_board_sums_points_and_counts_days(sprinted):
    board = sprinted.execute("sprint", action="board", as_of=AS_OF)
    assert board.ok, board.errors
    data = board.data
    assert (data["capacity"], data["committed"], data["done"], data["to_go"]) == (8, 8, 2, 6)
    assert data["unpointed"] == 1 and data["days_left"] == 12 and data["overdue"] is False and data["velocity"] is None
    assert data["warnings"] == ["sprint 1: 1 item(s) unpointed"] and len(data["items"]) == 4
    late = sprinted.execute("sprint", action="board", number=1, as_of="2026-11-10").data
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
    closed = sprinted.execute("sprint", action="close", as_of="2026-11-09", actor="me")
    assert closed.ok, closed.errors
    assert closed.data["done"] == 2 and closed.data["carried"] == 3 and closed.data["next"] == 2
    assert closed.data["velocity"] == 2.0 and closed.warnings == ["carried without points: ConOps located"]
    assert closed.data["sprint"]["status"] == "Closed" and closed.data["sprint"]["closed_on"] == "2026-11-09"
    nxt = _sprints(sprinted)[1]
    # the next sprint starts the day after the closed one's end, a Tuesday, and ends on the Monday 13 days later
    assert (nxt["number"], nxt["label"], nxt["status"], nxt["start"], nxt["end"], nxt["capacity"]) == (
        2, "SPRINT 2", "Active", "2026-11-10", "2026-11-23", 8,
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
        closed = sprinted.execute("sprint", action="close", number=number, as_of="2026-11-09")
        assert closed.ok, closed.errors
        return closed.data["velocity"]

    assert close_with(1, 0) == 8.0  # 3 + 3 + 2
    assert close_with(2, 4) == 6.0  # (8 + 4) / 2
    assert close_with(3, 2) == 4.7  # (8 + 4 + 2) / 3
    assert close_with(4, 0) == 2.0  # the window slides: (4 + 2 + 0) / 3
    board = sprinted.execute("sprint", action="board", as_of="2026-11-10").data
    assert board["sprint"]["number"] == 5 and board["velocity"] == 2.0 and board["committed"] == 0
    # each close opened the next sprint on the cadence, whatever the close date
    assert [(r["start"], r["end"]) for r in _sprints(sprinted)] == [
        ("2026-10-27", "2026-11-09"), ("2026-11-10", "2026-11-23"), ("2026-11-24", "2026-12-07"),
        ("2026-12-08", "2026-12-21"), ("2026-12-22", "2027-01-04"),
    ]


def test_start_opens_a_new_sprint_and_close_activates_the_planned_next_one(brain):
    assert not brain.execute("sprint", action="start", phase="99").ok
    started = brain.execute("sprint", action="start", phase="3", start="2026-10-27", goal="Clear the backlog")
    assert started.ok, started.errors
    row = started.data
    # a Tuesday start ends on the Monday 13 days later; capacity is the rule, not an option
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
    refused = brain.execute("sprint", action="start", number=4, as_of="2026-11-12")  # a Thursday
    assert not refused.ok and "not a Tuesday" in refused.errors[0] and CADENCE_RULE in refused.errors[0]
    activated = brain.execute("sprint", action="start", number=4, as_of="2026-11-10")
    assert activated.ok, activated.errors
    row = activated.data
    assert (row["status"], row["start"], row["end"], row["capacity"], row["label"]) == (
        "Active", "2026-11-10", "2026-11-23", 8, "SPRINT 4",
    )


def test_start_follows_on_from_the_previous_sprint_by_default(chained):
    assert chained.execute("sprint", action="close", as_of="2026-11-09").data["next"] == 3  # 3 opened, 11/10
    assert chained.execute("sprint", action="close", as_of="2026-11-20").data["next"] == 4  # 4 opened, 11/24
    assert chained.execute("sprint", action="close", as_of="2026-12-01").data["next"] == 5
    assert _dates(chained)[2:] == [
        (3, "SPRINT 3", "2026-11-10", "2026-11-23", "Closed"), (4, "SPRINT 4", "2026-11-24", "2026-12-07", "Closed"),
        (5, "SPRINT 5", "2026-12-08", "2026-12-21", "Active"),
    ]
    assert chained.execute("update", entity="sprint", id=5, set=["status=Planned"]).ok
    # no --start: the new sprint starts the day after sprint 5 ends, never on an arbitrary --as-of
    row = chained.execute("sprint", action="start", as_of="2026-12-30").data
    assert (row["number"], row["start"], row["end"]) == (5, "2026-12-08", "2026-12-21")  # the planned one, dated
    assert chained.execute("sprint", action="close", as_of="2026-12-21").ok
    assert chained.execute("delete", entity="sprint", id=_sprints(chained)[-1]["id"]).ok  # the close opened 6
    row = chained.execute("sprint", action="start", as_of="2026-12-30").data  # a new 6, by hand, no --start
    assert (row["number"], row["start"], row["end"]) == (6, "2026-12-22", "2027-01-04")
    refused = chained.execute("sprint", action="start", start="2027-01-05", end="2027-01-19")
    assert not refused.ok and "sprint 6 is active" in refused.errors[0]
    assert chained.execute("sprint", action="close", as_of="2027-01-04").ok
    assert chained.execute("delete", entity="sprint", id=_sprints(chained)[-1]["id"]).ok  # the close opened 7
    refused = chained.execute("sprint", action="start", start="2027-01-05", end="2027-01-19")
    assert not refused.ok and "not the Monday 13 days after 2027-01-05 (2027-01-18)" in refused.errors[0]
    refused = chained.execute("sprint", action="start", start="2027-01-12")
    assert not refused.ok and "sprint 7 starts 2027-01-12, not 2027-01-05" in refused.errors[0]


def test_holidays_never_move_a_sprint(brain):
    assert brain.execute("holiday", action="load", file=str(SEED_HOLIDAYS)).ok
    row = brain.execute("sprint", action="start", start="2026-11-10").data  # Veterans Day inside: a day off
    assert row["end"] == "2026-11-23"
    assert brain.execute("sprint", action="close", as_of="2026-11-23").data["next"] == 2
    second = brain.execute("list", entity="sprint", filter=["number=2"]).data[0]
    assert second["start"] == "2026-11-24" and second["end"] == "2026-12-07"  # Thanksgiving and the company Friday
    assert brain.execute("sprint", action="close", as_of="2026-12-07").ok
    assert brain.execute("sprint", action="close", as_of="2026-12-21").ok
    fourth = brain.execute("list", entity="sprint", filter=["number=4"]).data[0]
    assert (fourth["start"], fourth["end"]) == ("2026-12-22", "2027-01-04")  # straight through Christmas and New Year


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


def test_config_ignores_the_days_and_the_capacity_keys_with_a_warning(tmp_path, monkeypatch):
    from asi_kletz.brain import ENV_CONFIG, load_config

    config = tmp_path / "kletz.toml"
    config.write_text('sprint_capacity = 8\nsprint_days = 7\ntracker_byline = "Role"\n', encoding="utf-8")
    loaded = load_config(config)
    assert "sprint_days" not in loaded and "sprint_capacity" not in loaded and loaded["tracker_byline"] == "Role"
    assert loaded["warnings"] == [
        f"sprint_capacity = 8 in kletz.toml is ignored: {CAPACITY_RULE}",
        f"sprint_days = 7 in kletz.toml is ignored: {CADENCE_RULE}",
    ]
    config.write_text('default_points = 3\n', encoding="utf-8")
    assert "warnings" not in load_config(config)
    config.write_text('sprint_capacity = "10"\nsprint_days = 7\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "c.db") as b:
        assert b.sprint_capacity == 8 and b.sprint_length == 14 and not hasattr(b, "sprint_days")
        status = b.execute("status").data
        assert status["sprint_capacity"] == 8 and status["sprint_length_days"] == 14 and "sprint_days" not in status
        assert status["config_warnings"] == [
            f"sprint_capacity = '10' in kletz.toml is ignored: {CAPACITY_RULE}",
            f"sprint_days = 7 in kletz.toml is ignored: {CADENCE_RULE}",
        ]
        row = b.execute("sprint", action="start", start="2026-10-27").data
        assert row["capacity"] == 8 and row["end"] == "2026-11-09"  # fourteen days, whatever the file said
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


# -- the cadence on the rows (the law of 2026-10-29) --------------------------------------------------------


def test_a_sprint_starts_on_a_tuesday_and_ends_on_the_monday_13_days_later(chained):
    refused = chained.execute("create", entity="sprint", data={"number": 3, "start": "2026-11-11", "status": "Planned"})
    assert not refused.ok and refused.errors == [f"start 2026-11-11 is a Wednesday, not a Tuesday: {CADENCE_RULE}"]
    refused = chained.execute("create", entity="sprint", data={
        "number": 3, "start": "2026-11-10", "end": "2026-11-24", "status": "Planned",
    })
    assert not refused.ok and refused.errors == [
        f"end 2026-11-24 is not the Monday 13 days after 2026-11-10 (2026-11-23): {CADENCE_RULE}"
    ]
    filled = chained.execute("create", entity="sprint", data={"number": 3, "start": "2026-11-10", "status": "Planned"})
    assert filled.ok and filled.data["end"] == "2026-11-23"  # an empty end is the cadence's
    # an update of the dates is checked the same way; one that leaves them alone is not
    assert chained.execute("update", entity="sprint", id=3, set=["goal=Write the FSC"]).ok
    refused = chained.execute("update", entity="sprint", id=3, set=["end=2026-11-20"])
    assert not refused.ok and "not the Monday 13 days after 2026-11-10" in refused.errors[0]
    refused = chained.execute("update", entity="sprint", id=3, set=["start=2026-11-16"])
    assert not refused.ok and "is a Monday, not a Tuesday" in refused.errors[0]
    assert chained.execute("update", entity="sprint", id=3, set=["end="]).ok  # cleared: filled again
    assert chained.execute("get", entity="sprint", id=3).data["end"] == "2026-11-23"


def test_consecutive_sprints_stay_gapless(chained):
    refused = chained.execute("create", entity="sprint", data={"number": 3, "start": "2026-11-17", "status": "Planned"})
    assert not refused.ok and refused.errors == [
        f"sprint 3 starts 2026-11-17, not 2026-11-10, the day after sprint 2 ends (2026-11-09): {CADENCE_RULE}"
    ]
    assert chained.execute("create", entity="sprint", data={"number": 3, "start": "2026-11-10", "status": "Planned"}).ok
    assert chained.execute("create", entity="sprint", data={"number": 4, "start": "2026-11-24", "status": "Planned"}).ok
    refused = chained.execute("create", entity="sprint", data={"number": 5, "start": "2026-12-15", "status": "Planned"})
    assert not refused.ok and "not 2026-12-08, the day after sprint 4 ends (2026-12-07)" in refused.errors[0]
    refused = chained.execute("update", entity="sprint", id=4, set=["start=2026-12-01"])
    assert not refused.ok and "sprint 4 starts 2026-12-01, not 2026-11-24, the day after sprint 3" in refused.errors[0]
    # numbers and dates lock together: sprint 7 is three sprints after sprint 4, whether 5 and 6 exist yet or not
    refused = chained.execute("create", entity="sprint", data={"number": 7, "start": "2026-12-22", "status": "Planned"})
    assert not refused.ok and refused.errors == [
        f"sprint 7 starts 2026-12-22, not 2027-01-05, 2 sprint(s) of 14 days after sprint 4 ends (2026-12-07): "
        f"{CADENCE_RULE}"
    ]
    assert chained.execute("create", entity="sprint", data={"number": 7, "start": "2027-01-05", "status": "Planned"}).ok
    assert chained.execute("create", entity="sprint", data={"number": 6, "start": "2026-12-22", "status": "Planned"}).ok
    assert chained.execute("create", entity="sprint", data={"number": 5, "start": "2026-12-08", "status": "Planned"}).ok
    assert [r["start"] for r in _sprints(chained)[1:]] == [
        "2026-10-27", "2026-11-10", "2026-11-24", "2026-12-08", "2026-12-22", "2027-01-05",
    ]
    # a sprint that starts before the anchor is history: any dates, edited freely
    old = chained.execute("create", entity="sprint", data={
        "number": 0, "start": "2026-09-30", "end": "2026-10-11", "status": "Closed", "capacity": 6,
    })
    assert old.ok, old.errors
    assert chained.execute("update", entity="sprint", id=old.data["id"], set=["end=2026-10-09"]).ok
    assert chained.execute("update", entity="sprint", id=1, set=["start=2026-10-14"]).ok  # 10/12 to 10/27 as it was
    assert chained.execute("update", entity="sprint", id=1, set=["start=2026-10-12"]).ok


# -- the planner ------------------------------------------------------------------------------------------


def test_plan_extends_the_chain_three_years_on_the_cadence(chained):
    seen = []
    chained.events.subscribe("sprint.planned", lambda topic, event: seen.append(event))
    result = chained.execute("sprint", action="plan", actor="me")
    assert result.ok, result.errors
    data = result.data
    assert (data["added"], data["replanned"], data["length_days"], data["capacity"], data["holidays"]) == (
        79, 0, 14, 8, [],
    )
    assert data["first"] == {"number": 3, "start": "2026-11-10", "end": "2026-11-23"}
    assert data["last"] == {"number": 81, "start": "2029-11-06", "end": "2029-11-19"} and data["until"] == "2029-11-09"
    rows = _sprints(chained)
    assert len(rows) == 81 and [r["status"] for r in rows[2:]] == ["Planned"] * 79
    assert all(r["capacity"] == 8 and r["label"] == f"SPRINT {r['number']}" for r in rows[2:])
    assert all(not r["lifecycle_phase"] and not r["goal"] for r in rows[2:])
    # the picture's seven sprints, exactly, from the one that is Sprint 31 in it
    assert [(r["number"] + 29, r["start"], r["end"]) for r in rows[1:8]] == PICTURE
    for previous, row in zip(rows[1:], rows[2:], strict=False):  # Tuesday to Monday, the next the day after
        start, end = dt.date.fromisoformat(row["start"]), dt.date.fromisoformat(row["end"])
        assert start.weekday() == 1 and (end - start).days == 13
        assert (start - dt.date.fromisoformat(previous["end"])).days == 1
    assert rows[0]["capacity"] == 10 and rows[1]["status"] == "Active"  # untouched
    assert seen[0]["added"] == 79 and seen[0]["actor"] == "me"
    again = chained.execute("sprint", action="plan")
    assert again.ok and again.data["added"] == 0 and again.data["first"] is None and len(_sprints(chained)) == 81


def test_plan_names_the_holidays_and_never_moves_for_them(chained):
    assert chained.execute("holiday", action="load", file=str(SEED_HOLIDAYS)).ok
    data = chained.execute("sprint", action="plan").data
    assert data["added"] == 79 and data["first"] == {"number": 3, "start": "2026-11-10", "end": "2026-11-23"}
    assert data["last"] == {"number": 81, "start": "2029-11-06", "end": "2029-11-19"}  # the same chain
    assert len(data["holidays"]) == 38 and data["holidays"][0] == "Veterans Day (2026-11-11)"
    assert data["holidays"][-1] == "Veterans Day (2029-11-12)"
    rows = _sprints(chained)
    assert [(r["number"] + 29, r["start"], r["end"]) for r in rows[1:8]] == PICTURE
    assert rows[2]["goal"] == "Holidays: Veterans Day (11/11)"
    assert rows[3]["goal"] == "Holidays: Thanksgiving Day (11/26), Day after Thanksgiving (company, assumed) (11/27)"
    christmas = rows[5]  # Sprint 35 of the picture runs straight through Christmas and New Year
    assert christmas["goal"] == (
        "Holidays: Christmas Eve (company, assumed) (12/24), Christmas Day (12/25), New Year's Day (1/1)"
    )
    assert (dt.date.fromisoformat(christmas["end"]) - dt.date.fromisoformat(christmas["start"])).days + 1 == 14
    assert rows[4]["goal"] is None and sum(1 for r in rows[2:] if r["goal"]) == 31


def test_plan_until_a_date_and_the_errors(chained):
    data = chained.execute("sprint", action="plan", until="2027-01-31").data
    assert data["added"] == 6 and data["last"]["number"] == 8 and data["last"]["end"] == "2027-02-01"
    assert chained.execute("sprint", action="plan", until="2027-01-31").data["added"] == 0
    more = chained.execute("sprint", action="plan", until="2027-03-01").data
    assert more["added"] == 2 and more["first"] == {"number": 9, "start": "2027-02-02", "end": "2027-02-15"}
    assert more["last"] == {"number": 10, "start": "2027-02-16", "end": "2027-03-01"}  # starts on or before the horizon
    assert not chained.execute("sprint", action="plan", days=5).ok  # the business-day length is gone
    assert not chained.execute("sprint", action="plan", years=0).ok
    assert not chained.execute("sprint", action="plan", until="someday").ok
    assert not chained.execute("sprint", action="plan", capacity=8).ok  # no such option


def test_plan_needs_a_sprint_to_continue_from(brain):
    refused = brain.execute("sprint", action="plan")
    assert not refused.ok and "no sprint to continue from" in refused.errors[0]
    assert brain.execute("create", entity="sprint", data={"number": 1, "status": "Planned"}).ok
    refused = brain.execute("sprint", action="plan")
    assert not refused.ok and "has no end date" in refused.errors[0]


def test_replan_puts_an_older_chain_back_on_the_cadence(old_style):
    """Planned sprints dated under the old rule (loaded past the guard, as a dump is) come back onto the cadence
    after the active sprint; a human goal is kept, a holiday line the planner wrote follows the new dates."""
    assert old_style.execute("holiday", action="load", file=str(SEED_HOLIDAYS)).ok
    before = {r["number"]: (r["start"], r["end"]) for r in _sprints(old_style)}
    assert before[3] == ("2026-11-10", "2026-11-24") and before[5] == ("2026-12-11", "2026-12-28")
    data = old_style.execute("sprint", action="plan", until="2027-01-31", replan=True).data
    assert data["replanned"] == 3 and data["added"] == 3
    rows = {r["number"]: r for r in _sprints(old_style)}
    assert (rows[1]["start"], rows[1]["end"], rows[2]["start"], rows[2]["end"]) == (
        before[1] + before[2]
    )  # the closed and the active sprint never move
    assert (rows[3]["start"], rows[3]["end"], rows[3]["goal"]) == (
        "2026-11-10", "2026-11-23", "Holidays: Veterans Day (11/11)",
    )
    assert (rows[4]["start"], rows[4]["end"], rows[4]["goal"]) == ("2026-11-24", "2026-12-07", "Write the FSC")
    assert (rows[5]["start"], rows[5]["end"], rows[5]["goal"]) == ("2026-12-08", "2026-12-21", None)
    assert (rows[6]["start"], rows[6]["end"]) == ("2026-12-22", "2027-01-04")
    assert rows[6]["goal"] == (
        "Holidays: Christmas Eve (company, assumed) (12/24), Christmas Day (12/25), New Year's Day (1/1)"
    )
    assert (rows[7]["start"], rows[8]["end"]) == ("2027-01-05", "2027-02-01")
    assert data["holidays"][:2] == ["Veterans Day (2026-11-11)", "Thanksgiving Day (2026-11-26)"]
    assert old_style.execute("sprint", action="plan", until="2027-01-31", replan=True).data["replanned"] == 0


# -- the alignment (0.18.0) --------------------------------------------------------------------------------


def _plan_rows(brain):
    return {r["id"]: (r["sprint"], r["sprint_start"], r["sprint_end"], r["deadline"]) for r in
            brain.execute("list", entity=PLAN).data}


def test_align_check_prints_the_mapping_and_changes_nothing(old_style):
    before = _dates(old_style)
    audited = len(old_style.storage.audit_tail(100))
    result = old_style.execute("sprint", action="align", number=31, start="2026-10-27", check=True)
    assert result.ok, result.errors
    data = result.data
    assert data["check"] is True and data["offset"] == 29 and data["anchor"] == {"id": 2, "from": 2, "to": 31}
    assert (data["sprints"], data["renumbered"], data["redated"], data["scheduled"]) == (5, 5, 3, 0)
    assert data["references"] == {
        "sprint_item.sprint": 3, "sprint_item.carried_from": 1, "week.sprint": 3, "safety_plan_row.sprint": 2,
    }
    assert [(m["from"], m["to"], m["label"][1], m["start"][1], m["end"][1], m["changed"]) for m in data["mapping"]] == [
        (1, 30, "SPRINT 30", "2026-10-12", "2026-10-27", ["number"]),
        (2, 31, "SPRINT 31", "2026-10-27", "2026-11-09", ["number"]),
        (3, 32, "SPRINT 32", "2026-11-10", "2026-11-23", ["end", "number"]),
        (4, 33, "SPRINT 33", "2026-11-24", "2026-12-07", ["end", "number", "start"]),
        (5, 34, "SPRINT 34", "2026-12-08", "2026-12-21", ["end", "number", "start"]),
    ]
    assert data["mapping"][2]["start"] == ("2026-11-10", "2026-11-10") and data["mapping"][2]["label"][0] == "SPRINT 3"
    assert _dates(old_style) == before and len(old_style.storage.audit_tail(100)) == audited
    assert all(i["sprint"] == 2 for i in old_style.execute("list", entity=ITEM).data)


def test_align_renumbers_redates_and_carries_every_reference_once(old_style):
    seen = []
    old_style.events.subscribe("sprint.aligned", lambda topic, event: seen.append(event))
    # row 2 at 9 points: 3 committed as the HARA item, the 6 left spill into sprint 3 (sprint 2 is full); row 3's
    # 2 points are the FSC item's 3, so it finishes in sprint 2
    assert old_style.execute("update", entity=PLAN, id=2, set=["points=9"]).ok
    plan_before = _plan_rows(old_style)
    assert plan_before[2] == (3, "2026-11-10", "2026-11-24", "2026-11-24") and plan_before[3][0] == 2
    result = old_style.execute("sprint", action="align", number=31, start="2026-10-27", actor="me")
    assert result.ok, result.errors
    assert (result.data["check"], result.data["offset"], result.data["renumbered"], result.data["redated"]) == (
        False, 29, 5, 3,
    )
    assert _dates(old_style) == [
        (30, "SPRINT 30", "2026-10-12", "2026-10-27", "Closed"),  # history keeps its dates
        (31, "SPRINT 31", "2026-10-27", "2026-11-09", "Active"),
        (32, "SPRINT 32", "2026-11-10", "2026-11-23", "Planned"),
        (33, "SPRINT 33", "2026-11-24", "2026-12-07", "Planned"),
        (34, "SPRINT 34", "2026-12-08", "2026-12-21", "Planned"),
    ]
    sprints = {r["number"]: r for r in _sprints(old_style)}
    assert sprints[30]["capacity"] == 10 and sprints[32]["goal"] == "Holidays: Veterans Day (11/11)"
    items = old_style.execute("list", entity=ITEM).data
    assert [(i["title"], i["sprint"], i["carried_from"]) for i in items] == [
        ("HARA", 31, 30), ("FSC", 31, None), ("Intro meeting", 31, None),
    ]
    assert [(w["start"], w["sprint"]) for w in old_style.execute("list", entity="week").data] == [
        ("2026-10-12", 30), ("2026-10-19", 30), ("2026-10-26", 31),
    ]
    plan = _plan_rows(old_style)
    assert plan[1] == (None, None, None, "Phase 1 exit")  # Done: history
    assert plan[2] == (32, "2026-11-10", "2026-11-23", "2026-11-23") and result.data["scheduled"] == 1
    assert plan[3] == (31, "2026-10-27", "2026-11-09", "2026-11-09")
    tail = old_style.storage.audit_tail(2)
    assert [t["action"] for t in tail] == ["schedule", "align"] and tail[1]["actor"] == "me"
    assert tail[0]["payload"]["count"] == 1
    assert tail[1]["payload"] == {
        "number": 31, "start": "2026-10-27", "offset": 29, "renumbered": 5, "redated": 3,
        "references": {"sprint_item.sprint": 3, "sprint_item.carried_from": 1, "week.sprint": 3,
                       "safety_plan_row.sprint": 2},
        "mapping": {"1": 30, "2": 31, "3": 32, "4": 33, "5": 34},
    }
    event = {k: seen[0][k] for k in ("number", "start", "offset", "renumbered", "redated", "actor")}
    assert len(seen) == 1 and event == {
        "number": 31, "start": "2026-10-27", "offset": 29, "renumbered": 5, "redated": 3, "actor": "me",
    }
    assert old_style.execute("sprint", action="board", as_of="2026-10-29").data["sprint"]["number"] == 31
    # idempotent: the second run finds the chain aligned, writes nothing, audits nothing
    audited = len(old_style.storage.audit_tail(100))
    again = old_style.execute("sprint", action="align", number=31, start="2026-10-27")
    assert again.ok and (again.data["renumbered"], again.data["redated"], again.data["scheduled"]) == (0, 0, 0)
    assert again.data["references"] == {k: 0 for k in again.data["references"]}
    assert len(old_style.storage.audit_tail(100)) == audited and _dates(old_style)[1][0] == 31
    # and the chain continues on the cadence from there
    assert old_style.execute("sprint", action="plan", until="2027-01-31").data["first"] == {
        "number": 35, "start": "2026-12-22", "end": "2027-01-04",
    }
    assert old_style.execute("sprint", action="close", as_of="2026-11-09").data["next"] == 32


def test_align_refusals(old_style):
    for args, text in (
        ({"number": 31, "start": "2026-10-28"}, "2026-10-28 is a Wednesday, not a Tuesday"),
        ({"number": 31, "start": "2026-11-03"}, "no sprint starts on 2026-11-03"),
        ({"number": 1, "start": "2026-10-27"}, "sprint 1 would become sprint 0; numbers start at 1"),
        ({"number": 31}, "needs the number and --start"),
        ({"start": "2026-10-27"}, "needs the number and --start"),
        ({"number": 31, "start": "Tuesday"}, "is not a date"),
    ):
        refused = old_style.execute("sprint", action="align", **args)
        assert not refused.ok and text in refused.errors[0], (args, refused.errors)
    assert old_style.service("sprint").load_rows([{"number": 3, "label": "SPRINT 3", "status": "Planned"}], "append")
    refused = old_style.execute("sprint", action="align", number=31, start="2026-10-27")
    assert not refused.ok and refused.errors == ["two sprints share a number: 3; fix that first"]
    assert _dates(old_style)[1][0] == 2  # nothing moved


def test_cli_has_the_three_verbs():
    verbs = build_parser()._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    assert {"tracker", "sprint", "holiday"} <= set(verbs)
    ns = build_parser().parse_args(["tracker", "build", "week", "--jira", "--as-of", "2026-10-28"])
    assert ns.what == "week" and ns.jira is True and ns.as_of == "2026-10-28"
    ns = build_parser().parse_args(["sprint", "point", "--item", "3", "--points", "5"])
    assert ns.item == 3 and ns.points == 5 and ns.number is None
    ns = build_parser().parse_args(["sprint", "plan", "--years", "2", "--replan"])
    assert ns.years == 2 and ns.replan is True and ns.until is None
    ns = build_parser().parse_args(["sprint", "align", "31", "--start", "2026-10-27", "--check"])
    assert ns.action == "align" and ns.number == 31 and ns.start == "2026-10-27" and ns.check is True
    for bad in (["sprint", "start", "--capacity", "8"], ["sprint", "plan", "--days", "10"]):
        with pytest.raises(SystemExit):
            build_parser().parse_args(bad)
    ns = build_parser().parse_args(["holiday", "load", "data/us-holidays-2026-2029.json"])
    assert ns.action == "load" and ns.file == "data/us-holidays-2026-2029.json"
