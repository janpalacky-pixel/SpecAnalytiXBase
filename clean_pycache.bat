@echo off
REM Removes all __pycache__ and .pytest_cache folders under this directory.
REM Safe to run any time - Python regenerates __pycache__ automatically as needed.

for /d /r %%d in (__pycache__) do (
    if exist "%%d" rd /s /q "%%d"
)
for /d /r %%d in (.pytest_cache) do (
    if exist "%%d" rd /s /q "%%d"
)

echo Done.
pause
