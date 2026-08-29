param(
    [string]$Codes = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RunDir = Join-Path $ProjectRoot "data\local\run"
$LogDir = Join-Path $ProjectRoot "data\local\logs"
$PidFile = Join-Path $RunDir "backfill.pid"
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OutputLog = Join-Path $LogDir "backfill-$Stamp.log"
$ErrorLog = Join-Path $LogDir "backfill-$Stamp-error.log"
New-Item -ItemType Directory -Force -Path $RunDir,$LogDir | Out-Null

if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
        Write-Host "전체 자료 수집이 이미 실행 중입니다. PID: $OldPid"
        exit 0
    }
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$Arguments = @((Join-Path $PSScriptRoot "backfill_local.py"))
if ($Codes) {
    $Arguments += @("--codes", $Codes)
}
$Process = Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $OutputLog -RedirectStandardError $ErrorLog
$Process.Id | Set-Content -Encoding ascii $PidFile
Write-Host "전체 자료 수집을 시작했습니다. PID: $($Process.Id)"
Write-Host "진행 로그: $OutputLog"
