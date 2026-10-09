@echo off
rem Remove the Smart-Screen autostart task. Files in this folder are kept.
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
call "%~dp0stop.bat"
schtasks /Delete /TN "Smart-Screen" /F
echo Autostart removed. You can delete this folder now, or run install.bat again later.
echo To bring back the old UsbMonitor autostart, open UsbMonitor.exe and tick "Auto Start".
pause
