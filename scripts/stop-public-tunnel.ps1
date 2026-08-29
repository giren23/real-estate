$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot "data\local\run\public-tunnel.pid"
if (-not (Test-Path $PidFile)) {
    Write-Host "실행 중인 공개 터널 기록이 없습니다."
    exit 0
}
$TunnelPid = Get-Content $PidFile -ErrorAction SilentlyContinue
if ($TunnelPid) {
    Stop-Process -Id $TunnelPid -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "공개 터널을 중지했습니다."
