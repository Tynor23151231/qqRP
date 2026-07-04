from __future__ import annotations

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
