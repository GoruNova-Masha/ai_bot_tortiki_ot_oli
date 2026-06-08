"""Работа с фото из Telegram."""

from __future__ import annotations

import base64

from telegram import Update

from config.settings import Settings

PHOTO_REFERENCE_PROMPT = (
    "Клиент прислал фото референса торта или декора. "
    "Опиши, что видишь на изображении (стиль, цвета, элементы декора), "
    "и оцени реализуемость для кондитерской «Тортики от Оли». "
    "Если есть ограничения из брифа — мягко предложи альтернативу. "
    "Задай 1–2 уточняющих вопроса, если нужно."
)

PHOTO_BRIEF_PROMPT = (
    "Клиент прислал фото референса для заказа торта. "
    "Кратко опиши декор и стиль на фото (2–4 предложения) — "
    "это пойдёт в заявку кондитеру. Без приветствий и вопросов клиенту."
)


def _image_file_id(update: Update) -> tuple[str, str] | None:
    message = update.message
    if not message:
        return None
    if message.photo:
        return message.photo[-1].file_id, "image/jpeg"
    if message.document and (message.document.mime_type or "").startswith("image/"):
        mime = message.document.mime_type or "image/jpeg"
        return message.document.file_id, mime
    return None


async def get_image_data_url(update: Update, settings: Settings) -> str | None:
    """Скачивает фото и возвращает data URL для OpenAI Vision."""
    parsed = _image_file_id(update)
    if not parsed:
        return None

    file_id, mime = parsed
    tg_file = await update.get_bot().get_file(file_id)
    try:
        raw = bytes(await tg_file.download_as_bytearray())
    except (OSError, TypeError):
        return None
    if not raw:
        return None

    encoded = base64.standard_b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


async def get_image_url(update: Update, settings: Settings) -> str | None:
    """URL файла в Telegram (запасной вариант)."""
    parsed = _image_file_id(update)
    if not parsed:
        return None

    file_id, _mime = parsed
    tg_file = await update.get_bot().get_file(file_id)
    if not tg_file.file_path:
        return None

    base = settings.telegram_file_base_url
    return f"{base}/{tg_file.file_path}"
