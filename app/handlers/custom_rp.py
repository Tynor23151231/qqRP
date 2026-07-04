from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.action_service import ActionService

router = Router(name="custom_rp")


class AddRPStates(StatesGroup):
    waiting_trigger = State()
    waiting_emoji = State()
    waiting_template = State()


@router.message(Command("addrp"))
async def cmd_add_rp(message: Message, state: FSMContext) -> None:
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
        "🎨 Отправь эмодзи для этого действия (поддерживается премиум-эмодзи Telegram)."
    )


@router.message(AddRPStates.waiting_emoji)
async def on_emoji_entered(message: Message, state: FSMContext) -> None:
    custom_emoji_id: str | None = None
    fallback_emoji = "✨"

    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                custom_emoji_id = entity.custom_emoji_id
                fallback_emoji = message.text[entity.offset:entity.offset + entity.length]
                break

    if custom_emoji_id is None and message.text:
        fallback_emoji = message.text.strip()[:8] or fallback_emoji

    await state.update_data(emoji=fallback_emoji, custom_emoji_id=custom_emoji_id)
    await state.set_state(AddRPStates.waiting_template)

    data = await state.get_data()
    trigger = data["trigger"]
    await message.answer(
        "📝 Теперь введи текст действия. Используй <code>{user}</code> и <code>{target}</code> "
        "как плейсхолдеры для имён.\n\n"
        f"Например: <code>{{user}} выебал(а) {trigger}а {{target}}</code>"
    )


@router.message(AddRPStates.waiting_template, F.text)
async def on_template_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
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
        emoji=data["emoji"],
        template=template,
        custom_emoji_id=data.get("custom_emoji_id"),
    )
    await state.clear()

    await message.answer(
        f"✅ Готово! Новое действие <code>.{trigger_obj.trigger}</code> добавлено и уже доступно в чатах."
    )
