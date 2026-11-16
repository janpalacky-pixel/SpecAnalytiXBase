@echo off
REM "SpecAnalytiXBase_env Terminal": a command prompt in this folder with
REM SpecAnalytiXBase's own environment active (made by setup_env.bat), e.g. for
REM     python main.py
REM     python -m pytest -q
REM     BuildInstaller.bat
cd /d "%~dp0"
if not exist "%~dp0SpecAnalytiXBase_env\Scripts\activate.bat" (
    echo SpecAnalytiXBase_env does not exist yet - run setup_env.bat first.
    pause
    exit /b 1
)
title SpecAnalytiXBase_env Terminal
cmd /k call "%~dp0SpecAnalytiXBase_env\Scripts\activate.bat"
