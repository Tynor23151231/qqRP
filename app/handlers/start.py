from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.keyboards.gender import gender_keyboard
from app.keyboards.menu import back_only_keyboard, main_menu_keyboard, with_back_button
from app.keyboards.profile import profile_keyboard
from app.keyboards.settings import settings_keyboard
from app.models import Gender, User
from app.services.action_service import ActionService
from app.services.user_service import UserService

router = Router(name="start")

ONBOARDING_TEXT = (
    "👋 <b>Привет! Это qqRP Bot.</b>\n\n"
    "Я умею красиво оформлять RP-действия по коротким командам с точкой — "
    f"например <code>{settings.command_prefix}муа</code>, <code>{settings.command_prefix}обнять</code>, "
    f"<code>{settings.command_prefix}цветы</code>.\n\n"
    "<b>Как это работает:</b>\n"
    "1️⃣ Подключаешь меня как Telegram Business Bot к своему аккаунту\n"
    "2️⃣ Пишешь в любом чате (личном или группе) команду вида "
    f"<code>{settings.command_prefix}муа</code> (в ответ на сообщение человека, "
    "или с <code>@username</code> после команды)\n"
    "3️⃣ Я удаляю твоё сообщение-команду и отправляю красивое RP-действие "
    "с кликабельными именами вместо него\n\n"
    "Для начала выбери свой пол — это нужно, чтобы правильно склонять действия "
    "(«поцеловал» / «поцеловала»):"
)

_HOWTO_TEXT = (
    "📲 <b>Как подключить Telegram Business</b>\n\n"
    "Нужен Telegram Premium — без него бизнес-функции недоступны.\n\n"
    "1. Открой <b>Настройки</b> → <b>Telegram для бизнеса</b> → <b>Чат-боты</b>\n"
    "2. Введи имя этого бота и подключи его\n"
    "3. Обязательно включи права:\n"
    "   • <b>Читать сообщения</b>\n"
    "   • <b>Отправлять сообщения</b>\n"
    "   • <b>Удалять отправленные сообщения</b> ⚠️ без этого права команды "
    "не будут удаляться после срабатывания\n\n"
    "После подключения просто пиши команды вроде "
    f"<code>{settings.command_prefix}муа</code> в любом чате — я отвечу от твоего имени."
)


def _format_commands_list(action_service: ActionService) -> str:
    lines = ["📋 <b>Список команд</b>\n", "Пиши в чате в ответ на сообщение человека или с @username:\n"]
    for key, aliases, emoji in sorted(action_service.builtin_display_list(), key=lambda x: x[0]):
        names = f"{settings.command_prefix}{key}"
        if aliases:
            names += " / " + " / ".join(f"{settings.command_prefix}{a}" for a in aliases)
        lines.append(f"{emoji} <code>{names}</code>")
    lines.append(
        "\n➕ Плюс можно создать свои действия через <code>/addrp</code> (премиум)."
    )
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User) -> None:
    if db_user.is_configured:
        await message.answer(
            f"С возвращением, {db_user.display_name}! 👋",
            reply_markup=main_menu_keyboard(db_user),
        )
        return

    await message.answer(ONBOARDING_TEXT, reply_markup=gender_keyboard())


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User) -> None:
    await message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(db_user))


@router.callback_query(F.data.startswith("gender:"))
async def on_gender_chosen(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    gender_value = callback.data.split(":", 1)[1]
    gender = Gender.MALE if gender_value == "male" else Gender.FEMALE

    service = UserService(session)
    await service.set_gender(db_user, gender)

    label = "Мужчина 👨" if gender == Gender.MALE else "Женщина 👩"
    await callback.message.edit_text(
        f"Готово! Пол установлен: <b>{label}</b>.\n\n"
        "Осталось подключить меня как Telegram Business Bot — жми «📲 Как подключить Business» ниже, "
        f"а потом пробуй команды вроде <code>{settings.command_prefix}муа</code> в ответ на сообщение.",
        reply_markup=main_menu_keyboard(db_user),
    )
    await callback.answer("Пол сохранён")


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, db_user: User) -> None:
    await callback.message.edit_text("🏠 <b>Главное меню</b>", reply_markup=main_menu_keyboard(db_user))
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.profile import _format_profile  # локальный импорт во избежание циклов

    service = UserService(session)
    stats = await service.get_stats(db_user)
    favorite = stats["favorite"] or "ещё нет"

    text = _format_profile(db_user) + f"Любимое действие: {favorite}"
    await callback.message.edit_text(text, reply_markup=with_back_button(profile_keyboard()))
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery, db_user: User) -> None:
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>", reply_markup=with_back_button(settings_keyboard(db_user))
    )
    await callback.answer()


@router.callback_query(F.data == "menu:commands")
async def cb_menu_commands(callback: CallbackQuery, session: AsyncSession) -> None:
    action_service = ActionService(session)
    await callback.message.edit_text(
        _format_commands_list(action_service), reply_markup=back_only_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "menu:howto")
async def cb_menu_howto(callback: CallbackQuery) -> None:
    await callback.message.edit_text(_HOWTO_TEXT, reply_markup=back_only_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:addrp")
async def cb_menu_addrp(callback: CallbackQuery, db_user: User) -> None:
    if db_user.has_premium:
        text = (
            "➕ <b>Своё RP-действие</b>\n\n"
            "Отправь команду /addrp прямо сюда в чат — я по шагам спрошу триггер-слово, "
            "эмодзи и текст действия."
        )
    else:
        text = (
            "🔒 <b>Создание своих RP-действий — премиум-функция.</b>\n\n"
            f"За {settings.premium_price_stars} ⭐️ на {settings.premium_duration_days} дней "
            "открываются собственные команды через <code>/addrp</code> и <code>.typing</code>.\n\n"
            "Оформить можно на кнопке «💎 Премиум» в меню."
        )
    await callback.message.edit_text(text, reply_markup=back_only_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:premium")
async def cb_menu_premium(callback: CallbackQuery, db_user: User) -> None:
    from app.handlers.premium import _buy_keyboard, _status_text  # локальный импорт во избежание циклов

    await callback.message.edit_text(_status_text(db_user), reply_markup=with_back_button(_buy_keyboard()))
    await callback.answer()
