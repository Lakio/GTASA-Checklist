@echo off
rem Construit dist\GTASA_Checklist.exe (un seul fichier, sans Python requis)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv || goto :error
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || goto :error
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name GTASA_Checklist ^
    --icon assets\icon.ico ^
    --add-data "assets\icon.ico;assets" ^
    --exclude-module tkinter ^
    --exclude-module unittest ^
    --exclude-module PySide6.QtNetwork ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtOpenGL ^
    --exclude-module PySide6.QtSvg ^
    --exclude-module PySide6.QtPdf ^
    main.py || goto :error
echo.
echo OK : dist\GTASA_Checklist.exe
exit /b 0

:error
echo Echec de la construction.
pause
exit /b 1
