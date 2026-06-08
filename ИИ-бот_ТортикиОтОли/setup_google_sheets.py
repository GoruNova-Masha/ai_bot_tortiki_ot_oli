"""Первичная настройка Google Таблицы для заявок из Telegram-бота."""

from __future__ import annotations

import json
import re
import sys
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CREDS_DIR = PROJECT_ROOT / "credentials"
DEFAULT_CREDS = CREDS_DIR / "google-service-account.json"
ENV_PATH = PROJECT_ROOT / ".env"

CONSOLE_LINKS = (
    ("Создать проект Google Cloud", "https://console.cloud.google.com/projectcreate"),
    ("Включить Google Sheets API", "https://console.cloud.google.com/apis/library/sheets.googleapis.com"),
    ("Включить Google Drive API", "https://console.cloud.google.com/apis/library/drive.googleapis.com"),
    (
        "Сервисные аккаунты - создать ключ JSON",
        "https://console.cloud.google.com/iam-admin/serviceaccounts",
    ),
)


def _find_credentials_path() -> Path | None:
    if DEFAULT_CREDS.exists():
        return DEFAULT_CREDS
    for path in sorted(CREDS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("type") == "service_account" and data.get("client_email"):
            return path
    return None


def _update_env_value(key: str, value: str) -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text(f"{key}={value}\n", encoding="utf-8")
        return

    text = ENV_PATH.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += f"\n# --- Google Таблица ---\n{line}\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def _print_missing_credentials() -> None:
    print()
    print("=" * 60)
    print("  Нужен JSON-ключ сервисного аккаунта Google")
    print("=" * 60)
    print()
    print(f"1. Скачайте ключ и сохраните как:\n   {DEFAULT_CREDS}")
    print("2. Запустите этот скрипт снова: setup_google_sheets.bat")
    print()
    print("Кратко в Google Cloud Console:")
    print("  - Создайте проект")
    print("  - Включите Google Sheets API и Google Drive API")
    print("  • IAM -> Service Accounts -> Create -> Keys -> Add key -> JSON")
    print()
    for title, url in CONSOLE_LINKS:
        print(f"  -> {title}")
        print(f"    {url}")
    print()
    open_links = input("Открыть эти страницы в браузере? [Y/n]: ").strip().lower()
    if open_links in ("", "y", "yes", "д", "да"):
        for _title, url in CONSOLE_LINKS:
            webbrowser.open(url)


def main() -> int:
    creds_path = _find_credentials_path()
    if creds_path is None:
        CREDS_DIR.mkdir(parents=True, exist_ok=True)
        _print_missing_credentials()
        return 1

    if creds_path != DEFAULT_CREDS:
        DEFAULT_CREDS.write_bytes(creds_path.read_bytes())
        creds_path = DEFAULT_CREDS
        print(f"Ключ скопирован в {DEFAULT_CREDS}")

    creds_data = json.loads(creds_path.read_text(encoding="utf-8"))
    client_email = creds_data.get("client_email", "")
    print(f"Сервисный аккаунт: {client_email}")

    from google.oauth2.service_account import Credentials
    import gspread

    from bot.google_sheets import SCOPES, SHEET_HEADERS
    from config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    credentials = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    client = gspread.authorize(credentials)

    spreadsheet = None
    spreadsheet_id = settings.google_sheets_spreadsheet_id.strip()
    spreadsheet_name = settings.google_sheets_spreadsheet_name.strip() or "Заявки_ТортикиОтОли"

    if spreadsheet_id:
        try:
            spreadsheet = client.open_by_key(spreadsheet_id)
            print(f"Открыта таблица по ID: {spreadsheet_id}")
        except gspread.SpreadsheetNotFound:
            print(f"Таблица с ID {spreadsheet_id} не найдена — создаём новую.")

    if spreadsheet is None:
        try:
            spreadsheet = client.open(spreadsheet_name)
            print(f"Открыта таблица по имени: {spreadsheet_name}")
        except gspread.SpreadsheetNotFound:
            spreadsheet = client.create(spreadsheet_name)
            print(f"Создана новая таблица: {spreadsheet_name}")

    worksheet_name = settings.google_sheets_worksheet_name.strip() or "Лист1"
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=11)
        print(f"Создан лист: {worksheet_name}")

    first_row = worksheet.row_values(1)
    if not any(cell.strip() for cell in first_row):
        worksheet.update(values=[list(SHEET_HEADERS)], range_name="A1:K1")
        print("Добавлена шапка столбцов.")
    elif [cell.strip() for cell in first_row if cell.strip()] != list(SHEET_HEADERS):
        print("[!] Первая строка уже заполнена и отличается от шаблона — шапку не меняли.")

    share_email = settings.google_sheets_share_email.strip()
    if share_email:
        spreadsheet.share(share_email, perm_type="user", role="writer", notify=False)
        print(f"Доступ выдан: {share_email}")

    _update_env_value("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials/google-service-account.json")
    _update_env_value("GOOGLE_SHEETS_SPREADSHEET_ID", spreadsheet.id)
    _update_env_value("GOOGLE_SHEETS_SPREADSHEET_NAME", spreadsheet_name)
    _update_env_value("GOOGLE_SHEETS_WORKSHEET_NAME", worksheet_name)
    _update_env_value("GOOGLE_SHEETS_RETRY_MINUTES", str(settings.google_sheets_retry_minutes))

    test_row = [
        "0",
        "тест",
        "тестовая заявка",
        "",
        "",
        "",
        "",
        "",
        "Тест",
        "+7 900 000-00-00",
        "тест",
    ]
    worksheet.append_row(test_row, value_input_option="USER_ENTERED")
    print("Тестовая строка записана (можно удалить вручную).")

    print()
    print("=" * 60)
    print("  Google Таблица настроена")
    print("=" * 60)
    print(f"  URL: {spreadsheet.url}")
    print(f"  ID:  {spreadsheet.id}")
    print()
    print("Если таблица не видна в Google Drive — добавьте редактором:")
    print(f"  {client_email}")
    print()
    print("Перезапустите бота: run.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
