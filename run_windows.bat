@echo off
REM -------------------------------------------------------------------
REM ClearSight - Windows Launcher
REM Starts local server and opens in native Edge WebView2 / App mode.
REM -------------------------------------------------------------------

cd /d %~dp0

echo [*] Starting ClearSight Analytical Core on Windows...
start /b python server.py

timeout /t 2 /nobreak >nul

REM Discover dynamically assigned port from .clearsight_port
set CS_PORT=
if exist "%~dp0.clearsight_port" set /p CS_PORT=<"%~dp0.clearsight_port"
if "%CS_PORT%"=="" set CS_PORT=8540

REM Launch using Microsoft Edge in clean app mode (native WebView2 feel)
start msedge --app=http://127.0.0.1:%CS_PORT% --window-size=1440,920
echo ClearSight is running on port %CS_PORT%. Close this window to shut down the server.
pause >nul

REM Gracefully terminate the process on the designated port
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%CS_PORT% " ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
if exist "%~dp0.clearsight_pid" (
    set /p CS_PID=<"%~dp0.clearsight_pid"
    if not "%CS_PID%"=="" taskkill /PID %CS_PID% /F >nul 2>&1
)

