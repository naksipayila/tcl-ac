@echo off
setlocal
cd /d "%~dp0"
py web_app.py --config config.json
pause
