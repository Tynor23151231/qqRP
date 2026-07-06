from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.gender import gender_keyboard
from app.keyboards.menu import with_back_button
from app.keyboards.settings import settings_keyboard
from app.models import User
from app.services.user_service import UserService

router = Router(name="settings")

_TOGGLE_FIELDS = {"random_animations", "compact_mode", "random_templates"}
_MAX_NAME_LEN = 64


class ChangeNameStates(StatesGroup):
    waiting_name = State()


@router.message(Command("settings"))
async def cmd_settings(message: Message, db_user: User) -> None:
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=with_back_button(settings_keyboard(db_user)))


@router.callback_query(F.data == "settings:change_gender")
async def cb_change_gender(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Выбери свой пол:", reply_markup=gender_keyboard())
    await callback.answer()


@router.callback_query(F.data == "settings:change_name")
async def cb_change_name(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ChangeNameStates.waiting_name)
    await callback.message.answer(
        "✏️ Напиши имя, которое будет показываться в RP-сообщениях вместо твоего имени "
        "из Telegram. Клик по нему в сообщении по-прежнему будет вести на твой профиль.\n\n"
        "Чтобы вернуть имя из Telegram — отправь /reset_name."
    )
    await callback.answer()


@router.message(Command("reset_name"))
async def cmd_reset_name(message: Message, db_user: User, session: AsyncSession) -> None:
    service = UserService(session)
    await service.set_custom_name(db_user, None)
    await message.answer("✅ Имя сброшено на стандартное из Telegram.")


@router.message(ChangeNameStates.waiting_name, F.text)
async def on_name_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    name = message.text.strip()
    if not name or len(name) > _MAX_NAME_LEN:
        await message.answer(f"Имя должно быть от 1 до {_MAX_NAME_LEN} символов. Попробуй ещё раз:")
        return

    service = UserService(session)
    await service.set_custom_name(db_user, name)
    await state.clear()
    await message.answer(f"✅ Готово! Теперь в RP-сообщениях ты будешь фигурировать как «{name}».")


@router.callback_query(F.data.startswith("settings:toggle:"))
async def cb_toggle_setting(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    field = callback.data.split(":", 2)[2]
    if field not in _TOGGLE_FIELDS:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    new_value = not getattr(db_user, field)
    service = UserService(session)
    await service.update_settings(db_user, **{field: new_value})

    await callback.message.edit_reply_markup(reply_markup=with_back_button(settings_keyboard(db_user)))
    await callback.answer("Сохранено")


@router.callback_query(F.data == "settings:language")
async def cb_language(callback: CallbackQuery) -> None:
    # Заготовка под мультиязычность — пока поддерживается только русский.
    await callback.answer("Пока доступен только русский язык 🇷🇺", show_alert=True)
