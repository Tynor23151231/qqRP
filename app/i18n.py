from __future__ import annotations


def L(lang: str | None, ru: str, en: str) -> str:
    """Возвращает ru- или en-вариант строки в зависимости от языка пользователя."""
    return en if lang == "en" else ru
