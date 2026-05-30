from bot.constants import OUT_OF_AREA_HINT, SERVED_CITY_KEYS


def resolve_city(raw: str) -> tuple[bool, str]:
    """Возвращает (в зоне обслуживания, нормализованное название)."""
    text = " ".join(raw.strip().lower().split())
    for key, name in SERVED_CITY_KEYS.items():
        if text == key or key in text:
            return True, name
    return False, raw.strip().title() if raw.strip() else raw


def out_of_area_message(city: str) -> str:
    return OUT_OF_AREA_HINT
