"""Command layer: the single entry point every front end uses."""

from . import (  # noqa: F401  (registers the built-in commands)
    crud,
    generate,
    gui,
    holiday,
    jira,
    people,
    plan,
    session,
    sprint,
    standards,
    theme,
    tracker,
    transfer,
)
from .base import Argument, Command, Context, Result
from .dispatcher import Dispatcher
from .factory import CommandFactory, default_command_factory, register_command

__all__ = [
    "Argument",
    "Command",
    "CommandFactory",
    "Context",
    "Dispatcher",
    "Result",
    "default_command_factory",
    "register_command",
]
