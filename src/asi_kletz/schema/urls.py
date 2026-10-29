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
from urllib.parse import urlsplit

SEPARATORS = re.compile(r"[;\r\n]+")
SCHEMES = ("http", "https")
WRITE = "write an absolute http(s) URL, one per line"


class UrlsError(ValueError):
    """One message per problem, each naming the line."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _items(value: Any) -> list[Any]:
    """The raw entries behind ``value``: a list as given; text split on ``;`` and line breaks, or parsed when
    it is a JSON array."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    text = str(value).replace("\xa0", " ").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except ValueError as exc:
            raise UrlsError([f"not a JSON array of URLs: {exc}"]) from None
        if not isinstance(parsed, list):
            raise UrlsError(["not a JSON array of URLs"])
        return parsed
    return [part.strip() for part in SEPARATORS.split(text) if part.strip()]


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
