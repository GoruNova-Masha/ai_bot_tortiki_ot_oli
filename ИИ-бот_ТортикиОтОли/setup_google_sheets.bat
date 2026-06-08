@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

if not exist ".venv\Scripts\python.exe" (
    echo Сначала установите зависимости: install_deps.bat
    pause
    exit /b 1
)

echo.
echo === Настройка Google Таблицы для заявок бота ===
echo.

.venv\Scripts\pip install gspread google-auth -q
.venv\Scripts\python.exe setup_google_sheets.py
echo.
pause
