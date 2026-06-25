from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from bot.ai_client import AIAssistant
from bot.constants import (
    BENTO_CATEGORY_HINT,
    DELIVERY_CITIES_TEXT,
    MENU_CATEGORIES,
    PICKUP_CITY,
    RECEIPT_DELIVERY,
    RECEIPT_PICKUP,
    RECEIPT_PICKUP_LABEL,
)
from bot.geography import (
    out_of_area_message,
    pickup_available,
    receipt_options,
    receipt_options_hint,
    resolve_city,
)
from bot.google_sheets import GoogleSheetsLeadWriter
from bot.keyboards import (
    CONSENT_AGREE,
    CONSENT_DECLINE,
    CONSENT_PRIVACY,
    cancel_lead_keyboard,
    main_menu_keyboard,
    pd_consent_inline_keyboard,
    receipt_method_keyboard,
)
from bot.media import (
    PHOTO_BRIEF_PROMPT,
    PHOTO_REFERENCE_PROMPT,
    get_image_data_url,
    get_image_url,
)
from bot.lead import (
    Lead,
    client_handoff_text,
    consent_datetime_label,
    contact_date_label,
    format_phone_display,
    normalize_phone,
    pd_consent_message,
)
from bot.lead_draft import LeadDraft, format_draft_summary, wants_draft_reuse
from bot.privacy_policy import POLICY_BUTTON_LABEL, format_privacy_policy_html
from bot.network import retry_on_network
from bot.prompts import build_system_prompt
from bot.security import RateLimiter, is_user_allowed, sanitize_for_log, validate_message_length
from bot.storage import BusyDatesStore, ChatMemory, PdConsentStore
from config.settings import Settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Состояния оформления заявки
(
    LEAD_CONSENT,
    LEAD_NAME,
    LEAD_PHONE,
    LEAD_CITY,
    LEAD_RECEIPT,
    LEAD_ADDRESS,
    LEAD_PRODUCT,
    LEAD_BRIEF,
) = range(8)

CATEGORY_HINTS: dict[str, str] = {
    "cakes": (
        "🎂 <b>Торты на заказ</b>\n"
        "От 1,5 кг, ~2400 ₽/кг. Декор считается отдельно.\n"
        "Есть авторская линейка: Вишневый, Красный бархат, Сникерс и другие.\n"
        "Расскажи, на какой повод и примерный вес — подскажу варианты!"
    ),
    "bento": BENTO_CATEGORY_HINT,
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

PHOTO_FILTER = filters.PHOTO | filters.Document.IMAGE


class BotContext:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.memory = ChatMemory()
        self.busy_dates = BusyDatesStore()
        self.pd_consents = PdConsentStore()
        self.rate_limiter = RateLimiter(settings.rate_limit_per_minute)
        self.ai = AIAssistant(settings, build_system_prompt(settings))
        self.sheets = GoogleSheetsLeadWriter(settings)
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


async def _send_privacy_policy(update: Update, settings: Settings) -> None:
    await update.message.reply_text(
        format_privacy_policy_html(settings),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return
    await _send_privacy_policy(update, settings)


async def cmd_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return ConversationHandler.END
    context.user_data["in_lead"] = True
    await update.message.reply_text(
        "Оформим заявку для Оли 📋",
        reply_markup=cancel_lead_keyboard(),
    )
    await update.message.reply_text(
        pd_consent_message(settings),
        parse_mode=ParseMode.HTML,
        reply_markup=pd_consent_inline_keyboard(),
    )
    return LEAD_CONSENT


def _is_consent_agree(text: str) -> bool:
    normalized = text.strip().lower().lstrip("✅").strip()
    return normalized in ("согласен", "согласна", "да", "ok", "ок", "yes", "+")


def _is_consent_decline(text: str) -> bool:
    normalized = text.strip().lower().lstrip("❌").strip()
    return normalized in ("не согласен", "не согласна", "нет", "no")


def _get_lead_draft(context: ContextTypes.DEFAULT_TYPE) -> LeadDraft | None:
    return LeadDraft.from_dict(context.user_data.get("lead_draft"))


async def _load_draft_from_chat(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    history = get_ctx().memory.get(message.chat_id)
    if not history:
        return
    try:
        await message.chat.send_action("typing")
    except (TimedOut, NetworkError, TelegramError):
        pass
    try:
        draft = await get_ctx().ai.extract_lead_draft(history)
    except Exception:
        logger.exception("Не удалось извлечь черновик заявки из переписки")
        return
    if not draft or not draft.has_any():
        return
    context.user_data["lead_draft"] = draft.to_dict()
    summary = format_draft_summary(draft)
    if summary:
        await message.reply_text(
            "Из нашей переписки уже есть детали заказа:\n"
            f"{summary}\n\n"
            "Подтяну их в заявку — останется указать контакты "
            "и при необходимости дополнить данные."
        )


async def _grant_consent(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    consent_at = consent_datetime_label(settings)
    context.user_data["pd_consent_at"] = consent_at
    try:
        get_ctx().pd_consents.record_consent(
            user_id=message.chat_id,
            consent_at=consent_at,
        )
    except OSError:
        logger.exception("Не удалось сохранить согласие на ПД")

    await _load_draft_from_chat(message, context)

    await message.reply_text(
        "Спасибо! Как вас зовут?",
        reply_markup=cancel_lead_keyboard(),
    )
    return LEAD_NAME


async def _decline_consent(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_lead(context)
    await message.reply_text(
        "Без согласия на обработку персональных данных оформление заказа "
        "невозможно. Если передумаете — нажмите «Оформить заявку» в меню.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def lead_consent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return LEAD_CONSENT
    await query.answer()

    if query.data == CONSENT_PRIVACY:
        await query.message.reply_text(
            format_privacy_policy_html(get_ctx().settings),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return LEAD_CONSENT
    if query.data == CONSENT_DECLINE:
        return await _decline_consent(query.message, context)
    if query.data == CONSENT_AGREE:
        return await _grant_consent(query.message, context)
    return LEAD_CONSENT


async def lead_consent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    if text == POLICY_BUTTON_LABEL:
        await _send_privacy_policy(update, get_ctx().settings)
        return LEAD_CONSENT
    if _is_consent_decline(text) or text == "❌ Не согласен":
        return await _decline_consent(update.message, context)
    if _is_consent_agree(text) or text == "✅ Согласен":
        return await _grant_consent(update.message, context)

    await update.message.reply_text(
        "Нажми кнопку «✅ Согласен» или «❌ Не согласен» под сообщением выше. "
        "Можно также написать «согласен» или «не согласен».",
        reply_markup=pd_consent_inline_keyboard(),
    )
    return LEAD_CONSENT


async def lead_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    if len(text) < 2:
        await update.message.reply_text("Напиши, пожалуйста, имя — хотя бы 2 символа.")
        return LEAD_NAME
    context.user_data["lead_name"] = text[:100]
    await update.message.reply_text(
        "Укажи номер телефона для связи (например, +7 930 123-45-67)."
    )
    return LEAD_PHONE


async def lead_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    phone = normalize_phone(text)
    if not phone:
        await update.message.reply_text(
            "Не получилось распознать номер. Напиши телефон в формате "
            "+7XXXXXXXXXX или 8XXXXXXXXXX."
        )
        return LEAD_PHONE
    context.user_data["lead_phone"] = format_phone_display(phone)
    draft = _get_lead_draft(context)
    if draft and draft.city:
        await update.message.reply_text(
            f"Город из переписки: {draft.city}.",
            reply_markup=cancel_lead_keyboard(),
        )
        return await _apply_lead_city(update.message, context, draft.city)

    await update.message.reply_text(
        "Из какого вы города? (Балахна, Заволжье или Нижний Новгород)"
    )
    return LEAD_CITY


async def _start_delivery_address(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["lead_receipt"] = RECEIPT_DELIVERY
    await message.reply_text(
        "Укажи адрес доставки: улица, дом, подъезд, этаж.",
        reply_markup=cancel_lead_keyboard(),
    )
    return LEAD_ADDRESS


async def _start_pickup_order(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["lead_receipt"] = RECEIPT_PICKUP
    context.user_data["lead_delivery_address"] = ""
    if not pickup_available(context.user_data.get("lead_city", "")):
        await message.reply_text(f"Самовывоз — в {PICKUP_CITY}.")
    return await _continue_after_product_setup(message, context)


async def _continue_after_address(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _continue_after_product_setup(message, context)


async def _continue_after_product_setup(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_lead_draft(context)
    if draft and draft.product and not context.user_data.get("lead_product"):
        context.user_data["lead_product"] = draft.product[:300]
        return await _proceed_to_brief(message, context)
    return await _ask_lead_product(message, context)


async def _proceed_to_brief(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_lead_draft(context)
    brief_text = (draft.brief[:1500] if draft and draft.brief else "")
    if brief_text:
        context.user_data["lead_brief_candidate"] = brief_text
        await message.reply_text(
            "Пожелания из переписки:\n\n"
            f"{brief_text}\n\n"
            "Если всё верно — напишите «да». Или дополните и исправьте одним сообщением.",
            reply_markup=cancel_lead_keyboard(),
        )
        return LEAD_BRIEF

    if context.user_data.get("lead_receipt") == RECEIPT_DELIVERY:
        brief_prompt = (
            "Дополните, если нужно, пожелания к заказу: дата доставки, время, "
            "вес, вкусы, декор, надпись, аллергии."
        )
    else:
        brief_prompt = (
            "Дополните, если нужно, пожелания к заказу: дата самовывоза, "
            "вес, вкусы, декор, надпись, аллергии."
        )
    await message.reply_text(brief_prompt, reply_markup=cancel_lead_keyboard())
    return LEAD_BRIEF


async def _continue_after_city(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    can_pickup = context.user_data.get("lead_pickup_ok", False)
    can_deliver = context.user_data.get("lead_delivery_ok", False)
    draft = _get_lead_draft(context)

    if draft and draft.receipt_method:
        if draft.receipt_method == RECEIPT_PICKUP and can_pickup:
            return await _start_pickup_order(message, context)
        if draft.receipt_method == RECEIPT_DELIVERY and can_deliver:
            context.user_data["lead_receipt"] = RECEIPT_DELIVERY
            if draft.delivery_address:
                context.user_data["lead_delivery_address"] = draft.delivery_address[:300]
                return await _continue_after_address(message, context)
            return await _start_delivery_address(message, context)

    if can_pickup and can_deliver:
        await message.reply_text(
            "Как удобнее получить заказ?",
            reply_markup=receipt_method_keyboard(pickup=True, delivery=True),
        )
        return LEAD_RECEIPT

    if can_deliver:
        return await _start_delivery_address(message, context)

    return await _start_pickup_order(message, context)


async def _apply_lead_city(
    message, context: ContextTypes.DEFAULT_TYPE, city_text: str
) -> int:
    in_area, city = resolve_city(city_text)
    context.user_data["lead_city"] = city
    context.user_data["lead_city_ok"] = in_area

    can_pickup, can_deliver = receipt_options(city, in_area)
    context.user_data["lead_pickup_ok"] = can_pickup
    context.user_data["lead_delivery_ok"] = can_deliver

    if not in_area:
        await message.reply_text(out_of_area_message(city))
    else:
        await message.reply_text(receipt_options_hint(city, in_area))

    return await _continue_after_city(message, context)


async def lead_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)

    return await _apply_lead_city(update.message, context, text)


def _is_receipt_pickup(text: str) -> bool:
    normalized = text.strip().lower().replace("🏠", "").strip()
    return normalized == RECEIPT_PICKUP_LABEL.lower()


def _is_receipt_delivery(text: str) -> bool:
    normalized = text.strip().lower().replace("🚗", "").strip()
    return normalized == RECEIPT_DELIVERY_LABEL.lower()


async def _ask_lead_product(message, context: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _get_lead_draft(context)
    if draft and draft.has_order_details():
        await message.reply_text(
            "Тип заказа и пожелания уже есть в переписке.\n"
            "Напишите «да», чтобы продолжить, или укажите тип заказа, если нужно исправить.",
            reply_markup=cancel_lead_keyboard(),
        )
    else:
        await message.reply_text(
            "Какой тип заказа?\n"
            "Например: торт на день рождения, бенто-торт, набор клубники, сладкий стол.",
            reply_markup=cancel_lead_keyboard(),
        )
    return LEAD_PRODUCT


async def lead_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)

    can_pickup = context.user_data.get("lead_pickup_ok", False)
    can_deliver = context.user_data.get("lead_delivery_ok", False)
    keyboard = receipt_method_keyboard(pickup=can_pickup, delivery=can_deliver)

    if _is_receipt_pickup(text):
        if not can_pickup:
            await update.message.reply_text(
                f"Самовывоз возможен только в {PICKUP_CITY}.",
                reply_markup=keyboard,
            )
            return LEAD_RECEIPT
        return await _start_pickup_order(update.message, context)

    if _is_receipt_delivery(text):
        if not can_deliver:
            await update.message.reply_text(
                f"Доставка возможна только в {DELIVERY_CITIES_TEXT}. "
                f"Выбери самовывоз в {PICKUP_CITY} или укажи другой город.",
                reply_markup=keyboard,
            )
            return LEAD_RECEIPT
        return await _start_delivery_address(update.message, context)

    await update.message.reply_text(
        "Выбери способ получения кнопкой ниже.",
        reply_markup=keyboard,
    )
    return LEAD_RECEIPT


async def lead_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)
    if len(text) < 5:
        await update.message.reply_text(
            "Адрес слишком короткий. Укажи улицу, дом и при необходимости подъезд и этаж."
        )
        return LEAD_ADDRESS
    context.user_data["lead_delivery_address"] = text[:300]
    return await _continue_after_address(update.message, context)


async def lead_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)

    draft = _get_lead_draft(context)
    if wants_draft_reuse(text):
        if draft and draft.product:
            context.user_data["lead_product"] = draft.product[:300]
            return await _proceed_to_brief(update.message, context)
        if draft and draft.brief:
            context.user_data["lead_product"] = (
                draft.product or "Заказ по переписке"
            )[:300]
            return await _proceed_to_brief(update.message, context)
        await update.message.reply_text(
            "Не нашла детали в переписке. Коротко укажите тип заказа, "
            "например: бенто-торт."
        )
        return LEAD_PRODUCT

    if len(text) < 3:
        await update.message.reply_text("Опишите коротко, что хотите заказать.")
        return LEAD_PRODUCT

    context.user_data["lead_product"] = text[:300]
    return await _proceed_to_brief(update.message, context)


async def lead_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if text == "❌ Отменить заявку":
        return await _cancel_lead(update, context)

    draft = _get_lead_draft(context)
    candidate = str(context.user_data.get("lead_brief_candidate", "")).strip()

    if wants_draft_reuse(text):
        if candidate:
            context.user_data.pop("lead_brief_candidate", None)
            return await _finish_lead_brief(update, context, candidate)
        if draft and draft.brief:
            return await _finish_lead_brief(update, context, draft.brief[:1500])
        await update.message.reply_text(
            "Не нашла пожелания в переписке. Опишите заказ одним сообщением."
        )
        return LEAD_BRIEF

    context.user_data.pop("lead_brief_candidate", None)
    if candidate and text:
        merged = f"{candidate}\n\nДополнение клиента: {text}"[:1500]
        return await _finish_lead_brief(update, context, merged)

    return await _finish_lead_brief(update, context, text)


async def lead_brief_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    settings = get_ctx().settings
    image_data_url = await get_image_data_url(update, settings)
    if not image_data_url:
        await update.message.reply_text(
            "Не удалось загрузить фото. Попробуй отправить ещё раз "
            "или опиши пожелания текстом."
        )
        return LEAD_BRIEF

    caption = (update.message.caption or "").strip()
    try:
        await update.message.chat.send_action("typing")
    except (TimedOut, NetworkError, TelegramError):
        pass

    analysis = await get_ctx().ai.describe_image_for_brief(
        PHOTO_BRIEF_PROMPT,
        image_data_url,
    )
    if not analysis:
        if len(caption) >= 5:
            text = (
                f"{caption}\n\n"
                "📷 К заявке приложено фото-референс "
                "(автоописание временно недоступно)."
            )
            return await _finish_lead_brief(update, context, text[:1500])
        await update.message.reply_text(
            "Не получилось разобрать фото автоматически 😔\n"
            "Добавь, пожалуйста, текстом: дата, вес, вкусы и пожелания по декору. "
            "Можешь отправить фото ещё раз вместе с подписью."
        )
        return LEAD_BRIEF

    if caption:
        text = f"{caption}\n\nРеференс по фото: {analysis}"
    else:
        text = f"Референс по фото: {analysis}"
    return await _finish_lead_brief(update, context, text[:1500])


async def _finish_lead_brief(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> int:
    settings = get_ctx().settings
    if len(text) < 5:
        await update.message.reply_text("Добавь чуть больше деталей в ТЗ (минимум 5 символов).")
        return LEAD_BRIEF

    user = update.effective_user
    if not user:
        await update.message.reply_text("Не удалось определить пользователя. Нажми /start.")
        return ConversationHandler.END

    missing = [
        label
        for key, label in (
            ("lead_name", "имя"),
            ("lead_phone", "телефон"),
            ("lead_city", "город"),
            ("lead_receipt", "способ получения"),
            ("lead_product", "заказ"),
        )
        if not context.user_data.get(key)
    ]
    if (
        context.user_data.get("lead_receipt") == RECEIPT_DELIVERY
        and not context.user_data.get("lead_delivery_address")
    ):
        missing.append("адрес доставки")
    if missing:
        logger.warning(
            "Неполная заявка user_id=%s, нет полей: %s",
            user.id,
            ", ".join(missing),
        )
        _clear_lead(context)
        await update.message.reply_text(
            "Данные заявки потерялись (часто из‑за второго запущенного бота). "
            "Оформи заявку заново: /order",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    lead = Lead(
        name=context.user_data["lead_name"],
        phone=context.user_data["lead_phone"],
        city=context.user_data["lead_city"],
        city_in_service_area=context.user_data.get("lead_city_ok", False),
        product=context.user_data["lead_product"],
        brief=text[:1500],
        user_id=user.id,
        contact_date=contact_date_label(settings),
        pd_consent_at=context.user_data.get("pd_consent_at", "—"),
        receipt_method=context.user_data.get("lead_receipt", RECEIPT_PICKUP),
        delivery_address=context.user_data.get("lead_delivery_address", ""),
    )

    try:
        get_ctx().pd_consents.update_latest(
            user.id,
            name=lead.name,
            phone=lead.phone,
        )
    except OSError:
        logger.exception("Не удалось обновить журнал согласий на ПД")

    await _submit_lead(update, settings, lead)
    _clear_lead(context)
    return ConversationHandler.END


async def _send_ai_reply(update: Update, user_id: int, user_note: str, reply: str) -> None:
    ctx = get_ctx()
    ctx.memory.append(user_id, "user", user_note)
    ctx.memory.append(user_id, "assistant", reply)
    try:
        await retry_on_network(
            lambda: update.message.reply_text(reply),
            action_name="отправке ответа пользователю",
        )
    except TelegramError:
        logger.exception("Не удалось отправить ответ пользователю")
        try:
            await update.message.reply_text(
                "Ответ готов, но Telegram временно не отвечает. "
                "Попробуй написать ещё раз через минуту."
            )
        except TelegramError:
            pass


async def _submit_lead(update: Update, settings: Settings, lead: Lead) -> None:
    try:
        submit_result = await get_ctx().sheets.submit_lead(lead)
        if submit_result.saved_to_sheets:
            logger.info("Заявка №%s записана в Google Таблицу", submit_result.lead_id)
        elif submit_result.buffered:
            logger.warning(
                "Заявка №%s в буфере Google Sheets — повтор через %s мин",
                submit_result.lead_id,
                settings.google_sheets_retry_minutes,
            )
        else:
            logger.warning(
                "Заявка №%s оформлена без Google Sheets (интеграция отключена)",
                submit_result.lead_id,
            )
    except Exception:
        logger.exception("Критическая ошибка записи заявки №? в Google Sheets")
        from bot.google_sheets import LeadSubmitResult

        submit_result = LeadSubmitResult(
            lead_id=0,
            delivery_date="",
            receipt_method=lead.receipt_method,
            saved_to_sheets=False,
            buffered=False,
        )

    try:
        await retry_on_network(
            lambda: update.message.reply_text(
                client_handoff_text(
                    settings,
                    lead_id=submit_result.lead_id,
                    delivery_date=submit_result.delivery_date,
                    receipt_method=submit_result.receipt_method,
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(),
            ),
            action_name="подтверждении заявки",
        )
    except TelegramError:
        logger.exception("Не удалось отправить подтверждение заявки пользователю")

    manager_id = settings.telegram_manager_chat_id.strip()
    if not manager_id:
        return
    try:
        manager_note = lead.format_for_manager(submit_result.lead_id)
        if submit_result.buffered:
            manager_note += (
                "\n\n⚠️ <i>Запись в Google Таблицу отложена — "
                "бот повторит через несколько минут.</i>"
            )
        await update.get_bot().send_message(
            chat_id=int(manager_id),
            text=manager_note,
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Не удалось отправить заявку менеджеру chat_id=%s", manager_id)


def _clear_lead(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("in_lead", None)
    for key in (
        "lead_name",
        "lead_phone",
        "lead_city",
        "lead_city_ok",
        "lead_pickup_ok",
        "lead_delivery_ok",
        "lead_receipt",
        "lead_delivery_address",
        "lead_product",
        "lead_draft",
        "lead_brief_candidate",
        "pd_consent_at",
    ):
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

    try:
        await update.message.chat.send_action("typing")
    except (TimedOut, NetworkError, TelegramError) as exc:
        logger.warning("Не удалось отправить typing: %s", exc)

    reply = await ctx.ai.reply(ctx.memory.get(user.id), text)
    await _send_ai_reply(update, user.id, text, reply)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_ctx().settings
    if not await _guard(update, settings):
        return

    if context.user_data.get("in_lead"):
        return

    user = update.effective_user
    if not user:
        return

    image_data_url = await get_image_data_url(update, settings)
    if not image_data_url:
        image_data_url = await get_image_url(update, settings)
    if not image_data_url:
        await update.message.reply_text(
            "Не удалось загрузить фото. Попробуй отправить ещё раз или опиши идею текстом."
        )
        return

    caption = (update.message.caption or "").strip()
    prompt = PHOTO_REFERENCE_PROMPT
    if caption:
        prompt = f"{PHOTO_REFERENCE_PROMPT}\n\nКомментарий клиента: {caption}"

    logger.info("Фото user_id=%s caption=%s", user.id, sanitize_for_log(caption or "—"))

    try:
        await update.message.chat.send_action("typing")
    except (TimedOut, NetworkError, TelegramError) as exc:
        logger.warning("Не удалось отправить typing: %s", exc)

    ctx = get_ctx()
    history = ctx.memory.get(user.id)
    reply = await ctx.ai.reply_with_image(history, prompt, image_data_url)

    memory_note = "📷 Фото референс"
    if caption:
        memory_note = f"{memory_note}: {caption}"
    await _send_ai_reply(update, user.id, memory_note, reply)


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
            LEAD_CONSENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_consent),
                CallbackQueryHandler(lead_consent_callback, pattern=r"^pd_consent:"),
            ],
            LEAD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_name)],
            LEAD_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_phone)],
            LEAD_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_city)],
            LEAD_RECEIPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_receipt)],
            LEAD_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_address)],
            LEAD_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, lead_product)],
            LEAD_BRIEF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lead_brief),
                MessageHandler(PHOTO_FILTER, lead_brief_photo),
            ],
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
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(lead_conv)
    app.add_handler(MessageHandler(menu_filter, handle_menu_button))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("adddate", cmd_adddate))
    app.add_handler(CommandHandler("deldate", cmd_deldate))
    app.add_handler(MessageHandler(PHOTO_FILTER, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))
