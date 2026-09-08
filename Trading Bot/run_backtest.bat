@echo off
if "%~1"=="" (
  echo Usage: run_backtest.bat path\to\real_options_dataset.csv
  exit /b 1
)
cd backend
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
python -m app.backtest.cli --csv "%~1"
pause
