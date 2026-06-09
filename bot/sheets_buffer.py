"""Буфер заявок при временной недоступности Google Таблицы."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BUFFER_PATH = _PROJECT_ROOT / "data" / "sheets_buffer.json"


@dataclass
class BufferedLeadRow:
    buffer_id: str
    lead_id: int
    row: list[str]
    created_at: str
    attempts: int = 0

    @classmethod
    def create(cls, lead_id: int, row: list[str]) -> BufferedLeadRow:
        return cls(
            buffer_id=str(uuid.uuid4()),
            lead_id=lead_id,
            row=row,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


class SheetsBufferStore:
    def __init__(self, path: Path = _BUFFER_PATH) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write([])

    def _read(self) -> list[dict[str, Any]]:
        try:
            data: list[Any] = json.loads(self._path.read_text(encoding="utf-8"))
            return [dict(item) for item in data if isinstance(item, dict)]
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, records: list[dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def enqueue(self, lead_id: int, row: list[str]) -> BufferedLeadRow:
        records = self._read()
        item = BufferedLeadRow.create(lead_id, row)
        records.append(asdict(item))
        self._write(records)
        return item

    def list_pending(self) -> list[BufferedLeadRow]:
        items: list[BufferedLeadRow] = []
        for raw in self._read():
            try:
                items.append(
                    BufferedLeadRow(
                        buffer_id=str(raw["buffer_id"]),
                        lead_id=int(raw["lead_id"]),
                        row=[str(cell) for cell in raw["row"]],
                        created_at=str(raw.get("created_at", "")),
                        attempts=int(raw.get("attempts", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return items

    def remove(self, buffer_id: str) -> None:
        records = [item for item in self._read() if item.get("buffer_id") != buffer_id]
        self._write(records)

    def increment_attempts(self, buffer_id: str) -> None:
        records = self._read()
        for item in records:
            if item.get("buffer_id") == buffer_id:
                item["attempts"] = int(item.get("attempts", 0)) + 1
                break
        self._write(records)
