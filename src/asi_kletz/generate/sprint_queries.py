"""Read-side helpers over the sprints, their items and the weeks, shared by the board, the tracker text,
the dashboard and the diagrams, so a number on the screen is the number in the file. Nothing here writes."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..schema.definitions import SPRINT_CAPACITY

if TYPE_CHECKING:
    from ..brain import Brain

SPRINT, ITEM, WEEK, HOLIDAY = "sprint", "sprint_item", "week", "holiday"
VELOCITY_WINDOW = 3  # closed sprints averaged


def parse_date(value: Any, name: str = "date") -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise CommandError(f"{name}: {value!r} is not a date (use YYYY-MM-DD)")


def as_of_date(value: Any) -> dt.date:
    return parse_date(value, "as-of") if value not in (None, "") else dt.date.today()


def week_start(day: dt.date) -> dt.date:
    """The Monday on or before ``day``: the tracker's weeks run Monday to Sunday (``WEEK OF 10/26 - 11/01``)."""
    return day - dt.timedelta(days=day.weekday())


# -- rows -----------------------------------------------------------------------------
def sprints(brain: Brain) -> list[dict[str, Any]]:
    return brain.service(SPRINT).list(order_by=("number", "id"))


def sprint_by_number(brain: Brain, number: int | None) -> dict[str, Any]:
    """The sprint ``number``, or with ``None`` the active one; ``CommandError`` when there is none."""
    if number is None:
        active = active_sprint(brain)
        if active is None:
            raise CommandError("no active sprint; run `sprint start`")
        return active
    rows = brain.service(SPRINT).list(filters={"number": int(number)})
    if not rows:
        raise CommandError(f"no sprint number {number}")
    return rows[0]


def active_sprint(brain: Brain) -> dict[str, Any] | None:
    rows = brain.service(SPRINT).list(filters={"status": "Active"}, order_by=("number", "id"))
    return rows[0] if rows else None


def items(brain: Brain, number: int) -> list[dict[str, Any]]:
    return brain.service(ITEM).list(filters={"sprint": int(number)}, order_by=("order", "id"))


def weeks(brain: Brain, number: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """``{start: [section rows in print order]}`` for one sprint or for all."""
    rows = brain.service(WEEK).list(filters={"sprint": int(number)} if number is not None else None)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in sorted(rows, key=lambda r: (r.get("start") or "", r.get("order") or 0, r["id"])):
        grouped.setdefault(row["start"], []).append(row)
    return grouped


def holiday_dates(brain: Brain) -> dict[dt.date, str]:
    """``{date: name}`` of every holiday in the table, whatever its status: the calendar the planner skips.

    Two holidays on one date (an observed federal day landing on a company day) are one day off with both
    names, joined by `` / ``.
    """
    out: dict[dt.date, str] = {}
    for row in brain.service(HOLIDAY).list():
        if not row.get("date"):
            continue
        day, name = parse_date(row["date"]), row.get("name") or ""
        out[day] = f"{out[day]} / {name}" if day in out and name else out.get(day) or name
    return out


def capacity_of(sprint: dict[str, Any]) -> int:
    """The rule: 8 for any sprint that is not Closed, whatever the row says; a Closed sprint's stored value."""
    if sprint.get("status") == "Closed":
        return int(sprint.get("capacity") or SPRINT_CAPACITY)
    return SPRINT_CAPACITY


# -- points ----------------------------------------------------------------------------------
def committed(rows: list[dict[str, Any]]) -> int:
    return sum(int(r["points"]) for r in rows if r.get("points") and r.get("status") != "Carried")


def done(rows: list[dict[str, Any]]) -> int:
    return sum(int(r["points"]) for r in rows if r.get("points") and r.get("status") == "Done")


def unpointed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if not r.get("points") and r.get("status") != "Carried"]


def days_left(sprint: dict[str, Any], as_of: dt.date) -> int | None:
    if not sprint.get("end"):
        return None
    return max(0, (parse_date(sprint["end"]) - as_of).days)


def velocity(brain: Brain) -> float | None:
    """Mean points done over the last three closed sprints; ``None`` until one is closed."""
    closed = [s for s in sprints(brain) if s.get("status") == "Closed"][-VELOCITY_WINDOW:]
    if not closed:
        return None
    return round(sum(done(items(brain, s["number"])) for s in closed) / len(closed), 1)


def board(brain: Brain, sprint: dict[str, Any], as_of: dt.date | None = None) -> dict[str, Any]:
    """Everything the Sprint Board, the sprint line and the dashboard tile show, with the capacity warnings."""
    as_of = as_of or dt.date.today()
    rows = items(brain, sprint["number"])
    capacity = capacity_of(sprint)
    committed_points, done_points = committed(rows), done(rows)
    missing = unpointed(rows)
    left = days_left(sprint, as_of)
    overdue = bool(sprint.get("end")) and sprint.get("status") == "Active" and as_of > parse_date(sprint["end"])
    warnings: list[str] = []
    if committed_points > capacity:
        warnings.append(f"sprint {sprint['number']} committed {committed_points} of {capacity} points")
    if missing:
        warnings.append(f"sprint {sprint['number']}: {len(missing)} item(s) unpointed")
    return {
        "sprint": sprint, "items": rows, "capacity": capacity, "committed": committed_points,
        "done": done_points, "to_go": max(0, committed_points - done_points), "unpointed": len(missing),
        "unpointed_done": sum(1 for r in missing if r.get("status") == "Done"),
        "days_left": left, "overdue": overdue, "velocity": velocity(brain), "as_of": as_of.isoformat(),
        "warnings": warnings,
    }


def summary_line(board_data: dict[str, Any]) -> str | None:
    """The generated sprint line of the tracker text; ``None`` while nothing is pointed."""
    if not any(r.get("points") for r in board_data["items"]):
        return None
    sprint = board_data["sprint"]
    pace = (
        f"{board_data['days_left']} days left" if not board_data["overdue"]
        else f"{(dt.date.fromisoformat(board_data['as_of']) - parse_date(sprint['end'])).days} days overdue"
    )
    speed = "no closed sprint" if board_data["velocity"] is None else f"{board_data['velocity']:g} points per sprint"
    return (
        f"Sprint: {board_data['committed']} of {board_data['capacity']} points committed, {board_data['done']} done, "
        f"{board_data['to_go']} to go, {board_data['unpointed']} unpointed, {pace}; velocity {speed}."
    )
