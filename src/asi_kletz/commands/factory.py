"""CommandFactory: verb -> Command class. New verbs are added with @register_command."""

from __future__ import annotations

from ..errors import NotFound
from .base import Command


class CommandFactory:
    def __init__(self) -> None:
        self._commands: dict[str, type[Command]] = {}

    def register(self, command: type[Command]) -> type[Command]:
        if not command.verb:
            raise ValueError(f"{command.__name__} has no verb")
        if command.verb in self._commands:
            raise ValueError(f"command {command.verb!r} already registered")
        self._commands[command.verb] = command
        return command

    def create(self, verb: str) -> Command:
        return self.get(verb)()

    def get(self, verb: str) -> type[Command]:
        try:
            return self._commands[verb]
        except KeyError:
            raise NotFound(f"unknown command {verb!r}; known: {', '.join(self.verbs())}") from None

    def verbs(self) -> list[str]:
        return list(self._commands)

    def commands(self) -> list[type[Command]]:
        return list(self._commands.values())

    def signatures(self) -> list[dict]:
        return [c.signature() for c in self._commands.values()]


default_command_factory = CommandFactory()


def register_command(command: type[Command]) -> type[Command]:
    return default_command_factory.register(command)
