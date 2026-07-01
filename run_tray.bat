@echo off
setlocal
cd /d "%~dp0"
py tray_app.py --config config.json
