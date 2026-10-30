"""The timestamp suffix every exported file carries.

The owner, 2026-10-30: "ensure that files we export like the safety plan include a timestamp suffix".
``stamped("kletz.xlsx")`` is ``kletz_20261030-083512.xlsx``: the local time the file was written, to the
second, in the form the locked-file fallback had used since 0.8.x, so a folder of exports sorts by name
into the order they were made and no export overwrites the one before. A stem that already carries a
stamp (the path the Export / Import screen remembers from the last export, say) is stamped afresh,
never twice. Every Result carries the written ``path``, so nobody has to guess the name.

What is stamped: the workbook (``export excel``), the standards a plan row is exported into (``plan
export``), the documents of the catalog (``document``) and the tracker texts (``tracker build``): what a
person opens. The JSON dump (``dump``, ``export json``) keeps the exact name it is given, a machine artefact
that ``load`` and the scripts read back by that path; diagrams and control-structure bundles are views
regenerated in place under their catalog name and are not stamped either.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

FORMAT = "%Y%m%d-%H%M%S"
STAMP = re.compile(r"_\d{8}-\d{6}(?:-\d+)?$")        # a stamp, with the -2 / -3 of a locked-file sibling
_SIBLING = re.compile(r"^(.*_\d{8}-\d{6})(?:-(\d+))?$")


def stamp(now: dt.datetime | None = None) -> str:
    """``20261030-083512``: the local time, to the second."""
    return (now or dt.datetime.now()).strftime(FORMAT)


def stamped_stem(stem: str, now: dt.datetime | None = None) -> str:
    """``kletz`` -> ``kletz_20261030-083512``; a stem already stamped is stamped afresh, not twice."""
    return f"{STAMP.sub('', stem)}_{stamp(now)}"


def stamped(path: str | Path, now: dt.datetime | None = None) -> Path:
    """The path under its stamped name, in the same folder with the same suffix."""
    path = Path(path)
    return path.with_name(stamped_stem(path.stem, now) + path.suffix)


def next_sibling(path: Path) -> Path:
    """The name tried when a stamped file is locked (open in another program): the same stamp with ``-2``,
    then ``-3``, and so on; an unstamped name gets ``-2`` too."""
    m = _SIBLING.match(path.stem)
    if not m:
        return path.with_name(f"{path.stem}-2{path.suffix}")
    return path.with_name(f"{m.group(1)}-{int(m.group(2) or 1) + 1}{path.suffix}")
