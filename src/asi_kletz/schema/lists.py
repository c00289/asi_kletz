"""The lists of a control structure and of an STPA analysis: a ``FieldType.JSON`` column holding a JSON array.

0.19.0 gave a JSON column the shape of the people of a role (``schema/people.py``); 0.24.0 adds the plain
list: a controller's process-model entry names its control actions, variables and the feedback that updates
them one per line, a hazard its losses, a UCA its hazards, a scenario its types and constraints. ``list_of``
is the one reading: a list as it is, a JSON array parsed, any other text one item per line, blank the empty
list. The services write ``json_text(list_of(value))`` back, so the column always holds a JSON array and
the API answers with the list (``SqlRepository._decode``). Nothing here is a schema rule: the entity's own
guard calls it.
"""

from __future__ import annotations

import json
from typing import Any


def list_of(value: Any) -> list[Any]:
    """The list behind a value: ``None`` or blank is ``[]``; a list or a tuple is kept; a JSON array is
    parsed; any other text is one item per line, stripped, blanks dropped. A scalar that is none of these
    (a number, a dict) raises ``ValueError``."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                raise ValueError(f"{text[:40]!r} is not a JSON array") from None
            if isinstance(parsed, list):
                return parsed
        return [line.strip() for line in text.splitlines() if line.strip()]
    raise ValueError(f"{value!r} is not a list")


def lines_of(value: Any) -> str:
    """A list as a form shows it: one item per line (the inverse of ``list_of`` on typed text)."""
    try:
        items = list_of(value)
    except ValueError:
        return str(value)
    return "\n".join(str(item) for item in items)
