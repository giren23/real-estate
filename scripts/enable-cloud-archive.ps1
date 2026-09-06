$ErrorActionPreference = "Stop"
$Bucket = "korean-real-estate-archive"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Wrangler = Join-Path $ProjectRoot "cloudflare-worker\node_modules\.bin\wrangler.cmd"
$Flag = Join-Path $ProjectRoot "data\local\r2-enabled.flag"

if (-not (Test-Path -LiteralPath $Python)) { throw "Python 가상환경을 찾지 못했습니다." }
if (-not (Test-Path -LiteralPath $Wrangler)) { throw "Wrangler를 찾지 못했습니다." }
$env:PYTHONPATH = Join-Path $ProjectRoot "src"

Push-Location (Join-Path $ProjectRoot "cloudflare-worker")
try {
    & $Wrangler r2 bucket info $Bucket | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $Wrangler r2 bucket create $Bucket
        if ($LASTEXITCODE -ne 0) {
            throw "R2 버킷을 만들지 못했습니다. Cloudflare Dashboard의 Storage & databases > R2에서 R2를 먼저 활성화하세요."
        }
    }
} finally { Pop-Location }

& $Python (Join-Path $ProjectRoot "scripts\backup_real_estate_db.py") --label before-r2-enable
if ($LASTEXITCODE -ne 0) { throw "원본 DB 백업 검증에 실패하여 공개 보관소 생성을 중단했습니다." }
& $Python (Join-Path $ProjectRoot "scripts\export_real_estate_archive.py")
if ($LASTEXITCODE -ne 0) { throw "공개 분할 자료 생성에 실패했습니다." }
& $Python (Join-Path $ProjectRoot "scripts\upload_real_estate_archive.py") --bucket $Bucket
if ($LASTEXITCODE -ne 0) { throw "R2 업로드 또는 재다운로드 검증에 실패했습니다." }

Push-Location (Join-Path $ProjectRoot "cloudflare-worker")
try {
    & $Wrangler deploy --config wrangler.r2.toml --keep-vars
    if ($LASTEXITCODE -ne 0) { throw "Worker 배포에 실패했습니다." }
} finally { Pop-Location }

"enabled $(Get-Date -Format o) bucket=$Bucket" | Set-Content -LiteralPath $Flag -Encoding utf8
Write-Host "Cloudflare 공개 실거래 보관소가 활성화됐습니다. 다음 수집부터 자동 검증·업로드됩니다."
