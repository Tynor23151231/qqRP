from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.gender import gender_keyboard
from app.keyboards.profile import profile_keyboard
from app.keyboards.settings import settings_keyboard
from app.models import Gender, User
from app.services.user_service import UserService

router = Router(name="profile")

_GENDER_LABEL = {
    Gender.MALE: "👨 Мужчина",
    Gender.FEMALE: "👩 Женщина",
    Gender.UNKNOWN: "❔ Не выбран",
}


def _format_profile(user: User) -> str:
    reg_date = user.registered_at.strftime("%d.%m.%Y") if user.registered_at else "—"
    lines = ["👤 <b>Профиль</b>\n", f"Имя: {user.first_name}"]
    if user.username:
        lines.append(f"Username: @{user.username}")
    lines.append(f"Пол: {_GENDER_LABEL[user.gender]}")
    lines.append(f"Использований бота: {user.total_actions}")
    lines.append(f"Дата регистрации: {reg_date}")
    return "\n".join(lines) + "\n"


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User, session: AsyncSession) -> None:
    service = UserService(session)
    stats = await service.get_stats(db_user)
    favorite = stats["favorite"] or "ещё нет"

    text = _format_profile(db_user) + f"Любимое действие: {favorite}"
    await message.answer(text, reply_markup=profile_keyboard())


@router.callback_query(F.data == "profile:change_gender")
async def cb_change_gender(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Выбери свой пол:", reply_markup=gender_keyboard())
    await callback.answer()


@router.callback_query(F.data == "profile:stats")
async def cb_stats_from_profile(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.stats import format_stats_text  # локальный импорт во избежание циклов

    service = UserService(session)
    stats = await service.get_stats(db_user)
    await callback.message.edit_text(format_stats_text(stats))
    await callback.answer()


@router.callback_query(F.data == "profile:settings")
async def cb_settings_from_profile(callback: CallbackQuery, db_user: User) -> None:
    await callback.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=settings_keyboard(db_user))
    await callback.answer()
