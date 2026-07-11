from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.config import settings
from app.services import checker_client

logger = logging.getLogger(__name__)

_ALLOWED_STATUSES = {"member", "administrator", "creator"}


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """
    Проверяет, состоит ли пользователь в обязательном канале (settings.required_channel_id).

    Приоритет: внешний сервис-проверяльщик (если настроен CHECKER_URL/CHECKER_API_KEY),
    иначе — нативная проверка через Bot API (getChatMember).

    Fail-open: если ни один способ не смог проверить членство — пропускаем пользователя,
    а не блокируем регистрацию всем подряд из-за ошибки конфигурации/сети.
    """
    checker_result = await checker_client.check_subscribed(user_id, f"@{settings.required_channel_username}")
    if checker_result is not None:
        return checker_result

    try:
        member = await bot.get_chat_member(chat_id=settings.required_channel_id, user_id=user_id)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning(
            "Не удалось проверить подписку на канал %s для user_id=%s: %s. "
            "Убедись, что бот добавлен в канал как администратор.",
            settings.required_channel_id, user_id, e,
        )
        return True

    return member.status in _ALLOWED_STATUSES


async def notify_channel(bot: Bot, text: str) -> None:
    """Отправляет служебное сообщение в тот же канал (например о новой регистрации)."""
    try:
        await bot.send_message(chat_id=settings.required_channel_id, text=text, parse_mode=None)
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        logger.warning("Не удалось отправить сообщение в канал %s: %s", settings.required_channel_id, e)


def subscription_required_payload(lang: str = "ru") -> tuple[str, list]:
    """Текст+entities для сообщения 'нужна подписка', переиспользуется во всех хендлерах команд."""
    from app.i18n import L  # локальный импорт во избежание циклов
    from app.utils.entity_builder import EntityTextBuilder  # локальный импорт во избежание циклов
    from app.utils.premium_emoji import emoji

    b = EntityTextBuilder()
    glyph, cid = emoji("lock")
    b.add_custom_emoji(glyph, cid)
    b.add_text(
        L(
            lang,
            f" Подпишись на @{settings.required_channel_username}, чтобы пользоваться ботом.",
            f" Subscribe to @{settings.required_channel_username} to use the bot.",
        )
    )
    return b.build()
