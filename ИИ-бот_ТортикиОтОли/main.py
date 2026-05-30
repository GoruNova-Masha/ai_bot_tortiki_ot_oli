"""Точка входа — бот «Тортики от Оли»."""

from __future__ import annotations

import logging
import sys

from telegram.ext import Application

from bot import handlers
from bot.handlers import BotContext, register_handlers
from bot.startup import on_error, post_init
from config.settings import get_settings


def setup_logging(level: str) -> None:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
        stream=sys.stdout,
    )


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    handlers.bot_ctx = BotContext(settings)
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    app.add_error_handler(on_error)
    register_handlers(app, settings)

    logging.getLogger(__name__).info("Бот запущен (режим %s)", settings.bot_mode)
    if settings.bot_mode == "polling":
        app.run_polling(allowed_updates=["message"])
    else:
        raise NotImplementedError("Webhook-режим пока не настроен — используйте BOT_MODE=polling")


if __name__ == "__main__":
    main()
