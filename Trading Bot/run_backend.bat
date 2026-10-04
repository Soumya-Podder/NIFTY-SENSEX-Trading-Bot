@echo off
setlocal
set "TEMP=%~dp0..\.tmp"
set "TMP=%TEMP%"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%TEMP%" mkdir "%TEMP%"
pushd "%~dp0backend"
.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8080
popd
endlocal
