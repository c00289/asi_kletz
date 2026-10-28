"""Dispatcher: normalise arguments, run the command, and never let an exception escape."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..errors import BrainError, ValidationError
from .base import Context, Result
from .factory import CommandFactory, default_command_factory

if TYPE_CHECKING:
    from ..brain import Brain

log = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, brain: Brain, factory: CommandFactory | None = None) -> None:
        self.brain = brain
        self.factory = factory or default_command_factory

    def execute(self, verb: str, args: dict[str, Any] | None = None, actor: str = "python") -> Result:
        try:
            command = self.factory.create(verb)
        except BrainError as exc:
            return Result.failure(str(exc), verb=verb)
        try:
            normalised = self._normalise(command, dict(args or {}))
        except ValueError as exc:
            return Result.failure(str(exc), verb=verb)
        try:
            result = command.run(Context(self.brain, actor), normalised)
        except ValidationError as exc:
            result = Result.failure(*exc.errors)
        except BrainError as exc:
            result = Result.failure(str(exc))
        except Exception as exc:  # the API must always answer with a Result
            log.exception("command %s crashed", verb)
            result = Result.failure(f"{type(exc).__name__}: {exc}")
        result.verb = verb
        return result

    def execute_dict(self, payload: dict[str, Any], actor: str | None = None) -> Result:
        """Run ``{"verb": ..., "args": {...}, "actor": ...}`` (the wire format)."""
        if not isinstance(payload, dict) or "verb" not in payload:
            return Result.failure("payload must be an object with a 'verb' key")
        args = payload.get("args") or {}
        if not isinstance(args, dict):
            return Result.failure("'args' must be an object")
        return self.execute(str(payload["verb"]), args, actor or str(payload.get("actor") or "python"))

    @staticmethod
    def _normalise(command, args: dict[str, Any]) -> dict[str, Any]:
        known = {a.dest: a for a in command.arguments}
        aliases = {a.name: a.dest for a in command.arguments}
        clean: dict[str, Any] = {}
        for key, value in args.items():
            dest = aliases.get(key, key)
            if dest not in known:
                raise ValueError(
                    f"{command.verb}: unknown argument {key!r}; accepts {', '.join(known) or 'nothing'}"
                )
            clean[dest] = value
        for dest, spec in known.items():
            if clean.get(dest) is None:
                if spec.required:
                    raise ValueError(f"{command.verb}: missing required argument {spec.name!r}")
                clean[dest] = spec.default
            elif spec.choices and clean[dest] not in spec.choices:
                raise ValueError(f"{command.verb}: {spec.name} must be one of {', '.join(spec.choices)}")
        return clean
