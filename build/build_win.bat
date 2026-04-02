@echo off
REM build_win.bat — Build MouseShare.exe for Windows 10+
REM Run from the project root: build\build_win.bat

cd /d "%~dp0\.."

echo =^> Installing dependencies (Windows)
pip install -r requirements-win.txt

echo =^> Running PyInstaller
pyinstaller ^
  --name "MouseShare" ^
  --windowed ^
  --icon "assets\icon.ico" ^
  --add-data "assets;assets" ^
  --hidden-import "pynput.keyboard._win32" ^
  --hidden-import "pynput.mouse._win32" ^
  --hidden-import "pystray._win32" ^
  --hidden-import "PIL._tkinter_finder" ^
  --hidden-import "win32api" ^
  --hidden-import "win32con" ^
  --hidden-import "win32clipboard" ^
  "mouseshare\main.py"

echo.
echo =^> Build complete: dist\MouseShare.exe
echo    Run as normal user — no administrator rights required.
echo    Windows Firewall will prompt on first run; click "Allow".
