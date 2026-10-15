@echo off
rem Use the app normally while it records hand-point numbers (no images) and what it did.
rem Stop with tray icon -> Quit, or close this window. Saved to recordings\sessions\.
cd /d "%~dp0"
echo Recording a session. Use gestures normally. Quit from the tray icon (or close this window) to stop.
".venv\Scripts\python.exe" -m gesture_control --record %*
