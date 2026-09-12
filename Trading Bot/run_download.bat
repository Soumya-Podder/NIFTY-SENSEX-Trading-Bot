@echo off
echo =======================================================
echo   Dhan 5-Year Historical Data Downloader (NIFTY/SENSEX)
echo   Storage: Strictly inside E:\trading_bot_full\Trading Bot\data
echo =======================================================
cd /d "%~dp0backend"
if not exist .venv (
    echo Error: .venv not found.
    pause
    exit /b 1
)
call .venv\Scripts\activate
python -m app.backtest.download %*
pause
