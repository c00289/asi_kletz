"""The ``diagram`` and ``document`` verbs: generated views of the plan through asi_escher and asi_gutenberg.

Both verbs list their catalog when called without a name, turn layout issues into warnings,
write an audit entry (``generate``) and publish ``generated`` on the event bus. The result of
``document`` carries ``primary`` (the PDF, the reviewed artefact) beside ``paths`` and a
``diagrams`` list (one entry per figure asi_gutenberg rendered); the result of ``diagram``
carries the PNG as ``primary``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import CommandError, NotFound
from ..io.stamp import next_sibling, stamped_stem
from .base import Argument, Command, Context, Result, parse_kv
from .factory import register_command

NAME_DIAGRAM = Argument("name", "Diagram key; omit to list the catalog")
NAME_DOCUMENT = Argument("name", "Document key; omit to list the catalog")
OUT = Argument("out", "Output folder (default: $ASI_KLETZ_OUT, `out` in kletz.toml, or out/ next to the database)",
               flag=True, type="path")
PARAM = Argument("param", "Builder parameter as key=value (repeatable), e.g. --param phase=3",
                 flag=True, type="kv", multiple=True)
FORMATS = Argument("formats", "Comma-separated subset of png,svg,dot,mmd", flag=True, default="png,svg,dot,mmd")
DPI = Argument("dpi", "PNG resolution", flag=True, type="int", default=160)


def _out_dir(ctx: Context, args: dict[str, Any]) -> Path:
    return Path(args.get("out") or ctx.brain.out_dir)


def _record(ctx: Context, data: dict[str, Any]) -> None:
    """Audit entry ``generate`` and event ``generated``: a generated view is a change worth seeing."""
    payload = {k: data.get(k) for k in ("kind", "name", "params", "primary", "paths")}
    with ctx.brain.storage.transaction():
        ctx.brain.storage.audit(ctx.actor, "generate", data["kind"], None, payload)
    ctx.brain.events.publish("generated", actor=ctx.actor, **payload)


@register_command
class DiagramCommand(Command):
    verb = "diagram"
    help = "Draw a diagram of the plan with asi_escher (png, svg, dot, mmd); no name lists the catalog."
    arguments = (NAME_DIAGRAM, OUT, FORMATS, PARAM, DPI)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..generate import BuildContext, DiagramFactory
        from ..generate.figures import FORMATS as KNOWN_FORMATS
        from ..generate.figures import render_diagram

        if not args.get("name"):
            return Result.success({"diagrams": DiagramFactory.catalog()})
        formats = tuple(f.strip().lower() for f in str(args.get("formats") or "").split(",") if f.strip())
        unknown = [f for f in formats if f not in KNOWN_FORMATS]
        if unknown or not formats:
            known = ", ".join(KNOWN_FORMATS)
            return Result.failure(f"formats must be a subset of {known}; got {args.get('formats')!r}")
        try:
            DiagramFactory.get(args["name"])
        except NotFound as exc:
            return Result.failure(str(exc))
        build_ctx = BuildContext(ctx.brain, ctx.actor, _out_dir(ctx, args))
        try:
            data = render_diagram(
                ctx.brain, args["name"], parse_kv(args.get("param")), build_ctx,
                formats=formats, dpi=int(args.get("dpi") or 160),
            )
        except (CommandError, ValueError) as exc:
            return Result.failure(str(exc))
        _record(ctx, data)
        return Result.success(data, build_ctx.warnings)


@register_command
class DocumentCommand(Command):
    verb = "document"
    help = "Print a document of the plan with asi_gutenberg (md, pdf, docx); no name lists the catalog."
    arguments = (NAME_DOCUMENT, OUT, PARAM)

    def run(self, ctx: Context, args: dict[str, Any]) -> Result:
        from ..generate import BuildContext, DocumentFactory, check_params

        if not args.get("name"):
            return Result.success({"documents": DocumentFactory.catalog()})
        try:
            spec, builder = DocumentFactory.get(args["name"])
            params = check_params(spec, parse_kv(args.get("param")))
        except (NotFound, CommandError, ValueError) as exc:
            return Result.failure(str(exc))
        out_dir = _out_dir(ctx, args)
        build_ctx = BuildContext(ctx.brain, ctx.actor, out_dir)
        try:
            doc = builder(ctx.brain, params, build_ctx)
        except CommandError as exc:
            return Result.failure(str(exc))
        paths, warning = _build_with_fallback(doc, out_dir, spec.key)
        if warning:
            build_ctx.warn(warning)
        issues = [str(issue) for issue in paths.pop("issues", [])]
        for issue in issues:
            build_ctx.warn(issue)
        outputs = {fmt: paths.pop(fmt) for fmt in ("md", "pdf", "docx") if fmt in paths}
        diagrams = [{**d, "size": list(d.get("size", ()))} for d in paths.pop("diagrams", [])]
        data = {
            "kind": "document", "name": spec.key, "title": doc.title, "params": params,
            "out_dir": str(out_dir), "paths": outputs, "primary": outputs.get("pdf"),
            "pages": paths.pop("pages", None), "stats": paths, "diagrams": diagrams, "issues": issues,
        }
        _record(ctx, data)
        return Result.success(data, build_ctx.warnings)


def _build_with_fallback(doc: Any, out_dir: Path, stem: str) -> tuple[dict[str, Any], str | None]:
    """Write the triplet as ``<stem>_<stamp>.{md,pdf,docx}`` (0.27.0, :mod:`asi_kletz.io.stamp`); if a file is
    locked, use the ``-2`` sibling of the stamped stem."""
    from asi_gutenberg import build

    out_dir.mkdir(parents=True, exist_ok=True)
    name = stamped_stem(stem)
    try:
        return build(doc, str(out_dir), name=name), None
    except PermissionError:
        alt = next_sibling(out_dir / f"{name}.pdf").stem
        paths = build(doc, str(out_dir), name=alt)
        return paths, f"{name}.pdf or {name}.docx is locked (open in another program); wrote {alt}.* instead"
