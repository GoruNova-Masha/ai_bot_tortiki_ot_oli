"""Точка входа — бот «Тортики от Оли»."""

from __future__ import annotations

import logging
import sys

from bot import handlers
from bot.app_builder import build_application
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
    if settings.google_sheets_enabled:
        logging.getLogger(__name__).info(
            "Google Sheets: таблица %s, лист «%s»",
            settings.google_sheets_spreadsheet_id or settings.google_sheets_spreadsheet_name,
            settings.google_sheets_worksheet_name,
        )
    else:
        logging.getLogger(__name__).warning(
            "Google Sheets: не настроена — заявки не будут попадать в таблицу"
        )

    app = build_application(settings)
    app.add_error_handler(on_error)
    register_handlers(app, settings)

    logging.getLogger(__name__).info(
        "Бот запущен (режим %s, get_updates timeout %s сек)",
        settings.bot_mode,
        settings.telegram_get_updates_timeout,
    )
    if settings.bot_mode == "polling":
        app.run_polling(
            allowed_updates=["message", "callback_query"],
            timeout=settings.telegram_get_updates_timeout,
            bootstrap_retries=-1,
            poll_interval=1.0,
        )
    else:
        raise NotImplementedError("Webhook-режим пока не настроен — используйте BOT_MODE=polling")


if __name__ == "__main__":
    main()
