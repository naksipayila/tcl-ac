@echo off
setlocal
cd /d "%~dp0"

py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

py build_assets.py
if errorlevel 1 (
  echo Icon build failed.
  pause
  exit /b 1
)

py -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --name "TCL-Klima-Panel" ^
  --noconsole ^
  --icon "assets\fan.ico" ^
  --add-data "assets\fan.png;assets" ^
  --hidden-import "pystray._win32" ^
  tray_app.py
if errorlevel 1 (
  echo EXE build failed.
  pause
  exit /b 1
)

if not exist "dist\TCL-Klima-Panel\assets" mkdir "dist\TCL-Klima-Panel\assets"
copy /Y "config.json" "dist\TCL-Klima-Panel\config.json" >nul
copy /Y "assets\fan.png" "dist\TCL-Klima-Panel\assets\fan.png" >nul

echo.
echo Built: dist\TCL-Klima-Panel\TCL-Klima-Panel.exe
echo Keep config.json next to the EXE so settings can be edited later.
pause
