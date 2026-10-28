"""TrackerService: the Weekly Activity Tracker between the database and its text file.

``import_file`` reads the engineer's file once (``tracker/format.py`` is the grammar) into sprints,
sprint items and weeks; ``build`` writes the history or the current week back out, a view like the
workbook and the documents, never read back. ``--jira`` on a build refreshes the Jira lines of the
active sprint's items through ``jira live``; that is the only time Jira facts are written, and what
is written is the engineer's report line, not a cache.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from ..generate import plan_queries as pq
from ..generate import sprint_queries as q
from ..tracker import format as fmt
from ..tracker.format import Item, Sprint, Tracker, Week

if TYPE_CHECKING:
    from ..brain import Brain

KINDS = ("history", "week")
STEMS = {"history": "tracker_history", "week": "tracker_week"}
SECTIONS_ADDABLE = (fmt.SECTION_OUTCOMES, fmt.SECTION_ISSUES, fmt.SECTION_NOTE)


class TrackerService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- configuration ---------------------------------------------------------------
    @property
    def title(self) -> str:
        return self.brain.config.get("tracker_title") or fmt.DEFAULT_TITLE

    @property
    def byline(self) -> str:
        return self.brain.config.get("tracker_byline") or fmt.DEFAULT_BYLINE

    @property
    def scope(self) -> str | None:
        return self.brain.config.get("tracker_scope") or None

    @property
    def jira_scope(self) -> str:
        return self.brain.config.get("tracker_jira_scope") or fmt.DEFAULT_JIRA_SCOPE

    # -- import ------------------------------------------------------------------------------
    def import_file(self, path: str | Path, mode: str | None = None, actor: str = "import") -> dict[str, Any]:
        """Read the tracker text into the three entities. ``replace`` wipes first; ``merge`` matches rows.

        Without ``mode``: ``replace`` into an empty tracker, ``merge`` otherwise. A second import of
        the same file reports ``unchanged``.
        """
        file = Path(path)
        if not file.is_file():
            raise CommandError(f"no such file: {file}")
        try:
            parsed = fmt.parse(file.read_text(encoding="utf-8"))
        except fmt.ParseError as exc:
            raise CommandError(f"{file.name}: {exc}") from None
        warnings: list[str] = []
        existing = q.sprints(self.brain)
        if mode is None:
            mode = "replace" if not existing else "merge"
        if mode not in ("replace", "merge"):
            raise CommandError(f"mode must be replace or merge, not {mode!r}")
        sprint_rows, item_rows, week_rows = self._rows_from(parsed, existing if mode == "merge" else [], warnings)
        if self.scope is None and parsed.scope:
            warnings.append(f"the file's scope line is not in kletz.toml; set tracker_scope = {parsed.scope!r}")
        if parsed.jira_scope != self.jira_scope:
            warnings.append(f"the file's Jira heading says {parsed.jira_scope!r}; set tracker_jira_scope to keep it")
        if self.byline != parsed.byline:
            warnings.append(f"the file's byline {parsed.byline!r} is not in kletz.toml; set tracker_byline to keep it")
        counts: dict[str, dict[str, int]] = {}
        if mode == "replace":
            for entity, rows in ((q.SPRINT, sprint_rows), (q.ITEM, item_rows), (q.WEEK, week_rows)):
                summary = self.brain.service(entity).load_rows(rows, "replace", actor)
                counts[entity] = {"created": summary["inserted"], "updated": 0, "unchanged": 0}
                warnings.extend(summary["warnings"])
                if summary["errors"]:
                    raise CommandError("; ".join(summary["errors"]))
        else:
            counts[q.SPRINT] = self._sync(q.SPRINT, sprint_rows, _sprint_key, actor)
            counts[q.ITEM] = self._sync(q.ITEM, item_rows, _item_key, actor)
            counts[q.WEEK] = self._sync(q.WEEK, week_rows, lambda r: (r["start"], r["section"]), actor)
        changed = any(c["created"] or c["updated"] for c in counts.values())
        data = {
            "path": str(file), "mode": mode, "unchanged": not changed, "entities": counts,
            "sprints": len(sprint_rows), "items": len(item_rows), "weeks": len({r["start"] for r in week_rows}),
            "scope": parsed.scope, "byline": parsed.byline,
            "updated": parsed.updated.isoformat() if parsed.updated else None,
        }
        self.brain.events.publish("tracker.imported", path=str(file), mode=mode, unchanged=not changed, actor=actor)
        return {**data, "warnings": warnings}

    def _rows_from(
        self, parsed: Tracker, existing: list[dict[str, Any]], warnings: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        by_key = {(s.get("lifecycle_phase"), s.get("label")): s for s in existing}
        next_number = max((s["number"] for s in existing), default=0) + 1
        plan_rows = pq.all_rows(self.brain)
        sprint_rows: list[dict[str, Any]] = []
        item_rows: list[dict[str, Any]] = []
        week_rows: list[dict[str, Any]] = []
        for sprint in sorted(parsed.sprints, key=lambda s: s.start):
            try:
                phase = pq.resolve_phase(self.brain, sprint.phase_number)
            except CommandError as exc:
                raise CommandError(f"sprint {sprint.heading!r}: {exc}") from None
            known = by_key.get((phase, sprint.label))
            number = known["number"] if known else next_number
            if not known:
                next_number += 1
            sprint.number = number
            sprint_rows.append({
                "number": number, "label": sprint.label, "lifecycle_phase": phase, "start": sprint.start.isoformat(),
                "end": sprint.end.isoformat(), "capacity": (known or {}).get("capacity") or self.brain.sprint_capacity,
                "status": sprint.status, "closed_on": sprint.closed_on.isoformat() if sprint.closed_on else None,
            })
            order = 0
            for item in sprint.items:
                order += 1
                item_rows.append({
                    "sprint": number, "order": order, "kind": "Jira", "title": item.title, "jira_key": item.key,
                    "issue_type": item.issue_type, "heading": item.heading, "points": item.points,
                    "target": item.target, "note": item.note, "jira_line": item.jira_line, "status": "To Do",
                })
            for week in sorted(sprint.weeks, key=lambda w: w.start):
                for target in week.targets:
                    order += 1
                    item_rows.append(self._target_row(number, order, target, plan_rows, warnings))
                for section, text in (
                    (fmt.SECTION_NOTE, week.note), (fmt.SECTION_OUTCOMES, week.outcomes),
                    (fmt.SECTION_ISSUES, week.issues), (fmt.SECTION_JIRA, week.jira_frozen),
                ):
                    if text is None:
                        continue
                    week_rows.append({
                        "start": week.start.isoformat(), "sprint": number, "section": section,
                        "order": fmt.SECTION_ORDER[section], "text": text,
                    })
        return sprint_rows, item_rows, week_rows

    def _target_row(
        self, number: int, order: int, target: fmt.Target, plan_rows: list[dict[str, Any]], warnings: list[str]
    ) -> dict[str, Any]:
        row: dict[str, Any] = {"sprint": number, "order": order, "title": target.title, "status": "To Do"}
        if target.ask and not target.target:
            row.update({"kind": "Question", "title": target.ask, "note": target.title})
            return row
        row["target"] = target.target
        if target.ask:
            row["note"] = f"Ask: {target.ask}"
        if target.under and "people" in target.under.lower():
            row["kind"] = "Meeting"
            return row
        match = match_deliverable(target.title, plan_rows)
        if match is None:
            row["kind"] = "Other"
            warnings.append(f"no Safety Plan row matches {target.title!r}; imported as Other")
        else:
            row.update({"kind": "Deliverable", "plan_row": match["id"], "title": pq.one_line(match["deliverable"])})
        return row

    def _sync(self, entity: str, desired: list[dict[str, Any]], key, actor: str) -> dict[str, int]:
        service = self.brain.service(entity)
        index: dict[Any, dict[str, Any]] = {}
        for row in service.list():
            index.setdefault(key(row), row)
        counts = {"created": 0, "updated": 0, "unchanged": 0}
        for row in desired:
            current = index.get(key(row))
            if current is None:
                service.create(row, actor)
                counts["created"] += 1
                continue
            delta = {k: v for k, v in row.items() if current.get(k) != v and not (v is None and current.get(k) is None)}
            if delta:
                service.update(current["id"], delta, actor)
                counts["updated"] += 1
            else:
                counts["unchanged"] += 1
        return counts

    # -- model from rows -----------------------------------------------------------------------
    def tracker(self, as_of: dt.date) -> Tracker:
        """The whole tracker as ``format`` wants it, from the database."""
        tracker = Tracker(self.title, self.byline, self.scope, self.jira_scope)
        all_weeks = q.weeks(self.brain)
        for row in q.sprints(self.brain):
            phase = row.get("lifecycle_phase") or ""
            sprint = Sprint(
                pq.phase_number(phase) or str(row["number"]), pq.phase_title(phase) or phase,
                row.get("label") or f"SPRINT {row['number']}", q.parse_date(row.get("start") or as_of),
                q.parse_date(row.get("end") or as_of), row.get("status") or "Planned",
                closed_on=q.parse_date(row["closed_on"]) if row.get("closed_on") else None,
                goal=pq.one_line(row.get("goal")) or None, number=row["number"],
            )
            board = q.board(self.brain, row, as_of)
            sprint.summary = q.summary_line(board)
            sprint.items = [
                Item(r["jira_key"], r.get("issue_type"), r.get("title") or "", r.get("jira_line"), r.get("note"),
                     r.get("target"), r.get("points"), r.get("heading"), id=r["id"])
                for r in board["items"]
                if r.get("kind") == "Jira" and r.get("jira_key") and r.get("status") != "Carried"
            ]
            for start, rows in all_weeks.items():
                if rows[0]["sprint"] != row["number"]:
                    continue
                week = Week(q.parse_date(start))
                for section_row in rows:
                    section, text = section_row.get("section"), section_row.get("text")
                    if section == fmt.SECTION_NOTE:
                        week.note = text
                    elif section == fmt.SECTION_OUTCOMES:
                        week.outcomes = text
                    elif section == fmt.SECTION_ISSUES:
                        week.issues = text
                    elif section == fmt.SECTION_JIRA:
                        week.jira_frozen = text
                sprint.weeks.append(week)
            tracker.sprints.append(sprint)
        return tracker

    # -- build ------------------------------------------------------------------------------------
    def render(self, kind: str, as_of: Any = None) -> tuple[str, dict[str, Any]]:
        if kind not in KINDS:
            raise CommandError(f"kind must be history or week, not {kind!r}")
        day = q.as_of_date(as_of)
        tracker = self.tracker(day)
        info: dict[str, Any] = {"kind": kind, "as_of": day.isoformat()}
        if kind == "week":
            active = next((s for s in tracker.sprints if s.status == "Active"), None)
            if active is None:
                raise CommandError("no active sprint; run `sprint start`")
            weeks = [w for w in sorted(active.weeks, key=lambda w: w.start, reverse=True) if w.start <= day]
            if not weeks:
                raise CommandError(f"sprint {active.number} has no week on or before {day.isoformat()}; add one")
            info.update({"sprint": active.number, "week": weeks[0].start.isoformat()})
        return fmt.render(tracker, day, current_only=kind == "week"), info

    def build(
        self, kind: str, out_dir: str | Path | None = None, as_of: Any = None, jira: bool = False, actor: str = "python"
    ) -> dict[str, Any]:
        """Write ``<out>/tracker_<kind>.txt`` and return its path, the numbers and any warnings."""
        warnings: list[str] = []
        if jira:
            warnings.extend(self.refresh_jira(actor=actor))
        text, info = self.render(kind, as_of)
        folder = Path(out_dir or self.brain.out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{STEMS[kind]}.txt"
        try:
            target.write_text(text, encoding="utf-8", newline="\n")
        except PermissionError:
            alt = folder / f"{STEMS[kind]}_{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            alt.write_text(text, encoding="utf-8", newline="\n")
            warnings.append(f"{target.name} is locked (open in another program); wrote {alt.name} instead")
            target = alt
        data = {
            **info, "name": STEMS[kind], "path": str(target), "primary": str(target), "lines": text.count("\n"),
            "out_dir": str(folder), "jira_refreshed": bool(jira),
        }
        payload = {"kind": "tracker", "name": STEMS[kind], "params": {"as_of": info["as_of"]}, "primary": str(target)}
        with self.brain.storage.transaction():
            self.brain.storage.audit(actor, "generate", "tracker", None, payload)
        self.brain.events.publish("generated", actor=actor, paths={"txt": str(target)}, **payload)
        return {**data, "warnings": warnings}

    # -- jira -----------------------------------------------------------------------------------
    def refresh_jira(self, number: int | None = None, *, actor: str = "python") -> list[str]:
        """One ``jira live`` for the sprint's keys; ``title``, ``issue_type`` and ``jira_line`` of each item follow."""
        sprint = q.sprint_by_number(self.brain, number)
        rows = [r for r in q.items(self.brain, sprint["number"]) if r.get("jira_key") and r.get("status") != "Carried"]
        if not rows:
            return [f"sprint {sprint['number']} has no Jira items to refresh"]
        keys = sorted({r["jira_key"] for r in rows})
        try:
            live = self.brain.jira.live(f"key in ({', '.join(keys)}) ORDER BY key ASC", limit=len(keys) + 1)
        except CommandError as exc:
            return [f"Jira not fetched; lines as last seen ({exc})"]
        by_key = {issue["key"]: issue for issue in live["issues"]}
        service = self.brain.service(q.ITEM)
        warnings: list[str] = []
        for row in rows:
            issue = by_key.get(row["jira_key"])
            if issue is None:
                warnings.append(f"{row['jira_key']}: not returned by Jira; line as last seen")
                continue
            line = (
                f"{issue.get('status') or '?'} | Priority: {issue.get('priority') or '-'}"
                f" | Assignee: {issue.get('assignee') or 'Unassigned'}"
            )
            delta = {"jira_line": line, "issue_type": issue.get("issue_type") or row.get("issue_type"),
                     "title": issue.get("summary") or row.get("title")}
            delta = {k: v for k, v in delta.items() if row.get(k) != v}
            if delta:
                service.update(row["id"], delta, actor)
        return warnings

    def freeze_jira(self, number: int, as_of: dt.date, actor: str = "python") -> dict[str, Any] | None:
        """Write the sprint's Jira section into its newest week as a ``Jira`` row, so history stops moving."""
        tracker = self.tracker(as_of)
        sprint = next((s for s in tracker.sprints if s.number == number), None)
        if sprint is None or not sprint.weeks or not sprint.items:
            return None
        newest = max(sprint.weeks, key=lambda w: w.start)
        if newest.jira_frozen:
            return None
        text = fmt.render_jira(sprint, as_of, tracker.jira_scope)
        if not text:
            return None
        row, _ = self.brain.service(q.WEEK).create({
            "start": newest.start.isoformat(), "sprint": number, "section": fmt.SECTION_JIRA,
            "order": fmt.SECTION_ORDER[fmt.SECTION_JIRA], "text": text,
        }, actor)
        return row

    # -- add ----------------------------------------------------------------------------------------
    def add_line(
        self, text: str, section: str = fmt.SECTION_OUTCOMES, week: Any = None, as_of: Any = None, actor: str = "python"
    ) -> dict[str, Any]:
        """Append ``text`` to a section of a week (the current one by default); a new week joins the active sprint."""
        if section not in SECTIONS_ADDABLE:
            raise CommandError(f"section must be one of {', '.join(SECTIONS_ADDABLE)}, not {section!r}")
        text = text.rstrip()
        if not text.strip():
            raise CommandError("nothing to add")
        day = q.as_of_date(as_of)
        start = q.parse_date(week, "week") if week else q.week_start(day)
        service = self.brain.service(q.WEEK)
        rows = service.list(filters={"start": start.isoformat(), "section": section})
        if rows:
            current = rows[0].get("text") or ""
            row, _ = service.update(rows[0]["id"], {"text": f"{current}\n{text}" if current else text}, actor)
            return row
        sprint_rows = service.list(filters={"start": start.isoformat()})
        number = sprint_rows[0]["sprint"] if sprint_rows else q.sprint_by_number(self.brain, None)["number"]
        row, _ = service.create({
            "start": start.isoformat(), "sprint": number, "section": section, "order": fmt.SECTION_ORDER[section],
            "text": text,
        }, actor)
        return row


def _sprint_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("lifecycle_phase"), row.get("label"))


def _item_key(row: dict[str, Any]) -> tuple[Any, ...]:
    if row.get("jira_key"):
        return (row["sprint"], row["jira_key"], None)
    return (row["sprint"], None, (row.get("kind"), row["title"]))


def match_deliverable(title: str, plan_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """A plan row whose deliverable equals ``title`` (case and spacing aside), else the one it is a prefix of."""
    wanted = " ".join(title.casefold().split())
    if not wanted:
        return None
    normalised = [(" ".join(str(r.get("deliverable") or "").casefold().split()), r) for r in plan_rows]
    exact = [r for text, r in normalised if text == wanted]
    if len(exact) == 1:
        return exact[0]
    prefixed = [r for text, r in normalised if text.startswith(wanted)]
    return prefixed[0] if len(prefixed) == 1 else None
