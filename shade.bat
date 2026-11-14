@echo off
rem Start Shade in the background: tray icon, no console window.
rem Dependencies are brought up to date first (uv sync: about a second when nothing changed).
rem The caller does not wait; quit Shade from the tray menu.
setlocal
cd /d "%~dp0"

rem Find uv: PATH, the official installer folder, or a pip --user install.
set "UV="
for /f "delims=" %%U in ('where uv 2^>nul') do if not defined UV set "UV=%%U"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV for /d %%D in ("%APPDATA%\Python\Python3*" "%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~D\Scripts\uv.exe" set "UV=%%~D\Scripts\uv.exe"

if defined UV (
    "%UV%" sync --quiet
    if errorlevel 1 (
        echo uv sync failed. If Shade is already running, quit it from the tray and try again.
        pause
        exit /b 1
    )
) else if not exist ".venv\Scripts\pythonw.exe" (
    echo uv was not found. Install it from https://docs.astral.sh/uv/ and run this again.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m shade
