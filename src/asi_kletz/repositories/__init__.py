"""Repository layer: per-entity CRUD over a storage backend."""

from .factory import RepositoryFactory
from .sql_repo import SqlRepository

__all__ = ["RepositoryFactory", "SqlRepository"]
