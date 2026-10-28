"""The ``jira`` verb and ``JiraService`` against asi_hopper's replay fixtures: no network, no session, no keyring.

The fixture index carries a recorded search for ``OPEN_JQL`` (three issues, one page) and a recorded
``getJiraIssue`` for HWL-2575 with the ``comment`` field (an empty history), so both actions replay
end to end. A stub Hopper covers what the fixtures cannot reach: exactly-at-limit behaviour, null-heavy
rows, comment ordering, and the error classes.
"""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from asi_kletz import Brain
from asi_kletz.automation.cli import build_parser
from asi_kletz.brain import ENV_CONFIG
from asi_kletz.commands import default_command_factory
from asi_kletz.services.jira_service import INSTALL_HINT, LIVE_FIELDS, LIVE_JQL, LIVE_LIMIT, live_row
from tests.conftest import PLAN, REPO_ROOT, TABLES

HOPPER_FIXTURES = REPO_ROOT.parent / "asi_hopper" / "tests" / "fixtures"
OPEN_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY status ASC, updated DESC"
OPEN_KEYS = ["HWL-2572", "HWL-2575", "HWL-2620"]
LOGIN_HINT = "no Atlassian session for this account; run `asi-hopper auth login` once"

pytestmark = pytest.mark.skipif(
    not (HOPPER_FIXTURES / "index.json").is_file(), reason="asi_hopper fixtures are not checked out next to asi_kletz"
)


@pytest.fixture(autouse=True)
def _replay_hopper(monkeypatch):
    """asi_hopper reads its gateway from the environment: point it at the recorded fixtures."""
    monkeypatch.delenv("ASI_HOPPER_CONFIG", raising=False)
    monkeypatch.setenv("ASI_HOPPER_GATEWAY", "replay")
    monkeypatch.setenv("ASI_HOPPER_FIXTURES", str(HOPPER_FIXTURES))


# -- helpers --------------------------------------------------------------------------
def _tables(brain: Brain) -> set[str]:
    rows = brain.storage.fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return {r["name"] for r in rows} - {"schema_migrations", "audit_log"}


def _assert_aware_utc(text: str) -> None:
    parsed = dt.datetime.fromisoformat(text)
    assert parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0)


@dataclass(frozen=True)
class Rec:
    """The attributes ``live_row`` and ``comments`` read from an asi_hopper IssueRecord."""

    key: str
    issue_type: str | None = None
    summary: str = ""
    status: str | None = None
    status_category: str | None = None
    resolution: str | None = None
    priority: str | None = None
    assignee: str | None = None
    reporter: str | None = None
    labels: tuple[str, ...] = ()
    components: tuple[str, ...] = ()
    parent: Any = None
    created: str | None = None
    updated: str | None = None
    due: str | None = None
    url: str = ""
    comments: tuple[Any, ...] = ()


@dataclass(frozen=True)
class Com:
    id: str | None
    author: str | None
    author_id: str | None
    created: str | None
    updated: str | None
    body: str | None


class StubHopper:
    def __init__(self, records: list[Any] = (), *, fail: Exception | None = None) -> None:
        self.records = list(records)
        self.fail = fail
        self.calls: list[tuple] = []
        self.closed = False

    def search(self, jql: str, *, fields: Any = None, all_pages: bool, limit: int, page_size: int = 50) -> list[Any]:
        assert fields is not None and "description" not in fields and "summary" in fields  # list fields only
        assert page_size == 50
        self.calls.append(("search", jql, all_pages, limit))
        if self.fail is not None:
            raise self.fail
        return self.records[:limit]

    def get(self, key: str, *, comments: bool = False) -> Any:
        self.calls.append(("get", key, comments))
        if self.fail is not None:
            raise self.fail
        assert comments is True
        return self.records[0]

    def close(self) -> None:
        self.closed = True


def _stub(brain: Brain, monkeypatch, stub: StubHopper) -> StubHopper:
    monkeypatch.setattr(brain.jira, "open_hopper", lambda: stub)
    return stub


# -- jira live on replay ----------------------------------------------------------------
def test_live_fetches_the_recorded_search(seeded):
    before_audit = seeded.storage.audit_tail(10)
    result = seeded.execute("jira", action="live", jql=OPEN_JQL)
    assert result.ok, result.errors
    data = result.data
    assert data["count"] == 3 and data["truncated"] is False and data["jql"] == OPEN_JQL
    assert [i["key"] for i in data["issues"]] == OPEN_KEYS  # server order
    _assert_aware_utc(data["fetched_at"])
    for row in data["issues"]:
        assert tuple(row) == LIVE_FIELDS
        assert isinstance(row["labels"], list) and isinstance(row["components"], list)
    peer_review, step4, bug = data["issues"]
    assert peer_review["parent_key"] == "HWL-1915" and peer_review["status_category"] == "indeterminate"
    assert peer_review["issue_type"] == "Story" and peer_review["url"].endswith("/browse/HWL-2572")
    assert step4["status"] == "To Do" and step4["status_category"] == "new"
    assert bug["labels"] == ["VAT", "e-stop", "safety", "test-failure"] and bug["priority"] == "High"
    assert result.warnings == []
    # nothing written, one table, the event is the trace
    assert seeded.execute("count", entity=PLAN).data["count"] == 3
    assert seeded.storage.audit_tail(10) == before_audit
    assert _tables(seeded) == TABLES
    event = seeded.events.last(1)[0]
    assert event["topic"] == "jira.live" and event["count"] == 3 and event["truncated"] is False
    assert event["jql"] == OPEN_JQL and event["actor"] == "python" and event["fetched_at"] == data["fetched_at"]
    assert seeded.execute("status").data["recent_events"][-1]["topic"] == "jira.live"


def test_live_limit_and_truncation(brain):
    two = brain.execute("jira", action="live", jql=OPEN_JQL, limit=2)
    assert two.ok and two.data["count"] == 2 and two.data["truncated"] is True
    assert [i["key"] for i in two.data["issues"]] == OPEN_KEYS[:2]
    assert "truncated at 2" in two.warnings[0]
    assert brain.events.last(1)[0]["truncated"] is True
    three = brain.execute("jira", action="live", jql=OPEN_JQL, limit=3)
    assert three.ok and three.data["count"] == 3 and three.data["truncated"] is False and three.warnings == []
    zero = brain.execute("jira", action="live", jql=OPEN_JQL, limit=0)
    assert not zero.ok and "limit" in zero.errors[0]


def test_live_house_jql_has_no_fixture(brain):
    assert brain.jira.live_jql() == LIVE_JQL
    result = brain.execute("jira", action="live")
    assert not result.ok and result.errors[0].startswith("Jira read failed:")
    assert brain.execute("count", entity=PLAN).data["count"] == 0
    assert all(e["topic"] != "jira.live" for e in brain.events.last(10))


def test_live_jql_from_config(tmp_path, monkeypatch):
    config = tmp_path / "kletz.toml"
    config.write_text(f'jira_live_jql = "{OPEN_JQL}"\njira_live_autofetch = false\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "cfg.db", workbook_path=tmp_path / "v.xlsx", out_dir=tmp_path / "out") as brain:
        assert brain.jira.live_jql() == OPEN_JQL and brain.config["jira_live_autofetch"] is False
        result = brain.execute("jira", action="live")
        assert result.ok, result.errors
        assert result.data["count"] == 3 and result.data["jql"] == OPEN_JQL
        assert brain.jira.live_jql("project = X") == "project = X"  # --jql wins


def test_window_calls_replay_end_to_end(seeded):
    """What the two windows send, asserted here so the GUI tests stay free of the fixture."""
    live = seeded.execute("jira", action="live", jql=OPEN_JQL, actor="gui")
    assert live.ok and live.data["count"] == 3 and seeded.events.last(1)[0]["actor"] == "gui"
    comments = seeded.execute("jira", action="comments", key="HWL-2575", actor="gui")
    assert comments.ok and comments.data["key"] == "HWL-2575" and comments.data["comments"] == []
    assert seeded.execute("count", entity=PLAN).data["count"] == 3 and _tables(seeded) == TABLES


# -- the service with a stub ------------------------------------------------------------
def test_service_probes_one_past_the_limit(brain, monkeypatch):
    records = [Rec(key=f"HWL-{n}", summary=f"issue {n}", url=f"https://x/browse/HWL-{n}") for n in range(1, 8)]
    stub = _stub(brain, monkeypatch, StubHopper(records))
    data = brain.jira.live("project = X", 5)
    assert stub.calls == [("search", "project = X", True, 6)]
    assert data["truncated"] is True and data["count"] == 5 and stub.closed is True
    assert [i["key"] for i in data["issues"]] == [f"HWL-{n}" for n in range(1, 6)]

    exact = StubHopper(records[:5])
    data = brain.jira.live("project = X", 5, hopper=exact)
    assert data["truncated"] is False and data["count"] == 5 and exact.closed is False  # passed in, not closed

    with pytest.raises(Exception, match="at least 1"):
        brain.jira.live("project = X", 0, hopper=exact)


def test_live_row_maps_nulls_and_parents():
    bare = live_row(Rec(key="HWL-1", summary="s", url="u"))
    assert bare == {
        "key": "HWL-1", "issue_type": None, "summary": "s", "status": None, "status_category": None,
        "resolution": None, "priority": None, "assignee": None, "reporter": None, "labels": [], "components": [],
        "parent_key": None, "created": None, "updated": None, "due": None, "url": "u",
    }
    full = live_row(Rec(key="HWL-2", summary="t", url="v", labels=("a", "b"), components=("c",),
                        parent=SimpleNamespace(key="HWL-1"), status_category="done"))
    assert full["labels"] == ["a", "b"] and full["components"] == ["c"] and full["parent_key"] == "HWL-1"
    assert tuple(full) == LIVE_FIELDS


def test_auth_required_and_install_hint(brain, monkeypatch):
    from asi_hopper.errors import AuthRequired, GatewayError

    stub = _stub(brain, monkeypatch, StubHopper(fail=AuthRequired(LOGIN_HINT)))
    result = brain.execute("jira", action="live", jql="project = X")
    assert not result.ok and result.errors[0] == LOGIN_HINT and stub.closed is True

    _stub(brain, monkeypatch, StubHopper(fail=GatewayError("boom")))
    result = brain.execute("jira", action="live", jql="project = X")
    assert not result.ok and result.errors[0] == "Jira read failed: boom"

    monkeypatch.undo()  # the real open_hopper again
    monkeypatch.setitem(sys.modules, "asi_hopper", None)  # `from asi_hopper import Hopper` now raises ImportError
    result = brain.execute("jira", action="live", jql="project = X")
    assert not result.ok and result.errors[0] == INSTALL_HINT
    result = brain.execute("jira", action="comments", key="HWL-1")
    assert not result.ok and result.errors[0] == INSTALL_HINT


def test_verb_registration_and_schema(brain):
    assert not brain.execute("jira", action="sync").ok
    assert not brain.execute("jira", action="dance").ok
    assert not brain.execute("jira").ok  # action is required
    assert "jira" in default_command_factory.verbs()
    assert "jira" in brain.execute("status").data["commands"]
    signature = next(c for c in brain.execute("schema").data["commands"] if c["verb"] == "jira")
    by_name = {a["name"]: a for a in signature["arguments"]}
    assert list(by_name) == ["action", "key", "jql", "limit"]
    assert by_name["action"]["choices"] == ["live", "comments", "login"] and by_name["action"]["required"]
    assert by_name["key"]["flag"] is False
    assert by_name["limit"]["type"] == "int" and by_name["limit"]["default"] == LIVE_LIMIT == 2000
    assert by_name["jql"]["flag"] is True and LIVE_JQL in by_name["jql"]["help"]
    assert "jira" in build_parser().format_help()


# -- jira comments ------------------------------------------------------------------------
def test_comments_on_replay(seeded):
    before_audit = seeded.storage.audit_tail(10)
    before_events = seeded.events.last(1)
    result = seeded.execute("jira", action="comments", key="HWL-2575")
    assert result.ok, result.errors
    data = result.data
    assert data["key"] == "HWL-2575" and data["summary"].startswith("STPA Step 4")
    assert data["url"].endswith("/browse/HWL-2575") and isinstance(data["status"], str) and data["status"]
    assert data["count"] == 0 and data["comments"] == []
    _assert_aware_utc(data["fetched_at"])
    lower = seeded.execute("jira", action="comments", key="hwl-2575")
    assert lower.ok and lower.data["key"] == "HWL-2575"
    unknown = seeded.execute("jira", action="comments", key="HWL-1")
    assert not unknown.ok and unknown.errors[0].startswith("Jira read failed:")
    missing = seeded.execute("jira", action="comments")
    assert not missing.ok and "key" in missing.errors[0]
    assert seeded.execute("count", entity=PLAN).data["count"] == 3
    assert seeded.storage.audit_tail(10) == before_audit and _tables(seeded) == TABLES
    assert seeded.events.last(1) == before_events  # comments publishes nothing


def test_comments_newest_first_with_a_stub(brain, monkeypatch):
    from asi_hopper.errors import AuthRequired

    history = (
        Com("c1", "Ana", "a1", "2026-10-01T09:00:00.000-0600", "2026-10-01T09:00:00.000-0600", "first"),
        Com("c3", "Bo", "b1", "2026-10-03T09:00:00.000-0600", "2026-10-03T10:30:00.000-0600", "third, edited"),
        Com("c2", "Cy", "c1", "2026-10-02T09:00:00.000-0600", "2026-10-02T09:00:00.000-0600", None),
    )
    record = Rec(key="HWL-9", summary="Brakes", status="Done", url="https://x/browse/HWL-9", comments=history)
    stub = _stub(brain, monkeypatch, StubHopper([record]))
    result = brain.execute("jira", action="comments", key=" hwl-9 ")
    assert result.ok, result.errors
    assert stub.calls == [("get", "HWL-9", True)] and stub.closed is True
    data = result.data
    assert data["key"] == "HWL-9" and data["summary"] == "Brakes" and data["status"] == "Done" and data["count"] == 3
    assert [c["id"] for c in data["comments"]] == ["c3", "c2", "c1"]
    edited, empty, first = data["comments"]
    assert edited["updated"] == "2026-10-03T10:30:00.000-0600" and edited["created"] == "2026-10-03T09:00:00.000-0600"
    assert empty["body"] == "" and first["body"] == "first"
    assert all(set(c) == {"id", "author", "created", "updated", "body"} for c in data["comments"])

    _stub(brain, monkeypatch, StubHopper(fail=AuthRequired(LOGIN_HINT)))
    denied = brain.execute("jira", action="comments", key="HWL-9")
    assert not denied.ok and denied.errors[0] == LOGIN_HINT


def test_login_clears_the_session_then_signs_in_in_the_browser(brain, monkeypatch):
    """``jira login``: `auth logout` then `auth login` in one step, through one interactive Hopper."""
    import asi_hopper
    from asi_hopper.errors import AuthRequired, GatewayError

    events: list[str] = []

    class _Store:
        def clear(self) -> None:
            events.append("clear")

    class _Interactive:
        def __init__(self, *, fail: Exception | None = None) -> None:
            self.fail = fail

        def session_store(self):
            return _Store()

        def whoami(self):
            events.append("whoami")
            if self.fail is not None:
                raise self.fail
            return {"account_id": "a1", "display_name": "Roy Mendoza"}

        def close(self) -> None:
            events.append("close")

    made: list[dict] = []

    def hopper(**kwargs):
        made.append(kwargs)
        return _Interactive(fail=kwargs.pop("_fail", None))

    monkeypatch.setattr(asi_hopper, "Hopper", hopper)
    result = brain.execute("jira", action="login")
    assert result.ok and result.data["signed_in"] is True and result.data["account"]["account_id"] == "a1"
    assert made == [{"interactive": True}] and events == ["clear", "whoami", "close"]

    monkeypatch.setattr(asi_hopper, "Hopper", lambda **kw: _Interactive(fail=AuthRequired("the browser was closed")))
    result = brain.execute("jira", action="login")
    assert not result.ok and result.errors[0] == "Sign-in failed: the browser was closed"
    monkeypatch.setattr(asi_hopper, "Hopper", lambda **kw: _Interactive(fail=GatewayError("boom")))
    result = brain.execute("jira", action="login")
    assert not result.ok and result.errors[0] == "Sign-in failed: boom"
