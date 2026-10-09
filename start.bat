@echo off
rem Start Smart-Screen through its scheduled task (runs as admin without a UAC prompt)
schtasks /Run /TN "Smart-Screen" >nul 2>&1
if errorlevel 1 (
  echo Smart-Screen is not installed yet. Run install.bat first.
  pause
) else (
  echo Smart-Screen started.
)
