"""The built-in documents: the Safety Plan, a status report and a phase checklist, through asi_gutenberg.

Each builder is ``(brain, params, ctx) -> asi_gutenberg.Document``. Diagrams go in as
``diagram`` blocks through ``figures.add_diagram``; asi_gutenberg renders them into
``<out>/figures/`` when the triplet is built and numbers them as figures.
Metadata: ``date`` is today, ``author`` is the actor who asked, ``status`` is Draft; the
Safety Plan's ``doc_id``, ``project`` and revision history come from ``kletz.toml``.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from ..schema.definitions import SPRINT_RULE
from ..tracker.business_days import holidays_within
from . import plan_queries as q
from . import sprint_queries as sq
from .base import BuildContext, Spec, register_document
from .charts import SPRINT_PARAM, roadmap_data, sprint_for
from .figures import add_diagram

if TYPE_CHECKING:
    from ..brain import Brain

NO_DOC_ID = "kletz.toml has no doc_id"
NO_REVISIONS = "kletz.toml has no revisions"
DUE_DAYS = 30
RECENT_CHANGES = 20
STATUS_MEANINGS = {
    "Pending": "Planned; work has not started.",
    "Ongoing": "Work has started and is progressing.",
    "Blocked": "Work cannot progress until an impediment is removed.",
    "Alternative": "Covered by another deliverable or an equivalent activity; see the work product reference.",
    "Out-of-Scope": "Not applicable to this programme; the reason is recorded with the deliverable.",
    "Done": "Produced, verified and reviewed as planned.",
}


def _today() -> str:
    return dt.date.today().isoformat()


def _phase_heading(phase: str) -> str:
    number, title = q.phase_number(phase), q.phase_title(phase)
    return f"Phase {number}: {title}" if number != phase and title else phase


def _common(brain: Brain, ctx: BuildContext) -> dict[str, Any]:
    return {"date": _today(), "author": ctx.actor, "status": "Draft", "project": brain.project}


def _reference(brain: Brain) -> str:
    return brain.doc_id or "the platform Safety Plan"


def _cell(value: Any) -> str:
    return q.one_line(value)


# -- Safety Plan ---------------------------------------------------------------
@register_document(Spec(
    "safety_plan", "Platform Safety Plan",
    "The controlled Safety Plan document: purpose, scope, the lifecycle overview with its diagram, "
    "one section per lifecycle phase with a Deliverables table, an Ownership table and the phase "
    "flow diagram, and appendices for roles, QMS references and the status legend. The document id "
    "and revision history come from kletz.toml; the reviewed artefact is the PDF.",
))
def safety_plan(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_gutenberg import Document

    revisions = list(brain.revisions)
    doc = Document(
        "Platform Safety Plan", "plan", doc_id=brain.doc_id,
        revision=(revisions[-1].get("rev") or "0.1") if revisions else "0.1", **_common(brain, ctx),
    )
    if not brain.doc_id:
        ctx.warn(NO_DOC_ID)
    if revisions:
        for rev in revisions:
            doc.revision(rev.get("rev", ""), rev.get("date", ""), rev.get("author", ""), rev.get("description", ""))
    else:
        doc.revision("0.1", _today(), ctx.actor, "Generated draft")
        ctx.warn(NO_REVISIONS)

    schema = brain.registry.get(q.PLAN_ENTITY)
    rows = q.all_rows(brain)
    by_phase = q.rows_by_phase(brain, rows)
    statuses = q.statuses(brain)
    counts = q.counts_by_status(brain, rows)

    doc.h1("Purpose")
    doc.p(
        "This document is the platform Safety Plan"
        + (f" for {brain.project}" if brain.project else "")
        + ": one entry per safety deliverable with its lifecycle phase, where the work product lives, "
        "which QMS documents it references, who authors, verifies and reviews it, its deadline and its "
        f"status. It is generated from the ASI Kletz database, which is the single source of truth; "
        f"this issue reflects the database on {_today()}."
    )
    doc.h1("Scope")
    doc.p(
        f"The plan covers {counts['total']} deliverables across the safety lifecycle phases below, mapped "
        "onto the product development process (PDP) phases."
    )
    doc.fields(
        [(f"Phase {q.phase_number(p)}", q.phase_title(p) or p) for p in q.phases(brain, rows)],
        caption="Safety lifecycle phases",
    )
    doc.fields(
        [(f"PDP phase {p}", f"{len(r)} deliverables") for p, r in q.rows_by_pdp_phase(brain, rows).items() if p],
        caption="PDP phases",
    )

    doc.h1("Lifecycle overview")
    add_diagram(doc, ctx, "lifecycle_overview", caption="Safety lifecycle overview")
    doc.table(
        ["Phase", "Count", *statuses],
        [[rec["lifecycle_phase"], rec["deliverables"], *(rec[s] for s in statuses)]
         for rec in q.counts_by_phase(brain, rows)],
        caption="Deliverables per lifecycle phase and status",
    )

    for phase, phase_rows in by_phase.items():
        doc.h1(_phase_heading(phase))
        if not phase_rows:
            doc.p("No deliverables are planned in this phase.")
            continue
        done = sum(1 for r in phase_rows if r.get("status") == "Done")
        doc.p(f"{len(phase_rows)} deliverables, {done} Done.")
        number = q.phase_number(phase)
        doc.table(
            ["Deliverable", "PDP", "Location", "Reference", "Deadline", "Status"],
            [[
                _cell(r.get("deliverable")), _cell(r.get("pdp_phase")),
                q.describe(r, "work_product_location", "location", schema),
                q.describe(r, "work_product_reference", "reference", schema),
                _cell(r.get("deadline")), _cell(r.get("status")),
            ] for r in phase_rows],
            caption=f"Deliverables of phase {number}",
        )
        doc.table(
            ["Deliverable", "Author", "Verification", "Reviewer"],
            [[
                _cell(r.get("deliverable")),
                q.describe(r, "author", "author", schema),
                q.describe(r, None, "verification", schema),
                q.describe(r, "gate_reviewer", "reviewer", schema),
            ] for r in phase_rows],
            caption=f"Ownership of phase {number}",
        )
        add_diagram(doc, ctx, "phase_flow", {"phase": phase}, caption=f"Phase flow: {phase}")

    doc.appendix("Roles")
    doc.h2("Author roles")
    doc.bullets([spec.header for spec in q.group_flags("author", schema)])
    doc.h2("Reviewer roles")
    doc.bullets([spec.header for spec in q.group_flags("reviewer", schema)])
    doc.h2("Verification levels")
    doc.bullets([spec.header for spec in q.group_flags("verification", schema)])

    doc.appendix("QMS and reference legend")
    doc.p("The QMS documents and references a deliverable can point at, with the number of deliverables that do.")
    doc.table(
        ["Reference", "Deliverables"],
        [[spec.header, sum(1 for r in rows if r.get(spec.name))] for spec in q.group_flags("reference", schema)],
        caption="Reference legend",
    )

    doc.appendix("Status legend")
    doc.table(
        ["Status", "Meaning"],
        [[status, STATUS_MEANINGS.get(status, "")] for status in statuses],
        caption="Status legend",
    )
    return doc


# -- status report -------------------------------------------------------------
@register_document(Spec(
    "status_report", "Safety Plan Status",
    "A status report of the plan: totals by status with the status board, blocked deliverables, "
    f"deliverables due within {DUE_DAYS} days (and open deliverables with no parsable date), the "
    f"lifecycle overview, and the last {RECENT_CHANGES} changes from the audit log.",
))
def status_report(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_gutenberg import Document

    doc = Document("Safety Plan Status", "report", **_common(brain, ctx))
    rows = q.all_rows(brain)
    counts = q.counts_by_status(brain, rows)
    today = dt.date.today()

    doc.h1("Purpose")
    doc.p(
        f"This report gives the status of {_reference(brain)} on {today.isoformat()}, generated from the "
        "ASI Kletz database. Numbers are counts of deliverables."
    )
    doc.h1("Totals by status")
    doc.fields([*((s, counts[s]) for s in q.statuses(brain)), ("Total", counts["total"])], caption="Totals by status")
    add_diagram(doc, ctx, "status_board", caption="Status board")

    doc.h1("Blocked deliverables")
    blocked = q.blocked(rows)
    if blocked:
        doc.table(
            ["Deliverable", "Phase", "Deadline", "Author"],
            [[_cell(r.get("deliverable")), _cell(r.get("lifecycle_phase")), _cell(r.get("deadline")),
              q.describe(r, "author", "author")] for r in blocked],
            caption="Blocked deliverables",
        )
    else:
        doc.p("No deliverable is blocked.")

    doc.h1(f"Due within {DUE_DAYS} days")
    due, undated = q.due_within(rows, DUE_DAYS, today)
    if due:
        doc.table(
            ["Deliverable", "Phase", "Deadline", "Status"],
            [[_cell(r.get("deliverable")), _cell(r.get("lifecycle_phase")), when.isoformat(), _cell(r.get("status"))]
             for r, when in due],
            caption=f"Open deliverables due by {(today + dt.timedelta(days=DUE_DAYS)).isoformat()}",
        )
    else:
        doc.p(f"No open deliverable has a dated deadline within {DUE_DAYS} days.")
    if undated:
        doc.h2("Open deliverables without a date")
        doc.p("These open deliverables have no deadline: the sprint chain does not reach them (run `sprint plan`).")
        doc.table(
            ["Deliverable", "Phase", "Deadline", "Status"],
            [[_cell(r.get("deliverable")), _cell(r.get("lifecycle_phase")), _cell(r.get("deadline")),
              _cell(r.get("status"))] for r in undated],
            caption="Open deliverables without a parsable deadline",
        )

    doc.h1("Lifecycle overview")
    add_diagram(doc, ctx, "lifecycle_overview", caption="Safety lifecycle overview")
    doc.table(
        ["Phase", "Deliverables", "Done", "Open"],
        [[rec["lifecycle_phase"], rec["deliverables"], rec["done"],
          len(q.open_rows(q.rows_by_phase(brain, rows)[rec["lifecycle_phase"]]))]
         for rec in q.counts_by_phase(brain, rows)],
        caption="Deliverables per lifecycle phase",
    )

    doc.h1("Recent changes")
    audit = brain.storage.audit_tail(RECENT_CHANGES)
    if audit:
        doc.table(
            ["When", "Actor", "Action", "Entity", "Id"],
            [[_cell(a.get("ts")), _cell(a.get("actor")), _cell(a.get("action")), _cell(a.get("entity")),
              _cell(a.get("entity_id"))] for a in audit],
            caption=f"Last {len(audit)} changes recorded in the audit log",
        )
    else:
        doc.p("The audit log is empty.")
    return doc


# -- phase checklist -------------------------------------------------------------
@register_document(Spec(
    "phase_checklist", "Safety Plan Checklist",
    "One task list per lifecycle phase, a deliverable ticked when its status is Done, with the "
    "PDP map and a closing table of totals.",
))
def phase_checklist(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_gutenberg import Document

    doc = Document("Safety Plan Checklist", "checklist", **_common(brain, ctx))
    rows = q.all_rows(brain)
    counts = q.counts_by_status(brain, rows)

    doc.h1("Purpose")
    doc.p(
        f"This checklist tracks the status of {_reference(brain)} on {_today()}: one line per deliverable, "
        "ticked when the deliverable is Done. It is generated from the ASI Kletz database."
    )
    add_diagram(doc, ctx, "pdp_map", caption="PDP map of the safety plan")

    for phase, phase_rows in q.rows_by_phase(brain, rows).items():
        doc.h1(_phase_heading(phase))
        if not phase_rows:
            doc.p("No deliverables are planned in this phase.")
            continue
        doc.tasks([
            (f"{_cell(r.get('deliverable'))} ({_cell(r.get('status')) or 'no status'})", r.get("status") == "Done")
            for r in phase_rows
        ])

    doc.h1("Totals")
    doc.fields([*((s, counts[s]) for s in q.statuses(brain)), ("Total", counts["total"])], caption="Totals by status")
    return doc


# -- sprint report (0.12.0) -------------------------------------------------------------------------------
ITEM_STATUS_ORDER = ("To Do", "In Progress", "Done", "Carried")


@register_document(Spec(
    "sprint_report", "Sprint Report",
    "One sprint for the people who want a PDF rather than the text file: the sprint's facts and goal, the "
    "board table (To Do, In Progress, Done, Carried, with points), the burndown and velocity charts, the "
    "carried items and the holidays inside the sprint. The sprint rule: ten business days, eight points.",
    params=(SPRINT_PARAM,),
))
def sprint_report(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_gutenberg import Document

    sprint = sprint_for(brain, params)
    number = int(sprint["number"])
    params["sprint"] = str(number)
    label = sprint.get("label") or f"SPRINT {number}"
    board = sq.board(brain, sprint)
    doc = Document(f"Sprint Report: {label}", "report", **_common(brain, ctx))

    doc.h1("The sprint")
    velocity = "no closed sprint" if board["velocity"] is None else f"{board['velocity']:g} points per sprint"
    doc.fields([
        ("Sprint", f"{number} · {label}"), ("Lifecycle phase", _cell(sprint.get("lifecycle_phase")) or "none yet"),
        ("Dates", f"{sprint.get('start') or '?'} to {sprint.get('end') or '?'}"),
        ("Status", _cell(sprint.get("status"))), ("Capacity", f"{board['capacity']} points"),
        ("Committed", f"{board['committed']} points"), ("Done", f"{board['done']} points"),
        ("To go", f"{board['to_go']} points"), ("Unpointed items", str(board["unpointed"])),
        ("Days left", "overdue" if board["overdue"] else str(board["days_left"])), ("Velocity", velocity),
    ], caption="The sprint on " + board["as_of"])
    doc.h1("Goal")
    doc.p(_cell(sprint.get("goal")) or "No goal recorded.")

    doc.h1("Board")
    items = board["items"]
    ordered = sorted(items, key=lambda i: (
        ITEM_STATUS_ORDER.index(i.get("status")) if i.get("status") in ITEM_STATUS_ORDER else len(ITEM_STATUS_ORDER),
        i.get("order") or 0, i["id"],
    ))
    if ordered:
        doc.table(
            ["Status", "Item", "Kind", "Points", "Plan row", "Target"],
            [[_cell(i.get("status")), _cell(i.get("title")), _cell(i.get("kind")),
              "" if i.get("points") is None else str(i["points"]), _cell(i.get("plan_row")), _cell(i.get("target"))]
             for i in ordered],
            caption=f"The board of {label}",
        )
    else:
        doc.p("The sprint has no items.")
    summary = sq.summary_line(board)
    if summary:
        doc.p(summary)
    for warning in board["warnings"]:
        doc.p(f"Warning: {warning}.")

    doc.h1("Burndown")
    add_diagram(doc, ctx, "sprint_burndown", {"sprint": str(number)}, caption=f"Burndown of {label}")
    doc.h1("Velocity")
    add_diagram(doc, ctx, "velocity", caption="Points done per Closed sprint")

    doc.h1("Carried items")
    carried_out = [i for i in items if i.get("status") == "Carried"]
    carried_in = [i for i in items if i.get("carried_from")]
    if carried_out:
        doc.table(
            ["Item", "Points", "Kind"],
            [[_cell(i.get("title")), "" if i.get("points") is None else str(i["points"]), _cell(i.get("kind"))]
             for i in carried_out],
            caption=f"Carried out of {label} into the next sprint",
        )
    else:
        doc.p("No item was carried out of this sprint.")
    if carried_in:
        doc.table(
            ["Item", "Points", "Carried from"],
            [[_cell(i.get("title")), "" if i.get("points") is None else str(i["points"]), f"Sprint {i['carried_from']}"]
             for i in carried_in],
            caption=f"Carried into {label}",
        )

    doc.h1("Holidays in the sprint")
    holidays = sq.holiday_dates(brain)
    inside = (
        holidays_within(sq.parse_date(sprint["start"]), sq.parse_date(sprint["end"]), holidays)
        if sprint.get("start") and sprint.get("end") else []
    )
    if inside:
        doc.table(["Date", "Holiday"], [[d.isoformat(), holidays[d]] for d in inside], caption="Holidays, no work")
        doc.p("A sprint spans 10 business days; each holiday inside it stretched the dates by one calendar day.")
    else:
        doc.p("No holiday falls in this sprint.")
    return doc


# -- the roadmap (0.12.0) ------------------------------------------------------------------------------------
@register_document(Spec(
    "plan_roadmap", "Safety Plan Roadmap",
    "For the tech lead and the team: the sprint rule, the total points and the completion sprint and date, "
    "one table per lifecycle phase (deliverable, points, sprint, start, end, status), the roadmap chart, "
    "the rows the sprint chain does not reach, and a holidays appendix. Built from the scheduler's output, "
    "the single source of the plan's sprint and deadline.",
))
def plan_roadmap(brain: Brain, params: dict[str, str], ctx: BuildContext) -> Any:
    from asi_gutenberg import Document

    data = roadmap_data(brain)
    rows = data["rows"]
    doc = Document("Safety Plan Roadmap", "plan", **_common(brain, ctx))

    doc.h1("Purpose")
    doc.p(
        f"This roadmap says in which sprint each safety deliverable of {_reference(brain)} is expected to be "
        f"finished, and so by which date, generated from the ASI Kletz database on {_today()}. Every sprint and "
        "date below is the scheduler's: the plan's points poured into the sprint chain, eight points a sprint, "
        "committed items first."
    )
    doc.h1("The sprint rule")
    doc.p(SPRINT_RULE)

    doc.h1("Totals")
    scheduled = [r for r in rows if r["sprint"] is not None and r["status"] != "Done"]
    done = [r for r in rows if r["status"] == "Done"]
    completion = data["completion"]
    doc.fields([
        ("Deliverables", str(len(rows))), ("Done", str(len(done))), ("Scheduled", str(len(scheduled))),
        ("Beyond the chain", str(len(data["unscheduled"]))), ("Points to schedule", str(data["total_points"])),
        ("Completion", f"Sprint {completion['sprint']} ({completion['date']})" if completion
         else "not reached: no sprint chain to schedule into"),
    ], caption="The plan in points and sprints")
    if data["columns"]:
        first, last = data["columns"][0], data["columns"][-1]
        doc.p(
            f"The roadmap runs from Sprint {first['number']} ({first['start']}) to Sprint {last['number']} "
            f"({last['end']}), {len(data['columns'])} sprints."
        )

    doc.h1("Roadmap")
    add_diagram(doc, ctx, "plan_roadmap", caption="Deliverables against the sprint chain; the darker mark is the "
                                                  "sprint a deliverable finishes in")

    by_phase: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_phase.setdefault(row["phase"] or "(no lifecycle phase)", []).append(row)
    for phase in [*q.phases(brain), "(no lifecycle phase)"]:
        phase_rows = by_phase.get(phase)
        if not phase_rows:
            continue
        doc.h1(_phase_heading(phase))
        doc.table(
            ["Deliverable", "Points", "Sprint", "Start", "End", "Status"],
            [[r["deliverable"], str(r["weight"]) if r["status"] != "Done" else "",
              "" if r["sprint"] is None else str(r["sprint"]), _cell(r["start"]), _cell(r["end"]), r["status"]]
             for r in phase_rows],
            caption=f"Deliverables of {_phase_heading(phase)}",
        )

    if data["unscheduled"]:
        doc.h1("Not scheduled")
        doc.p("The sprint chain ends before these deliverables are finished; `sprint plan` extends it.")
        doc.table(
            ["Deliverable", "Points", "Status"],
            [[r["deliverable"], str(r["weight"]), r["status"]] for r in rows if r["id"] in data["unscheduled"]],
            caption="Deliverables the chain does not reach",
        )
        doc.bullets(data["warnings"])

    doc.appendix("Holidays")
    holidays = sq.holiday_dates(brain)
    span = [c for c in data["columns"] if c["start"] and c["end"]]
    inside = holidays_within(sq.parse_date(span[0]["start"]), sq.parse_date(span[-1]["end"]), holidays) if span else []
    if inside:
        by_sprint = {
            d: next((c["number"] for c in span
                     if sq.parse_date(c["start"]) <= d <= sq.parse_date(c["end"])), None)
            for d in inside
        }
        doc.table(
            ["Date", "Holiday", "Sprint"],
            [[d.isoformat(), holidays[d], "" if by_sprint[d] is None else str(by_sprint[d])] for d in inside],
            caption="Holidays within the roadmap: each stretches its sprint by one calendar day",
        )
    else:
        doc.p("No holiday falls within the roadmap.")
    return doc
