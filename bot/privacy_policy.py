"""Загрузка и форматирование политики конфиденциальности."""

from __future__ import annotations

import html
import re

from config.settings import Settings

POLICY_BUTTON_LABEL = "📄 Политика конфиденциальности"


def _clean_policy_text(raw: str) -> str:
    text = raw.replace("\\.", ".").replace("\\+", "+").replace("\\_", "_")
    text = text.replace("\\[", "[").replace("\\]", "]")
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        lambda m: f'{m.group(1).lstrip("@")} ({m.group(2)})',
        text,
    )
    return text.strip()


def load_privacy_policy_text(settings: Settings) -> str:
    return _clean_policy_text(settings.privacy_policy_path.read_text(encoding="utf-8"))


def format_privacy_policy_html(settings: Settings) -> str:
    text = load_privacy_policy_text(settings)
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            lines.append("")
            continue
        if line.startswith("Политика конфиденциальности"):
            lines.append(f"<b>{html.escape(line)}</b>")
        elif re.match(r"^\d+\.", line):
            lines.append(f"<b>{html.escape(line)}</b>")
        else:
            lines.append(html.escape(line))
    return "\n".join(lines)
