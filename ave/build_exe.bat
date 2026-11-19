@echo off
REM Build Ave.exe locally. Needs Python + PyInstaller (pip install "pyinstaller>=6.10").
cd /d "%~dp0"
python ave.py --make-icon ave.ico
pyinstaller --onefile --noconsole --name Ave --icon ave.ico ave.py
echo.
echo Done: dist\Ave.exe
pause
