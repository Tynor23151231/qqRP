from __future__ import annotations

import re
from dataclasses import dataclass

_USERNAME_RE = re.compile(r"^@([A-Za-z0-9_]{5,32})$")


@dataclass(frozen=True)
class ParsedCommand:
    action_key: str
    target_username: str | None
    keyword: str | None = None


def parse_dot_command(text: str, prefix: str = ".") -> ParsedCommand | None:
    """
    Разбирает сообщение вида:
      ".муа"
      ".муа @username"
      ".лизь попу"              -> keyword="попу"
      ".лизь попу @username"    -> keyword="попу", target_username="username"

    Возвращает None, если сообщение не является dot-командой
    (не начинается с префикса, или после префикса пусто).
    """
    if not text or not text.startswith(prefix):
        return None

    body = text[len(prefix):].strip()
    if not body:
        return None

    parts = body.split()
    action_key = parts[0].lower()
    if not action_key:
        return None

    target_username: str | None = None
    keyword: str | None = None

    for token in parts[1:]:
        match = _USERNAME_RE.match(token)
        if match and target_username is None:
            target_username = match.group(1)
        elif keyword is None:
            keyword = token.lower()

    return ParsedCommand(action_key=action_key, target_username=target_username, keyword=keyword)


def parse_typing_command(text: str, prefix: str = ".") -> str | None:
    """
    Разбирает ".typing <текст>" (регистр действия неважен), сохраняя исходный
    текст сообщения (пробелы, регистр, переносы строк) — в отличие от
    parse_dot_command, который разбивает тело на отдельные токены.

    Возвращает текст для "печатания" или None, если это не .typing-команда.
    """
    if not text or not text.startswith(prefix):
        return None

    body = text[len(prefix):]
    lowered = body.lower()
    if not lowered.startswith("typing"):
        return None

    rest = body[len("typing"):]
    if not rest or not rest[0].isspace():
        return None

    payload = rest.strip()
    return payload or None
