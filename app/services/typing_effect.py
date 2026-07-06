from __future__ import annotations

import asyncio
import math

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

_CURSOR = "▍"

# Telegram (Bot API) жёстко ограничивает частоту редактирования одного сообщения.
# Если печатать посимвольно с маленькой задержкой на длинном тексте — легко словить
# flood-control (429). Поэтому реальное число edit-запросов ограничено сверху,
# а на длинных сообщениях кадры укрупняются (несколько символов за один edit).
_MAX_EDITS = 25
_DELAY_SECONDS = 0.35


async def reveal_text(
    bot: Bot,
    chat_id: int,
    text: str,
    business_connection_id: str | None = None,
) -> None:
    """
    Постепенно "печатает" text в чате по нарастающей: с, со, соо, ...
    как будто сообщение набирает человек — до финального полного текста.

    parse_mode=None на каждом edit'е: текст произвольный (от пользователя),
    не должен интерпретироваться как HTML.
    """
    if not text:
        return

    chunk_size = max(1, math.ceil(len(text) / _MAX_EDITS))

    message = await bot.send_message(
        chat_id=chat_id,
        text=_CURSOR,
        parse_mode=None,
        business_connection_id=business_connection_id,
    )

    for i in range(chunk_size, len(text), chunk_size):
        await _safe_edit(bot, chat_id, message.message_id, text[:i] + _CURSOR, business_connection_id)
        await asyncio.sleep(_DELAY_SECONDS)

    # Финальный кадр — точный полный текст, без курсора.
    await _safe_edit(bot, chat_id, message.message_id, text, business_connection_id)


async def _safe_edit(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    business_connection_id: str | None,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=None,
            business_connection_id=business_connection_id,
        )
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=None,
                business_connection_id=business_connection_id,
            )
        except TelegramBadRequest:
            pass
    except TelegramBadRequest:
        # Например "message is not modified", если кадр совпал с предыдущим — не критично.
        pass
