@echo off
REM PYAV Kernel + Client Launcher
REM Run as Administrator

set SVC=pyav
set DRIVER=%~dp0pyav_kernel.sys
set CLIENT=%~dp0pyav_client.py
set NOTIFIER=%~dp0pyav_notify.exe

echo === PYAV Launcher ===

REM 1. Install and start driver
sc.exe stop %SVC% >nul 2>&1
sc.exe delete %SVC% >nul 2>&1
sc.exe create %SVC% type= kernel binPath= "%DRIVER%" >nul
sc.exe start %SVC% >nul
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Driver failed to start
    pause
    exit /b 1
)
echo [OK] Driver loaded

REM 2. Wait for user login (explorer.exe), then launch notifier
python "%CLIENT%" --auto-launch "%NOTIFIER%"

pause
