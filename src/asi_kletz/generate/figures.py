"""Rendering through asi_escher, with the warning captured and the issues made plain data.

``asi_escher.build`` emits a ``LayoutWarning`` and returns ``LayoutIssue`` objects whenever
the layout had to settle for a degraded drawing. Kletz turns the issues into dicts (so they
travel in a ``Result``) and reports them as warnings; the Python warning itself never escapes.
Importing this module does not import asi_escher or matplotlib; the functions do, lazily.
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError
from .base import BuildContext, DiagramFactory, Spec, check_params

if TYPE_CHECKING:
    from ..brain import Brain

FORMATS = ("png", "svg", "dot", "mmd")
FIGURES_DIR = "figures"
DEFAULT_DPI = 160


def slug(text: str) -> str:
    """File-system-safe stem: lower case, runs of other characters become one underscore."""
    stem = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return stem or "diagram"


def output_stem(spec: Spec, params: dict[str, str]) -> str:
    """``phase_flow`` with ``phase=3`` -> ``phase_flow_3``; a diagram without params keeps its key."""
    parts = [spec.key, *(slug(params[p.name]) for p in spec.params if params.get(p.name))]
    return "_".join(parts)


def issue_to_dict(issue: Any) -> dict[str, Any]:
    """``LayoutIssue`` -> plain dict (``kind``, ``message``, ``edge``, ``node``)."""
    edge = getattr(issue, "edge", None)
    return {
        "kind": getattr(issue, "kind", "issue"),
        "message": getattr(issue, "message", str(issue)),
        "edge": list(edge) if edge else None,
        "node": getattr(issue, "node", None),
    }


def build_diagram(
    diagram: Any, out_dir: str | Path, name: str | None = None,
    formats: tuple[str, ...] = FORMATS, dpi: int = DEFAULT_DPI,
) -> dict[str, Any]:
    """``asi_escher.build`` with the ``LayoutWarning`` captured and the issues as dicts.

    Returns the Escher summary: one path per written format, ``size``, ``nodes``, ``edges``
    and ``issues`` (list of dicts).
    """
    from asi_escher import LayoutWarning, build

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", LayoutWarning)
        summary = build(diagram, str(out_dir), name=name, formats=tuple(formats), dpi=dpi)
    summary["issues"] = [issue_to_dict(issue) for issue in summary.get("issues", [])]
    summary["size"] = list(summary.get("size", ()))
    return summary


def render_diagram(
    brain: Brain, key: str, params: dict[str, Any] | None, ctx: BuildContext, *,
    out_dir: str | Path | None = None, formats: tuple[str, ...] = FORMATS, dpi: int = DEFAULT_DPI,
) -> dict[str, Any]:
    """Build catalog diagram ``key`` from the plan and write it into ``out_dir`` (default ``ctx.out_dir``).

    The result carries ``name``, ``title``, ``params``, ``paths`` per format, ``primary`` (the
    PNG, else the first format written), ``size``, ``nodes``, ``edges`` and ``issues``. Layout
    issues are also appended to ``ctx.warnings``.
    """
    spec, builder = DiagramFactory.get(key)
    clean = check_params(spec, params)
    diagram = builder(brain, clean, ctx)
    target = Path(out_dir) if out_dir is not None else Path(ctx.out_dir)
    stem = output_stem(spec, clean)
    if getattr(diagram, "kind", None) == "chart":  # a matplotlib chart (0.12.0): png and svg only
        from .charts import CHART_FORMATS

        dropped = [fmt for fmt in formats if fmt not in CHART_FORMATS]
        kept = tuple(fmt for fmt in formats if fmt in CHART_FORMATS)
        if not kept:
            raise CommandError(f"{key} is a chart and writes {', '.join(CHART_FORMATS)} only, not {', '.join(dropped)}")
        if dropped:
            ctx.warn(f"{key} is a chart: {', '.join(dropped)} not written, {', '.join(kept)} only")
        summary = diagram.render(target, stem, formats=kept, dpi=dpi)
    else:
        summary = build_diagram(diagram, target, name=stem, formats=formats, dpi=dpi)
    paths = {fmt: summary[fmt] for fmt in formats if fmt in summary}
    for issue in summary["issues"]:
        ctx.warn(f"{key}: {issue['message']}")
    return {
        "kind": "diagram", "name": key, "title": spec.title, "params": clean, "stem": stem,
        "out_dir": str(target), "paths": paths,
        "primary": paths.get("png") or next(iter(paths.values()), None),
        "size": summary["size"], "nodes": summary["nodes"], "edges": summary["edges"],
        "issues": summary["issues"],
    }


def add_diagram(
    doc: Any, ctx: BuildContext, key: str, params: dict[str, Any] | None = None, caption: str = ""
) -> Any:
    """Build catalog diagram ``key`` and add it to ``doc`` as a ``diagram`` block.

    asi_gutenberg renders the block into ``<out>/figures/<stem>.png`` when the document is
    built, numbers it as a figure and reports its layout issues in ``doc.issues``; the stem
    is the same one the standalone ``diagram`` verb would use.
    """
    spec, builder = DiagramFactory.get(key)
    clean = check_params(spec, params)
    diagram = builder(ctx.brain, clean, ctx)
    stem = output_stem(spec, clean)
    ctx.figures.append({"name": key, "params": clean, "stem": stem, "path": f"{FIGURES_DIR}/{stem}.png"})
    if getattr(diagram, "kind", None) == "chart":
        # a chart is rendered now into <out>/figures/ and goes in as a figure block: asi_gutenberg resolves
        # the relative path against the output folder when it builds, as it does for its own diagram PNGs
        diagram.render(Path(ctx.out_dir) / FIGURES_DIR, stem, formats=("png",))
        return doc.figure(f"{FIGURES_DIR}/{stem}.png", caption)
    return doc.diagram(diagram, caption, name=stem)
