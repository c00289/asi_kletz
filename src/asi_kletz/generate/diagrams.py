"""The built-in diagrams: four views of the Safety Plan drawn with asi_escher, and since 0.24.0 the STPA trace.

Each builder is ``(brain, params, ctx) -> asi_escher.Diagram``. They read the plan only
through ``plan_queries`` and import asi_escher lazily, so the catalog can be listed without
loading matplotlib.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import plan_queries as q
from .base import BuildContext, Param, Spec, register_diagram
from .figures import slug

if TYPE_CHECKING:
    from ..brain import Brain

LANES = (("author", "Author"), ("verification", "Verification"), ("reviewer", "Reviewer"))
# the conventional status transitions; a convention of the tool, not data in the plan
STATUS_TRANSITIONS = (
    ("Pending", "Ongoing"), ("Ongoing", "Done"), ("Ongoing", "Blocked"), ("Blocked", "Ongoing"),
    ("Pending", "Alternative"), ("Pending", "Out-of-Scope"),
)
DELIVERABLE_LABEL_LIMIT = 72


@register_diagram(Spec(
    "lifecycle_overview", "Lifecycle overview",
    "The safety lifecycle phases in order, left to right, each with its deliverable count and how "
    "many are Done. A phase with a Blocked deliverable takes the decision tint; a phase whose "
    "deliverables are all Done takes the state tint.",
))
def lifecycle_overview(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_escher import THEME, Diagram

    d = Diagram("Safety lifecycle overview", "flowchart", "LR")
    previous: str | None = None
    for record in q.counts_by_phase(brain):
        phase = record["lifecycle_phase"]
        count, done = record["deliverables"], record["done"]
        tint: dict[str, str] = {}
        if record.get("Blocked"):
            tint = dict(zip(("fill", "stroke"), THEME["decision"], strict=True))
        elif count and done == count:
            tint = dict(zip(("fill", "stroke"), THEME["state"], strict=True))
        node_id = f"phase_{slug(phase)}"
        d.node(node_id, f"{phase}\n{count} deliverables, {done} done", "process", **tint)
        if previous:
            d.edge(previous, node_id)
        previous = node_id
    return d


@register_diagram(Spec(
    "phase_flow", "Phase flow",
    "The deliverables of one lifecycle phase as an activity diagram with Author, Verification and "
    "Reviewer lanes: each deliverable is an action in the Author lane (with its author and status), "
    "followed by a verification step when a verification flag is set and a review step when a gate "
    "reviewer or reviewer flag is set. A note names the work product location.",
    params=(Param("phase", "Lifecycle phase: the lookup value or its leading number (for example 3)",
                  required=True, lookup="lifecycle_phase"),),
))
def phase_flow(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_escher import Diagram

    phase = q.resolve_phase(brain, params["phase"])
    params["phase"] = q.phase_number(phase)  # normalised, so "3" and "3. FSC" share one output stem
    rows = q.rows_by_phase(brain).get(phase, [])
    schema = brain.registry.get(q.PLAN_ENTITY)
    d = Diagram(f"Phase flow {phase}", "activity")
    for lane_id, title in LANES:
        d.lane(lane_id, title)
    d.start(lane="author")
    previous = "start"
    if not rows:
        ctx.warn(f"phase {phase!r} has no deliverables; the diagram is start -> end")
    for index, row in enumerate(rows, start=1):
        author_parts = [q.one_line(row.get("author"))] if row.get("author") else []
        author_parts.extend(q.set_flags(row, "author", schema))
        status = q.one_line(row.get("status"))
        lines = [q.one_line(row.get("deliverable"), DELIVERABLE_LABEL_LIMIT)]
        if author_parts:
            lines.append(q.summarise(author_parts))
        if status:
            lines.append(f"[{status}]")
        action = f"a{index}"
        d.action(action, "\n".join(lines), lane="author", stereotype=status or None)
        d.edge(previous, action)
        previous = action
        if row.get("work_product_location"):
            note = f"n{index}"
            d.note(note, f"Location: {q.one_line(row['work_product_location'], 60)}", lane="author")
            d.edge(note, action, kind="dependency", style="dashed")
        verification = q.set_flags(row, "verification", schema)
        if verification:
            step = f"v{index}"
            d.action(step, "Verify: " + q.summarise(verification), lane="verification")
            d.edge(previous, step)
            previous = step
        reviewers = [q.one_line(row.get("gate_reviewer"))] if row.get("gate_reviewer") else []
        reviewers.extend(flag for flag in q.set_flags(row, "reviewer", schema) if flag not in reviewers)
        if reviewers:
            step = f"r{index}"
            d.action(step, "Review: " + q.summarise(reviewers), lane="reviewer")
            d.edge(previous, step)
            previous = step
    d.end(lane="author")
    d.edge(previous, "end")
    return d


@register_diagram(Spec(
    "status_board", "Status board",
    "One state per plan status, labelled with its deliverable count, joined by the conventional "
    "transitions Pending -> Ongoing -> Done, Ongoing <-> Blocked, Pending -> Alternative and "
    "Pending -> Out-of-Scope. The transitions are a convention of the tool, not data in the plan.",
))
def status_board(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_escher import Diagram

    counts = q.counts_by_status(brain)
    d = Diagram("Safety plan status board", "state")
    ids = {status: f"s_{slug(status)}" for status in q.statuses(brain)}
    for status, node_id in ids.items():
        d.state(node_id, f"{status}\n{counts.get(status, 0)}")
    d.start()
    first = next(iter(ids.values()), None)
    if "Pending" in ids:
        d.edge("start", ids["Pending"])
    elif first:
        d.edge("start", first)
    for source, target in STATUS_TRANSITIONS:
        if source in ids and target in ids:
            d.edge(ids[source], ids[target])
    return d


@register_diagram(Spec(
    "pdp_map", "PDP map",
    "A SysML block definition diagram: the Safety Plan composed of one block per PDP phase, each "
    "listing the lifecycle phases that have deliverables in it.",
))
def pdp_map(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_escher import Diagram

    rows = q.all_rows(brain)
    d = Diagram("PDP map of the safety plan", "bdd", frame="bdd [Package] Safety Plan")
    d.block("plan", "Safety Plan", values=[f"{len(rows)} deliverables"])
    for pdp, pdp_rows in q.rows_by_pdp_phase(brain, rows).items():
        if not pdp:
            continue
        phases = list(dict.fromkeys(r.get("lifecycle_phase") or "(no phase)" for r in pdp_rows))
        node_id = f"pdp_{slug(pdp)}"
        d.node(
            node_id, f"PDP phase {pdp}", "block", stereotype="block",
            compartments=[("lifecycle phases", phases or ["none planned"])],
        )
        d.edge("plan", node_id, kind="composition")
    return d


# -- stpa_trace (0.24.0, from the sister tool's 0.10.0) --------------------------------------------------------
TRACE_LABEL_CHARS = 48
RETIRED_TINT = "state"


def short(text: Any, limit: int = TRACE_LABEL_CHARS) -> str:
    line = q.one_line(text)
    return line if len(line) <= limit else line[: limit - 1].rstrip() + "…"


@register_diagram(Spec(
    "stpa_trace", "STPA trace",
    "Hazards, unsafe control actions, loss scenarios and constraints of one analysis as four columns with the "
    "edges the page states; a swimlane per controller of the linked control structure when the UCAs are linked "
    "to one, a retired UCA in the state tint, a duplicate as a dashed edge.",
    params=(Param("analysis", "The analysis: its id, uid or slug", required=True),),
))
def stpa_trace(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_escher import THEME, Diagram

    from ..schema.lists import list_of

    row = brain.stpa.resolve(params["analysis"])
    parts = brain.stpa.parts(row["slug"])
    hazards = {h["code"]: h for h in parts["hazards"]}
    ucas = {u["code"]: u for u in parts["ucas"]}
    constraints = {c["code"]: c for c in parts["constraints"]}
    linked = [u["cs_controller"] for u in parts["ucas"] if u.get("cs_controller")]
    structure = row.get("control_structure")
    lanes: dict[str, str] = {}  # lane id -> title, in order; empty: a plain layered graph, left to right
    if structure and linked:
        order = {c["key"]: (c.get("order") or 0, c.get("name") or c["key"])
                 for c in brain.service("cs_controller").list({"structure": structure})}
        lanes["lane_hazards"] = "Hazards"
        for key in sorted(dict.fromkeys(linked), key=lambda k: order.get(k, (10**6, k))):
            lanes[f"lane_{slug(key)}"] = order.get(key, (0, key))[1]
        if any(not u.get("cs_controller") for u in parts["ucas"]):
            lanes["lane_unlinked"] = "Not linked"
        lanes["lane_constraints"] = "Constraints"
    d = Diagram(f"STPA trace: {row['name']}", "flowchart", direction="TB" if lanes else "LR")
    for lane_id, title in lanes.items():
        d.lane(lane_id, title)

    def lane_of(uca: dict[str, Any] | None) -> str | None:
        if not lanes:
            return None
        if uca is None or not uca.get("cs_controller"):
            return "lane_unlinked"
        return f"lane_{slug(uca['cs_controller'])}"

    retired_fill, retired_stroke = THEME[RETIRED_TINT]
    for code, h in hazards.items():
        d.node(f"h_{slug(code)}", f"{code}\n{short(h.get('text'))}", "io", lane="lane_hazards" if lanes else None)
    for code, u in ucas.items():
        label = f"{code}\n{short(u.get('text'))}"
        if u.get("retired"):
            label += "\n«retired»"
        tint = (retired_fill, retired_stroke) if u.get("retired") else (None, None)
        d.node(f"u_{slug(code)}", label, "process", lane=lane_of(u), fill=tint[0], stroke=tint[1])
    for code, c in constraints.items():
        d.node(f"c_{slug(code)}", f"{code}\n{short(c.get('text')) or '(referenced only)'}", "document",
               lane="lane_constraints" if lanes else None)
    for s in parts["scenarios"]:
        uca = ucas.get(s.get("uca") or "")
        row_text = f"row {s['row']}" if s.get("row") is not None else f"order {s.get('order')}"
        head = s.get("counterpart") or s.get("uca") or row_text
        if s.get("row") is not None:
            head += f" ({row_text})"
        types = ", ".join(f"type {t}" for t in list_of(s.get("types")))
        label = "\n".join(x for x in (head, types, short(s.get("causal_factors"))) if x)
        node_id = f"s_{s['id']}"
        d.node(node_id, label, "action", lane=lane_of(uca))
        if uca is not None:
            d.edge(f"u_{slug(uca['code'])}", node_id)
        for c in list_of(s.get("constraints")):
            if c in constraints:
                d.edge(node_id, f"c_{slug(c)}")
    for code, u in ucas.items():
        for h in list_of(u.get("hazards")):
            if h in hazards:
                d.edge(f"h_{slug(h)}", f"u_{slug(code)}")
        if u.get("duplicate_of") in ucas:
            d.edge(f"u_{slug(code)}", f"u_{slug(u['duplicate_of'])}", "duplicate of", style="dashed")
    if not d.nodes:
        d.note("empty", "The analysis holds no objects yet", lane="lane_hazards" if lanes else None)
    return d
