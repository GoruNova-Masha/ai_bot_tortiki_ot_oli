from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.ai_client import AIAssistant
from bot.constants import MENU_CATEGORIES, PHONE_DISPLAY
from bot.geography import out_of_area_message, resolve_city
from bot.keyboards import cancel_lead_keyboard, main_menu_keyboard, phone_keyboard
from bot.lead import Lead, client_handoff_text, contact_date_label
from bot.prompts import build_system_prompt
from bot.security import RateLimiter, is_user_allowed, sanitize_for_log, validate_message_length
from bot.storage import BusyDatesStore, ChatMemory
from config.settings import Settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Состояния оформления заявки
LEAD_NAME, LEAD_CITY, LEAD_PRODUCT, LEAD_BRIEF = range(4)

CATEGORY_HINTS: dict[str, str] = {
    "cakes": (
        "🎂 <b>Торты на заказ</b>\n"
        "От 1,5 кг, ~2400 ₽/кг. Декор считается отдельно.\n"
        "Есть авторская линейка: Вишневый, Красный бархат, Сникерс и другие.\n"
        "Расскажи, на какой повод и примерный вес — подскажу варианты!"
    ),
    "bento": (
        "🍰 <b>Бенто-торты</b>\n"
        "S — 650 г, 1600 ₽ | M — 1 кг, 2600 ₽.\n"
        "По умолчанию начинка «Вишневый». Декор проще, чем у большого торта.\n"
        "Для кого торт и какая надпись нужна?"
    ),
    "sets": (
        "🎁 <b>Букеты из клубники в шоколаде</b>\n"
        "Стандартные наборы от 4 до 16 ягод, премиум — 4000 ₽.\n"
        "Набор 17 ягод — 3200 ₽ (наличие уточняется у кондитера).\n"
        "На какое число и сколько порций примерно?"
    ),
    "sweet_table": (
        "🧁 <b>Сладкий стол</b>\n"
        "Капкейки, трайфлы, кейк-попсы, эклеры, зефир, меренговый рулет.\n"
        "Сколько гостей и что больше нравится — порционные десерты или рулет?"
    ),
    "ideas": (
        "💡 Давай придумаем идею!\n"
        "Напиши повод, возраст именинника (если есть), любимые вкусы "
        "и хочешь ли яркий декор или что-то нежное."
    ),
}

MENU_LABEL_TO_KEY = {label: key for key, label in MENU_CATEGORIES}


class BotContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.memory = ChatMemory()
        self.busy_dates = BusyDatesStore()
        self.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
        self.ai = AIAssistant(settings, build_system_prompt(settings))
        self._admin_ids = settings.admin_user_id_set


bot_ctx: BotContext | None = None


def get_ctx() -> BotContext:
    if bot_ctx is None:
        raise RuntimeError("BotContext не инициализирован")
    return bot_ctx


def _denied() -> str:
    return "Бот сейчас в тестовом режиме. Доступ только для приглашённых пользователей."


async def _guard(update: Update, settings: Settings) -> bool:
    user = update.effective_user
    if not user:
        return False
    if not is_user_allowed(settings, user.id):
        if update.message:
            await update.message.reply_text(_denied())
        return False
    if not get_ctx().rate_limiter.is_allowed(user.id):
        if update.message:
            await update.message.reply_text(
                "Слишком много сообщений подряд — подожди минутку ⏳"
            )
        return False
    return True


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return ConversationHandler.END

    text = (
        "Привет! Я бот «Тортики от Оли» 🎂\n\n"
        "Помогу выбрать торт, бенто, набор или сладкий стол, "
        "подскажу идеи и соберу заявку для кондитера.\n\n"
        "Выбери раздел в меню или просто напиши, что ищешь!"
    )
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())
    return ConversationHandler.END


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await cmd_start(update, context)


async def cmd_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return ConversationHandler.END
    context.user_data["in_lead"] = True
    await update.message.reply_text(
        "Оформим заявку для Оли 📋\nКак тебя зовут?",
        reply_markup=cancel_lead_keyboard(),
    )
    return LEAD_NAME


async def lead_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    if len(text) < 2:
        await update.message.reply_text("Напиши, пожалуйста, имя — хотя бы 2 символа.")
        return LEAD_NAME
    context.user_data["lead_name"] = text[:100]
    await update.message.reply_text(
        "Из какого ты города? (Балахна, Заволжье или Нижний Новгород)"
    )
    return LEAD_CITY


async def lead_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)

    in_area, city = resolve_city(text)
    context.user_data["lead_city"] = city
    context.user_data["lead_city_ok"] = in_area

    if not in_area:
        await update.message.reply_text(out_of_area_message(city))

    await update.message.reply_text(
        "Что тебя интересует?\n"
        "Например: торт на день рождения, бенто, набор клубники, сладкий стол."
    )
    return LEAD_PRODUCT


async def lead_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    if len(text) < 3:
        await update.message.reply_text("Опиши коротко, что хочешь заказать.")
        return LEAD_PRODUCT
    context.user_data["lead_product"] = text[:300]
    await update.message.reply_text(
        "Кратко опиши пожелания: дата праздника, вес/количество, вкусы, декор, аллергии."
    )
    return LEAD_BRIEF


async def lead_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    if len(text) < 5:
        await update.message.reply_text("Добавь чуть больше деталей в ТЗ (минимум 5 символов).")
        return LEAD_BRIEF

    user = update.effective_user
    lead = Lead(
        name=context.user_data["lead_name"],
        city=context.user_data["lead_city"],
        city_in_service_area=context.user_data.get("lead_city_ok", False),
        product=context.user_data["lead_product"],
        brief=text[:1500],
        user_id=user.id,
        contact_date=contact_date_label(settings),
    )

    await _submit_lead(update, settings, lead)
    _clear_lead(context)
    return ConversationHandler.END


async def _submit_lead(update: Update, settings: Settings, lead: Lead) -> None:
    manager_id = settings.telegram_manager_chat_id.strip()
    if manager_id:
        try:
            await update.get_bot().send_message(
                chat_id=int(manager_id),
                text=lead.format_for_manager(),
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Не удалось отправить заявку менеджеру chat_id=%s", manager_id)

    await update.message.reply_text(
        client_handoff_text(settings),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )
    await update.message.reply_text(
        f"Или нажми кнопку ниже, чтобы позвонить: {PHONE_DISPLAY}",
        reply_markup=phone_keyboard(settings),
    )


def _clear_lead(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_lead", None)
    for key in ("lead_name", "lead_city", "lead_city_ok", "lead_product"):
        context.user_data.pop(key, None)


async def _cancel_lead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_lead(context)
    await update.message.reply_text(
        "Заявка отменена. Если понадоблюсь — напиши в меню 🎂",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return ConversationHandler.END

    label = (update.message.text or "").strip()
    key = MENU_LABEL_TO_KEY.get(label)
    if not key:
        return ConversationHandler.END

    if key == "order":
        return await cmd_order(update, context)

    hint = CATEGORY_HINTS.get(key, "")
    if hint:
        await update.message.reply_text(hint, parse_mode=ParseMode.HTML)
    return ConversationHandler.END


async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return

    if context.user_data.get("in_lead"):
        return

    text = (update.message.text or "").strip()
    if text in MENU_LABEL_TO_KEY:
        return
    if not text:
        return
    if not validate_message_length(text, settings.max_message_length):
        await update.message.reply_text(
            f"Сообщение слишком длинное (макс. {settings.max_message_length} символов)."
        )
        return

    ctx = get_ctx()
    user = update.effective_user
    logger.info(
        "Сообщение user_id=%s: %s",
        user.id,
        sanitize_for_log(text),
    )

    await update.message.chat.send_action("typing")
    ctx.memory.append(user.id, "user", text)
    reply = await ctx.ai.reply(ctx.memory.get(user.id), text)
    ctx.memory.append(user.id, "assistant", reply)
    await update.message.reply_text(reply)


# --- Админ: занятые даты (не показываются клиентам) ---

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ctx = get_ctx()
    if not user or user.id not in ctx._admin_ids:
        await update.message.reply_text("Команда только для администратора.")
        return

    dates = ctx.busy_dates.list_dates()
    lines = "\n".join(f"• {d}" for d in dates) if dates else "— список пуст"
    await update.message.reply_text(
        "🛠 <b>Админ-панель</b> (занятые даты не видны клиентам)\n\n"
        f"<b>Занятые даты:</b>\n{lines}\n\n"
        "Команды:\n"
        "/adddate ГГГГ-ММ-ДД — добавить\n"
        "/deldate ГГГГ-ММ-ДД — удалить",
        parse_mode=ParseMode.HTML,
    )


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


async def cmd_adddate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ctx = get_ctx()
    if not user or user.id not in ctx._admin_ids:
        return
    if not context.args or not _DATE_RE.match(context.args[0]):
        await update.message.reply_text("Формат: /adddate 2026-06-20")
        return
    iso = context.args[0]
    if ctx.busy_dates.add(iso):
        await update.message.reply_text(f"Дата {iso} добавлена.")
    else:
        await update.message.reply_text(f"Дата {iso} уже в списке.")


async def cmd_deldate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    ctx = get_ctx()
    if not user or user.id not in ctx._admin_ids:
        return
    if not context.args or not _DATE_RE.match(context.args[0]):
        await update.message.reply_text("Формат: /deldate 2026-06-20")
        return
    iso = context.args[0]
    if ctx.busy_dates.remove(iso):
        await update.message.reply_text(f"Дата {iso} удалена.")
    else:
        await update.message.reply_text(f"Даты {iso} нет в списке.")


def register_handlers(app: Application, settings: Settings) -> None:
    menu_filter = filters.Regex(
        "^(" + "|".join(re.escape(label) for _, label in MENU_CATEGORIES) + ")$"
    )

    lead_conv = ConversationHandler(
        entry_points=[
            CommandHandler("order", cmd_order),
            MessageHandler(
                filters.Regex(f"^{re.escape(MENU_CATEGORIES[-1][1])}$"),
                cmd_order,
            ),
        ],
        states={
            LEAD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)],
            LEAD_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_city)],
            LEAD_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_product)],
            LEAD_BRIEF: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_brief)],
        },
        fallbacks=[
            CommandHandler("cancel", _cancel_lead),
            MessageHandler(
                filters.Regex("^❌ Отменить заявку$"),
                _cancel_lead,
            ),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(lead_conv)
    app.add_handler(MessageHandler(menu_filter, handle_menu_button))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("adddate", cmd_adddate))
    app.add_handler(CommandHandler("deldate", cmd_deldate))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
