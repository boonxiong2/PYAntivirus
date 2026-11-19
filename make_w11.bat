@echo off
chcp 65001 >nul
echo === 编译 _Win11LPC ===
"C:\Program Files\LLVM\bin\clang++.exe" -std=c++17 -O2 w11lpc.cpp -o w11lpc.exe
if %errorlevel% equ 0 (
    echo [OK] 编译成功!
    echo.
    echo === 运行 hello.w11 ===
    w11lpc.exe hello.w11
) else (
    echo [FAIL] 编译失败
)
pause
