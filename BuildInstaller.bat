@echo off

REM Build executable with PyInstaller
REM (build_hooks adds the program's own tests, so that Help - Run tests works in the installed version)
pyinstaller --name="SpecAnalytiXBase" --windowed --onedir --add-data "resources;resources" --additional-hooks-dir=build_hooks --icon="resources/icons/app_icon.ico" main.py
if errorlevel 1 (
    echo PyInstaller build failed - stopping.
    pause
    exit /b 1
)

REM Create installer with Inno Setup
REM Inno Setup: version 7 or 6, in Program Files or Program Files (x86), else ISCC.exe on PATH
set "ISCC="
if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC for %%I in (ISCC.exe) do if not "%%~$PATH:I"=="" set "ISCC=%%~$PATH:I"
if not defined ISCC (
    echo Inno Setup was not found. Install it from https://jrsoftware.org/isdl.php
    echo in its default folder, then run this file again.
    pause
    exit /b 1
)
echo Inno Setup: %ISCC%
"%ISCC%" installer.iss
if errorlevel 1 (
    echo Inno Setup build failed - stopping. build\ and dist\ left in place for debugging.
    pause
    exit /b 1
)

REM Installer built successfully - clean up intermediate output.
REM Both folders are regenerated from scratch on every run, so nothing is lost.
rd /s /q build
rd /s /q dist

echo Build and packaging process completed. Installer is in installer\
pause
