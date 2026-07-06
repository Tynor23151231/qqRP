from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.services.action_service import ActionService

router = Router(name="custom_rp")

_PAYWALL_TEXT = (
    "🔒 <b>Создание своих РП-действий — премиум-функция</b>\n\n"
    f"За {settings.premium_price_stars} ⭐️ на {settings.premium_duration_days} дней открывается:\n"
    "• создание собственных команд через <code>/addrp</code> (в том числе с несколькими "
    "премиум-эмодзи в одном действии, из которых при каждом использовании случайно "
    "выбирается один)\n"
    "• <code>.typing</code>\n\n"
    "Оформить: /premium"
)


class AddRPStates(StatesGroup):
    waiting_trigger = State()
    waiting_emoji = State()
    waiting_template = State()


@router.message(Command("addrp"))
async def cmd_add_rp(message: Message, state: FSMContext, db_user: User) -> None:
    if not db_user.has_premium:
        await message.answer(_PAYWALL_TEXT)
        return

    await state.set_state(AddRPStates.waiting_trigger)
    await message.answer(
        "✍️ Введи триггер-слово/фразу для нового действия (то, что будет писаться после точки).\n\n"
        "Например: <code>выепать</code>"
    )


@router.message(AddRPStates.waiting_trigger, F.text)
async def on_trigger_entered(message: Message, state: FSMContext) -> None:
    trigger = message.text.strip().lower().lstrip(".")
    if not trigger or " " in trigger:
        await message.answer("Триггер должен быть одним словом без пробелов. Попробуй ещё раз:")
        return

    await state.update_data(trigger=trigger)
    await state.set_state(AddRPStates.waiting_emoji)
    await message.answer(
        "🎨 Отправь один или несколько эмодзи для этого действия одним сообщением "
        "(поддерживаются премиум-эмодзи Telegram — можно вставить сразу несколько подряд, "
        "при каждом использовании действия один из них будет выбираться случайно)."
    )


@router.message(AddRPStates.waiting_emoji)
async def on_emoji_entered(message: Message, state: FSMContext) -> None:
    emojis: list[tuple[str, str | None]] = []

    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                placeholder = message.text[entity.offset:entity.offset + entity.length]
                emojis.append((placeholder, entity.custom_emoji_id))

    if not emojis and message.text:
        # Обычные (не премиум) эмодзи/символы — берём как один вариант без custom_emoji_id.
        fallback = message.text.strip()[:8]
        if fallback:
            emojis = [(fallback, None)]

    if not emojis:
        await message.answer("Не нашёл ни одного эмодзи в сообщении. Пришли ещё раз:")
        return

    await state.update_data(emojis=emojis)
    await state.set_state(AddRPStates.waiting_template)

    data = await state.get_data()
    trigger = data["trigger"]
    count_note = f" (сохранил {len(emojis)} шт., один будет выбираться случайно)" if len(emojis) > 1 else ""
    await message.answer(
        f"Принято{count_note}. 📝 Теперь введи текст действия. Используй <code>{{user}}</code> и "
        "<code>{target}</code> как плейсхолдеры для имён.\n\n"
        f"Например: <code>{{user}} выебал(а) {trigger}а {{target}}</code>"
    )


@router.message(AddRPStates.waiting_template, F.text)
async def on_template_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    if not db_user.has_premium:
        # Премиум мог закончиться прямо во время диалога — перепроверяем перед сохранением.
        await state.clear()
        await message.answer(_PAYWALL_TEXT)
        return

    template = message.text.strip()
    if "{user}" not in template or "{target}" not in template:
        await message.answer(
            "В шаблоне обязательно должны быть <code>{user}</code> и <code>{target}</code>. Попробуй ещё раз:"
        )
        return

    data = await state.get_data()
    action_service = ActionService(session)
    trigger_obj = await action_service.create_custom_trigger(
        owner=db_user,
        trigger=data["trigger"],
        emojis=data["emojis"],
        template=template,
    )
    await state.clear()

    await message.answer(
        f"✅ Готово! Новое действие <code>.{trigger_obj.trigger}</code> добавлено и уже доступно в чатах."
    )
