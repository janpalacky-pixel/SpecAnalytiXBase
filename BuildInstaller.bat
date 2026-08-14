@echo off

REM Build executable with PyInstaller
pyinstaller --name="SpecAnalytiXBase" --windowed --onedir --add-data "resources;resources" --icon="resources/icons/app_icon.ico" main.py
if errorlevel 1 (
    echo PyInstaller build failed - stopping.
    pause
    exit /b 1
)

REM Create installer with Inno Setup
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
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
