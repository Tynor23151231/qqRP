from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.gender import gender_keyboard
from app.keyboards.menu import with_back_button
from app.keyboards.profile import profile_keyboard
from app.keyboards.settings import settings_keyboard
from app.models import Gender, User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="profile")


def _format_profile_entities(user: User, favorite: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("profile")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold("Профиль")
    b.add_text(f"\n\nИмя: {user.first_name}\n")
    if user.username:
        b.add_text(f"Username: @{user.username}\n")

    b.add_text("Пол: ")
    if user.gender == Gender.MALE:
        g, gid = emoji("male")
        b.add_custom_emoji(g, gid)
        b.add_text(" Мужчина\n")
    elif user.gender == Gender.FEMALE:
        g, gid = emoji("female")
        b.add_custom_emoji(g, gid)
        b.add_text(" Женщина\n")
    else:
        b.add_text("❔ Не выбран\n")

    reg_date = user.registered_at.strftime("%d.%m.%Y") if user.registered_at else "—"
    b.add_text(f"Использований бота: {user.total_actions}\n")
    b.add_text(f"Дата регистрации: {reg_date}\n")
    b.add_text(f"Любимое действие: {favorite}")
    return b.build()


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User, session: AsyncSession) -> None:
    service = UserService(session)
    stats = await service.get_stats(db_user)
    favorite = stats["favorite"] or "ещё нет"

    text, entities = _format_profile_entities(db_user, favorite)
    await message.answer(
        text, entities=entities, parse_mode=None, reply_markup=with_back_button(profile_keyboard())
    )


@router.callback_query(F.data == "profile:change_gender")
async def cb_change_gender(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Выбери свой пол:", reply_markup=gender_keyboard())
    await callback.answer()


@router.callback_query(F.data == "profile:stats")
async def cb_stats_from_profile(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.stats import format_stats_text  # локальный импорт во избежание циклов

    service = UserService(session)
    stats = await service.get_stats(db_user)
    await callback.message.edit_text(format_stats_text(stats), reply_markup=with_back_button(profile_keyboard()))
    await callback.answer()


@router.callback_query(F.data == "profile:settings")
async def cb_settings_from_profile(callback: CallbackQuery, db_user: User) -> None:
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>", reply_markup=with_back_button(settings_keyboard(db_user))
    )
    await callback.answer()
