from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import L
from app.keyboards.menu import back_only_keyboard
from app.models import User
from app.services.user_service import UserService

router = Router(name="stats")


def format_stats_text(stats: dict, lang: str = "ru") -> str:
    total = stats["total"]
    per_action = stats["per_action"]
    favorite = stats["favorite"] or "—"
    last_used = stats["last_used_at"].strftime("%d.%m.%Y %H:%M") if stats["last_used_at"] else "—"

    if not per_action:
        breakdown = L(lang, "Пока нет ни одного действия.", "No actions yet.")
    else:
        top = sorted(per_action.items(), key=lambda kv: kv[1], reverse=True)
        breakdown = "\n".join(f"  • .{key} — {count}" for key, count in top)

    title = L(lang, "📊 <b>Статистика</b>", "📊 <b>Stats</b>")
    total_label = L(lang, "Всего действий", "Total actions")
    favorite_label = L(lang, "Любимое действие", "Favorite action")
    last_used_label = L(lang, "Последнее использование", "Last used")
    breakdown_label = L(lang, "По действиям", "By action")

    return (
        f"{title}\n\n"
        f"{total_label}: {total}\n"
        f"{favorite_label}: .{favorite}\n"
        f"{last_used_label}: {last_used}\n\n"
        f"<b>{breakdown_label}:</b>\n{breakdown}"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message, db_user: User, session: AsyncSession) -> None:
    service = UserService(session)
    stats = await service.get_stats(db_user)
    await message.answer(
        format_stats_text(stats, db_user.language), reply_markup=back_only_keyboard(db_user.language)
    )
