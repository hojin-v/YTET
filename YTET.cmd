@echo off
setlocal EnableExtensions
set "PROJECT=%~dp0"
set "PYTHONW=%PROJECT%.venv-win\Scripts\pythonw.exe"
set "DENO=%PROJECT%runtimes\deno.exe"

if /I "%~1"=="--update" goto update
if /I "%~1"=="update" goto update
if /I "%~1"=="/update" goto update

if not exist "%PYTHONW%" (
  goto setup
)

if not exist "%DENO%" (
  goto setup
)

goto run

:update
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT%SETUP.ps1" -Update
  pause
  exit /b %ERRORLEVEL%

:setup
  echo Setup is required.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT%SETUP.ps1"
  if errorlevel 1 (
    echo.
    echo Setup failed. Check setup.log next to this file.
    pause
    exit /b 1
  )

:run
start "" /D "%PROJECT%" "%PYTHONW%" "%PROJECT%run_app.py"
