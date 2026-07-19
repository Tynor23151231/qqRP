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


def is_placeholder(message: Message) -> bool:
    """
    Многие 'рич-пост'-боты сперва шлют заглушку ('⏳ Загружаю...'), а потом
    РЕДАКТИРУЮТ это же сообщение, вставляя медиа. Заглушкой считаем сообщение
    без вложений — на неё смысла останавливаться нет, ждём либо медиа, либо правку.
    """
    return not any(
        [
            message.photo,
            message.video,
            message.animation,
            message.document,
            message.audio,
            message.voice,
            message.video_note,
            message.rich_message,
        ]
    )


def _flatten_rich_text(value) -> str:
    """Достаёт обычный текст из RichText (может быть строкой, списком или обёрткой типа RichTextBold)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_flatten_rich_text(v) for v in value)
    text_attr = getattr(value, "text", None)
    if text_attr is not None:
        return _flatten_rich_text(text_attr)
    return ""


def _extract_from_rich_message(rich_message) -> tuple[str | None, object, str]:
    """
    Рич-сообщения (RichMessage) нельзя переслать 1-в-1 через sendRichMessage — та
    ссылается на медиа только по HTTP(S) URL, а полученные блоки содержат уже
    готовые file_id. Поэтому берём первое медиа из блоков как есть (photo/video/...),
    а весь текст сообщения "расплющиваем" в обычную подпись — теряется структурная
    разметка (таблицы, заголовки), но само видео/фото и текст доходят.
    Возвращает (media_type, media_object, caption_text).
    """
    media_type: str | None = None
    media_obj = None
    text_parts: list[str] = []

    for block in rich_message.blocks or []:
        block_type = getattr(block, "type", None)
        if media_type is None and block_type == "photo" and getattr(block, "photo", None):
            media_type, media_obj = "photo", block.photo[-1]
        elif media_type is None and block_type == "video" and getattr(block, "video", None):
            media_type, media_obj = "video", block.video
        elif media_type is None and block_type == "animation" and getattr(block, "animation", None):
            media_type, media_obj = "animation", block.animation
        elif media_type is None and block_type == "audio" and getattr(block, "audio", None):
            media_type, media_obj = "audio", block.audio
        elif media_type is None and block_type == "voice_note" and getattr(block, "voice_note", None):
            media_type, media_obj = "voice", block.voice_note

        block_text = getattr(block, "text", None)
        if block_text is not None:
            flattened = _flatten_rich_text(block_text)
            if flattened:
                text_parts.append(flattened)
        caption = getattr(block, "caption", None)
        if caption is not None:
            flattened = _flatten_rich_text(getattr(caption, "text", caption))
            if flattened:
                text_parts.append(flattened)

    return media_type, media_obj, "\n".join(text_parts).strip()


async def resend_message(bot, chat_id: int, source: Message, business_connection_id: str | None = None) -> None:
    """
    Пересылка/копирование сообщений запрещена Bot API через business_connection_id
    ("can't forward messages as business"), а RichMessage (см. документацию Rich
    messages) вообще нельзя скопировать через copy_message. Поэтому во всех случаях
    пересобираем сообщение заново нужным send-методом (business_connection_id=None
    в обычных группах — параметр просто не передаётся) с тем же file_id — для
    Telegram это новая отправка, а не копия/форвард.
    """
    kwargs = dict(chat_id=chat_id, business_connection_id=business_connection_id, reply_markup=source.reply_markup)

    if source.rich_message is not None:
        media_type, media_obj, caption_text = _extract_from_rich_message(source.rich_message)
        caption = caption_text or None
        if media_type == "photo":
            await bot.send_photo(photo=media_obj.file_id, caption=caption, **kwargs)
        elif media_type == "video":
            await bot.send_video(video=media_obj.file_id, caption=caption, **kwargs)
        elif media_type == "animation":
            await bot.send_animation(animation=media_obj.file_id, caption=caption, **kwargs)
        elif media_type == "audio":
            await bot.send_audio(audio=media_obj.file_id, caption=caption, **kwargs)
        elif media_type == "voice":
            await bot.send_voice(voice=media_obj.file_id, caption=caption, **kwargs)
        elif caption_text:
            await bot.send_message(text=caption_text, **kwargs)
        return

    if source.text is not None:
        await bot.send_message(text=source.text, entities=source.entities, **kwargs)
    elif source.photo:
        await bot.send_photo(
            photo=source.photo[-1].file_id, caption=source.caption, caption_entities=source.caption_entities, **kwargs
        )
    elif source.video:
        await bot.send_video(
            video=source.video.file_id, caption=source.caption, caption_entities=source.caption_entities, **kwargs
        )
    elif source.animation:
        await bot.send_animation(
            animation=source.animation.file_id, caption=source.caption, caption_entities=source.caption_entities, **kwargs
        )
    elif source.document:
        await bot.send_document(
            document=source.document.file_id, caption=source.caption, caption_entities=source.caption_entities, **kwargs
        )
    elif source.audio:
        await bot.send_audio(
            audio=source.audio.file_id, caption=source.caption, caption_entities=source.caption_entities, **kwargs
        )
    elif source.voice:
        await bot.send_voice(
            voice=source.voice.file_id, caption=source.caption, caption_entities=source.caption_entities, **kwargs
        )
    elif source.video_note:
        kwargs.pop("reply_markup", None)
        await bot.send_video_note(video_note=source.video_note.file_id, **kwargs)
    else:
        # Неизвестный/неподдерживаемый тип — на крайний случай подпись/текст, если есть.
        if source.caption:
            await bot.send_message(text=source.caption, entities=source.caption_entities, **kwargs)
    """Обновляет 'последнее сообщение' по ключу, не завершая ожидание (см. is_placeholder)."""
    _last_message[key] = message


def resolve_waiter(key: str, message: Message) -> bool:
    """Вызывается, когда приходит финальное сообщение от QQdownloadbot. Возвращает True, если кто-то ждал."""
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
