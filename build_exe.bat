@echo off
REM Build FocusLock.exe. Needs Python + PyInstaller (pip install pyinstaller).
pyinstaller --onefile --noconsole --name FocusLock focuslock.py
echo.
echo Done. Your app is in the "dist" folder: dist\FocusLock.exe
pause
