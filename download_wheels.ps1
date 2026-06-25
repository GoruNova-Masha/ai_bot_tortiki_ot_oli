# Скачивание пакетов в папку wheels\ (запустите при стабильном интернете / с телефона через раздачу Wi‑Fi)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$wd = Join-Path $PSScriptRoot "wheels"
New-Item -ItemType Directory -Force -Path $wd | Out-Null

$packages = @(
    "python-telegram-bot==21.10",
    "python-dotenv==1.0.1",
    "pydantic-settings==2.7.1",
    "openai==1.58.1"
)

Write-Host "Скачиваю пакеты в $wd ..."
pip download -d $wd @packages --timeout 180 --retries 5 --proxy=
if ($LASTEXITCODE -ne 0) {
    Write-Host "Пробую зеркало Aliyun..."
    pip download -d $wd @packages --timeout 180 --retries 5 --proxy= `
        --index-url https://mirrors.aliyun.com/pypi/simple/ `
        --trusted-host mirrors.aliyun.com
}
if ($LASTEXITCODE -eq 0) {
    Write-Host "Готово. Запустите install_deps.bat"
} else {
    Write-Host "Не вышло. Отключите VPN, попробуйте другую сеть."
}
