"""Ограничения доступа и защита от злоупотреблений."""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from config.settings import Settings


@dataclass
class RateLimiter:
    """Простой in-memory лимит сообщений на пользователя."""

    limit_per_minute: int
    _buckets: dict[int, list[float]] = field(default_factory=lambda: defaultdict(list))

    def is_allowed(self, user_id: int) -> bool:
        now = time.monotonic()
        window = 60.0
        bucket = self._buckets[user_id]
        self._buckets[user_id] = [t for t in bucket if now - t < window]
        if len(self._buckets[user_id]) >= self.limit_per_minute:
            return False
        self._buckets[user_id].append(now)
        return True


def is_user_allowed(settings: Settings, user_id: int) -> bool:
    if not settings.bot_whitelist_enabled:
        return True
    allowed = settings.allowed_user_id_set
    if not allowed:
        return False
    return user_id in allowed


def validate_message_length(text: str, max_length: int) -> bool:
    return len(text) <= max_length


def sanitize_for_log(text: str, max_visible: int = 80) -> str:
    """Не логировать полный текст пользователя в проде — обрезка."""
    t = text.replace("\n", " ").strip()
    if len(t) <= max_visible:
        return t
    return t[:max_visible] + "…"
