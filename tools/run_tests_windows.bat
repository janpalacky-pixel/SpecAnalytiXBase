@echo off
rem ===========================================================================
rem  Runs all tests on this Windows computer, with the same libraries as the
rem  GitHub build (double-click it, or run it from any folder). About 7-12
rem  minutes. Result: tools\logs\tests_windows.txt - first the check of the
rem  libraries ("Libraries OK" or "WARNING - LIBRARIES DIFFER"), last line
rem  passed / failed; tools\logs\tests_finished.txt is written at the end.
rem  Python: %%SAX_PYTHON%% if set, else %%USERPROFILE%%\fresh_env, else "python".
rem ===========================================================================
cd /d "%~dp0.."
set "PY=python"
if exist "%USERPROFILE%\fresh_env\Scripts\python.exe" set "PY=%USERPROFILE%\fresh_env\Scripts\python.exe"
if defined SAX_PYTHON set "PY=%SAX_PYTHON%"
if not exist tools\logs mkdir tools\logs
if exist tools\logs\tests_finished.txt del tools\logs\tests_finished.txt
rem the same library versions as the GitHub build? (shown here and at the top of the log)
"%PY%" tools\check_libraries.py > tools\logs\tests_windows.txt 2>&1
type tools\logs\tests_windows.txt
echo Running all tests (about 7 minutes)...
"%PY%" -m pytest tests/ -q -p no:cacheprovider >> tools\logs\tests_windows.txt 2>&1
echo finished %DATE% %TIME% > tools\logs\tests_finished.txt
