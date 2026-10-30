"""Work product URLs: what a Safety Plan row's ``urls`` holds since 0.20.0.

The owner, 2026-10-29: "please add the ability to add url parameters to each deliverable... each deliverable
may have multiple url... on multiple urls just go to first; list of urls is sequential while lists of names
are alphabetical".

A deliverable's ``urls`` is an ORDERED list of absolute ``http`` or ``https`` URLs: the first is *the link*
(the one the Excel hyperlink, the window's Open button and a standard's ``row_N_url`` go to), the rest follow
in the order typed; nothing here sorts. Three spellings of the same list:

- the API's array, ``["https://a.example/x", "https://b.example/y"]`` (also JSON text);
- the text a person types, one URL per line (or ``;`` between them: the CLI's ``--set "urls=https://a; https://b"``);
- the storage, a JSON array in the ``urls`` text column (``FieldType.JSON``).

Pure functions, no storage: ``parse_urls`` reads any of the first two and raises ``UrlsError`` with one message
per bad line; ``urls_json`` is the canonical storage text; ``urls_of``, ``urls_lines``, ``urls_text`` and
``first_url`` are the spellings out.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from .lists import typed_items

SCHEMES = ("http", "https")
WRITE = "write an absolute http(s) URL, one per line"


class UrlsError(ValueError):
    """One message per problem, each naming the line."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _items(value: Any) -> list[Any]:
    """The raw entries behind ``value``: ``lists.typed_items`` (a list as given; text split on ``;`` and line
    breaks, or parsed when it is a JSON array)."""
    return typed_items(value, "URLs", UrlsError)


def is_url(text: Any) -> bool:
    """Whether ``text`` is an absolute ``http`` or ``https`` URL with a host."""
    if not isinstance(text, str):
        return False
    try:
        parts = urlsplit(text.strip())
    except ValueError:
        return False
    return parts.scheme.lower() in SCHEMES and bool(parts.netloc) and not any(ch.isspace() for ch in text.strip())


def parse_urls(value: Any, field: str = "urls") -> list[str]:
    """The URLs behind ``value`` (an array, its JSON text, or one URL per line / ``;`` between them), validated,
    in the order given. Every problem is reported at once, each message naming the field and the line
    (``urls, line 2 ('ftp://x'): not an absolute http(s) URL``); a URL listed twice is refused."""
    errors: list[str] = []
    urls: list[str] = []
    seen: dict[str, int] = {}
    try:
        items = _items(value)
    except UrlsError as exc:
        raise UrlsError([f"{field}: {e}" for e in exc.errors]) from None
    for index, item in enumerate(items, start=1):
        where = f"{field}, line {index}"
        text = " ".join(str(item if item is not None else "").replace("\xa0", " ").split())
        if not text:
            errors.append(f"{where}: an empty entry; {WRITE}")
            continue
        if not is_url(text):
            errors.append(f"{where} ({text!r}): not an absolute http(s) URL; {WRITE}")
            continue
        if text in seen:
            errors.append(f"{field}: {text!r} is listed twice (lines {seen[text]} and {index})")
            continue
        seen[text] = index
        urls.append(text)
    if errors:
        raise UrlsError(errors)
    return urls


def urls_json(urls: Iterable[str]) -> str | None:
    """The canonical storage text: a JSON array in the order given; ``None`` for none."""
    rows = [str(u) for u in urls]
    return json.dumps(rows, ensure_ascii=False, separators=(", ", ": ")) if rows else None


def urls_of(value: Any) -> list[str]:
    """The URLs a stored row carries (``row["urls"]``: a decoded list, JSON text, or nothing); a value that
    does not parse is none. For reading what is stored, never for validating what comes in."""
    try:
        return parse_urls(value)
    except UrlsError:
        return []


def first_url(value: Any) -> str | None:
    """The link: the first URL of the list, or ``None``."""
    urls = urls_of(value)
    return urls[0] if urls else None


def urls_text(value: Any, sep: str = "; ") -> str:
    """``https://a; https://b``: the typed form on one line (the table cell, the CLI example)."""
    return sep.join(urls_of(value))


def urls_lines(value: Any) -> str:
    """One URL per line: what the editor and the workbook show."""
    return urls_text(value, "\n")


def url_host(url: str) -> str:
    """``www.microsoft.com`` for ``https://www.microsoft.com/``: the text an Excel hyperlink shows."""
    try:
        return urlsplit(url).netloc or url
    except ValueError:
        return url


# -- what a URL is (0.22.0, Phase A of the Confluence integration plan) ----------------------------------------
# The plan, 2026-10-29: "URLs that know what they are". The kind is decided from the host and the path, nothing
# is fetched. Confluence is the one that matters: the association between a deliverable and its Confluence page
# is the URL itself, so the tool must at least say which URLs are pages. Jama has no host, no kind and no door
# (the owner's "jama" of 2026-10-29 was a slip for Confluence); ``other`` and the optional host map of
# ``kletz.toml`` (``[urls] hosts = {jama = "...", dms = "..."}``) are there only so a pasted link is not mislabelled.
URL_KINDS = ("confluence", "jira", "sharepoint", "placeholder", "other")
ATLASSIAN_HOST = "asirobots.atlassian.net"
CONFLUENCE_PATHS = ("/wiki/",)
JIRA_PATHS = ("/browse/", "/jira/")
SHAREPOINT_SUFFIX = ".sharepoint.com"
PLACEHOLDER_HOST = "www.microsoft.com"  # the 0.20.0 placeholder: the owner's "use microsoft homepage"
KIND_LABELS = {"confluence": "Confluence", "jira": "Jira", "sharepoint": "SharePoint"}
ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


def _host_and_path(url: Any) -> tuple[str, str]:
    """The lower-case host (no port, no credentials) and the path of ``url``; empty for text that is no URL."""
    if not isinstance(url, str):
        return "", ""
    try:
        parts = urlsplit(url.strip())
        return (parts.hostname or "").lower(), parts.path or "/"
    except ValueError:
        return "", ""


def _host_matches(host: str, pattern: Any) -> bool:
    """``pattern`` names ``host``: the same host (any case), or ``*.example.com`` for any host under it."""
    text = str(pattern or "").strip().lower()
    if not text or not host:
        return False
    if text.startswith("*."):
        return host.endswith(text[1:]) and host != text[2:]
    return host == text


def _under(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p) for p in prefixes)


def url_kind(url: Any, hosts: dict[str, Any] | None = None) -> str:
    """What ``url`` is, one of ``URL_KINDS`` or a name from ``hosts``, decided from the host and the path:

    - a kind of ``hosts`` (``kletz.toml`` ``[urls] hosts``: name -> host or list of hosts, ``*.`` for a whole
      domain) whose host matches, the owner's word first;
    - ``confluence``: ``asirobots.atlassian.net`` with a path under ``/wiki/``;
    - ``jira``: the same host with a path under ``/browse/`` or ``/jira/``;
    - ``sharepoint``: any ``*.sharepoint.com`` host;
    - ``placeholder``: ``www.microsoft.com`` (the 0.20.0 placeholder);
    - ``other``: anything else, text that is no URL included.
    """
    host, path = _host_and_path(url)
    if not host:
        return "other"
    for name, pattern in (hosts or {}).items():
        patterns = pattern if isinstance(pattern, (list, tuple)) else [pattern]
        if any(_host_matches(host, p) for p in patterns):
            return str(name).strip().lower() or "other"
    folded = path.lower()
    if host == ATLASSIAN_HOST:
        if _under(folded, CONFLUENCE_PATHS):
            return "confluence"
        if _under(folded, JIRA_PATHS):
            return "jira"
        return "other"
    if host.endswith(SHAREPOINT_SUFFIX) and host != SHAREPOINT_SUFFIX[1:]:
        return "sharepoint"
    if host == PLACEHOLDER_HOST:
        return "placeholder"
    return "other"


def kind_label(url: Any, hosts: dict[str, Any] | None = None) -> str:
    """The kind and the host for a reader: ``Confluence, asirobots.atlassian.net``; ``Jira, ...``;
    ``SharePoint, ...``; a configured kind by its name (``jama, jama.example.com``); ``other, <host>``; a
    placeholder reads ``placeholder`` alone, so a reviewer sees which deliverables still point nowhere."""
    kind = url_kind(url, hosts)
    if kind == "placeholder":
        return kind
    return f"{KIND_LABELS.get(kind, kind)}, {url_host(str(url).strip())}"


def url_kinds(value: Any, hosts: dict[str, Any] | None = None) -> list[str]:
    """The kinds present on a stored list, each once, in the order the URLs come (the audit's ``kinds``)."""
    kinds: list[str] = []
    for url in urls_of(value):
        kind = url_kind(url, hosts)
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def jira_issue_key(url: Any) -> str | None:
    """The issue key a Jira URL names, upper case (``HWL-2554`` for ``.../browse/HWL-2554``,
    ``.../jira/software/c/projects/HWL/issues/HWL-2554`` or ``...?selectedIssue=HWL-2554``), or ``None``."""
    if not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    segments = [s for s in parts.path.split("/") if s]
    for marker in ("browse", "issues"):
        if marker in segments:
            index = segments.index(marker)
            if index + 1 < len(segments) and ISSUE_KEY.match(segments[index + 1].upper()):
                return segments[index + 1].upper()
    for name, value in parse_qsl(parts.query):
        if name == "selectedIssue" and ISSUE_KEY.match(value.strip().upper()):
            return value.strip().upper()
    return None
