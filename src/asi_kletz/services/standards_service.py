"""StandardsService: the parametrised standards (asi_standards) a Safety Plan row can be exported into.

A *standard* is one folder of the standards directory (``standards_dir`` in kletz.toml, default
``../asi_standards`` beside the repo) holding a Gutenberg Markdown source of the same name
(``qf-17-safety-plan/qf-17-safety-plan.md``): a controlled QMS document whose blanks are ``{{ name }}``
parameters. A person supplies the document-level ones (``vehicle_type``, the roles) once, through the
``parameter`` entity; Kletz supplies the row-level ones (``row_N_points``, ``row_N_sprint_end``,
``row_N_status``, N the plan row's order) from the plan and from Jira. A plan row has a standard when one
of its QMS reference flags (``ref_qf_17``) names a folder that starts with that QMS id in slug form
(``qf-17-...``).

The owner, 2026-10-29: the Expected Duration/Deadline is "x points" (the chosen points, never the default)
then the date the sprint is expected to conclude; the Status is the status of the Jira ticket tied to the
deliverable, not the spreadsheet's names. asi_gutenberg is imported inside the methods that need it, so
``import asi_kletz`` never loads it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound, ValidationError
from ..generate import plan_queries as pq
from ..generate.plan_schedule import SOURCE_FLOOR, weight_of

if TYPE_CHECKING:
    from ..brain import Brain

PARAMETER = "parameter"
ROW_PARAM = re.compile(r"^row_(\d+)_(points|sprint_end|jira_key|status)$")
PARAM_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
UNFILLED = "unfilled parameter: "
NO_STANDARD = "No standard for this deliverable: its QMS references name none in {root}"


@dataclass
class Standard:
    folder: str
    path: Path
    title: str
    parameters: list[str] = field(default_factory=list)
    template: Path | None = None  # the Word original under source/, when the folder holds exactly one (0.16.0)

    @property
    def document_parameters(self) -> list[str]:
        """The names a person supplies: everything that is not a row parameter."""
        return [p for p in self.parameters if not ROW_PARAM.match(p)]

    @property
    def row_parameters(self) -> list[str]:
        """The names Kletz supplies: ``row_N_points``, ``row_N_sprint_end``, ``row_N_jira_key``, ``row_N_status``."""
        return [p for p in self.parameters if ROW_PARAM.match(p)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "folder": self.folder, "path": str(self.path), "title": self.title,
            "template": str(self.template) if self.template else None,
            "parameters": len(self.parameters), "document_parameters": self.document_parameters,
            "row_parameters": len(self.row_parameters),
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
        return Standard(folder, source, str(doc.title or folder), parameters(doc), template)

    def for_row(self, row: dict[str, Any]) -> list[Standard]:
        """The standards a plan row has: those whose folder a set QMS reference flag of the row names."""
        schema = self.brain.registry.get(pq.PLAN_ENTITY)
        slugs = [qms_slug(s.name) for s in schema.fields if s.group == "reference" and s.is_flag and row.get(s.name)]
        return [s for s in self.list() if any(folder_names(s.folder, slug) for slug in slugs)]

    # -- the parameter entity's rule -----------------------------------------------------------
    def parameter_guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> None:
        """A parameter's name is unique within its standard (``""`` is the standard of every document)."""
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

    # -- the values ------------------------------------------------------------------------------------
    def document_values(self, standard: Standard) -> dict[str, str]:
        """The document-level values: every ``parameter`` row whose standard is empty or this one, the
        standard's own row winning over the global one."""
        values: dict[str, str] = {}
        rows = self.brain.service(PARAMETER).list(order_by=("standard", "name", "id"))
        for row in rows:  # "" sorts first, so a standard's own row overwrites the global value
            if (row.get("standard") or "") in ("", standard.folder) and row.get("value") not in (None, ""):
                values[row["name"]] = str(row["value"])
        return values

    def row_values(
        self, rows: list[dict[str, Any]], statuses: dict[str, str | None], warnings: list[str] | None = None
    ) -> dict[str, str]:
        """``row_N_points``, ``row_N_sprint_end``, ``row_N_jira_key``, ``row_N_status`` for every plan row that
        has an order.

        The points are the weight the schedule used for the row, as ``plan_schedule.weight_of`` resolves it
        (the owner's revision of 2026-10-29): the chosen ``points`` when set, else the row's
        ``default_points``; only a row with neither (the scheduler fell back to the floor) stays unfilled,
        with one warning naming the rows. So the points and the sprint end printed under them agree. The
        status is the Jira status of the row's key; absent when unknown. The key is the row's ``jira_key``
        upper-cased, the part before a colon when one was typed (the owner, 2026-10-29: "the prefix before
        the colon of the assigned Jira ticket name", stacked over the status in the Status column).
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
            if key and statuses.get(key):
                values[f"row_{order}_status"] = str(statuses[key])
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
            out.append({
                **std.to_dict(), "values": used,
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
        file are Gutenberg's renderings of the source, as before, and a warning says so for the PDF."""
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
            if std.get("template"):
                filled = fill_docx(
                    std["template"], source, std["values"], str(target / f"{std['folder']}.docx"),
                    strict=False, mark=True, pdf=True,
                )
                files["docx"] = filled.docx
                exact["docx"] = True
                if filled.pdf:
                    files["pdf"] = filled.pdf
                    exact["pdf"] = True
                for issue in filled.issues:
                    warnings.append(f"{std['folder']}: {issue}; the PDF is Gutenberg's rendering, not the template")
            built.append({
                "standard": std["folder"], "title": std["title"], "files": files, "primary": files.get("pdf"),
                "pages": paths.get("pages"), "filled": std["filled"], "unfilled": unfilled,
                "template": std.get("template"), "exact": exact,
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
