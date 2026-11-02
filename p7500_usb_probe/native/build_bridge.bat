@echo off
setlocal
cd /d "%~dp0"
where zig >nul 2>&1
if errorlevel 1 (
    echo Zig 0.13 must be available on PATH. The prebuilt helper is in bin.
    exit /b 1
)
zig cc -target x86-windows-gnu -O2 -s -municode usb_bridge.c -o ..\bin\usb_bridge32.exe -lsetupapi -lcfgmgr32 -ladvapi32 -fno-sanitize=undefined -Werror
if errorlevel 1 exit /b 1
