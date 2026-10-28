"""The agile rules: ten points a sprint, capacity as a warning, close and carry, one active sprint, velocity."""

from __future__ import annotations

import pytest

from asi_kletz.automation.cli import build_parser

ITEM = "sprint_item"
AS_OF = "2026-10-28"


@pytest.fixture
def sprinted(brain):
    """Sprint 1, active, 10/27 to 11/10, with four items: 3 and 5 points open, one unpointed, one done at 2."""
    assert brain.execute("create", entity="sprint", data={
        "number": 1, "label": "SPRINT 1", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "start": "2026-10-27", "end": "2026-11-10", "capacity": 10, "status": "Active",
    }).ok
    for order, (title, points, status) in enumerate([
        ("Safety Plan dated", 3, "To Do"), ("Activity Flow reviewed", 5, "In Progress"),
        ("ConOps located", None, "To Do"), ("Intro meeting", 2, "Done"),
    ], 1):
        assert brain.execute("create", entity=ITEM, data={
            "sprint": 1, "order": order, "kind": "Deliverable", "title": title, "points": points, "status": status,
        }).ok
    return brain


def _items(brain, number):
    return brain.execute("list", entity=ITEM, filter=[f"sprint={number}"]).data


def test_board_sums_points_and_counts_days(sprinted):
    board = sprinted.execute("sprint", action="board", as_of=AS_OF)
    assert board.ok, board.errors
    data = board.data
    assert (data["capacity"], data["committed"], data["done"], data["to_go"]) == (10, 10, 2, 8)
    assert data["unpointed"] == 1 and data["days_left"] == 13 and data["overdue"] is False and data["velocity"] is None
    assert data["warnings"] == ["sprint 1: 1 item(s) unpointed"] and len(data["items"]) == 4
    late = sprinted.execute("sprint", action="board", number=1, as_of="2026-11-12").data
    assert late["days_left"] == 0 and late["overdue"] is True
    assert not sprinted.execute("sprint", action="board", number=9).ok


def test_point_validates_and_warns_over_capacity(sprinted):
    third = _items(sprinted, 1)[2]
    assert not sprinted.execute("sprint", action="point", item=third["id"], points=11).ok
    assert not sprinted.execute("sprint", action="point", item=third["id"], points="three").ok
    over = sprinted.execute("sprint", action="point", item=third["id"], points=5)
    assert over.ok and over.data["points"] == 5 and over.warnings == ["sprint 1 committed 15 of 10 points"]
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
    sprints = sprinted.execute("list", entity="sprint").data
    nxt = sprints[1]
    assert (nxt["number"], nxt["label"], nxt["status"], nxt["start"], nxt["end"], nxt["capacity"]) == (
        2, "SPRINT 2", "Active", "2026-11-10", "2026-11-24", 10,
    )
    assert nxt["lifecycle_phase"] == sprints[0]["lifecycle_phase"]
    assert [(i["title"], i["status"]) for i in _items(sprinted, 1)] == [
        ("Safety Plan dated", "Carried"), ("Activity Flow reviewed", "Carried"), ("ConOps located", "Carried"),
        ("Intro meeting", "Done"),
    ]
    carried = _items(sprinted, 2)
    assert [(i["title"], i["points"], i["status"], i["carried_from"]) for i in carried] == [
        ("Safety Plan dated", 3, "To Do", 1), ("Activity Flow reviewed", 5, "To Do", 1),
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

    assert close_with(1, 0) == 10.0  # 3 + 5 + 2
    assert close_with(2, 4) == 7.0  # (10 + 4) / 2
    assert close_with(3, 2) == 5.3  # (10 + 4 + 2) / 3
    assert close_with(4, 0) == 2.0  # the window slides: (4 + 2 + 0) / 3
    board = sprinted.execute("sprint", action="board", as_of="2026-11-10").data
    assert board["sprint"]["number"] == 5 and board["velocity"] == 2.0 and board["committed"] == 0


def test_start_opens_a_new_sprint_and_close_activates_the_planned_next_one(brain):
    assert not brain.execute("sprint", action="start", phase="99").ok
    started = brain.execute("sprint", action="start", phase="3", start="2026-10-27", goal="Clear the backlog")
    assert started.ok, started.errors
    row = started.data
    assert (row["number"], row["label"], row["status"], row["end"]) == (1, "SPRINT 1", "Active", "2026-11-10")
    assert row["capacity"] == 10
    assert row["lifecycle_phase"] == "3. Functional Safety Concept (FSC)" and row["goal"] == "Clear the backlog"
    assert brain.execute("create", entity="sprint", data={"number": 2, "status": "Planned", "label": "SPRINT 2"}).ok
    closed = brain.execute("sprint", action="close", as_of="2026-11-10")
    assert closed.ok and closed.data["next"] == 2
    second = brain.execute("list", entity="sprint", filter=["number=2"]).data[0]
    assert second["status"] == "Active" and second["start"] == "2026-11-10" and second["end"] == "2026-11-24"
    assert second["capacity"] == 10 and second["label"] == "SPRINT 2"
    refused = brain.execute("sprint", action="start", number=2)
    assert not refused.ok and "sprint 2 is active" in refused.errors[0]


def test_start_activates_a_planned_sprint_when_none_is_active(brain):
    assert brain.execute("create", entity="sprint", data={"number": 4, "status": "Planned"}).ok
    assert not brain.execute("sprint", action="start", number=9).ok
    activated = brain.execute("sprint", action="start", number=4, as_of="2026-11-10")
    assert activated.ok, activated.errors
    row = activated.data
    assert (row["status"], row["start"], row["end"], row["capacity"], row["label"]) == (
        "Active", "2026-11-10", "2026-11-24", 10, "SPRINT 4",
    )


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


def test_config_sets_the_sprint_defaults(tmp_path, monkeypatch):
    from asi_kletz import Brain
    from asi_kletz.brain import ENV_CONFIG, load_config

    config = tmp_path / "kletz.toml"
    config.write_text('sprint_capacity = 8\nsprint_days = 7\ntracker_byline = "Role"\n', encoding="utf-8")
    assert load_config(config)["sprint_capacity"] == 8 and load_config(config)["sprint_days"] == 7
    config.write_text('sprint_capacity = "8"\nsprint_days = true\n', encoding="utf-8")
    assert "sprint_capacity" not in load_config(config) and "sprint_days" not in load_config(config)
    config.write_text("sprint_capacity = 8\nsprint_days = 7\n", encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "c.db") as b:
        assert b.sprint_capacity == 8 and b.sprint_days == 7
        status = b.execute("status").data
        assert status["sprint_capacity"] == 8 and status["tracker"]["byline"] == "FuSa Engineer"
        row = b.execute("sprint", action="start", start="2026-10-27").data
        assert row["capacity"] == 8 and row["end"] == "2026-11-03"
        assert not b.execute("sprint", action="point", item=1, points=9).ok


def test_cli_has_the_two_verbs():
    verbs = build_parser()._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    assert {"tracker", "sprint"} <= set(verbs)
    ns = build_parser().parse_args(["tracker", "build", "week", "--jira", "--as-of", "2026-10-28"])
    assert ns.what == "week" and ns.jira is True and ns.as_of == "2026-10-28"
    ns = build_parser().parse_args(["sprint", "point", "--item", "3", "--points", "5"])
    assert ns.item == 3 and ns.points == 5 and ns.number is None
