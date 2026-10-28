from __future__ import annotations

import json

import pytest

from asi_kletz.automation.cli import build_parser, main


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_cli_end_to_end(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    code, res = run(capsys, "--db", db, "create", "safety_plan_row", "--set", "deliverable=hello", "--set", "order=3")
    assert code == 0 and res["ok"] and res["data"]["order"] == 3

    data = '{"deliverable": "t", "status": "Ongoing"}'
    code, res = run(capsys, "--db", db, "--actor", "me", "create", "Safety Plan", "--data", data)
    assert code == 0 and res["data"]["status"] == "Ongoing"

    code, res = run(capsys, "--db", db, "--compact", "list", "safety_plan_row", "--filter", "order=3")
    assert code == 0 and len(res["data"]) == 1

    code, res = run(capsys, "--db", db, "get", "safety_plan_row", "42")
    assert code == 1 and not res["ok"]

    code, res = run(capsys, "--db", db, "get", "safety_plan_row", "1")
    uid = res["data"]["uid"]
    code, res = run(capsys, "--db", db, "get", "safety_plan_row", uid)  # the id positional takes a uid
    assert code == 0 and res["data"]["id"] == 1 and res["data"]["order"] == 3
    code, res = run(capsys, "--db", db, "update", "safety_plan_row", uid, "--set", "status=Done")
    assert code == 0 and res["data"]["id"] == 1 and res["data"]["status"] == "Done"
    other = "00000000-0000-4000-8000-000000000000"
    code, res = run(capsys, "--db", db, "update", "safety_plan_row", uid, "--set", f"uid={other}")
    assert code == 1 and res["errors"] == ["uid is immutable"]
    code, res = run(capsys, "--db", db, "--actor", "me", "delete", "safety_plan_row", uid)
    assert code == 0 and res["data"]["deleted"] == 1

    code, res = run(capsys, "--db", db, "status")
    assert res["data"]["recent_audit"][0]["actor"] == "me"

    code, res = run(capsys, "--db", db, "schema", "safety_plan_row")
    assert res["data"]["name"] == "safety_plan_row"


def test_cli_rejects_bad_json(capsys, tmp_path):
    with pytest.raises(SystemExit):
        main(["--db", str(tmp_path / "x.db"), "create", "safety_plan_row", "--data", "{not json"])


def test_parser_covers_every_verb():
    parser = build_parser()
    verbs = parser._subparsers._group_actions[0].choices  # type: ignore[union-attr]
    assert {"list", "get", "create", "update", "delete", "count", "schema", "status",
            "dump", "load", "export", "import", "run", "theme", "session"} <= set(verbs)


def test_parser_has_the_no_forward_flag():
    assert build_parser().parse_args(["--no-forward", "status"]).no_forward is True
    assert build_parser().parse_args(["status"]).no_forward is False


def test_session_verb_with_no_window_opens_no_database(tmp_path, capsys):
    from asi_kletz.automation.session import session_path

    db = tmp_path / "never.db"
    code, res = run(capsys, "--db", str(db), "session")
    assert code == 0 and res["ok"] and res["verb"] == "session"
    assert res["data"] == {"path": str(session_path()), "present": False, "alive": False, "reachable": False,
                           "session": None, "status": None, "quit": False}
    assert not db.exists() and not (tmp_path / "locks" / "primary.lock").exists()
    code, res = run(capsys, "session", "--quit")
    assert code == 1 and not res["ok"] and "no live automation session" in res["errors"][0]
    assert not db.exists()


def test_session_verb_is_registered_with_the_quit_flag(brain):
    from asi_kletz.commands import default_command_factory

    command = default_command_factory.get("session")
    assert [a.name for a in command.arguments] == ["quit"] and command.arguments[0].type == "bool"
    assert "session" in brain.status()["commands"]
    result = brain.execute("session")
    assert result.ok and result.data["present"] is False and result.data["alive"] is False


def test_theme_verb_lists_latches_and_rejects(tmp_path, capsys):
    from asi_kletz.prefs import prefs_path

    db = str(tmp_path / "cli.db")
    code, res = run(capsys, "--db", db, "theme")
    assert code == 0 and res["ok"]
    data = res["data"]
    assert len(data["themes"]) == 32 and data["latched"] is None and data["theme"] == "cyan-neon"
    assert data["default"] == "cyan-neon" and data["prefs"] == str(prefs_path())
    assert data["themes"][0] == {"key": "cyan-noir", "title": "Cyan Noir", "family": "cyan", "tone": "noir",
                                 "primary": "#12c0e2", "accent": "#ec7813"}
    assert "tron" not in {t["key"] for t in data["themes"]}

    code, res = run(capsys, "--db", db, "theme", "pink-noir")
    assert code == 0 and res["ok"] and res["data"]["latched"] == "pink-noir" and res["data"]["theme"] == "pink-noir"
    assert json.loads(prefs_path().read_text(encoding="utf-8"))["theme"] == "pink-noir"

    code, res = run(capsys, "--db", db, "theme", "--list")
    assert code == 0 and res["data"]["latched"] == "pink-noir" and len(res["data"]["themes"]) == 32

    code, res = run(capsys, "--db", db, "theme", "nope")
    assert code == 1 and not res["ok"] and "unknown theme 'nope'" in res["errors"][0]
    assert json.loads(prefs_path().read_text(encoding="utf-8"))["theme"] == "pink-noir"

    code, res = run(capsys, "--db", db, "theme", "tron")
    assert code == 0 and res["data"]["latched"] == "cyan-neon"


def test_theme_verb_publishes_theme_changed(brain):
    result = brain.execute("theme", key="pink-noir", actor="agent")
    assert result.ok
    event = brain.events.last(1)[0]
    assert event["topic"] == "theme.changed" and event["theme"] == "pink-noir" and event["actor"] == "agent"
    assert brain.execute("theme").data["latched"] == "pink-noir"
    assert "theme" in brain.status()["commands"]


def test_cli_is_refused_with_exit_3_while_another_process_runs(tmp_path, capsys):
    from tests.test_locks import _release, hold_brain

    db = str(tmp_path / "cli.db")
    proc = hold_brain(tmp_path / "held.db")
    try:
        code, res = run(capsys, "--db", db, "status")
        assert code == 3 and not res["ok"] and res["verb"] == "status"
        assert res["data"]["slot"] == "family" and res["data"]["holder"]["pid"] == proc.held_pid
        assert res["data"]["holder"]["tool"] == "asi_kletz" and "is running" in res["errors"][0]
        assert not (tmp_path / "cli.db").exists()
        code, res = run(capsys, "--db", db, "--wait", "0.3", "--compact", "list", "safety_plan_row")
        assert code == 3 and res["data"]["slot"] == "family"
    finally:
        _release(proc)
    code, res = run(capsys, "--db", db, "status")
    assert code == 0 and res["ok"] and res["data"]["locks"]["family"]["pid"] == __import__("os").getpid()


def test_cli_wait_succeeds_when_the_holder_leaves_in_time(tmp_path, capsys):
    from tests.test_locks import _release, hold_brain

    proc = hold_brain(tmp_path / "held.db", hold="0.5")
    try:
        code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "--wait", "10", "count", "safety_plan_row")
        assert code == 0 and res["ok"] and res["data"]["count"] == 0
    finally:
        _release(proc)


def test_parser_has_the_wait_flag():
    ns = build_parser().parse_args(["--wait", "2.5", "status"])
    assert ns.wait == 2.5 and build_parser().parse_args(["status"]).wait == 0.0
