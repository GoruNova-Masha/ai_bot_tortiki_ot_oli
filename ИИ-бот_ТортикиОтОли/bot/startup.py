"""Настройка бота при старте: команды, описание, обработка ошибок."""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.error import BadRequest, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import Application, ContextTypes

from bot import handlers

logger = logging.getLogger(__name__)
BOT_COMMANDS = [
    BotCommand("start", "Начать общение 🎂"),
    BotCommand("menu", "Главное меню"),
    BotCommand("order", "Оформить заявку"),
    BotCommand("privacy", "Политика конфиденциальности"),
    BotCommand("cancel", "Отменить оформление заявки"),
]

BOT_DESCRIPTION = (
    "Помогу выбрать торт, бенто, набор клубники или сладкий стол. "
    "Подскажу идеи и передам заявку кондитеру Оле."
)


async def post_init(application: Application) -> None:
    bot = application.bot
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_my_description(BOT_DESCRIPTION)
    me = await bot.get_me()
    logger.info("Бот @%s готов к работе", me.username)

    settings = handlers.get_ctx().settings
    if settings.google_sheets_enabled:
        if application.job_queue is None:
            logger.warning(
                "Google Sheets: буфер без автоповтора — установите "
                "python-telegram-bot[job-queue] (install_deps.bat)"
            )
        else:
            interval = settings.google_sheets_retry_minutes * 60
            application.job_queue.run_repeating(
                flush_sheets_buffer,
                interval=interval,
                first=interval,
                name="google_sheets_buffer_flush",
            )
            logger.info(
                "Google Sheets: включена, повтор буфера каждые %s мин",
                settings.google_sheets_retry_minutes,
            )
    else:
        logger.info(
            "Google Sheets: отключена (нет ключа или ID таблицы) — "
            "номера заявок выдаются локально"
        )


async def flush_sheets_buffer(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        flushed = await handlers.get_ctx().sheets.flush_buffer()
        if flushed:
            logger.info("Из буфера записано заявок в Google Таблицу: %s", flushed)
    except Exception:
        logger.exception("Ошибка при повторной записи буфера Google Sheets")

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error

    if isinstance(err, RetryAfter):
        logger.warning("Telegram просит подождать %s сек", err.retry_after)
        return

    if isinstance(err, (TimedOut, NetworkError)):
        logger.warning("Сетевая ошибка при обработке сообщения: %s", err)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "Telegram временно не отвечает. Попробуй отправить сообщение ещё раз через минуту."
                )
            except TelegramError:
                logger.warning("Не удалось отправить сообщение о сетевой ошибке")
        return

    if isinstance(err, BadRequest):
        logger.warning("Некорректный запрос к Telegram API: %s", err)
        return

    logger.exception("Ошибка при обработке update: %s", err)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Упс, что-то пошло не так 😔 Попробуй ещё раз или нажми /start"
            )
        except TelegramError:
            logger.exception("Не удалось отправить сообщение об ошибке")
