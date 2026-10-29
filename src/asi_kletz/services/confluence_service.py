"""ConfluenceService: a read-only door to Confluence through asi_hopper (0.23.0, Phase B of the Confluence
integration plan, ``asi_hopper/docs/confluence-integration-plan.md``).

The owner, 2026-10-29: "when we add confluence read only into kletz we should be able to associate objects
with [confluence] urls". The association is the plan row's ``urls`` list, as 0.20.0 designed it; nothing here
adds a column. ``search`` finds pages by title (CQL ``title ~``, one space, never Rovo), ``page`` reads one,
``link`` appends a page's canonical URL to a row through the ordinary update path (the guard, the audit and the
event apply), ``evidence`` writes a Hopper page bundle for every Confluence URL of the chosen rows into the Kletz
evidence folder and audits it once, ``check`` says whether every linked page is still there, what version it is
and whether it moved since the last bundle. Nothing is written to Confluence, ever, and no page text enters
Kletz: the bundle is Hopper's, verifiable with ``asi-hopper verify``.

Every import of ``asi_hopper`` is inside a function, so ``import asi_kletz`` and ``Brain(":memory:")`` never
load it (the rule the generators and ``JiraService`` follow). Kletz imports ``Hopper``, the records,
``PageSource``, ``page_id_of`` and the error classes, never ``asi_hopper.gateway``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..generate import plan_queries as pq
from ..schema.urls import urls_json, urls_of
from .jira_service import INSTALL_HINT, _now

if TYPE_CHECKING:
    from ..brain import Brain

PLAN = pq.PLAN_ENTITY
DEFAULT_SPACE = "STPA"  # the STPA space holds the analyses the deliverables point at
SEARCH_LIMIT = 25  # Hopper's own page size; the server caps a page at 250
EVIDENCE_ACTION = "confluence_evidence"  # the audit log's action, one entry per bundle
EVIDENCE_EVENT = "plan.confluence_evidence"
EVIDENCE_TITLE = "Safety Plan work products"  # the bundle folder's default stem (slugged, dated by Hopper)
SEARCH_FIELDS = ("id", "title", "space_key", "url", "last_modified", "excerpt")
PAGE_FIELDS = ("id", "title", "version", "updated", "url")


def search_row(ref: Any) -> dict[str, Any]:
    """An asi_hopper PageRef -> the row of ``confluence search``."""
    return {name: getattr(ref, name, None) for name in SEARCH_FIELDS}


def page_summary(record: Any) -> dict[str, Any]:
    """The five facts of a page that ``link`` and ``check`` answer with: never the body."""
    return {name: getattr(record, name, None) for name in PAGE_FIELDS}


def cql_literal(text: str) -> str:
    """``text`` as a CQL string literal: backslashes and double quotes escaped, in double quotes."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class ConfluenceService:
    """Reads only. Writes Kletz's own database alone: a row's ``urls`` (``link``) and one audit entry per
    bundle (``evidence``)."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- the door -------------------------------------------------------------------------------------
    def open_hopper(self) -> Any:
        """A read-only, non-interactive Hopper. A missing session is reported, never a browser."""
        try:
            from asi_hopper import Hopper
        except ImportError:
            raise CommandError(INSTALL_HINT) from None
        return Hopper(interactive=False)

    def has_session(self) -> bool:
        """Whether Hopper holds an Atlassian session on this machine: the stored token, read locally; nothing
        connects. The window greys **Find page** on ``False``. Any failure (asi_hopper missing, no keyring, a
        broken hopper.toml) is ``False``."""
        try:
            hopper = self.open_hopper()
        except Exception:  # noqa: BLE001  (a probe never raises)
            return False
        try:
            return bool(hopper.session_store().has_session())
        except Exception:  # noqa: BLE001
            return False
        finally:
            hopper.close()

    @property
    def space(self) -> str:
        """The space ``search`` looks in when none is given: ``[confluence] space`` in kletz.toml, else STPA."""
        return str(getattr(self.brain, "confluence_space", "") or DEFAULT_SPACE).strip().upper() or DEFAULT_SPACE

    @staticmethod
    def page_id(ref: Any) -> str:
        """The page id behind ``ref``: digits as they are, else the id a Confluence page URL names
        (``pageId=<id>`` or ``/pages/<id>``), else a ``CommandError``."""
        text = str(ref or "").strip()
        if not text:
            raise CommandError("a page id or a Confluence page URL is needed")
        if text.isdigit():
            return text
        from asi_hopper.model import page_id_of  # lazy: ``import asi_kletz`` never loads asi_hopper

        page_id = page_id_of(text)
        if not page_id:
            raise CommandError(f"{text!r} is neither a page id nor a Confluence page URL (pageId=<id> or /pages/<id>)")
        return page_id

    # -- search and page ------------------------------------------------------------------------------
    def search(
        self, text: str | None, space: str | None = None, limit: int | None = None, *, hopper: Any = None
    ) -> dict[str, Any]:
        """The pages of one space whose title contains ``text``, newest change first: one CQL (``title ~``, the
        text escaped, pages only), never Rovo. Nothing is stored."""
        needle = " ".join(str(text or "").split())
        if not needle:
            raise CommandError("confluence search needs <text>, part of a page title")
        limit = SEARCH_LIMIT if limit is None else int(limit)
        if limit < 1:
            raise CommandError("limit must be at least 1")
        key = (space or self.space).strip().upper()
        cql = f"title ~ {cql_literal(needle)} AND type = page ORDER BY lastmodified DESC"
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            refs = self._guard(lambda: hopper.cql(cql, space=key, limit=limit, page_size=min(limit, 250)))
        finally:
            if own:
                hopper.close()
        pages = [search_row(r) for r in refs if getattr(r, "type", "page") == "page"]
        return {"text": needle, "cql": cql, "space": key, "limit": limit, "fetched_at": _now(),
                "count": len(pages), "pages": pages}

    def page(self, ref: Any, *, body: bool = False, hopper: Any = None) -> dict[str, Any]:
        """One page's record (title, version, updated, url, parent...), the Markdown body only when asked."""
        page_id = self.page_id(ref)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            record = self._guard(lambda: hopper.page(page_id))
        finally:
            if own:
                hopper.close()
        data = record.to_dict()
        if not body:
            data.pop("body", None)
        return data

    # -- link -----------------------------------------------------------------------------------------
    def link(
        self, row_ref: Any, page_ref: Any, *, first: bool = False, actor: str = "python", hopper: Any = None
    ) -> dict[str, Any]:
        """The page's canonical URL appended to the row's ``urls`` (first with ``first``), through
        ``EntityService.update``: the guard parses, the audit records an update, ``entity.updated`` fires. The
        page must exist and be visible (``hopper.page``); a page already on the row, under any URL form, is
        refused."""
        service = self.brain.service(PLAN)
        row = service.get(row_ref)
        page_id = self.page_id(page_ref)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            record = self._guard(lambda: hopper.page(page_id))
        finally:
            if own:
                hopper.close()
        urls = urls_of(row.get("urls"))
        for url in urls:
            if url == record.url or (self._is_confluence(url) and self._page_id_or_none(url) == record.id):
                raise CommandError(f"page {record.id} is already on row {row['id']} ({url})")
        new_urls = [record.url, *urls] if first else [*urls, record.url]
        updated, warnings = service.update(row["id"], {"urls": urls_json(new_urls)}, actor)
        stored = urls_of(updated.get("urls"))
        return {
            "row": self._row_facts(updated), "page": page_summary(record), "urls": stored,
            "position": stored.index(record.url) + 1 if record.url in stored else None, "first": bool(first),
            "warnings": list(warnings),
        }

    # -- evidence and check ---------------------------------------------------------------------------
    def evidence(
        self, rows: list[Any] | None = None, *, comments: bool = False, out: str | Path | None = None,
        name: str | None = None, actor: str = "python", hopper: Any = None,
    ) -> dict[str, Any]:
        """A Hopper page bundle of every Confluence page the chosen rows (default all) point at, written under
        the Kletz evidence folder (``out``, else ``evidence_dir``); the answer is the manifest plus ``rows``
        (which rows contributed which page ids). One audit entry (``confluence_evidence``: the folder, the page
        ids, the rows, the time, the versions) and the event ``plan.confluence_evidence``. No page text is
        stored in Kletz: the bundle is the evidence, ``asi-hopper verify`` checks it."""
        contributions, pages, warnings = self._collect(rows)
        if not pages:
            raise CommandError("no Confluence page URL on the chosen rows; link one first (confluence link)")
        folder = Path(out) if out else Path(self.brain.evidence_dir)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        try:
            from asi_hopper.services.evidence import PageSource  # lazy

            source = PageSource(kind="pages", ids=tuple(pages))
            manifest = self._guard(
                lambda: hopper.evidence.snapshot_pages(
                    source, folder, name=name or None, comments=bool(comments), title=EVIDENCE_TITLE
                )
            )
        finally:
            if own:
                hopper.close()
        versions = {str(p["id"]): p.get("version") for p in manifest.get("pages") or []}
        payload = {
            "folder": manifest["folder"], "pages": pages,
            "rows": [{"id": c["id"], "pages": c["pages"]} for c in contributions],
            "taken_at": manifest.get("taken_at"), "versions": versions, "comments": bool(comments),
        }
        with self.brain.storage.transaction():
            self.brain.storage.audit(actor, EVIDENCE_ACTION, PLAN, None, payload)
        self.brain.events.publish(
            EVIDENCE_EVENT, folder=manifest["folder"], pages=len(pages), rows=len(contributions), actor=actor
        )
        return {**manifest, "rows": contributions, "warnings": warnings}

    def check(self, rows: list[Any] | None = None, *, hopper: Any = None) -> dict[str, Any]:
        """For every Confluence URL on the chosen rows: is the page still there and what version is it
        (``hopper.page``, the body dropped); ``last_evidence`` names the latest bundle that holds the page
        (from the audit log, the manifest read when the folder still exists) and ``moved`` whether the version
        differs from it (``None`` without a bundle). Read only, a report; a page that cannot be read carries
        its ``error`` and stays in the list."""
        contributions, pages, warnings = self._collect(rows)
        own = hopper is None
        hopper = hopper or self.open_hopper()
        records: dict[str, Any] = {}
        errors: dict[str, str] = {}
        try:
            for page_id in pages:
                try:
                    records[page_id] = self._guard(lambda page_id=page_id: hopper.page(page_id))
                except CommandError as exc:
                    if self._is_auth(exc):
                        raise
                    errors[page_id] = str(exc)
        finally:
            if own:
                hopper.close()
        out: list[dict[str, Any]] = []
        for row in contributions:
            for page_id in row["pages"]:
                record = records.get(page_id)
                facts = page_summary(record) if record is not None else dict.fromkeys(PAGE_FIELDS)
                facts["id"] = page_id
                if record is None:
                    facts["url"] = row["urls"].get(page_id)
                last = self.last_evidence(page_id)
                version = facts.get("version")
                moved = None
                if last is not None and last.get("version") is not None and version is not None:
                    moved = version != last["version"]
                out.append({
                    "row": row["id"], "uid": row["uid"], "order": row["order"], "deliverable": row["deliverable"],
                    **facts, "last_evidence": last, "moved": moved, "error": errors.get(page_id),
                })
        return {"fetched_at": _now(), "count": len(out), "pages": out, "warnings": warnings}

    def last_evidence(self, page_id: str) -> dict[str, Any] | None:
        """The most recent ``confluence_evidence`` audit entry naming ``page_id``: ``{folder, taken_at,
        version}``, the version and the time read from the folder's ``manifest.json`` when it still exists,
        else from the entry itself; ``None`` when no bundle holds the page."""
        wanted = str(page_id)
        entries = self.brain.storage.fetchall(
            "SELECT ts, payload FROM audit_log WHERE action = ? ORDER BY id DESC", (EVIDENCE_ACTION,)
        )
        for entry in entries:
            try:
                payload = json.loads(entry.get("payload") or "{}")
            except ValueError:
                continue
            if wanted not in [str(p) for p in payload.get("pages") or []]:
                continue
            folder = str(payload.get("folder") or "")
            taken_at = payload.get("taken_at") or entry.get("ts")
            version = (payload.get("versions") or {}).get(wanted)
            manifest_path = Path(folder) / "manifest.json" if folder else None
            if manifest_path is not None and manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except ValueError:
                    manifest = {}
                taken_at = manifest.get("taken_at") or taken_at
                for page in manifest.get("pages") or []:
                    if str(page.get("id")) == wanted:
                        version = page.get("version")
            return {"folder": folder, "taken_at": taken_at, "version": version}
        return None

    # -- helpers --------------------------------------------------------------------------------------
    def _is_confluence(self, url: str) -> bool:
        return self.brain.work_products.kind(url) == "confluence"

    @staticmethod
    def _page_id_or_none(url: str) -> str | None:
        from asi_hopper.model import page_id_of  # lazy

        return page_id_of(url)

    @staticmethod
    def _row_facts(row: dict[str, Any]) -> dict[str, Any]:
        return {"id": row["id"], "uid": row.get("uid"), "order": row.get("order"),
                "deliverable": pq.one_line(row.get("deliverable") or "", 60)}

    def _collect(self, rows: list[Any] | None) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        """The rows (default all) that carry a Confluence page URL, each with its page ids in URL order, the
        page ids over all of them (each once, in plan order) and the warnings (a Confluence URL that names no
        page id is skipped)."""
        contributions: list[dict[str, Any]] = []
        pages: list[str] = []
        warnings: list[str] = []
        for row in self.brain.work_products.rows(rows):
            ids: list[str] = []
            by_id: dict[str, str] = {}
            for url in urls_of(row.get("urls")):
                if not self._is_confluence(url):
                    continue
                page_id = self._page_id_or_none(url)
                if not page_id:
                    warnings.append(f"row {row['id']}: {url} names no page id; skipped")
                    continue
                if page_id not in ids:
                    ids.append(page_id)
                    by_id[page_id] = url
            if ids:
                contributions.append({**self._row_facts(row), "pages": ids, "urls": by_id})
                pages.extend(i for i in ids if i not in pages)
        return contributions, pages, warnings

    @staticmethod
    def _is_auth(exc: CommandError) -> bool:
        return "asi-hopper auth login" in str(exc)

    @staticmethod
    def _guard(call: Callable[[], Any]) -> Any:
        """Hopper's errors become command errors: the login hint as is (the one line the Jira verbs show),
        everything else prefixed."""
        from asi_hopper.errors import AuthRequired, HopperError

        try:
            return call()
        except AuthRequired as exc:
            raise CommandError(str(exc)) from None
        except HopperError as exc:
            raise CommandError(f"Confluence read failed: {exc}") from None
