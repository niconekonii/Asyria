@echo off
REM Build Ave.exe locally. Needs Python + PyInstaller (pip install pyinstaller).
cd /d "%~dp0"
pyinstaller --onefile --noconsole --name Ave ave.py
echo.
echo Done: dist\Ave.exe
pause
