from __future__ import annotations

import re
from dataclasses import dataclass, field

_USERNAME_RE = re.compile(r"^@([A-Za-z0-9_]{5,32})$")
_MAX_TARGETS = 5
_URL_RE = re.compile(r"^(https?://|tg://)\S+$", re.IGNORECASE)
_BTN_LABEL_MAX_LEN = 64
_BTN_ALERT_MAX_LEN = 200  # Telegram обрезает текст alert-а показа примерно на этой длине


@dataclass(frozen=True)
class ParsedCommand:
    action_key: str
    target_username: str | None
    keyword: str | None = None
    target_usernames: list[str] = field(default_factory=list)


def parse_dot_command(text: str, prefix: str = ".") -> ParsedCommand | None:
    """
    Разбирает сообщение вида:
      ".муа"
      ".муа @username"
      ".муа @a @b @c"           -> мульти-таргет, target_usernames=["a","b","c"]
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

    target_usernames: list[str] = []
    keyword: str | None = None

    for token in parts[1:]:
        match = _USERNAME_RE.match(token)
        if match:
            if len(target_usernames) < _MAX_TARGETS:
                target_usernames.append(match.group(1))
        elif keyword is None:
            keyword = token.lower()

    target_username = target_usernames[0] if target_usernames else None

    return ParsedCommand(
        action_key=action_key,
        target_username=target_username,
        keyword=keyword,
        target_usernames=target_usernames,
    )


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


@dataclass(frozen=True)
class ParsedButtonCommand:
    label: str
    payload: str


def parse_btn_command(text: str, prefix: str = ".") -> ParsedButtonCommand | None:
    """
    Разбирает ".btn Название кнопки | содержимое" (регистр "btn" неважен).

    "содержимое" после "|":
      - если похоже на ссылку (http://, https://, tg://) -> кнопка-ссылка;
      - иначе -> кнопка-alert, при нажатии показывает этот текст всплывающим окном
        (см. is_button_url для проверки, какой вариант получился).

    Возвращает None, если это не .btn-команда, либо в ней нет "|",
    либо название/содержимое пустые.
    """
    if not text or not text.startswith(prefix):
        return None

    body = text[len(prefix):]
    lowered = body.lower()
    if not lowered.startswith("btn"):
        return None

    rest = body[len("btn"):]
    if not rest or not rest[0].isspace():
        return None

    rest = rest.strip()
    if "|" not in rest:
        return None

    label, payload = rest.split("|", 1)
    label = label.strip()
    payload = payload.strip()
    if not label or not payload:
        return None

    return ParsedButtonCommand(label=label[:_BTN_LABEL_MAX_LEN], payload=payload)


def is_button_url(payload: str) -> bool:
    """True, если содержимое кнопки — ссылка (кнопка-URL), иначе это alert-кнопка."""
    return bool(_URL_RE.match(payload))


_NEXT_KEYWORDS = {"next", "далее", "дальше", "next screen", "следующий"}


def parse_flow_buttons(text: str, max_buttons: int) -> list[dict] | None:
    """
    Разбирает блок кнопок для одного экрана "Кнопок" — по одной кнопке на строку:
        Название | https://example.com   -> кнопка-ссылка
        Название | Текст показа           -> кнопка-alert (всплывающее окно)
        Название | next                   -> ведёт на следующий экран цепочки

    Возвращает None, если ни одной валидной строки не нашлось или строк больше max_buttons.
    """
    if not text:
        return None

    buttons: list[dict] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        label, payload = line.split("|", 1)
        label = label.strip()[:_BTN_LABEL_MAX_LEN]
        payload = payload.strip()
        if not label or not payload:
            continue

        if payload.lower() in _NEXT_KEYWORDS:
            buttons.append({"label": label, "type": "next", "payload": ""})
        elif is_button_url(payload):
            buttons.append({"label": label, "type": "url", "payload": payload})
        else:
            buttons.append({"label": label, "type": "alert", "payload": payload[:_BTN_ALERT_MAX_LEN]})

    if not buttons or len(buttons) > max_buttons:
        return None
    return buttons
