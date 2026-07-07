from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.keyboards.menu import back_to_menu_row
from app.models import CustomTrigger, User
from app.services.action_service import ActionService
from app.services.subscription_service import is_subscribed, subscription_required_payload
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="custom_rp")


def _paywall_payload() -> tuple[str, list]:
    b = EntityTextBuilder()
    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold("Создание своих РП-действий — премиум-функция")
    b.add_text(
        f"\n\nЗа {settings.premium_price_stars} ⭐️ на {settings.premium_duration_days} дней открывается:\n"
        "• создание собственных команд через "
    )
    b.add_code("/addrp")
    b.add_text(
        " (в том числе с несколькими премиум-эмодзи и своей гифкой в одном действии, из которых "
        "при каждом использовании случайно выбирается один эмодзи)\n"
        "• своё действие может переопределить даже встроенную команду (например свой "
    )
    b.add_code(f"{settings.command_prefix}муа")
    b.add_text(" вместо стандартного) — удалишь своё, вернётся встроенное\n• ")
    b.add_code(f"{settings.command_prefix}typing")
    b.add_text("\n\nОформить: ")
    b.add_code("/premium")
    return b.build()


async def _my_rp_list_payload(db_user: User, session: AsyncSession) -> tuple[str, list]:
    action_service = ActionService(session)
    triggers = await action_service.list_custom_triggers(db_user.id)

    b = EntityTextBuilder()
    g, gid = emoji("addrp")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold("Свои RP-действия")

    if not triggers:
        b.add_text("\n\nПока не создано ни одного своего действия.")
    else:
        b.add_text("\n\n")
        for t in triggers:
            is_override = action_service.is_builtin(t.trigger)
            b.add_text(f"{t.emoji} ")
            b.add_code(f"{settings.command_prefix}{t.trigger}")
            if t.gif_file_id:
                b.add_text(" 🎬")
            if is_override:
                b.add_text(" (переопределяет встроенное)")
            b.add_text("\n")

    return b.build()


def _my_rp_keyboard(triggers: list[CustomTrigger]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in triggers:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ .{t.trigger}", callback_data=f"myrp:edit:{t.trigger}"
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"myrp:delete:{t.trigger}", style="danger"
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Создать новое", callback_data="myrp:new", icon_custom_emoji_id=emoji("addrp")[1]
            )
        ]
    )
    rows.append(back_to_menu_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def my_rp_screen(
    db_user: User, session: AsyncSession
) -> tuple[str, list, InlineKeyboardMarkup]:
    """Единая точка входа для экрана «Своё RP» — используется и из /addrp, и из меню."""
    if not db_user.has_premium:
        text, entities = _paywall_payload()
        return text, entities, InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row()])

    action_service = ActionService(session)
    triggers = await action_service.list_custom_triggers(db_user.id)
    text, entities = await _my_rp_list_payload(db_user, session)
    return text, entities, _my_rp_keyboard(triggers)


class AddRPStates(StatesGroup):
    waiting_trigger = State()
    waiting_emoji = State()
    waiting_template = State()
    waiting_gif = State()


def _wizard_keyboard(*, skip: bool, back: bool) -> InlineKeyboardMarkup | None:
    row: list[InlineKeyboardButton] = []
    if skip:
        row.append(InlineKeyboardButton(text="Пропустить", callback_data="addrp:skip_gif"))
    if back:
        row.append(
            InlineKeyboardButton(
                text="Назад", callback_data="addrp:back", icon_custom_emoji_id=emoji("back")[1]
            )
        )
    if not row:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def _prompt_trigger(message: Message, state: FSMContext) -> None:
    await state.set_state(AddRPStates.waiting_trigger)
    await message.answer(
        "✍️ Введи триггер-слово/фразу для действия (то, что будет писаться после точки).\n\n"
        "Если укажешь слово уже существующего своего действия или даже встроенной команды "
        "(например <code>муа</code>) — оно будет переопределено этим новым.\n\n"
        "Например: <code>выепать</code>",
        reply_markup=_wizard_keyboard(skip=False, back=False),
    )


async def _prompt_emoji(message: Message, state: FSMContext, trigger: str, editing: bool) -> None:
    await state.set_state(AddRPStates.waiting_emoji)
    prefix = f"✏️ Редактируем <code>{settings.command_prefix}{trigger}</code>.\n\n" if editing else ""
    await message.answer(
        f"{prefix}🎨 Отправь один или несколько эмодзи для этого действия одним сообщением "
        "(поддерживаются премиум-эмодзи Telegram — можно вставить сразу несколько подряд, "
        "при каждом использовании действия один из них будет выбираться случайно).",
        reply_markup=_wizard_keyboard(skip=False, back=True),
    )


async def _prompt_template(message: Message, state: FSMContext, trigger: str) -> None:
    await state.set_state(AddRPStates.waiting_template)
    await message.answer(
        "📝 Теперь введи текст действия. Используй <code>{user}</code> и <code>{target}</code> "
        "как плейсхолдеры для имён.\n\n"
        f"Например: <code>{{user}} выебал(а) {trigger}а {{target}}</code>",
        reply_markup=_wizard_keyboard(skip=False, back=True),
    )


async def _prompt_gif(message: Message, state: FSMContext) -> None:
    await state.set_state(AddRPStates.waiting_gif)
    await message.answer(
        "🎬 Хочешь прикрепить гифку/видео к этому действию? Она будет отправляться вместе с "
        "текстом (текст станет подписью под гифкой).\n\n"
        "Пришли гифку/видео одним сообщением, или нажми «Пропустить», если гифка не нужна.",
        reply_markup=_wizard_keyboard(skip=True, back=True),
    )


async def _save_trigger(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession, gif_file_id: str | None
) -> None:
    data = await state.get_data()
    action_service = ActionService(session)
    trigger_obj = await action_service.create_custom_trigger(
        owner=db_user,
        trigger=data["trigger"],
        emojis=data["emojis"],
        template=data["template"],
        gif_file_id=gif_file_id,
    )
    await state.clear()

    override_note = (
        " Оно переопределяет встроенную команду — если удалишь своё, вернётся стандартное поведение."
        if action_service.is_builtin(trigger_obj.trigger)
        else ""
    )
    gif_note = " С гифкой." if gif_file_id else ""
    await message.answer(
        f"✅ Готово! Действие <code>{settings.command_prefix}{trigger_obj.trigger}</code> "
        f"сохранено и уже доступно в чатах.{gif_note}{override_note}"
    )


@router.message(Command("addrp"))
async def cmd_add_rp(message: Message, state: FSMContext, db_user: User) -> None:
    if not await is_subscribed(message.bot, message.from_user.id):
        text, entities = subscription_required_payload()
        await message.answer(text, entities=entities, parse_mode=None)
        return

    if not db_user.has_premium:
        text, entities = _paywall_payload()
        await message.answer(text, entities=entities, parse_mode=None)
        return

    await state.update_data(editing=False)
    await _prompt_trigger(message, state)


@router.callback_query(F.data == "myrp:new")
async def cb_myrp_new(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not await is_subscribed(callback.bot, callback.from_user.id):
        text, entities = subscription_required_payload()
        await callback.answer()
        await callback.message.answer(text, entities=entities, parse_mode=None)
        return
    if not db_user.has_premium:
        await callback.answer("Нужен премиум", show_alert=True)
        return
    await callback.answer()
    await state.update_data(editing=False)
    await _prompt_trigger(callback.message, state)


@router.callback_query(F.data.startswith("myrp:edit:"))
async def cb_myrp_edit(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    trigger = callback.data.split(":", 2)[2]
    await state.update_data(trigger=trigger, editing=True)
    await callback.answer()
    await _prompt_emoji(callback.message, state, trigger, editing=True)


@router.callback_query(F.data.startswith("myrp:delete:"))
async def cb_myrp_delete(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    trigger = callback.data.split(":", 2)[2]
    action_service = ActionService(session)
    deleted = await action_service.delete_custom_trigger(db_user.id, trigger)

    if deleted:
        note = " Встроенное действие с этим именем снова активно." if action_service.is_builtin(trigger) else ""
        await callback.answer(f"Удалено.{note}", show_alert=True)
    else:
        await callback.answer("Уже удалено", show_alert=True)

    text, entities, keyboard = await my_rp_screen(db_user, session)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)


@router.callback_query(F.data == "addrp:back")
async def cb_addrp_back(
    callback: CallbackQuery, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    await callback.answer()
    current = await state.get_state()
    data = await state.get_data()
    trigger = data.get("trigger", "")
    editing = data.get("editing", False)

    if current == AddRPStates.waiting_gif.state:
        await _prompt_template(callback.message, state, trigger)
    elif current == AddRPStates.waiting_template.state:
        await _prompt_emoji(callback.message, state, trigger, editing)
    elif current == AddRPStates.waiting_emoji.state:
        if editing:
            await state.clear()
            text, entities, keyboard = await my_rp_screen(db_user, session)
            await callback.message.answer(text, entities=entities, parse_mode=None, reply_markup=keyboard)
        else:
            await _prompt_trigger(callback.message, state)
    elif current == AddRPStates.waiting_trigger.state:
        await state.clear()
        text, entities, keyboard = await my_rp_screen(db_user, session)
        await callback.message.answer(text, entities=entities, parse_mode=None, reply_markup=keyboard)


@router.callback_query(F.data == "addrp:skip_gif")
async def cb_addrp_skip_gif(
    callback: CallbackQuery, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    await callback.answer()
    await _save_trigger(callback.message, state, db_user, session, gif_file_id=None)


@router.message(AddRPStates.waiting_trigger, F.text)
async def on_trigger_entered(message: Message, state: FSMContext) -> None:
    trigger = message.text.strip().lower().lstrip(".")
    if not trigger or " " in trigger:
        await message.answer("Триггер должен быть одним словом без пробелов. Попробуй ещё раз:")
        return

    await state.update_data(trigger=trigger)
    await _prompt_emoji(message, state, trigger, editing=False)


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

    data = await state.get_data()
    trigger = data["trigger"]
    count_note = f" (сохранил {len(emojis)} шт., один будет выбираться случайно)" if len(emojis) > 1 else ""
    await message.answer(f"Принято{count_note}.")
    await _prompt_template(message, state, trigger)


@router.message(AddRPStates.waiting_template, F.text)
async def on_template_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    if not db_user.has_premium:
        # Премиум мог закончиться прямо во время диалога — перепроверяем перед сохранением.
        await state.clear()
        text, entities = _paywall_payload()
        await message.answer(text, entities=entities, parse_mode=None)
        return

    template = message.text.strip()
    if "{user}" not in template or "{target}" not in template:
        await message.answer(
            "В шаблоне обязательно должны быть <code>{user}</code> и <code>{target}</code>. Попробуй ещё раз:"
        )
        return

    await state.update_data(template=template)
    await _prompt_gif(message, state)


@router.message(AddRPStates.waiting_gif)
async def on_gif_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    file_id: str | None = None
    if message.animation:
        file_id = message.animation.file_id
    elif message.video:
        file_id = message.video.file_id
    elif message.video_note:
        file_id = message.video_note.file_id
    elif message.document:
        file_id = message.document.file_id

    if not file_id:
        await message.answer(
            "Это не похоже на гифку/видео. Пришли гифку/видео одним сообщением, "
            "или нажми «Пропустить»:",
            reply_markup=_wizard_keyboard(skip=True, back=True),
        )
        return

    await _save_trigger(message, state, db_user, session, gif_file_id=file_id)
