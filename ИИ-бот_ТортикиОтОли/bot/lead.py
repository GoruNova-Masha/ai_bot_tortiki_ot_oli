from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from bot.constants import CLIENT_AFTER_LEAD_MESSAGE, PHONE_DISPLAY
from config.settings import Settings


@dataclass
class Lead:
    name: str
    city: str
    city_in_service_area: bool
    product: str
    brief: str
    user_id: int
    contact_date: str

    def format_for_manager(self) -> str:
        area = "✅ в зоне доставки" if self.city_in_service_area else "⚠️ вне зоны (информирован)"
        return (
            "🆕 <b>Заявка из бота «Тортики от Оли»</b>\n\n"
            f"<b>Имя:</b> {self._esc(self.name)}\n"
            f"<b>Город:</b> {self._esc(self.city)} ({area})\n"
            f"<b>Дата обращения:</b> {self.contact_date}\n"
            f"<b>Интерес:</b> {self._esc(self.product)}\n"
            f"<b>Краткое ТЗ:</b> {self._esc(self.brief)}\n\n"
            f"<b>Telegram ID клиента:</b> <code>{self.user_id}</code>"
        )

    @staticmethod
    def _esc(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def contact_date_label(settings: Settings) -> str:
    tz = ZoneInfo(settings.tz)
    return datetime.now(tz).strftime("%d.%m.%Y")


def client_handoff_text(settings: Settings) -> str:
    phone = PHONE_DISPLAY
    return (
        f"Заявка принята! 🎂\n\n"
        f"{CLIENT_AFTER_LEAD_MESSAGE}\n\n"
        f"Чтобы связаться с кондитером напрямую, позвони или напиши:\n"
        f"<b>{phone}</b>"
    )
