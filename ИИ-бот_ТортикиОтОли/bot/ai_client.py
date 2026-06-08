from __future__ import annotations

import logging
from typing import Any

from openai import AsyncOpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)

CHAT_UNAVAILABLE_MESSAGE = (
    "Сейчас не получается ответить через ассистента 😔\n"
    "Попробуй переформулировать вопрос или нажми «Оформить заявку» в меню."
)

BRIEF_IMAGE_SYSTEM_PROMPT = (
    "Ты помощник кондитера «Тортики от Оли». "
    "Кратко и по делу описываешь торты и декор на фото для внутренней заявки."
)


class AIAssistant:
    def __init__(self, settings: Settings, system_prompt: str) -> None:
        self._settings = settings
        self._system_prompt = system_prompt
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

    async def reply(
        self, history: list[dict[str, str]], user_message: str
    ) -> str:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        result = await self._complete_raw(messages)
        return result or CHAT_UNAVAILABLE_MESSAGE

    async def reply_with_image(
        self,
        history: list[dict[str, str]],
        user_message: str,
        image_url: str,
    ) -> str:
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_prompt}]
        messages.extend(history)
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        )
        result = await self._complete_raw(
            messages,
            model=self._settings.openai_vision_model_name,
        )
        return result or CHAT_UNAVAILABLE_MESSAGE

    async def describe_image_for_brief(self, prompt: str, image_data_url: str) -> str | None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": BRIEF_IMAGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]
        return await self._complete_raw(
            messages,
            model=self._settings.openai_vision_model_name,
            max_tokens=400,
        )

    async def _complete_raw(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int = 900,
    ) -> str | None:
        try:
            response = await self._client.chat.completions.create(
                model=model or self._settings.openai_model,
                messages=messages,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content
            if text and text.strip():
                return text.strip()
            return None
        except Exception:
            logger.exception("Ошибка OpenAI API")
            return None
