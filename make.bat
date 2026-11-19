@echo off
chcp 65001 >nul
title PYAV Build + Package

set ROOT=%~dp0
set BUILD=%ROOT%out\build\x64-Debug
set DIST=%ROOT%dist

echo ═══════════════════════════════════════
echo  PYAV Build Script
echo ═══════════════════════════════════════

REM ── 0. VS env ────────────────────────────────────────────────────
call "D:\VS26\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64 >nul

REM ── 0.5 Generate integrity data ──────────────────────────────────
echo.
echo [0/5] Generating integrity hashes...
if exist "%ROOT%tools\gen_integrity.py" (
    python "%ROOT%tools\gen_integrity.py" || (echo [WARN] gen_integrity.py had errors & timeout /t 2 >nul)
    echo [OK] integrity data generated
) else (
    echo [SKIP] tools\gen_integrity.py not found
)

REM ── 1. Build kernel driver ────────────────────────────────────────
echo.
echo [1/5] Building pyav_kernel.sys (kernel driver)...
cmake --build "%BUILD%"
if %ERRORLEVEL% neq 0 (
    echo [FAIL] Driver build failed
    pause & exit /b %ERRORLEVEL%
)
echo [OK] pyav_kernel.sys built

REM Sign driver with PFX (密码从环境变量 PFX_PASSWORD 读取，仓库里不存明文密码)
set PFX=%ROOT%_Windows11.pfx
if not defined PFX_PASSWORD (
    echo [SKIP] PFX_PASSWORD not set - driver will stay unsigned
) else (
    if exist "%PFX%" (
        echo [*] Signing pyav_kernel.sys...
        signtool sign /fd SHA256 /a /p %PFX_PASSWORD% /f "%PFX%" "%BUILD%\pyav_kernel.sys" >nul 2>&1 && (echo [OK] Driver signed) || (echo [WARN] Signing failed - skip)
    ) else (
        echo [SKIP] %PFX% not found, driver unsigned
    )
)

REM ── 2. Package pyav_client.exe (PyInstaller) ──────────────────────
echo.
echo [2/5] Packaging pyav_client.exe (IOCTL client)...
python -m PyInstaller --version >nul 2>&1 || pip install pyinstaller >nul

rmdir /s /q "%DIST%\pyav_client" 2>nul
python -m PyInstaller --onefile --noconsole --noupx --noconfirm ^
    --runtime-tmpdir "%%TEMP%%\PyAV\client" ^
    --name pyav_client ^
    --add-data "%BUILD%\pyav_notify.exe;." ^
    --distpath "%DIST%\packages" ^
    "%ROOT%pyav_client.py"
if %ERRORLEVEL% neq 0 ( echo [FAIL] pyav_client.exe failed & pause & exit /b %ERRORLEVEL% )
echo [OK] pyav_client.exe packaged

REM ── 3. Build PYAntivirus.exe (GUI main app) ───────────────────────
echo.
echo [3/5] Building PYAntivirus.exe (main GUI)...
rmdir /s /q "%DIST%\PYAntivirus" 2>nul
python -m PyInstaller --onefile --windowed --noupx --noconfirm ^
    --runtime-tmpdir "%%TEMP%%\PyAV\main" ^
    --name "PYAntivirus" ^
    --icon "%ROOT%resources\antivirus.ico" ^
    --hidden-import customtkinter ^
    --hidden-import pystray ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import PIL.ImageTk ^
    --hidden-import windows_toasts ^
    --hidden-import pefile ^
    --hidden-import psutil ^
    --hidden-import win32api ^
    --hidden-import ctypes ^
    --hidden-import ctypes.wintypes ^
    --hidden-import numpy ^
    --exclude-module sklearn ^
    --exclude-module scipy ^
    --exclude-module pandas ^
    --add-data "%ROOT%resources\antivirus.ico;resources" ^
    --add-data "%ROOT%resources\icon.png;resources" ^
    --add-data "%ROOT%resources\virus_hash_lib.txt;resources" ^
    --add-data "%ROOT%resources\virus_hash_lib.json;resources" ^
    --add-data "%ROOT%resources\integrity.json;resources" ^
    --add-data "%ROOT%resources\NSudo.exe;resources" ^
    --add-data "%ROOT%resources\Minecraft.ttf;resources" ^
    --add-data "%ROOT%resources\yara_rules.json;resources" ^
    "%ROOT%src\PYAntivirus.py"
if %ERRORLEVEL% neq 0 ( echo [FAIL] PYAntivirus.exe failed & pause & exit /b %ERRORLEVEL% )
echo [OK] PYAntivirus.exe packaged

REM ── 3.5 Build ml_trainer.exe (standalone ML trainer, sklearn bundled) ──
echo.
echo [3.5/5] Building ml_trainer.exe (ML trainer, includes sklearn)...
python -m PyInstaller --onefile --console --noupx --noconfirm ^
    --runtime-tmpdir "%%TEMP%%\PyAV\trainer" ^
    --name ml_trainer ^
    --distpath "%DIST%\packages" ^
    "%ROOT%src\train_model.py"
if %ERRORLEVEL% neq 0 ( echo [FAIL] ml_trainer.exe failed & pause & exit /b %ERRORLEVEL% )
echo [OK] ml_trainer.exe packaged

REM ── 4. Build uninstaller ──────────────────────────────────────────
echo.
echo [4/5] Building uninstaller...
rmdir /s /q "%DIST%\uninsPYAV" 2>nul
python -m PyInstaller --onefile --windowed --noupx --noconfirm ^
    --runtime-tmpdir "%%TEMP%%\PyAV\unins" ^
    --name "uninsPYAV" --icon "%ROOT%resources\antivirus.ico" ^
    --hidden-import customtkinter --hidden-import ctypes ^
    "%ROOT%src\uninstaller.py"
if %ERRORLEVEL% neq 0 ( echo [FAIL] uninsPYAV.exe failed & pause & exit /b %ERRORLEVEL% )
echo [OK] uninsPYAV.exe packaged

REM Copy client + notifier + ps1 to dist for installer to bundle
REM (driver .sys is bundled straight from the CMake build dir, see below)
copy "%BUILD%\pyav_notify.exe" "%DIST%\packages\" >nul
copy "%ROOT%install_pyav.ps1"  "%DIST%\packages\" >nul

REM ── 5. Build all-in-one installer ─────────────────────────────────
echo.
echo [5/5] Building PYAntivirus_Installer.exe (bundles everything)...
rmdir /s /q "%DIST%\PYAntivirus_Installer" 2>nul
python -m PyInstaller --onefile --windowed --noupx --noconfirm ^
    --runtime-tmpdir "%%TEMP%%\PyAV\installer" ^
    --name "PYAntivirus_Installer" --icon "%ROOT%resources\antivirus.ico" ^
    --add-data "%DIST%\PYAntivirus.exe;." ^
    --add-data "%DIST%\uninsPYAV.exe;." ^
    --add-data "%DIST%\packages\pyav_client.exe;." ^
    --add-data "%DIST%\packages\pyav_notify.exe;." ^
    --add-data "%DIST%\packages\install_pyav.ps1;." ^
    --add-data "%ROOT%resources\icon.png;resources" ^
    --add-data "%ROOT%resources\virus_hash_lib.txt;resources" ^
    --add-data "%ROOT%resources\integrity.json;resources" ^
    --add-data "%ROOT%resources\Minecraft.ttf;resources" ^
    --add-data "%ROOT%resources\yara_rules.json;resources" ^
    --add-data "%ROOT%out\build\x64-Debug\pyav_kernel.sys;resources" ^
    --hidden-import customtkinter ^
    --hidden-import win32com --hidden-import win32com.client ^
    "%ROOT%src\installer.py"
if %ERRORLEVEL% neq 0 ( echo [FAIL] Installer failed & pause & exit /b %ERRORLEVEL% )

echo.
echo ═══════════════════════════════════════
echo  Build Complete!
echo ═══════════════════════════════════════
echo.
echo Output:
echo   dist\PYAntivirus.exe           (main GUI)
echo   dist\uninsPYAV.exe            (uninstaller)
echo   dist\PYAntivirus_Installer.exe (all-in-one installer)
echo   dist\packages\                 (client + notifier, for debugging)
echo.
dir "%DIST%\PYAntivirus_Installer" 2>nul
pause
