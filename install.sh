#!/usr/bin/env bash
set -euo pipefail
git add .
git commit -m "Install nationwide real-estate platform" || true
git push origin main
echo "업로드 완료. GitHub Actions에서 Bootstrap real-estate data를 실행하세요."
