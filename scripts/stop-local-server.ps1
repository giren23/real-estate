$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $ProjectRoot "data\local\run\server.pid"
if (-not (Test-Path $PidFile)) {
    Write-Host "실행 중인 AIServer 기록이 없습니다."
    exit 0
}
$ServerPid = Get-Content $PidFile -ErrorAction SilentlyContinue
if ($ServerPid) {
    Stop-Process -Id $ServerPid -Force -ErrorAction SilentlyContinue
}
$Listeners = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
if (-not $Listeners) {
    $Listeners = netstat -ano | Select-String "^\s*TCP\s+\S+:8787\s+\S+\s+LISTENING\s+(\d+)\s*$" | ForEach-Object {
        [pscustomobject]@{ OwningProcess = [int]$_.Matches[0].Groups[1].Value }
    }
}
foreach ($Listener in ($Listeners | Sort-Object OwningProcess -Unique)) {
    Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "AIServer를 중지했습니다."
