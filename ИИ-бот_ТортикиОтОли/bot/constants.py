"""Бизнес-правила из answers.md и брифа."""

from __future__ import annotations

SERVED_CITY_KEYS: dict[str, str] = {
    "балахна": "Балахна",
    "заволжье": "Заволжье",
    "нижний новгород": "Нижний Новгород",
    "нижний": "Нижний Новгород",
    "нн": "Нижний Новгород",
    "нижний н": "Нижний Новгород",
}

SERVED_CITIES_TEXT = "Балахна, Заволжье и Нижний Новгород"
DELIVERY_CITIES_TEXT = SERVED_CITIES_TEXT
PICKUP_CITY = "Балахна"

OUT_OF_AREA_HINT = (
    "К сожалению, доставка в твой город пока не осуществляется 🎂\n"
    f"Доставка — в {DELIVERY_CITIES_TEXT}.\n"
    f"Самовывоз возможен только в {PICKUP_CITY}."
)

RECEIPT_PICKUP = "pickup"
RECEIPT_DELIVERY = "delivery"
RECEIPT_PICKUP_LABEL = "Самовывоз"
RECEIPT_DELIVERY_LABEL = "Доставка"
RECEIPT_PICKUP_BUTTON = "🏠 Самовывоз"
RECEIPT_DELIVERY_BUTTON = "🚗 Доставка"

CLIENT_AFTER_LEAD_MESSAGE = (
    "Оля свяжется с тобой в течение 1 рабочего дня, чтобы уточнить детали заказа ✨"
)

PHONE_DISPLAY = "+7 930 800-14-79"

MENU_CATEGORIES = (
    ("cakes", "🎂 Торты"),
    ("bento", "🍰 Бенто-торты"),
    ("sets", "🎁 Наборы клубники"),
    ("sweet_table", "🧁 Сладкий стол"),
    ("ideas", "💡 Помочь с идеей"),
    ("order", "📞 Оформить заявку"),
)

SET_17_BERRIES_NOTE = (
    "Набор из 17 ягод — 3 200 ₽. "
    "⚠️ Наличие требует подтверждения у кондитера."
)
