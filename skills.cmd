@echo off
setlocal
set "NPM_CONFIG_CACHE=%~dp0.npm-cache"
set "TEMP=%~dp0.tmp-tests"
set "TMP=%TEMP%"
set "XDG_STATE_HOME=%~dp0.cache\skills-state"
set "DISABLE_TELEMETRY=1"
if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%~dp0.tools\npm-global\skills.cmd" (
  echo Install the CLI first: npm install -g skills --prefix "%~dp0.tools\npm-global" --cache "%NPM_CONFIG_CACHE%"
  exit /b 1
)
call "%~dp0.tools\npm-global\skills.cmd" %*
exit /b %ERRORLEVEL%
