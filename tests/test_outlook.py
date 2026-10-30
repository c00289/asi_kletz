"""0.20.0, the owner, 2026-10-29: "use the outlook method please". The Outlook address book lookup: the
PowerShell script, the parsing of its answer, the service and the ``people lookup`` verb with the COM call
monkeypatched (nothing here launches Outlook), every way the machine can say no, and one real lookup of the
owner's own name that runs only where Outlook desktop is installed and prints nothing."""

from __future__ import annotations

import json
import subprocess

import pytest

from asi_kletz.errors import CommandError
from asi_kletz.services import outlook_service as outlook
from asi_kletz.services.outlook_service import (
    LIMIT,
    NO_OUTLOOK,
    NOT_WINDOWS,
    PR_SMTP_ADDRESS,
    OutlookUnavailable,
    lookup,
    matches_from,
    outlook_present,
    run_outlook,
    script,
)
from tests.test_cli import run

ANN = {"name": "Ann Lee", "email": "ann.lee@asirobots.com"}
BEN = {"name": "Ben Ray", "email": "Ben.Ray@asirobots.com"}


def _answer(*items):
    return json.dumps(list(items))


@pytest.fixture
def com(monkeypatch):
    """The COM call replaced: records what it was asked and answers from ``com.answer`` (JSON text) or raises
    ``com.failure``."""

    class Com:
        def __init__(self) -> None:
            self.answer = _answer(ANN, BEN)
            self.failure: Exception | None = None
            self.calls: list[tuple[str, float, int]] = []

        def __call__(self, text, timeout=outlook.TIMEOUT, limit=LIMIT):
            self.calls.append((text, timeout, limit))
            if self.failure is not None:
                raise self.failure
            return self.answer

    stub = Com()
    monkeypatch.setattr(outlook, "run_outlook", stub)
    return stub


# -- the script and the parsing ------------------------------------------------------------------------------


def test_the_script_asks_outlook_the_owners_way():
    text = script("O'Brien", limit=7)
    assert "New-Object -ComObject Outlook.Application" in text and "GetNamespace('MAPI')" in text
    assert "$text = 'O''Brien'" in text and "$limit = 7" in text  # the quote escaped, the cap in place
    assert "CreateRecipient($text)" in text and ".Resolve()" in text  # the exact hit
    assert "GetGlobalAddressList().AddressEntries" in text and "-like ('*' + $text + '*')" in text  # the partials
    assert "GetExchangeUser()" in text and "PrimarySmtpAddress" in text and PR_SMTP_ADDRESS in text
    assert "ConvertTo-Json" in text and "$o.Quit()" in text  # JSON out; an Outlook this call started is ended


def test_matches_from_reads_the_answer_and_drops_what_is_not_a_person():
    payload = [ANN, BEN, {"name": "Ben Ray", "email": "ben.ray@asirobots.com"},  # the same email, another case
               {"name": "", "email": "x@y.io"}, {"name": "No Email", "email": ""}, {"name": "Odd", "email": "odd"},
               "not a dict"]
    matches = matches_from(json.dumps(payload))
    assert matches == [
        {"name": "Ann Lee", "email": "ann.lee@asirobots.com", "text": "Ann Lee <ann.lee@asirobots.com>"},
        {"name": "Ben Ray", "email": "Ben.Ray@asirobots.com", "text": "Ben Ray <Ben.Ray@asirobots.com>"},
    ]
    assert matches_from(json.dumps(ANN))[0]["text"] == "Ann Lee <ann.lee@asirobots.com>"  # one hit: an object
    assert matches_from("null") == [] and matches_from("[]") == [] and matches_from([]) == []
    with pytest.raises(OutlookUnavailable) as info:
        matches_from("{not json")
    assert str(info.value).startswith(NO_OUTLOOK + "unreadable answer")
    with pytest.raises(OutlookUnavailable):
        matches_from('"a string"')


# -- the service and the verb, the COM call monkeypatched ------------------------------------------------


def test_lookup_answers_with_the_matches_and_stores_nothing(com, seeded):
    data = lookup("  ann   lee ")
    assert data == {
        "text": "ann lee", "count": 2, "source": "outlook", "limit": LIMIT,
        "matches": [
            {"name": "Ann Lee", "email": "ann.lee@asirobots.com", "text": "Ann Lee <ann.lee@asirobots.com>"},
            {"name": "Ben Ray", "email": "Ben.Ray@asirobots.com", "text": "Ben Ray <Ben.Ray@asirobots.com>"},
        ],
    }
    assert com.calls == [("ann lee", outlook.TIMEOUT, LIMIT)]
    with pytest.raises(CommandError, match="at least two characters"):
        lookup("a")
    assert len(com.calls) == 1  # refused before any COM call
    result = seeded.execute("people", action="lookup", text="Ann", limit=5)
    assert result.ok and result.data["count"] == 2 and com.calls[-1] == ("Ann", outlook.TIMEOUT, 5)
    assert [m["text"] for m in result.data["matches"]] == [
        "Ann Lee <ann.lee@asirobots.com>", "Ben Ray <Ben.Ray@asirobots.com>",
    ]
    assert seeded.execute("people", action="lookup", text="").errors == ["people lookup needs <text>, part of a name"]
    assert seeded.execute("count", entity="parameter").data["count"] == 0  # nothing stored
    assert all(entry["action"] != "people" for entry in seeded.storage.audit_tail(10))


def test_a_machine_without_outlook_gives_one_clear_line(com, seeded):
    com.failure = OutlookUnavailable(NO_OUTLOOK + "Retrieving the COM class factory failed")
    result = seeded.execute("people", action="lookup", text="Ann")
    assert not result.ok and result.errors == [NO_OUTLOOK + "Retrieving the COM class factory failed"]


def test_the_cli_lookup_prints_the_matches(com, tmp_path, capsys):
    code, res = run(capsys, "--db", str(tmp_path / "cli.db"), "people", "lookup", "Ann")
    assert code == 0 and res["ok"] and res["data"]["count"] == 2
    assert res["data"]["matches"][0]["text"] == "Ann Lee <ann.lee@asirobots.com>"


def test_run_outlook_turns_every_refusal_into_one_line(monkeypatch):
    monkeypatch.setattr(outlook.os, "name", "posix")
    with pytest.raises(OutlookUnavailable, match=NOT_WINDOWS):
        run_outlook("Ann")
    monkeypatch.setattr(outlook.os, "name", "nt")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        outcome = fake_run.outcome
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", fake_run)
    fake_run.outcome = subprocess.TimeoutExpired("powershell", 45)
    with pytest.raises(OutlookUnavailable, match="no answer within 45 s"):
        run_outlook("Ann")
    assert calls[-1][0][:4] == ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    assert calls[-1][1]["timeout"] == outlook.TIMEOUT and "$text = 'Ann'" in calls[-1][0][4]
    fake_run.outcome = OSError("no powershell")
    with pytest.raises(OutlookUnavailable, match="no powershell"):
        run_outlook("Ann")
    fake_run.outcome = subprocess.CompletedProcess([], 1, stdout="", stderr="New-Object : COM refused\nmore")
    with pytest.raises(OutlookUnavailable, match="COM refused"):
        run_outlook("Ann")
    fake_run.outcome = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    with pytest.raises(OutlookUnavailable, match="exit 0"):
        run_outlook("Ann")
    fake_run.outcome = subprocess.CompletedProcess([], 0, stdout=_answer(ANN), stderr="")
    assert run_outlook("Ann", timeout=3, limit=2) == _answer(ANN) and calls[-1][1]["timeout"] == 3


# -- the one real lookup ---------------------------------------------------------------------------------------


@pytest.mark.skipif(not outlook_present(), reason="Outlook desktop is not installed here")
def test_a_real_lookup_of_the_owners_name_finds_someone():
    """Runs only where Outlook desktop is installed (the owner's machine, never CI): the owner's own name, read
    from the git identity so that no person is named here, is in the address book, so the lookup is non-empty;
    nothing about the matches is printed."""
    me = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, check=False).stdout.strip()
    if not me:
        pytest.skip("no git identity to look up")
    data = lookup(me)
    assert data["count"] >= 1 and all(m["name"] and "@" in m["email"] for m in data["matches"])
