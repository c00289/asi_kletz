"""OutlookService: the Outlook address book on this machine, searched for a name (0.20.0).

The owner, 2026-10-29: "use the outlook method please" for the names a role parameter holds. A person types
part of a name; the tool asks Outlook desktop through its COM automation (PowerShell, ``New-Object -ComObject
Outlook.Application``, the same subprocess pattern as asi_gutenberg's ``pdf_with_word``): an exact hit through
``Session.CreateRecipient(text).Resolve()``, then the Global Address List's ``AddressEntries`` for the partial
matches, each entry's ``Name`` and its SMTP address (``GetExchangeUser().PrimarySmtpAddress``, else the
``PR_SMTP_ADDRESS`` property). Nothing is stored here: the caller keeps the one line the person picks.

The COM call is one function, ``run_outlook``, that the tests monkeypatch; ``lookup`` is the pure part around
it. A machine without Outlook, a refused COM call, or a timeout is one ``OutlookUnavailable`` with one clear
line, never a traceback; the PowerShell process ends with the call (``timeout``), nothing is left running.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

from ..errors import CommandError

TIMEOUT = 45.0  # seconds: the GAL walk of a large company can take a while; the picker says it is searching
LIMIT = 30  # matches at most: a partial name that hits more wants more letters
NOT_WINDOWS = "the Outlook address book needs Windows with Outlook desktop installed"
NO_OUTLOOK = "Outlook is not available on this machine (no Outlook desktop, or its COM automation refused): "
# the SMTP address of an address entry that is not an Exchange user (a contact, a one-off address)
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"


class OutlookUnavailable(CommandError):
    """One line: why the lookup could not ask Outlook."""


def _ps(text: str) -> str:
    """A PowerShell single-quoted literal of ``text``."""
    return text.replace("'", "''")


SCRIPT = """
$ErrorActionPreference = 'Stop'
$text = '{text}'
$limit = {limit}
$before = @(Get-Process OUTLOOK -ErrorAction SilentlyContinue | ForEach-Object Id)
$o = New-Object -ComObject Outlook.Application
$ns = $o.GetNamespace('MAPI')
$out = New-Object System.Collections.ArrayList
$seen = @{{}}
function Add-Hit($entry) {{
  if ($null -eq $entry) {{ return }}
  $name = [string]$entry.Name
  $email = ''
  try {{ $u = $entry.GetExchangeUser(); if ($null -ne $u) {{ $email = [string]$u.PrimarySmtpAddress }} }} catch {{}}
  if (-not $email) {{ try {{ $email = [string]$entry.PropertyAccessor.GetProperty('{smtp}') }} catch {{}} }}
  if (-not $email) {{ try {{ $email = [string]$entry.Address }} catch {{}} }}
  if (-not $name -or -not $email -or $email -notmatch '@') {{ return }}
  $key = $email.ToLowerInvariant()
  if ($seen.ContainsKey($key)) {{ return }}
  $seen[$key] = 1
  [void]$out.Add(@{{ name = $name; email = $email }})
}}
try {{ $r = $ns.CreateRecipient($text); if ($r.Resolve()) {{ Add-Hit $r.AddressEntry }} }} catch {{}}
try {{
  $entries = $ns.GetGlobalAddressList().AddressEntries
  $e = $entries.GetFirst()
  while ($null -ne $e -and $out.Count -lt $limit) {{
    if ($e.Name -like ('*' + $text + '*')) {{ Add-Hit $e }}
    $e = $entries.GetNext()
  }}
}} catch {{}}
ConvertTo-Json -Compress -InputObject @($out)
if ($before.Count -eq 0) {{ try {{ $o.Quit() }} catch {{}} }}
"""


def script(text: str, limit: int = LIMIT) -> str:
    """The PowerShell that asks Outlook for ``text`` and prints a JSON array of ``{name, email}``: the exact
    hit first (``CreateRecipient(text).Resolve()``), then the Global Address List's entries whose name
    contains ``text``, up to ``limit``; each with its SMTP address."""
    return SCRIPT.format(text=_ps(text), limit=int(limit), smtp=PR_SMTP_ADDRESS)


def run_outlook(text: str, timeout: float = TIMEOUT, limit: int = LIMIT) -> str:
    """The COM call, isolated: run the PowerShell for ``text`` and return its stdout (JSON). Raises
    ``OutlookUnavailable`` when there is no Outlook, the call is refused, or it times out. The tests
    monkeypatch this function; nothing in the suite launches Outlook."""
    if os.name != "nt":
        raise OutlookUnavailable(NOT_WINDOWS)
    try:
        run = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script(text, limit)],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        raise OutlookUnavailable(NO_OUTLOOK + f"no answer within {timeout:.0f} s") from None
    except OSError as exc:
        raise OutlookUnavailable(NO_OUTLOOK + str(exc)) from None
    if run.returncode != 0 or not run.stdout.strip():
        detail = (run.stderr or run.stdout or "").strip().splitlines()
        raise OutlookUnavailable(NO_OUTLOOK + (detail[0].strip() if detail else f"exit {run.returncode}"))
    return run.stdout


def matches_from(payload: Any) -> list[dict[str, str]]:
    """``[{name, email, text}]`` from the script's JSON (a list, or one object when there was one hit)."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise OutlookUnavailable(NO_OUTLOOK + f"unreadable answer: {exc}") from None
    if isinstance(payload, dict):
        payload = [payload]
    if payload is None:
        payload = []
    if not isinstance(payload, list):
        raise OutlookUnavailable(NO_OUTLOOK + "unreadable answer")
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("name") or "").split())
        email = str(item.get("email") or "").strip()
        if not name or "@" not in email or email.casefold() in seen:
            continue
        seen.add(email.casefold())
        out.append({"name": name, "email": email, "text": f"{name} <{email}>"})
    return out


def lookup(text: str, timeout: float = TIMEOUT, limit: int = LIMIT) -> dict[str, Any]:
    """The matches for ``text`` (part of a name; at least two characters): ``{"text", "count", "matches":
    [{name, email, text}], "limit"}``. Only ever called because a person pressed, or an agent asked."""
    needle = " ".join(str(text or "").split())
    if len(needle) < 2:
        raise CommandError("people lookup needs at least two characters of a name")
    matches = matches_from(run_outlook(needle, timeout, limit))
    return {"text": needle, "count": len(matches), "matches": matches, "limit": limit, "source": "outlook"}


def outlook_present() -> bool:
    """Whether Outlook desktop is installed here (its executable is where Office puts it); for the one test
    that does a real lookup, nothing else."""
    if os.name != "nt":
        return False
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if root and os.path.isfile(os.path.join(root, "Microsoft Office", "root", "Office16", "OUTLOOK.EXE")):
            return True
    return False
