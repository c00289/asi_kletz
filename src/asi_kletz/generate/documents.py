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

from . import plan_queries as q
from .base import BuildContext, Spec, register_document
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
        doc.p("The deadline column is free text; these open deliverables carry no date the tool can parse.")
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
