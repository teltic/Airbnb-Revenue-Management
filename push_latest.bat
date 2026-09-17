@echo off
setlocal

rem %~dp0 is this .bat file's own folder, so this works regardless of
rem where the repo is cloned to -- no hardcoded path to edit.
cd /d "%~dp0"

echo Finding the most recent Daily Pacing Pickup file and showing what would be pushed...
echo (Nothing gets sent to PriceLabs yet -- this is a preview.)
echo.
python -m pacing_tracker.push
if errorlevel 1 (
    echo.
    echo Something went wrong above -- see the message for details.
    pause
    exit /b 1
)

echo.
set /p CONFIRM="Push these changes for real to PriceLabs? Type YES to confirm, anything else to cancel: "
if /I not "%CONFIRM%"=="YES" (
    echo Cancelled -- nothing was sent.
    pause
    exit /b 0
)

echo.
echo === PUSHING FOR REAL ===
python -m pacing_tracker.push --confirm

echo.
pause
