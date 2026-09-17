@echo off
setlocal

rem %~dp0 is this .bat file's own folder, so this works regardless of
rem where the repo is cloned to -- no hardcoded path to edit.
cd /d "%~dp0"

if not exist logs mkdir logs

echo ==== %date% %time% ==== >> logs\daily_run.log
python -m pacing_tracker.data_pull --out data\pull_today.json >> logs\daily_run.log 2>&1
python -m pacing_tracker.excel_report --in data\pull_today.json >> logs\daily_run.log 2>&1
echo ==== done ==== >> logs\daily_run.log
