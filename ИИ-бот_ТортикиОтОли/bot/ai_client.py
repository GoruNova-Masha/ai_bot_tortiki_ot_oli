from __future__ import annotations

import logging

from openai import AsyncOpenAI

from config.settings import Settings

logger = logging.getLogger(__name__)


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
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_model,
                messages=messages,
                temperature=0.7,
                max_tokens=900,
            )
            text = response.choices[0].message.content
            return text.strip() if text else "Не смог сформулировать ответ — попробуй переформулировать вопрос 🎂"
        except Exception:
            logger.exception("Ошибка OpenAI API")
            return (
                "Сейчас не получается ответить через ассистента 😔\n"
                "Можешь оформить заявку — кнопка «Оформить заявку» в меню, "
                "и Оля свяжется с тобой."
            )
