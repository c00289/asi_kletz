"""The scheduler: which sprint each deliverable's last point lands in, and so its deadline. Pure.

``schedule(rows, sprints, items, floor)`` walks the plan in plan order and pours each deliverable's weight
into the sprint chain. The sprint rule (owner, 2026-10-28): a sprint spans 10 business days; capacity is 8
points, company policy, fixed (``SPRINT_CAPACITY``; a Closed sprint keeps its own as history); sprints are
consecutive, numbered across the programme. Nothing here reads or writes a database: the rows, the sprints
and the sprint items come in as the lists the services hold, the answer goes out as plain dicts.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .plan_queries import one_line
from .sprint_queries import capacity_of, committed

DONE = "Done"
EXCLUDED = ("Blocked", "Alternative", "Out-of-Scope")  # no sprint, no deadline, no capacity consumed
SOURCE_POINTS, SOURCE_DEFAULT, SOURCE_FLOOR, SOURCE_DONE, SOURCE_EXCLUDED = (
    "points", "default", "floor", "done", "excluded",
)


@dataclass
class Schedule:
    assignments: dict[int, tuple[int | None, str | None]] = field(default_factory=dict)  # row id -> (sprint, deadline)
    spans: dict[int, tuple[str | None, str | None]] = field(default_factory=dict)  # row id -> the sprint's (start, end)
    sources: dict[int, str] = field(default_factory=dict)  # row id -> where its weight came from
    weights: dict[int, int] = field(default_factory=dict)  # row id -> the weight used
    committed: dict[int, int] = field(default_factory=dict)  # row id -> points already committed as its own items
    occupancy: dict[int, set[int]] = field(default_factory=dict)  # row id -> the sprints it takes points from
    warnings: list[str] = field(default_factory=list)


def weight_of(row: dict[str, Any], floor: int) -> tuple[int, str]:
    """``points`` if set, else ``default_points``, else the floor; with the source's name."""
    if row.get("points"):
        return int(row["points"]), SOURCE_POINTS
    if row.get("default_points"):
        return int(row["default_points"]), SOURCE_DEFAULT
    return int(floor), SOURCE_FLOOR


def chain(sprints: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sprints to schedule into: the Active one (else the first Planned) and every later one that is not
    Closed, by number."""
    ordered = sorted(sprints, key=lambda s: (int(s.get("number") or 0), s.get("id") or 0))
    active = [s for s in ordered if s.get("status") == "Active"]
    first = active[0] if active else next((s for s in ordered if s.get("status") == "Planned"), None)
    if first is None:
        return []
    return [s for s in ordered if int(s["number"]) >= int(first["number"]) and s.get("status") != "Closed"]


def free_capacity(sprint: dict[str, Any], items: Iterable[dict[str, Any]]) -> int:
    """The sprint's capacity minus the points of its committed items that are not Carried."""
    own = [i for i in items if i.get("sprint") == sprint.get("number")]
    return max(0, capacity_of(sprint) - committed(own))


UidMap = dict[str, int]  # a plan row's uid -> its id, from the rows; the pointer an item carries since 0.13.0


def uid_map(rows: Iterable[dict[str, Any]]) -> UidMap:
    return {str(r["uid"]): int(r["id"]) for r in rows if r.get("uid") and r.get("id") is not None}


def plan_row_of(item: dict[str, Any], uids: UidMap | None = None) -> int | None:
    """The plan row an item points at: by ``plan_uid`` when the item carries one the rows know (0.13.0), else
    by ``plan_row``."""
    if uids and item.get("plan_uid") in uids:
        return uids[item["plan_uid"]]
    return int(item["plan_row"]) if item.get("plan_row") else None


def own_items(items: Iterable[dict[str, Any]], uids: UidMap | None = None) -> list[dict[str, Any]]:
    """A deliverable's own sprint items: kind Deliverable, pointing at a plan row, not Carried (the copy left
    behind by a carry is a trace, the item itself lives on in the next sprint)."""
    return [
        i for i in items
        if i.get("kind") == "Deliverable" and plan_row_of(i, uids) is not None and i.get("status") != "Carried"
    ]


def pins(
    items: Iterable[dict[str, Any]], numbers: set[int] | None = None, uids: UidMap | None = None
) -> dict[int, int]:
    """``{plan row id: sprint number}``: the last sprint that holds one of the deliverable's own items (any
    sprint when ``numbers`` is None, else sprints of the chain only); a deliverable never finishes before it."""
    out: dict[int, int] = {}
    for item in own_items(items, uids):
        number = item.get("sprint")
        if number is None or (numbers is not None and number not in numbers):
            continue
        row_id = plan_row_of(item, uids)
        out[row_id] = max(out.get(row_id, 0), int(number))
    return out


def committed_points(items: Iterable[dict[str, Any]], uids: UidMap | None = None) -> dict[int, int]:
    """``{plan row id: points}``: the part of each deliverable already committed as its own sprint items (any
    sprint, any status but Carried; an unpointed item commits nothing). The owner's rule, 2026-10-28."""
    out: dict[int, int] = {}
    for item in own_items(items, uids):
        if item.get("points"):
            row_id = plan_row_of(item, uids)
            out[row_id] = out.get(row_id, 0) + int(item["points"])
    return out


def schedule(
    rows: Iterable[dict[str, Any]], sprints: Iterable[dict[str, Any]], items: Iterable[dict[str, Any]], floor: int
) -> Schedule:
    """The plan scheduled: rows in plan order, each poured into successive sprints as capacity allows.

    A Done row keeps what it has (absent from ``assignments``); Blocked, Alternative and Out-of-Scope get
    ``(None, None)``; every other row gets the number of the sprint its last point lands in and that sprint's
    ``end``, or ``(None, None)`` and a warning when the chain runs out.

    The points of a deliverable's own sprint items are the part of it already committed (0.11.4): they come
    off its weight, the remainder pours from the last sprint that holds one of its items onward, and the
    items' points reduce their sprints' free capacity once, as any committed item's do. A remainder of 0
    finishes in that last sprint, Closed or not.
    """
    items = list(items)
    rows = list(rows)
    uids = uid_map(rows)
    line = chain(sprints)
    free = [free_capacity(s, items) for s in line]
    numbers = {int(s["number"]) for s in line}
    index_of = {int(s["number"]): i for i, s in enumerate(line)}
    by_number = {int(s["number"]): s for s in sprints if s.get("number") is not None}
    pinned = pins(items, numbers, uids)
    held = pins(items, None, uids)  # the last sprint holding one of the deliverable's items, Closed ones included
    committed = committed_points(items, uids)
    mine = own_items(items, uids)
    out = Schedule()
    for row in rows:
        row_id = int(row["id"])
        status = row.get("status")
        if status == DONE:
            out.sources[row_id] = SOURCE_DONE
            continue
        if status in EXCLUDED:
            out.assignments[row_id] = (None, None)
            out.spans[row_id] = (None, None)
            out.sources[row_id] = SOURCE_EXCLUDED
            continue
        weight, source = weight_of(row, floor)
        out.weights[row_id], out.sources[row_id] = weight, source
        out.committed[row_id] = committed.get(row_id, 0)
        out.occupancy[row_id] = {
            int(i["sprint"]) for i in mine if plan_row_of(i, uids) == row_id and i.get("sprint") is not None
        }
        remaining = max(0, weight - out.committed[row_id])
        if remaining == 0 and held.get(row_id) in by_number:  # fully committed: it finishes where its last item is
            sprint = by_number[held[row_id]]
            out.assignments[row_id] = (int(sprint["number"]), sprint.get("end") or None)
            out.spans[row_id] = (sprint.get("start") or None, sprint.get("end") or None)
            continue
        first_free = next((i for i, f in enumerate(free) if f > 0), len(line))
        pointer = max(first_free, index_of.get(pinned.get(row_id, -1), 0))
        finished: int | None = None
        while remaining > 0 and pointer < len(line):
            take = min(free[pointer], remaining)
            free[pointer] -= take
            remaining -= take
            if take:
                out.occupancy[row_id].add(int(line[pointer]["number"]))
            if remaining == 0:
                finished = pointer
            else:
                pointer += 1
        if finished is None:
            title = one_line(row.get("deliverable") or "", 60)
            reach = f"the sprint chain ends at Sprint {line[-1]['number']}" if line else "no Active or Planned sprint"
            out.warnings.append(f'row {row_id} "{title}" needs {remaining} more point(s): {reach}; run sprint plan')
            out.assignments[row_id] = (None, None)
            out.spans[row_id] = (None, None)
            continue
        sprint = line[finished]
        out.assignments[row_id] = (int(sprint["number"]), sprint.get("end") or None)
        out.spans[row_id] = (sprint.get("start") or None, sprint.get("end") or None)
    return out
