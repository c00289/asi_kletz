"""Command, Argument, Context, and Result: the vocabulary of the command layer."""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ..brain import Brain


@dataclass
class Result:
    """Structured outcome of a command. Serialises to JSON for every transport."""

    ok: bool = True
    data: Any = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    verb: str | None = None

    @classmethod
    def success(
        cls, data: Any = None, warnings: list[str] | tuple[str, ...] = (), verb: str | None = None
    ) -> Result:
        return cls(True, data, [], list(warnings), verb)

    @classmethod
    def failure(cls, *errors: str, data: Any = None, verb: str | None = None) -> Result:
        return cls(False, data, list(errors), [], verb)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "verb": self.verb, "data": self.data, "errors": self.errors, "warnings": self.warnings}

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False, default=str)


@dataclass(frozen=True)
class Argument:
    """Declares one command argument; the CLI and ``schema`` output are built from these."""

    name: str
    help: str = ""
    required: bool = False
    flag: bool = False  # True: --option, False: positional
    type: str = "str"  # str | int | json | kv | path | bool
    choices: tuple[str, ...] = ()
    default: Any = None
    multiple: bool = False

    @property
    def dest(self) -> str:
        return self.name.replace("-", "_")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "help": self.help, "required": self.required, "flag": self.flag,
            "type": self.type, "choices": list(self.choices), "default": self.default,
            "multiple": self.multiple,
        }


@dataclass
class Context:
    brain: Brain
    actor: str = "python"


class Command(abc.ABC):
    verb: ClassVar[str] = ""
    help: ClassVar[str] = ""
    arguments: ClassVar[tuple[Argument, ...]] = ()

    @abc.abstractmethod
    def run(self, ctx: Context, args: dict[str, Any]) -> Result: ...

    @classmethod
    def signature(cls) -> dict[str, Any]:
        return {"verb": cls.verb, "help": cls.help, "arguments": [a.to_dict() for a in cls.arguments]}


def parse_kv(items: Any) -> dict[str, Any]:
    """Turn ``["k=v", ...]`` (or a dict) into a dict. Used by --filter and --set."""
    if items is None:
        return {}
    if isinstance(items, dict):
        return dict(items)
    if isinstance(items, str):
        items = [items]
    out: dict[str, Any] = {}
    for item in items:
        if isinstance(item, dict):
            out.update(item)
            continue
        key, sep, value = str(item).partition("=")
        if not sep or not key.strip():
            raise ValueError(f"expected key=value, got {item!r}")
        out[key.strip()] = value
    return out


def merge_data(args: dict[str, Any]) -> dict[str, Any]:
    """Combine ``--data`` (JSON object) and ``--set k=v`` into one row dict."""
    data = args.get("data")
    if isinstance(data, str):
        data = json.loads(data) if data.strip() else {}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("--data must be a JSON object")
    data = dict(data)
    data.update(parse_kv(args.get("set")))
    return data
