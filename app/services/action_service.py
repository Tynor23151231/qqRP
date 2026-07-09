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
    gif_file_id: str | None = None


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

    def builtin_display_list(self) -> list[tuple[str, list[str], str, str | None]]:
        """
        Список встроенных действий для показа пользователю:
        (основной_триггер, алиасы, эмодзи-превью, custom_emoji_id).
        Дедуплицирует алиасы (они указывают на тот же объект действия, что и основной ключ).
        """
        actions = ActionService._builtin_actions or {}
        seen: set[int] = set()
        result: list[tuple[str, list[str], str, str | None]] = []
        for key, action in actions.items():
            if id(action) in seen:
                continue
            seen.add(id(action))

            emoji = "✨"
            custom_emoji_id: str | None = None
            mode = action.get("emoji_mode")
            if mode == "fixed" and action.get("emojis"):
                emoji = action["emojis"][0]["emoji"]
                custom_emoji_id = action["emojis"][0].get("id")
            elif mode == "actor_gender" and action.get("by_gender"):
                first_group = next(iter(action["by_gender"].values()), None)
                if first_group:
                    emoji = first_group[0]["emoji"]
                    custom_emoji_id = first_group[0].get("id")
            elif mode == "pair" and action.get("pairs"):
                first_group = next(iter(action["pairs"].values()), None)
                if first_group:
                    emoji = first_group[0]["emoji"]
                    custom_emoji_id = first_group[0].get("id")

            result.append((key, action.get("aliases", []), emoji, custom_emoji_id))

        return result

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

    async def get_custom_trigger_by_id(self, trigger_id: int) -> CustomTrigger | None:
        return await self.session.get(CustomTrigger, trigger_id)

    async def list_custom_triggers(self, owner_id: int) -> list[CustomTrigger]:
        result = await self.session.execute(
            select(CustomTrigger).where(CustomTrigger.owner_id == owner_id)
        )
        return list(result.scalars().all())

    async def create_custom_trigger(
        self,
        owner: User,
        trigger: str,
        emojis: list[tuple[str, str | None]],
        template: str,
        gif_file_id: str | None = None,
    ) -> CustomTrigger:
        """
        emojis — список (emoji, custom_emoji_id) в порядке добавления. При каждом
        использовании действия случайно выбирается один эмодзи из набора (как и
        у встроенных действий) — премиум-пользователи могут задать сразу несколько.

        gif_file_id — необязательный file_id гифки/видео, которая будет отправляться
        вместе с текстом действия (как подпись к send_animation).

        Если у owner уже есть триггер с таким именем — обновляет его на месте
        (апдейт), а не создаёт дубликат: пользователь может как создавать новые
        действия, так и переопределять/менять существующие (в т.ч. встроенные —
        см. приоритет custom > builtin в render()).
        """
        first_emoji, first_custom_id = emojis[0] if emojis else ("✨", None)
        emojis_json = json.dumps([{"emoji": e, "id": cid} for e, cid in emojis])

        existing = await self.get_custom_trigger(owner.id, trigger)
        if existing is not None:
            existing.emoji = first_emoji
            existing.custom_emoji_id = first_custom_id
            existing.emojis_json = emojis_json
            existing.template = template
            existing.gif_file_id = gif_file_id
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        trigger_obj = CustomTrigger(
            owner_id=owner.id,
            trigger=trigger,
            emoji=first_emoji,
            custom_emoji_id=first_custom_id,
            emojis_json=emojis_json,
            template=template,
            gif_file_id=gif_file_id,
        )
        self.session.add(trigger_obj)
        await self.session.commit()
        await self.session.refresh(trigger_obj)
        return trigger_obj

    async def delete_custom_trigger(self, owner_id: int, trigger: str) -> bool:
        """Удаляет свой триггер. Если он совпадал по имени со встроенным действием —
        поведение автоматически вернётся к встроенному (см. приоритет в render())."""
        existing = await self.get_custom_trigger(owner_id, trigger)
        if existing is None:
            return False
        await self.session.delete(existing)
        await self.session.commit()
        return True

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

        Приоритет: если у actor'а есть СВОЙ триггер с этим именем (в т.ч. совпадающий
        по имени со встроенным действием) — используется он. Так пользователь может
        переопределить даже встроенное действие своим текстом/эмодзи; если он потом
        удалит свой триггер — поведение вернётся к встроенному автоматически.
        """
        custom = await self.get_custom_trigger(actor.id, action_key)
        if custom is not None:
            candidates = self._custom_trigger_emojis(custom)
            emoji_sequence = [random.choice(candidates)] if candidates else []
            rendered = self._render_template(
                custom.template, actor, target_id, target_name, target_username,
                verb=None, emoji_sequence=emoji_sequence,
            )
            return RenderedAction(
                text=rendered.text, entities=rendered.entities, gif_file_id=custom.gif_file_id
            )

        builtin = (ActionService._builtin_actions or {}).get(action_key)
        if builtin is not None:
            if actor.language == "en" and builtin.get("template_en"):
                verb = builtin["verb_en"]
                template = builtin["template_en"]
            else:
                verb = self._verb_form(builtin["verb"], actor.gender)
                template = builtin["template"]
            candidates = await self._select_builtin_emojis(builtin, actor, target_id, keyword)
            emoji_sequence = self._pick_emoji(builtin, candidates)
            return self._render_template(
                template, actor, target_id, target_name, target_username,
                verb=verb, emoji_sequence=emoji_sequence,
            )

        return None

    def _custom_trigger_emojis(self, custom: CustomTrigger) -> list[tuple[str, str | None]]:
        """Читает набор эмодзи пользовательского триггера (JSON), с fallback на старые записи."""
        if custom.emojis_json:
            try:
                items = json.loads(custom.emojis_json)
                candidates = [(item["emoji"], item.get("id")) for item in items]
                if candidates:
                    return candidates
            except (ValueError, KeyError, TypeError):
                pass
        return [(custom.emoji, custom.custom_emoji_id)]
