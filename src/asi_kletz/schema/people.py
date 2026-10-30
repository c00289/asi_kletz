"""People: what a role parameter holds since 0.19.0.

The owner, 2026-10-29: "each safety deliverable can have multiple authors, so for any safety case field,
instead of the parameter being a string it is now an array of human names sorted alphabetically; make all
updates necessary; also must include email alongside name."

A *person* is a name and an email. A *role parameter* (a ``parameter`` whose name is one of
``definitions.ROLE_SLUGS``: ``fusa_engineer``, ``tech_lead_functional_safety``, ...) holds a list of them,
kept sorted by name (case-insensitive, the full name as typed), each with a non-empty name and an email that
looks like one (``local@domain.tld``), no email twice. Three spellings of the same list:

- the API's array, ``[{"name": "Ann Lee", "email": "ann.lee@asirobots.com"}, ...]`` (also JSON text);
- the text form a person types, ``Ann Lee <ann.lee@asirobots.com>; Ben Ray <ben.ray@asirobots.com>``:
  people separated by ``;`` or by a line break, the email in angle brackets;
- the rendering an export prints inline, ``Ann Lee (ann.lee@asirobots.com), Ben Ray (ben.ray@asirobots.com)``.

Pure functions, no storage: ``parse_people`` reads any of the first two and raises ``PeopleError`` with one
message per bad line naming the role; ``people_json`` is the canonical storage text; ``people_text``,
``people_lines`` and ``render_people`` are the three spellings out.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .definitions import ROLE_SLUGS
from .lists import typed_items

PERSON_LINE = re.compile(r"^(?P<name>[^<>]*?)\s*<(?P<email>[^<>]*)>$")
EMAIL = re.compile(r"^[^\s@<>()]+@[^\s@<>()]+\.[^\s@<>()]+$")
WRITE = "write Name <email>"


class PeopleError(ValueError):
    """One message per problem, each naming the role and the line."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Person:
    name: str
    email: str

    @property
    def text(self) -> str:
        """``Ann Lee <ann.lee@asirobots.com>``: the form a person types."""
        return f"{self.name} <{self.email}>"

    @property
    def rendered(self) -> str:
        """``Ann Lee (ann.lee@asirobots.com)``: the form an export prints."""
        return f"{self.name} ({self.email})"

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "email": self.email}


def is_role(name: Any) -> bool:
    """Whether a parameter name is a role (the slug of an author or reviewer header)."""
    return isinstance(name, str) and name in ROLE_SLUGS


def sort_people(people: Iterable[Person]) -> list[Person]:
    """Alphabetical by name, case-insensitive, the full name string as typed; the email breaks a tie."""
    return sorted(people, key=lambda p: (p.name.casefold(), p.name, p.email.casefold()))


def _items(value: Any) -> list[Any]:
    """The raw entries behind ``value``: one person as given; else ``lists.typed_items`` (a list as given; text
    split on ``;`` and line breaks, or parsed when it is a JSON array)."""
    if isinstance(value, (Person, dict)):
        return [value]
    return typed_items(value, "people", PeopleError)


def _person(item: Any, where: str) -> Person:
    """One entry as a Person: a dict ``{"name", "email"}``, a ``Name <email>`` string, or a Person."""
    if isinstance(item, Person):
        name, email = item.name, item.email
    elif isinstance(item, dict):
        name = str(item.get("name") or "").strip()
        email = str(item.get("email") or "").strip()
        if not name and not email:
            raise PeopleError([f"{where}: a person needs a name and an email"])
    else:
        line = " ".join(str(item).replace("\xa0", " ").split())
        match = PERSON_LINE.match(line)
        if match is None:
            if "<" in line or ">" in line:
                raise PeopleError([f"{where} ({line!r}): the email goes in angle brackets, once; {WRITE}"])
            raise PeopleError([f"{where} ({line!r}): no email; {WRITE}"])
        name, email = match.group("name").strip(), match.group("email").strip()
    name = " ".join(name.split())
    if not name:
        raise PeopleError([f"{where} ({item if isinstance(item, str) else email!r}): no name; {WRITE}"])
    if "@" in name or "<" in name or ">" in name:
        raise PeopleError([
            f"{where}: the name {name!r} holds an email; the email goes after it, once, in angle brackets"
        ])
    if not email:
        raise PeopleError([f"{where} ({name!r}): no email; {WRITE}"])
    if not EMAIL.match(email):
        raise PeopleError([f"{where}: {email!r} is not an email (local@domain.tld)"])
    return Person(name, email)


def parse_people(value: Any, role: str = "people") -> list[Person]:
    """The people behind ``value`` (an array of dicts, a JSON text of one, the ``Name <email>; ...`` text, or
    one person per line), validated and sorted. Every problem is reported at once, each message naming the
    role and the line (``fusa_engineer, line 2 ('Ben Ray'): no email; write Name <email>``)."""
    errors: list[str] = []
    people: list[Person] = []
    seen: dict[str, int] = {}
    try:
        items = _items(value)
    except PeopleError as exc:
        raise PeopleError([f"{role}: {e}" for e in exc.errors]) from None
    for index, item in enumerate(items, start=1):
        where = f"{role}, line {index}"
        try:
            person = _person(item, where)
        except PeopleError as exc:
            errors.extend(exc.errors)
            continue
        key = person.email.casefold()
        if key in seen:
            errors.append(f"{role}: {person.email!r} is listed twice (lines {seen[key]} and {index})")
            continue
        seen[key] = index
        people.append(person)
    if errors:
        raise PeopleError(errors)
    return sort_people(people)


def people_json(people: Iterable[Person]) -> str | None:
    """The canonical storage text: a JSON array of ``{"name", "email"}`` in sorted order; ``None`` for nobody."""
    rows = [p.to_dict() for p in sort_people(people)]
    return json.dumps(rows, ensure_ascii=False, separators=(", ", ": ")) if rows else None


def people_of(value: Any) -> list[Person]:
    """The people a stored row carries (``row["people"]``: a decoded list, JSON text, or nothing); a value
    that does not parse is nobody. For reading what is stored, never for validating what comes in."""
    try:
        return parse_people(value)
    except PeopleError:
        return []


def people_text(value: Any, sep: str = "; ") -> str:
    """``Ann Lee <ann@...>; Ben Ray <ben@...>``: the typed form, one line (the table cell, the CLI example)."""
    return sep.join(p.text for p in people_of(value))


def people_lines(value: Any) -> str:
    """One person per line, ``Name <email>``: what the editors show."""
    return people_text(value, "\n")


def render_people(value: Any) -> str:
    """``Ann Lee (ann@...), Ben Ray (ben@...)``: what an export prints in the role's cell, alphabetical."""
    return ", ".join(p.rendered for p in people_of(value))
