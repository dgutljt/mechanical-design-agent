@echo off
setlocal
pushd "%~dp0" || exit /b 1
set "DSH_BIN=packages\dsh-mechanical-plugin\node_modules\@deepseek-ai\dsh\lib\bin.js"
if not exist "%DSH_BIN%" goto :fail
if not exist ".dsh\mechanical-overhung.patch.yml" goto :fail
where node.exe >nul 2>&1 || goto :fail

rem Explicit standalone opt-in. A separate home keeps the running old DSH untouched.
set "DSH_HOME=%TEMP%\mechanical-overhung-%RANDOM%-%RANDOM%"
if exist "%DSH_HOME%" goto :fail
mkdir "%DSH_HOME%" || goto :fail
set "DSH_TELEMETRY_MODE=DISABLED"
node packages\dsh-mechanical-plugin\scripts\build.mjs
if errorlevel 1 goto :fail
echo Explicit restricted 12 Tool profile; task input follows the config checks.
echo The DSH home is isolated. No HTTP server or listening port is used.
node scripts\verify_p1c_runtime.mjs --launch
set "DSH_EXIT=%ERRORLEVEL%"
popd
exit /b %DSH_EXIT%
:fail
echo ERROR: Cannot safely start the explicit overhung profile. No fallback was started.
popd
exit /b 1
