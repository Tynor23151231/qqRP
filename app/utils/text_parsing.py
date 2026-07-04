from __future__ import annotations

import re
from dataclasses import dataclass

_USERNAME_RE = re.compile(r"^@([A-Za-z0-9_]{5,32})$")


@dataclass(frozen=True)
class ParsedCommand:
    action_key: str
    target_username: str | None


def parse_dot_command(text: str, prefix: str = ".") -> ParsedCommand | None:
    """
    Разбирает сообщение вида ".муа" или ".муа @username".

    Возвращает None, если сообщение не является dot-командой
    (не начинается с префикса, или после префикса пусто).
    """
    if not text or not text.startswith(prefix):
        return None

    body = text[len(prefix):].strip()
    if not body:
        return None

    parts = body.split(maxsplit=1)
    action_key = parts[0].lower()
    if not action_key:
        return None

    target_username: str | None = None
    if len(parts) > 1:
        candidate = parts[1].strip()
        match = _USERNAME_RE.match(candidate)
        if match:
            target_username = match.group(1)

    return ParsedCommand(action_key=action_key, target_username=target_username)
