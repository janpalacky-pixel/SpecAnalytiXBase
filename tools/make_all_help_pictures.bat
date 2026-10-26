@echo off
rem ===========================================================================
rem  Makes every picture of the help again, in one run (double-click it, or run
rem  it from any folder). Takes about 15-20 minutes: windows of the program open
rem  and close by themselves - do not use the mouse or keyboard meanwhile.
rem
rem  Afterwards GitHub Desktop (Changes) shows only the pictures that really
rem  changed; the others come out exactly the same and are not listed.
rem  Logs: tools\logs\pictures_*.txt; problems (a picture not taken, an error):
rem  tools\logs\pictures_problems.txt. See tools\help_pictures\README.md.
rem
rem  Python: the one in %%SAX_PYTHON%% if set, else %%USERPROFILE%%\fresh_env,
rem  else "python" on the PATH.
rem ===========================================================================
cd /d "%~dp0.."
set "PY=python"
if exist "%USERPROFILE%\fresh_env\Scripts\python.exe" set "PY=%USERPROFILE%\fresh_env\Scripts\python.exe"
if defined SAX_PYTHON set "PY=%SAX_PYTHON%"
rem real Windows windows (the Windows look), UTF-8 in the logs
set QT_QPA_PLATFORM=windows
set PYTHONIOENCODING=utf-8
rem one thread for the numerical libraries: the same numbers - and so the same plots - every run
set OMP_NUM_THREADS=1
set OPENBLAS_NUM_THREADS=1
set MKL_NUM_THREADS=1
if not exist tools\logs mkdir tools\logs
if exist tools\logs\pictures_finished.txt del tools\logs\pictures_finished.txt
rem the pictures as they are now, to put back the ones that differ only in a few pixels
if exist tools\logs\pictures_before rmdir /s /q tools\logs\pictures_before
xcopy resources\images\help_screenshots tools\logs\pictures_before\ /e /i /q > nul

echo Help pictures: main window (User Guide)...
"%PY%" tools\help_pictures\make_user_guide_screenshots.py > tools\logs\pictures_user_guide_console.txt 2>&1
echo Help pictures: tool windows...
"%PY%" tools\help_pictures\make_tool_screenshots.py > tools\logs\pictures_tool_windows_console.txt 2>&1
echo Help pictures: Group Statistics and its tutorial...
"%PY%" tools\help_pictures\make_group_statistics_tutorial_figures.py > tools\logs\pictures_group_statistics.txt 2>&1
echo Help pictures: Peak Detection figures...
"%PY%" tools\help_pictures\make_peak_detection_figures.py > tools\logs\pictures_peak_detection.txt 2>&1
echo Help pictures: calculation figures...
"%PY%" tools\help_pictures\make_calculation_figures.py > tools\logs\pictures_calculations.txt 2>&1
echo Help pictures: Unmixing figures...
"%PY%" tools\help_pictures\make_unmixing_figures.py > tools\logs\pictures_unmixing.txt 2>&1
"%PY%" tools\help_pictures\make_unmixing_glenodinium_figures.py > tools\logs\pictures_unmixing_glenodinium.txt 2>&1
"%PY%" tools\help_pictures\make_suggest_explained_figure.py > tools\logs\pictures_suggest_explained.txt 2>&1

echo Help pictures: putting back the ones that differ only in a few pixels...
"%PY%" tools\help_pictures\keep_unchanged.py tools\logs\pictures_before > tools\logs\pictures_kept.txt 2>&1
findstr /c:"NOT TAKEN" /c:"Traceback" /c:"FAILED " /c:"skipped" tools\logs\pictures_*.txt > tools\logs\pictures_problems.txt
echo finished %DATE% %TIME% > tools\logs\pictures_finished.txt
echo.
echo Finished. Changed pictures: GitHub Desktop, Changes. Problems: tools\logs\pictures_problems.txt
