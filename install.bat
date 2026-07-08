@echo off
REM One-command install for Windows: double-click install.bat
cd /d "%~dp0"
echo == Companion installer ==

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 is required. Install it from https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" in the installer, then re-run this file.
  pause
  exit /b 1
)

echo -^> creating virtual environment
python -m venv .venv
call .venv\Scripts\pip install --quiet --upgrade pip
echo -^> installing dependencies
call .venv\Scripts\pip install --quiet -r requirements.txt

where ollama >nul 2>nul
if errorlevel 1 (
  echo.
  echo !! Ollama is not installed - the app needs it to think.
  echo    Install it from https://ollama.com/download then run: ollama pull llama3.1:8b
) else (
  echo -^> Ollama found; pulling default chat model if missing ^(one time, ~5GB^)
  ollama pull llama3.1:8b
)

echo.
echo Done. Start her with start.bat ^(or: .venv\Scripts\python run.py^)
echo then open http://localhost:8320
pause
