@echo off
rem Run with a console window and the debug view open. Extra flags pass through, e.g.  run.bat --dry-run
cd /d "%~dp0"
".venv\Scripts\python.exe" -m gesture_control --preview %*
