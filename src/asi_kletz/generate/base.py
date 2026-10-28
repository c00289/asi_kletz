"""Spec, Param, BuildContext and the generator factories.

A *generator* is a builder function registered under a ``Spec``: diagrams return an
``asi_escher.Diagram``, documents an ``asi_gutenberg.Document``. Both read the plan only
through ``brain.service("safety_plan_row")`` and ``brain.lookups`` (see ``plan_queries``), and
both receive a ``BuildContext`` for the actor, the output folder and the warnings they want
to surface. Nothing in this module imports a generator library.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from ..errors import CommandError, NotFound

if TYPE_CHECKING:
    from ..brain import Brain


@dataclass(frozen=True)
class Param:
    """One builder parameter, passed on the command line as ``--param name=value``."""

    name: str
    help: str = ""
    required: bool = False
    choices: tuple[str, ...] = ()
    lookup: str | None = None  # a lookup list that feeds the window's combobox for this param

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "help": self.help, "required": self.required,
            "choices": list(self.choices), "lookup": self.lookup,
        }


@dataclass(frozen=True)
class Spec:
    """Catalog entry of a diagram or a document: key, title, description, parameters."""

    key: str
    title: str
    description: str = ""
    params: tuple[Param, ...] = ()

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "title": self.title, "description": self.description,
            "params": [p.to_dict() for p in self.params],
        }


def check_params(spec: Spec, params: Mapping[str, Any] | None) -> dict[str, str]:
    """Validate ``params`` against ``spec``: unknown names, missing required ones, bad choices.

    Returns the cleaned ``{name: str}`` dict. Raises ``CommandError`` naming the known
    parameters or values, so a caller can correct the call without reading the code.
    """
    given = {str(k).strip(): ("" if v is None else str(v).strip()) for k, v in (params or {}).items()}
    known = {p.name: p for p in spec.params}
    unknown = sorted(set(given) - set(known))
    if unknown:
        accepted = ", ".join(known) or "no parameters"
        raise CommandError(f"{spec.key}: unknown param(s) {', '.join(unknown)}; accepts {accepted}")
    clean: dict[str, str] = {}
    for name, param in known.items():
        value = given.get(name, "")
        if not value:
            if param.required:
                raise CommandError(f"{spec.key}: missing required param {name!r} ({param.help})")
            continue
        if param.choices and value not in param.choices:
            raise CommandError(f"{spec.key}: {name} must be one of {', '.join(param.choices)}, not {value!r}")
        clean[name] = value
    return clean


@dataclass
class BuildContext:
    """What a builder needs beyond the data: who asked, where files go, and a place for warnings."""

    brain: Brain
    actor: str = "python"
    out_dir: Path = field(default_factory=lambda: Path("out"))
    warnings: list[str] = field(default_factory=list)
    figures: list[dict[str, Any]] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


Builder = Callable[["Brain", dict[str, str], BuildContext], Any]


class GeneratorFactory:
    """Key -> (Spec, builder). Subclasses get a registry of their own; new entries are decorators."""

    label: ClassVar[str] = "generator"
    _entries: ClassVar[dict[str, tuple[Spec, Builder]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._entries = {}

    @classmethod
    def register(cls, spec: Spec) -> Callable[[Builder], Builder]:
        if spec.key in cls._entries:
            raise ValueError(f"{cls.label} {spec.key!r} already registered")

        def decorate(builder: Builder) -> Builder:
            cls._entries[spec.key] = (spec, builder)
            return builder

        return decorate

    @classmethod
    def get(cls, key: str) -> tuple[Spec, Builder]:
        try:
            return cls._entries[key]
        except KeyError:
            raise NotFound(f"unknown {cls.label} {key!r}; known: {', '.join(cls._entries) or 'none'}") from None

    @classmethod
    def spec(cls, key: str) -> Spec:
        return cls.get(key)[0]

    @classmethod
    def keys(cls) -> list[str]:
        return list(cls._entries)

    @classmethod
    def specs(cls) -> list[Spec]:
        return [spec for spec, _ in cls._entries.values()]

    @classmethod
    def catalog(cls) -> list[dict[str, Any]]:
        return [spec.to_dict() for spec in cls.specs()]

    @classmethod
    def build(cls, key: str, brain: Brain, params: Mapping[str, Any] | None, ctx: BuildContext) -> Any:
        """Look up ``key``, check ``params`` and run the builder."""
        spec, builder = cls.get(key)
        return builder(brain, check_params(spec, params), ctx)


class DiagramFactory(GeneratorFactory):
    """Registry of the diagrams Kletz can draw from the plan with asi_escher."""

    label = "diagram"


class DocumentFactory(GeneratorFactory):
    """Registry of the documents Kletz can print from the plan with asi_gutenberg."""

    label = "document"


register_diagram = DiagramFactory.register
register_document = DocumentFactory.register
