@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-local-server.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\start-public-tunnel.ps1
pause
