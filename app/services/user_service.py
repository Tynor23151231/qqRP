from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActionLog, Gender, User


class UserService:
    """Всё, что связано с созданием, обновлением и статистикой пользователя."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_business_connection_id(self, connection_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.business_connection_id == connection_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username.lstrip("@"))
        )
        return result.scalar_one_or_none()

    async def list_premium_users(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.premium_until.is_not(None)).order_by(User.premium_until.desc())
        )
        return [u for u in result.scalars().all() if u.has_premium]

    async def get_or_create(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None,
    ) -> tuple[User, bool]:
        """Возвращает (user, created) — создаёт запись при первом обращении."""
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            # обновляем имя/username, если они изменились в Telegram
            changed = False
            if user.first_name != first_name:
                user.first_name = first_name
                changed = True
            if user.username != username:
                user.username = username
                changed = True
            if changed:
                await self.session.commit()
            return user, False

        user = User(telegram_id=telegram_id, first_name=first_name, username=username)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def set_gender(self, user: User, gender: Gender) -> None:
        user.gender = gender
        await self.session.commit()

    async def set_referrer(self, user: User, referrer_telegram_id: int) -> bool:
        """
        Привязывает нового пользователя к пригласившему (по deep-link /start<id>).
        Срабатывает только один раз для нового пользователя и не даёт указать себя же.
        """
        if user.invited_by_id is not None:
            return False
        if referrer_telegram_id == user.telegram_id:
            return False

        user.invited_by_id = referrer_telegram_id
        await self.session.commit()
        return True

    REFERRAL_THRESHOLD = 10
    REFERRAL_REWARD_DAYS = 7

    async def register_referral_completion(self, referrer: User) -> bool:
        """
        Вызывается, когда приглашённый им человек первый раз выбрал пол (т.е. реально
        начал пользоваться ботом, а не просто нажал /start). Увеличивает счётчик
        рефералов; если достигнут порог и награда ещё не выдавалась — выдаёт её
        (одноразовая акция) и возвращает True.
        """
        referrer.referral_count += 1

        reward_granted = False
        if referrer.referral_count >= self.REFERRAL_THRESHOLD and not referrer.referral_reward_claimed:
            await self.grant_premium(referrer, self.REFERRAL_REWARD_DAYS)
            referrer.referral_reward_claimed = True
            referrer.discount_pending = True
            reward_granted = True

        await self.session.commit()
        return reward_granted

    async def consume_discount(self, user: User) -> None:
        user.discount_pending = False
        await self.session.commit()

    async def set_custom_name(self, user: User, custom_name: str | None) -> None:
        user.custom_name = custom_name
        await self.session.commit()

    async def set_business_connection(self, user: User, connection_id: str | None) -> None:
        user.business_connection_id = connection_id
        await self.session.commit()

    async def grant_premium(self, user: User, days: int, extend: bool = True) -> dt.datetime:
        """
        Выдаёт/продлевает премиум на `days` дней от текущего момента.
        Если extend=True и подписка ещё активна — продлеваем от даты её окончания
        (а не от "сейчас"), чтобы повторная покупка не пропадала впустую.
        """
        now = dt.datetime.now(dt.timezone.utc)
        base = now
        if extend and user.has_premium and user.premium_until is not None:
            base = user.premium_until
            if base.tzinfo is None:
                base = base.replace(tzinfo=dt.timezone.utc)

        user.premium_until = base + dt.timedelta(days=days)
        await self.session.commit()
        return user.premium_until

    async def revoke_premium(self, user: User) -> None:
        user.premium_until = None
        await self.session.commit()

    async def update_settings(
        self,
        user: User,
        *,
        random_animations: bool | None = None,
        compact_mode: bool | None = None,
        random_templates: bool | None = None,
        language: str | None = None,
    ) -> None:
        if random_animations is not None:
            user.random_animations = random_animations
        if compact_mode is not None:
            user.compact_mode = compact_mode
        if random_templates is not None:
            user.random_templates = random_templates
        if language is not None:
            user.language = language
        await self.session.commit()

    async def register_action_usage(
        self, user: User, action_key: str, target_telegram_id: int | None
    ) -> None:
        """Пишет запись в лог и обновляет агрегаты (счётчик, дата последнего использования)."""
        log = ActionLog(user_id=user.id, action_key=action_key, target_telegram_id=target_telegram_id)
        self.session.add(log)

        user.total_actions += 1
        user.last_used_at = dt.datetime.now(dt.timezone.utc)
        await self.session.commit()

    async def get_stats(self, user: User) -> dict:
        """Считает количество каждого действия и определяет любимое."""
        result = await self.session.execute(
            select(ActionLog.action_key, ActionLog.id).where(ActionLog.user_id == user.id)
        )
        rows = result.all()

        per_action: dict[str, int] = {}
        for action_key, _ in rows:
            per_action[action_key] = per_action.get(action_key, 0) + 1

        favorite = max(per_action, key=per_action.get) if per_action else None

        return {
            "total": user.total_actions,
            "per_action": per_action,
            "favorite": favorite,
            "last_used_at": user.last_used_at,
        }
