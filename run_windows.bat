@echo off
REM -------------------------------------------------------------------
REM ClearSight - Windows Launcher
REM Starts local server and opens in native Edge WebView2 / App mode.
REM -------------------------------------------------------------------

cd /d %~dp0

echo [*] Starting ClearSight Analytical Core on Windows...
start /b python server.py

timeout /t 2 /nobreak >nul

REM Launch using Microsoft Edge in clean app mode (native WebView2 feel)
start msedge --app=http://127.0.0.1:8540 --window-size=1440,920
echo ClearSight is running. Close this window to shut down the server.
pause >nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8540') do taskkill /f /pid %%a >nul 2>&1
