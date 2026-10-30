"""StandardsService: the parametrised standards (asi_standards) a Safety Plan row can be exported into.

A *standard* is one folder of the standards directory (``standards_dir`` in kletz.toml, default
``../asi_standards`` beside the repo) holding a Gutenberg Markdown source of the same name
(``qf-17-safety-plan/qf-17-safety-plan.md``): a controlled QMS document whose blanks are ``{{ name }}``
parameters. A person supplies the document-level ones (``vehicle_type``, the roles) once, through the
``parameter`` entity; Kletz supplies the row-level ones (``row_N_points``, ``row_N_sprint_end``,
``row_N_jira_key``, ``row_N_status``, and since 0.20.0 ``row_N_url`` and ``row_N_urls``, the work product's
links, N the plan row's order) from the plan and from Jira. A plan row has a standard when one
of its QMS reference flags (``ref_qf_17``) names a folder that starts with that QMS id in slug form
(``qf-17-...``).

The owner, 2026-10-29: the Expected Duration/Deadline is "x points" (the chosen points, never the default)
then the date the sprint is expected to conclude; the Status is the status of the Jira ticket tied to the
deliverable, not the spreadsheet's names. asi_gutenberg is imported inside the methods that need it, so
``import asi_kletz`` never loads it.

0.19.0, the owner: "each safety deliverable can have multiple authors, so for any safety case field, instead
of the parameter being a string it is now an array of human names sorted alphabetically; also must include
email alongside name." A role parameter (``schema.people.is_role``) holds ``people``; its ``value`` is a
legacy string written before 0.19.0 (a name with no email yet), kept, printed verbatim and replaced the moment
people are saved. A role renders inline as ``Ann Lee (ann@...), Ben Ray (ben@...)``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound, ValidationError
from ..generate import plan_queries as pq
from ..generate.plan_schedule import SOURCE_FLOOR, weight_of
from ..schema.definitions import NO_TICKET, ROLE_SLUGS
from ..schema.people import PeopleError, is_role, parse_people, people_json, people_of, render_people
from ..schema.urls import urls_of

if TYPE_CHECKING:
    from ..brain import Brain

PARAMETER = "parameter"
ROW_PARAM = re.compile(r"^row_(\d+)_(points|sprint_end|jira_key|status|url|urls)$")
PARAM_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
UNFILLED = "unfilled parameter: "
STATUS_NOT_FETCHED = "status not fetched (sign in to Jira)"  # 0.25.1: what the Status cell says offline
ABRIDGED_HEADERS = "abridged-headers.json"  # beside the source: verbatim column heading -> short form (0.21.0)
ABRIDGE_NEEDS_WORD = "abridged headers"  # how asi_gutenberg's issue starts when Word could not run the pass
NO_STANDARD = "No standard for this deliverable: its QMS references name none in {root}"
NO_EMAIL_YET = "a legacy value with no email yet"
LEGACY, PEOPLE, EMPTY = "legacy", "people", "empty"  # the three states of a role (``role_summary``)


@dataclass
class Standard:
    folder: str
    path: Path
    title: str
    parameters: list[str] = field(default_factory=list)
    template: Path | None = None  # the Word original under source/, when the folder holds exactly one (0.16.0)
    abridged_headers: Path | None = None  # abridged-headers.json beside the source, when there is one (0.21.0)

    @property
    def document_parameters(self) -> list[str]:
        """The names a person supplies: everything that is not a row parameter."""
        return [p for p in self.parameters if not ROW_PARAM.match(p)]

    @property
    def row_parameters(self) -> list[str]:
        """The names Kletz supplies: ``row_N_points``, ``row_N_sprint_end``, ``row_N_jira_key``, ``row_N_status``,
        ``row_N_url`` and ``row_N_urls`` (0.20.0)."""
        return [p for p in self.parameters if ROW_PARAM.match(p)]

    @property
    def role_parameters(self) -> list[str]:
        """The document parameters that are roles (0.19.0): each holds people, name and email, alphabetical."""
        return [p for p in self.document_parameters if is_role(p)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder": self.folder, "path": str(self.path), "title": self.title,
            "template": str(self.template) if self.template else None,
            "abridged_headers": str(self.abridged_headers) if self.abridged_headers else None,
            "parameters": len(self.parameters), "document_parameters": self.document_parameters,
            "role_parameters": self.role_parameters, "row_parameters": len(self.row_parameters),
        }


def qms_slug(flag_name: str) -> str:
    """``ref_qf_17`` -> ``qf_17``: the QMS id a reference flag names, in slug form."""
    return flag_name[4:] if flag_name.startswith("ref_") else flag_name


def folder_names(folder: str, slug: str) -> bool:
    """Whether a standard's folder (``qf-17-safety-plan``) starts with the QMS id ``qf_17``: equal, or the id
    followed by a separator, never a longer id (``qf_170``)."""
    normalised = folder.lower().replace("-", "_")
    return normalised == slug or normalised.startswith(slug + "_")


class StandardsService:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- the folder ---------------------------------------------------------------------------
    def root(self) -> Path:
        return Path(self.brain.standards_dir)

    def list(self) -> list[Standard]:
        """Every subfolder of the standards directory holding a Markdown file of the same name, by folder."""
        root = self.root()
        if not root.is_dir():
            return []
        out: list[Standard] = []
        for folder in sorted(p for p in root.iterdir() if p.is_dir()):
            source = folder / f"{folder.name}.md"
            if source.is_file():
                out.append(self.load(folder.name))
        return out

    def load(self, folder: str) -> Standard:
        """One standard, its title from the front matter and its parameters through asi_gutenberg."""
        source = self.root() / folder / f"{folder}.md"
        if not source.is_file():
            known = ", ".join(s.folder for s in self.list()) or "none"
            raise NotFound(f"no standard {folder!r} in {self.root()}; known: {known}")
        from asi_gutenberg import from_markdown, parameters

        doc = from_markdown(source.read_text(encoding="utf-8"))
        originals = sorted((source.parent / "source").glob("*.docx")) if (source.parent / "source").is_dir() else []
        template = originals[0] if len(originals) == 1 else None
        abridged = source.parent / ABRIDGED_HEADERS
        return Standard(folder, source, str(doc.title or folder), parameters(doc), template,
                        abridged if abridged.is_file() else None)

    def for_row(self, row: dict[str, Any]) -> list[Standard]:
        """The standards a plan row has: those whose folder a set QMS reference flag of the row names."""
        schema = self.brain.registry.get(pq.PLAN_ENTITY)
        slugs = [qms_slug(s.name) for s in schema.fields if s.group == "reference" and s.is_flag and row.get(s.name)]
        return [s for s in self.list() if any(folder_names(s.folder, slug) for slug in slugs)]

    # -- the parameter entity's rule -----------------------------------------------------------
    def parameter_guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> list[str]:
        """A parameter's name is unique within its standard (``""`` is the standard of every document).

        0.19.0, the people rule: a role parameter holds ``people`` (parsed from the API's array, its JSON text
        or the ``Name <email>; ...`` text; validated, stored sorted), never a value: the moment people are
        saved the ``value`` is cleared (a differing value sent in the same call is ignored with a warning), and
        a value on a role that already holds people is refused. A value on a role that has no people (a name
        with no email yet, as every role was before 0.19.0) is kept with a warning; people on a parameter that
        is not a role are refused. Returns the warnings."""
        name = clean.get("name", (current or {}).get("name"))
        standard = clean.get("standard", (current or {}).get("standard")) or ""
        if name is not None and not PARAM_NAME.match(str(name)):
            raise ValidationError(PARAMETER, [f"name: {name!r} is not a parameter name ([a-z_][a-z0-9_]*)"])
        if "standard" in clean and clean["standard"] is None:
            clean["standard"] = ""
        for other in self.brain.service(PARAMETER).list(filters={"name": name}):
            if (other.get("standard") or "") == standard and (current is None or other["id"] != current["id"]):
                where = f"standard {standard!r}" if standard else "every standard"
                raise ValidationError(PARAMETER, [f"parameter {name!r} already exists for {where} (row {other['id']})"])
        return self._people_rule(str(name), current, clean)

    def _people_rule(self, name: str, current: dict[str, Any] | None, clean: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        role = is_role(name)
        if "people" in clean:
            if clean["people"] in (None, "", "[]"):
                clean["people"] = None
            elif not role:
                raise ValidationError(PARAMETER, [
                    f"{name} is not a role: it holds a value, not people (the roles: {', '.join(ROLE_SLUGS)})"
                ])
            else:
                try:
                    clean["people"] = people_json(parse_people(clean["people"], name))
                except PeopleError as exc:
                    raise ValidationError(PARAMETER, exc.errors) from None
        people_now = bool(clean["people"]) if "people" in clean else bool((current or {}).get("people"))
        value_given = clean.get("value") not in (None, "")
        if people_now and value_given:
            if "people" in clean:  # people saved: they replace the value, whatever was sent with them
                if clean["value"] != (current or {}).get("value"):
                    warnings.append(f"{name}: the value {clean['value']!r} is ignored; a role holds people")
                clean["value"] = None
            else:
                raise ValidationError(PARAMETER, [
                    f"{name} holds people: set people (Name <email>; ...) instead of a value, or clear them first"
                ])
        elif people_now and "people" in clean:
            clean["value"] = None  # replaced the moment people are saved
        elif role and value_given and not people_now:
            warnings.append(
                f"{name}: a role holds people (Name <email>; ...); {clean['value']!r} is kept as {NO_EMAIL_YET}"
            )
        return warnings

    def parameter_loaded(self, clean: dict[str, Any]) -> list[str]:
        """A row of a dump or a workbook (``EntityService.load_rows`` runs no guard): its people parsed,
        validated and sorted as on a create; a bad people value is dropped with the messages as warnings, so
        the row still loads; people on a name that is not a role are dropped too; people clear the value."""
        warnings: list[str] = []
        name = str(clean.get("name") or "")
        if clean.get("people") in (None, "", "[]"):
            clean["people"] = None
            return warnings
        if not is_role(name):
            warnings.append(f"{name}: people ignored, not a role")
            clean["people"] = None
            return warnings
        try:
            clean["people"] = people_json(parse_people(clean["people"], name))
        except PeopleError as exc:
            warnings.extend(f"{e}; people ignored" for e in exc.errors)
            clean["people"] = None
        if clean["people"]:
            clean["value"] = None
        return warnings

    # -- the values ------------------------------------------------------------------------------------
    def document_rows(self, standard: Standard) -> dict[str, dict[str, Any]]:
        """The ``parameter`` row per name a standard sees: every row whose standard is empty or this one, the
        standard's own row winning over the global one."""
        rows: dict[str, dict[str, Any]] = {}
        for row in self.brain.service(PARAMETER).list(order_by=("standard", "name", "id")):
            if (row.get("standard") or "") in ("", standard.folder):
                rows[row["name"]] = row  # "" sorts first, so a standard's own row overwrites the global one
        return rows

    @staticmethod
    def parameter_text(row: dict[str, Any]) -> str:
        """What a parameter row fills: its people rendered inline, alphabetical, ``Name (email)`` joined by
        ``, ``; else its value verbatim (a plain parameter, or a role's legacy name); ``""`` for nothing."""
        if row.get("people"):
            return render_people(row["people"])
        value = row.get("value")
        return "" if value in (None, "") else str(value)

    def document_values(self, standard: Standard) -> dict[str, str]:
        """The document-level values a standard fills: ``parameter_text`` per row, the empty ones left out."""
        values: dict[str, str] = {}
        for name, row in self.document_rows(standard).items():
            text = self.parameter_text(row)
            if text:
                values[name] = text
        return values

    def role_summary(self, standard: Standard) -> dict[str, Any]:
        """Per role of the standard: how many people, their names, and the state: ``people``, ``legacy`` (a
        value with no email yet, printed verbatim) or ``empty`` (no one: the blank stays unfilled); plus the
        roles still legacy and the roles still empty, as lists."""
        rows = self.document_rows(standard)
        roles: dict[str, dict[str, Any]] = {}
        for name in standard.role_parameters:
            row = rows.get(name) or {}
            people = people_of(row.get("people")) if row.get("people") else []
            if people:
                roles[name] = {
                    "state": PEOPLE, "people": len(people), "names": [p.name for p in people], "legacy": None,
                }
            elif row.get("value") not in (None, ""):
                roles[name] = {"state": LEGACY, "people": 0, "names": [], "legacy": str(row["value"])}
            else:
                roles[name] = {"state": EMPTY, "people": 0, "names": [], "legacy": None}
        return {
            "roles": roles,
            "legacy_roles": [n for n, r in roles.items() if r["state"] == LEGACY],
            "empty_roles": [n for n, r in roles.items() if r["state"] == EMPTY],
        }

    @staticmethod
    def role_warnings(folder: str, summary: dict[str, Any]) -> list[str]:
        """One line for the roles still legacy, one for the roles with no one."""
        out = []
        if summary["legacy_roles"]:
            out.append(f"{folder}: {len(summary['legacy_roles'])} role(s) with {NO_EMAIL_YET} (printed verbatim): "
                       + ", ".join(summary["legacy_roles"]))
        if summary["empty_roles"]:
            out.append(f"{folder}: {len(summary['empty_roles'])} role(s) with no one (left unfilled): "
                       + ", ".join(summary["empty_roles"]))
        return out

    def row_values(
        self, rows: list[dict[str, Any]], statuses: dict[str, str | None], warnings: list[str] | None = None
    ) -> dict[str, str]:
        """``row_N_points``, ``row_N_sprint_end``, ``row_N_jira_key``, ``row_N_status``, ``row_N_url`` and
        ``row_N_urls`` for every plan row that has an order.

        The points are the weight the schedule used for the row, as ``plan_schedule.weight_of`` resolves it
        (the owner's revision of 2026-10-29): the chosen ``points`` when set, else the row's
        ``default_points``; only a row with neither (the scheduler fell back to the floor) stays unfilled,
        with one warning naming the rows. So the points and the sprint end printed under them agree. The
        status is the Jira status of the row's key, ``status not fetched (sign in to Jira)`` when the read
        failed (0.25.1); a row without a ticket prints ``no ticket attached`` as its key and an empty status,
        never a placeholder. The key is the row's ``jira_key``
        upper-cased, the part before a colon when one was typed (the owner, 2026-10-29: "the prefix before
        the colon of the assigned Jira ticket name", stacked over the status in the Status column). The url is
        the row's first work product URL (0.20.0, the owner: "on multiple urls just go to first"), the urls
        every one of them joined by a line break; a row with none leaves both unfilled.
        """
        values: dict[str, str] = {}
        floored: list[str] = []
        for row in rows:
            order = row.get("order")
            if order is None:
                continue
            weight, source = weight_of(row, self.brain.default_points)
            if source == SOURCE_FLOOR:
                floored.append(str(order))
            else:
                values[f"row_{order}_points"] = str(weight)
            if row.get("sprint_end"):
                values[f"row_{order}_sprint_end"] = str(row["sprint_end"])
            key = (row.get("jira_key") or "").strip().upper()
            if key:
                values[f"row_{order}_jira_key"] = key.split(":", 1)[0].strip()
                values[f"row_{order}_status"] = str(statuses[key]) if statuses.get(key) else STATUS_NOT_FETCHED
            else:  # 0.25.1: a readable cell, never a placeholder, where there is no ticket or no session
                values[f"row_{order}_jira_key"] = NO_TICKET
                values[f"row_{order}_status"] = ""
            urls = urls_of(row.get("urls"))
            if urls:
                values[f"row_{order}_url"] = urls[0]
                values[f"row_{order}_urls"] = "\n".join(urls)
        if floored and warnings is not None:
            warnings.append(
                f"row(s) {', '.join(floored)} have neither points nor a default: their points stay unfilled"
            )
        return values

    def jira_statuses(self, rows: list[dict[str, Any]], warnings: list[str]) -> dict[str, str | None]:
        """One non-interactive Hopper read per distinct Jira key of the rows; offline means nothing, with one
        warning naming the keys skipped; rows without a key are named in another."""
        keys = sorted({(r.get("jira_key") or "").strip().upper() for r in rows if (r.get("jira_key") or "").strip()})
        without = [str(r.get("order") or r["id"]) for r in rows if not (r.get("jira_key") or "").strip()]
        if without:
            warnings.append(f"row(s) {', '.join(without)} have no Jira key: their status stays unfilled")
        if not keys:
            return {}
        try:
            return self.brain.jira.statuses(keys)
        except CommandError as exc:
            warnings.append(f"Jira statuses skipped ({exc}): {', '.join(keys)}")
            return {}

    def value_set(self, row_id: int, standard: str | None = None) -> dict[str, Any]:
        """What an export of ``row_id`` would fill, per standard, without building anything."""
        row = self.brain.service(pq.PLAN_ENTITY).get(row_id)
        standards = [self.load(standard)] if standard else self.for_row(row)
        if not standards:
            raise CommandError(NO_STANDARD.format(root=self.root()) + f" (row {row_id})")
        rows = pq.all_rows(self.brain)
        warnings: list[str] = []
        statuses = self.jira_statuses(rows, warnings)
        row_values = self.row_values(rows, statuses, warnings)
        out = []
        for std in standards:
            values = {**self.document_values(std), **row_values}
            used = {name: values[name] for name in std.parameters if name in values}
            summary = self.role_summary(std)
            warnings.extend(self.role_warnings(std.folder, summary))
            out.append({
                **std.to_dict(), "values": used, **summary,
                "filled": len(used), "unfilled": [name for name in std.parameters if name not in values],
            })
        return {"row": row_id, "order": row.get("order"), "standards": out, "statuses": statuses, "warnings": warnings}

    # -- the export ------------------------------------------------------------------------------------
    def export(
        self, row_id: int, out_dir: str | Path | None = None, standard: str | None = None, actor: str = "python"
    ) -> dict[str, Any]:
        """Build each standard of the row (or the one named) with asi_gutenberg, the parameters filled from
        the ``parameter`` table, the plan and Jira, the rest left and reported; audited once.

        The Markdown is always written (the filled source, its values marked). When the standard's folder
        holds the Word original under ``source/`` (0.16.0, the owner: "match the template exactly"), the
        Word file is that original filled in place, every filled value shaded the theme's green (0.17.0, the
        owner: "bring back the color formatting for parameters"), every table's first row repeating per
        page, and the PDF is Word's own print of it; without an original, or when Word cannot print, the PDF and Word
        file are Gutenberg's renderings of the source, as before, and a warning says so for the PDF.

        0.21.0: when the folder also holds ``abridged-headers.json`` (verbatim column heading -> short form) it
        goes to the fill as ``abridged_headers`` (asi_gutenberg 0.8.0: the plan table's header verbatim on its
        first page, abridged on every later one, a Word pass with the print); the export carries ``abridged``
        (the tables split, by first heading) and ``pages`` (Word's count when it ran, else the rendering's);
        without Word the Word file keeps the verbatim repeating header and a warning says so. The deliverable
        names the source links (``[Safety Plan]({{ row_N_url }})``) come out as blue hyperlinks to the row's
        first work product URL (asi_gutenberg 0.9.0)."""
        import json

        from asi_gutenberg import build, fill_docx, from_markdown

        plan = self.value_set(row_id, standard)
        target = Path(out_dir) if out_dir else Path(self.brain.out_dir)
        target.mkdir(parents=True, exist_ok=True)
        warnings = list(plan["warnings"])
        built = []
        for std in plan["standards"]:
            source = Path(std["path"]).read_text(encoding="utf-8")
            paths = build(
                from_markdown(source), str(target), name=std["folder"],
                params=std["values"], strict_params=False, mark_params=True,
            )
            issues = [str(i) for i in paths.pop("issues", [])]
            unfilled = sorted(i[len(UNFILLED):] for i in issues if i.startswith(UNFILLED))
            for name in unfilled:
                warnings.append(f"{std['folder']}: unfilled parameter {name}")
            files = {fmt: paths[fmt] for fmt in ("md", "pdf", "docx") if fmt in paths}
            exact = {"docx": False, "pdf": False}
            pages, abridged = paths.get("pages"), []
            if std.get("template"):
                mapping = None
                if std.get("abridged_headers"):
                    mapping = json.loads(Path(std["abridged_headers"]).read_text(encoding="utf-8"))
                filled = fill_docx(
                    std["template"], source, std["values"], str(target / f"{std['folder']}.docx"),
                    strict=False, mark=True, pdf=True, abridged_headers=mapping,
                )
                files["docx"] = filled.docx
                exact["docx"] = True
                if filled.pdf:
                    files["pdf"] = filled.pdf
                    exact["pdf"] = True
                if filled.pages:
                    pages = filled.pages
                abridged = list(filled.abridged)
                for issue in filled.issues:
                    if issue.startswith(ABRIDGE_NEEDS_WORD):
                        how = "the Word file keeps the verbatim header on every page"
                    else:
                        how = "the PDF is Gutenberg's rendering, not the template"
                    warnings.append(f"{std['folder']}: {issue}; {how}")
            built.append({
                "standard": std["folder"], "title": std["title"], "files": files, "primary": files.get("pdf"),
                "pages": pages, "abridged": abridged, "filled": std["filled"], "unfilled": unfilled,
                "template": std.get("template"), "abridged_headers": std.get("abridged_headers"), "exact": exact,
                "issues": [i for i in issues if not i.startswith(UNFILLED)],
            })
        data = {
            "row": row_id, "order": plan["order"], "out_dir": str(target), "exports": built,
            "statuses": plan["statuses"], "warnings": warnings,
        }
        with self.brain.storage.transaction():
            self.brain.storage.audit(actor, "export", pq.PLAN_ENTITY, row_id, {
                "standards": [b["standard"] for b in built], "filled": [b["filled"] for b in built],
                "unfilled": [len(b["unfilled"]) for b in built], "out_dir": str(target),
            })
        self.brain.events.publish(
            "plan.exported", row=row_id, standards=[b["standard"] for b in built], out_dir=str(target), actor=actor
        )
        return data
