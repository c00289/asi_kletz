"""CLI front end: ``asi-kletz <verb> ...``. Built from the command signatures, prints JSON.

Exit codes: 0 the command ran and succeeded, 1 it ran and failed, 3 it never ran because the
family lock refused it. Since 0.7.0 a refusal by a **Kletz window** with a live automation
session is forwarded to that window (``POST /execute`` on its local server) and the forwarded
``Result`` is printed untouched, exit 0 or 1 by its ``ok``; ``--no-forward`` turns that off. A
window of the sister tool, a dead or missing session, or a session that does not answer is still
exit 3. ``session`` is the one verb that opens no ``Brain`` and therefore needs no forwarding.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from ..commands import CommandFactory, Result, default_command_factory
from ..version import __version__

SESSION_VERB = "session"
NO_SESSION_HINT = (
    "; no automation session; the window may have been started with --no-server or ASI_KLETZ_AUTOMATION=off"
)


def _bool(text: str) -> bool:
    return text.strip().lower() in {"1", "true", "yes", "y", "on"}


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from None


_TYPES = {"str": str, "path": str, "int": int, "json": _json, "kv": str, "bool": _bool}


def build_parser(factory: CommandFactory | None = None) -> argparse.ArgumentParser:
    factory = factory or default_command_factory
    parser = argparse.ArgumentParser(
        prog="asi-kletz",
        description="ASI Kletz: FuSa safety-plan API. Every verb prints a JSON Result.",
    )
    parser.add_argument("--db", help="SQLite file (default: $ASI_KLETZ_DB or ./kletz.db)")
    parser.add_argument("--actor", default="cli", help="Who is driving (recorded in the audit log)")
    parser.add_argument("--compact", action="store_true", help="Print single-line JSON")
    parser.add_argument(
        "--wait",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Queue for the family lock this long (polling every 250 ms) instead of refusing at once "
        "with exit code 3 while another primary tool, or another Kletz, is running",
    )
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="Never forward to a running Kletz window's automation session: a refusal is exit code 3 "
        "(and --wait queues) exactly as if the window had no server",
    )
    parser.add_argument("--version", action="version", version=f"asi-kletz {__version__}")
    sub = parser.add_subparsers(dest="verb", metavar="<verb>", required=True)
    for command in factory.commands():
        sp = sub.add_parser(command.verb, help=command.help, description=command.help)
        for arg in command.arguments:
            kwargs: dict[str, Any] = {"help": arg.help, "type": _TYPES.get(arg.type, str)}
            if arg.choices:
                kwargs["choices"] = list(arg.choices)
            if arg.flag:
                if arg.multiple:
                    kwargs["action"] = "append"
                if arg.type == "bool":  # `--list` alone means true; `--list false` still works
                    kwargs["nargs"] = "?"
                    kwargs["const"] = True
                kwargs["default"] = arg.default
                kwargs["required"] = arg.required
                kwargs["dest"] = arg.dest
                sp.add_argument(f"--{arg.name}", **kwargs)
            else:
                if arg.multiple:
                    kwargs["nargs"] = "+" if arg.required else "*"
                elif not arg.required:
                    kwargs["nargs"] = "?"
                    kwargs["default"] = arg.default
                sp.add_argument(arg.dest, metavar=arg.name, **kwargs)
    return parser


EXIT_BUSY = 3  # another primary tool holds the family lock; 1 still means "the command ran and failed"


def _print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:  # Windows consoles without UTF-8
        sys.stdout.buffer.write(text.encode("utf-8", "replace") + b"\n")


def _forward_or_refuse(exc: Any, ns: argparse.Namespace, args: dict[str, Any]) -> tuple[Result, int]:
    """After a lock refusal: the forwarded ``Result`` (exit 0/1), or the refusal with a hint (exit 3).

    Forward only to a window of the same tool (the holder says ``asi_kletz`` and its pid is the
    session file's) whose session is alive (pid alive, ``GET /status`` answering as that pid).
    """
    from ..locks import TOOL, resolve_db_key
    from .session import SessionUnreachable, forward, probe, read_session

    holder = exc.holder or {}
    refusal = {"slot": exc.slot, "holder": exc.holder}
    hint = ""
    if not ns.no_forward and holder.get("tool") == TOOL:
        session = read_session()
        if session is None or session.get("pid") != holder.get("pid"):
            hint = NO_SESSION_HINT
        elif probe(session) is None:
            hint = f"; the automation session at {session['address']} did not answer"
        else:
            if ns.db and session.get("db") and resolve_db_key(ns.db) != resolve_db_key(session["db"]):
                print(
                    f"warning: --db {ns.db} ignored; the command runs in the open window on {session['db']}",
                    file=sys.stderr,
                )
            try:
                result = forward(session, ns.verb, args, actor=ns.actor)
            except SessionUnreachable as reason:
                hint = f"; the automation session at {session['address']} did not answer ({reason})"
            else:
                return result, (0 if result.ok else 1)
    return Result.failure(str(exc) + hint, data=refusal, verb=ns.verb), EXIT_BUSY


def main(argv: list[str] | None = None) -> int:
    from ..brain import Brain
    from ..locks import PrimaryToolBusy

    factory = default_command_factory
    parser = build_parser(factory)
    ns = parser.parse_args(argv)
    command = factory.get(ns.verb)
    args = {a.dest: getattr(ns, a.dest, None) for a in command.arguments}
    indent = None if ns.compact else 2
    if ns.verb == SESSION_VERB:  # touches no database: works while a window holds the lock
        from ..commands.session import SessionCommand

        result = SessionCommand.report(quit=bool(args.get("quit")))
        _print(result.to_json(indent=indent))
        return 0 if result.ok else 1
    try:
        brain = Brain(ns.db, wait=ns.wait)
    except PrimaryToolBusy as exc:
        result, code = _forward_or_refuse(exc, ns, args)
        _print(result.to_json(indent=indent))
        return code
    with brain:
        result = brain.execute(ns.verb, args, actor=ns.actor)
    _print(result.to_json(indent=indent))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
