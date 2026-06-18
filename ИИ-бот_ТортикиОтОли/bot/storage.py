"""Локальное хранение: история диалога и занятые даты (только для админки)."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BUSY_DATES_PATH = _PROJECT_ROOT / "data" / "busy_dates.json"
_PD_CONSENTS_PATH = _PROJECT_ROOT / "data" / "pd_consents.json"
_MAX_HISTORY = 24


def _ensure_data_dir() -> None:
    _BUSY_DATES_PATH.parent.mkdir(parents=True, exist_ok=True)


class ChatMemory:
    def __init__(self) -> None:
        self._sessions: dict[int, list[dict[str, str]]] = {}

    def append(self, user_id: int, role: str, content: str) -> None:
        history = self._sessions.setdefault(user_id, [])
        history.append({"role": role, "content": content})
        if len(history) > _MAX_HISTORY:
            self._sessions[user_id] = history[-_MAX_HISTORY:]

    def get(self, user_id: int) -> list[dict[str, str]]:
        return list(self._sessions.get(user_id, []))

    def clear(self, user_id: int) -> None:
        self._sessions.pop(user_id, None)


class BusyDatesStore:
    def __init__(self, path: Path = _BUSY_DATES_PATH) -> None:
        self._path = path
        _ensure_data_dir()
        if not self._path.exists():
            self._write([])

    def _read(self) -> list[str]:
        try:
            data: list[Any] = json.loads(self._path.read_text(encoding="utf-8"))
            return sorted({str(d) for d in data})
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, dates: list[str]) -> None:
        _ensure_data_dir()
        self._path.write_text(
            json.dumps(sorted(set(dates)), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_dates(self) -> list[str]:
        return self._read()

    def add(self, iso_date: str) -> bool:
        dates = self._read()
        if iso_date in dates:
            return False
        dates.append(iso_date)
        self._write(dates)
        return True

    def remove(self, iso_date: str) -> bool:
        dates = self._read()
        if iso_date not in dates:
            return False
        self._write([d for d in dates if d != iso_date])
        return True

    def is_busy(self, day: date) -> bool:
        return day.isoformat() in self._read()


def today_iso() -> str:
    return datetime.now().date().isoformat()


class PdConsentStore:
    """Журнал согласий на обработку персональных данных."""

    def __init__(self, path: Path = _PD_CONSENTS_PATH) -> None:
        self._path = path
        _ensure_data_dir()
        if not self._path.exists():
            self._write([])

    def _read(self) -> list[dict[str, Any]]:
        try:
            data: list[Any] = json.loads(self._path.read_text(encoding="utf-8"))
            return [dict(item) for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, records: list[dict[str, Any]]) -> None:
        _ensure_data_dir()
        self._path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_consent(
        self,
        *,
        user_id: int,
        consent_at: str,
        name: str = "",
        phone: str = "",
    ) -> None:
        records = self._read()
        records.append(
            {
                "user_id": user_id,
                "consent_at": consent_at,
                "name": name,
                "phone": phone,
            }
        )
        self._write(records)

    def update_latest(self, user_id: int, *, name: str, phone: str) -> None:
        records = self._read()
        for item in reversed(records):
            if item.get("user_id") == user_id:
                item["name"] = name
                item["phone"] = phone
                self._write(records)
                return
