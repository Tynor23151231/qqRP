from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path

from aiogram.types import MessageEntity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CustomTrigger, Gender, User
from app.utils.entity_builder import EntityTextBuilder, utf16_len

_ACTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "actions.json"
_TOKEN_RE = re.compile(r"\{(user|target|verb|emoji)\}")


@dataclass(frozen=True)
class RenderedAction:
    text: str
    entities: list[MessageEntity]


class ActionService:
    """
    Единая точка входа для всей логики RP-действий:
    - хранит встроенные действия (загружены один раз из JSON при старте);
    - умеет находить пользовательские триггеры в БД;
    - рендерит итоговое красивое сообщение с учётом пола и настроек пользователя.

    Добавление нового встроенного действия требует правки только actions.json —
    код сервиса менять не нужно (принцип открытости/закрытости).
    """

    _builtin_actions: dict[str, dict] | None = None

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        if ActionService._builtin_actions is None:
            ActionService._builtin_actions = self._load_builtin_actions()

    @staticmethod
    def _load_builtin_actions() -> dict[str, dict]:
        with _ACTIONS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)

    def is_builtin(self, action_key: str) -> bool:
        return action_key in (ActionService._builtin_actions or {})

    async def get_custom_trigger(self, owner_id: int, action_key: str) -> CustomTrigger | None:
        result = await self.session.execute(
            select(CustomTrigger).where(
                CustomTrigger.owner_id == owner_id,
                CustomTrigger.trigger == action_key,
            )
        )
        return result.scalar_one_or_none()

    async def list_custom_triggers(self, owner_id: int) -> list[CustomTrigger]:
        result = await self.session.execute(
            select(CustomTrigger).where(CustomTrigger.owner_id == owner_id)
        )
        return list(result.scalars().all())

    async def create_custom_trigger(
        self,
        owner: User,
        trigger: str,
        emoji: str,
        template: str,
        custom_emoji_id: str | None = None,
    ) -> CustomTrigger:
        trigger_obj = CustomTrigger(
            owner_id=owner.id,
            trigger=trigger,
            emoji=emoji,
            custom_emoji_id=custom_emoji_id,
            template=template,
        )
        self.session.add(trigger_obj)
        await self.session.commit()
        await self.session.refresh(trigger_obj)
        return trigger_obj

    def _verb_form(self, verb: dict[str, str], gender: Gender) -> str:
        if gender == Gender.FEMALE:
            return verb.get("female", verb.get("male", ""))
        return verb.get("male", verb.get("female", ""))

    def _render_template(
        self,
        template_text: str,
        actor: User,
        target_id: int,
        target_name: str,
        target_username: str | None,
        verb: str | None,
        emoji: str,
        custom_emoji_id: str | None,
    ) -> RenderedAction:
        """Подставляет токены {user}/{target}/{verb}/{emoji} с правильными entity-смещениями."""
        builder = EntityTextBuilder()
        pos = 0
        for match in _TOKEN_RE.finditer(template_text):
            builder.add_text(template_text[pos:match.start()])
            token = match.group(1)
            if token == "user":
                builder.add_mention(actor.display_name, actor.telegram_id, actor.username)
            elif token == "target":
                builder.add_mention(target_name, target_id, target_username)
            elif token == "verb":
                builder.add_text(verb or "")
            elif token == "emoji":
                builder.add_custom_emoji(emoji, custom_emoji_id)
            pos = match.end()
        builder.add_text(template_text[pos:])

        text, entities = builder.build()
        # Эмодзи-префикс действия (для built-in действий, где {emoji} не указан в шаблоне явно)
        if "{emoji}" not in template_text and emoji:
            prefix_builder = EntityTextBuilder()
            prefix_builder.add_custom_emoji(emoji, custom_emoji_id)
            prefix_builder.add_text(" ")
            prefix_text, prefix_entities = prefix_builder.build()
            prefix_len = utf16_len(prefix_text)

            shifted = [
                MessageEntity(
                    type=e.type,
                    offset=e.offset + prefix_len,
                    length=e.length,
                    url=e.url,
                    custom_emoji_id=e.custom_emoji_id,
                )
                for e in entities
            ]
            text = prefix_text + text
            entities = prefix_entities + shifted

        return RenderedAction(text=text, entities=entities)

    async def render(
        self,
        actor: User,
        action_key: str,
        target_id: int,
        target_name: str,
        target_username: str | None = None,
    ) -> RenderedAction | None:
        """
        Возвращает готовый к отправке текст + entities (ссылки на профили, премиум эмодзи)
        либо None, если такого действия не существует ни среди встроенных,
        ни среди пользовательских триггеров actor'а.
        """
        builtin = (ActionService._builtin_actions or {}).get(action_key)
        if builtin is not None:
            templates = builtin["templates"]
            template = random.choice(templates) if actor.random_templates else templates[0]
            verb = self._verb_form(template["verb"], actor.gender)
            return self._render_template(
                template["text"], actor, target_id, target_name, target_username,
                verb=verb, emoji=template["emoji"], custom_emoji_id=None,
            )

        custom = await self.get_custom_trigger(actor.id, action_key)
        if custom is not None:
            return self._render_template(
                custom.template, actor, target_id, target_name, target_username,
                verb=None, emoji=custom.emoji, custom_emoji_id=custom.custom_emoji_id,
            )

        return None

    def builtin_keys(self) -> list[str]:
        return list((ActionService._builtin_actions or {}).keys())
