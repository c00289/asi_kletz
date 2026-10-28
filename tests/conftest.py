from __future__ import annotations

from pathlib import Path

import pytest

from asi_kletz import Brain
from asi_kletz.automation.session import ENV_AUTOMATION, ENV_SESSION
from asi_kletz.brain import ENV_CONFIG, ENV_DB, ENV_OUT, ENV_WORKBOOK, load_config
from asi_kletz.gui.theme import ENV_THEME
from asi_kletz.locks import ENV_LOCK_DIR
from asi_kletz.prefs import ENV_PREFS

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures"
# a small 0.8.4 database (three plan rows, one sprint; no ``uid`` column): what 0.9.0 opens and stamps.
# Never opened in place: a test copies it, because opening it would stamp the committed file.
DB_0_8_4 = FIXTURES / "kletz-0.8.4.db"
# the real workbook, if kletz.toml in the repo names one; the seeding test skips otherwise
WORKBOOK = Path(load_config(REPO_ROOT / "kletz.toml").get("workbook") or REPO_ROOT / "kletz.xlsx")

SEED_HOLIDAYS = REPO_ROOT / "data" / "us-holidays-2026-2029.json"  # 52 weekday holidays, the planner's calendar

PLAN = "safety_plan_row"
# every registered entity, in registration order (the list is the design, not a cap), and its table
ENTITIES = [PLAN, "sprint", "sprint_item", "week", "holiday"]
TABLES = {"safety_plan", "sprint", "sprint_item", "week", "holiday"}
TABLES_0_8_4 = TABLES - {"holiday"}  # what the 0.8.4 fixture database holds
SHEETS = ["Safety Plan", "Sprints", "Sprint Items", "Weekly Status", "Holidays"]


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
        "verify_level_u3_refer_section_3_2": 1, "reviewer_tech_lead_functional_safety": 1,
        "deadline": "Phase 1 exit", "status": "Done",
    })
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
