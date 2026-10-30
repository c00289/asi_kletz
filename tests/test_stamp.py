"""The timestamp suffix of every exported file (0.27.0)."""

import datetime as dt
import re
from pathlib import Path

from asi_kletz.io.stamp import STAMP, next_sibling, stamp, stamped, stamped_stem

NOON = dt.datetime(2026, 10, 30, 12, 34, 56)


def test_stamp_is_the_local_time_to_the_second():
    assert stamp(NOON) == "20261030-123456"
    assert re.fullmatch(r"\d{8}-\d{6}", stamp())


def test_stamped_stem_never_stamps_twice():
    assert stamped_stem("kletz", NOON) == "kletz_20261030-123456"
    assert stamped_stem("kletz_20261029-080000", NOON) == "kletz_20261030-123456"
    assert stamped_stem("kletz_20261029-080000-2", NOON) == "kletz_20261030-123456"
    assert stamped_stem("tracker_week", NOON) == "tracker_week_20261030-123456"      # an inner underscore stays


def test_stamped_path_keeps_folder_and_suffix():
    assert stamped(Path("C:/out/kletz.xlsx"), NOON) == Path("C:/out/kletz_20261030-123456.xlsx")
    assert stamped("qf-17-safety-plan.docx", NOON) == Path("qf-17-safety-plan_20261030-123456.docx")
    assert STAMP.search(stamped("a.json").stem)


def test_next_sibling_counts_up():
    first = Path("out/kletz_20261030-123456.xlsx")
    second = next_sibling(first)
    assert second == Path("out/kletz_20261030-123456-2.xlsx")
    assert next_sibling(second) == Path("out/kletz_20261030-123456-3.xlsx")
    assert next_sibling(Path("plain.txt")) == Path("plain-2.txt")
