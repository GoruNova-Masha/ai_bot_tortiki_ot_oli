"""Приведение Google Таблицы заявок к единому оформлению и исправление данных."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from google.oauth2.service_account import Credentials
import gspread

from bot.google_sheets import SCOPES, SHEET_HEADERS, SHEET_HEADER_RANGE, STATUS_IN_PROGRESS
from config.settings import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parent
_COUNTER_PATH = _PROJECT_ROOT / "data" / "lead_id_counter.json"

# Палитра «Тортики от Оли»: тёплый розово-карамельный тон
COLOR_HEADER_BG = {"red": 0.718, "green": 0.431, "blue": 0.475}  # #B76E79
COLOR_HEADER_TEXT = {"red": 1.0, "green": 1.0, "blue": 1.0}
COLOR_BAND_LIGHT = {"red": 1.0, "green": 1.0, "blue": 1.0}
COLOR_BAND_CREAM = {"red": 0.984, "green": 0.953, "blue": 0.941}  # #FBF3F0
COLOR_BORDER = {"red": 0.91, "green": 0.835, "blue": 0.816}  # #E8D5D0
COLOR_STATUS_BG = {"red": 0.996, "green": 0.949, "blue": 0.78}  # мягкий жёлтый

STATUS_OPTIONS = ["Новая", STATUS_IN_PROGRESS, "Готово", "Отменена", "Завершена"]
COL_COUNT = len(SHEET_HEADERS)
PHONE_COL_INDEX = 10
STATUS_COL_INDEX = 11


def _sheet_cell(value: str) -> str:
    text = str(value)
    if text.startswith(("+", "=", "-", "@")):
        return f"'{text}"
    return text


def _reset_lead_counter() -> None:
    _COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _COUNTER_PATH.write_text(
        json.dumps({"last_id": 0}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _remove_existing_banding(spreadsheet: gspread.Spreadsheet, sheet_id: int) -> None:
    meta = spreadsheet.fetch_sheet_metadata()
    for sheet in meta.get("sheets", []):
        if sheet["properties"]["sheetId"] != sheet_id:
            continue
        bandings = sheet.get("bandedRanges", [])
        if not bandings:
            return
        requests = [
            {"deleteBanding": {"bandedRangeId": band["bandedRangeId"]}}
            for band in bandings
        ]
        spreadsheet.batch_update({"requests": requests})


def _build_format_requests(sheet_id: int) -> list[dict]:
    data_end = 1000
    data_range = {
        "sheetId": sheet_id,
        "startRowIndex": 1,
        "endRowIndex": data_end,
        "startColumnIndex": 0,
        "endColumnIndex": COL_COUNT,
    }
    full_grid = {
        "sheetId": sheet_id,
        "startRowIndex": 0,
        "endRowIndex": data_end,
        "startColumnIndex": 0,
        "endColumnIndex": COL_COUNT,
    }

    requests: list[dict] = [
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {
                        "frozenRowCount": 1,
                        "rowCount": data_end,
                    },
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.rowCount",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": COL_COUNT,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_HEADER_BG,
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": COLOR_HEADER_TEXT,
                            "fontSize": 10,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": (
                    "userEnteredFormat(backgroundColor,textFormat,"
                    "horizontalAlignment,verticalAlignment,wrapStrategy)"
                ),
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 42},
                "fields": "pixelSize",
            }
        },
        {
            "repeatCell": {
                "range": data_range,
                "cell": {
                    "userEnteredFormat": {
                        "verticalAlignment": "TOP",
                        "wrapStrategy": "WRAP",
                        "textFormat": {"fontSize": 10},
                    }
                },
                "fields": "userEnteredFormat(verticalAlignment,wrapStrategy,textFormat)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": data_end,
                    "startColumnIndex": PHONE_COL_INDEX,
                    "endColumnIndex": PHONE_COL_INDEX + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {"type": "TEXT"},
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": data_end,
                    "startColumnIndex": STATUS_COL_INDEX,
                    "endColumnIndex": STATUS_COL_INDEX + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        {
            "updateBorders": {
                "range": full_grid,
                "top": {"style": "SOLID", "width": 1, "color": COLOR_BORDER},
                "bottom": {"style": "SOLID", "width": 1, "color": COLOR_BORDER},
                "left": {"style": "SOLID", "width": 1, "color": COLOR_BORDER},
                "right": {"style": "SOLID", "width": 1, "color": COLOR_BORDER},
                "innerHorizontal": {"style": "SOLID", "width": 1, "color": COLOR_BORDER},
                "innerVertical": {"style": "SOLID", "width": 1, "color": COLOR_BORDER},
            }
        },
        {
            "addBanding": {
                "bandedRange": {
                    "range": data_range,
                    "rowProperties": {
                        "firstBandColor": COLOR_BAND_LIGHT,
                        "secondBandColor": COLOR_BAND_CREAM,
                    },
                }
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": data_end,
                    "startColumnIndex": STATUS_COL_INDEX,
                    "endColumnIndex": STATUS_COL_INDEX + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": COLOR_STATUS_BG,
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)",
            }
        },
    ]

    column_widths = [70, 110, 140, 70, 130, 100, 90, 140, 120, 130, 100]
    for index, width in enumerate(column_widths):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": index,
                        "endIndex": index + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )

    return requests


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()

    if not settings.google_sheets_enabled:
        print("[ОШИБКА] Google Sheets не настроена")
        return 1

    credentials = Credentials.from_service_account_file(
        str(settings.google_sheets_credentials_file),
        scopes=SCOPES,
    )
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
    worksheet = spreadsheet.worksheet(settings.google_sheets_worksheet_name)
    sheet_id = worksheet.id

    rows = worksheet.get_all_values()
    print(f"Строк до очистки: {len(rows)}")

    # Шапка
    worksheet.update(values=[list(SHEET_HEADERS)], range_name=SHEET_HEADER_RANGE)

    # Удаляем битые тестовые строки (старый тест с некорректными данными)
    if len(rows) > 1:
        worksheet.delete_rows(2, len(rows))
        print(f"Удалено тестовых строк: {len(rows) - 1}")

    _reset_lead_counter()
    print("Счётчик заявок сброшен — следующая заявка будет №1")

    _remove_existing_banding(spreadsheet, sheet_id)
    requests = _build_format_requests(sheet_id)
    spreadsheet.batch_update({"requests": requests})

    print("[OK] Шапка, цвета, границы и выпадающий список статусов применены")
    print(f"URL: {spreadsheet.url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
