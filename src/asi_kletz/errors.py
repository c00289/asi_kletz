"""Exception hierarchy. Every error the core raises on purpose derives from BrainError."""

from __future__ import annotations


class BrainError(Exception):
    """Base class for errors raised by ASI Kletz."""


class ValidationError(BrainError, ValueError):
    """A row did not satisfy its entity schema. ``errors`` lists every problem found."""

    def __init__(self, entity: str, errors: list[str] | tuple[str, ...]):
        self.entity = entity
        self.errors = list(errors)
        super().__init__(f"{entity}: " + "; ".join(self.errors))


class NotFound(BrainError, LookupError):
    """A row, entity, command, or file was asked for and does not exist."""


class CommandError(BrainError):
    """A command was called with bad arguments."""


class StorageError(BrainError):
    """The storage backend could not complete an operation."""


def __getattr__(name: str):
    # ``PrimaryToolBusy`` lives in ``locks.py`` with the lock it reports; it is reachable from here too.
    if name == "PrimaryToolBusy":
        from .locks import PrimaryToolBusy

        return PrimaryToolBusy
    raise AttributeError(name)
