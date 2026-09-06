param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Cloudflared = Join-Path $ProjectRoot "tools\cloudflared.exe"
$RunDir = Join-Path $ProjectRoot "data\local\run"
$PidFile = Join-Path $RunDir "public-tunnel.pid"
$LogFile = Join-Path $RunDir "public-tunnel.log"
$ErrorLog = Join-Path $RunDir "public-tunnel-error.log"
$UrlFile = Join-Path $ProjectRoot "PUBLIC_URL.txt"
$WorkerDir = Join-Path $ProjectRoot "cloudflare-worker"
$Wrangler = Join-Path $WorkerDir "node_modules\.bin\wrangler.cmd"
$R2Flag = Join-Path $ProjectRoot "data\local\r2-enabled.flag"

New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
if (-not (Test-Path $Cloudflared)) {
    throw "cloudflared.exe가 없습니다: $Cloudflared"
}

if (Test-Path $PidFile) {
    $OldPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if ($OldPid -and (Get-Process -Id $OldPid -ErrorAction SilentlyContinue)) {
        if (Test-Path $UrlFile) {
            Write-Host "공개 터널이 이미 실행 중입니다: $(Get-Content $UrlFile)"
        }
        exit 0
    }
}

$HealthUrl = "http://127.0.0.1:$Port/api/health"
for ($Attempt = 1; $Attempt -le 15; $Attempt++) {
    try {
        Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 | Out-Null
        break
    } catch {
        if ($Attempt -eq 15) { throw "로컬 서버가 응답하지 않습니다: $HealthUrl" }
        Start-Sleep -Seconds 1
    }
}

Remove-Item -LiteralPath $LogFile,$ErrorLog -Force -ErrorAction SilentlyContinue
$Process = Start-Process -FilePath $Cloudflared `
    -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port" `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $LogFile -RedirectStandardError $ErrorLog
$Process.Id | Set-Content -Encoding ascii $PidFile

$PublicUrl = ""
for ($Attempt = 1; $Attempt -le 45; $Attempt++) {
    Start-Sleep -Seconds 1
    $Text = ""
    if (Test-Path $LogFile) { $Text += Get-Content -Raw $LogFile -ErrorAction SilentlyContinue }
    if (Test-Path $ErrorLog) { $Text += Get-Content -Raw $ErrorLog -ErrorAction SilentlyContinue }
    $Match = [regex]::Match($Text, "https://[a-z0-9-]+\.trycloudflare\.com")
    if ($Match.Success) {
        $PublicUrl = $Match.Value
        break
    }
    if (-not (Get-Process -Id $Process.Id -ErrorAction SilentlyContinue)) {
        throw "공개 터널이 종료되었습니다. $ErrorLog 파일을 확인하세요."
    }
}

if (-not $PublicUrl) {
    Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue
    throw "45초 안에 공개 주소를 받지 못했습니다. $ErrorLog 파일을 확인하세요."
}

$PublicUrl | Set-Content -Encoding utf8 $UrlFile

# 외부 저장소에는 주소나 코드를 게시하지 않습니다. Worker에는 현재 PC의
# 임시 터널 주소만 설정하며 PC/터널이 꺼지면 고정 주소도 503이 됩니다.
if (Test-Path $Wrangler) {
    try {
        $NodeExecutable = Get-ChildItem "$env:LOCALAPPDATA\OpenAI\Codex\runtimes\cua_node\*\bin\node.exe" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if (-not $NodeExecutable) {
            $NodeExecutable = Get-ChildItem "$env:USERPROFILE\.cache\codex-runtimes\*\dependencies\node\bin\node.exe" -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending | Select-Object -First 1
        }
        if ($NodeExecutable) {
            $env:PATH = "$($NodeExecutable.DirectoryName);$env:PATH"
        }
        Push-Location $WorkerDir
        if (Test-Path -LiteralPath $R2Flag) {
            & $Wrangler deploy --config wrangler.r2.toml --var "UPSTREAM_ORIGIN:$PublicUrl" | Out-Null
        } else {
            & $Wrangler deploy --var "UPSTREAM_ORIGIN:$PublicUrl" | Out-Null
        }
        if ($LASTEXITCODE -ne 0) { throw "Wrangler deploy failed." }
    } catch {
        Write-Warning "The tunnel is active, but the stable Worker address could not be updated: $($_.Exception.Message)"
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "Wrangler is not installed; the stable Worker address was not updated: $Wrangler"
}
Write-Host "공개 접속 주소: $PublicUrl"
