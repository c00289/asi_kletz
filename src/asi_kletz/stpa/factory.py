"""ControlStructureFactory: the builders, the drawing and the export (docs/control-structure-plan.md, 3).

A **builder** turns options into a plain dataset (see ``ControlStructureService.dataset``) that
``create`` loads through the service, so every structure, however it was made, obeys the same
rules. The registry holds ``blank``, ``template:wheel_loader_master`` (the owner's structure, read
from the private shelf ``control_structures_dir`` points at and listed as unavailable when it is
absent), ``from_drawio``, ``from_datasets`` and ``clone``; ``register_builder`` adds one.

``to_diagram`` is the one place that decides how rows become the drawing: a controller is an
``asi_escher`` box of its kind with its algorithms as ``(code, name)`` and its process model as
``(title, entries)``, an entry rendered ``heading: variables; updated by ...``; an edge is a
control action or feedback carrying its signal lines ``CA-01 Mission Data`` in order; a note is
attached to its controller. Every entry is drawn behind a dash, which is how the reader tells
one entry from the wrapped rest of the previous one when the file comes back. ``build_files`` hands
a diagram to ``asi_escher.build`` with provenance and the OCR gate on and answers with the files
written, the OCR verdict and the layout issues; ``export`` wraps it with the audit and the event,
the window's preview calls it alone. Kletz never draws anything itself.
"""

from __future__ import annotations

import warnings as _warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound
from ..generate.figures import issue_to_dict
from ..schema.lists import list_of
from .drawio_reader import BULLET, read_dataset_folder, read_drawio, render_entry

if TYPE_CHECKING:
    from ..brain import Brain

FORMATS = ("drawio", "png", "svg")  # asi_escher.FORMATS, the set the export dialog offers
DEFAULT_FORMATS = ("drawio", "png")  # the file to edit and the picture to look at
TEMPLATE_BUILDER = "template:wheel_loader_master"
TEMPLATE_FOLDER = Path("wheel-loader") / "datasets"  # under control_structures_dir
TEMPLATE_NAME = "Wheel Loader Master Control Structure"
TEMPLATE_SYSTEM = "Autonomous wheel loader"
EXPORT_DIR = "control_structures"  # under Brain.out_dir when --out is not given
PREVIEW_DIR = "figures"  # under Brain.out_dir: the window's preview, beside the documents' figures

BuildFn = Callable[["Brain", dict[str, Any]], dict[str, Any]]
AvailableFn = Callable[["Brain"], str | None]


@dataclass(frozen=True)
class Builder:
    """A named way to make a structure. ``build(brain, options)`` returns a dataset; ``available``
    answers ``None`` or the reason the builder cannot run on this machine."""

    name: str
    description: str
    build: BuildFn
    options: tuple[str, ...] = ()
    available: AvailableFn = field(default=lambda brain: None)

    def to_dict(self, brain: Brain) -> dict[str, Any]:
        reason = self.available(brain)
        return {
            "name": self.name, "description": self.description, "options": list(self.options),
            "available": reason is None, "reason": reason,
        }


_BUILDERS: dict[str, Builder] = {}


def register_builder(builder: Builder) -> Builder:
    if builder.name in _BUILDERS:
        raise ValueError(f"builder {builder.name!r} already registered")
    _BUILDERS[builder.name] = builder
    return builder


def _require(options: dict[str, Any], key: str, builder: str) -> str:
    value = options.get(key)
    if value in (None, ""):
        raise CommandError(f"{builder} needs --{'from' if key == 'path' else key}")
    return str(value)


def _blank(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    return {"structure": {"name": _require(options, "name", "blank"), "source": "built by hand"}}


def template_folder(brain: Brain) -> Path:
    return Path(brain.control_structures_dir) / TEMPLATE_FOLDER


def _template_available(brain: Brain) -> str | None:
    folder = template_folder(brain)
    if not (folder / "controllers.json").is_file():
        return f"no datasets at {folder} (set control_structures_dir in kletz.toml)"
    return None


def _template(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    reason = _template_available(brain)
    if reason:
        raise NotFound(f"{TEMPLATE_BUILDER} is unavailable: {reason}")
    data = read_dataset_folder(template_folder(brain))
    data["structure"] = {"name": TEMPLATE_NAME, "system": TEMPLATE_SYSTEM, "source": str(template_folder(brain))}
    return data


def _from_drawio(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    kinds = options.get("kinds") or {}
    return read_drawio(_require(options, "path", "from_drawio"), kinds)


def _from_datasets(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    return read_dataset_folder(_require(options, "path", "from_datasets"))


def _clone(brain: Brain, options: dict[str, Any]) -> dict[str, Any]:
    source = brain.control_structures.resolve(_require(options, "path", "clone"))
    data = brain.control_structures.dataset(source)
    data["structure"] = {
        **data["structure"], "source": f"duplicate of {source['slug']}", "status": "Draft", "revision": 1,
    }
    data["structure"].pop("slug", None)
    return data


register_builder(Builder("blank", "The structure and nothing else.", _blank, ("name", "system")))
register_builder(Builder(
    TEMPLATE_BUILDER,
    "The owner's wheel loader master structure, read from the private datasets control_structures_dir points at.",
    _template, ("name", "system"), _template_available,
))
register_builder(Builder(
    "from_drawio", "Parse a draw.io file (asi_escher's or hand-drawn).", _from_drawio, ("path", "name", "system"),
))
register_builder(Builder(
    "from_datasets", "The six JSON files of a datasets folder.", _from_datasets, ("path", "name", "system"),
))
register_builder(Builder(
    "clone", "A deep copy of an existing structure (--from its id or slug).", _clone, ("path", "name", "system"),
))


class ControlStructureFactory:
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
        """Build a structure with ``builder``: the dataset it returns is loaded through the service.
        ``name``, ``slug`` and ``system`` given here replace the dataset's; the builder's own
        warnings (what a file could not say) come first in the warnings."""
        spec = self.builder(builder)
        reason = spec.available(self.brain)
        if reason:
            raise NotFound(f"{spec.name} is unavailable: {reason}")
        dataset = spec.build(self.brain, dict(options))
        head = dict(dataset.get("structure") or {})
        head.update({k: options[k] for k in ("name", "slug", "system") if options.get(k)})
        read_warnings = [str(w) for w in dataset.get("warnings") or []]
        row, warnings = self.brain.control_structures.create_from_dataset(dataset, actor, **head)
        return row, [*read_warnings, *warnings]

    # -- the drawing ----------------------------------------------------
    def to_diagram(self, ref: Any):
        """The structure as an ``asi_escher.Diagram`` of kind ``control_structure``."""
        from asi_escher import Diagram

        row = self.brain.control_structures.resolve(ref)
        parts = self.brain.control_structures.parts(row["slug"])
        d = Diagram(row["name"], "control_structure")
        algorithms: dict[str, list[tuple[str, str]]] = {}
        for a in parts["algorithms"]:
            algorithms.setdefault(a["controller"], []).append((a["code"], a.get("name") or ""))
        entries: dict[str, list[str]] = {}
        for p in parts["process_model_entries"]:
            entry = {**p, "variables": list_of(p.get("variables")), "updated_by": list_of(p.get("updated_by"))}
            entries.setdefault(p["controller"], []).append(BULLET + render_entry(entry))
        for c in parts["controllers"]:
            title = c.get("process_model_title") or ""
            lines = entries.get(c["key"], [])
            d.controller(
                c["key"], c["name"], kind=c.get("kind") or "controller",
                responsibility=c.get("responsibility") or "",
                algorithms=algorithms.get(c["key"], []),
                process_model=(title, lines) if (title or lines) else None,
            )
        signals: dict[str, list[str]] = {}
        for s in parts["signals"]:
            signals.setdefault(s["edge"], []).append(f"{s['signal_id']} {s.get('name') or ''}".strip())
        for e in parts["edges"]:
            lines = signals.get(e["key"], [])
            if e.get("kind") == "feedback":
                d.feedback(e["source"], e["target"], lines)
            else:
                d.control_action(e["source"], e["target"], lines)
        for index, n in enumerate(parts["notes"], start=1):
            d.note(f"note_{n.get('order') or index}", n["text"], attached_to=n.get("attached_to") or None)
        return d

    # -- the files ------------------------------------------------------
    @staticmethod
    def build_files(
        diagram: Any, out_dir: str | Path, name: str, formats: tuple[str, ...] | None = None, *, ocr: bool = True,
    ) -> dict[str, Any]:
        """Write ``<out_dir>/<name>.<fmt>`` for every format through ``asi_escher.build`` (provenance on,
        the OCR gate on the PNG unless ``ocr=False``) and return the plain-data form: ``formats``,
        ``paths``, ``files``, ``primary``, ``size``, ``nodes``, ``edges``, ``issues``, ``layout_issues``,
        ``ocr`` (escher's report as a dict, or None) and ``ocr_verdict``. No database, no audit, no
        event: ``export`` adds those; the window's preview calls this alone, off the Tk thread, with a
        diagram made on it."""
        from asi_escher import LayoutWarning, build

        formats = tuple(dict.fromkeys(formats or DEFAULT_FORMATS))
        unknown = [f for f in formats if f not in FORMATS]
        if unknown:
            raise CommandError(f"unknown format(s) {', '.join(unknown)}; choose from {', '.join(FORMATS)}")
        out = Path(out_dir)
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always", LayoutWarning)
            built = build(diagram, str(out), name, formats=formats, provenance=True, ocr=ocr and "png" in formats)
        for w in caught:
            if not issubclass(w.category, LayoutWarning):
                _warnings.warn(w.message, w.category, stacklevel=2)
        issues = [issue_to_dict(i) for i in built["issues"]]
        report = built.get("ocr")
        paths = {fmt: str(built[fmt]) for fmt in formats}
        return {
            "out": str(out),
            "formats": list(formats), "paths": paths, "files": list(paths.values()),
            "primary": paths.get("png") or paths.get("drawio") or next(iter(paths.values())),
            "size": [int(built["size"][0]), int(built["size"][1])],
            "nodes": int(built["nodes"]), "edges": int(built["edges"]),
            "issues": issues,
            "layout_issues": [i for i in issues if i["kind"] != "ocr"],
            "ocr": report.to_dict() if report is not None else None,
            "ocr_verdict": report.verdict if report is not None else ("ocr skipped" if not ocr else "no png written"),
        }

    def export(
        self, ref: Any, out_dir: str | Path | None = None, formats: tuple[str, ...] | None = None,
        *, ocr: bool = True, actor: str = "python",
    ) -> dict[str, Any]:
        """Write ``<out>/<slug>.<fmt>`` for every format (``build_files``). Returns the paths, the OCR
        verdict and the issues; audited as ``cs.export``, published as ``cs.exported``."""
        row = self.brain.control_structures.resolve(ref)
        out = Path(out_dir) if out_dir else Path(self.brain.out_dir) / EXPORT_DIR
        data = {
            "id": row["id"], "slug": row["slug"], "name": row["name"],
            **self.build_files(self.to_diagram(row), out, row["slug"], formats, ocr=ocr),
        }
        paths = data["paths"]
        self.brain.storage.audit(actor, "cs.export", "control_structure", row["id"],
                                 {"slug": row["slug"], "paths": paths, "ocr_verdict": data["ocr_verdict"]})
        self.brain.events.publish(
            "cs.exported", structure=row["slug"], paths=paths, ocr_verdict=data["ocr_verdict"], actor=actor,
        )
        return data

    def preview_dir(self) -> Path:
        """Where the window's preview goes: ``figures/`` under the out folder, beside the documents' figures."""
        return Path(self.brain.out_dir) / PREVIEW_DIR
