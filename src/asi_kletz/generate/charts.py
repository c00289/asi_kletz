"""Charts: the sprint burndown, the velocity and the plan roadmap, drawn with matplotlib.

asi_escher draws node-and-edge diagrams (activity, flowchart, state, bdd, ibd, req) and nothing else;
a burndown line, a velocity bar chart and a deliverables-by-sprints grid are charts. They sit in the
diagram catalog like any diagram (the ``diagram`` verb draws them, the Generate screen lists them, a
document embeds them as figures) and are rendered by ``Chart.render`` with matplotlib, the plotting
library asi_escher brings, into PNG and SVG. Each builder returns a ``Chart`` whose ``data`` is the
plain numbers the picture is drawn from, so a test reads the numbers and never the pixels.

The sprint rule (owner, 2026-10-28): a sprint spans 10 business days (weekends and holidays excluded,
so holidays stretch dates); capacity is 8 points, company policy, a fixed global; sprints are
consecutive, numbered across the programme; 1 point = one productive day. Nothing here computes a
schedule of its own: the roadmap reads ``plan_schedule.schedule``, the single source.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..tracker.business_days import holidays_within, is_business_day
from . import plan_queries as pq
from . import sprint_queries as q
from .base import BuildContext, Param, Spec, register_diagram
from .plan_schedule import DONE, EXCLUDED, chain, schedule

if TYPE_CHECKING:
    from ..brain import Brain

CHART_FORMATS = ("png", "svg")  # what matplotlib writes here; dot and mmd are a graph's formats
DEFAULT_SIZE = (10.0, 5.0)
GAP_COLOUR = "#d9d9d9"
IDEAL_COLOUR = "#9e9e9e"
ACTUAL_COLOUR = "#1f77b4"
MARK_COLOUR = "#a6c8e8"
FINISH_COLOUR = "#1f4e79"
DONE_COLOUR = "#bdbdbd"
SPRINT_PARAM = Param("sprint", "Sprint number (default: the active sprint)")


@dataclass
class Chart:
    """A picture drawn from plain numbers: ``draw(ax)`` paints it on a matplotlib Axes; ``data`` is what it
    shows, for the tests and for the document that embeds it."""

    title: str
    data: dict[str, Any]
    draw: Callable[[Any], None]
    size: tuple[float, float] = DEFAULT_SIZE
    kind: str = field(default="chart", init=False)

    def render(
        self, out_dir: str | Path, stem: str, formats: tuple[str, ...] = CHART_FORMATS, dpi: int = 160
    ) -> dict[str, Any]:
        """Write ``<out_dir>/<stem>.<fmt>`` for every chart format asked for; the summary has the shape of
        asi_escher's (one path per format, ``size`` in pixels, ``nodes`` and ``edges`` 0, no ``issues``)."""
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure

        figure = Figure(figsize=self.size, dpi=dpi)
        FigureCanvasAgg(figure)
        ax = figure.add_subplot(111)
        self.draw(ax)
        ax.set_title(self.title)
        figure.tight_layout()
        target = Path(out_dir)
        target.mkdir(parents=True, exist_ok=True)
        summary: dict[str, Any] = {}
        for fmt in formats:
            if fmt in CHART_FORMATS:
                path = target / f"{stem}.{fmt}"
                figure.savefig(path, format=fmt, dpi=dpi)
                summary[fmt] = str(path)
        width, height = figure.get_size_inches()
        summary.update({"size": [int(width * dpi), int(height * dpi)], "nodes": 0, "edges": 0, "issues": []})
        return summary


def sprint_for(brain: Brain, params: dict[str, str]) -> dict[str, Any]:
    """The sprint a ``sprint`` param names, else the active one; ``CommandError`` when there is neither."""
    value = params.get("sprint")
    if value:
        try:
            number = int(value)
        except ValueError:
            raise CommandError(f"sprint must be a number, not {value!r}") from None
        return q.sprint_by_number(brain, number)
    return q.sprint_by_number(brain, None)


# -- burndown ---------------------------------------------------------------------------------------------
def burndown_data(brain: Brain, sprint: dict[str, Any]) -> dict[str, Any]:
    """Points remaining per business day of the sprint, the ideal line and the gaps (weekends, holidays).

    The committed points are the sprint's items that are not Carried; a Done item burns its points on its
    ``done_on`` (clamped to the sprint; an item Done without a date burns on the first day and is counted
    in ``undated_done``). The ideal line falls from the capacity to 0 over the business days.
    """
    if not sprint.get("start") or not sprint.get("end"):
        raise CommandError(f"sprint {sprint['number']} has no dates; the burndown needs its start and end")
    start, end = q.parse_date(sprint["start"]), q.parse_date(sprint["end"])
    holidays = q.holiday_dates(brain)
    items = [i for i in q.items(brain, sprint["number"]) if i.get("status") != "Carried"]
    committed = q.committed(items)
    capacity = q.capacity_of(sprint)
    burned: dict[dt.date, int] = {}
    undated = 0
    for item in items:
        if item.get("status") != "Done" or not item.get("points"):
            continue
        if item.get("done_on"):
            day = min(max(q.parse_date(item["done_on"]), start), end)
        else:
            day, undated = start, undated + 1
        burned[day] = burned.get(day, 0) + int(item["points"])
    days: list[dt.date] = []
    day = start
    while day <= end:
        days.append(day)
        day += dt.timedelta(days=1)
    business = [d for d in days if is_business_day(d, holidays)]
    remaining: list[int] = []
    for d in business:
        remaining.append(committed - sum(p for when, p in burned.items() if when <= d))
    steps = max(1, len(business) - 1)
    ideal = [round(capacity * (1 - k / steps), 2) for k in range(len(business))] if business else []
    gaps = [d for d in days if d not in business]
    return {
        "sprint": sprint["number"], "label": sprint.get("label") or f"SPRINT {sprint['number']}",
        "start": start.isoformat(), "end": end.isoformat(), "capacity": capacity, "committed": committed,
        "business_days": [d.isoformat() for d in business], "remaining": remaining, "ideal": ideal,
        "gaps": [d.isoformat() for d in gaps],
        "holidays": [(d.isoformat(), holidays[d]) for d in holidays_within(start, end, holidays)],
        "undated_done": undated, "items": len(items),
    }


@register_diagram(Spec(
    "sprint_burndown", "Sprint burndown",
    "Points remaining per business day of one sprint (a Done item burns its points on its done_on), the "
    "ideal line from the capacity to zero over the ten business days, weekends and holidays shown as gaps. "
    "A chart (PNG, SVG), drawn with matplotlib.",
    params=(SPRINT_PARAM,),
))
def sprint_burndown(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Chart:
    sprint = sprint_for(brain, params)
    params["sprint"] = str(sprint["number"])  # the output stem names the sprint drawn, default or not
    data = burndown_data(brain, sprint)
    if data["undated_done"]:
        ctx.warn(f"sprint {sprint['number']}: {data['undated_done']} Done item(s) without done_on burn on day one")
    if not data["items"]:
        ctx.warn(f"sprint {sprint['number']} has no items; the burndown is the ideal line alone")

    def draw(ax: Any) -> None:
        import matplotlib.dates as mdates

        days = [dt.date.fromisoformat(d) for d in data["business_days"]]
        for gap in data["gaps"]:
            d = dt.date.fromisoformat(gap)
            ax.axvspan(d - dt.timedelta(hours=12), d + dt.timedelta(hours=12), color=GAP_COLOUR, alpha=0.5, lw=0)
        for iso, name in data["holidays"]:
            ax.annotate(name, (dt.date.fromisoformat(iso), data["capacity"]), rotation=90, fontsize=7,
                        ha="center", va="top", color="#555555")
        if days:
            ax.plot(days, data["ideal"], linestyle="--", color=IDEAL_COLOUR, label="ideal")
            ax.plot(days, data["remaining"], marker="o", color=ACTUAL_COLOUR, label="remaining")
        ax.set_ylim(bottom=0, top=max(data["capacity"], data["committed"], 1) * 1.15)
        ax.set_ylabel("points")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        ax.grid(True, axis="y", alpha=0.3)
        ax.legend(loc="upper right")

    title = (
        f"Burndown: {data['label']} ({data['start']} to {data['end']}, "
        f"{data['committed']} of {data['capacity']} points)"
    )
    return Chart(title, data, draw)


# -- velocity ---------------------------------------------------------------------------------------------
def velocity_data(brain: Brain) -> dict[str, Any]:
    """Points done per Closed sprint, by number, and the three-sprint mean at each."""
    closed = [s for s in q.sprints(brain) if s.get("status") == "Closed"]
    done = [q.done(q.items(brain, s["number"])) for s in closed]
    mean = []
    for index in range(len(done)):
        window = done[max(0, index - q.VELOCITY_WINDOW + 1): index + 1]
        mean.append(round(sum(window) / len(window), 1))
    return {
        "sprints": [s["number"] for s in closed], "labels": [s.get("label") or f"SPRINT {s['number']}" for s in closed],
        "done": done, "mean": mean, "capacity": [q.capacity_of(s) for s in closed], "window": q.VELOCITY_WINDOW,
    }


@register_diagram(Spec(
    "velocity", "Velocity",
    "One bar per Closed sprint (points done) and the three-sprint mean as a line: the velocity the board and "
    "the sprint line print. A chart (PNG, SVG), drawn with matplotlib.",
))
def velocity(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Chart:
    data = velocity_data(brain)
    if not data["sprints"]:
        ctx.warn("no Closed sprint; the velocity chart is empty")

    def draw(ax: Any) -> None:
        positions = list(range(len(data["sprints"])))
        if positions:
            ax.bar(positions, data["done"], color=MARK_COLOUR, edgecolor=FINISH_COLOUR, label="points done")
            ax.plot(positions, data["mean"], marker="o", color=ACTUAL_COLOUR, label=f"{data['window']}-sprint mean")
            ax.set_xticks(positions, [f"S{n}" for n in data["sprints"]])
            ax.legend(loc="upper left")
        else:
            ax.text(0.5, 0.5, "no Closed sprint yet", ha="center", va="center", transform=ax.transAxes)
            ax.set_xticks([])
        ax.set_ylabel("points")
        ax.set_ylim(bottom=0)
        ax.grid(True, axis="y", alpha=0.3)

    return Chart("Velocity: points done per Closed sprint", data, draw, size=(8.0, 4.5))


# -- roadmap ---------------------------------------------------------------------------------------------
def roadmap_data(brain: Brain) -> dict[str, Any]:
    """The plan against the sprint chain, from the scheduler and the rows and nothing else.

    ``rows``: every deliverable in plan order with its phase, status, weight, source, committed points, the
    sprints it occupies and the one it finishes in; ``columns``: the sprints from the active one (else the
    first Planned) to the last one any deliverable finishes in, each with its dates and holidays;
    ``total_points``, ``completion`` (the last finishing sprint and its end), ``unscheduled`` and the
    scheduler's ``warnings``.
    """
    rows = pq.all_rows(brain)
    sprints = q.sprints(brain)
    items = brain.service(q.ITEM).list()
    result = schedule(rows, sprints, items, brain.default_points)
    line = chain(sprints)
    finishing = [n for n, _ in result.assignments.values() if n is not None]
    last = max(finishing) if finishing else (int(line[0]["number"]) if line else None)
    columns = [s for s in line if last is not None and int(s["number"]) <= last]
    holidays = q.holiday_dates(brain)
    out_rows: list[dict[str, Any]] = []
    total = 0
    for row in rows:
        row_id = int(row["id"])
        number, deadline = result.assignments.get(row_id, (row.get("sprint"), row.get("deadline")))
        span = result.spans.get(row_id, (row.get("sprint_start"), row.get("sprint_end")))
        weight = result.weights.get(row_id, 0)
        if row.get("status") not in (DONE, *EXCLUDED):
            total += weight
        out_rows.append({
            "id": row_id, "order": row.get("order"), "deliverable": pq.one_line(row.get("deliverable") or "", 70),
            "phase": row.get("lifecycle_phase") or "", "status": row.get("status") or "",
            "weight": weight, "source": result.sources.get(row_id, ""),
            "committed": result.committed.get(row_id, 0), "sprint": number, "deadline": deadline,
            "start": span[0], "end": span[1], "occupied": sorted(result.occupancy.get(row_id, ())),
        })
    completion = None
    if last is not None and columns:
        final = next((s for s in columns if int(s["number"]) == last), columns[-1])
        completion = {"sprint": last, "date": final.get("end")}
    return {
        "rows": out_rows,
        "columns": [{
            "number": int(s["number"]), "label": s.get("label") or f"SPRINT {s['number']}",
            "start": s.get("start"), "end": s.get("end"), "status": s.get("status"),
            "holidays": [
                holidays[d] for d in holidays_within(q.parse_date(s["start"]), q.parse_date(s["end"]), holidays)
            ] if s.get("start") and s.get("end") else [],
        } for s in columns],
        "total_points": total, "completion": completion,
        "unscheduled": [r["id"] for r in out_rows if r["sprint"] is None and r["status"] not in (DONE, *EXCLUDED)],
        "warnings": list(result.warnings),
    }


@register_diagram(Spec(
    "plan_roadmap", "Safety Plan roadmap",
    "The deliverables as rows in plan order against the sprint chain as columns, from the active sprint to "
    "the last one any deliverable finishes in: one mark per sprint a deliverable occupies, the finishing "
    "sprint emphasised, holidays marked on the sprint axis. Drawn from the scheduler's output, the single "
    "source of the plan's sprint and deadline. A chart (PNG, SVG), drawn with matplotlib.",
))
def plan_roadmap(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Chart:
    data = roadmap_data(brain)
    for warning in data["warnings"]:
        ctx.warn(warning)
    if not data["columns"]:
        ctx.warn("no Active or Planned sprint; the roadmap has no columns")
    rows, columns = data["rows"], data["columns"]
    height = max(3.0, 0.24 * len(rows) + 1.6)
    width = max(8.0, 0.42 * len(columns) + 5.5)

    def draw(ax: Any) -> None:
        from matplotlib.patches import Rectangle

        index_of = {c["number"]: i for i, c in enumerate(columns)}
        for y, row in enumerate(rows):
            label = f"{row['order'] or ''} {row['deliverable']}".strip()
            done = row["status"] == DONE
            for number in row["occupied"]:
                x = index_of.get(number)
                if x is None:
                    continue
                finishing = number == row["sprint"]
                ax.add_patch(Rectangle(
                    (x - 0.4, y - 0.4), 0.8, 0.8,
                    facecolor=FINISH_COLOUR if finishing else MARK_COLOUR,
                    edgecolor=FINISH_COLOUR, linewidth=1.2 if finishing else 0.5,
                ))
            ax.text(-0.7, y, label, ha="right", va="center", fontsize=6.5, color=DONE_COLOUR if done else "black")
        ax.set_xlim(-0.6, max(len(columns), 1) - 0.4)
        ax.set_ylim(len(rows) - 0.4, -0.6)
        ax.set_xticks(range(len(columns)))
        ax.set_xticklabels([f"S{c['number']}\n{(c['start'] or '')[5:]}" + ("\n*" if c["holidays"] else "")
                            for c in columns], fontsize=6.5)
        ax.set_yticks([])
        ax.tick_params(axis="x", top=True, labeltop=True, bottom=False, labelbottom=False)
        ax.grid(True, axis="x", alpha=0.2)
        for spine in ("left", "right", "bottom"):
            ax.spines[spine].set_visible(False)
        if any(c["holidays"] for c in columns):
            ax.text(0.0, -0.02, "* a sprint that contains a holiday (its dates stretched)", transform=ax.transAxes,
                    fontsize=6.5, va="top", color="#555555")

    title = "Safety Plan roadmap"
    if data["completion"]:
        done = data["completion"]
        title += f": {data['total_points']} points, done in Sprint {done['sprint']} ({done['date']})"
    return Chart(title, data, draw, size=(width, height))
