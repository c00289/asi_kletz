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
    sources: dict[int, str] = field(default_factory=dict)  # row id -> where its weight came from
    weights: dict[int, int] = field(default_factory=dict)  # row id -> the weight used
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


def pins(items: Iterable[dict[str, Any]], numbers: set[int]) -> dict[int, int]:
    """``{plan row id: sprint number}``: a deliverable with a sprint item (kind Deliverable) in sprint n of the
    chain never finishes before n; the highest such n wins."""
    out: dict[int, int] = {}
    for item in items:
        if item.get("kind") != "Deliverable" or not item.get("plan_row") or item.get("status") == "Carried":
            continue
        number = item.get("sprint")
        if number in numbers:
            row_id = int(item["plan_row"])
            out[row_id] = max(out.get(row_id, 0), int(number))
    return out


def schedule(
    rows: Iterable[dict[str, Any]], sprints: Iterable[dict[str, Any]], items: Iterable[dict[str, Any]], floor: int
) -> Schedule:
    """The plan scheduled: rows in plan order, each poured into successive sprints as capacity allows.

    A Done row keeps what it has (absent from ``assignments``); Blocked, Alternative and Out-of-Scope get
    ``(None, None)``; every other row gets the number of the sprint its last point lands in and that sprint's
    ``end``, or ``(None, None)`` and a warning when the chain runs out.
    """
    items = list(items)
    line = chain(sprints)
    free = [free_capacity(s, items) for s in line]
    numbers = {int(s["number"]) for s in line}
    index_of = {int(s["number"]): i for i, s in enumerate(line)}
    pinned = pins(items, numbers)
    out = Schedule()
    for row in rows:
        row_id = int(row["id"])
        status = row.get("status")
        if status == DONE:
            out.sources[row_id] = SOURCE_DONE
            continue
        if status in EXCLUDED:
            out.assignments[row_id] = (None, None)
            out.sources[row_id] = SOURCE_EXCLUDED
            continue
        weight, source = weight_of(row, floor)
        out.weights[row_id], out.sources[row_id] = weight, source
        remaining = weight
        first_free = next((i for i, f in enumerate(free) if f > 0), len(line))
        pointer = max(first_free, index_of.get(pinned.get(row_id, -1), 0))
        finished: int | None = None
        while remaining > 0 and pointer < len(line):
            take = min(free[pointer], remaining)
            free[pointer] -= take
            remaining -= take
            if remaining == 0:
                finished = pointer
            else:
                pointer += 1
        if finished is None:
            title = one_line(row.get("deliverable") or "", 60)
            reach = f"the sprint chain ends at Sprint {line[-1]['number']}" if line else "no Active or Planned sprint"
            out.warnings.append(f'row {row_id} "{title}" needs {remaining} more point(s): {reach}; run sprint plan')
            out.assignments[row_id] = (None, None)
            continue
        sprint = line[finished]
        out.assignments[row_id] = (int(sprint["number"]), sprint.get("end") or None)
    return out
