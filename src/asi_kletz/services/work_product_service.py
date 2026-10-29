"""WorkProductService: the work product URLs of a Safety Plan row (0.20.0).

The owner, 2026-10-29: "please add the ability to add url parameters to each deliverable... each deliverable
may have multiple url... make sure that the excel export includes links to the work products wherever they
may be... on multiple urls just go to first; list of urls is sequential while lists of names are alphabetical...
use microsoft homepage as placeholder url for all".

``guard`` is the rule on every create and update of a plan row: ``urls`` (the API's array, its JSON text, or
the ``https://a; https://b`` / one-per-line text) is parsed, validated (each an absolute http(s) URL, none
twice) and stored as JSON in the order given; a Jira key that reads ``no ticket attached`` (the workbook's
text for an empty cell) is no key. ``loaded`` does the same for a row of a dump or a workbook, dropping a bad
list with the messages as warnings so the row still loads. ``fill_placeholder`` puts one URL on every row
that has none (audited once, idempotent; ``check`` writes nothing).

0.22.0, Phase A of the Confluence integration plan ("URLs that know what they are"): ``audit`` reads every
row's URLs by kind (``schema/urls.py:url_kind``) and names the findings an agent acts on (a placeholder still
present; no Confluence page on a deliverable whose work product location names Confluence; a Jira URL that
disagrees with the row's Jira key), writing nothing; ``replace`` swaps one URL for another on every row that
carries it, in place, one transaction, one audit entry, so the placeholder gives way to a real page URL on
every row at once and a page that moves is corrected once. Neither touches Confluence or Jira.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import CommandError, ValidationError
from ..generate import plan_queries as pq
from ..schema.definitions import NO_TICKET
from ..schema.urls import UrlsError, is_url, jira_issue_key, parse_urls, url_kind, url_kinds, urls_json, urls_of

if TYPE_CHECKING:
    from ..brain import Brain

PLAN = pq.PLAN_ENTITY


def no_ticket(value: Any) -> bool:
    """Whether a Jira key cell holds the workbook's ``no ticket attached`` text (any case, any spacing)."""
    return isinstance(value, str) and " ".join(value.split()).casefold() == NO_TICKET


class WorkProductService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- the rule on the rows -------------------------------------------------------------
    def guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> list[str]:
        """Before a create or an update: ``urls`` parsed, validated and stored as JSON, in order; a key that
        says ``no ticket attached`` is cleared."""
        if "urls" in clean:
            try:
                clean["urls"] = urls_json(parse_urls(clean["urls"]))
            except UrlsError as exc:
                raise ValidationError(PLAN, exc.errors) from None
        if no_ticket(clean.get("jira_key")):
            clean["jira_key"] = None
        return []

    def loaded(self, clean: dict[str, Any]) -> list[str]:
        """A row of a dump or a workbook (``EntityService.load_rows`` runs no guard): the same parsing; a bad
        list is dropped with the messages as warnings, the row still loads; the workbook's ``no ticket
        attached`` is no key."""
        warnings: list[str] = []
        if clean.get("urls") not in (None, ""):
            try:
                clean["urls"] = urls_json(parse_urls(clean["urls"]))
            except UrlsError as exc:
                warnings.extend(f"{e}; urls ignored" for e in exc.errors)
                clean["urls"] = None
        else:
            clean["urls"] = None
        if no_ticket(clean.get("jira_key")):
            clean["jira_key"] = None
        return warnings

    # -- the placeholder ----------------------------------------------------------------------
    def fill_placeholder(self, url: str, actor: str = "python", check: bool = False) -> dict[str, Any]:
        """Every plan row with no URL gets ``[url]``; a row that has any is left alone, so a second run
        changes nothing. One transaction, one audit entry (``urls_placeholder``, with the ids); ``check``
        reports the rows it would fill and writes nothing."""
        text = " ".join(str(url or "").split())
        if not is_url(text):
            raise CommandError(f"{url!r} is not an absolute http(s) URL")
        rows = pq.all_rows(self.brain)
        empty = [r for r in rows if not urls_of(r.get("urls"))]
        filled = [r["id"] for r in empty]
        if not check and empty:
            repo = self.brain.service(PLAN).repo
            with self.brain.storage.transaction():
                for row in empty:
                    repo.update(row["id"], {"urls": urls_json([text])})
                self.brain.storage.audit(actor, "urls_placeholder", PLAN, None, {"url": text, "rows": filled})
            self.brain.events.publish("plan.urls_placeholder", url=text, rows=len(filled), actor=actor)
        return {
            "placeholder": text, "check": bool(check), "rows": len(rows),
            "filled": filled if not check else [], "would_fill": filled if check else [],
            "already": len(rows) - len(empty),
            "rows_filled": [
                {"id": r["id"], "order": r.get("order"), "deliverable": pq.one_line(r.get("deliverable") or "", 60)}
                for r in empty
            ],
        }

    # -- the kinds (0.22.0) ---------------------------------------------------------------------------
    @property
    def hosts(self) -> dict[str, list[str]]:
        """The owner's extra URL kinds (``kletz.toml`` ``[urls] hosts``), handed to ``url_kind``."""
        return getattr(self.brain, "url_hosts", {}) or {}

    def kind(self, url: str) -> str:
        return url_kind(url, self.hosts)

    def _rows(self, rows: list[Any] | None) -> list[dict[str, Any]]:
        """Every plan row in plan order, or only the ones named (ids or uids; an unknown one is refused)."""
        every = pq.all_rows(self.brain)
        if not rows:
            return every
        service = self.brain.service(PLAN)
        wanted = [service.resolve(ref) for ref in rows]
        by_id = {r["id"]: r for r in every}
        missing = [ref for ref, row_id in zip(rows, wanted, strict=True) if row_id not in by_id]
        if missing:
            raise CommandError(f"no plan row {', '.join(str(m) for m in missing)}")
        return [by_id[row_id] for row_id in dict.fromkeys(wanted)]

    def rows(self, rows: list[Any] | None = None) -> list[dict[str, Any]]:
        """``_rows`` for a sibling service (0.23.0: the Confluence evidence and check read the same selection)."""
        return self._rows(rows)

    def audit(self, rows: list[Any] | None = None) -> list[dict[str, Any]]:
        """The findings on the rows (default all), writing nothing; each ``{id, uid, order, deliverable, kinds,
        urls, code, finding}``. The codes: ``placeholder`` (the placeholder is still a URL of the row),
        ``no_confluence`` (the work product location names Confluence and no URL is a Confluence page),
        ``jira_key`` (a Jira URL names an issue other than the row's Jira key). Findings are data, not errors:
        a row with none appears nowhere."""
        findings: list[dict[str, Any]] = []
        for row in self._rows(rows):
            urls = urls_of(row.get("urls"))
            kinds = url_kinds(urls, self.hosts)
            key = (row.get("jira_key") or "").strip().upper()
            location = str(row.get("work_product_location") or "")
            notes: list[tuple[str, str]] = []
            for url in urls:
                if self.kind(url) == "placeholder":
                    notes.append(("placeholder", f"the placeholder {url} is still present"))
            if "confluence" in location.casefold() and "confluence" not in kinds:
                notes.append((
                    "no_confluence",
                    f"the work product location says {location!r} and no URL is a Confluence page",
                ))
            for url in urls:
                issue = jira_issue_key(url) if self.kind(url) == "jira" else None
                if issue and issue != key:
                    notes.append(("jira_key", f"the Jira URL names {issue} and the row's Jira key is {key or 'empty'}"))
            findings.extend(
                {
                    "id": row["id"], "uid": row.get("uid"), "order": row.get("order"),
                    "deliverable": pq.one_line(row.get("deliverable") or "", 60), "kinds": kinds, "urls": urls,
                    "code": code, "finding": text,
                }
                for code, text in notes
            )
        return findings

    def replace(self, old: str, new: str, actor: str = "python", check: bool = False) -> dict[str, Any]:
        """Every plan row whose list contains ``old`` gets ``new`` in the same position; a row that already
        carries ``new`` elsewhere is left alone with a warning (a URL may not be listed twice). One
        transaction, one audit entry (``urls_replace``, with the ids), the event ``plan.urls_replaced``;
        ``check`` names the rows and writes nothing. Both URLs must be absolute http(s) URLs, and differ."""
        old_text = " ".join(str(old or "").split())
        new_text = " ".join(str(new or "").split())
        for text, given in ((old_text, old), (new_text, new)):
            if not is_url(text):
                raise CommandError(f"{given!r} is not an absolute http(s) URL")
        if old_text == new_text:
            raise CommandError(f"the old and the new URL are the same ({old_text})")
        rows = pq.all_rows(self.brain)
        changes: list[tuple[dict[str, Any], list[str], int]] = []
        refused: list[int] = []
        warnings: list[str] = []
        for row in rows:
            urls = urls_of(row.get("urls"))
            if old_text not in urls:
                continue
            if new_text in urls:
                refused.append(row["id"])
                warnings.append(
                    f"row {row['id']} ({pq.one_line(row.get('deliverable') or '', 60)}): {new_text} is already "
                    "on the row; left as it is"
                )
                continue
            changes.append((row, [new_text if u == old_text else u for u in urls], urls.index(old_text)))
        replaced = [row["id"] for row, _urls, _position in changes]
        if not check and changes:
            repo = self.brain.service(PLAN).repo
            with self.brain.storage.transaction():
                for row, urls, _position in changes:
                    repo.update(row["id"], {"urls": urls_json(urls)})
                self.brain.storage.audit(
                    actor, "urls_replace", PLAN, None,
                    {"old": old_text, "new": new_text, "rows": replaced, "refused": refused},
                )
            self.brain.events.publish("plan.urls_replaced", old=old_text, new=new_text, rows=len(replaced), actor=actor)
        return {
            "old": old_text, "new": new_text, "kind": self.kind(new_text), "check": bool(check), "rows": len(rows),
            "replaced": replaced if not check else [], "would_replace": replaced if check else [],
            "refused": refused,
            "rows_replaced": [
                {"id": row["id"], "order": row.get("order"), "position": position + 1,
                 "deliverable": pq.one_line(row.get("deliverable") or "", 60)}
                for row, _urls, position in changes
            ],
            "warnings": warnings,
        }
