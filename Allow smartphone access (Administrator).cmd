@echo off
net session >nul 2>&1
if not %errorlevel%==0 (
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
netsh advfirewall firewall delete rule name="AIServer Real Estate 8787 LocalSubnet" >nul 2>&1
netsh advfirewall firewall add rule name="AIServer Real Estate 8787 LocalSubnet" dir=in action=allow protocol=TCP localport=8787 remoteip=localsubnet profile=any
echo.
echo 같은 네트워크의 스마트폰과 PC 접속을 허용했습니다.
pause
