@echo off
setlocal
pushd "%~dp0" || goto :directory_error

where node.exe >nul 2>&1 || goto :node_error
where npm.cmd >nul 2>&1 || goto :npm_error
set "DSH_BIN=packages\dsh-mechanical-plugin\node_modules\@deepseek-ai\dsh\lib\bin.js"
if not exist "%DSH_BIN%" goto :install_error
if not exist ".dsh\mechanical-engineering.patch.yml" goto :patch_error
if not exist ".dsh\mechanical-web.patch.yml" goto :patch_error

call npm.cmd run build --prefix packages/dsh-mechanical-plugin
if errorlevel 1 goto :build_error

for /f "delims=" %%V in ('node "%DSH_BIN%" -V 2^>nul') do set "DSH_VERSION=%%V"
if not "%DSH_VERSION%"=="0.2.0-rc.2" goto :version_error

echo Starting restricted Mechanical Engineering DSH Web UI...
echo The browser will open automatically. Keep this window open while using the agent.
node "%DSH_BIN%" --profile web --patch .dsh\mechanical-engineering.patch.yml --patch .dsh\mechanical-web.patch.yml --host 127.0.0.1 --port 0
if errorlevel 1 goto :runtime_error
popd
exit /b 0

:directory_error
echo ERROR: Cannot enter the Mechanical Design Agent repository directory.
goto :fail
:node_error
echo ERROR: Node.js 24 or later is required and node.exe was not found on PATH.
goto :fail
:npm_error
echo ERROR: npm.cmd was not found on PATH.
goto :fail
:install_error
echo ERROR: Local DSH dependencies are missing. Run npm install --prefix packages/dsh-mechanical-plugin first.
goto :fail
:patch_error
echo ERROR: The restricted Mechanical Engineering profile patch is missing.
goto :fail
:build_error
echo ERROR: The local mechanical plugin failed to build. Review the npm error above.
goto :fail
:version_error
echo ERROR: Expected DSH 0.2.0-rc.2; found "%DSH_VERSION%".
goto :fail
:runtime_error
echo ERROR: DSH Web UI failed to start. Review the runtime error above; check local port, profile, and plugin loading.
:fail
echo.
pause
popd
exit /b 1
