"""Настройка бота при старте: команды, описание, обработка ошибок."""

from __future__ import annotations

import logging

from telegram import BotCommand, Update
from telegram.ext import Application, ContextTypes

logger = logging.getLogger(__name__)

BOT_COMMANDS = [
    BotCommand("start", "Начать общение 🎂"),
    BotCommand("menu", "Главное меню"),
    BotCommand("order", "Оформить заявку"),
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


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Ошибка при обработке update: %s", context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Упс, что-то пошло не так 😔 Попробуй ещё раз или нажми /start"
            )
        except Exception:
            logger.exception("Не удалось отправить сообщение об ошибке")
