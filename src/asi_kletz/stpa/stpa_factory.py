"""StpaFactory: the builders of an STPA analysis and its export (confluence-integration-plan.md, 7.2).

A **builder** turns options into the plain dataset ``StpaService.create_from_dataset`` loads through
the services, so every analysis obeys the same rules however it was made. The registry holds
``blank`` (the analysis and nothing else), ``from_bundle`` (**the primary builder**: a Hopper
Confluence evidence bundle, offline, hashed, replayable), ``from_confluence`` (a snapshot through
Kletz's own Confluence door, ``ConfluenceService.snapshot_page``, into the evidence folder, then
``from_bundle``; the bundle it writes is the evidence) and ``clone``; ``register_stpa_builder`` adds
one. The same ``Builder`` shape as the control-structure factory.

``read_bundle`` reads ``manifest.json``, ``pages.json`` and ``pages/<id>.md`` of a bundle and hands
the Markdown body with its citation context to the reader (``confluence_reader.read_stpa_page``); the
analysis's ``source_*`` come from the manifest. ``export`` writes the six-sheet workbook, the
``stpa_report`` document (Gutenberg) and the ``stpa_trace`` diagram (Escher) for an analysis.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound
from ..schema.fields import json_text
from ..schema.lists import list_of
from .factory import Builder

if TYPE_CHECKING:
    from ..brain import Brain

FORMATS = ("xlsx", "md", "docx", "pdf", "svg", "png")
DEFAULT_FORMATS = ("xlsx", "md", "png")
DOCUMENT_FORMATS = ("md", "docx", "pdf")
DIAGRAM_FORMATS = ("svg", "png")
EXPORT_DIR = "stpa"  # under Brain.out_dir when --out is not given
MANIFEST_FILE = "manifest.json"
PAGES_FILE = "pages.json"
PAGES_DIR = "pages"

BuildFn = Callable[["Brain", dict[str, Any]], dict[str, Any]]
_BUILDERS: dict[str, Builder] = {}


def register_stpa_builder(builder: Builder) -> Builder:
    if builder.name in _BUILDERS:
        raise ValueError(f"STPA builder {builder.name!r} already registered")
    _BUILDERS[builder.name] = builder
    return builder


def _require(options: dict[str, Any], key: str, builder: str) -> str:
    value = options.get(key)
    if value in (None, ""):
        raise CommandError(f"{builder} needs --{'from' if key == 'path' else key}")
    return str(value)


# -- bundles -----------------------------------------------------------------------------------------
def bundle_folder(path: str | Path) -> Path:
    p = Path(path)
    folder = p if p.is_dir() else p.parent
    if not (folder / MANIFEST_FILE).is_file():
        raise NotFound(f"no {MANIFEST_FILE} in {folder}: not a Hopper bundle")
    return folder


def read_bundle(path: str | Path, page_id: str | None = None) -> dict[str, Any]:
    """The dataset of one page of a Confluence bundle: the body read by the reader, the ``source_*``
    from the manifest (page id, URL, version, body hash, time taken, folder) and the page's
    comments, for the report's appendix. ``page_id`` picks the page when the bundle holds several
    (default: the manifest's first)."""
    from .confluence_reader import read_stpa_page  # lazy: the reader stands on asi_hopper's page anatomy

    folder = bundle_folder(path)
    manifest = json.loads((folder / MANIFEST_FILE).read_text(encoding="utf-8"))
    if (manifest.get("kind") or "jira") != "confluence":
        raise CommandError(f"{folder} is a {manifest.get('kind') or 'jira'} bundle, not a Confluence one")
    pages = list(manifest.get("pages") or [])
    if not pages:
        raise NotFound(f"{folder}: the bundle holds no pages")
    wanted = str(page_id).strip() if page_id not in (None, "") else str(pages[0]["id"])
    head = next((p for p in pages if str(p.get("id")) == wanted), None)
    if head is None:
        raise NotFound(f"{folder}: no page {wanted} in the bundle (it holds {', '.join(str(p['id']) for p in pages)})")
    entries = []
    if (folder / PAGES_FILE).is_file():
        entries = json.loads((folder / PAGES_FILE).read_text(encoding="utf-8"))
    entry = next((e for e in entries if str(e.get("id")) == wanted), {})
    body_file = entry.get("body_file") or f"{PAGES_DIR}/{wanted}.md"
    body_path = folder / body_file
    if not body_path.is_file():
        raise NotFound(f"{folder}: no body file {body_file}")
    body = body_path.read_text(encoding="utf-8")
    version = head.get("version")
    data = read_stpa_page(
        body,
        page_id=wanted,
        url=str(entry.get("url") or ""),
        version=int(version) if version is not None else None,
        title=str(head.get("title") or entry.get("title") or ""),
    )
    data["analysis"].update(
        {
            "source_kind": "confluence",
            "source_page_id": wanted,
            "source_url": entry.get("url") or None,
            "source_version": version,
            "source_body_sha256": head.get("body_sha256") or entry.get("body_sha256"),
            "source_taken_at": manifest.get("taken_at"),
            "source_bundle": str(folder),
        }
    )
    data["comments"] = list(entry.get("comments") or [])
    return data


def bundle_comments(folder: str | None, page_id: str | None) -> list[dict[str, Any]]:
    """The comments ``pages.json`` holds for ``page_id`` in ``folder``, or none when either is gone."""
    if not folder or not page_id:
        return []
    pages = Path(folder) / PAGES_FILE
    if not pages.is_file():
        return []
    try:
        entries = json.loads(pages.read_text(encoding="utf-8"))
    except ValueError:
        return []
    entry = next((e for e in entries if str(e.get("id")) == str(page_id)), {})
    return list(entry.get("comments") or [])


# -- builders ----------------------------------------------------------------------------------------
def _blank(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    return {"analysis": {"name": _require(options, "name", "blank"), "source_kind": "hand"}}


def _from_bundle(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    return read_bundle(_require(options, "path", "from_bundle"), options.get("page"))


def snapshot_page(brain: Brain, page_id: str, out: str | Path | None = None, *, hopper: Any = None) -> dict[str, Any]:
    """Snapshot ``page_id`` (with its comments) into ``out`` (default: ``brain.evidence_dir``) through
    Kletz's Confluence door (``ConfluenceService.snapshot_page``: the one Hopper facade of the tool, a
    missing session reported as the login hint, never a browser); returns the manifest."""
    return brain.confluence.snapshot_page(page_id, out, comments=True, hopper=hopper)


def _from_confluence(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    page_id = str(options.get("page") or options.get("path") or "").strip()
    if not page_id:
        raise CommandError("from_confluence needs --page <page id> (or --from <page id>)")
    if not page_id.isdigit():
        raise CommandError(f"from_confluence needs a Confluence page id (digits), not {page_id!r}")
    manifest = snapshot_page(brain, page_id, options.get("out"), hopper=options.get("hopper"))
    return read_bundle(manifest["folder"], page_id)


def _clone(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    from ..services.stpa_service import SOURCE_FIELDS

    source = brain.stpa.resolve(_require(options, "path", "clone"))
    data = brain.stpa.dataset(source)
    head = {k: v for k, v in data["analysis"].items() if k not in SOURCE_FIELDS}
    head.pop("slug", None)
    data["analysis"] = {**head, "status": "Draft", "source_kind": "hand", "note": f"duplicate of {source['slug']}"}
    return data


register_stpa_builder(
    Builder("blank", "The analysis and nothing else, for one written by hand.", _blank, ("name", "system"))
)
register_stpa_builder(
    Builder(
        "from_bundle",
        "A Hopper Confluence evidence bundle folder (--from), its first page or --page <id>: offline and hashed.",
        _from_bundle,
        ("path", "page", "name", "system"),
    )
)
register_stpa_builder(
    Builder(
        "from_confluence",
        "Snapshot a Confluence page (--page <id>) with its comments into the evidence folder (--out), then read it.",
        _from_confluence,
        ("page", "out", "name", "system"),
    )
)
register_stpa_builder(
    Builder(
        "clone",
        "A deep copy of an existing analysis (--from its id or slug).",
        _clone,
        ("path", "name", "system"),
    )
)


class StpaFactory:
    def __init__(self, brain: Brain) -> None:
        self.brain = brain

    # -- builders -------------------------------------------------------
    @staticmethod
    def builders() -> list[str]:
        return list(_BUILDERS)

    @staticmethod
    def builder(name: str) -> Builder:
        try:
            return _BUILDERS[str(name)]
        except KeyError:
            raise NotFound(f"unknown builder {name!r}; known: {', '.join(_BUILDERS)}") from None

    def catalog(self) -> list[dict[str, Any]]:
        return [b.to_dict(self.brain) for b in _BUILDERS.values()]

    def create(self, builder: str, actor: str = "python", **options: Any) -> tuple[dict[str, Any], list[str]]:
        """Build an analysis with ``builder``: the dataset it returns is loaded through the services.
        ``name``, ``slug`` and ``system`` given here replace the dataset's; the reader's warnings
        (what the page could not say) come first in the warnings."""
        spec = self.builder(builder)
        reason = spec.available(self.brain)
        if reason:
            raise NotFound(f"{spec.name} is unavailable: {reason}")
        dataset = spec.build(self.brain, dict(options))
        head = dict(dataset.get("analysis") or {})
        head.update({k: options[k] for k in ("name", "slug", "system") if options.get(k)})
        read_warnings = [str(w) for w in dataset.get("warnings") or []]
        row, warnings = self.brain.stpa.create_from_dataset(dataset, actor, **head)
        return row, [*read_warnings, *warnings]

    # -- refresh --------------------------------------------------------
    def reread(self, ref: Any, path: str | Path | None = None, *, hopper: Any = None) -> dict[str, Any]:
        """The page of an analysis read again: from the bundle ``path`` when given, else a new snapshot
        of its ``source_page_id`` through Hopper into the evidence folder."""
        row = self.brain.stpa.resolve(ref)
        page_id = row.get("source_page_id")
        if path:
            return read_bundle(path, page_id)
        if not page_id:
            raise CommandError(
                f"analysis {row['slug']} was not read from Confluence (no source_page_id); refresh needs --from"
            )
        manifest = snapshot_page(self.brain, str(page_id), hopper=hopper)
        return read_bundle(manifest["folder"], str(page_id))

    # -- the files ------------------------------------------------------
    def export(
        self,
        ref: Any,
        out_dir: str | Path | None = None,
        formats: tuple[str, ...] | None = None,
        *,
        actor: str = "python",
    ) -> dict[str, Any]:
        """Write ``<out>/<slug>.<fmt>`` for every format: ``xlsx`` the six sheets of this analysis, ``md`` /
        ``docx`` / ``pdf`` the ``stpa_report`` document (one Gutenberg build, every document format it
        writes is kept), ``svg`` / ``png`` the ``stpa_trace`` diagram. Audited as ``stpa.export``,
        published as ``stpa.exported``."""
        formats = tuple(dict.fromkeys(formats or DEFAULT_FORMATS))
        unknown = [f for f in formats if f not in FORMATS]
        if unknown:
            raise CommandError(f"unknown format(s) {', '.join(unknown)}; choose from {', '.join(FORMATS)}")
        row = self.brain.stpa.resolve(ref)
        out = Path(out_dir) if out_dir else Path(self.brain.out_dir) / EXPORT_DIR
        out.mkdir(parents=True, exist_ok=True)
        paths: dict[str, str] = {}
        issues: list[str] = []
        if "xlsx" in formats:
            paths["xlsx"] = str(self.export_workbook(row, out / f"{row['slug']}.xlsx"))
        wanted_docs = [f for f in DOCUMENT_FORMATS if f in formats]
        if wanted_docs:
            from ..generate import BuildContext, DocumentFactory

            ctx = BuildContext(self.brain, actor, out)
            doc = DocumentFactory.build("stpa_report", self.brain, {"analysis": row["slug"]}, ctx)
            doc.meta.author = actor
            built = self._build_document(doc, out, f"{row['slug']}_report")
            issues.extend(ctx.warnings)
            issues.extend(str(i) for i in built.get("issues", []))
            for fmt in wanted_docs:
                paths[fmt] = str(built[fmt])
        wanted_pics = tuple(f for f in DIAGRAM_FORMATS if f in formats)
        if wanted_pics:
            from ..generate import BuildContext, DiagramFactory
            from ..generate.figures import build_diagram

            ctx = BuildContext(self.brain, actor, out)
            diagram = DiagramFactory.build("stpa_trace", self.brain, {"analysis": row["slug"]}, ctx)
            built = build_diagram(diagram, out, f"{row['slug']}_trace", formats=wanted_pics)
            issues.extend(i["message"] for i in built["issues"])
            paths.update({fmt: str(built[fmt]) for fmt in wanted_pics})
        data = {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "out": str(out),
            "formats": list(formats),
            "paths": paths,
            "files": list(paths.values()),
            "primary": paths.get("pdf") or paths.get("png") or paths.get("xlsx") or next(iter(paths.values()), None),
            "issues": issues,
        }
        self.brain.storage.audit(
            actor, "stpa.export", "stpa_analysis", row["id"], {"slug": row["slug"], "paths": paths}
        )
        self.brain.events.publish("stpa.exported", analysis=row["slug"], paths=paths, actor=actor)
        return data

    @staticmethod
    def _build_document(doc: Any, out: Path, stem: str) -> dict[str, Any]:
        from asi_gutenberg import build

        doc.revision(doc.meta.revision, doc.meta.date, doc.meta.author, "Generated from the database")
        return build(doc, str(out), name=stem)

    def export_workbook(self, row: dict[str, Any], path: Path) -> Path:
        """One sheet per STPA entity holding this analysis's rows, headed as the workbook exporter heads
        them (the field labels, ``uid`` last and hidden), JSON lists as JSON text."""
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        from ..schema import FieldType
        from ..services.stpa_service import ANALYSIS_ENTITY, PART_ENTITIES

        wb = Workbook()
        wb.remove(wb.active)
        for entity in (ANALYSIS_ENTITY, *PART_ENTITIES):
            schema = self.brain.registry.get(entity)
            ws = wb.create_sheet(schema.sheet[:31])
            rows = [row] if entity == ANALYSIS_ENTITY else self.brain.service(entity).list({"analysis": row["slug"]})
            for col, spec in enumerate(schema.fields, start=1):
                cell = ws.cell(row=1, column=col, value=spec.header)
                cell.font = Font(bold=True)
                if spec.hidden:
                    ws.column_dimensions[get_column_letter(col)].hidden = True
            for r, record in enumerate(rows, start=2):
                for col, spec in enumerate(schema.fields, start=1):
                    value = record.get(spec.name)
                    if value is None or value == []:
                        continue
                    if spec.type is FieldType.JSON:
                        value = json_text(list_of(value))
                    elif spec.type is FieldType.BOOL:
                        value = 1 if value else 0
                    ws.cell(row=r, column=col, value=value)
            ws.freeze_panes = "A2"
        wb.save(path)
        return path
