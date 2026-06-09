"""Извлечение структурированных полей из текста ТЗ заявки."""

from __future__ import annotations

import re
from dataclasses import dataclass

_WEIGHT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:кг|kg)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b(\d{1,2}[./](?:0[1-9]|1[0-2])(?:[./]\d{2,4})?)\b"
)
_TIME_RE = re.compile(
    r"\b(?:в\s+)?(\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)
_FLAVOR_HINT_RE = re.compile(
    r"(?:вкус(?:ы|а)?|начинк(?:а|и|ой|у)?)\s*[:\-—]?\s*([^\n.;]{3,120})",
    re.IGNORECASE,
)
_ADDRESS_HINT_RE = re.compile(
    r"(?:адрес|доставк(?:а|и|у|ой))\s*[:\-—]?\s*([^\n.;]{5,200})",
    re.IGNORECASE,
)
_PRODUCT_KEYWORDS_RE = re.compile(
    r"\b(?:"
    r"бенто(?:[\-\s]?торт)?|"
    r"торт(?:\s+на\s+\w+)?|"
    r"набор(?:\s+клубник\w*)?|"
    r"сладкий\s+стол|"
    r"клубник\w*|"
    r"капкейк\w*|"
    r"трайфл\w*|"
    r"рулет\w*"
    r")\b",
    re.IGNORECASE,
)
_CONVERSATIONAL_PRODUCT_RE = re.compile(
    r"(?:"
    r"уже\s+(?:скинул\w*|отправил\w*|писал\w*|договор\w*)|"
    r"мы\s+же\s+обо\s+вс|"
    r"как\s+я\s+(?:писал\w*|говорил\w*)|"
    r"не\s+понимаю|"
    r"референс\s+(?:я|уже)"
    r")",
    re.IGNORECASE,
)

_MONTH_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedBrief:
    weight_kg: str = ""
    flavors: str = ""
    delivery_date: str = ""
    delivery_time: str = ""
    address: str = ""


def format_order_description(
    product: str,
    brief: str,
    *,
    max_len: int = 500,
) -> str:
    """Описание заказа для колонки «Тип торта» в Google Таблице."""
    product_text = (product or "").strip()
    brief_text = (brief or "").strip()

    if not brief_text:
        return product_text[:max_len]

    product_usable = bool(
        product_text
        and _PRODUCT_KEYWORDS_RE.search(product_text)
        and not _CONVERSATIONAL_PRODUCT_RE.search(product_text)
    )
    if not product_usable:
        return brief_text[:max_len]

    product_lower = product_text.lower()
    brief_lower = brief_text.lower()
    if brief_lower.startswith(product_lower) or product_lower in brief_lower[:80]:
        return brief_text[:max_len]

    return f"{product_text}. {brief_text}"[:max_len]


def parse_brief(text: str) -> ParsedBrief:
    normalized = (text or "").strip()
    if not normalized:
        return ParsedBrief()

    weight = _extract_weight(normalized)
    flavors = _extract_flavors(normalized)
    delivery_date = _extract_delivery_date(normalized)
    delivery_time = _extract_delivery_time(normalized)
    address = _extract_address(normalized)

    return ParsedBrief(
        weight_kg=weight,
        flavors=flavors,
        delivery_date=delivery_date,
        delivery_time=delivery_time,
        address=address,
    )


def _extract_weight(text: str) -> str:
    match = _WEIGHT_RE.search(text)
    if not match:
        return ""
    return match.group(1).replace(",", ".")


def _extract_flavors(text: str) -> str:
    match = _FLAVOR_HINT_RE.search(text)
    if match:
        return match.group(1).strip()
    return ""


def _extract_delivery_date(text: str) -> str:
    cleaned = _WEIGHT_RE.sub(" ", text)

    month_match = _MONTH_DATE_RE.search(cleaned)
    if month_match:
        day = month_match.group(1)
        month = month_match.group(2)
        year = month_match.group(3) or ""
        return f"{day} {month}{f' {year}' if year else ''}".strip()

    match = _DATE_RE.search(cleaned)
    if match:
        return match.group(1)
    return ""


def _extract_delivery_time(text: str) -> str:
    match = _TIME_RE.search(text)
    if match:
        return match.group(1)
    return ""


def _extract_address(text: str) -> str:
    match = _ADDRESS_HINT_RE.search(text)
    if match:
        return match.group(1).strip()
    return ""
