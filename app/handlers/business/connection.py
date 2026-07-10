from __future__ import annotations

import datetime as dt

from aiogram import Router
from aiogram.types import BusinessConnection
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.user_service import UserService

router = Router(name="business_connection")


@router.business_connection()
async def on_business_connection(
    connection: BusinessConnection, db_user: User, session: AsyncSession
) -> None:
    """Сохраняет / очищает business_connection_id владельца при подключении и отключении."""
    service = UserService(session)
    connection_id = connection.id if connection.is_enabled else None
    await service.set_business_connection(db_user, connection_id)

    if connection.is_enabled and db_user.business_connected_at is None:
        # Фиксируем момент первого подключения — от него считаем 3 дня до награды.
        db_user.business_connected_at = dt.datetime.now(dt.timezone.utc)
        await session.commit()

    can_edit_name = bool(connection.rights and connection.rights.can_edit_name)
    # Оригинал имени/фамилии обновляем, только если у нас ещё не включён значок —
    # иначе затрём "оригинал" уже изменённым нами именем при повторном событии.
    if not db_user.name_badge_enabled:
        await service.update_name_badge_source(
            db_user, can_edit_name, connection.user.first_name, connection.user.last_name
        )
    else:
        await service.update_name_badge_source(db_user, can_edit_name, None, None, only_right=True)
