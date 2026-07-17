from __future__ import annotations

import asyncio

from aiogram.types import Message

# Ожидающие ответа от QQdownloadbot запросы, по одному на business_connection_id.
_pending: dict[str, asyncio.Future] = {}

# Последнее полученное от QQdownloadbot сообщение — на случай, если новый ответ
# не придёт за отведённое время (fallback: переслать то, что есть).
_last_message: dict[str, Message] = {}


def register_waiter(connection_id: str) -> asyncio.Future:
    """Создаёт (пересоздаёт, если уже была) точку ожидания ответа для этого подключения."""
    old = _pending.get(connection_id)
    if old is not None and not old.done():
        old.cancel()

    future: asyncio.Future = asyncio.get_event_loop().create_future()
    _pending[connection_id] = future
    return future


def resolve_waiter(connection_id: str, message: Message) -> bool:
    """Вызывается, когда приходит сообщение от QQdownloadbot. Возвращает True, если кто-то ждал."""
    _last_message[connection_id] = message

    future = _pending.get(connection_id)
    if future is not None and not future.done():
        future.set_result(message)
        return True
    return False


def clear_waiter(connection_id: str) -> None:
    _pending.pop(connection_id, None)


def get_last_message(connection_id: str) -> Message | None:
    return _last_message.get(connection_id)
