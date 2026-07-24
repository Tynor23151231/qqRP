from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.keyboards.menu import back_to_menu_row, with_back_button
from app.models import ButtonFlow, User
from app.services.button_flow_service import ButtonFlowService
from app.services.inline_button_alert_service import register_alert
from app.utils.premium_emoji import emoji
from app.utils.text_parsing import parse_flow_buttons

router = Router(name="button_flows")

MAX_SCREENS = 6
MAX_BUTTONS_PER_SCREEN = 6

_NEXT_CALLBACK_PREFIX = "bflow:"
_ALERT_CALLBACK_PREFIX = "btnalert:"


# ---------------------------------------------------------------------------
# Рендер экрана (текст + клавиатура) из сохранённого screens[i] — используется
# и при первом вызове триггера (business/actions.py), и при переходе "next".
# ---------------------------------------------------------------------------

def _build_screen_markup(flow_id: int, screen_index: int, buttons: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for b in buttons:
        if b["type"] == "url":
            rows.append([InlineKeyboardButton(text=b["label"], url=b["payload"])])
        elif b["type"] == "next":
            rows.append(
                [
                    InlineKeyboardButton(
                        text=b["label"],
                        callback_data=f"{_NEXT_CALLBACK_PREFIX}{flow_id}:{screen_index + 1}",
                    )
                ]
            )
        else:  # alert — callback_data формируется в render_screen ниже
            rows.append([InlineKeyboardButton(text=b["label"], callback_data=b["_callback_data"])])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_screen(
    session: AsyncSession,
    owner_id: int,
    business_connection_id: str | None,
    flow_id: int,
    screen_index: int,
    screen_text: str,
    buttons: list[dict],
) -> tuple[str, InlineKeyboardMarkup]:
    """
    Готовит (текст, клавиатура) для одного экрана цепочки.
    Для alert-кнопок создаёт запись InlineButtonAlert в момент показа экрана
    (а не при создании цепочки — так текст остаётся актуальным даже для старых цепочек).
    """
    buttons = [dict(b) for b in buttons]
    for b in buttons:
        if b["type"] == "alert":
            alert_id = await register_alert(session, owner_id, business_connection_id, b["payload"])
            b["_callback_data"] = f"{_ALERT_CALLBACK_PREFIX}{alert_id}"
    markup = _build_screen_markup(flow_id, screen_index, buttons)
    return screen_text, markup


@router.callback_query(F.data.startswith(_NEXT_CALLBACK_PREFIX))
async def handle_flow_next(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    """Нажатие на кнопку типа 'next' — заменяет сообщение следующим экраном цепочки."""
    try:
        _, flow_id_s, next_index_s = callback.data.split(":", 2)
        flow_id, next_index = int(flow_id_s), int(next_index_s)
    except ValueError:
        await callback.answer()
        return

    service = ButtonFlowService(session)
    flow = await service.get_by_id(flow_id)
    if flow is None or next_index >= len(flow.screens):
        await callback.answer(
            L(db_user.language, "Эта цепочка больше не активна.", "This chain is no longer active."),
            show_alert=True,
        )
        return

    screen = flow.screens[next_index]
    text, markup = await render_screen(
        session, flow.owner_id, None, flow.id, next_index, screen["text"], screen["buttons"]
    )
    await callback.answer()
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:  # сообщение могли удалить/оно не изменилось — не критично
        pass


# ---------------------------------------------------------------------------
# Список "Кнопок" в меню — тот же вид, что и "Своё RP"
# ---------------------------------------------------------------------------

_SYNTAX_REMINDER_RU = (
    "Формат кнопки: <code>Название | next</code> (дальше по цепочке), "
    "<code>Название | Текст</code> (alert) или <code>Название | https://ссылка</code>."
)
_SYNTAX_REMINDER_EN = (
    "Button format: <code>Label | next</code> (go to the next screen), "
    "<code>Label | Text</code> (alert) or <code>Label | https://link</code>."
)


async def _flows_list_payload(db_user: User, session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    lang = db_user.language
    service = ButtonFlowService(session)
    flows = await service.list_flows(db_user.id)

    lines = [L(lang, "🔘 <b>Свои цепочки кнопок</b>", "🔘 <b>My button chains</b>")]
    lines.append(L(lang, _SYNTAX_REMINDER_RU, _SYNTAX_REMINDER_EN))

    if not flows:
        lines.append(
            L(
                lang,
                "\nПока не создано ни одной — жми «Создать новую».",
                "\nNone created yet — tap \u201cCreate new\u201d.",
            )
        )
    else:
        lines.append("")
        for f in flows:
            dots = "🔘" * len(f.screens)
            lines.append(f"{dots} <code>{settings.command_prefix}{f.trigger}</code>")

    rows: list[list[InlineKeyboardButton]] = []
    for f in flows:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✏️ .{f.trigger}", callback_data=f"bflowedit:{f.trigger}"
                ),
                InlineKeyboardButton(
                    text=L(lang, "Поделиться", "Share"),
                    callback_data=f"bflowshare:{f.trigger}",
                    icon_custom_emoji_id=emoji("share")[1],
                ),
                InlineKeyboardButton(
                    text=L(lang, "Удалить", "Delete"),
                    callback_data=f"bflowdel:{f.trigger}",
                    style="danger",
                    icon_custom_emoji_id=emoji("delete")[1],
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=L(lang, "Создать новое", "Create new"),
                callback_data="bflow:new",
                icon_custom_emoji_id=emoji("addrp")[1],
            )
        ]
    )
    rows.append(back_to_menu_row(lang))

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:buttons")
async def cb_menu_buttons(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    text, keyboard = await _flows_list_payload(db_user, session)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("bflowdel:"))
async def cb_flow_delete(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    trigger = callback.data.split(":", 1)[1]
    service = ButtonFlowService(session)
    deleted = await service.delete(db_user.id, trigger)
    await callback.answer(
        L(db_user.language, "Удалено." if deleted else "Уже удалено", "Deleted." if deleted else "Already deleted"),
        show_alert=True,
    )
    text, keyboard = await _flows_list_payload(db_user, session)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Поделиться / забрать цепочку (аналогично "Своё RP")
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("bflowshare:"))
async def cb_flow_share(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    trigger = callback.data.split(":", 1)[1]
    service = ButtonFlowService(session)
    flow = await service.get_by_trigger(db_user.id, trigger)
    if flow is None:
        await callback.answer(L(lang, "Не найдено", "Not found"), show_alert=True)
        return

    me = await callback.bot.get_me()
    link = f"https://t.me/{me.username}?start=bf_{flow.id}"
    text = L(
        lang,
        f"🔗 Ссылка, чтобы поделиться цепочкой <code>{settings.command_prefix}{flow.trigger}</code>:\n\n"
        f"<code>{link}</code>\n\n"
        "Отправь её другу — он сможет забрать её себе одним нажатием.",
        f"🔗 Link to share the chain <code>{settings.command_prefix}{flow.trigger}</code>:\n\n"
        f"<code>{link}</code>\n\n"
        "Send it to a friend — they can grab it for themselves with one tap.",
    )
    await callback.answer()
    await callback.message.answer(text, parse_mode="HTML")


async def shared_flow_preview(
    flow_id: int, db_user: User, session: AsyncSession
) -> tuple[str, InlineKeyboardMarkup] | None:
    """Готовит превью полученной по ссылке цепочки + кнопки Забрать/Отмена."""
    lang = db_user.language
    service = ButtonFlowService(session)
    shared = await service.get_by_id(flow_id)
    if shared is None:
        return None

    lines = [L(lang, "😋 Тебе прислали цепочку кнопок:\n", "😋 You've been sent a button chain:\n")]
    dots = "🔘" * len(shared.screens)
    lines.append(f"{dots} <code>{settings.command_prefix}{shared.trigger}</code>")
    lines.append(f"\n<i>{shared.screens[0]['text']}</i>")

    existing = await service.get_by_trigger(db_user.id, shared.trigger)
    if existing is not None:
        lines.append(
            L(
                lang,
                "\n\n⚠️ У тебя уже есть цепочка с таким же названием — если заберёшь эту, она заменится.",
                "\n\n⚠️ You already have a chain with this name — grabbing this one will replace it.",
            )
        )

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Забрать себе", "Grab it"),
                    callback_data=f"bflowimport:{flow_id}",
                    icon_custom_emoji_id=emoji("confirm")[1],
                ),
                InlineKeyboardButton(
                    text=L(lang, "Не нужно", "No thanks"),
                    callback_data="bflowimport:cancel",
                    icon_custom_emoji_id=emoji("cancel")[1],
                ),
            ]
        ]
    )
    return text, keyboard


@router.callback_query(F.data.startswith("bflowimport:") & ~F.data.endswith(":cancel"))
async def cb_flow_import(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    flow_id = int(callback.data.split(":", 1)[1])
    service = ButtonFlowService(session)
    shared = await service.get_by_id(flow_id)
    if shared is None:
        await callback.answer(L(lang, "Цепочка больше не существует", "This chain no longer exists"), show_alert=True)
        return

    await service.create_or_replace(db_user.id, shared.trigger, shared.screens)
    await callback.answer(L(lang, "Забрано!", "Grabbed!"))
    await callback.message.edit_text(
        L(
            lang,
            f"✅ Цепочка {settings.command_prefix}{shared.trigger} теперь и твоя. Посмотреть все свои — в «Кнопки».",
            f"✅ The {settings.command_prefix}{shared.trigger} chain is now yours too. See all yours in \u201cButtons\u201d.",
        )
    )


@router.callback_query(F.data == "bflowimport:cancel")
async def cb_flow_import_cancel(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer()
    await callback.message.edit_text(L(db_user.language, "Окей, не забираем.", "Okay, not grabbing it."))


# ---------------------------------------------------------------------------
# Мастер создания / изменения
# ---------------------------------------------------------------------------

class ButtonFlowStates(StatesGroup):
    waiting_trigger = State()
    waiting_screen_text = State()
    waiting_screen_buttons = State()


def _intro_text(lang: str) -> str:
    return L(
        lang,
        (
            "🔘 <b>Как устроена цепочка кнопок</b>\n\n"
            "1️⃣ Придумываешь короткое название команды без точки (например <code>пожатьруку</code>) — "
            "по нему цепочка будет вызываться в чате.\n\n"
            "2️⃣ Пишешь текст первого экрана — сообщение, которое увидит собеседник "
            "(можно вставить <code>{target}</code> — подставится имя того, кому отвечаешь).\n\n"
            "3️⃣ Указываешь кнопки для этого экрана, по одной на строке:\n"
            "   • <code>Название | next</code> — кнопка ведёт на следующий экран\n"
            "   • <code>Название | Текст</code> — кнопка-alert (покажет текст всплывающим окном)\n"
            "   • <code>Название | https://ссылка</code> — кнопка-ссылка\n\n"
            "4️⃣ Если хотя бы одна кнопка ведёт <code>next</code> — бот попросит текст следующего "
            f"экрана, и всё повторяется (максимум {MAX_SCREENS} экранов). Как только на экране больше "
            "нет кнопок <code>next</code> — цепочка сохраняется.\n\n"
            "<b>Пример:</b> <code>.пожатьруку</code> → «{target} хочет пожать руку» "
            "[Принять → next] [Отказаться → alert] → нажали «Принять» → «Договорились!» [Ок → alert]\n\n"
            "Напиши название команды, чтобы начать:"
        ),
        (
            "🔘 <b>How a button chain works</b>\n\n"
            "1️⃣ Pick a short command name without a dot (e.g. <code>handshake</code>) — it's what "
            "triggers the chain in chat.\n\n"
            "2️⃣ Write the text for the first screen — the message the other person will see "
            "(you can use <code>{target}</code> — it's replaced with the name of who you're replying to).\n\n"
            "3️⃣ Set the buttons for that screen, one per line:\n"
            "   • <code>Label | next</code> — leads to the next screen\n"
            "   • <code>Label | Text</code> — alert button (shows text as a popup)\n"
            "   • <code>Label | https://link</code> — link button\n\n"
            "4️⃣ If at least one button says <code>next</code> — the bot asks for the next screen's "
            f"text, and it repeats (max {MAX_SCREENS} screens). Once a screen has no <code>next</code> "
            "buttons left — the chain is saved.\n\n"
            "<b>Example:</b> <code>.handshake</code> → \u201c{target} wants to shake hands\u201d "
            "[Accept → next] [Decline → alert] → tapped \u201cAccept\u201d → \u201cDeal!\u201d [OK → alert]\n\n"
            "Send the command name to start:"
        ),
    )


@router.callback_query(F.data == "bflow:new")
async def cb_flow_new(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    lang = db_user.language
    await state.set_state(ButtonFlowStates.waiting_trigger)
    await state.update_data(screens=[])
    await callback.answer()
    await callback.message.edit_text(
        _intro_text(lang),
        parse_mode="HTML",
        reply_markup=with_back_button(InlineKeyboardMarkup(inline_keyboard=[]), lang),
    )


@router.callback_query(F.data.startswith("bflowedit:"))
async def cb_flow_edit(callback: CallbackQuery, state: FSMContext, db_user: User, session: AsyncSession) -> None:
    """"Изменить" — пересобирает цепочку с нуля под тем же названием (старая версия стирается)."""
    lang = db_user.language
    trigger = callback.data.split(":", 1)[1]
    service = ButtonFlowService(session)
    existing = await service.get_by_trigger(db_user.id, trigger)
    if existing is None:
        await callback.answer(L(lang, "Не найдено", "Not found"), show_alert=True)
        return

    await state.set_state(ButtonFlowStates.waiting_screen_text)
    await state.update_data(trigger=trigger, screens=[])
    await callback.answer()
    await callback.message.edit_text(
        L(
            lang,
            f"✏️ Пересоздаём <code>{settings.command_prefix}{trigger}</code> с нуля — прежняя версия будет "
            "стёрта после сохранения новой.\n\nТекст первого экрана:",
            f"✏️ Rebuilding <code>{settings.command_prefix}{trigger}</code> from scratch — the old version "
            "will be replaced once the new one is saved.\n\nText for the first screen:",
        ),
        parse_mode="HTML",
    )


@router.message(ButtonFlowStates.waiting_trigger, F.text)
async def on_flow_trigger(message: Message, state: FSMContext, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    trigger = message.text.strip().lower().lstrip(".")
    if not trigger or " " in trigger or len(trigger) > 40:
        await message.answer(
            L(
                lang,
                "Одно слово без пробелов, до 40 символов. Попробуй ещё раз:",
                "One word, no spaces, up to 40 characters. Try again:",
            )
        )
        return

    service = ButtonFlowService(session)
    if await service.get_by_trigger(db_user.id, trigger) is not None:
        await message.answer(
            L(
                lang,
                "У тебя уже есть цепочка с таким названием. Выбери другое (или удали старую и создай заново):",
                "You already have a chain with this name. Pick another (or delete the old one and start over):",
            )
        )
        return

    await state.update_data(trigger=trigger)
    await state.set_state(ButtonFlowStates.waiting_screen_text)
    await message.answer(
        L(
            lang,
            "Текст первого экрана (можно использовать <code>{target}</code>):",
            "Text for the first screen (you can use <code>{target}</code>):",
        ),
        parse_mode="HTML",
    )


@router.message(ButtonFlowStates.waiting_screen_text, F.text)
async def on_flow_screen_text(message: Message, state: FSMContext, db_user: User) -> None:
    lang = db_user.language
    data = await state.get_data()
    screens = data.get("screens", [])
    screens.append({"text": message.text.strip(), "buttons": []})
    await state.update_data(screens=screens, current_screen=len(screens) - 1)
    await state.set_state(ButtonFlowStates.waiting_screen_buttons)
    await message.answer(
        L(
            lang,
            f"Экран {len(screens)}: теперь кнопки, по одной на строке (максимум {MAX_BUTTONS_PER_SCREEN}):\n"
            "<code>Название | next</code> / <code>Название | Текст</code> / <code>Название | https://ссылка</code>",
            f"Screen {len(screens)}: now the buttons, one per line (max {MAX_BUTTONS_PER_SCREEN}):\n"
            "<code>Label | next</code> / <code>Label | Text</code> / <code>Label | https://link</code>",
        ),
        parse_mode="HTML",
    )


@router.message(ButtonFlowStates.waiting_screen_buttons, F.text)
async def on_flow_screen_buttons(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    lang = db_user.language
    buttons = parse_flow_buttons(message.text, MAX_BUTTONS_PER_SCREEN)
    if buttons is None:
        await message.answer(
            L(
                lang,
                f"Не удалось разобрать. Проверь формат (максимум {MAX_BUTTONS_PER_SCREEN} строк, "
                "в каждой обязателен разделитель |). Попробуй ещё раз:",
                f"Couldn't parse that. Check the format (max {MAX_BUTTONS_PER_SCREEN} lines, each "
                "needs a | separator). Try again:",
            )
        )
        return

    data = await state.get_data()
    screens = data["screens"]
    current = data["current_screen"]
    screens[current]["buttons"] = buttons
    await state.update_data(screens=screens)

    has_next = any(b["type"] == "next" for b in buttons)
    if has_next and len(screens) < MAX_SCREENS:
        await state.set_state(ButtonFlowStates.waiting_screen_text)
        await message.answer(
            L(
                lang,
                f"Текст экрана {len(screens) + 1}:",
                f"Text for screen {len(screens) + 1}:",
            ),
            parse_mode="HTML",
        )
        return

    if has_next and len(screens) >= MAX_SCREENS:
        # достигли предела экранов — превращаем оставшиеся "next"-кнопки в обычный alert
        fallback_text = L(lang, "Это была последняя кнопка в цепочке.", "This was the last button in the chain.")
        for b in screens[current]["buttons"]:
            if b["type"] == "next":
                b["type"] = "alert"
                b["payload"] = fallback_text

    service = ButtonFlowService(session)
    flow = await service.create_or_replace(db_user.id, data["trigger"], screens)
    await state.clear()
    await message.answer(
        L(
            db_user.language,
            f"✅ Готово! Вызывай в бизнес-чате командой <code>{settings.command_prefix}{flow.trigger}</code>.",
            f"✅ Done! Trigger it in a business chat with <code>{settings.command_prefix}{flow.trigger}</code>.",
        ),
        parse_mode="HTML",
    )
