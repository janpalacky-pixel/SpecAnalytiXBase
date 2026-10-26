@echo off
rem ===========================================================================
rem  Runs all tests on this Windows computer, with the same libraries as the
rem  GitHub build (double-click it, or run it from any folder). About 7-12
rem  minutes. Result: tools\logs\tests_windows.txt (last line: passed / failed);
rem  tools\logs\tests_finished.txt is written at the end.
rem  Python: %%SAX_PYTHON%% if set, else %%USERPROFILE%%\fresh_env, else "python".
rem ===========================================================================
cd /d "%~dp0.."
set "PY=python"
if exist "%USERPROFILE%\fresh_env\Scripts\python.exe" set "PY=%USERPROFILE%\fresh_env\Scripts\python.exe"
if defined SAX_PYTHON set "PY=%SAX_PYTHON%"
if not exist tools\logs mkdir tools\logs
if exist tools\logs\tests_finished.txt del tools\logs\tests_finished.txt
"%PY%" -m pytest tests/ -q -p no:cacheprovider > tools\logs\tests_windows.txt 2>&1
echo finished %DATE% %TIME% > tools\logs\tests_finished.txt
