from bot.constants import (
    DELIVERY_CITIES_TEXT,
    OUT_OF_AREA_HINT,
    PICKUP_CITY,
    SERVED_CITY_KEYS,
)


def resolve_city(raw: str) -> tuple[bool, str]:
    """Возвращает (в зоне доставки, нормализованное название)."""
    text = " ".join(raw.strip().lower().split())
    for key, name in SERVED_CITY_KEYS.items():
        if text == key or key in text:
            return True, name
    return False, raw.strip().title() if raw.strip() else raw


def pickup_available(city: str) -> bool:
    """Самовывоз только в Балахне."""
    return city == PICKUP_CITY


def delivery_available(in_service_area: bool) -> bool:
    """Доставка в Балахну, Заволжье и Нижний Новгород."""
    return in_service_area


def receipt_options(city: str, in_service_area: bool) -> tuple[bool, bool]:
    """Возвращает (доступен самовывоз, доступна доставка) для заявки."""
    can_deliver = delivery_available(in_service_area)
    can_pickup = pickup_available(city) or not can_deliver
    return can_pickup, can_deliver


def receipt_options_hint(city: str, in_service_area: bool) -> str:
    if pickup_available(city) and in_service_area:
        return (
            f"В {city} доступны доставка и самовывоз 🎂\n"
            f"Самовывоз — только в {PICKUP_CITY}."
        )
    if in_service_area:
        return (
            f"В {city} доступна доставка 🎂\n"
            f"Самовывоз возможен только в {PICKUP_CITY}."
        )
    return OUT_OF_AREA_HINT


def out_of_area_message(city: str) -> str:
    return OUT_OF_AREA_HINT
