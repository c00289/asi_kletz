"""Lookup lists: the small reference tables behind enum fields.

Lookups are *soft* in the alpha: a value outside the list produces a warning,
not an error, so real-world data from the workbook always loads. Values can be
added at runtime with ``LookupRegistry.add``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping


class LookupRegistry(Mapping[str, tuple[str, ...]]):
    def __init__(self) -> None:
        self._lists: dict[str, tuple[str, ...]] = {}

    def register(self, name: str, values: Iterable[str]) -> None:
        if name in self._lists:
            raise ValueError(f"lookup {name!r} already registered")
        self._lists[name] = tuple(dict.fromkeys(str(v) for v in values))

    def add(self, name: str, value: str) -> None:
        current = self._lists.get(name, ())
        if value not in current:
            self._lists[name] = current + (value,)

    def __getitem__(self, name: str) -> tuple[str, ...]:
        return self._lists[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._lists)

    def __len__(self) -> int:
        return len(self._lists)

    def to_dict(self) -> dict[str, list[str]]:
        return {name: list(values) for name, values in self._lists.items()}


default_lookups = LookupRegistry()
