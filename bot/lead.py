from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bot.constants import CLIENT_AFTER_LEAD_MESSAGE, PHONE_DISPLAY
from config.settings import Settings


@dataclass
class Lead:
    name: str
    phone: str
    city: str
    city_in_service_area: bool
    product: str
    brief: str
    user_id: int
    contact_date: str
    pd_consent_at: str

    def format_for_manager(self, lead_id: int | None = None) -> str:
        area = "✅ в зоне доставки" if self.city_in_service_area else "⚠️ вне зоны (информирован)"
        id_line = f"<b>№ заявки:</b> {lead_id}\n" if lead_id else ""
        return (
            "🆕 <b>Заявка из бота «Тортики от Оли»</b>\n\n"
            f"{id_line}"
            f"<b>Имя:</b> {self._esc(self.name)}\n"
            f"<b>Телефон:</b> {self._esc(self.phone)}\n"
            f"<b>Город:</b> {self._esc(self.city)} ({area})\n"
            f"<b>Дата обращения:</b> {self.contact_date}\n"
            f"<b>Согласие на ПД:</b> {self._esc(self.pd_consent_at)}\n"
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


def _timezone(settings: Settings):
    try:
        return ZoneInfo(settings.tz)
    except ZoneInfoNotFoundError:
        if settings.tz == "Europe/Moscow":
            return timezone(timedelta(hours=3))
        return timezone.utc


def contact_date_label(settings: Settings) -> str:
    return datetime.now(_timezone(settings)).strftime("%d.%m.%Y")


def consent_datetime_label(settings: Settings) -> str:
    return datetime.now(_timezone(settings)).strftime("%d.%m.%Y %H:%M")


def normalize_phone(text: str) -> str | None:
    digits = "".join(c for c in text if c.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    return None


def format_phone_display(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("7"):
        return f"+7 {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return phone


def pd_consent_message(settings: Settings) -> str:
    policy_url = settings.privacy_policy_url.strip()
    if policy_url:
        policy_part = f'<a href="{policy_url}">Политикой конфиденциальности</a>'
    else:
        policy_part = (
            "Политикой конфиденциальности (/privacy или кнопка «📄 Политика конфиденциальности»)"
        )
    return (
        "Для оформления заказа мне понадобятся ваши контактные данные. "
        "Нажимая кнопку «Согласен», вы подтверждаете согласие на обработку "
        f"персональных данных в соответствии с {policy_part}."
    )


def client_handoff_text(
    settings: Settings,
    *,
    lead_id: int,
    delivery_date: str = "",
) -> str:
    phone = PHONE_DISPLAY
    if delivery_date.strip():
        ready_line = f"Ваш заказ будет готов к <b>{delivery_date.strip()}</b>."
    else:
        ready_line = (
            "Точную дату готовности Оля уточнит при звонке — "
            "обычно это в течение 1 рабочего дня ✨"
        )
    return (
        f"Заявка №{lead_id} принята! 🎂\n\n"
        f"{ready_line}\n\n"
        f"{CLIENT_AFTER_LEAD_MESSAGE}\n\n"
        f"Чтобы связаться с кондитером напрямую, позвони или напиши:\n"
        f"<b>{phone}</b>"
    )
