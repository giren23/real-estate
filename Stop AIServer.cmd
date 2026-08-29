@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\stop-public-tunnel.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\stop-local-server.ps1
pause
