"""Сборка Application с таймаутами для Telegram API."""

from __future__ import annotations

from telegram.ext import Application
from telegram.request import HTTPXRequest

from bot.startup import post_init
from config.settings import Settings


def _build_request(settings: Settings, *, for_updates: bool) -> HTTPXRequest:
    return HTTPXRequest(
        connect_timeout=settings.telegram_connect_timeout,
        read_timeout=(
            settings.telegram_get_updates_read_timeout
            if for_updates
            else settings.telegram_read_timeout
        ),
        write_timeout=settings.telegram_write_timeout,
        pool_timeout=settings.telegram_pool_timeout,
    )


def build_application(settings: Settings) -> Application:
    builder = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .request(_build_request(settings, for_updates=False))
        .get_updates_request(_build_request(settings, for_updates=True))
    )

    if settings.telegram_base_url:
        builder = builder.base_url(settings.telegram_base_url.rstrip("/"))
    if settings.telegram_base_file_url:
        builder = builder.base_file_url(settings.telegram_base_file_url.rstrip("/"))

    return builder.build()
