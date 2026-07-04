from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.keyboards.gender import gender_keyboard
from app.models import Gender, User
from app.services.user_service import UserService

router = Router(name="start")

WELCOME_TEXT = (
    "👋 <b>Добро пожаловать в qqRP Bot!</b>\n\n"
    "Я — твой личный RP-помощник в Telegram Business.\n"
    "После подключения меня к твоему Telegram Premium ты сможешь отправлять "
    "команды вроде <code>.муа</code>, <code>.обнять</code>, <code>.цветы</code> "
    "прямо в личных чатах и группах — а я красиво оформлю действие от твоего имени.\n\n"
    "Для начала выбери свой пол — это нужно для правильного склонения слов:"
)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    if db_user.is_configured:
        await message.answer(
            "С возвращением! Пол уже настроен — используй /profile, чтобы посмотреть профиль, "
            "или /settings, чтобы что-то поменять."
        )
        return

    await message.answer(WELCOME_TEXT, reply_markup=gender_keyboard())


@router.callback_query(F.data.startswith("gender:"))
async def on_gender_chosen(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    gender_value = callback.data.split(":", 1)[1]
    gender = Gender.MALE if gender_value == "male" else Gender.FEMALE

    service = UserService(session)
    await service.set_gender(db_user, gender)

    label = "Мужчина 👨" if gender == Gender.MALE else "Женщина 👩"
    await callback.message.edit_text(
        f"Готово! Пол установлен: <b>{label}</b>.\n\n"
        "Теперь подключи меня как Telegram Business Bot в настройках Telegram, "
        "и можешь пробовать команды вроде <code>.муа</code> в ответ на сообщение."
    )
    await callback.answer("Пол сохранён")
