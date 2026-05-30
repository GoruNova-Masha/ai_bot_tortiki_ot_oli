from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.constants import MENU_CATEGORIES, PHONE_DISPLAY
from config.settings import Settings


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [MENU_CATEGORIES[0][1], MENU_CATEGORIES[1][1]],
        [MENU_CATEGORIES[2][1], MENU_CATEGORIES[3][1]],
        [MENU_CATEGORIES[4][1], MENU_CATEGORIES[5][1]],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def phone_keyboard(settings: Settings) -> InlineKeyboardMarkup:
    tel = settings.phone_tel_uri
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=f"📞 Позвонить: {PHONE_DISPLAY}",
                    url=f"tel:{tel}",
                )
            ],
        ]
    )


def cancel_lead_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ Отменить заявку"]], resize_keyboard=True)
