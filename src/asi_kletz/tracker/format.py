"""The grammar of the Weekly Activity Tracker text file: ``parse`` reads it, ``render`` writes it.

The file the engineer kept by hand is the specification: an import followed by a build gives the
file back. One module knows the shape, so the importer and the builder cannot drift::

    <title>
    <byline>. Newest week at the top. Last updated m/d/yyyy.

    TIMELINE
    - Phase 2 (HARA / Risk Assessment): Sprint 1: 10/12 - 10/27/2026. Closed 10/27.
    - Phase 3 (Functional Safety Concept): opened 10/27/2026. Sprint 2: 10/27 - 11/10.
    - Scope: <scope>

    =====================================================================
    PHASE 3 - SPRINT 2 (10/27 - 11/10)   [in progress]
    =====================================================================
    Sprint: 9 of 10 points committed, ...          (generated, only when an item is pointed)

    WEEK OF 10/26 - 11/01   (<note>)

    Outcomes so far                                 ("Outcomes" once the week is over)
    - ...

    Miscellaneous issues

      <verbatim text>

    Jira issues (<jira scope>, as of 10/28)         (built from the sprint's Jira items)

      <heading lines, 2 spaces>

      HWL-2554  Story  <title>
                Jira status: <jira line>
                Note: <note>
                Sprint 2 target: <target>
                Points: 3                           (omitted while unpointed)

Nothing here reads or writes the database: the service turns rows into ``Tracker`` and back.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

DEFAULT_TITLE = "WHEEL LOADER FUNCTIONAL SAFETY ENGINEERING - WEEKLY ACTIVITY TRACKER"
DEFAULT_BYLINE = "FuSa Engineer"
DEFAULT_JIRA_SCOPE = "project HWL, open items I am assigned, reported or watching"
RULE = "=" * 69
KEY_INDENT = "  "
DETAIL_INDENT = " " * 12
TITLE_INDENT = " " * 19  # continuation lines of a wrapped title align under its first line

SECTION_NOTE, SECTION_OUTCOMES, SECTION_ISSUES, SECTION_JIRA = "Note", "Outcomes", "Issues", "Jira"
SECTION_ORDER = {SECTION_NOTE: 0, SECTION_OUTCOMES: 1, SECTION_ISSUES: 2, SECTION_JIRA: 3}
_SECTION_HEADINGS = {
    "outcomes": SECTION_OUTCOMES, "outcomes so far": SECTION_OUTCOMES, "miscellaneous issues": SECTION_ISSUES,
}

_BYLINE = re.compile(r"^(?P<byline>.*?)\. Newest week at the top\. Last updated (?P<date>\d{1,2}/\d{1,2}/\d{4})\.$")
_SPRINT = re.compile(
    r"^PHASE (?P<phase>\d+) - (?P<label>.+?) \((?P<start>\d{1,2}/\d{1,2}) - (?P<end>\d{1,2}/\d{1,2})\)"
    r"\s+\[(?P<status>[^\]]+)\]$"
)
_WEEK = re.compile(r"^WEEK OF (?P<start>\d{1,2}/\d{1,2}) - (?P<end>\d{1,2}/\d{1,2})(?:\s+\((?P<note>.*)\))?$")
_JIRA_HEADING = re.compile(r"^Jira issues \((?P<scope>.*?)(?:, as of (?P<asof>\d{1,2}/\d{1,2}))?\)$")
_ITEM = re.compile(r"^  (?P<key>[A-Z][A-Z0-9_]*-\d+)  (?P<type>\S+)\s+(?P<title>\S.*)$")
_DETAIL = re.compile(r"^ {12}(?P<label>\S[^:]*): ?(?P<value>.*)$")
_CLOSED = re.compile(r"^closed (?P<date>\d{1,2}/\d{1,2})$")
_YEAR = re.compile(r"\d{1,2}/\d{1,2}/(\d{4})")
_TIMELINE_PHASE = re.compile(r"^- Phase (?P<n>\d+) \((?P<title>.+?)\): ")
_TARGET = re.compile(r" (?P<label>\S+(?: \S+)?) target: (?P<target>.+)$")
_ASK = re.compile(r"\bAsk: (?P<ask>.+?)(?= Sprint \S+ target:|$)")
_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")


class ParseError(ValueError):
    """The text does not follow the grammar; the message names the line."""


# -- model ------------------------------------------------------------------------
@dataclass
class Item:
    """A Jira item as the tracker prints it (the other kinds never print; they live on the board)."""

    key: str
    issue_type: str | None = None
    title: str = ""  # may hold newlines: a wrapped title keeps its wrap
    jira_line: str | None = None
    note: str | None = None
    target: str | None = None
    points: int | None = None
    heading: str | None = None  # printed before the item, once per run of items that share it
    id: int | None = None


@dataclass
class Target:
    """A ``Sprint n target:`` or ``Ask:`` found inside the Issues text of a week."""

    title: str
    target: str | None = None
    ask: str | None = None
    under: str | None = None  # the sub-heading the bullet sat under, e.g. "People and cadence"


@dataclass
class Week:
    start: dt.date
    note: str | None = None
    outcomes: str | None = None
    issues: str | None = None
    jira_frozen: str | None = None  # the whole Jira section, heading included, once the week is history
    jira_scope: str | None = None
    jira_as_of: str | None = None
    targets: list[Target] = field(default_factory=list)

    @property
    def end(self) -> dt.date:
        return self.start + dt.timedelta(days=6)

    def is_current(self, as_of: dt.date) -> bool:
        return self.start <= as_of <= self.end


@dataclass
class Sprint:
    phase_number: str  # "3"
    phase_title: str  # "Functional Safety Concept (FSC)"; the timeline drops a trailing parenthesis
    label: str  # "SPRINT 1", "SPRINT 2": one dated interval is one sprint, numbered across the programme
    start: dt.date
    end: dt.date
    status: str  # Planned | Active | Closed
    closed_on: dt.date | None = None
    goal: str | None = None
    summary: str | None = None  # the generated sprint line; None while nothing is pointed
    number: int | None = None
    weeks: list[Week] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)

    @property
    def heading(self) -> str:
        if self.status == "Closed":
            when = self.closed_on or self.end
            status = f"closed {_md(when)}"
        elif self.status == "Active":
            status = "in progress"
        else:
            status = "planned"
        return f"PHASE {self.phase_number} - {self.label} ({_md(self.start)} - {_md(self.end)})   [{status}]"

    @property
    def target_label(self) -> str:
        """``SPRINT 1`` -> ``Sprint 1``, the word before ``target:`` on an item line."""
        return self.label.capitalize()


@dataclass
class Tracker:
    title: str = DEFAULT_TITLE
    byline: str = DEFAULT_BYLINE
    scope: str | None = None
    jira_scope: str = DEFAULT_JIRA_SCOPE
    updated: dt.date | None = None
    sprints: list[Sprint] = field(default_factory=list)


# -- dates ----------------------------------------------------------------------------
def _md(day: dt.date) -> str:
    return day.strftime("%m/%d")


def _mdy(day: dt.date) -> str:
    return day.strftime("%m/%d/%Y")


def _parse_md(text: str, year: int, near: dt.date | None = None) -> dt.date:
    """``10/27`` with a year; when ``near`` is given the year is shifted so the date is within six months of it."""
    month, day = (int(p) for p in text.split("/"))
    when = dt.date(year, month, day)
    if near is not None:
        for candidate in (when, when.replace(year=year + 1), when.replace(year=year - 1)):
            if abs((candidate - near).days) <= 183:
                return candidate
    return when


# -- parse ------------------------------------------------------------------------------
def parse(text: str) -> Tracker:
    """Read the tracker text. Raises ``ParseError`` naming the line that does not fit."""
    lines = text.splitlines()
    if len(lines) < 2:
        raise ParseError("line 1: expected the title line and the byline line")
    match = _BYLINE.match(lines[1].strip())
    if not match:
        raise ParseError("line 2: expected '<byline>. Newest week at the top. Last updated m/d/yyyy.'")
    tracker = Tracker(title=lines[0].strip(), byline=match["byline"])
    tracker.updated = dt.datetime.strptime(match["date"], "%m/%d/%Y").date()
    year = tracker.updated.year

    timeline = next((i for i, line in enumerate(lines) if line.strip() == "TIMELINE"), None)
    if timeline is None:
        raise ParseError("no TIMELINE line")
    index = timeline + 1
    year_seen = False
    titles: dict[str, str] = {}  # phase number -> title as the timeline bullets name it
    while index < len(lines) and lines[index].strip():
        line = lines[index].strip()
        if line.startswith("- Scope: "):
            tracker.scope = line[len("- Scope: "):]
        elif phase := _TIMELINE_PHASE.match(line):
            titles.setdefault(phase["n"], phase["title"])
        found = _YEAR.search(line)
        if found and not year_seen:
            year, year_seen = int(found.group(1)), True
        index += 1

    rules = [i for i, line in enumerate(lines) if line.strip() and set(line.strip()) == {"="}]
    starts: list[int] = []
    index = 0
    while index + 1 < len(rules):
        if rules[index + 1] == rules[index] + 2:
            starts.append(rules[index])
            index += 2
        else:
            index += 1
    for position, top in enumerate(starts):
        heading = lines[top + 1].strip()
        found = _SPRINT.match(heading)
        if not found:
            raise ParseError(f"line {top + 2}: expected 'PHASE n - LABEL (m/d - m/d)   [status]', got {heading!r}")
        status_text = found["status"].strip().lower()
        closed_on = None
        if status_text == "in progress":
            status = "Active"
        elif status_text == "planned":
            status = "Planned"
        elif closed := _CLOSED.match(status_text):
            status = "Closed"
            closed_on = closed["date"]
        else:
            raise ParseError(f"line {top + 2}: unknown sprint status {found['status']!r}")
        start = _parse_md(found["start"], year, near=tracker.updated)
        end = _parse_md(found["end"], year, near=start)
        if end < start:
            end = end.replace(year=end.year + 1)
        sprint = Sprint(found["phase"], titles.get(found["phase"], ""), found["label"], start, end, status,
                        closed_on=_parse_md(closed_on, year, near=end) if closed_on else None)
        stop = starts[position + 1] if position + 1 < len(starts) else len(lines)
        _parse_weeks(sprint, lines, top + 3, stop, year, tracker)
        tracker.sprints.append(sprint)
    return tracker


def _parse_weeks(sprint: Sprint, lines: list[str], begin: int, stop: int, year: int, tracker: Tracker) -> None:
    heads = [i for i in range(begin, stop) if _WEEK.match(lines[i].strip())]
    for index in range(begin, heads[0] if heads else stop):
        line = lines[index].strip()
        if line.startswith("Goal: "):
            sprint.goal = line[len("Goal: "):]
        elif line and not line.startswith("Sprint: "):
            raise ParseError(f"line {index + 1}: expected a Goal line, the sprint line or WEEK OF, got {line!r}")
    seen_keys = {item.key for item in sprint.items}
    for position, head in enumerate(heads):
        found = _WEEK.match(lines[head].strip())
        assert found is not None
        week = Week(_parse_md(found["start"], year, near=sprint.start), note=found["note"])
        end = heads[position + 1] if position + 1 < len(heads) else stop
        _parse_sections(week, sprint, lines, head + 1, end, tracker, seen_keys)
        sprint.weeks.append(week)


def dedent_issues(text: str) -> str:
    """Drop the two-space indent every line of the Issues section carries; the database holds the text without it."""
    lines = text.splitlines()
    if all(line.startswith(KEY_INDENT) for line in lines if line.strip()):
        lines = [line[len(KEY_INDENT):] if line.startswith(KEY_INDENT) else line for line in lines]
    return "\n".join(lines)


def indent_issues(text: str) -> str:
    return "\n".join(KEY_INDENT + line if line.strip() else "" for line in text.splitlines())


def _strip_blank(block: list[str]) -> str | None:
    while block and not block[0].strip():
        block.pop(0)
    while block and not block[-1].strip():
        block.pop()
    return "\n".join(block) if block else None


def _parse_sections(
    week: Week, sprint: Sprint, lines: list[str], begin: int, end: int, tracker: Tracker, seen_keys: set[str]
) -> None:
    sections: list[tuple[str, str, list[str]]] = []  # (section, heading line, body lines)
    for index in range(begin, end):
        line = lines[index]
        stripped = line.strip()
        is_heading = stripped and not line.startswith((" ", "-", "\t"))
        if is_heading:
            key = _SECTION_HEADINGS.get(stripped.lower())
            if key is None and _JIRA_HEADING.match(stripped):
                key = SECTION_JIRA
            if key is not None:
                sections.append((key, stripped, []))
                continue
        if sections:
            sections[-1][2].append(line)
        elif stripped:
            raise ParseError(f"line {index + 1}: text before the first section heading of the week: {stripped!r}")
    for key, heading, body in sections:
        text = _strip_blank(body)
        if key == SECTION_OUTCOMES:
            week.outcomes = text
        elif key == SECTION_ISSUES:
            week.issues = dedent_issues(text) if text else text
            week.targets = scan_targets(week.issues or "")
        else:
            found = _JIRA_HEADING.match(heading)
            assert found is not None
            week.jira_scope, week.jira_as_of = found["scope"], found["asof"]
            if week.jira_scope and tracker.jira_scope == DEFAULT_JIRA_SCOPE:
                tracker.jira_scope = week.jira_scope
            if sprint.status == "Closed":
                week.jira_frozen = heading + ("\n\n" + text if text else "")
                continue
            for item in parse_items(text or ""):
                if item.key not in seen_keys:
                    seen_keys.add(item.key)
                    sprint.items.append(item)


def parse_items(body: str) -> list[Item]:
    """The item blocks of a Jira section: key, type, (wrapped) title, the detail lines, the heading before them."""
    items: list[Item] = []
    pending: list[str] = []
    current: Item | None = None
    for line in body.splitlines():
        if not line.strip():
            continue
        found = _ITEM.match(line)
        if found:
            current = Item(found["key"], found["type"], found["title"], heading="\n".join(pending) or None)
            pending = []
            items.append(current)
            continue
        detail = _DETAIL.match(line)
        if detail and current is not None:
            label, value = detail["label"].strip(), detail["value"].strip()
            if label == "Jira status":
                current.jira_line = value
            elif label == "Note":
                current.note = value
            elif label == "Points":
                current.points = int(value) if value.isdigit() else None
            elif label.endswith(" target"):
                current.target = value
            else:
                current.note = f"{current.note}\n{label}: {value}" if current.note else f"{label}: {value}"
            continue
        if current is not None and line.startswith(TITLE_INDENT):
            current.title += "\n" + line[len(TITLE_INDENT):]
            continue
        if current is not None and line.startswith(DETAIL_INDENT):  # an unlabelled detail line continues the note
            current.note = f"{current.note}\n{line.strip()}" if current.note else line.strip()
            continue
        if line.startswith(KEY_INDENT):
            pending.append(line[len(KEY_INDENT):])
            current = None
    return items


def scan_targets(issues: str) -> list[Target]:
    """Bullets of the (dedented) Issues text that carry a ``... target:`` or an ``Ask:``, with the sub-heading above."""
    bullets: list[tuple[str | None, str]] = []
    under: str | None = None
    for line in issues.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and not line.startswith(" "):
            bullets.append((under, stripped[2:]))
        elif line.startswith(" ") and bullets:
            under_, text = bullets[-1]
            bullets[-1] = (under_, f"{text} {stripped}")
        else:
            under = stripped
    out: list[Target] = []
    for under_, text in bullets:
        target = _TARGET.search(text)
        ask = _ASK.search(text)
        if not target and not ask:
            continue
        title = re.split(r":|\s\(", text, maxsplit=1)[0].strip()
        out.append(Target(
            title, target["target"].strip() if target else None, ask["ask"].strip() if ask else None, under_,
        ))
    return out


# -- render --------------------------------------------------------------------------------
def timeline_title(phase_title: str) -> str:
    """``Functional Safety Concept (FSC)`` -> ``Functional Safety Concept``: the bullet adds its own parentheses."""
    return _TRAILING_PAREN.sub("", phase_title).strip()


def timeline_bullet(sprint: Sprint) -> str:
    """One TIMELINE bullet. A sprint without a lifecycle phase (the planner's, until the work is known) has no
    ``Phase n (title)`` head; the parser ignores a bullet it does not recognise, and such a sprint prints no
    block either, so it lives in the database, never in the text."""
    if sprint.phase_title:
        head = f"- Phase {sprint.phase_number} ({timeline_title(sprint.phase_title)}):"
    else:
        head = "- Phase to be assigned:"
    if sprint.status == "Closed":
        when = sprint.closed_on or sprint.end
        return f"{head} {sprint.target_label}: {_md(sprint.start)} - {_mdy(sprint.end)}. Closed {_md(when)}."
    if sprint.status == "Active":
        return f"{head} opened {_mdy(sprint.start)}. {sprint.target_label}: {_md(sprint.start)} - {_md(sprint.end)}."
    return f"{head} planned. {sprint.target_label}: {_md(sprint.start)} - {_md(sprint.end)}."


def render_jira(sprint: Sprint, as_of: dt.date, scope: str) -> str | None:
    """The Jira section of the sprint's items, or ``None`` when the sprint has none."""
    if not sprint.items:
        return None
    body: list[str] = []
    previous: str | None = None
    for item in sprint.items:
        if item.heading and item.heading != previous:
            body.extend(KEY_INDENT + line if line else "" for line in item.heading.splitlines())
            body.append("")
            previous = item.heading
        title_lines = item.title.splitlines() or [""]
        body.append(f"{KEY_INDENT}{item.key}  {item.issue_type or '':<5}  {title_lines[0]}")
        body.extend(TITLE_INDENT + line for line in title_lines[1:])
        if item.jira_line:
            body.append(f"{DETAIL_INDENT}Jira status: {item.jira_line}")
        if item.note:
            note_lines = item.note.splitlines()
            body.append(f"{DETAIL_INDENT}Note: {note_lines[0]}")
            body.extend(DETAIL_INDENT + line for line in note_lines[1:])
        if item.target:
            body.append(f"{DETAIL_INDENT}{sprint.target_label} target: {item.target}")
        if item.points:
            body.append(f"{DETAIL_INDENT}Points: {item.points}")
        body.append("")
    while body and not body[-1]:
        body.pop()
    return f"Jira issues ({scope}, as of {_md(as_of)})\n\n" + "\n".join(body)


def render_week(week: Week, sprint: Sprint, as_of: dt.date, jira_scope: str, *, with_jira: bool) -> list[str]:
    heading = f"WEEK OF {_md(week.start)} - {_md(week.end)}"
    if week.note:
        heading += f"   ({week.note})"
    blocks: list[str] = []
    if week.outcomes is not None:
        label = "Outcomes so far" if week.is_current(as_of) and sprint.status != "Closed" else "Outcomes"
        blocks.append(f"{label}\n{week.outcomes}")
    if week.issues is not None:
        blocks.append(f"Miscellaneous issues\n\n{indent_issues(week.issues)}")
    if week.jira_frozen:
        blocks.append(week.jira_frozen)
    elif with_jira and sprint.status != "Closed":
        jira = render_jira(sprint, as_of, jira_scope)
        if jira:
            blocks.append(jira)
    out = ["", heading]
    if blocks:
        out += ["", "\n\n".join(blocks)]
    return out


def has_content(sprint: Sprint) -> bool:
    """A sprint the text tells about: started or closed, or planned with weeks or items. A planned sprint
    with nothing in it (the planner's) adds no ``=====`` block; the TIMELINE names the next one only."""
    return sprint.status != "Planned" or bool(sprint.weeks) or bool(sprint.items)


def timeline_sprints(sprints: list[Sprint]) -> list[Sprint]:
    """The sprints the TIMELINE lists, in order: every one with content, plus the next planned sprint (the
    earliest planned one without content), so seventy planned sprints are one bullet, not seventy."""
    ordered = sorted(sprints, key=lambda s: (s.start, s.number or 0))
    listed = [s for s in ordered if has_content(s)]
    upcoming = [s for s in ordered if not has_content(s)]
    if upcoming:
        listed.append(upcoming[0])
    return sorted(listed, key=lambda s: (s.start, s.number or 0))


def render(tracker: Tracker, as_of: dt.date, *, current_only: bool = False) -> str:
    """The whole tracker (newest sprint and week first), or with ``current_only`` the active sprint's current week."""
    out = [tracker.title, f"{tracker.byline}. Newest week at the top. Last updated {_mdy(as_of)}.", "", "TIMELINE"]
    out.extend(timeline_bullet(s) for s in timeline_sprints(tracker.sprints))
    if tracker.scope:
        out.append(f"- Scope: {tracker.scope}")
    sprints = sorted(
        (s for s in tracker.sprints if has_content(s)), key=lambda s: (s.start, s.number or 0), reverse=True
    )
    if current_only:
        sprints = [s for s in sprints if s.status == "Active"][:1]
    for sprint in sprints:
        out += ["", RULE, sprint.heading, RULE]
        if sprint.goal:
            out.append(f"Goal: {sprint.goal}")
        if sprint.summary:
            out.append(sprint.summary)
        weeks = sorted(sprint.weeks, key=lambda w: w.start, reverse=True)
        if current_only:
            weeks = [w for w in weeks if w.start <= as_of][:1]
        for position, week in enumerate(weeks):
            out += render_week(week, sprint, as_of, tracker.jira_scope, with_jira=position == 0)
    return "\n".join(out) + "\n"
