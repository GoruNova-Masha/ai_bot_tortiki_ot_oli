"""Извлечение структурированных полей из текста ТЗ заявки для Google Таблицы."""

from __future__ import annotations

import re
from dataclasses import dataclass

_WEIGHT_KG_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:кг|kg)\b",
    re.IGNORECASE,
)
_WEIGHT_G_RE = re.compile(
    r"(\d+)\s*г(?:рамм)?\b",
    re.IGNORECASE,
)
_DATE_DD_MM_RE = re.compile(
    r"\b(\d{1,2})[./](\d{1,2})(?:[./]\d{2,4})?\b"
)
_TIME_COLON_RE = re.compile(
    r"\b(\d{1,2}):(\d{2})\b",
)
_TIME_H_RE = re.compile(
    r"\b(?:в\s+)?(\d{1,2})\s*ч(?:ас(?:ов)?)?\b",
    re.IGNORECASE,
)
_FLAVOR_HINT_RE = re.compile(
    r"(?:начинк[аиойуе]*|вкус(?:ы|а)?)\s*[:\-—]?\s*([^\n.;«»]{2,120})",
    re.IGNORECASE,
)
_CITY_HINT_RE = re.compile(
    r"(?:город|место)\s*[:\-—]?\s*([^\n.;]{2,80})",
    re.IGNORECASE,
)
_ADDRESS_HINT_RE = re.compile(
    r"адрес(?:\s+доставки)?\s*[:\-—]?\s*([^\n;]{3,200})",
    re.IGNORECASE,
)
_DELIVERY_TO_RE = re.compile(
    r"доставк[аиуой]\s+в\s+(?!\d)([^\n;]{2,200})",
    re.IGNORECASE,
)
_CAKE_LINE_RE = re.compile(
    r"(?:\*\*)?торт(?:\*\*)?\s*[:\-—]\s*([^\n]+)",
    re.IGNORECASE,
)
_BENTO_SIZE_RE = re.compile(
    r"бенто[\-\s]*(?:торт)?\s*([SMМ])\b",
    re.IGNORECASE,
)
_BENTO_SIZE_HINT_RE = re.compile(
    r"(?:размер|размера|выбран(?:\s+размер)?)\s*[:\-—]?\s*([SMМ])\b",
    re.IGNORECASE,
)

_BENTO_WEIGHT_BY_SIZE = {
    "S": 0.65,
    "M": 1.0,
}
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
    r"референс\s+(?:я|уже)|"
    r"обсуждали|из\s+переписк"
    r")",
    re.IGNORECASE,
)

_MONTH_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE,
)

_MONTH_TO_NUM = {
    "январ": "01",
    "феврал": "02",
    "март": "03",
    "апрел": "04",
    "ма": "05",
    "май": "05",
    "июн": "06",
    "июл": "07",
    "август": "08",
    "сентябр": "09",
    "октябр": "10",
    "ноябр": "11",
    "декабр": "12",
}


@dataclass(frozen=True)
class ParsedBrief:
    weight_kg: str = ""
    flavors: str = ""
    delivery_date: str = ""
    delivery_time: str = ""
    address: str = ""


def combine_lead_text(product: str, brief: str) -> str:
    parts = [part.strip() for part in (product, brief) if part and part.strip()]
    return "\n".join(parts)


def format_order_description(
    product: str,
    brief: str,
    *,
    max_len: int = 500,
) -> str:
    """Устаревший алиас — для таблицы используйте extract_cake_type."""
    return extract_cake_type(product, brief)[:max_len]


def extract_cake_type(product: str, brief: str) -> str:
    """Тип и размер торта без начинки, надписи и логистики."""
    product_text = (product or "").strip()
    brief_text = (brief or "").strip()
    source = combine_lead_text(product_text, brief_text)

    cake_line = _CAKE_LINE_RE.search(source)
    if cake_line:
        source = cake_line.group(1).strip()

    bento_match = _BENTO_SIZE_RE.search(source)
    if bento_match:
        size = bento_match.group(1).upper().replace("М", "M")
        return f"бенто {size}"

    if re.search(r"\bбенто", source, re.IGNORECASE):
        return "бенто-торт"

    typed = _extract_named_product(source)
    if typed:
        return typed

    if product_text and not _CONVERSATIONAL_PRODUCT_RE.search(product_text):
        return _strip_non_type_details(product_text)

    return _strip_non_type_details(brief_text)[:80]


def parse_brief(text: str) -> ParsedBrief:
    normalized = (text or "").strip()
    if not normalized:
        return ParsedBrief()

    return ParsedBrief(
        weight_kg=_extract_weight(normalized),
        flavors=_extract_flavors(normalized),
        delivery_date=_extract_delivery_date(normalized),
        delivery_time=_extract_delivery_time(normalized),
        address=_extract_address(normalized),
    )


def parse_lead_text(product: str, brief: str) -> ParsedBrief:
    return parse_brief(combine_lead_text(product, brief))


def _extract_named_product(source: str) -> str:
    patterns = (
        (r"набор\s+клубник\w*", "набор клубники"),
        (r"сладкий\s+стол", "сладкий стол"),
        (r"торт\s+на\s+день\s+рожд\w*", "торт на день рождения"),
        (r"торт\s+на\s+др\b", "торт на день рождения"),
        (r"капкейк\w*", "капкейки"),
        (r"трайфл\w*", "трайфлы"),
    )
    for pattern, label in patterns:
        if re.search(pattern, source, re.IGNORECASE):
            return label
    if re.search(r"\bторт\b", source, re.IGNORECASE):
        return "торт"
    return ""


def _strip_non_type_details(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.split(
        r",\s*(?:начинк|надпись|доставк|дата|вкус|способ|город|место)\b",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = re.split(
        r"\s+(?:с\s+)?начинк\w*\s+",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = re.sub(r"\s*\([^)]*\)\s*", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;")
    return cleaned[:80]


def _detect_bento_size(text: str) -> str:
    for pattern in (
        _BENTO_SIZE_RE,
        _BENTO_SIZE_HINT_RE,
        re.compile(r"размер/вес\s*[:\-—]?\s*([SMМ])\b", re.IGNORECASE),
    ):
        match = pattern.search(text)
        if match:
            return match.group(1).upper().replace("М", "M")
    if re.search(r"бенто", text, re.IGNORECASE):
        match = re.search(r"\b([SMМ])\b", text, re.IGNORECASE)
        if match:
            return match.group(1).upper().replace("М", "M")
    return ""


def _extract_weight(text: str) -> str:
    kg_match = _WEIGHT_KG_RE.search(text)
    if kg_match:
        return _format_weight_kg(float(kg_match.group(1).replace(",", ".")))

    g_match = _WEIGHT_G_RE.search(text)
    if g_match:
        return _format_weight_kg(int(g_match.group(1)) / 1000)

    size = _detect_bento_size(text)
    if size in _BENTO_WEIGHT_BY_SIZE:
        return _format_weight_kg(_BENTO_WEIGHT_BY_SIZE[size])

    return ""


def _format_weight_kg(value: float) -> str:
    if value <= 0:
        return ""
    rounded = round(value, 2)
    if rounded == int(rounded) and rounded >= 1:
        return f"{int(rounded)}.0"
    text = f"{rounded:.2f}".rstrip("0").rstrip(".")
    if "." not in text and rounded < 1:
        return f"{rounded:.2f}".rstrip("0").rstrip(".")
    return text


def _extract_flavors(text: str) -> str:
    match = _FLAVOR_HINT_RE.search(text)
    if not match:
        return ""
    return _clean_flavors(match.group(1))


def _clean_flavors(raw: str) -> str:
    text = raw.strip()
    text = re.sub(
        r"^(?:начинк[аиойуе]*|вкус(?:ы|а)?)\s*[:\-—]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^с\s+начинкой\s+", "", text, flags=re.IGNORECASE)
    text = re.split(
        r"(?:надпись|доставк|дата|способ|город|место|время)\b",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    text = text.strip(" .,;«»\"'")
    return text[:120]


def _extract_delivery_date(text: str) -> str:
    cleaned = _WEIGHT_KG_RE.sub(" ", text)
    cleaned = _WEIGHT_G_RE.sub(" ", cleaned)

    match = _DATE_DD_MM_RE.search(cleaned)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        return f"{day:02d}.{month:02d}"

    month_match = _MONTH_DATE_RE.search(cleaned)
    if month_match:
        day = int(month_match.group(1))
        month_key = month_match.group(2).lower()[:5]
        month_num = _MONTH_TO_NUM.get(month_key)
        if month_num:
            return f"{day:02d}.{month_num}"

    return ""


def _extract_delivery_time(text: str) -> str:
    match = _TIME_COLON_RE.search(text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

    match = _TIME_H_RE.search(text)
    if match:
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"

    return ""


def _extract_address(text: str) -> str:
    match = _ADDRESS_HINT_RE.search(text)
    if match:
        return _clean_address(match.group(1))

    match = _CITY_HINT_RE.search(text)
    if match:
        return _clean_address(match.group(1))

    match = _DELIVERY_TO_RE.search(text)
    if match:
        return _clean_address(match.group(1))

    return ""


def _clean_address(raw: str) -> str:
    text = raw.strip()[:200]
    if re.fullmatch(r"\d{1,2}(?:[./]\d{1,2})?", text):
        return ""
    if re.fullmatch(r"\d{1,2}", text):
        return ""
    return text
