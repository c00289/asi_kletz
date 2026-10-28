# Open the ASI Kletz desktop window on the database named in kletz.toml.
# Runs from the repo folder so kletz.toml is found. Extra arguments are passed through,
# for example:  .\gui.ps1 --theme plain
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$exe = Join-Path $PSScriptRoot ".venv\Scripts\asi-kletz-gui.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Virtual environment not found. Run 'uv sync' in $PSScriptRoot first."
}

& $exe @args
exit $LASTEXITCODE
