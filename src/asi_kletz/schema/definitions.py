"""The built-in entities: the Safety Plan, since 0.8.0 the sprints, sprint items and weeks of
the Weekly Activity Tracker, since 0.10.0 the holidays the sprint planner skips, since 0.14.0 the
parameters of the standards, since 0.24.0 the STPA control structures and the STPA analyses (the
owner, 2026-10-29: "control structures were supposed to go into Kletz and not Dewey ... move everything
to Kletz"), and since 0.28.0 the HARA: the reference lists, the rating table and the assessment rows of
the ISO 19014 risk assessment, the MPLr of every row computed here, never typed (the owner, 2026-10-30:
"lets parametrize the hara ... the workbook is complicated as hell").

Importing this module registers the entities and their lookups with the default registries.
Column labels are the exact workbook headers so the Excel export reproduces the familiar sheet
and the Excel import can read it back. ``ALL_ENTITIES`` lists the registered entities in order:
the list is the design, not a cap (the one-table rule was retired in 0.8.0 by the tracker plan).
Since 0.9.0 every entity ends with the hidden ``uid`` (``fields.uid_field``): the trace of a row
across files and databases, never a column on a screen.
"""

from __future__ import annotations

import datetime as dt

from .entity import EntitySchema, flag_fields, slugify
from .fields import FieldSpec, FieldType, uid_field
from .lookups import default_lookups
from .registry import register_entity

T, M, N, E, D, J, B, U = (
    FieldType.TEXT, FieldType.MULTILINE, FieldType.INT, FieldType.ENUM, FieldType.DATE, FieldType.JSON,
    FieldType.BOOL, FieldType.URL,
)

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
# 0.19.0: the roles a standard's document parameters name (``fusa_engineer``, ``tech_lead_functional_safety``):
# the slugs of the author and reviewer headers, 22 of them. A ``parameter`` so named holds people (name and
# email each, alphabetical), never a plain value; see ``schema/people.py``.
ROLE_SLUGS = tuple(sorted({slugify(header) for header in (*AUTHOR_FLAGS, *REVIEWER_FLAGS)}))

# The owner, 2026-10-28: "the expected duration and deadline field is now a calculated field; another calculated
# field would be sprint, which tells you which sprint this deadline belongs to; when displaying the number of
# points switch to some default value enforced globally". The floor below is what a row with neither points nor
# a default weighs; `default_points` in kletz.toml overrides it.
DEFAULT_POINTS = 2
# 0.20.0: the Excel export's Safety Plan sheet. ``Work product`` is a derived column (no field): a hyperlink to
# the row's first URL, read by nobody; ``Work product URLs`` is the ``urls`` field, one URL per line. A row
# without a Jira ticket prints ``no ticket attached`` in its Jira key cell (the owner, 2026-10-29), and the
# import reads that text back as no key.
WORK_PRODUCT_HEADER = "Work product"
WORK_PRODUCT_URLS_HEADER = "Work product URLs"
NO_TICKET = "no ticket attached"
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
        # 0.14.0, the owner: "this company ties deliverables to Jira tickets"; the ticket's live status is the
        # Status column of an exported standard (docs: README, Standards and export)
        FieldSpec("jira_key", T, "Jira key", source=False, picker="jira",
                  help="The Jira ticket that tracks the deliverable; its live status fills an exported standard."),
        # 0.20.0, the owner: "add the ability to add url parameters to each deliverable... each deliverable may
        # have multiple url... on multiple urls just go to first; list of urls is sequential while lists of names
        # are alphabetical". An ORDERED JSON list of absolute http(s) URLs; the first is the link (the Excel
        # hyperlink, the window's Open button, a standard's ``row_N_url``); see ``schema/urls.py``.
        FieldSpec("urls", J, WORK_PRODUCT_URLS_HEADER, source=False, picker="urls",
                  help="The work product's URLs, in order, one per line; the first is the link; JSON [url, ...] on "
                       "the API."),
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
# The owner's law, 2026-10-29, verbatim: "what we know as sprint 3 is actually sprint 31, renumber appropriately,
# and then ensure that sprints always go Tuesday to Tuesday; this supersedes anything I said before; I also
# included a picture from systems engineering that is law for our sprints." The picture, a strip of seven
# sprints: 31 10/27-11/9, 32 11/10-11/23, 33 11/24-12/7, 34 12/8-12/21, 35 12/22-1/4, 36 1/5-1/18, 37 1/19-2/1.
# So a sprint is 14 calendar days, from a Tuesday to the Monday 13 days later, the next starting the next day;
# holidays never move, stretch or shorten one (35 runs straight through Christmas and New Year); capacity stays
# 8, fixed. This replaces the rule of 2026-10-28 (10 business days, holidays stretching the dates) everywhere.
SPRINT_LENGTH = 14  # calendar days, Tuesday to Monday
SPRINT_WEEKDAY = 1  # a sprint starts on a Tuesday (Monday is 0)
CADENCE_NUMBER = 31  # the picture's first sprint ...
CADENCE_START = dt.date(2026, 10, 27)  # ... starts here; every other sprint is 14 days times its distance away
CADENCE_RULE = (
    "a sprint starts on a Tuesday and ends on the Monday 13 days later (14 calendar days; holidays never move it), "
    f"the next starting the next day, from Sprint {CADENCE_NUMBER} ({CADENCE_START.isoformat()} to "
    f"{(CADENCE_START + dt.timedelta(days=SPRINT_LENGTH - 1)).isoformat()}); the owner's law of 2026-10-29"
)
# The owner's sprint rule, verbatim (docs/sprint-planner-plan.md, superseded 2026-10-29; README, Sprints): the
# `sprint` verb's help, the README and the roadmap document quote it from here.
SPRINT_RULE = (
    "The owner, 2026-10-29: \"what we know as sprint 3 is actually sprint 31, renumber appropriately, and then "
    "ensure that sprints always go Tuesday to Tuesday; this supersedes anything I said before; I also included a "
    "picture from systems engineering that is law for our sprints.\" The picture: Sprint 31 10/27 to 11/9, "
    "Sprint 32 11/10 to 11/23, Sprint 33 11/24 to 12/7, Sprint 34 12/8 to 12/21, Sprint 35 12/22 to 1/4, "
    "Sprint 36 1/5 to 1/18, Sprint 37 1/19 to 2/1. So a sprint is 14 calendar days, Tuesday to the Monday 13 "
    "days later, the next starting the next day; holidays never move, stretch or shorten a sprint; capacity is "
    "8 points per sprint, company policy, fixed (holidays never reduce points); sprints are consecutive with no "
    "gaps, numbered across the programme (SPRINT n) from Sprint 31 (2026-10-27 to 2026-11-09). The rule of "
    "2026-10-28 (10 business days, holidays stretching the dates) is superseded."
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

# -- the parameters of the standards (0.14.0) ---------------------------------------------------------------
# A parametrised standard (asi_standards) has blanks a person fills once: the vehicle type, the people in the
# roles. One row per name; ``standard`` is the folder the value belongs to, empty for every standard. The
# row-level parameters (points, sprint end, Jira status per plan row) are never stored: Kletz fills them.
# 0.19.0, the owner: "each safety deliverable can have multiple authors, so for any safety case field, instead
# of the parameter being a string it is now an array of human names sorted alphabetically; also must include
# email alongside name." A role parameter (its name in ``ROLE_SLUGS``) holds ``people``, a JSON list of
# ``{"name", "email"}`` kept alphabetical by name; ``value`` stays the plain string of ``vehicle_type`` and of
# a role written before 0.19.0 (a legacy name with no email yet, replaced the moment people are saved).
PARAMETER = register_entity(EntitySchema(
    name="parameter", table="parameter", label="Parameter", sheet="Parameters",
    description=(
        "One document-level parameter of the parametrised standards: its name (as the standard's source "
        "names it), the standard it belongs to (empty for every standard), its value (a plain parameter such "
        "as vehicle_type), its people (a role: name and email each, alphabetical) and a note."
    ),
    order_by=("standard", "name", "id"),
    fields=(
        FieldSpec("name", T, "Name", required=True),
        FieldSpec("standard", T, "Standard"),
        FieldSpec("value", T, "Value", help="A plain parameter's text (vehicle_type); a role holds people instead."),
        FieldSpec("people", J, "People", picker="people",
                  help="A role's people, alphabetical: one per line as Name <email>; JSON [{name, email}] on the API."),
        FieldSpec("note", M, "Note"),
        uid_field(),
    ),
))

# -- STPA control structures (0.24.0, moved here from the sister tool's 0.9.0; docs/control-structure-plan.md) ---
# The owner, 2026-10-29: "control structures were supposed to go into Kletz and not Dewey"; asked where STPA
# should live, "move everything to Kletz". One structure holds everything; every part names its structure by
# slug and its parent by key, so the rows survive any export and import (a workbook sheet carries no id column)
# and the STPA step objects below point at a controller by key and a signal by its id (plan section 2). The box
# kinds are asi_escher's CONTROL_NODE_KINDS, the arrow kinds its CONTROL_EDGE_KINDS; the service refuses a
# value outside them. The lists are JSON arrays (``schema/lists.py``), typed one item per line.
CS_STATUSES = ("Draft", "Reviewed", "Baselined")
CS_CONTROLLER_KINDS = (
    "controller", "human_controller", "controlled_process", "environment", "sensor", "actuator", "external_system",
)
CS_EDGE_KINDS = ("control_action", "feedback")
default_lookups.register("cs_status", CS_STATUSES)
default_lookups.register("cs_controller_kind", CS_CONTROLLER_KINDS)
default_lookups.register("cs_edge_kind", CS_EDGE_KINDS)

STRUCTURE = FieldSpec(
    "structure", T, "structure", required=True, help="Slug of the control structure this row belongs to",
)

CONTROL_STRUCTURE = register_entity(EntitySchema(
    name="control_structure", table="control_structures", label="Control Structure", sheet="CS structures",
    description=(
        "An STPA control structure: the controllers, their algorithms and process models, the control actions "
        "and feedback between them. Built by the factory, drawn by asi_escher, exported as draw.io, PNG and SVG."
    ),
    order_by=("name", "id"),
    fields=(
        FieldSpec("name", T, "name", required=True),
        FieldSpec("slug", T, "slug", help="Stable key the parts point at; unique; from the name when not given"),
        FieldSpec("system", T, "system", help="The system the structure controls, e.g. an autonomous loader"),
        FieldSpec("description", M, "description"),
        FieldSpec("source", T, "source", help="The file it came from, or 'built by hand'"),
        FieldSpec("status", E, "status", lookup="cs_status"),
        FieldSpec("revision", N, "revision"),
        uid_field(),
    ),
))

CS_CONTROLLER = register_entity(EntitySchema(
    name="cs_controller", table="cs_controllers", label="CS Controller", sheet="CS controllers",
    description=(
        "A box of a control structure: a controller, a human controller, the controlled process, "
        "the environment, a sensor, an actuator or an external system."
    ),
    order_by=("structure", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("order", N, "order", help="Top of the hierarchy first"),
        FieldSpec("key", T, "key", help="Stable slug within the structure; from the name if empty"),
        FieldSpec("name", T, "name", required=True),
        FieldSpec("kind", E, "kind", lookup="cs_controller_kind"),
        FieldSpec("responsibility", M, "responsibility"),
        FieldSpec("process_model_title", T, "process model title"),
        FieldSpec("note", M, "note"),
        uid_field(),
    ),
))

CS_ALGORITHM = register_entity(EntitySchema(
    name="cs_algorithm", table="cs_algorithms", label="CS Algorithm", sheet="CS algorithms",
    description="A control algorithm of a controller (V1, S3 ...), drawn in the orange section of its box.",
    order_by=("structure", "controller", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("controller", T, "controller", required=True, help="Key of the controller that owns it"),
        FieldSpec("order", N, "order"),
        FieldSpec("code", T, "code", required=True, help="V1, S3 ..."),
        FieldSpec("name", T, "name"),
        uid_field(),
    ),
))

CS_PROCESS_MODEL_ENTRY = register_entity(EntitySchema(
    name="cs_process_model_entry", table="cs_process_model_entries", label="CS Process Model Entry",
    sheet="CS process model",
    description=(
        "One entry of a controller's process model: a heading naming control actions, the variables "
        "the decision depends on, the feedback that updates them."
    ),
    order_by=("structure", "controller", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("controller", T, "controller", required=True, help="Key of the controller that owns it"),
        FieldSpec("order", N, "order"),
        FieldSpec("heading", T, "heading"),
        FieldSpec("control_actions", J, "control actions", help="Signal ids, one per line"),
        FieldSpec("variables", J, "variables", help="One per line"),
        FieldSpec("updated_by", J, "updated by", help="Signal ids, one per line"),
        FieldSpec("references", J, "references", help="Every signal id the entry mentions, one per line"),
        uid_field(),
    ),
))

CS_EDGE = register_entity(EntitySchema(
    name="cs_edge", table="cs_edges", label="CS Edge", sheet="CS edges",
    description=(
        "An arrow between two controllers carrying signals: a control action down the hierarchy or feedback up."
    ),
    order_by=("structure", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("order", N, "order"),
        FieldSpec("key", T, "key", help="Stable key within the structure, e.g. e7; the next free one when not given"),
        FieldSpec("kind", E, "kind", lookup="cs_edge_kind"),
        FieldSpec("source", T, "source", required=True, help="Key of the controller the arrow leaves"),
        FieldSpec("target", T, "target", required=True, help="Key of the controller the arrow enters"),
        uid_field(),
    ),
))

CS_SIGNAL = register_entity(EntitySchema(
    name="cs_signal", table="cs_signals", label="CS Signal", sheet="CS signals",
    description="One line on an arrow: CA-xx a control action, FB-xx feedback, with its name.",
    order_by=("structure", "edge", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("edge", T, "edge", required=True, help="Key of the edge that carries it"),
        FieldSpec("order", N, "order"),
        FieldSpec("signal_id", T, "signal id", required=True, help="CA-01, FB-12 ..."),
        FieldSpec("kind", E, "kind", lookup="cs_edge_kind", help="Defaults to the edge's kind and must match it"),
        FieldSpec("name", T, "name"),
        FieldSpec("placeholder", B, "placeholder", help="A signal still to be numbered"),
        uid_field(),
    ),
))

CS_NOTE = register_entity(EntitySchema(
    name="cs_note", table="cs_notes", label="CS Note", sheet="CS notes",
    description="A free-standing text of a control structure, floating beside a controller when attached to one.",
    order_by=("structure", "order", "id"),
    fields=(
        STRUCTURE,
        FieldSpec("order", N, "order"),
        FieldSpec("text", M, "text", required=True),
        FieldSpec("attached_to", T, "attached to", help="Key of the controller it floats beside, or empty"),
        uid_field(),
    ),
))

CS_ENTITIES = (
    CONTROL_STRUCTURE, CS_CONTROLLER, CS_ALGORITHM, CS_PROCESS_MODEL_ENTRY, CS_EDGE, CS_SIGNAL, CS_NOTE,
)

# -- STPA analyses: the step objects read from a Confluence page (0.24.0, from the sister tool's 0.10.0) -------
# One analysis holds everything read from one page; every part names its analysis by slug, so the same
# local code (UCA1, H2, CSTR28) means different things under different analyses and the rows survive
# any export and import. ``cite`` is the citation the reader builds: ``page <id> v<version> § <heading>
# (<anchor url>)``, editable, the one thing a report prints beside the object
# (asi_hopper/docs/confluence-integration-plan.md, section 7.1). The four UCA categories are the four columns
# of a context table, in the table's order.
STPA_SOURCE_KINDS = ("confluence", "hand", "workbook")  # 0.28.0: step 1 read from a HARA workbook
STPA_UCA_CATEGORIES = ("not_providing", "providing", "timing_order", "duration")
default_lookups.register("stpa_status", CS_STATUSES)
default_lookups.register("stpa_source_kind", STPA_SOURCE_KINDS)
default_lookups.register("stpa_uca_category", STPA_UCA_CATEGORIES)

ANALYSIS = FieldSpec(
    "analysis", T, "analysis", required=True, help="Slug of the STPA analysis this row belongs to",
)
CITE = FieldSpec(
    "cite", T, "cite",
    help="The citation: page <id> v<version> § <heading> (<anchor url>); built by the reader, editable",
)
NOTE = FieldSpec("note", M, "note", help="A note written here; kept when the page is refreshed")

STPA_ANALYSIS = register_entity(EntitySchema(
    name="stpa_analysis", table="stpa_analyses", label="STPA Analysis", sheet="STPA analyses",
    description=(
        "One STPA analysis: the losses, hazards, unsafe control actions, loss scenarios and constraints of "
        "one Confluence page (or written by hand), with the page, version and bundle it was read from."
    ),
    order_by=("name", "id"),
    fields=(
        FieldSpec("name", T, "name", required=True),
        FieldSpec("slug", T, "slug", help="Stable key the parts point at; unique; from the name when not given"),
        FieldSpec("system", T, "system", help="The system under analysis"),
        FieldSpec("status", E, "status", lookup="stpa_status"),
        FieldSpec("control_structure", T, "control structure",
                  help="Slug of the control structure the UCAs are linked to, or empty"),
        FieldSpec("source_kind", E, "source kind", lookup="stpa_source_kind", group="source"),
        FieldSpec("source_page_id", T, "source page id", group="source", help="The Confluence page id"),
        FieldSpec("source_url", U, "source url", group="source"),
        FieldSpec("source_version", N, "source version", group="source", help="The page version read"),
        FieldSpec("source_body_sha256", T, "source body sha256", group="source",
                  help="SHA-256 of the Markdown body read, as the bundle records it"),
        FieldSpec("source_taken_at", T, "source taken at", group="source", help="When the bundle was taken"),
        FieldSpec("source_bundle", T, "source bundle", group="source", help="The Hopper bundle folder read"),
        FieldSpec("note", M, "note"),
        uid_field(),
    ),
))

STPA_LOSS = register_entity(EntitySchema(
    name="stpa_loss", table="stpa_losses", label="STPA Loss", sheet="STPA losses",
    description="A loss (L1 ...) of an analysis.",
    order_by=("analysis", "order", "id"),
    fields=(
        ANALYSIS,
        FieldSpec("order", N, "order"),
        FieldSpec("code", T, "code", required=True, help="L1, L2 ...; unique within the analysis"),
        FieldSpec("text", M, "text"),
        CITE,
        NOTE,
        uid_field(),
    ),
))

STPA_HAZARD = register_entity(EntitySchema(
    name="stpa_hazard", table="stpa_hazards", label="STPA Hazard", sheet="STPA hazards",
    description="A hazard (H2, H4.3 ...) of an analysis; a dotted code refines the code before its last dot.",
    order_by=("analysis", "order", "id"),
    fields=(
        ANALYSIS,
        FieldSpec("order", N, "order"),
        FieldSpec("code", T, "code", required=True, help="H1, H4.3 ...; unique within the analysis"),
        FieldSpec("text", M, "text"),
        FieldSpec("parent", T, "parent", help="The hazard this one refines (H4 for H4.3), or empty"),
        FieldSpec("losses", J, "losses", help="Loss codes, one per line"),
        FieldSpec("retired", B, "retired", help="Struck through on the page"),
        CITE,
        NOTE,
        uid_field(),
    ),
))

STPA_UCA = register_entity(EntitySchema(
    name="stpa_uca", table="stpa_ucas", label="STPA UCA", sheet="STPA UCAs",
    description=(
        "An unsafe control action (UCA14 ...): a controller, a control action, one of the four categories, "
        "the hazards it leads to, and the controller and signal of a control structure when linked."
    ),
    order_by=("analysis", "order", "id"),
    fields=(
        ANALYSIS,
        FieldSpec("order", N, "order"),
        FieldSpec("code", T, "code", required=True, help="UCA1 ...; unique within the analysis"),
        FieldSpec("controller", T, "controller", help="The controller as the page names it"),
        FieldSpec("control_action", T, "control action", help="The control action as the page names it"),
        FieldSpec("category", E, "category", lookup="stpa_uca_category"),
        FieldSpec("text", M, "text"),
        FieldSpec("hazards", J, "hazards", help="Hazard codes, one per line"),
        FieldSpec("retired", B, "retired", help="Struck through on the page"),
        FieldSpec("duplicate_of", T, "duplicate of", help="The UCA this one duplicates, or empty"),
        FieldSpec("cs_controller", T, "cs controller", group="structure",
                  help="Key of the linked control structure's controller, or empty"),
        FieldSpec("cs_signal", T, "cs signal", group="structure",
                  help="Signal id of the linked control structure (CA-07), or empty"),
        CITE,
        NOTE,
        uid_field(),
    ),
))

STPA_SCENARIO = register_entity(EntitySchema(
    name="stpa_scenario", table="stpa_scenarios", label="STPA Scenario", sheet="STPA scenarios",
    description=(
        "One row of a loss-scenario table: the UCA (or its safe counterpart CAn), the scenario types, the causal "
        "factors, the beliefs and the constraints it leads to."
    ),
    order_by=("analysis", "order", "id"),
    fields=(
        ANALYSIS,
        FieldSpec("order", N, "order"),
        FieldSpec("row", N, "row", help="The table's row number"),
        FieldSpec("uca", T, "uca", help="The UCA code the row belongs to; empty with a warning when the cell is"),
        FieldSpec("counterpart", T, "counterpart", help="CA14 when the row is the safe counterpart, else empty"),
        FieldSpec("types", J, "types", help="Scenario types 1 to 4, one per line"),
        FieldSpec("causal_factors", M, "causal factors"),
        FieldSpec("beliefs", M, "beliefs"),
        FieldSpec("constraints", J, "constraints", help="CSTR codes, one per line"),
        FieldSpec("retired", B, "retired", help="Struck through on the page"),
        CITE,
        NOTE,
        uid_field(),
    ),
))

STPA_CONSTRAINT = register_entity(EntitySchema(
    name="stpa_constraint", table="stpa_constraints", label="STPA Constraint", sheet="STPA constraints",
    description="A safety constraint (CSTR28 ...); the text is empty when the page only references it.",
    order_by=("analysis", "order", "id"),
    fields=(
        ANALYSIS,
        FieldSpec("order", N, "order"),
        FieldSpec("code", T, "code", required=True, help="CSTR1 ...; unique within the analysis"),
        FieldSpec("text", M, "text", help="From the first row that spells it out; empty when only referenced"),
        CITE,
        NOTE,
        uid_field(),
    ),
))

STPA_ENTITIES = (STPA_ANALYSIS, STPA_LOSS, STPA_HAZARD, STPA_UCA, STPA_SCENARIO, STPA_CONSTRAINT)

# -- HARA: the ISO 19014 risk assessment, parametrised (0.28.0) ------------------------------------------------
# The owner, 2026-10-30: "lets parametrize the hara ... the workbook is complicated as hell". The wheel loader
# HARA workbook (26 sheets, 24,000 formulas) reduces to six kinds of sheet, one chain of ids and one lookup
# (Roy's Brain, work product playground/hara/dissection). Here it is nine tables and one rule. A ``hara`` row is
# the document: its parameters (the Document Information and Cover sheets) and the slug of the STPA analysis
# that holds its step 1 (the losses, the hazards H-n, their scenarios H-n.m and hazardous events H-n.m.k, the
# system-level constraints SC-n). The reference lists are ``hara_vehicle`` (the ISO 19014 annex letters),
# ``hara_function``, ``hara_use_case``, ``hara_failure_mode`` and ``hara_assumption``. ``hara_rating`` is the
# judgment, once per (function, use case, failure mode): the MPLr under every annex letter and the foundation
# vehicle's cumulative one. ``hara_assessment`` is one row of the four context sheets (base or work implement
# functions x base or work implement use cases): a hazardous event, a function, a use case, a failure mode;
# its ``mplr`` is **calculated** from the rating table and the document's vehicle code (the rule the workbook's
# second generation began and never finished: its vehicle code was empty), what the workbook typed is kept as
# ``stated_mplr`` beside it, so ``hara check`` can say where they differ. ``hara_approval`` is the Y / N of an
# approver **role** on a hazardous event: the workbook headed those columns "Role: Name"; the name stays in the
# workbook, never here (the Brain shows roles, never people).
HARA_STATUSES = CS_STATUSES
HARA_CONTEXTS = ("BF-BUC", "BF-WIUC", "WIF-BUC", "WIF-WIUC")
HARA_FUNCTION_KINDS = ("base", "work_implement")
HARA_ASSUMPTION_SOURCES = ("ISO 19014", "ASI")
HARA_DECISIONS = ("Y", "N")
# the MPLr scale (ISO 19014), lowest first; "-" is no rating found, "" an empty rating cell
MPLR_SCALE = ("QM", "a", "b", "c", "d", "e")
# the other standards' terms for an MPLr, as the workbook's Summary states them: PLr (ISO 13849) the same
# letter, AgPLr (ISO 25119) the same letter and no term for QM, SIL (IEC 61508) by the usual correspondence
MPLR_TO_PLR = {"QM": "QM", "a": "a", "b": "b", "c": "c", "d": "d", "e": "e"}
MPLR_TO_AGPLR = {"QM": "-", "a": "a", "b": "b", "c": "c", "d": "d", "e": "e"}
MPLR_TO_SIL = {"QM": "QM", "a": "-", "b": "1", "c": "1", "d": "2", "e": "3"}
CUMULATIVE_CODE = "cumulative"  # the vehicle code that reads the foundation vehicle's cumulative column
default_lookups.register("hara_status", HARA_STATUSES)
default_lookups.register("hara_context", HARA_CONTEXTS)
default_lookups.register("hara_function_kind", HARA_FUNCTION_KINDS)
default_lookups.register("hara_assumption_source", HARA_ASSUMPTION_SOURCES)
default_lookups.register("hara_decision", HARA_DECISIONS)

HARA_REF = FieldSpec("hara", T, "hara", required=True, help="Slug of the HARA this row belongs to")

HARA = register_entity(EntitySchema(
    name="hara", table="haras", label="HARA", sheet="HARA",
    description=(
        "One hazard analysis and risk assessment (ISO 19014): the document's parameters, the vehicle code every "
        "MPLr is computed for, and the STPA analysis that holds its losses, hazards and constraints."
    ),
    order_by=("name", "id"),
    fields=(
        FieldSpec("name", T, "name", required=True),
        FieldSpec("slug", T, "slug", help="Stable key the parts point at; unique; from the name when not given"),
        FieldSpec("system", T, "system", help="The system under analysis (Document Information: System Name)"),
        FieldSpec("status", E, "status", lookup="hara_status"),
        FieldSpec("vehicle_code", T, "vehicle code",
                  help="The ISO 19014 annex letter the MPLr is read for (G: large wheel loaders), or "
                       "`cumulative` for the foundation vehicle's column; empty: no MPLr is computed"),
        FieldSpec("vehicle_name", T, "vehicle name"),
        FieldSpec("analysis", T, "analysis",
                  help="Slug of the STPA analysis holding step 1: the losses, hazards (H-n, H-n.m, H-n.m.k) and "
                       "system-level constraints (SC-n)"),
        FieldSpec("project", T, "project", group="document"),
        FieldSpec("department", T, "department", group="document"),
        FieldSpec("company", T, "company", group="document"),
        FieldSpec("standard", T, "standard", group="document", help="Risk Assessment- ISO 19014"),
        FieldSpec("supporting_document", T, "supporting document", group="document"),
        FieldSpec("analysis_date", D, "analysis date", group="document"),
        FieldSpec("revision", T, "revision", group="document", help="The revision mark on the cover"),
        FieldSpec("description", M, "description", group="document", help="The system description paragraph"),
        FieldSpec("scope", M, "scope", group="document", help="The scope sentence"),
        FieldSpec("source", T, "source", group="source", help="The workbook the HARA was read from, or empty"),
        FieldSpec("source_sha256", T, "source sha256", group="source"),
        FieldSpec("source_generation", N, "source generation", group="source",
                  help="1: the assessment sheets Document Information names; 2: the hidden HARA-n twins"),
        NOTE,
        uid_field(),
    ),
))

HARA_VEHICLE = register_entity(EntitySchema(
    name="hara_vehicle", table="hara_vehicles", label="HARA Vehicle", sheet="HARA vehicles",
    description="An ISO 19014 annex vehicle (the Scope sheet): its letter, the ASI vehicle under it, the project.",
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("letter", T, "letter", required=True, help="The annex letter A to Z; unique within the HARA"),
        FieldSpec("iso_vehicle", T, "ISO 19014 vehicle"),
        FieldSpec("asi_vehicle", T, "ASI vehicle"),
        FieldSpec("projects", T, "ASI projects"),
        uid_field(),
    ),
))

HARA_FUNCTION = register_entity(EntitySchema(
    name="hara_function", table="hara_functions", label="HARA Function", sheet="HARA functions",
    description=(
        "A machine function (the Function List): base or work implement, the annex vehicles it applies to, "
        "the function-level MPLr the list carries, the definition from the Vocabulary."
    ),
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("name", T, "name", required=True, help="As the assessment rows spell it; unique within the HARA"),
        FieldSpec("kind", E, "kind", lookup="hara_function_kind"),
        FieldSpec("vehicles", J, "vehicles", help="Annex letters the function applies to, one per line"),
        FieldSpec("cumulative_mplr", T, "cumulative MPLr", help="The Function List's Foundation Vehicle Cumulative"),
        FieldSpec("specific_mplr", T, "specific MPLr", help="The Function List's '<vehicle> Specific MPLr'"),
        FieldSpec("definition", M, "definition"),
        uid_field(),
    ),
))

HARA_USE_CASE = register_entity(EntitySchema(
    name="hara_use_case", table="hara_use_cases", label="HARA Use Case", sheet="HARA use cases",
    description="An ISO 19014 use case (the Use Case List): the annex vehicles it applies to, the definition.",
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("name", T, "name", required=True, help="As the assessment rows spell it; unique within the HARA"),
        FieldSpec("base", B, "base", help="Applies to the base functions (the list's asterisk)"),
        FieldSpec("vehicles", J, "vehicles", help="Annex letters the use case applies to, one per line"),
        FieldSpec("definition", M, "definition"),
        uid_field(),
    ),
))

HARA_FAILURE_MODE = register_entity(EntitySchema(
    name="hara_failure_mode", table="hara_failure_modes", label="HARA Failure Mode", sheet="HARA failure modes",
    description="A failure mode (ISO 19014-5): failure to apply or release on demand, uncommanded activation "
                "or deactivation.",
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("name", T, "name", required=True, help="As the assessment rows spell it; unique within the HARA"),
        uid_field(),
    ),
))

HARA_ASSUMPTION = register_entity(EntitySchema(
    name="hara_assumption", table="hara_assumptions", label="HARA Assumption", sheet="HARA assumptions",
    description="An assumption (the Assumption List): ISO 19014's per vehicle, or ASI's.",
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("source", E, "source", lookup="hara_assumption_source"),
        FieldSpec("vehicle", T, "vehicle", help="The ISO 19014 vehicle, or All"),
        FieldSpec("text", M, "text", required=True),
        uid_field(),
    ),
))

HARA_RATING = register_entity(EntitySchema(
    name="hara_rating", table="hara_ratings", label="HARA Rating", sheet="HARA ratings",
    description=(
        "The judgment, once per (function, use case, failure mode): the MPLr under every annex letter and the "
        "foundation vehicle's cumulative one (the RA(ISO 19014) sheet, widened by RA(for all vehicles))."
    ),
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("function", T, "function", required=True),
        FieldSpec("use_case", T, "use case", required=True),
        FieldSpec("failure_mode", T, "failure mode", required=True),
        FieldSpec("ratings", J, "ratings",
                  help="A JSON object: annex letter to MPLr (QM, a to e); typed as `G: b` lines"),
        FieldSpec("cumulative", T, "cumulative MPLr", help="The Foundation Vehicle Cumulative column"),
        FieldSpec("comment", M, "comment"),
        uid_field(),
    ),
))

HARA_ASSESSMENT = register_entity(EntitySchema(
    name="hara_assessment", table="hara_assessments", label="HARA Assessment", sheet="HARA assessments",
    description=(
        "One row of a context sheet: a hazardous event, a function, a use case, a failure mode; the MPLr "
        "calculated from the rating table and the HARA's vehicle code, the workbook's typed value beside it."
    ),
    order_by=("hara", "context", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("context", E, "context", required=True, lookup="hara_context"),
        FieldSpec("order", N, "order"),
        FieldSpec("hazard", T, "hazard", help="H-n: the hazard the event refines (from the event code)"),
        FieldSpec("scenario", T, "scenario", help="H-n.m: the scenario the event refines (from the event code)"),
        FieldSpec("event", T, "hazardous event", required=True, help="H-n.m.k, a hazard of the STPA analysis"),
        FieldSpec("function", T, "function"),
        FieldSpec("use_case", T, "use case"),
        FieldSpec("failure_mode", T, "failure mode"),
        FieldSpec("mplr", T, "MPLr", calculated=True,
                  help="Calculated: the rating of (function, use case, failure mode) under the HARA's vehicle code; "
                       "`-` when the rating table has no such key, empty when the cell is empty"),
        FieldSpec("stated_mplr", T, "stated MPLr", help="What the workbook's own formula answered, kept as evidence"),
        FieldSpec("cumulative_mplr", T, "cumulative hazard MPLr", help="Typed on the hazard's first row"),
        FieldSpec("comment", M, "comment"),
        FieldSpec("sg_global_id", T, "SG global id"),
        FieldSpec("safety_goal", T, "safety goal", help="SC-n: the system-level constraint of the hazard"),
        FieldSpec("sg_mplr", T, "SG MPLr", help="Typed on the hazard's first row"),
        uid_field(),
    ),
))

HARA_APPROVAL = register_entity(EntitySchema(
    name="hara_approval", table="hara_approvals", label="HARA Approval", sheet="HARA approvals",
    description="An approver role's Y / N on a hazardous event (the Hazardous Events sheet); roles, never people.",
    order_by=("hara", "order", "id"),
    fields=(
        HARA_REF,
        FieldSpec("order", N, "order"),
        FieldSpec("event", T, "hazardous event", required=True, help="H-n.m.k"),
        FieldSpec("role", T, "role", required=True, help="robot_chief, software_lead, ...: a role slug, never a name"),
        FieldSpec("decision", E, "decision", lookup="hara_decision"),
        FieldSpec("comment", M, "comment"),
        uid_field(),
    ),
))

HARA_ENTITIES = (
    HARA, HARA_VEHICLE, HARA_FUNCTION, HARA_USE_CASE, HARA_FAILURE_MODE, HARA_ASSUMPTION, HARA_RATING,
    HARA_ASSESSMENT, HARA_APPROVAL,
)

ALL_ENTITIES = (
    SAFETY_PLAN_ROW, SPRINT, SPRINT_ITEM, WEEK, HOLIDAY, PARAMETER, *CS_ENTITIES, *STPA_ENTITIES, *HARA_ENTITIES,
)
