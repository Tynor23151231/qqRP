from __future__ import annotations

import asyncio

from aiogram.types import Message

# Ожидающие ответа от QQdownloadbot запросы, по ключу (обычно str(chat_id)
# служебной группы-релея, у каждого пользователя своя).
_pending: dict[str, asyncio.Future] = {}

# Последнее полученное от QQdownloadbot сообщение по каждому ключу — на случай,
# если новый ответ не придёт за отведённое время (fallback: переслать то, что есть).
_last_message: dict[str, Message] = {}


def register_waiter(key: str) -> asyncio.Future:
    """Создаёт (пересоздаёт, если уже была) точку ожидания ответа по этому ключу."""
    old = _pending.get(key)
    if old is not None and not old.done():
        old.cancel()

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending[key] = future
    return future


def resolve_waiter(key: str, message: Message) -> bool:
    """Вызывается, когда приходит сообщение от QQdownloadbot. Возвращает True, если кто-то ждал."""
    _last_message[key] = message

    future = _pending.get(key)
    if future is not None and not future.done():
        future.set_result(message)
        return True
    return False


def clear_waiter(key: str) -> None:
    _pending.pop(key, None)


def get_last_message(key: str) -> Message | None:
    return _last_message.get(key)
