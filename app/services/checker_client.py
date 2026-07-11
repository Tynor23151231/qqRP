from __future__ import annotations

import logging

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=5)


def is_configured() -> bool:
    return bool(settings.checker_url and settings.checker_api_key)


async def check_subscribed(user_id: int, channel: str) -> bool | None:
    """
    Проверка подписки на один канал через внешний сервис-проверяльщик.
    Возвращает None, если сервис не настроен или недоступен (вызывающий код
    должен в этом случае fail-open — не блокировать пользователя).
    """
    if not is_configured():
        return None

    url = f"{settings.checker_url.rstrip('/')}/check"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                url,
                params={"user_id": user_id, "channel": channel},
                headers={"X-API-Key": settings.checker_api_key},
            ) as resp:
                if resp.status != 200:
                    logger.warning("Проверяльщик подписок вернул статус %s для user_id=%s", resp.status, user_id)
                    return None
                data = await resp.json()
                return bool(data.get("subscribed", False))
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.warning("Не удалось достучаться до проверяльщика подписок: %s", e)
        return None


async def check_subscribed_to_all(user_id: int, channels: list[str]) -> bool | None:
    """Проверка подписки сразу на несколько каналов одним запросом. None = сервис недоступен."""
    if not is_configured():
        return None

    url = f"{settings.checker_url.rstrip('/')}/check_many"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(
                url,
                params={"user_id": user_id, "channels": ",".join(channels)},
                headers={"X-API-Key": settings.checker_api_key},
            ) as resp:
                if resp.status != 200:
                    logger.warning("Проверяльщик подписок вернул статус %s для user_id=%s", resp.status, user_id)
                    return None
                data = await resp.json()
                return bool(data.get("all_subscribed", False))
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.warning("Не удалось достучаться до проверяльщика подписок: %s", e)
        return None
