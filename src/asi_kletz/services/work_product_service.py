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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..errors import CommandError, ValidationError
from ..generate import plan_queries as pq
from ..schema.definitions import NO_TICKET
from ..schema.urls import UrlsError, is_url, parse_urls, urls_json, urls_of

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
