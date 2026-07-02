@echo off
setlocal
cd /d "%~dp0"

set "SSO_TOKEN="
for /f "usebackq tokens=1,* delims==" %%a in (`set TCL_SSO_TOKEN`) do set "SSO_TOKEN=%%b"
if not defined SSO_TOKEN set "SSO_TOKEN="

if exist .env for /f "usebackq tokens=1,* delims==" %%a in (`.env`) do (
    if "%%a"=="TCL_SSO_TOKEN" set "SSO_TOKEN=%%b"
)

if defined SSO_TOKEN set "TCL_SSO_TOKEN=%SSO_TOKEN%"

start "" /B pyw.exe "%~dp0web_app.py" --config "%~dp0config.json" --no-browser
