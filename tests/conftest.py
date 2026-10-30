from __future__ import annotations

from pathlib import Path

import pytest

from asi_kletz import Brain
from asi_kletz.automation.session import ENV_AUTOMATION, ENV_SESSION
from asi_kletz.brain import (
    ENV_CONFIG,
    ENV_CONTROL_STRUCTURES,
    ENV_DB,
    ENV_OUT,
    ENV_STANDARDS,
    ENV_WORKBOOK,
    load_config,
)
from asi_kletz.gui.theme import ENV_THEME
from asi_kletz.locks import ENV_LOCK_DIR
from asi_kletz.prefs import ENV_PREFS
from asi_kletz.services.confluence_service import ConfluenceService

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
# a small 0.8.4 database (three plan rows, one sprint; no ``uid`` column): what 0.9.0 opens and stamps.
# Never opened in place: a test copies it, because opening it would stamp the committed file.
DB_0_8_4 = FIXTURES / "kletz-0.8.4.db"
# a small schema-10 database made with the 0.23.0 code (three plan rows, one parameter): what 0.24.0 opens and adds the
# thirteen STPA tables to. Copied, never opened in place.
DB_0_23_0 = FIXTURES / "kletz-0.23.0.db"
# the real workbook, if kletz.toml in the repo names one; the seeding test skips otherwise
WORKBOOK = Path(load_config(REPO_ROOT / "kletz.toml").get("workbook") or REPO_ROOT / "kletz.xlsx")

SEED_HOLIDAYS = REPO_ROOT / "data" / "us-holidays-2026-2029.json"  # 52 weekday holidays, the planner's calendar
SEED_WEIGHTS = REPO_ROOT / "data" / "deliverable-points.json"  # the estimation panel's consensus, 48 rows, 174 points

PLAN = "safety_plan_row"
# every registered entity, in registration order (the list is the design, not a cap), and its table
# 0.24.0: the seven control-structure entities and the six STPA entities follow the six of 0.14.0
CS_ENTITIES = [
    "control_structure", "cs_controller", "cs_algorithm", "cs_process_model_entry", "cs_edge", "cs_signal", "cs_note",
]
STPA_ENTITIES = ["stpa_analysis", "stpa_loss", "stpa_hazard", "stpa_uca", "stpa_scenario", "stpa_constraint"]
# 0.28.0: the nine HARA entities follow the STPA ones
HARA_ENTITIES = [
    "hara", "hara_vehicle", "hara_function", "hara_use_case", "hara_failure_mode", "hara_assumption", "hara_rating",
    "hara_assessment", "hara_approval",
]
ENTITIES = [PLAN, "sprint", "sprint_item", "week", "holiday", "parameter", *CS_ENTITIES, *STPA_ENTITIES, *HARA_ENTITIES]
CS_TABLES = [
    "control_structures", "cs_controllers", "cs_algorithms", "cs_process_model_entries", "cs_edges", "cs_signals",
    "cs_notes",
]
STPA_TABLES = ["stpa_analyses", "stpa_losses", "stpa_hazards", "stpa_ucas", "stpa_scenarios", "stpa_constraints"]
HARA_TABLES = [
    "haras", "hara_vehicles", "hara_functions", "hara_use_cases", "hara_failure_modes", "hara_assumptions",
    "hara_ratings", "hara_assessments", "hara_approvals",
]
TABLES = {
    "safety_plan", "sprint", "sprint_item", "week", "holiday", "parameter", *CS_TABLES, *STPA_TABLES, *HARA_TABLES,
}
# what the 0.8.4 fixture database holds
TABLES_0_8_4 = TABLES - {"holiday", "parameter", *CS_TABLES, *STPA_TABLES, *HARA_TABLES}
EMPTY_COUNTS = dict.fromkeys(ENTITIES, 0)  # every entity empty: what `status` and `dump` report on a fresh database
SHEETS = [
    "Safety Plan", "Sprints", "Sprint Items", "Weekly Status", "Holidays", "Parameters",
    "CS structures", "CS controllers", "CS algorithms", "CS process model", "CS edges", "CS signals", "CS notes",
    "STPA analyses", "STPA losses", "STPA hazards", "STPA UCAs", "STPA scenarios", "STPA constraints",
    "HARA", "HARA vehicles", "HARA functions", "HARA use cases", "HARA failure modes", "HARA assumptions",
    "HARA ratings", "HARA assessments", "HARA approvals",
]
# the real session probe (0.23.0), kept here because the autouse fixture below replaces it on the class; the one
# test of the probe itself puts it back with a stub Hopper
REAL_HAS_SESSION = ConfluenceService.has_session


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch, tmp_path):
    """Tests never see the developer's kletz.toml, environment, theme latch or lock directory.

    No test may touch a real file, and the family lock lives in a per-test folder so this suite
    never collides with a running tool or with the sister suite running at the same time.
    """
    monkeypatch.setenv(ENV_CONFIG, str(tmp_path / "absent.toml"))
    monkeypatch.delenv(ENV_DB, raising=False)
    monkeypatch.delenv(ENV_WORKBOOK, raising=False)
    monkeypatch.delenv(ENV_OUT, raising=False)
    monkeypatch.setenv(ENV_PREFS, str(tmp_path / "prefs.json"))
    monkeypatch.delenv(ENV_THEME, raising=False)
    monkeypatch.setenv(ENV_LOCK_DIR, str(tmp_path / "locks"))
    # the automation session file is per test too, and the server is on: a developer's open window
    # never receives test traffic, and no test reads or writes a real session
    monkeypatch.setenv(ENV_SESSION, str(tmp_path / "session.json"))
    monkeypatch.delenv(ENV_AUTOMATION, raising=False)
    # the standards folder is per test too: never the sibling repo (a test that wants one writes it)
    monkeypatch.setenv(ENV_STANDARDS, str(tmp_path / "standards"))
    # the template builder never finds the private control-structure shelf beside the repo by accident (0.24.0): a
    # test that wants it (the local-only smoke test) points the variable at it on purpose
    monkeypatch.setenv(ENV_CONTROL_STRUCTURES, str(tmp_path / "no-control-structures"))
    # the Find page button's session probe (0.23.0) reads the developer's keyring through asi_hopper: never
    # in a test (the Confluence GUI tests set it to True themselves)
    monkeypatch.setattr(ConfluenceService, "has_session", lambda self: False)


@pytest.fixture
def brain(tmp_path):
    with Brain(tmp_path / "test.db", workbook_path=tmp_path / "view.xlsx", out_dir=tmp_path / "out") as b:
        yield b


@pytest.fixture
def seeded(brain):
    """Three deliverables: one done, one ongoing, one pending."""
    brain.execute("create", entity=PLAN, data={
        "order": 1, "pdp_phase": "1", "lifecycle_phase": "1. Concept Development",
        "deliverable": "Safety Plan", "loc_dms": 1, "ref_qf_17": "1", "author_fusa_engineer": True,
        "verify_level_u3_refer_section_3_2": 1, "reviewer_tech_lead_functional_safety": 1, "status": "Done",
    })
    # the owner's sheet carried free text in the deadline column; a Done row keeps it as history (0.11.0), so
    # it is written the way an import writes it, through the repository
    brain.service(PLAN).repo.update(1, {"deadline": "Phase 1 exit"})
    brain.execute("create", entity=PLAN, data={
        "order": 2, "pdp_phase": "2", "lifecycle_phase": "2. HARA / Risk Assessment",
        "deliverable": "Hazard Analysis and Risk Assessment", "loc_jama": True, "ref_qp_11": True,
        "author_asi_stpa_practitioners": True, "status": "Ongoing",
    })
    brain.execute("create", entity=PLAN, data={
        "order": 3, "pdp_phase": "3", "lifecycle_phase": "3. Functional Safety Concept (FSC)",
        "deliverable": "Functional Safety Concept", "work_product_location": "DMS", "status": "Pending",
    })
    return brain
