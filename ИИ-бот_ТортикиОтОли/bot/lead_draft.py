"""Черновик заявки из истории диалога с ассистентом."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from bot.constants import RECEIPT_DELIVERY, RECEIPT_PICKUP, RECEIPT_PICKUP_LABEL
from bot.geography import pickup_available, resolve_city

_DRAFT_REUSE_RE = re.compile(
    r"(?:"
    r"обсуждали(?:\s+ранее)?|"
    r"уже\s+(?:говорил\w*|писал\w*|договорил\w*|сказал\w*)|"
    r"как\s+(?:выше|ранее|в\s+чате)|"
    r"из\s+переписк\w*|"
    r"всё\s+верно|"
    r"^да\.?$"
    r")",
    re.IGNORECASE,
)

EXTRACT_SYSTEM_PROMPT = """Ты извлекаешь данные для заявки кондитерской из переписки бота с клиентом.
Верни ТОЛЬКО JSON-объект без markdown и пояснений.

Поля:
- city: город клиента — только «Балахна», «Заволжье», «Нижний Новгород» или пустая строка
- receipt_method: «pickup» (самовывоз) или «delivery» (доставка) или пустая строка
- delivery_address: улица, дом, подъезд — только если клиент назвал; иначе пустая строка
- product: тип заказа кратко (бенто-торт, торт на день рождения, набор клубники и т.п.)
- brief: все пожелания одной строкой: размер S/M (обязательно для бенто), начинка, декор в формате «Кремовая надпись: …», надпись, дата и время получения, аллергии

Правила:
- Бери только то, что явно есть в переписке. Не выдумывай.
- Для бенто размер S или M обязателен — не переходи к дате без него.
- Декор бенто: только кремовые надписи, простые рисунки, фотопечать; шары и мастика недопустимы.
- Самовывоз только в Балахне; доставка — Балахна, Заволжье, Нижний Новгород.
- Если в переписке есть итоговое резюме бота — используй его для product и brief.
- Пустые поля — пустые строки.
"""


@dataclass
class LeadDraft:
    city: str = ""
    receipt_method: str = ""
    delivery_address: str = ""
    product: str = ""
    brief: str = ""

    def has_any(self) -> bool:
        return bool(
            self.city
            or self.receipt_method
            or self.delivery_address
            or self.product
            or self.brief
        )

    def has_order_details(self) -> bool:
        return bool(self.product or self.brief)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, str] | None) -> LeadDraft | None:
        if not data:
            return None
        return cls(
            city=str(data.get("city", "")).strip(),
            receipt_method=_normalize_receipt(str(data.get("receipt_method", "")).strip()),
            delivery_address=str(data.get("delivery_address", "")).strip(),
            product=str(data.get("product", "")).strip(),
            brief=str(data.get("brief", "")).strip(),
        )


def wants_draft_reuse(text: str) -> bool:
    return bool(_DRAFT_REUSE_RE.search(text.strip()))


def _normalize_receipt(value: str) -> str:
    lowered = value.lower()
    if lowered in ("pickup", "самовывоз", RECEIPT_PICKUP_LABEL.lower()):
        return RECEIPT_PICKUP
    if lowered in ("delivery", "доставка"):
        return RECEIPT_DELIVERY
    return ""


def parse_lead_draft_json(raw: str) -> LeadDraft | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    draft = LeadDraft.from_dict({k: str(v) for k, v in data.items() if v is not None})
    return _sanitize_draft(draft)


def _sanitize_draft(draft: LeadDraft | None) -> LeadDraft | None:
    if draft is None:
        return None

    if draft.city:
        in_area, city = resolve_city(draft.city)
        if in_area:
            draft.city = city
        else:
            draft.city = ""

    if draft.receipt_method == RECEIPT_PICKUP and draft.city and not pickup_available(draft.city):
        draft.receipt_method = RECEIPT_DELIVERY

    if draft.receipt_method == RECEIPT_DELIVERY and not draft.city:
        pass
    elif draft.receipt_method == RECEIPT_PICKUP:
        draft.delivery_address = ""

    if draft.delivery_address and len(draft.delivery_address) < 5:
        draft.delivery_address = ""

    if draft.product and len(draft.product) < 3:
        draft.product = ""
    if draft.brief and len(draft.brief) < 5:
        draft.brief = ""

    return draft if draft.has_any() else None


def format_draft_summary(draft: LeadDraft) -> str:
    lines: list[str] = []
    if draft.city:
        lines.append(f"• Город: {draft.city}")
    if draft.receipt_method == RECEIPT_DELIVERY:
        lines.append("• Способ получения: доставка")
        if draft.delivery_address:
            lines.append(f"• Адрес: {draft.delivery_address}")
    elif draft.receipt_method == RECEIPT_PICKUP:
        lines.append("• Способ получения: самовывоз (Балахна)")
    if draft.product:
        lines.append(f"• Заказ: {draft.product}")
    if draft.brief:
        lines.append(f"• Пожелания: {draft.brief}")
    return "\n".join(lines)
