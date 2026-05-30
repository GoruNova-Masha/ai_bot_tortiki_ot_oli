@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
where python >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else (
        echo Python не найден. Установите с https://www.python.org/downloads/
        echo При установке отметьте "Add python.exe to PATH".
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    "%PY%" -m venv .venv
)

call .venv\Scripts\activate.bat

set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set PIP_NO_CACHE_DIR=1

echo Установка библиотек (до 3 мин, нужен интернет)...
call "%~dp0install_deps.bat" --quiet
if errorlevel 1 (
    echo.
    echo Установка не удалась. Запустите отдельно: install_deps.bat
    pause
    exit /b 1
)

echo.
echo Запуск бота «Тортики от Оли»...
echo Остановка: Ctrl+C
echo.
python main.py
pause
