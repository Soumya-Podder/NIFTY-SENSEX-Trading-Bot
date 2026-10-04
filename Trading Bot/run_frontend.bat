@echo off
setlocal
set "TEMP=%~dp0..\.tmp"
set "TMP=%TEMP%"
set "npm_config_cache=%~dp0..\.npm-cache"
if not exist "%TEMP%" mkdir "%TEMP%"
pushd "%~dp0frontend"
if not exist "node_modules\vite\bin\vite.js" call npm ci
call npm run dev
popd
endlocal
