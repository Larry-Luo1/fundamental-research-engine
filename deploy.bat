@echo off
REM One-click setup for Windows. After `git clone`, run: deploy.bat
REM Then edit .env (password + API key) and run run.bat
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

echo ==^> creating virtualenv (.venv)
%PY% -m venv .venv || goto :err

echo ==^> installing engine + web extra
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip || goto :err
".venv\Scripts\python.exe" -m pip install --quiet -e ".[web]" || goto :err

if not exist .env (
  copy /y .env.example .env >nul
  echo ==^> created .env from template
)

echo.
echo Setup complete.
echo NEXT: edit .env (set FRE_WEB_PASSWORD and ANTHROPIC_API_KEY), then run run.bat
goto :eof

:err
echo.
echo Setup failed. Ensure Python 3.10+ is installed and on PATH.
exit /b 1
