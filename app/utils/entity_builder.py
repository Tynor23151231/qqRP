from __future__ import annotations

from dataclasses import dataclass, field

from aiogram.types import MessageEntity


def utf16_len(text: str) -> int:
    """
    Telegram считает offset/length сущностей в UTF-16 code units, а не в
    Python-символах. Для большинства кириллических/эмодзи-символов из BMP
    это совпадает с len(), но для эмодзи вне BMP — нет, поэтому считаем честно.
    """
    return len(text.encode("utf-16-le")) // 2


def utf16_slice(text: str, offset: int, length: int) -> str:
    """
    Достаёт подстроку по offset/length из MessageEntity, которые считаются в
    UTF-16 code units. Обычная питоновская срезка text[offset:offset+length]
    ломается на 2+ эмодзи подряд: большинство эмодзи (в т.ч. премиум-плейсхолдеры)
    лежат вне BMP и в UTF-16 занимают 2 code unit, а в Python-строке — 1 символ,
    поэтому offset второго и следующих эмодзи "уезжает" без этой перекодировки.
    """
    raw = text.encode("utf-16-le")
    return raw[offset * 2:(offset + length) * 2].decode("utf-16-le")


@dataclass
class EntityTextBuilder:
    """
    Собирает финальный plain-текст сообщения вместе со списком MessageEntity
    (ссылки на профили и премиум-эмодзи), т.к. Bot API не позволяет
    одновременно использовать parse_mode и entities.
    """

    _parts: list[str] = field(default_factory=list)
    _entities: list[MessageEntity] = field(default_factory=list)
    _offset: int = 0

    def add_text(self, text: str) -> "EntityTextBuilder":
        self._parts.append(text)
        self._offset += utf16_len(text)
        return self

    def add_mention(self, text: str, user_id: int, username: str | None = None) -> "EntityTextBuilder":
        """
        Добавляет имя как кликабельную ссылку на профиль.

        text_mention entity в бизнес-сообщениях часто просто не рендерится
        Telegram-клиентом, поэтому вместо него используем обычную URL-ссылку
        (text_link): на @username, если он есть, иначе на tg://user?id=,
        который открывает профиль по id даже без username.
        """
        start = self._offset
        self.add_text(text)
        url = f"https://t.me/{username}" if username else f"tg://user?id={user_id}"
        self._entities.append(
            MessageEntity(
                type="text_link",
                offset=start,
                length=utf16_len(text),
                url=url,
            )
        )
        return self

    def add_bold(self, text: str) -> "EntityTextBuilder":
        start = self._offset
        self.add_text(text)
        self._entities.append(MessageEntity(type="bold", offset=start, length=utf16_len(text)))
        return self

    def add_code(self, text: str) -> "EntityTextBuilder":
        start = self._offset
        self.add_text(text)
        self._entities.append(MessageEntity(type="code", offset=start, length=utf16_len(text)))
        return self

    def add_custom_emoji(self, placeholder: str, custom_emoji_id: str | None) -> "EntityTextBuilder":
        start = self._offset
        self.add_text(placeholder)
        if custom_emoji_id:
            self._entities.append(
                MessageEntity(
                    type="custom_emoji",
                    offset=start,
                    length=utf16_len(placeholder),
                    custom_emoji_id=custom_emoji_id,
                )
            )
        return self

    def add_emoji_sequence(self, emojis: list[tuple[str, str | None]]) -> "EntityTextBuilder":
        """
        Добавляет несколько эмодзи подряд без пробелов между ними
        (например несколько премиум-эмодзи одно за другим в наборе для действия),
        каждый — со своей custom_emoji entity, если id указан.
        """
        for placeholder, custom_emoji_id in emojis:
            self.add_custom_emoji(placeholder, custom_emoji_id)
        return self

    def build(self) -> tuple[str, list[MessageEntity]]:
        return "".join(self._parts), self._entities
