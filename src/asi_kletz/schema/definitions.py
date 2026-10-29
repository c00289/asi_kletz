"""The built-in entities: the Safety Plan, since 0.8.0 the sprints, sprint items and weeks of
the Weekly Activity Tracker, and since 0.10.0 the holidays the sprint planner skips.

Importing this module registers the entities and their lookups with the default registries.
Column labels are the exact workbook headers so the Excel export reproduces the familiar sheet
and the Excel import can read it back. ``ALL_ENTITIES`` lists the registered entities in order:
the list is the design, not a cap (the one-table rule was retired in 0.8.0 by the tracker plan).
Since 0.9.0 every entity ends with the hidden ``uid`` (``fields.uid_field``): the trace of a row
across files and databases, never a column on a screen.
"""

from __future__ import annotations

from .entity import EntitySchema, flag_fields
from .fields import FieldSpec, FieldType, uid_field
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

# The owner, 2026-10-28: "the expected duration and deadline field is now a calculated field; another calculated
# field would be sprint, which tells you which sprint this deadline belongs to; when displaying the number of
# points switch to some default value enforced globally". The floor below is what a row with neither points nor
# a default weighs; `default_points` in kletz.toml overrides it.
DEFAULT_POINTS = 2
CALCULATED_RULE = "sprint, sprint start, sprint end and deadline are calculated from points and the sprint chain"
DEFAULTS_RULE = "default_points is set by `plan weights load` (the estimation panel's record)"

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
        # 0.11.0: the weight in sprint points (editable; empty means the default), the estimation panel's
        # default (set by `plan weights load`), the sprint the last point lands in and that sprint's end
        FieldSpec("points", N, "Points", source=False, default_from="default_points",
                  help="The weight of the deliverable in sprint points; a deliverable may span sprints."),
        FieldSpec("default_points", N, "Default points", source=False, readonly=True,
                  help="The estimation panel's consensus (docs/deliverable-points.md); set by `plan weights load`."),
        FieldSpec("sprint", N, "Sprint", source=False, calculated=True,
                  help="Calculated: the sprint in which the deliverable's last point lands."),
        # 0.11.2, the owner: "add the beginning of sprint and end of sprint to the right of the sprint column"
        FieldSpec("sprint_start", D, "Sprint start", source=False, calculated=True,
                  help="Calculated: the first day of that sprint."),
        FieldSpec("sprint_end", D, "Sprint end", source=False, calculated=True,
                  help="Calculated: the last day of that sprint; the deadline is the same date."),
        FieldSpec("work_product_location", T, "Work Product Location"),
        *flag_fields("location", "loc", LOCATION_FLAGS),
        FieldSpec("work_product_reference", T, "Work Product Reference"),
        *flag_fields("reference", "ref", REFERENCE_FLAGS),
        FieldSpec("author", T, "Author", group="author"),
        *flag_fields("author", "author", AUTHOR_FLAGS),
        *flag_fields("verification", "verify", VERIFICATION_FLAGS),
        FieldSpec("gate_reviewer", T, "Gate Reviewer", group="reviewer"),
        *flag_fields("reviewer", "reviewer", REVIEWER_FLAGS),
        FieldSpec("deadline", T, "Expected Duration/Deadline", calculated=True,
                  help="Calculated: the end date of the sprint in which the deliverable's last point lands."),
        FieldSpec("status", E, "Status (Pending/ Ongoing/ Blocked/ Alternative/Out-of-Scope/ Done)",
                  lookup="plan_status"),
        uid_field(),
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
# The owner's rule, 2026-10-28 (docs/sprint-planner-plan.md): "Capacity is 8 points per sprint, company policy
# (8 productive days of the 10). Holidays never reduce points." And: "every single sprint except the one in the
# past is 8 points; set this as a global value that is fixed." So this is not a default: every sprint that is
# not Closed has it (enforced on open and on every create and update); a Closed sprint keeps its stored capacity
# as history. No kletz.toml key and no command option sets it.
SPRINT_CAPACITY = 8
CAPACITY_RULE = (
    f"every sprint that is not Closed has a capacity of {SPRINT_CAPACITY} points (company policy, fixed: "
    "\"every single sprint except the one in the past is 8 points\"); a Closed sprint keeps its own as history"
)
# "A sprint spans 10 business days. Monday to Friday count; weekends and holidays do not." Business days, not
# calendar days, since 0.10.0; the holidays are the `holiday` table. `sprint_days` in kletz.toml overrides it.
SPRINT_DAYS = 10
# The owner's sprint rule, 2026-10-28, verbatim (docs/sprint-planner-plan.md): the `sprint` verb's help, the
# README and the roadmap document quote it from here.
SPRINT_RULE = (
    "A sprint spans 10 business days. Monday to Friday count; weekends and holidays do not, so a sprint that "
    "contains a holiday ends one calendar day later per holiday. Dates move as holidays become real; the cadence "
    "does not. Capacity is 8 points per sprint, company policy (8 productive days of the 10). Holidays never "
    "reduce points. Sprints are consecutive with no gaps, numbered across the programme (SPRINT n); the chain "
    "continues from Sprint 2 (2026-10-27 to 2026-11-10). We do not know the work yet: future sprints are empty, "
    "Planned, with no lifecycle phase, and will be adjusted as dates become real. "
    "Every single sprint except the one in the past is 8 points; set this as a global value that is fixed."
)

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
        uid_field(),
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
        # 0.13.0: the plan row's uid beside its id, hidden; the pointer that survives a plan re-import that
        # renumbered the rows (docs/hidden-identity-plan.md, open question 1). Kept in step with plan_row by
        # the sprint service: given one, the other follows; the uid wins when both are given and disagree.
        FieldSpec("plan_uid", T, "Safety Plan row uid", hidden=True,
                  help="Hidden: the uid of the Safety Plan row plan_row points at."),
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
        uid_field(),
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
        uid_field(),
    ),
))

# -- holidays (0.10.0) -----------------------------------------------------------------------------------
# The owner's rule, 2026-10-28 (docs/sprint-planner-plan.md): a sprint spans 10 business days; Monday to
# Friday count, weekends and holidays do not. The holidays live here, any status counts for the calendar;
# ``assumed`` until the company confirms the date, then ``confirmed``.
HOLIDAY_STATUSES = ("assumed", "confirmed")
default_lookups.register("holiday_status", HOLIDAY_STATUSES)

HOLIDAY = register_entity(EntitySchema(
    name="holiday", table="holiday", label="Holiday", sheet="Holidays",
    description=(
        "One holiday the sprint planner skips: its date (observed), its name, whether it is assumed or "
        "confirmed, and a note. Loaded from data/us-holidays-2026-2029.json by `holiday load`."
    ),
    order_by=("date", "id"),
    fields=(
        FieldSpec("date", D, "Date", required=True),
        FieldSpec("name", T, "Name", required=True),
        FieldSpec("status", E, "Status (assumed/ confirmed)", lookup="holiday_status"),
        FieldSpec("note", M, "Note"),
        uid_field(),
    ),
))

ALL_ENTITIES = (SAFETY_PLAN_ROW, SPRINT, SPRINT_ITEM, WEEK, HOLIDAY)
