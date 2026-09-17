@echo off
setlocal

rem Registers/updates the Windows Task Scheduler entry for the daily
rem pull + Excel generation, using schtasks instead of the Task Scheduler
rem GUI wizard. Safe to re-run any time -- e.g. after moving or renaming
rem this folder -- since it overwrites the existing task rather than
rem erroring on a duplicate name.

set TASK_NAME=Daily Pacing Pickup Tracker
set RUN_TIME=06:00

rem %~dp0 is this .bat file's own folder, so the registered task always
rem points at wherever this repo actually lives.
set SCRIPT_PATH=%~dp0run_daily.bat

schtasks /create /tn "%TASK_NAME%" /tr "\"%SCRIPT_PATH%\"" /sc daily /st %RUN_TIME% /f

if errorlevel 1 (
    echo.
    echo Something went wrong registering the task -- see the message above.
    pause
    exit /b 1
)

echo.
echo Registered "%TASK_NAME%" to run daily at %RUN_TIME%, pointing at:
echo   %SCRIPT_PATH%
echo.
echo To change the time, edit RUN_TIME at the top of this file and re-run it.
echo.
echo One thing this script can't set: open the task in Task Scheduler once,
echo Properties -^> Settings tab, and check "Run task as soon as possible
echo after a scheduled start is missed" -- so a sleeping/off PC at 6am
echo still catches up instead of skipping that day.
pause
