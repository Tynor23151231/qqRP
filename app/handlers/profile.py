from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import L
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
    lang = user.language
    b = EntityTextBuilder()
    glyph, cid = emoji("profile")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold(L(lang, "Профиль", "Profile"))
    b.add_text(f"\n\n{L(lang, 'Имя', 'Name')}: {user.first_name}\n")
    if user.username:
        b.add_text(f"Username: @{user.username}\n")

    b.add_text(f"{L(lang, 'Пол', 'Gender')}: ")
    if user.gender == Gender.MALE:
        g, gid = emoji("male")
        b.add_custom_emoji(g, gid)
        b.add_text(f" {L(lang, 'Мужчина', 'Man')}\n")
    elif user.gender == Gender.FEMALE:
        g, gid = emoji("female")
        b.add_custom_emoji(g, gid)
        b.add_text(f" {L(lang, 'Женщина', 'Woman')}\n")
    else:
        b.add_text(f"❔ {L(lang, 'Не выбран', 'Not set')}\n")

    reg_date = user.registered_at.strftime("%d.%m.%Y") if user.registered_at else "—"
    b.add_text(f"{L(lang, 'Использований бота', 'Bot uses')}: {user.total_actions}\n")
    b.add_text(f"{L(lang, 'Дата регистрации', 'Registered on')}: {reg_date}\n")
    b.add_text(f"{L(lang, 'Любимое действие', 'Favorite action')}: {favorite}")
    return b.build()


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    service = UserService(session)
    stats = await service.get_stats(db_user)
    favorite = stats["favorite"] or L(lang, "ещё нет", "none yet")

    text, entities = _format_profile_entities(db_user, favorite)
    await message.answer(
        text, entities=entities, parse_mode=None, reply_markup=with_back_button(profile_keyboard(lang), lang)
    )


@router.callback_query(F.data == "profile:change_gender")
async def cb_change_gender(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    await callback.message.edit_text(
        L(lang, "Выбери свой пол:", "Choose your gender:"), reply_markup=gender_keyboard(lang)
    )
    await callback.answer()


@router.callback_query(F.data == "profile:stats")
async def cb_stats_from_profile(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.stats import format_stats_text  # локальный импорт во избежание циклов

    lang = db_user.language
    service = UserService(session)
    stats = await service.get_stats(db_user)
    await callback.message.edit_text(
        format_stats_text(stats, lang), reply_markup=with_back_button(profile_keyboard(lang), lang)
    )
    await callback.answer()


@router.callback_query(F.data == "profile:settings")
async def cb_settings_from_profile(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    await callback.message.edit_text(
        L(lang, "⚙️ <b>Настройки</b>", "⚙️ <b>Settings</b>"),
        reply_markup=with_back_button(settings_keyboard(db_user), lang),
    )
    await callback.answer()
