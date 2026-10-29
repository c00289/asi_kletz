"""0.23.0, Phase B of the Confluence integration plan (asi_hopper/docs/confluence-integration-plan.md): the
``confluence`` verb and ``ConfluenceService`` against asi_hopper's replay fixtures, no network, no session, no
keyring, the way the jira tests run.

The recorded CQL set has no ``title ~`` search, so the suite copies Hopper's fixtures folder to a temporary one
and adds index entries whose ``args`` are exactly what the verb sends, aliased to the recorded STPA space search
(Hopper's own index does this: "same page; the server would filter"). Nothing is recorded into asi_hopper. The
fixtures hold page 399343803 with its two children and their comments, which is what ``page``, ``link``,
``evidence`` and ``check`` read; a stub Hopper covers the error classes, the escaping and the session probe. All
fixture text is synthetic."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from asi_kletz import Brain
from asi_kletz.automation.cli import build_parser
from asi_kletz.brain import ENV_CONFIG
from asi_kletz.commands import default_command_factory
from asi_kletz.generate.plan_queries import counts_by_link
from asi_kletz.services.confluence_service import (
    DEFAULT_SPACE,
    EVIDENCE_ACTION,
    EVIDENCE_EVENT,
    PAGE_FIELDS,
    SEARCH_FIELDS,
    SEARCH_LIMIT,
    ConfluenceService,
    cql_literal,
)
from asi_kletz.services.jira_service import INSTALL_HINT
from tests.conftest import PLAN, REAL_HAS_SESSION, REPO_ROOT, TABLES
from tests.test_cli import run

HOPPER_FIXTURES = REPO_ROOT.parent / "asi_hopper" / "tests" / "fixtures"
LOGIN_HINT = "no Atlassian session for this account; run `asi-hopper auth login` once"
PAGE = "399343803"  # the STPA page of the fixtures, version 45, two children
CHILD = "5763236170"  # version 9
CHILD2 = "5779062840"  # version 1
SITE = "https://asirobots.atlassian.net"
VIEW = f"{SITE}/wiki/pages/viewpage.action?pageId={PAGE}"  # the canonical URL Hopper gives a page
CHILD_VIEW = f"{SITE}/wiki/pages/viewpage.action?pageId={CHILD}"
WIKI = f"{SITE}/wiki/spaces/STPA/pages/{PAGE}/Locator+Safety+Function+STPA"  # the pretty URL of the same page
CHILD_WIKI = f"{SITE}/wiki/spaces/STPA/pages/{CHILD}/Low-precision+GPS"
OVERVIEW = f"{SITE}/wiki/spaces/STPA/overview"  # a Confluence URL that names no page
GONE = f"{SITE}/wiki/pages/viewpage.action?pageId=1"  # no fixture: the replay says so
MS = "https://www.microsoft.com/"
JAMA = "https://jama.example.com/items/2554"
STPA_HITS = ["262996144", "7629013406", "5791842487"]  # the recorded STPA space search, newest first
STPA_CQL = "space = STPA AND (title ~ \"Locator\" AND type = page) ORDER BY lastmodified DESC"

pytestmark = pytest.mark.skipif(
    not (HOPPER_FIXTURES / "index.json").is_file(), reason="asi_hopper fixtures are not checked out next to asi_kletz"
)


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory):
    """Hopper's fixtures copied, plus the aliases for the CQL this verb sends (limit 25, the default, and 3)."""
    root = tmp_path_factory.mktemp("hopper-fixtures")
    shutil.copytree(HOPPER_FIXTURES, root / "fixtures")
    index_path = root / "fixtures" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for limit in (SEARCH_LIMIT, 3):
        index.append({
            "tool": "searchConfluenceUsingCql", "args": {"cql": STPA_CQL, "limit": limit},
            "file": "searchConfluenceUsingCql_space_STPA.json",
            "note": "Kletz test alias: the recorded STPA space search; the server would filter on the title",
        })
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return root / "fixtures"


@pytest.fixture(autouse=True)
def _replay_hopper(monkeypatch, fixtures):
    """asi_hopper reads its gateway from the environment: point it at the copied fixtures."""
    monkeypatch.delenv("ASI_HOPPER_CONFIG", raising=False)
    monkeypatch.setenv("ASI_HOPPER_GATEWAY", "replay")
    monkeypatch.setenv("ASI_HOPPER_FIXTURES", str(fixtures))


# -- helpers --------------------------------------------------------------------------
def _tables(brain: Brain) -> set[str]:
    rows = brain.storage.fetchall("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return {r["name"] for r in rows} - {"schema_migrations", "audit_log"}


def _assert_aware_utc(text: str) -> None:
    parsed = dt.datetime.fromisoformat(text)
    assert parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0)


def _ref(page_id: str, title: str, **extra: Any) -> Any:
    from asi_hopper.model import PageRef

    return PageRef(id=page_id, title=title, space_key="STPA", url=f"{SITE}/wiki/spaces/STPA/pages/{page_id}/x",
                   last_modified="2026-10-01T00:00:00.000Z", **extra)


def _record(page_id: str, title: str, version: int = 1) -> Any:
    from asi_hopper.model import PageRecord

    return PageRecord(
        id=page_id, title=title, status="current", type="page", space_id="1", parent_id=None, parent_type=None,
        author_id=None, owner_id=None, created=None, updated="2026-10-01T00:00:00.000Z", version=version,
        version_message=None, version_author_id=None, body_format="markdown", body="# synthetic",
        url=f"{SITE}/wiki/pages/viewpage.action?pageId={page_id}",
    )


class StubHopper:
    """What the service reads from a Hopper: ``cql``, ``page``, ``evidence.snapshot_pages``, ``session_store``."""

    def __init__(self, *, refs: list[Any] = (), pages: dict[str, Any] | None = None, fail: Exception | None = None,
                 session: Any = False) -> None:
        self.refs = list(refs)
        self.pages = dict(pages or {})
        self.fail = fail
        self.session = session
        self.calls: list[tuple] = []
        self.closed = False
        self.evidence = SimpleNamespace(snapshot_pages=self._snapshot)

    def cql(self, cql: str, *, space: str | None = None, limit: int | None = None, page_size: int = 25) -> list[Any]:
        self.calls.append(("cql", cql, space, limit, page_size))
        if self.fail is not None:
            raise self.fail
        return self.refs[:limit]

    def page(self, page_id: str) -> Any:
        from asi_hopper.errors import NotFound

        self.calls.append(("page", page_id))
        if self.fail is not None:
            raise self.fail
        if page_id not in self.pages:
            raise NotFound(f"page {page_id} not found or not visible to this account")
        return self.pages[page_id]

    def _snapshot(self, source: Any, out_dir: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("snapshot", source, str(out_dir), kwargs))
        if self.fail is not None:
            raise self.fail
        raise AssertionError("the stub takes no evidence")

    def session_store(self) -> Any:
        if isinstance(self.session, Exception):
            raise self.session
        return SimpleNamespace(has_session=lambda: self.session)

    def close(self) -> None:
        self.closed = True


def _stub(brain: Brain, monkeypatch, stub: StubHopper) -> StubHopper:
    monkeypatch.setattr(brain.confluence, "open_hopper", lambda: stub)
    return stub


def _verify(folder: Any) -> dict[str, Any]:
    """Hopper's own check of a bundle, through the replay door."""
    from asi_hopper import Hopper

    with Hopper(interactive=False) as hopper:
        return hopper.evidence.verify(folder)


# -- search -----------------------------------------------------------------------------
def test_search_lists_the_pages_of_the_space_and_sends_one_cql(seeded, monkeypatch):
    before_audit = seeded.storage.audit_tail(10)
    before_events = seeded.events.last(1)
    result = seeded.execute("confluence", action="search", target="Locator")
    assert result.ok, result.errors
    data = result.data
    assert data["text"] == "Locator" and data["space"] == DEFAULT_SPACE == "STPA"
    assert data["limit"] == SEARCH_LIMIT == 25
    assert data["cql"] == 'title ~ "Locator" AND type = page ORDER BY lastmodified DESC'
    assert data["count"] == 3 and [p["id"] for p in data["pages"]] == STPA_HITS  # server order, newest first
    _assert_aware_utc(data["fetched_at"])
    for page in data["pages"]:
        assert tuple(page) == SEARCH_FIELDS and page["space_key"] == "STPA" and page["url"].startswith(f"{SITE}/wiki/")
    assert data["pages"][0]["title"] == "V2X to VCU STPA (Old Format)" and data["pages"][1]["excerpt"] is None
    assert result.warnings == []
    # a read: nothing written, nothing published, one table set as before
    assert seeded.storage.audit_tail(10) == before_audit and seeded.events.last(1) == before_events
    assert _tables(seeded) == TABLES and seeded.execute("count", entity=PLAN).data["count"] == 3
    three = seeded.execute("confluence", action="search", target=" Locator ", limit=3)
    assert three.ok and three.data["count"] == 3 and three.data["limit"] == 3 and three.data["text"] == "Locator"
    # what reaches Hopper: the escaped literal, the space, the limit as the page size; nothing on Rovo
    stub = _stub(seeded, monkeypatch, StubHopper(refs=[_ref("1", "A \"quoted\" title"), _ref("2", "B"),
                                                        _ref("3", "C", type="blogpost")]))
    result = seeded.execute("confluence", action="search", target='say "hi" \\ there', space="fst", limit=2)
    assert result.ok, result.errors
    assert stub.calls == [
        ("cql", 'title ~ "say \\"hi\\" \\\\ there" AND type = page ORDER BY lastmodified DESC', "FST", 2, 2)
    ]
    assert stub.closed is True and [p["id"] for p in result.data["pages"]] == ["1", "2"]  # pages only, the limit kept
    assert cql_literal('a"b') == '"a\\"b"' and cql_literal("plain") == '"plain"'
    assert seeded.execute("confluence", action="search").errors == [
        "confluence search needs <text>, part of a page title"
    ]
    assert seeded.execute("confluence", action="search", target="  ").errors[0].startswith("confluence search needs")
    assert seeded.execute("confluence", action="search", target="x", limit=0).errors == ["limit must be at least 1"]


# -- page ---------------------------------------------------------------------------------
def test_page_by_id_and_by_url_with_and_without_body(seeded):
    before_audit = seeded.storage.audit_tail(10)
    bare = seeded.execute("confluence", action="page", target=PAGE)
    assert bare.ok, bare.errors
    data = bare.data
    assert "body" not in data and "raw" not in data
    assert data["id"] == PAGE and data["title"] == "Locator Safety Function STPA" and data["version"] == 45
    assert data["url"] == VIEW and data["parent_id"] == "6051201086" and data["body_format"] == "markdown"
    assert data["updated"] == "2021-10-20T20:49:25.061Z" and data["status"] == "current"
    pretty = seeded.execute("confluence", action="page", target=WIKI)  # the pretty URL: the id is read off it
    assert pretty.ok and pretty.data == data
    view = seeded.execute("confluence", action="page", target=f" {VIEW} ")  # pageId=
    assert view.ok and view.data == data
    full = seeded.execute("confluence", action="page", target=CHILD, body=True)
    assert full.ok and full.data["id"] == CHILD and full.data["version"] == 9 and full.data["parent_id"] == PAGE
    assert isinstance(full.data["body"], str) and full.data["body"] and full.data["title"].startswith("Low-precision")
    assert {k: v for k, v in full.data.items() if k != "body"} == seeded.execute(
        "confluence", action="page", target=CHILD_WIKI).data
    assert seeded.execute("confluence", action="page").errors == ["confluence page needs <id-or-url>"]
    bad = seeded.execute("confluence", action="page", target="https://example.com/not-a-page")
    assert bad.errors == ["'https://example.com/not-a-page' is neither a page id nor a Confluence page URL "
                          "(pageId=<id> or /pages/<id>)"]
    gone = seeded.execute("confluence", action="page", target=GONE)
    assert not gone.ok and gone.errors[0].startswith("Confluence read failed:")
    assert seeded.storage.audit_tail(10) == before_audit  # reads leave no trace


# -- link ---------------------------------------------------------------------------------
def test_link_goes_through_the_guard_first_and_appended_and_refuses_what_it_must(seeded):
    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [MS]}).ok
    before = len(seeded.storage.audit_tail(50))
    result = seeded.execute("confluence", action="link", target="1", page=PAGE, actor="agent")
    assert result.ok and result.warnings == [], result.errors
    assert result.data["row"] == {"id": 1, "uid": seeded.execute("get", entity=PLAN, id=1).data["uid"], "order": 1,
                                  "deliverable": "Safety Plan"}
    assert result.data["page"] == {"id": PAGE, "title": "Locator Safety Function STPA", "version": 45,
                                   "updated": "2021-10-20T20:49:25.061Z", "url": VIEW}
    assert tuple(result.data["page"]) == PAGE_FIELDS
    assert result.data["urls"] == [MS, VIEW] and result.data["position"] == 2 and result.data["first"] is False
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [MS, VIEW]  # appended, the placeholder kept
    # the ordinary update path: the guard stored the JSON, the audit says update, the event fired
    entries = seeded.storage.audit_tail(50)
    assert len(entries) == before + 1 and entries[0]["action"] == "update" and entries[0]["entity"] == PLAN
    assert entries[0]["entity_id"] == 1 and entries[0]["actor"] == "agent"
    assert json.loads(entries[0]["payload"]["urls"]) == [MS, VIEW]
    event = seeded.events.last(1)[0]
    assert event["topic"] == "entity.updated" and event["id"] == 1 and event["actor"] == "agent"
    # the same page again, under its canonical URL: refused; under the pretty URL too: the same page id
    again = seeded.execute("confluence", action="link", target="1", page=PAGE)
    assert again.errors == [f"page {PAGE} is already on row 1 ({VIEW})"]
    assert seeded.execute("update", entity=PLAN, id=2, data={"urls": [WIKI]}).ok
    pretty = seeded.execute("confluence", action="link", target="2", page=VIEW)
    assert pretty.errors == [f"page {PAGE} is already on row 2 ({WIKI})"]
    assert seeded.execute("get", entity=PLAN, id=2).data["urls"] == [WIKI]
    # --first puts the page in front, as the link; the row may be a uid; the page may be a URL
    uid = seeded.execute("get", entity=PLAN, id=1).data["uid"]
    first = seeded.execute("confluence", action="link", target=uid, page=CHILD_WIKI, first=True)
    assert first.ok, first.errors
    assert first.data["urls"] == [CHILD_VIEW, MS, VIEW] and first.data["position"] == 1 and first.data["first"] is True
    assert first.data["page"]["id"] == CHILD and first.data["page"]["version"] == 9 and first.data["row"]["id"] == 1
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [CHILD_VIEW, MS, VIEW]
    # a row with no URLs yet gets the page as its first and only one
    third = seeded.execute("confluence", action="link", target="3", page=CHILD2)
    assert third.ok and third.data["urls"] == [f"{SITE}/wiki/pages/viewpage.action?pageId={CHILD2}"]
    assert third.data["position"] == 1 and third.data["page"]["version"] == 1
    # the refusals: an unknown row, an unknown page, a page URL that names no page, missing arguments
    unknown = seeded.execute("confluence", action="link", target="99", page=PAGE)
    assert unknown.errors == ["safety_plan_row 99 not found"]
    gone = seeded.execute("confluence", action="link", target="1", page=GONE)
    assert not gone.ok and gone.errors[0].startswith("Confluence read failed:")
    assert seeded.execute("confluence", action="link", target="1", page=OVERVIEW).errors[0].endswith(
        "is neither a page id nor a Confluence page URL (pageId=<id> or /pages/<id>)")
    assert seeded.execute("confluence", action="link", target="1").errors == ["confluence link needs <row> <id-or-url>"]
    assert seeded.execute("confluence", action="link", page=PAGE).errors == ["confluence link needs <row> <id-or-url>"]
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [CHILD_VIEW, MS, VIEW]  # a refusal changes nothing
    assert seeded.execute("plan", action="urls", audit=True, rows=["1"]).data[0]["code"] == "placeholder"  # still there


# -- evidence -----------------------------------------------------------------------------
def test_evidence_writes_a_bundle_hopper_verifies_audits_once_and_publishes(seeded, tmp_path):
    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [VIEW]}).ok
    assert seeded.execute("update", entity=PLAN, id=2, data={"urls": [MS, CHILD_WIKI, JAMA]}).ok
    assert seeded.execute("update", entity=PLAN, id=3, data={"urls": [MS]}).ok  # no page: contributes nothing
    before = len(seeded.storage.audit_tail(50))
    result = seeded.execute("confluence", action="evidence", out=str(tmp_path / "proof"), name="stpa-pages",
                            comments=True, actor="agent")
    assert result.ok and result.warnings == [], result.errors
    data = result.data
    folder = tmp_path / "proof" / "stpa-pages"
    assert data["folder"] == str(folder) and folder.is_dir()
    assert data["kind"] == "confluence" and data["source"] == {"kind": "pages", "ids": [PAGE, CHILD]}  # plan order
    assert data["comments"] is True and data["count"] == 2
    assert [(p["id"], p["version"]) for p in data["pages"]] == [(PAGE, 45), (CHILD, 9)]
    assert data["rows"] == [
        {"id": 1, "uid": seeded.execute("get", entity=PLAN, id=1).data["uid"], "order": 1, "deliverable": "Safety Plan",
         "pages": [PAGE], "urls": {PAGE: VIEW}},
        {"id": 2, "uid": seeded.execute("get", entity=PLAN, id=2).data["uid"], "order": 2,
         "deliverable": "Hazard Analysis and Risk Assessment", "pages": [CHILD], "urls": {CHILD: CHILD_WIKI}},
    ]
    assert {p.name for p in folder.iterdir()} == {"manifest.json", "pages.json", "pages.csv", "pages.md", "pages"}
    assert {p.name for p in (folder / "pages").iterdir()} == {f"{PAGE}.md", f"{CHILD}.md"}
    entries = json.loads((folder / "pages.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in entries] == [PAGE, CHILD] and entries[0]["comment_count"] > 0 and "body" not in entries[0]
    assert (folder / "pages" / f"{PAGE}.md").read_text(encoding="utf-8").startswith("Related Links:")
    verified = _verify(folder)  # Hopper's own check, through its replay door
    assert verified["intact"] is True and verified["kind"] == "confluence" and len(verified["files"]) == 3
    # one audit entry for the whole bundle, the event, and no page text anywhere in Kletz
    audit = seeded.storage.audit_tail(50)
    assert len(audit) == before + 1 and audit[0]["action"] == EVIDENCE_ACTION == "confluence_evidence"
    assert audit[0]["entity"] == PLAN and audit[0]["entity_id"] is None and audit[0]["actor"] == "agent"
    payload = audit[0]["payload"]
    assert payload["folder"] == str(folder) and payload["pages"] == [PAGE, CHILD] and payload["comments"] is True
    assert payload["rows"] == [{"id": 1, "pages": [PAGE]}, {"id": 2, "pages": [CHILD]}]
    assert payload["taken_at"] == data["taken_at"] and payload["versions"] == {PAGE: 45, CHILD: 9}
    event = seeded.events.last(1)[0]
    assert event["topic"] == EVIDENCE_EVENT == "plan.confluence_evidence" and event["folder"] == str(folder)
    assert event["pages"] == 2 and event["rows"] == 2 and event["actor"] == "agent"
    db_bytes = (seeded.db_path and open(seeded.db_path, "rb").read())
    assert b"HAZARD FOCUS" not in db_bytes and b"Related Links" not in db_bytes
    assert _tables(seeded) == TABLES and seeded.execute("count", entity=PLAN).data["count"] == 3
    # the default folder is the Kletz evidence folder beside the database, the default name dated by Hopper
    default = seeded.execute("confluence", action="evidence", rows=["2"])
    assert default.ok, default.errors
    assert default.data["source"]["ids"] == [CHILD] and default.data["comments"] is False
    assert default.data["folder"].startswith(seeded.evidence_dir) and seeded.evidence_dir.endswith("evidence")
    assert default.data["folder"].endswith(f"safety-plan-work-products-{dt.date.today():%Y-%m-%d}")
    assert _verify(default.data["folder"])["intact"] is True
    assert len(default.data["rows"]) == 1 and default.data["rows"][0]["id"] == 2
    # a selection without a page is refused; an unknown row too; a page URL that names no page is a warning
    none = seeded.execute("confluence", action="evidence", rows=["3"])
    assert none.errors == ["no Confluence page URL on the chosen rows; link one first (confluence link)"]
    assert seeded.execute("confluence", action="evidence", rows=["42"]).errors == ["no plan row 42"]
    assert seeded.execute("update", entity=PLAN, id=3, data={"urls": [OVERVIEW, VIEW]}).ok
    warned = seeded.execute("confluence", action="evidence", rows=["3"], out=str(tmp_path / "more"))
    assert warned.ok and warned.warnings == [f"row 3: {OVERVIEW} names no page id; skipped"]
    assert warned.data["source"]["ids"] == [PAGE]
    assert len([a for a in seeded.storage.audit_tail(50) if a["action"] == EVIDENCE_ACTION]) == 3


# -- check --------------------------------------------------------------------------------
def test_check_with_and_without_earlier_evidence(seeded, tmp_path):
    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [VIEW, MS]}).ok
    assert seeded.execute("update", entity=PLAN, id=2, data={"urls": [CHILD_WIKI]}).ok
    before_audit = seeded.storage.audit_tail(10)
    result = seeded.execute("confluence", action="check")
    assert result.ok and result.warnings == [], result.errors
    _assert_aware_utc(result.data["fetched_at"])
    assert result.data["count"] == 2
    first, second = result.data["pages"]
    assert first == {
        "row": 1, "uid": seeded.execute("get", entity=PLAN, id=1).data["uid"], "order": 1, "deliverable": "Safety Plan",
        "id": PAGE, "title": "Locator Safety Function STPA", "version": 45, "updated": "2021-10-20T20:49:25.061Z",
        "url": VIEW, "last_evidence": None, "moved": None, "error": None,
    }
    assert second["row"] == 2 and second["id"] == CHILD and second["version"] == 9 and second["last_evidence"] is None
    assert seeded.storage.audit_tail(10) == before_audit  # read only
    # a bundle of row 1 alone: its page knows its evidence, the other still does not
    taken = seeded.execute("confluence", action="evidence", rows=["1"], out=str(tmp_path / "e"), name="one")
    assert taken.ok, taken.errors
    folder = tmp_path / "e" / "one"
    result = seeded.execute("confluence", action="check")
    first, second = result.data["pages"]
    assert first["last_evidence"] == {"folder": str(folder), "taken_at": taken.data["taken_at"], "version": 45}
    assert first["moved"] is False and second["last_evidence"] is None and second["moved"] is None
    # the manifest says an older version: the page moved since; the newest bundle wins when there are several
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"][0]["version"] = 44
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    moved = seeded.execute("confluence", action="check", rows=["1"]).data["pages"][0]
    assert moved["moved"] is True and moved["last_evidence"]["version"] == 44
    newer = seeded.execute("confluence", action="evidence", rows=["1", "2"], out=str(tmp_path / "e"), name="two")
    assert newer.ok
    both = seeded.execute("confluence", action="check").data["pages"]
    assert [p["last_evidence"]["folder"] for p in both] == [str(tmp_path / "e" / "two")] * 2
    assert [p["moved"] for p in both] == [False, False]
    # the folder is gone: the audit entry still names it and carries the version it recorded
    shutil.rmtree(tmp_path / "e" / "two")
    gone = seeded.execute("confluence", action="check", rows=["2"]).data["pages"][0]
    assert gone["last_evidence"] == {"folder": str(tmp_path / "e" / "two"), "taken_at": newer.data["taken_at"],
                                     "version": 9} and gone["moved"] is False
    # a page that cannot be read stays in the report with its error; a URL naming no page is a warning
    assert seeded.execute("update", entity=PLAN, id=3, data={"urls": [OVERVIEW, GONE]}).ok
    result = seeded.execute("confluence", action="check", rows=["3"])
    assert result.ok and result.warnings == [f"row 3: {OVERVIEW} names no page id; skipped"]
    (missing,) = result.data["pages"]
    assert missing["id"] == "1" and missing["title"] is None and missing["version"] is None and missing["url"] == GONE
    assert missing["error"].startswith("Confluence read failed:") and missing["moved"] is None
    assert seeded.execute("confluence", action="check", rows=["42"]).errors == ["no plan row 42"]


# -- the door's refusals --------------------------------------------------------------------
def test_auth_required_is_one_line_everywhere_and_the_install_hint(seeded, monkeypatch, tmp_path):
    from asi_hopper.errors import AuthRequired, GatewayError

    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [VIEW]}).ok
    stub = _stub(seeded, monkeypatch, StubHopper(fail=AuthRequired(LOGIN_HINT)))
    for args in (
        {"action": "search", "target": "x"}, {"action": "page", "target": PAGE},
        {"action": "link", "target": "1", "page": CHILD}, {"action": "check"},
        {"action": "evidence", "out": str(tmp_path)},
    ):
        result = seeded.execute("confluence", **args)
        assert not result.ok and result.errors == [LOGIN_HINT], args
    assert stub.closed is True
    assert seeded.execute("get", entity=PLAN, id=1).data["urls"] == [VIEW]  # the refused link changed nothing
    assert all(a["action"] != EVIDENCE_ACTION for a in seeded.storage.audit_tail(50))  # no bundle, no entry
    _stub(seeded, monkeypatch, StubHopper(fail=GatewayError("boom")))
    assert seeded.execute("confluence", action="search", target="x").errors == ["Confluence read failed: boom"]
    assert seeded.execute("confluence", action="page", target=PAGE).errors == ["Confluence read failed: boom"]
    # a check keeps going past a page it cannot read, but a rejected session stops it: one line
    pages = seeded.execute("confluence", action="check").data["pages"]
    assert pages[0]["error"] == "Confluence read failed: boom" and pages[0]["title"] is None
    monkeypatch.undo()
    monkeypatch.setitem(sys.modules, "asi_hopper", None)  # `from asi_hopper import Hopper` now raises ImportError
    assert seeded.execute("confluence", action="search", target="x").errors == [INSTALL_HINT]
    assert seeded.execute("confluence", action="page", target=PAGE).errors == [INSTALL_HINT]


def test_has_session_reads_the_stored_token_locally_and_never_raises(brain, monkeypatch):
    monkeypatch.setattr(ConfluenceService, "has_session", REAL_HAS_SESSION)  # the suite's autouse stub undone
    yes = _stub(brain, monkeypatch, StubHopper(session=True))
    assert brain.confluence.has_session() is True and yes.closed is True and yes.calls == []  # nothing fetched
    no = _stub(brain, monkeypatch, StubHopper(session=False))
    assert brain.confluence.has_session() is False and no.closed is True
    broken = _stub(brain, monkeypatch, StubHopper(session=RuntimeError("no keyring")))
    assert brain.confluence.has_session() is False and broken.closed is True
    monkeypatch.setattr(brain.confluence, "open_hopper", lambda: (_ for _ in ()).throw(RuntimeError("no toml")))
    assert brain.confluence.has_session() is False
    monkeypatch.setitem(sys.modules, "asi_hopper", None)
    monkeypatch.undo()
    monkeypatch.setattr(ConfluenceService, "has_session", REAL_HAS_SESSION)
    monkeypatch.setitem(sys.modules, "asi_hopper", None)
    assert brain.confluence.has_session() is False  # asi_hopper missing: a probe, not an error


# -- configuration ------------------------------------------------------------------------------
def test_the_space_and_the_evidence_folder_come_from_kletz_toml(tmp_path, monkeypatch):
    config = tmp_path / "kletz.toml"
    config.write_text('evidence_dir = "proof"\n\n[confluence]\nspace = " fst "\n', encoding="utf-8")
    monkeypatch.setenv(ENV_CONFIG, str(config))
    with Brain(tmp_path / "cfg.db", workbook_path=tmp_path / "v.xlsx", out_dir=tmp_path / "out") as brain:
        assert brain.confluence.space == "FST" and brain.confluence_space == "FST"
        assert brain.evidence_dir == str((tmp_path / "proof").resolve()) and brain.config_warnings == []
        status = brain.execute("status").data
        assert status["evidence_dir"] == brain.evidence_dir and status["confluence_space"] == "FST"
        stub = _stub(brain, monkeypatch, StubHopper(refs=[_ref("1", "A")]))
        assert brain.execute("confluence", action="search", target="A").data["space"] == "FST"
        assert stub.calls[0][2] == "FST"
        assert brain.execute("confluence", action="search", target="A", space="stpa").data["space"] == "STPA"
    config.write_text("[confluence]\nspace = 7\n", encoding="utf-8")
    with Brain(tmp_path / "cfg2.db", workbook_path=tmp_path / "v.xlsx", out_dir=tmp_path / "out") as brain:
        assert brain.confluence.space == DEFAULT_SPACE  # a bad value: the default, and a warning status reports
        assert brain.config_warnings == [
            '[confluence] space = 7 in kletz.toml is ignored: write a space key such as "STPA"'
        ]
        assert brain.evidence_dir == str(tmp_path / "evidence")  # beside the database


def test_counts_by_link_for_the_dashboard_tile(seeded):
    assert counts_by_link(seeded) == {"confluence": 0, "placeholder": 0, "none": 3, "total": 3}
    assert seeded.execute("update", entity=PLAN, id=1, data={"urls": [VIEW]}).ok
    assert seeded.execute("update", entity=PLAN, id=2, data={"urls": [MS, WIKI]}).ok  # counts under both
    assert counts_by_link(seeded) == {"confluence": 2, "placeholder": 1, "none": 1, "total": 3}
    assert counts_by_link(seeded, rows=[{"urls": [JAMA]}]) == {"confluence": 0, "placeholder": 0, "none": 0, "total": 1}


# -- the verb in its three forms ----------------------------------------------------------------
def test_verb_registration_schema_wire_format_and_cli(seeded, tmp_path, capsys):
    assert not seeded.execute("confluence", action="snapshot").ok  # no write-shaped action exists
    assert not seeded.execute("confluence").ok  # action is required
    assert "confluence" in default_command_factory.verbs() and "confluence" in seeded.execute("status").data["commands"]
    signature = next(c for c in seeded.execute("schema").data["commands"] if c["verb"] == "confluence")
    by_name = {a["name"]: a for a in signature["arguments"]}
    assert list(by_name) == ["action", "target", "page", "space", "limit", "body", "first", "rows", "comments", "out",
                             "name"]
    assert by_name["action"]["choices"] == ["search", "page", "link", "evidence", "check"]
    assert by_name["action"]["required"] is True
    assert by_name["target"]["flag"] is False and by_name["page"]["flag"] is False
    assert by_name["rows"]["multiple"] is True and by_name["rows"]["type"] == "ref" and by_name["rows"]["flag"] is True
    assert by_name["body"]["type"] == by_name["first"]["type"] == by_name["comments"]["type"] == "bool"
    assert by_name["out"]["type"] == "path" and "STPA" in by_name["space"]["help"]
    assert "confluence" in build_parser().format_help()
    # the wire format, as an agent sends it
    wired = seeded.execute_dict({"verb": "confluence", "args": {"action": "link", "target": "1", "page": PAGE},
                                 "actor": "claude"})
    assert wired.ok and wired.data["urls"] == [VIEW] and seeded.storage.audit_tail(1)[0]["actor"] == "claude"
    wired = seeded.execute_dict({"verb": "confluence", "args": {"action": "check", "rows": ["1"]}})
    assert wired.ok and wired.data["pages"][0]["version"] == 45
    # the CLI, end to end on its own database
    db = str(tmp_path / "cli.db")
    code, res = run(capsys, "--db", db, "create", PLAN, "--set", "deliverable=STPA step 2", "--set", "order=1")
    assert code == 0 and res["ok"]
    code, res = run(capsys, "--db", db, "confluence", "search", "Locator", "--limit", "3")
    assert code == 0 and res["data"]["count"] == 3 and res["data"]["limit"] == 3
    code, res = run(capsys, "--db", db, "confluence", "page", WIKI)
    assert code == 0 and res["data"]["version"] == 45 and "body" not in res["data"]
    code, res = run(capsys, "--db", db, "confluence", "page", PAGE, "--body")
    assert code == 0 and res["data"]["body"].startswith("Related Links:")
    code, res = run(capsys, "--db", db, "confluence", "link", "1", PAGE)
    assert code == 0 and res["data"]["urls"] == [VIEW] and res["data"]["position"] == 1
    code, res = run(capsys, "--db", db, "confluence", "link", "1", CHILD, "--first")
    assert code == 0 and res["data"]["urls"] == [CHILD_VIEW, VIEW] and res["data"]["first"] is True
    code, res = run(capsys, "--db", db, "confluence", "link", "1", CHILD)
    assert code == 1 and res["errors"] == [f"page {CHILD} is already on row 1 ({CHILD_VIEW})"]
    code, res = run(capsys, "--db", db, "confluence", "evidence", "--rows", "1", "--out", str(tmp_path / "ev"),
                    "--name", "cli", "--comments")
    assert code == 0 and res["data"]["source"]["ids"] == [CHILD, PAGE] and res["data"]["comments"] is True
    assert _verify(tmp_path / "ev" / "cli")["intact"] is True
    code, res = run(capsys, "--db", db, "confluence", "check", "--rows", "1")
    assert code == 0 and [p["moved"] for p in res["data"]["pages"]] == [False, False]
    assert res["data"]["pages"][0]["last_evidence"]["folder"] == str(tmp_path / "ev" / "cli")
    code, res = run(capsys, "--db", db, "confluence", "check", "--rows", "7")
    assert code == 1 and res["errors"] == ["no plan row 7"]
