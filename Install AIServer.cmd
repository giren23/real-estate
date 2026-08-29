@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python 가상환경이 없습니다. D:\AIServer\.venv를 확인해 주세요.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
set PYTHONPATH=%CD%\src
".venv\Scripts\python.exe" scripts\backfill_local.py --initialize-only
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local-server.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-public-tunnel.ps1
echo.
echo 설치와 실행이 완료되었습니다.
pause
