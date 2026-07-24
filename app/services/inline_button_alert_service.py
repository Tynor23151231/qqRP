from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InlineButtonAlert


async def register_alert(
    session: AsyncSession, owner_id: int, business_connection_id: str | None, text: str
) -> int:
    """Сохраняет текст alert-кнопки и возвращает id записи для callback_data вида btnalert:<id>."""
    alert = InlineButtonAlert(
        owner_id=owner_id,
        business_connection_id=business_connection_id,
        text=text[:500],
    )
    session.add(alert)
    await session.flush()
    return alert.id
