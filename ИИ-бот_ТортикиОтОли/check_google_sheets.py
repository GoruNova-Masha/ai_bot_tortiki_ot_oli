"""Проверка подключения бота к Google Таблице."""

from __future__ import annotations

import asyncio
import sys

from config.settings import get_settings


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()

    print("=== Проверка Google Sheets ===")
    print(f"ID таблицы: {settings.google_sheets_spreadsheet_id or '(не задан)'}")
    print(f"Лист: {settings.google_sheets_worksheet_name}")
    print(f"Ключ: {settings.google_sheets_credentials_file}")

    if not settings.google_sheets_credentials_file.exists():
        print("\n[ОШИБКА] Нет файла ключа:", settings.google_sheets_credentials_file)
        print("Положите JSON сервисного аккаунта и запустите setup_google_sheets.bat")
        return 1

    if not settings.google_sheets_spreadsheet_id.strip():
        print("\n[ОШИБКА] Задайте GOOGLE_SHEETS_SPREADSHEET_ID в .env")
        return 1

    import json

    from google.oauth2.service_account import Credentials
    import gspread

    from bot.google_sheets import (
        SCOPES,
        SHEET_HEADERS,
        SHEET_HEADER_RANGE,
        GoogleSheetsLeadWriter,
    )
    from bot.lead import Lead

    creds_data = json.loads(settings.google_sheets_credentials_file.read_text(encoding="utf-8"))
    service_email = creds_data.get("client_email", "?")
    print(f"Сервисный аккаунт: {service_email}")

    try:
        credentials = Credentials.from_service_account_file(
            str(settings.google_sheets_credentials_file),
            scopes=SCOPES,
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
    except PermissionError:
        print("\n[ОШИБКА] Нет доступа к таблице (403).")
        print("Откройте таблицу в Google Sheets -> Поделиться -> добавьте редактора:")
        print(f"  {service_email}")
        print("Затем запустите этот скрипт снова.")
        return 1
    except gspread.SpreadsheetNotFound:
        print("\n[ОШИБКА] Таблица с таким ID не найдена. Проверьте GOOGLE_SHEETS_SPREADSHEET_ID")
        return 1
    except Exception as exc:
        print(f"\n[ОШИБКА] {exc}")
        return 1

    print(f"\n[OK] Таблица открыта: {spreadsheet.title}")
    worksheets = [ws.title for ws in spreadsheet.worksheets()]
    print(f"[OK] Листы: {', '.join(worksheets)}")

    ws_name = settings.google_sheets_worksheet_name.strip()
    try:
        worksheet = spreadsheet.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.get_worksheet(0)
        print(f"[!] Лист «{ws_name}» не найден, используется: {worksheet.title}")
        print(f"    Обновите в .env: GOOGLE_SHEETS_WORKSHEET_NAME={worksheet.title}")

    header = worksheet.row_values(1)
    if not any(cell.strip() for cell in header):
        worksheet.update(values=[list(SHEET_HEADERS)], range_name=SHEET_HEADER_RANGE)
        print("[OK] Шапка столбцов создана")
    elif [c.strip() for c in header if c.strip()] == list(SHEET_HEADERS):
        print("[OK] Шапка столбцов совпадает с шаблоном")
    else:
        print("[!] Шапка отличается от шаблона бота — запись всё равно возможна")

    async def test_write() -> None:
        writer = GoogleSheetsLeadWriter(settings)
        lead = Lead(
            name="Проверка бота",
            phone="+7 900 000-00-99",
            city="Заволжье",
            city_in_service_area=True,
            product="тест",
            brief="Проверка записи из check_google_sheets.py, 1.5 кг, 20.06 в 14:00",
            user_id=0,
            contact_date="07.06.2026",
            pd_consent_at="—",
        )
        result = await writer.submit_lead(lead)
        print(f"\n[OK] Тестовая заявка №{result.lead_id} записана")
        print(f"     В таблице: {'да' if result.saved_to_sheets else 'нет (буфер)'}")

    asyncio.run(test_write())
    print(f"\nСсылка: {spreadsheet.url}")
    print("\n=== Всё работает ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
