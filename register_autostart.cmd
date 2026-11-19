@echo off
REM PYAV — Register auto-start at user login
REM Run as Administrator

set LAUNCHER=%~dp0pyav_launcher.cmd
set CLIENT=%~dp0pyav_client.py
set NOTIFIER=%~dp0pyav_notify.exe

echo === PYAV Auto-Start Registration ===

REM 1. Schedule driver + client at user login
schtasks /create /tn "PYAV" /tr "\"%LAUNCHER%\"" /sc onlogon /rl highest /f
if %ERRORLEVEL% equ 0 (
    echo [OK] Scheduled task created: PYAV
) else (
    echo [FAIL] Failed to create scheduled task
    pause
    exit /b 1
)

REM 2. Option: also install driver service (runs at boot, no login needed)
echo.
echo Driver already runs via sc start. To make it boot-start:
echo   sc config pyav start= auto
echo.

echo === Done ===
echo PYAV will auto-start at next login.
