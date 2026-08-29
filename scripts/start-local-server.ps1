param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RunDir = Join-Path $ProjectRoot "data\local\run"
$PidFile = Join-Path $RunDir "server.pid"
$LogFile = Join-Path $RunDir "server.log"
$ErrorLog = Join-Path $RunDir "server-error.log"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
        Write-Host "AIServer가 이미 실행 중입니다. PID: $OldPid"
        exit 0
    }
}

if (-not (Test-Path $Python)) {
    throw "가상환경이 없습니다. Install AIServer.cmd를 먼저 실행하세요."
}

$env:AISERVER_ROOT = $ProjectRoot
$env:PYTHONPATH = Join-Path $ProjectRoot "src"
$Process = Start-Process -FilePath $Python `
    -ArgumentList "-m", "uvicorn", "realestate.server:app", "--host", "0.0.0.0", "--port", $Port `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLog
$Ready = $false
for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
    Start-Sleep -Milliseconds 250
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
        if ($Health.ok) { $Ready = $true; break }
    } catch { }
}
if (-not $Ready) {
    throw "서버가 시작되지 않았습니다. $ErrorLog 파일을 확인하세요."
}
$ListenerPid = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
if (-not $ListenerPid) {
    $Match = netstat -ano | Select-String "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$" | Select-Object -First 1
    if ($Match -and $Match.Matches.Count) { $ListenerPid = [int]$Match.Matches[0].Groups[1].Value }
}
if (-not $ListenerPid) { $ListenerPid = $Process.Id }
$ListenerPid | Set-Content -Encoding ascii $PidFile
Write-Host "AIServer 시작 완료: http://localhost:$Port/ (PID: $ListenerPid)"
