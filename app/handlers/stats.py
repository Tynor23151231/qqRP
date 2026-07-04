from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.user_service import UserService

router = Router(name="stats")


def format_stats_text(stats: dict) -> str:
    total = stats["total"]
    per_action = stats["per_action"]
    favorite = stats["favorite"] or "—"
    last_used = stats["last_used_at"].strftime("%d.%m.%Y %H:%M") if stats["last_used_at"] else "—"

    if not per_action:
        breakdown = "Пока нет ни одного действия."
    else:
        top = sorted(per_action.items(), key=lambda kv: kv[1], reverse=True)
        breakdown = "\n".join(f"  • .{key} — {count}" for key, count in top)

    return (
        "📊 <b>Статистика</b>\n\n"
        f"Всего действий: {total}\n"
        f"Любимое действие: .{favorite}\n"
        f"Последнее использование: {last_used}\n\n"
        f"<b>По действиям:</b>\n{breakdown}"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, db_user: User, session: AsyncSession) -> None:
    service = UserService(session)
    stats = await service.get_stats(db_user)
    await message.answer(format_stats_text(stats))
