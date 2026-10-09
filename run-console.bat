@echo off
rem Run Smart-Screen in a console window to see what it is doing (for troubleshooting).
rem Run it as administrator to get temperatures. Stop the normal one first (stop.bat).
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py --console
pause
