$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Startup = [Environment]::GetFolderPath("Startup")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "AIServer AutoStart.cmd") -Destination (Join-Path $Startup "AIServer AutoStart.cmd") -Force

$RuleName = "AIServer Real Estate 8787 LocalSubnet"
if (-not (Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8787 -Profile Any -RemoteAddress LocalSubnet | Out-Null
}

Write-Host "로그인 자동 시작, 서버 내부 매일 갱신, 같은 네트워크 접속 허용 설정이 완료되었습니다."
