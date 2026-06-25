@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "QUIET=0"
if /i "%~1"=="--quiet" set "QUIET=1"

if not exist ".venv\Scripts\python.exe" (
    echo Сначала запустите run.bat — нужно виртуальное окружение .venv
    if "%QUIET%"=="0" pause
    exit /b 1
)

call .venv\Scripts\activate.bat

set HTTP_PROXY=
set HTTPS_PROXY=
set ALL_PROXY=
set PIP_NO_CACHE_DIR=1

if exist "wheels\*.whl" (
    echo Установка из локальной папки wheels\ ...
    python -m pip install --no-index --find-links=wheels -r requirements.txt
    if not errorlevel 1 goto ok
    echo Локальные файлы не подошли, пробую скачать из интернета...
)

echo Обновляю pip...
python -m pip install --upgrade pip --timeout 180 --retries 5 --proxy=

echo.
echo Зеркало 1: pypi.org (таймаут 180 сек)...
python -m pip install -r requirements.txt --timeout 180 --retries 5 --proxy= ^
    --index-url https://pypi.org/simple --trusted-host pypi.org --trusted-host files.pythonhosted.org
if not errorlevel 1 goto ok

echo.
echo Зеркало 2: Aliyun...
python -m pip install -r requirements.txt --timeout 180 --retries 5 --proxy= ^
    --index-url https://mirrors.aliyun.com/pypi/simple/ ^
    --trusted-host mirrors.aliyun.com --trusted-host files.pythonhosted.org
if not errorlevel 1 goto ok

echo.
echo Зеркало 3: Tsinghua...
python -m pip install -r requirements.txt --timeout 180 --retries 5 --proxy= ^
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple ^
    --trusted-host pypi.tuna.tsinghua.edu.cn --trusted-host files.pythonhosted.org
if not errorlevel 1 goto ok

echo.
echo Не удалось установить пакеты.
echo  1. Отключите VPN / антивирус с фильтрацией HTTPS
echo  2. Попробуйте интернет с телефона (раздача Wi-Fi)
echo  3. В PowerShell: .\download_wheels.ps1  затем снова install_deps.bat
if "%QUIET%"=="0" pause
exit /b 1

:ok
echo.
echo Библиотеки установлены.
python check_setup.py
if errorlevel 1 (
    if "%QUIET%"=="0" pause
    exit /b 1
)
if "%QUIET%"=="0" pause
exit /b 0
