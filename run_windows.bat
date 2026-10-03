@echo off
REM -------------------------------------------------------------------
REM Sukat by Lunsad - Windows Launcher
REM Starts local server and opens in native Edge WebView2 / App mode.
REM -------------------------------------------------------------------

cd /d %~dp0

echo [*] Starting Sukat Analytical Core on Windows...
start /b python server.py

timeout /t 2 /nobreak >nul

REM Launch using Microsoft Edge in clean app mode (native WebView2 feel)
start msedge --app=http://127.0.0.1:8540 --window-size=1440,920
