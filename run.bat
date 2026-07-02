@echo off
REM Start the web server on Windows. Reads .env for configuration.
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist .venv (
  echo error: .venv missing. Run deploy.bat first.
  exit /b 1
)

if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%~A"=="" set "%%A=%%B"
  )
)

".venv\Scripts\python.exe" -m web
