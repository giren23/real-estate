$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "data\local\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Log = Join-Path $LogDir "daily-$Stamp.log"
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $Python (Join-Path $PSScriptRoot "backfill_local.py") --current-year --force *>&1 | Tee-Object -FilePath $Log
exit $LASTEXITCODE
