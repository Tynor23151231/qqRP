from __future__ import annotations

import asyncio
import datetime as dt
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

from app.database.base import async_session_maker
from app.i18n import L
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 20 * 60 * 60  # раз в 20 часов, награда всё равно одноразовая
_THRESHOLD = dt.timedelta(days=3)


def _congrats_payload(lang: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    g1, gid1 = emoji("party")
    b.add_bold(L(lang, "ПОЗДРАВЛЯЕМ", "CONGRATULATIONS"))
    b.add_text(" ")
    b.add_custom_emoji(g1, gid1)
    b.add_text(
        L(
            lang,
            "\n\nТы пользуешься подключённым Business Bot уже 3 дня — и получаешь в подарок "
            "5 дней Премиум+!\nВсе свои RP-действия, созданные за это время, останутся с тобой "
            "навсегда, даже после окончания срока. ",
            "\n\nYou've had the Business Bot connected for 3 days now — here's 5 days of "
            "Premium+ as a gift!\nAny custom RP actions you create during this time stay yours "
            "forever, even after it ends. ",
        )
    )
    g2, gid2 = emoji("flex")
    b.add_custom_emoji(g2, gid2)
    b.add_text(
        L(
            lang,
            "\n\nА ещё специально для тебя — скидка 50% на Премиум+ (обычно "
            "99 ⭐️). Успей воспользоваться в течение недели, потом она сгорит!",
            "\n\nAnd there's also a 50% discount on Premium+ (normally 99 ⭐️) just for you. "
            "Use it within a week, before it expires!",
        )
    )
    return b.build()


async def _check_once(bot: Bot) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    threshold = now - _THRESHOLD

    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(
                User.business_connection_id.is_not(None),
                User.business_connected_at.is_not(None),
                User.business_connected_at <= threshold,
                User.weekly_reward_claimed.is_(False),
            )
        )
        eligible = list(result.scalars().all())
        if not eligible:
            return

        service = UserService(session)
        for user in eligible:
            await service.grant_weekly_reward(user)
            text, entities = _congrats_payload(user.language)
            try:
                await bot.send_message(chat_id=user.telegram_id, text=text, entities=entities, parse_mode=None)
            except TelegramForbiddenError:
                pass  # пользователь заблокировал бота — награда всё равно засчитана
            except Exception:
                logger.exception(
                    "Не удалось отправить сообщение о еженедельной награде user_id=%s", user.telegram_id
                )


async def run_weekly_reward_loop(bot: Bot) -> None:
    """Фоновая задача: раз в _CHECK_INTERVAL_SECONDS проверяет, кому пора выдать награду."""
    while True:
        try:
            await _check_once(bot)
        except Exception:
            logger.exception("Ошибка в цикле еженедельной награды")
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
