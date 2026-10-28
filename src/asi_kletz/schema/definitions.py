"""The built-in entities: the Safety Plan, and since 0.8.0 the sprints, sprint items and weeks of
the Weekly Activity Tracker.

Importing this module registers the entities and their lookups with the default registries.
Column labels are the exact workbook headers so the Excel export reproduces the familiar sheet
and the Excel import can read it back. ``ALL_ENTITIES`` lists the registered entities in order:
the list is the design, not a cap (the one-table rule was retired in 0.8.0 by the tracker plan).
"""

from __future__ import annotations

from .entity import EntitySchema, flag_fields
from .fields import FieldSpec, FieldType
from .lookups import default_lookups
from .registry import register_entity

T, M, N, E, D = FieldType.TEXT, FieldType.MULTILINE, FieldType.INT, FieldType.ENUM, FieldType.DATE

# -- lookups ----------------------------------------------------------------
LIFECYCLE_PHASES = (
    "1. Concept Development",
    "2. HARA / Risk Assessment",
    "3. Functional Safety Concept (FSC)",
    "4. System Design and Development",
    "5. HW & SW Design and Development",
    "6. Integration and Testing",
    "7. Safety Validation",
    "8. Functional Safety Assessment",
    "9. Production and Operation",
    "10. Decommissioning",
)
PLAN_STATUSES = ("Pending", "Ongoing", "Blocked", "Alternative", "Out-of-Scope", "Done")

default_lookups.register("pdp_phase", ("1", "2", "3", "4", "5", "6"))
default_lookups.register("lifecycle_phase", LIFECYCLE_PHASES)
default_lookups.register("plan_status", PLAN_STATUSES)

# -- safety plan matrix --------------------------------------------------------
LOCATION_FLAGS = ("DMS", "JAMA", "Sharepoint")
REFERENCE_FLAGS = (
    "Foundational RA", "PDP/QF", "PDP-16", "PDP-17", "Platform FSC", "Platform TSC",
    "QF-12", "QF-17", "QF-18", "QF-19", "QF-FSA Report", "QF-Safety Case",
    "QM/QP-Risk Assessment Plan", "QM-Production Plan", "QM-Validation Plan",
    "QP-06", "QP-11", "QP-12", "QP-31", "QP-32", "QP-FSA", "Scope Definition", "Supplier",
)
AUTHOR_FLAGS = (
    "Dev Manager", "Electronics Engineer (Mechanical and Electrical)", "Embedded Software Engineer",
    "FuSa Engineer", "Mechatronics Software Engineer", "Mechatronics Systems Engineer",
    "Product Manager", "Production Team", "Reliability Engineer", "Respective Robot Team Member",
    "Robot Chief", "System Architect", "Tech Lead - Occupational Safety", "V&V Team",
    "Independent Reviewer", "ASI STPA Practitioners", "Tech Lead - Functional Safety",
)
VERIFICATION_FLAGS = ("Level U3 (refer section 3.2)", "QP-06 Review Process", "Scope Definition Review")
REVIEWER_FLAGS = (
    "Tech Lead - Functional Safety", "Tech Lead - Occupational Safety", "Tech Lead - Respective Area",
    "Tech Lead - Safety and Compliance", "Tech Lead - Systems", "PAT", "Technical Training Team",
)

SAFETY_PLAN_ROW = register_entity(EntitySchema(
    name="safety_plan_row", table="safety_plan", label="Safety Plan Row", sheet="Safety Plan",
    description=(
        "One deliverable of the platform safety plan: lifecycle phase, where the work product "
        "lives, which QMS documents it references, who authors, verifies, and reviews it."
    ),
    order_by=("order", "id"),
    fields=(
        FieldSpec("order", N, "order"),
        FieldSpec("pdp_phase", E, "PDP Phases", lookup="pdp_phase"),
        FieldSpec("lifecycle_phase", E, "Safety Lifecycle Phase", lookup="lifecycle_phase"),
        FieldSpec("deliverable", M, "Safety Deliverables", required=True),
        FieldSpec("work_product_location", T, "Work Product Location"),
        *flag_fields("location", "loc", LOCATION_FLAGS),
        FieldSpec("work_product_reference", T, "Work Product Reference"),
        *flag_fields("reference", "ref", REFERENCE_FLAGS),
        FieldSpec("author", T, "Author", group="author"),
        *flag_fields("author", "author", AUTHOR_FLAGS),
        *flag_fields("verification", "verify", VERIFICATION_FLAGS),
        FieldSpec("gate_reviewer", T, "Gate Reviewer", group="reviewer"),
        *flag_fields("reviewer", "reviewer", REVIEWER_FLAGS),
        FieldSpec("deadline", T, "Expected Duration/Deadline"),
        FieldSpec("status", E, "Status (Pending/ Ongoing/ Blocked/ Alternative/Out-of-Scope/ Done)",
                  lookup="plan_status"),
    ),
))

# -- weekly activity tracker (0.8.0) --------------------------------------------
# A sprint is a dated interval of work with a capacity in points (10 by default); a sprint item is
# one thing it commits to (a deliverable of the plan, a Jira issue, a meeting, a question); a week
# is one ``WEEK OF`` block of the tracker text, one row per section, the prose kept verbatim.
SPRINT_STATUSES = ("Planned", "Active", "Closed")
ITEM_STATUSES = ("To Do", "In Progress", "Done", "Carried")
ITEM_KINDS = ("Deliverable", "Jira", "Meeting", "Question", "Other")
WEEK_SECTIONS = ("Note", "Outcomes", "Issues", "Jira")
SPRINT_CAPACITY = 10  # points per sprint when neither kletz.toml nor the sprint says otherwise
SPRINT_DAYS = 14

default_lookups.register("sprint_status", SPRINT_STATUSES)
default_lookups.register("item_status", ITEM_STATUSES)
default_lookups.register("item_kind", ITEM_KINDS)
default_lookups.register("week_section", WEEK_SECTIONS)

SPRINT = register_entity(EntitySchema(
    name="sprint", table="sprint", label="Sprint", sheet="Sprints",
    description=(
        "One sprint of the Weekly Activity Tracker: its number across the programme, the printed "
        "label (SPRINT 1, SPRINT 2), lifecycle phase, dates, capacity in points, goal and status."
    ),
    order_by=("number", "id"),
    fields=(
        FieldSpec("number", N, "Number", required=True),
        FieldSpec("label", T, "Label"),
        FieldSpec("lifecycle_phase", E, "Safety Lifecycle Phase", lookup="lifecycle_phase"),
        FieldSpec("start", D, "Start"),
        FieldSpec("end", D, "End"),
        FieldSpec("capacity", N, "Capacity (points)"),
        FieldSpec("goal", M, "Goal"),
        FieldSpec("status", E, "Status (Planned/ Active/ Closed)", lookup="sprint_status"),
        FieldSpec("closed_on", D, "Closed on"),
    ),
))

SPRINT_ITEM = register_entity(EntitySchema(
    name="sprint_item", table="sprint_item", label="Sprint Item", sheet="Sprint Items",
    description=(
        "One commitment of a sprint: a deliverable of the plan (by row id), a Jira issue (by key), "
        "a meeting or a question, with its points, target, note and status."
    ),
    order_by=("sprint", "order", "id"),
    fields=(
        FieldSpec("sprint", N, "Sprint", required=True),
        FieldSpec("order", N, "order"),
        FieldSpec("kind", E, "Kind (Deliverable/ Jira/ Meeting/ Question/ Other)", lookup="item_kind"),
        FieldSpec("title", M, "Title", required=True),
        FieldSpec("plan_row", N, "Safety Plan row id"),
        FieldSpec("jira_key", T, "Jira key"),
        FieldSpec("issue_type", T, "Jira type"),
        FieldSpec("heading", M, "Heading printed before the item"),
        FieldSpec("points", N, "Points"),
        FieldSpec("target", T, "Sprint target"),
        FieldSpec("note", M, "Note"),
        FieldSpec("jira_line", T, "Jira status line"),
        FieldSpec("status", E, "Status (To Do/ In Progress/ Done/ Carried)", lookup="item_status"),
        FieldSpec("carried_from", N, "Carried from sprint"),
        FieldSpec("done_on", D, "Done on"),
    ),
))

WEEK = register_entity(EntitySchema(
    name="week", table="week", label="Week", sheet="Weekly Status",
    description=(
        "One section of one WEEK OF block of the tracker text: the week's start date, its sprint, "
        "the section (Note, Outcomes, Issues, Jira) and the text, verbatim."
    ),
    order_by=("start", "order", "id"),
    fields=(
        FieldSpec("start", D, "Week of", required=True),
        FieldSpec("sprint", N, "Sprint", required=True),
        FieldSpec("section", E, "Section (Note/ Outcomes/ Issues/ Jira)", lookup="week_section", required=True),
        FieldSpec("order", N, "order"),
        FieldSpec("text", M, "Text"),
    ),
))

ALL_ENTITIES = (SAFETY_PLAN_ROW, SPRINT, SPRINT_ITEM, WEEK)
