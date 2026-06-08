@echo off
REM =============================================================================
REM Основная папка проекта (все последние изменения):
REM   C:\Users\mweig\OneDrive\project vs code\ИИ-бот_ТортикиОтОли
REM Запуск бота только отсюда: run.bat
REM Вторая копия (неполная, не использовать): C:\Projects\ИИ-бот_ТортикиОтОли
REM =============================================================================
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
echo Проверка: останавливаем ранее запущенные экземпляры бота...
for /f "tokens=*" %%p in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name=''python.exe''\" ^| Where-Object { $_.CommandLine -match 'main\.py' } ^| ForEach-Object { $_.ProcessId }"') do (
    echo Останавливаю PID %%p
    taskkill /F /PID %%p >nul 2>&1
)
timeout /t 2 /nobreak >nul
for /f "tokens=*" %%p in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name=''python.exe''\" ^| Where-Object { $_.CommandLine -match 'main\.py' } ^| ForEach-Object { $_.ProcessId }"') do (
    echo Повторно останавливаю PID %%p
    taskkill /F /PID %%p >nul 2>&1
)

echo Проверка зависимостей...
python -c "from openai import AsyncOpenAI" 2>nul
if errorlevel 1 (
    echo Восстанавливаю пакет openai...
    python -m pip install --force-reinstall "openai==1.58.1" -q
)

echo.
echo Запуск бота «Тортики от Оли»...
echo Остановка: Ctrl+C
echo.
python main.py
pause
