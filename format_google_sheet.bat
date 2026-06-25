@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe format_google_sheet.py
pause
