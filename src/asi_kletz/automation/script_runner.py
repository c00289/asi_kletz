"""Replay a ``.jsonl`` (or JSON array) of commands through the dispatcher."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..commands.base import Result
from ..errors import NotFound

if TYPE_CHECKING:
    from ..brain import Brain


def read_script(path: str | Path) -> list[dict[str, Any]]:
    file = Path(path)
    if not file.is_file():
        raise NotFound(f"script not found: {file}")
    text = file.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        return [dict(item) for item in json.loads(text)]
    steps: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            steps.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise NotFound(f"{file}:{lineno}: invalid JSON ({exc.msg})") from None
    return steps


def run_script(
    brain: Brain,
    path: str | Path,
    actor: str = "script",
    stop_on_error: bool = False,
) -> list[Result]:
    results: list[Result] = []
    for step in read_script(path):
        result = brain.execute_dict(step, actor=step.get("actor", actor))
        results.append(result)
        if stop_on_error and not result.ok:
            break
    return results
