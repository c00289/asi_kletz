# Open the ASI Kletz desktop window on the database named in kletz.toml.
# Runs from the repo folder so kletz.toml is found. Extra arguments are passed through,
# for example:  .\gui.ps1 --theme plain
#
# 0.27.3: the environment is synced first ("uv sync"), so a launch after a sibling's release, or after an
# install that half-applied, heals itself. The repos live under OneDrive, which holds a freshly written
# folder for a moment while it uploads it; an install that lands in that moment fails with "Access is
# denied" on a .dist-info folder and leaves the launcher missing (the owner met "Virtual environment not
# found" that way on 2026-10-30). So the sync is tried up to three times, two seconds apart. A sync that
# still cannot run is a warning, not a stop: the window starts on the environment as it is.
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv) {
    $synced = $false
    foreach ($attempt in 1..3) {
        & uv sync --quiet
        if ($LASTEXITCODE -eq 0) { $synced = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $synced) {
        Write-Warning "uv sync failed three times (OneDrive may be holding a folder under .venv); starting the window on the environment as it is."
    }
} else {
    Write-Warning "uv is not on PATH; the environment is not synced before the window starts."
}

$exe = Join-Path $PSScriptRoot ".venv\Scripts\asi-kletz-gui.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Virtual environment not found. Run 'uv sync' in $PSScriptRoot first (again, if OneDrive was holding a folder)."
}

& $exe @args
exit $LASTEXITCODE
