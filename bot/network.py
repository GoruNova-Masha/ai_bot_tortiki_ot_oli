"""Проверка доступа к Telegram API и повтор при сетевых сбоях."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

import httpx
from telegram.error import NetworkError, TelegramError, TimedOut

if TYPE_CHECKING:
    from config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_on_network(
    action: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    delay_sec: float = 2.0,
    action_name: str = "запрос",
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await action()
        except (TimedOut, NetworkError, httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
            if attempt >= attempts:
                break
            wait = delay_sec * attempt
            logger.warning(
                "Сетевая ошибка при %s (попытка %s/%s): %s. Повтор через %.0f сек...",
                action_name,
                attempt,
                attempts,
                exc,
                wait,
            )
            await asyncio.sleep(wait)
    assert last_error is not None
    raise last_error


async def send_message_safe(
    send_action: Callable[[], Awaitable[T]],
    *,
    action_name: str = "отправке сообщения",
) -> T:
    try:
        return await retry_on_network(send_action, action_name=action_name)
    except TelegramError:
        raise
