@echo off
cd /d D:\AIServer
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File D:\AIServer\scripts\start-local-server.ps1
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File D:\AIServer\scripts\start-public-tunnel.ps1
