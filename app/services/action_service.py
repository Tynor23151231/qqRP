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
from app.utils.entity_builder import EntityTextBuilder

_ACTIONS_PATH = Path(__file__).resolve().parent.parent / "data" / "actions.json"
_TOKEN_RE = re.compile(r"\{(user|target|verb)\}")

# ключ для по-парного набора эмодзи: (пол автора, пол цели) -> ключ в JSON "pairs"
_PAIR_KEYS = {
    (Gender.MALE, Gender.FEMALE): "male_female",
    (Gender.FEMALE, Gender.MALE): "female_male",
    (Gender.FEMALE, Gender.FEMALE): "female_female",
    (Gender.MALE, Gender.MALE): "male_male",
}


@dataclass(frozen=True)
class RenderedAction:
    text: str
    entities: list[MessageEntity]


class ActionService:
    """
    Единая точка входа для всей логики RP-действий:
    - хранит встроенные действия (загружены один раз из JSON при старте);
    - умеет находить пользовательские триггеры в БД;
    - подбирает набор премиум-эмодзи в зависимости от пола автора и/или цели;
    - рендерит итоговое сообщение с корректными UTF-16 офсетами для ссылок-упоминаний
      (text_link) и custom_emoji entities (см. app/utils/entity_builder.py).

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
            data: dict[str, dict] = json.load(f)

        # Разворачиваем aliases (например "поцеловать" -> тот же объект, что "муа"),
        # чтобы команда-синоним вела себя абсолютно идентично основной.
        for action in list(data.values()):
            for alias in action.get("aliases", []):
                data[alias] = action

        return data

    def is_builtin(self, action_key: str) -> bool:
        return action_key in (ActionService._builtin_actions or {})

    def builtin_keys(self) -> list[str]:
        return list((ActionService._builtin_actions or {}).keys())

    # ------------------------------------------------------------------ #
    # Пользовательские (custom) триггеры
    # ------------------------------------------------------------------ #

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

    # ------------------------------------------------------------------ #
    # Вспомогательное
    # ------------------------------------------------------------------ #

    def _verb_form(self, verb: dict[str, str], gender: Gender) -> str:
        if gender == Gender.FEMALE:
            return verb.get("female", verb.get("male", ""))
        return verb.get("male", verb.get("female", ""))

    async def _target_gender(self, target_id: int) -> Gender:
        """Пытается определить пол цели, если она уже когда-либо запускала бота."""
        result = await self.session.execute(select(User).where(User.telegram_id == target_id))
        target_user = result.scalar_one_or_none()
        if target_user is None:
            return Gender.UNKNOWN
        return target_user.gender

    def _emoji_list_to_pairs(self, emoji_list: list[dict]) -> list[tuple[str, str | None]]:
        return [(item["emoji"], item.get("id")) for item in emoji_list]

    async def _select_builtin_emojis(
        self, action: dict, actor: User, target_id: int, keyword: str | None
    ) -> list[tuple[str, str | None]]:
        """
        Определяет набор эмодзи-кандидатов для встроенного действия с учётом
        emoji_mode ('pair' | 'actor_gender' | 'fixed') и, если есть,
        keyword_variants (например ".лизь попу" -> отдельный набор эмодзи).

        Из набора кандидатов дальше выбирается ОДИН эмодзи случайно
        (см. _pick_emoji), кроме действий с "sequence_mode": true —
        там показываются все эмодзи набора сразу (например .печенье).
        """
        if keyword and "keyword_variants" in action:
            variant = action["keyword_variants"].get(keyword)
            if variant is not None:
                return self._emoji_list_to_pairs(variant["emojis"])

        mode = action["emoji_mode"]

        if mode == "fixed":
            return self._emoji_list_to_pairs(action["emojis"])

        if mode == "actor_gender":
            by_gender = action["by_gender"]
            key = "female" if actor.gender == Gender.FEMALE else "male"
            return self._emoji_list_to_pairs(by_gender.get(key, by_gender.get("male", [])))

        if mode == "pair":
            target_gender = await self._target_gender(target_id)
            actor_gender = actor.gender if actor.gender != Gender.UNKNOWN else Gender.MALE

            if target_gender == Gender.UNKNOWN:
                # Цель ещё не запускала бота и пол неизвестен — по умолчанию
                # считаем разнополую пару (самый частый случай использования).
                target_gender = Gender.FEMALE if actor_gender == Gender.MALE else Gender.MALE

            pair_key = _PAIR_KEYS.get((actor_gender, target_gender), "male_female")
            return self._emoji_list_to_pairs(action["pairs"].get(pair_key, []))

        return []

    def _pick_emoji(
        self, action: dict, candidates: list[tuple[str, str | None]]
    ) -> list[tuple[str, str | None]]:
        """Случайно выбирает ОДИН эмодзи из кандидатов, если у действия не выставлен sequence_mode."""
        if not candidates:
            return []
        if action.get("sequence_mode"):
            return candidates
        return [random.choice(candidates)]

    def _render_template(
        self,
        template_text: str,
        actor: User,
        target_id: int,
        target_name: str,
        target_username: str | None,
        verb: str | None,
        emoji_sequence: list[tuple[str, str | None]],
    ) -> RenderedAction:
        """Подставляет токены {user}/{target}/{verb} и добавляет эмодзи-префикс с entities."""
        builder = EntityTextBuilder()

        if emoji_sequence:
            builder.add_emoji_sequence(emoji_sequence)
            builder.add_text(" | ")

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
            pos = match.end()
        builder.add_text(template_text[pos:])

        text, entities = builder.build()
        return RenderedAction(text=text, entities=entities)

    # ------------------------------------------------------------------ #
    # Главный метод
    # ------------------------------------------------------------------ #

    async def render(
        self,
        actor: User,
        action_key: str,
        target_id: int,
        target_name: str,
        target_username: str | None = None,
        keyword: str | None = None,
    ) -> RenderedAction | None:
        """
        Возвращает готовый к отправке текст + entities (ссылки на профили, премиум эмодзи)
        либо None, если такого действия не существует ни среди встроенных,
        ни среди пользовательских триггеров actor'а.
        """
        builtin = (ActionService._builtin_actions or {}).get(action_key)
        if builtin is not None:
            verb = self._verb_form(builtin["verb"], actor.gender)
            candidates = await self._select_builtin_emojis(builtin, actor, target_id, keyword)
            emoji_sequence = self._pick_emoji(builtin, candidates)
            return self._render_template(
                builtin["template"], actor, target_id, target_name, target_username,
                verb=verb, emoji_sequence=emoji_sequence,
            )

        custom = await self.get_custom_trigger(actor.id, action_key)
        if custom is not None:
            emoji_sequence = [(custom.emoji, custom.custom_emoji_id)]
            return self._render_template(
                custom.template, actor, target_id, target_name, target_username,
                verb=None, emoji_sequence=emoji_sequence,
            )

        return None
