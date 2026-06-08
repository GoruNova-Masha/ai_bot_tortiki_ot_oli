from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.constants import MENU_CATEGORIES

CONSENT_AGREE = "pd_consent:agree"
CONSENT_DECLINE = "pd_consent:decline"
CONSENT_PRIVACY = "pd_consent:privacy"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [MENU_CATEGORIES[0][1], MENU_CATEGORIES[1][1]],
        [MENU_CATEGORIES[2][1], MENU_CATEGORIES[3][1]],
        [MENU_CATEGORIES[4][1], MENU_CATEGORIES[5][1]],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def cancel_lead_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["❌ Отменить заявку"]], resize_keyboard=True)


def pd_consent_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "📄 Политика конфиденциальности",
                    callback_data=CONSENT_PRIVACY,
                )
            ],
            [
                InlineKeyboardButton("✅ Согласен", callback_data=CONSENT_AGREE),
                InlineKeyboardButton("❌ Не согласен", callback_data=CONSENT_DECLINE),
            ],
        ]
    )
