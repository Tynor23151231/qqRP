from __future__ import annotations

from dataclasses import dataclass, field

from aiogram.types import MessageEntity
from aiogram.types import User as TgUser


def utf16_len(text: str) -> int:
    """
    Telegram считает offset/length сущностей в UTF-16 code units, а не в
    Python-символах. Для большинства кириллических/эмодзи-символов из BMP
    это совпадает с len(), но для эмодзи вне BMP — нет, поэтому считаем честно.
    """
    return len(text.encode("utf-16-le")) // 2


@dataclass
class EntityTextBuilder:
    """
    Собирает финальный plain-текст сообщения вместе со списком MessageEntity
    (упоминания пользователей и премиум-эмодзи), т.к. Bot API не позволяет
    одновременно использовать parse_mode и entities.
    """

    _parts: list[str] = field(default_factory=list)
    _entities: list[MessageEntity] = field(default_factory=list)
    _offset: int = 0

    def add_text(self, text: str) -> "EntityTextBuilder":
        self._parts.append(text)
        self._offset += utf16_len(text)
        return self

    def add_mention(self, text: str, user_id: int, first_name: str) -> "EntityTextBuilder":
        start = self._offset
        self.add_text(text)
        self._entities.append(
            MessageEntity(
                type="text_mention",
                offset=start,
                length=utf16_len(text),
                user=TgUser(id=user_id, is_bot=False, first_name=first_name or "User"),
            )
        )
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

    def build(self) -> tuple[str, list[MessageEntity]]:
        return "".join(self._parts), self._entities
