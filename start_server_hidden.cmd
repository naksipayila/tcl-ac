@echo off
setlocal
cd /d "%~dp0"
start "" /B pyw.exe "%~dp0web_app.py" --config "%~dp0config.json" --no-browser
