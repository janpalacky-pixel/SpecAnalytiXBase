@echo off
REM ======================================================================
REM  setup_env.bat - creates (or updates) SpecAnalytiXBase's own Python
REM  environment "SpecAnalytiXBase_env" in this folder, and a desktop shortcut
REM  "SpecAnalytiXBase_env Terminal" that opens a command prompt here with the
REM  environment active.
REM
REM  Naming: every project has its own environment called <Project>_env
REM  (here SpecAnalytiXBase_env), kept inside the project
REM  folder and ignored by git.
REM
REM  Another computer (e.g. the laptop): get the project with git, then
REM  double-click this file. The environment cannot be copied between
REM  computers (it contains fixed paths); it is rebuilt here with exactly the
REM  versions listed in requirements-lock.txt.
REM
REM  requirements-lock.txt does not exist yet: it is written here from what
REM  got installed (requirements-dev.txt). Commit it, so that every computer
REM  gets the same versions. To update the libraries on purpose: delete
REM  requirements-lock.txt and the SpecAnalytiXBase_env folder, run this file
REM  again, run the tests, commit the new lock file.
REM
REM  Which Python: set PYTHON to choose one, e.g.
REM      set PYTHON=C:\Python312\python.exe  &  setup_env.bat
REM  otherwise the newest Python 3 found by the "py" launcher, else "python".
REM ======================================================================
setlocal
cd /d "%~dp0"
set "ENV_NAME=SpecAnalytiXBase_env"
set "ENV_DIR=%~dp0%ENV_NAME%"

if defined PYTHON goto :have_python
set "PYTHON=python"
where py >nul 2>nul && set "PYTHON=py -3"
:have_python

echo Python used to build the environment:
%PYTHON% --version
if errorlevel 1 (
    echo.
    echo No Python found. Install Python 3.11 or newer from https://www.python.org/downloads/
    echo ^(tick "Add python.exe to PATH"^), or set PYTHON to the python.exe to use.
    goto :fail
)

if exist "%ENV_DIR%\Scripts\python.exe" (
    echo %ENV_NAME% exists - updating it.
) else (
    echo Creating %ENV_NAME% ...
    %PYTHON% -m venv "%ENV_DIR%" --prompt %ENV_NAME%
    if errorlevel 1 goto :fail
)
set "EPY=%ENV_DIR%\Scripts\python.exe"

"%EPY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

if exist requirements-lock.txt (
    echo Installing the exact versions of requirements-lock.txt ...
    "%EPY%" -m pip install -r requirements-lock.txt
    if errorlevel 1 goto :fail
) else (
    echo Installing requirements-dev.txt ...
    "%EPY%" -m pip install -r requirements-dev.txt
    if errorlevel 1 goto :fail
    "%EPY%" -m pip freeze > requirements-lock.txt
    echo.
    echo Wrote requirements-lock.txt - commit it, so that other computers get the same versions.
)

echo Creating the desktop shortcut "%ENV_NAME% Terminal" ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\%ENV_NAME% Terminal.lnk'); $s.TargetPath='%~dp0%ENV_NAME% Terminal.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0installer_assets\setupicon.ico'; $s.Save()"

echo.
echo Done. Use the desktop shortcut "%ENV_NAME% Terminal" (or "%ENV_NAME% Terminal.bat"
echo in this folder), then:   python main.py      or      python -m pytest -q
pause
exit /b 0

:fail
echo.
echo Setting up %ENV_NAME% did not finish - see the messages above.
pause
exit /b 1
