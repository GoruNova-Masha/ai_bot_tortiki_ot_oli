"""Проверка окружения перед запуском бота."""

from __future__ import annotations

import sys


def main() -> int:
    print("Python:", sys.version.split()[0])

    try:
        from config.settings import get_settings

        s = get_settings()
        print("TELEGRAM_BOT_TOKEN: OK")
        print("OPENAI_API_KEY: OK")
        print("TELEGRAM_MANAGER_CHAT_ID:", s.telegram_manager_chat_id or "(не задан)")
        print("BUSINESS_PHONE:", s.business_phone)
        print("Модель ИИ:", s.openai_model)
    except Exception as e:
        print("Ошибка настроек:", e)
        return 1

    try:
        from bot.prompts import build_system_prompt

        prompt = build_system_prompt(s)
        print(f"Промпт загружен: {len(prompt)} символов")
    except Exception as e:
        print("Ошибка промпта:", e)
        return 1

    print("\nВсё готово. Запустите: python main.py  или  run.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
