@echo off
rem ===========================================================================
rem  Makes only the help pictures of the main window again (User Guide: the
rem  window, the plot types, the panels, a window beside the plot) - about
rem  2 minutes instead of the whole make_all_help_pictures.bat. For a change
rem  of the main window only. Do not use the mouse or keyboard meanwhile.
rem  Logs: tools\logs\pictures_user_guide*.txt, pictures_main_window.txt.
rem ===========================================================================
cd /d "%~dp0.."
set "PY=python"
if exist "%USERPROFILE%\fresh_env\Scripts\python.exe" set "PY=%USERPROFILE%\fresh_env\Scripts\python.exe"
if defined SAX_PYTHON set "PY=%SAX_PYTHON%"
set QT_QPA_PLATFORM=windows
set PYTHONIOENCODING=utf-8
set OMP_NUM_THREADS=1
set OPENBLAS_NUM_THREADS=1
set MKL_NUM_THREADS=1
if not exist tools\logs mkdir tools\logs
if exist tools\logs\pictures_finished.txt del tools\logs\pictures_finished.txt
if exist tools\logs\pictures_before rmdir /s /q tools\logs\pictures_before
xcopy resources\images\help_screenshots tools\logs\pictures_before\ /e /i /q > nul
echo Help pictures: main window (User Guide)...
"%PY%" tools\help_pictures\make_user_guide_screenshots.py > tools\logs\pictures_user_guide_console.txt 2>&1
echo Help pictures: a window beside the plot (Peaks window)...
"%PY%" tools\help_pictures\make_tool_screenshots.py peak_detection > tools\logs\pictures_main_window.txt 2>&1
"%PY%" tools\help_pictures\keep_unchanged.py tools\logs\pictures_before > tools\logs\pictures_kept.txt 2>&1
findstr /c:"NOT TAKEN" /c:"Traceback" /c:"FAILED " /c:"skipped" tools\logs\pictures_user_guide*.txt tools\logs\pictures_main_window.txt > tools\logs\pictures_problems.txt
echo finished %DATE% %TIME% > tools\logs\pictures_finished.txt
echo.
echo Finished. Changed pictures: GitHub Desktop, Changes. Problems: tools\logs\pictures_problems.txt
