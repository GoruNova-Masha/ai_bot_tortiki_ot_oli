"""Запись заявок в Google Таблицу через gspread (Service Account)."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from bot.constants import (
    PICKUP_CITY,
    RECEIPT_DELIVERY,
    RECEIPT_DELIVERY_LABEL,
    RECEIPT_PICKUP_LABEL,
)
from bot.lead import Lead
from bot.lead_parser import ParsedBrief, extract_cake_type, parse_lead_text
from bot.sheets_buffer import SheetsBufferStore
from config.settings import Settings

logger = logging.getLogger(__name__)

SCOPES = (
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
)

SHEET_HEADERS = (
    "ID заявки",
    "Дата создания заявки",
    "Тип торта",
    "Вес (кг)",
    "Вкусы начинки",
    "Способ получения",
    "Дата получения",
    "Время получения",
    "Адрес",
    "Имя клиента",
    "Телефон клиента",
    "Статус",
)

SHEET_HEADER_RANGE = f"A1:{chr(ord('A') + len(SHEET_HEADERS) - 1)}1"

STATUS_IN_PROGRESS = "В работе"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_COUNTER_PATH = _PROJECT_ROOT / "data" / "lead_id_counter.json"


def _sheet_cell(value: str) -> str:
    """Google Sheets трактует + и = в начале как формулы."""
    text = str(value)
    if text.startswith(("+", "=", "-", "@")):
        return f"'{text}"
    return text


@dataclass(frozen=True)
class LeadSubmitResult:
    lead_id: int
    delivery_date: str
    receipt_method: str
    saved_to_sheets: bool
    buffered: bool


class GoogleSheetsLeadWriter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._buffer = SheetsBufferStore()
        self._worksheet: gspread.Worksheet | None = None

    @property
    def enabled(self) -> bool:
        return self._settings.google_sheets_enabled

    def build_row(self, lead: Lead, lead_id: int, parsed: ParsedBrief | None = None) -> list[str]:
        parsed = parsed or parse_lead_text(lead.product, lead.brief)
        receipt_label = (
            RECEIPT_DELIVERY_LABEL
            if lead.receipt_method == RECEIPT_DELIVERY
            else RECEIPT_PICKUP_LABEL
        )
        if lead.receipt_method == RECEIPT_DELIVERY:
            if lead.delivery_address:
                address = f"{lead.city}, {lead.delivery_address}"
            elif parsed.address:
                address = parsed.address
            else:
                address = lead.city
        else:
            address = f"Самовывоз ({PICKUP_CITY})"
        return [
            str(lead_id),
            lead.contact_date,
            extract_cake_type(lead.product, lead.brief),
            parsed.weight_kg,
            parsed.flavors,
            receipt_label,
            parsed.delivery_date,
            parsed.delivery_time,
            address,
            lead.name,
            _sheet_cell(lead.phone),
            STATUS_IN_PROGRESS,
        ]

    async def submit_lead(self, lead: Lead) -> LeadSubmitResult:
        lead_id = self._next_lead_id()
        parsed = parse_lead_text(lead.product, lead.brief)
        row = self.build_row(lead, lead_id, parsed)

        if not self.enabled:
            logger.info(
                "Google Sheets отключена — заявка №%s сохранена только локально",
                lead_id,
            )
            return LeadSubmitResult(
                lead_id=lead_id,
                delivery_date=parsed.delivery_date,
                receipt_method=lead.receipt_method,
                saved_to_sheets=False,
                buffered=False,
            )

        saved = await self._try_append_row(row)
        if saved:
            logger.info("Заявка №%s записана в Google Таблицу", lead_id)
            return LeadSubmitResult(
                lead_id=lead_id,
                delivery_date=parsed.delivery_date,
                receipt_method=lead.receipt_method,
                saved_to_sheets=True,
                buffered=False,
            )

        self._buffer.enqueue(lead_id, row)
        logger.warning(
            "Заявка №%s не записана в Google Таблицу — добавлена в буфер",
            lead_id,
        )
        return LeadSubmitResult(
            lead_id=lead_id,
            delivery_date=parsed.delivery_date,
            receipt_method=lead.receipt_method,
            saved_to_sheets=False,
            buffered=True,
        )

    async def flush_buffer(self) -> int:
        if not self.enabled:
            return 0

        flushed = 0
        for item in self._buffer.list_pending():
            saved = await self._try_append_row(item.row)
            if saved:
                self._buffer.remove(item.buffer_id)
                flushed += 1
                logger.info(
                    "Заявка №%s из буфера записана в Google Таблицу",
                    item.lead_id,
                )
            else:
                self._buffer.increment_attempts(item.buffer_id)
                logger.warning(
                    "Повторная запись заявки №%s из буфера не удалась (попытка %s)",
                    item.lead_id,
                    item.attempts + 1,
                )
        return flushed

    async def _try_append_row(self, row: list[str]) -> bool:
        try:
            await asyncio.to_thread(self._append_row_sync, row)
            return True
        except Exception:
            logger.exception("Ошибка записи строки в Google Таблицу")
            return False

    def _append_row_sync(self, row: list[str]) -> None:
        worksheet = self._get_worksheet()
        self._ensure_headers(worksheet)
        worksheet.append_row(row, value_input_option="USER_ENTERED")

    def _get_worksheet(self) -> gspread.Worksheet:
        if self._worksheet is not None:
            return self._worksheet

        creds_path = self._settings.google_sheets_credentials_file
        if not creds_path.exists():
            raise FileNotFoundError(f"Файл ключа Google не найден: {creds_path}")

        credentials = Credentials.from_service_account_file(
            str(creds_path),
            scopes=SCOPES,
        )
        client = gspread.authorize(credentials)

        spreadsheet_id = self._settings.google_sheets_spreadsheet_id.strip()
        spreadsheet_name = self._settings.google_sheets_spreadsheet_name.strip()

        if spreadsheet_id:
            try:
                spreadsheet = client.open_by_key(spreadsheet_id)
            except gspread.SpreadsheetNotFound as exc:
                raise gspread.SpreadsheetNotFound(
                    f"Таблица с ID {spreadsheet_id} не найдена. "
                    "Запустите setup_google_sheets.bat"
                ) from exc
        elif spreadsheet_name:
            try:
                spreadsheet = client.open(spreadsheet_name)
            except gspread.SpreadsheetNotFound:
                spreadsheet = client.create(spreadsheet_name)
                logger.info(
                    "Создана Google Таблица «%s», id=%s. "
                    "Запустите setup_google_sheets.bat для доступа и шапки.",
                    spreadsheet_name,
                    spreadsheet.id,
                )
        else:
            raise ValueError(
                "Укажите GOOGLE_SHEETS_SPREADSHEET_ID или GOOGLE_SHEETS_SPREADSHEET_NAME"
            )

        worksheet_name = self._settings.google_sheets_worksheet_name.strip() or "Лист1"
        self._worksheet = spreadsheet.worksheet(worksheet_name)
        return self._worksheet

    @staticmethod
    def _ensure_headers(worksheet: gspread.Worksheet) -> None:
        try:
            first_row = worksheet.row_values(1)
        except gspread.exceptions.APIError:
            first_row = []

        if [cell.strip() for cell in first_row if cell.strip()] == list(SHEET_HEADERS):
            return

        if not any(cell.strip() for cell in first_row):
            worksheet.update(values=[list(SHEET_HEADERS)], range_name=SHEET_HEADER_RANGE)
            logger.info("Создана шапка Google Таблицы")
            return

        worksheet.update(values=[list(SHEET_HEADERS)], range_name=SHEET_HEADER_RANGE)
        logger.info("Шапка Google Таблицы приведена к шаблону бота")
        return

    def _next_lead_id(self) -> int:
        _COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        counter = 0
        if _COUNTER_PATH.exists():
            try:
                data: dict[str, Any] = json.loads(_COUNTER_PATH.read_text(encoding="utf-8"))
                counter = int(data.get("last_id", 0))
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                counter = 0

        counter += 1
        _COUNTER_PATH.write_text(
            json.dumps({"last_id": counter}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return counter
