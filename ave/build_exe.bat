@echo off
REM Build Ave.exe locally. Needs Python + PyInstaller (pip install "pyinstaller>=6.10").
cd /d "%~dp0"
pyinstaller --onefile --noconsole --name Ave ave.py
echo.
echo Done: dist\Ave.exe
pause
