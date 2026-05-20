@echo off
setlocal EnableExtensions
set "PROJECT=%~dp0"
set "PYTHONW=%PROJECT%.venv-win\Scripts\pythonw.exe"

if not exist "%PYTHONW%" (
  echo First run setup is required.
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT%SETUP.ps1"
  if errorlevel 1 (
    echo.
    echo Setup failed. Check setup.log next to this file.
    pause
    exit /b 1
  )
)

start "" /D "%PROJECT%" "%PYTHONW%" "%PROJECT%run_app.py"
