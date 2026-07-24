from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.keyboards.menu import back_to_menu_row
from app.models import CustomTrigger, User
from app.services.action_service import ActionService
from app.services.subscription_service import is_subscribed, subscription_required_payload
from app.utils.entity_builder import EntityTextBuilder, utf16_slice
from app.utils.premium_emoji import emoji

router = Router(name="custom_rp")


def _paywall_payload(lang: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Создание своих РП-действий — премиум-функция", "Creating your own RP actions is a premium feature"))
    b.add_text(
        L(
            lang,
            f"\n\nЗа {settings.premium_price_stars} ⭐️ на {settings.premium_duration_days} дней открывается:\n"
            "• создание собственных команд через ",
            f"\n\nFor {settings.premium_price_stars} ⭐️ for {settings.premium_duration_days} days you unlock:\n"
            "• creating your own commands via ",
        )
    )
    b.add_code("/addrp")
    b.add_text(
        L(
            lang,
            " (в том числе с несколькими премиум-эмодзи и своей гифкой в одном действии, из которых "
            "при каждом использовании случайно выбирается один эмодзи)\n"
            "• своё действие может переопределить даже встроенную команду (например свой ",
            " (including several premium emoji and your own GIF in one action, with one emoji "
            "randomly picked each time it's used)\n"
            "• your own action can even override a built-in command (e.g. your own ",
        )
    )
    b.add_code(f"{settings.command_prefix}муа")
    b.add_text(
        L(
            lang,
            " вместо стандартного) — удалишь своё, вернётся встроенное\n• ",
            " instead of the default one) — delete yours and the built-in one comes back\n• ",
        )
    )
    b.add_code(f"{settings.command_prefix}typing")
    b.add_text(L(lang, "\n\nОформить: ", "\n\nGet it: "))
    b.add_code("/premium")
    return b.build()


async def _my_rp_list_payload(db_user: User, session: AsyncSession) -> tuple[str, list]:
    lang = db_user.language
    action_service = ActionService(session)
    triggers = await action_service.list_custom_triggers(db_user.id)

    b = EntityTextBuilder()
    g, gid = emoji("addrp")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Свои RP-действия", "My RP actions"))

    limit = db_user.custom_rp_limit
    if limit is not None:
        b.add_text(L(lang, f" ({len(triggers)}/{limit})", f" ({len(triggers)}/{limit})"))

    if not triggers:
        b.add_text(L(lang, "\n\nПока не создано ни одного своего действия.", "\n\nNo custom actions created yet."))
    else:
        b.add_text("\n\n")
        for t in triggers:
            is_override = action_service.is_builtin(t.trigger)
            for e, eid in action_service._custom_trigger_emojis(t):
                b.add_custom_emoji(e, eid)
            b.add_text(" ")
            b.add_code(f"{settings.command_prefix}{t.trigger}")
            if t.gif_file_id:
                b.add_text(" 🎬")
            if is_override:
                b.add_text(L(lang, " (переопределяет встроенное)", " (overrides built-in)"))
            b.add_text("\n")

    return b.build()


def _my_rp_keyboard(triggers: list[CustomTrigger], lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for t in triggers:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ .{t.trigger}", callback_data=f"myrp:edit:{t.trigger}"
                ),
                InlineKeyboardButton(
                    text=L(lang, "Поделиться", "Share"),
                    callback_data=f"myrp:share:{t.trigger}",
                    icon_custom_emoji_id=emoji("share")[1],
                ),
                InlineKeyboardButton(
                    text=L(lang, "Удалить", "Delete"),
                    callback_data=f"myrp:delete:{t.trigger}",
                    style="danger",
                    icon_custom_emoji_id=emoji("delete")[1],
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L(lang, "Создать новое", "Create new"),
                callback_data="myrp:new",
                icon_custom_emoji_id=emoji("addrp")[1],
            )
        ]
    )
    rows.append(back_to_menu_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def my_rp_screen(
    db_user: User, session: AsyncSession
) -> tuple[str, list, InlineKeyboardMarkup]:
    """Единая точка входа для экрана «Своё RP» — используется и из /addrp, и из меню."""
    lang = db_user.language
    if not db_user.has_premium:
        text, entities = _paywall_payload(lang)
        return text, entities, InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row(lang)])

    action_service = ActionService(session)
    triggers = await action_service.list_custom_triggers(db_user.id)
    text, entities = await _my_rp_list_payload(db_user, session)
    return text, entities, _my_rp_keyboard(triggers, lang)


class AddRPStates(StatesGroup):
    waiting_trigger = State()
    waiting_emoji = State()
    waiting_emoji_mode = State()
    waiting_template = State()
    waiting_gif = State()


def _wizard_keyboard(lang: str, *, skip: bool, back: bool) -> InlineKeyboardMarkup | None:
    row: list[InlineKeyboardButton] = []
    if skip:
        row.append(InlineKeyboardButton(text=L(lang, "Пропустить", "Skip"), callback_data="addrp:skip_gif"))
    if back:
        row.append(
            InlineKeyboardButton(
                text=L(lang, "Назад", "Back"), callback_data="addrp:back", icon_custom_emoji_id=emoji("back")[1]
            )
        )
    if not row:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def _prompt_trigger(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AddRPStates.waiting_trigger)
    await message.answer(
        L(
            lang,
            "✍️ Введи триггер-слово/фразу для действия (то, что будет писаться после точки).\n\n"
            "Если укажешь слово уже существующего своего действия или даже встроенной команды "
            "(например <code>муа</code>) — оно будет переопределено этим новым.\n\n"
            "Например: <code>поприветствовать</code>",
            "✍️ Send the trigger word/phrase for the action (what goes after the dot).\n\n"
            "If you use the name of an existing custom action or even a built-in command "
            "(e.g. <code>hug</code>) — it will be overridden by this new one.\n\n"
            "For example: <code>greet</code>",
        ),
        reply_markup=_wizard_keyboard(lang, skip=False, back=False),
    )


async def _prompt_emoji(message: Message, state: FSMContext, trigger: str, editing: bool, lang: str) -> None:
    await state.set_state(AddRPStates.waiting_emoji)
    prefix = (
        L(lang, f"✏️ Редактируем <code>{settings.command_prefix}{trigger}</code>.\n\n", f"✏️ Editing <code>{settings.command_prefix}{trigger}</code>.\n\n")
        if editing
        else ""
    )
    await message.answer(
        prefix
        + L(
            lang,
            "🎨 Отправь один или несколько эмодзи для этого действия одним сообщением "
            "(поддерживаются премиум-эмодзи Telegram — можно вставить сразу несколько подряд, "
            "при каждом использовании действия один из них будет выбираться случайно).",
            "🎨 Send one or several emoji for this action in a single message "
            "(Telegram premium emoji are supported — you can add several in a row, "
            "and one of them will be randomly picked each time the action is used).",
        ),
        reply_markup=_wizard_keyboard(lang, skip=False, back=True),
    )


async def _prompt_emoji_mode(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AddRPStates.waiting_emoji_mode)
    await message.answer(
        L(
            lang,
            "🎲 Ты прислал несколько эмодзи — как их показывать при использовании действия?",
            "🎲 You sent several emoji — how should they be shown when the action is used?",
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=L(lang, "🎲 Один случайный", "🎲 One at random"),
                        callback_data="addrp:mode:random",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=L(lang, "✨ Все вместе", "✨ All together"),
                        callback_data="addrp:mode:all",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=L(lang, "Назад", "Back"),
                        callback_data="addrp:back",
                        icon_custom_emoji_id=emoji("back")[1],
                    )
                ],
            ]
        ),
    )


async def _prompt_template(message: Message, state: FSMContext, trigger: str, lang: str) -> None:
    await state.set_state(AddRPStates.waiting_template)
    await message.answer(
        L(
            lang,
            "📝 Теперь введи текст действия. Используй <code>{user}</code> и <code>{target}</code> "
            "как плейсхолдеры для имён.\n\n"
            f"Например: <code>{{user}} поприветствовал(а) {{target}}</code>",
            "📝 Now send the action text. Use <code>{user}</code> and <code>{target}</code> "
            "as placeholders for the names.\n\n"
            f"For example: <code>{{user}} greeted {{target}}</code>",
        ),
        reply_markup=_wizard_keyboard(lang, skip=False, back=True),
    )


async def _prompt_gif(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AddRPStates.waiting_gif)
    await message.answer(
        L(
            lang,
            "🎬 Хочешь прикрепить гифку/видео к этому действию? Она будет отправляться вместе с "
            "текстом (текст станет подписью под гифкой).\n\n"
            "Пришли гифку/видео одним сообщением, или нажми «Пропустить», если гифка не нужна.",
            "🎬 Want to attach a GIF/video to this action? It will be sent together with "
            "the text (the text becomes the caption under the GIF).\n\n"
            "Send a GIF/video in a single message, or tap \"Skip\" if you don't need one.",
        ),
        reply_markup=_wizard_keyboard(lang, skip=True, back=True),
    )


async def _save_trigger(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession, gif_file_id: str | None
) -> None:
    lang = db_user.language
    data = await state.get_data()
    action_service = ActionService(session)
    trigger_obj = await action_service.create_custom_trigger(
        owner=db_user,
        trigger=data["trigger"],
        emojis=data["emojis"],
        template=data["template"],
        gif_file_id=gif_file_id,
        emoji_display_mode=data.get("emoji_display_mode", "random"),
    )
    await state.clear()

    override_note = (
        L(
            lang,
            " Оно переопределяет встроенную команду — если удалишь своё, вернётся стандартное поведение.",
            " It overrides a built-in command — if you delete yours, the default behaviour returns.",
        )
        if action_service.is_builtin(trigger_obj.trigger)
        else ""
    )
    gif_note = L(lang, " С гифкой.", " With a GIF.") if gif_file_id else ""
    await message.answer(
        L(
            lang,
            f"✅ Готово! Действие <code>{settings.command_prefix}{trigger_obj.trigger}</code> "
            f"сохранено и уже доступно в чатах.{gif_note}{override_note}",
            f"✅ Done! Action <code>{settings.command_prefix}{trigger_obj.trigger}</code> "
            f"is saved and already available in chats.{gif_note}{override_note}",
        )
    )


async def shared_rp_preview(
    trigger_id: int, db_user: User, session: AsyncSession
) -> tuple[str, list, InlineKeyboardMarkup] | None:
    """Готовит превью полученного по ссылке действия + кнопки Забрать/Отмена."""
    lang = db_user.language
    action_service = ActionService(session)
    shared = await action_service.get_custom_trigger_by_id(trigger_id)
    if shared is None:
        return None

    b = EntityTextBuilder()
    g1, gid1 = emoji("received_1")
    g2, gid2 = emoji("received_2")
    b.add_custom_emoji(g1, gid1)
    b.add_custom_emoji(g2, gid2)
    b.add_text(L(lang, " Тебе прислали RP-действие:\n\n", " You've been sent an RP action:\n\n"))
    for e, eid in action_service._custom_trigger_emojis(shared):
        b.add_custom_emoji(e, eid)
    b.add_text(" ")
    b.add_code(f"{settings.command_prefix}{shared.trigger}")
    if shared.gif_file_id:
        b.add_text(" 🎬")
    b.add_text(f"\n{shared.template}\n\n")

    existing = await action_service.get_custom_trigger(db_user.id, shared.trigger)
    if existing is not None:
        wg, wid = emoji("warning")
        b.add_custom_emoji(wg, wid)
        b.add_text(
            L(
                lang,
                " У тебя уже есть своё действие с таким же триггером — если заберёшь это, "
                "оно заменится.\n\n",
                " You already have your own action with this trigger — grabbing this one "
                "will replace it.\n\n",
            )
        )
    b.add_text(
        L(
            lang,
            "Чтобы им пользоваться, нужен активный премиум.",
            "You'll need active premium to use it.",
        )
    )
    text, entities = b.build()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Забрать себе", "Grab it"),
                    callback_data=f"share:import:{trigger_id}",
                    icon_custom_emoji_id=emoji("confirm")[1],
                ),
                InlineKeyboardButton(
                    text=L(lang, "Не нужно", "No thanks"),
                    callback_data="share:cancel",
                    icon_custom_emoji_id=emoji("cancel")[1],
                ),
            ]
        ]
    )
    return text, entities, keyboard


@router.callback_query(F.data.startswith("share:import:"))
async def cb_share_import(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    trigger_id = int(callback.data.split(":", 2)[2])
    action_service = ActionService(session)
    shared = await action_service.get_custom_trigger_by_id(trigger_id)
    if shared is None:
        await callback.answer(L(lang, "Действие больше не существует", "This action no longer exists"), show_alert=True)
        return

    emojis = action_service._custom_trigger_emojis(shared)
    await action_service.create_custom_trigger(
        owner=db_user,
        trigger=shared.trigger,
        emojis=emojis,
        template=shared.template,
        gif_file_id=shared.gif_file_id,
    )
    await callback.answer(L(lang, "Забрано!", "Grabbed!"))
    await callback.message.edit_text(
        L(
            lang,
            f"✅ Действие {settings.command_prefix}{shared.trigger} теперь и твоё. "
            "Посмотреть все свои действия можно в «Своё RP».",
            f"✅ The {settings.command_prefix}{shared.trigger} action is now yours too. "
            "Check all your actions in \"My RP\".",
        )
    )


@router.callback_query(F.data == "share:cancel")
async def cb_share_cancel(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer()
    await callback.message.edit_text(L(db_user.language, "Окей, не забираем.", "Okay, not grabbing it."))


async def _limit_reached_payload(db_user: User, session: AsyncSession) -> tuple[str, list] | None:
    """Если у пользователя базовый тариф и лимit своих RP исчерпан — возвращает текст отказа."""
    limit = db_user.custom_rp_limit
    if limit is None:
        return None  # Премиум+ — безлимит

    action_service = ActionService(session)
    current = len(await action_service.list_custom_triggers(db_user.id))
    if current < limit:
        return None

    lang = db_user.language
    b = EntityTextBuilder()
    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(
        L(
            lang,
            f" На тарифе «Премиум» можно создать до {limit} своих RP-действий — лимит уже "
            "исчерпан. Удали одно из существующих или перейди на Премиум+ (безлимит) в ",
            f" On the \"Premium\" plan you can create up to {limit} custom RP actions — the "
            "limit is already reached. Delete one of your existing actions, or upgrade to "
            "Premium+ (unlimited) in ",
        )
    )
    b.add_code("/premium")
    b.add_text(".")
    return b.build()


def _remaining_slots_note(db_user: User, current: int, lang: str) -> tuple[str, list] | None:
    """
    Короткая подсказка "осталось X из Y", которую показываем перед созданием нового RP —
    чтобы было видно, сколько слотов ещё доступно, а не только когда лимит уже исчерпан.
    Для Премиум+ (limit is None) ничего не показываем — там безлимит.
    """
    limit = db_user.custom_rp_limit
    if limit is None:
        return None

    remaining = max(limit - current, 0)
    b = EntityTextBuilder()
    b.add_text(
        L(
            lang,
            f"Своих RP: {current}/{limit} (осталось {remaining}).",
            f"Custom RP: {current}/{limit} ({remaining} left).",
        )
    )
    return b.build()


@router.message(Command("addrp"))
async def cmd_add_rp(message: Message, state: FSMContext, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    if not await is_subscribed(message.bot, message.from_user.id, message.from_user.username):
        text, entities = subscription_required_payload(lang)
        await message.answer(text, entities=entities, parse_mode=None)
        return

    if not db_user.has_premium:
        text, entities = _paywall_payload(lang)
        await message.answer(text, entities=entities, parse_mode=None)
        return

    limit_payload = await _limit_reached_payload(db_user, session)
    if limit_payload is not None:
        text, entities = limit_payload
        await message.answer(text, entities=entities, parse_mode=None)
        return

    action_service = ActionService(session)
    current = len(await action_service.list_custom_triggers(db_user.id))
    note = _remaining_slots_note(db_user, current, lang)
    if note is not None:
        text, entities = note
        await message.answer(text, entities=entities, parse_mode=None)

    await state.update_data(editing=False)
    await _prompt_trigger(message, state, lang)


@router.callback_query(F.data == "myrp:new")
async def cb_myrp_new(callback: CallbackQuery, state: FSMContext, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    if not await is_subscribed(callback.bot, callback.from_user.id, callback.from_user.username):
        text, entities = subscription_required_payload(lang)
        await callback.answer()
        await callback.message.answer(text, entities=entities, parse_mode=None)
        return
    if not db_user.has_premium:
        await callback.answer(L(lang, "Нужен премиум", "Premium required"), show_alert=True)
        return

    limit_payload = await _limit_reached_payload(db_user, session)
    if limit_payload is not None:
        text, entities = limit_payload
        await callback.answer()
        await callback.message.answer(text, entities=entities, parse_mode=None)
        return

    action_service = ActionService(session)
    current = len(await action_service.list_custom_triggers(db_user.id))
    note = _remaining_slots_note(db_user, current, lang)
    if note is not None:
        text, entities = note
        await callback.message.answer(text, entities=entities, parse_mode=None)

    await callback.answer()
    await state.update_data(editing=False)
    await _prompt_trigger(callback.message, state, lang)


@router.callback_query(F.data.startswith("myrp:edit:"))
async def cb_myrp_edit(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    trigger = callback.data.split(":", 2)[2]
    await state.update_data(trigger=trigger, editing=True)
    await callback.answer()
    await _prompt_emoji(callback.message, state, trigger, editing=True, lang=db_user.language)


@router.callback_query(F.data.startswith("myrp:share:"))
async def cb_myrp_share(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    trigger_name = callback.data.split(":", 2)[2]
    action_service = ActionService(session)
    trigger_obj = await action_service.get_custom_trigger(db_user.id, trigger_name)
    if trigger_obj is None:
        await callback.answer(L(lang, "Не найдено", "Not found"), show_alert=True)
        return

    me = await callback.bot.get_me()
    link = f"https://t.me/{me.username}?start=rp_{trigger_obj.id}"

    b = EntityTextBuilder()
    g, gid = emoji("share_link")
    b.add_custom_emoji(g, gid)
    b.add_text(
        L(
            lang,
            f" Ссылка, чтобы поделиться действием ",
            f" Link to share the action ",
        )
    )
    b.add_code(f"{settings.command_prefix}{trigger_obj.trigger}")
    b.add_text(
        L(
            lang,
            ":\n\nОтправь её другу — он сможет забрать это действие себе одним нажатием "
            "(чтобы им пользоваться, ему тоже понадобится премиум).\n\n",
            ":\n\nSend it to a friend — they can grab this action for themselves with one tap "
            "(they'll need premium too to use it).\n\n",
        )
    )
    b.add_code(link)
    text, entities = b.build()

    await callback.answer()
    await callback.message.answer(text, entities=entities, parse_mode=None)


@router.callback_query(F.data.startswith("myrp:delete:"))
async def cb_myrp_delete(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    trigger = callback.data.split(":", 2)[2]
    action_service = ActionService(session)
    deleted = await action_service.delete_custom_trigger(db_user.id, trigger)

    if deleted:
        note = (
            L(lang, " Встроенное действие с этим именем снова активно.", " The built-in action with this name is active again.")
            if action_service.is_builtin(trigger)
            else ""
        )
        await callback.answer(L(lang, f"Удалено.{note}", f"Deleted.{note}"), show_alert=True)
    else:
        await callback.answer(L(lang, "Уже удалено", "Already deleted"), show_alert=True)

    text, entities, keyboard = await my_rp_screen(db_user, session)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)


@router.callback_query(F.data == "addrp:back")
async def cb_addrp_back(
    callback: CallbackQuery, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    lang = db_user.language
    await callback.answer()
    current = await state.get_state()
    data = await state.get_data()
    trigger = data.get("trigger", "")
    editing = data.get("editing", False)

    if current == AddRPStates.waiting_gif.state:
        await _prompt_template(callback.message, state, trigger, lang)
    elif current == AddRPStates.waiting_template.state:
        emojis = data.get("emojis", [])
        if len(emojis) > 1:
            await _prompt_emoji_mode(callback.message, state, lang)
        else:
            await _prompt_emoji(callback.message, state, trigger, editing, lang)
    elif current == AddRPStates.waiting_emoji_mode.state:
        await _prompt_emoji(callback.message, state, trigger, editing, lang)
    elif current == AddRPStates.waiting_emoji.state:
        if editing:
            await state.clear()
            text, entities, keyboard = await my_rp_screen(db_user, session)
            await callback.message.answer(text, entities=entities, parse_mode=None, reply_markup=keyboard)
        else:
            await _prompt_trigger(callback.message, state, lang)
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
async def on_trigger_entered(message: Message, state: FSMContext, db_user: User) -> None:
    lang = db_user.language
    trigger = message.text.strip().lower().lstrip(".")
    if not trigger or " " in trigger:
        await message.answer(
            L(lang, "Триггер должен быть одним словом без пробелов. Попробуй ещё раз:", "The trigger must be a single word with no spaces. Try again:")
        )
        return

    await state.update_data(trigger=trigger)
    await _prompt_emoji(message, state, trigger, editing=False, lang=lang)


@router.message(AddRPStates.waiting_emoji)
async def on_emoji_entered(message: Message, state: FSMContext, db_user: User) -> None:
    lang = db_user.language
    emojis: list[tuple[str, str | None]] = []

    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                placeholder = utf16_slice(message.text, entity.offset, entity.length)
                emojis.append((placeholder, entity.custom_emoji_id))

    if not emojis and message.text:
        # Обычные (не премиум) эмодзи/символы — берём как один вариант без custom_emoji_id.
        fallback = message.text.strip()[:8]
        if fallback:
            emojis = [(fallback, None)]

    if not emojis:
        await message.answer(L(lang, "Не нашёл ни одного эмодзи в сообщении. Пришли ещё раз:", "Couldn't find any emoji in the message. Send it again:"))
        return

    await state.update_data(emojis=emojis)

    data = await state.get_data()
    trigger = data["trigger"]

    if len(emojis) > 1:
        await message.answer(L(lang, f"Принято ({len(emojis)} шт.).", f"Got it ({len(emojis)})."))
        await _prompt_emoji_mode(message, state, lang)
    else:
        await state.update_data(emoji_display_mode="random")
        await message.answer(L(lang, "Принято.", "Got it."))
        await _prompt_template(message, state, trigger, lang)


@router.callback_query(F.data.startswith("addrp:mode:"))
async def cb_addrp_emoji_mode(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    lang = db_user.language
    mode = callback.data.split(":", 2)[2]  # "random" | "all"
    await state.update_data(emoji_display_mode=mode)
    await callback.answer()

    data = await state.get_data()
    await _prompt_template(callback.message, state, data["trigger"], lang)


@router.message(AddRPStates.waiting_template, F.text)
async def on_template_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    lang = db_user.language
    if not db_user.has_premium:
        # Премиум мог закончиться прямо во время диалога — перепроверяем перед сохранением.
        await state.clear()
        text, entities = _paywall_payload(lang)
        await message.answer(text, entities=entities, parse_mode=None)
        return

    template = message.text.strip()
    if "{user}" not in template or "{target}" not in template:
        await message.answer(
            L(
                lang,
                "В шаблоне обязательно должны быть <code>{user}</code> и <code>{target}</code>. Попробуй ещё раз:",
                "The template must contain <code>{user}</code> and <code>{target}</code>. Try again:",
            )
        )
        return

    await state.update_data(template=template)
    await _prompt_gif(message, state, lang)


@router.message(AddRPStates.waiting_gif)
async def on_gif_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    lang = db_user.language
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
            L(
                lang,
                "Это не похоже на гифку/видео. Пришли гифку/видео одним сообщением, или нажми «Пропустить»:",
                "That doesn't look like a GIF/video. Send a GIF/video in one message, or tap \"Skip\":",
            ),
            reply_markup=_wizard_keyboard(lang, skip=True, back=True),
        )
        return

    await _save_trigger(message, state, db_user, session, gif_file_id=file_id)
