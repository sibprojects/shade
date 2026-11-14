@echo off
rem Start Shade in the background: tray icon, no console window.
rem The caller does not wait; quit Shade from the tray menu.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Shade is not installed here yet: run "uv sync" in this folder first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m shade
