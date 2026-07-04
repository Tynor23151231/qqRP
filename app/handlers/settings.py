from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.gender import gender_keyboard
from app.keyboards.settings import settings_keyboard
from app.models import User
from app.services.user_service import UserService

router = Router(name="settings")

_TOGGLE_FIELDS = {"random_animations", "compact_mode", "random_templates"}


@router.message(Command("settings"))
async def cmd_settings(message: Message, db_user: User) -> None:
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_keyboard(db_user))


@router.callback_query(F.data == "settings:change_gender")
async def cb_change_gender(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Выбери свой пол:", reply_markup=gender_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("settings:toggle:"))
async def cb_toggle_setting(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    field = callback.data.split(":", 2)[2]
    if field not in _TOGGLE_FIELDS:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    new_value = not getattr(db_user, field)
    service = UserService(session)
    await service.update_settings(db_user, **{field: new_value})

    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(db_user))
    await callback.answer("Сохранено")


@router.callback_query(F.data == "settings:language")
async def cb_language(callback: CallbackQuery) -> None:
    # Заготовка под мультиязычность — пока поддерживается только русский.
    await callback.answer("Пока доступен только русский язык 🇷🇺", show_alert=True)
