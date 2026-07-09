from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import L
from app.keyboards.menu import back_to_menu_row
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="autoreact")


def _paywall_payload(lang: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Авто-реакции — премиум-функция", "Auto-reactions is a premium feature"))
    b.add_text(
        L(
            lang,
            "\n\nВыбери одного собеседника — и на все его сообщения в бизнес-чате будет "
            "автоматически ставиться выбранная тобой реакция (можно даже премиум-эмодзи).\n\n"
            "Оформить: ",
            "\n\nPick one contact — and every message they send in the business chat will "
            "automatically get the reaction you chose (premium emoji included).\n\n"
            "Get it: ",
        )
    )
    b.add_code("/premium")
    return b.build()


def _autoreact_keyboard(lang: str, *, configured: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=L(lang, "Изменить", "Change") if configured else L(lang, "Настроить", "Set up"),
                callback_data="autoreact:setup",
            )
        ]
    ]
    if configured:
        rows.append(
            [InlineKeyboardButton(text=L(lang, "Отключить", "Turn off"), callback_data="autoreact:clear")]
        )
    rows.append(back_to_menu_row(lang))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def autoreact_screen(
    db_user: User, session: AsyncSession
) -> tuple[str, list, InlineKeyboardMarkup]:
    lang = db_user.language
    if not db_user.has_premium:
        text, entities = _paywall_payload(lang)
        return text, entities, InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row(lang)])

    b = EntityTextBuilder()
    b.add_bold(L(lang, "Авто-реакции", "Auto-reactions"))
    b.add_text(
        L(
            lang,
            "\n\nАвтоматически ставит выбранную реакцию (в т.ч. премиум-эмодзи) на все "
            "сообщения от одного выбранного собеседника в бизнес-чате.\n\n",
            "\n\nAutomatically sets your chosen reaction (premium emoji included) on every "
            "message from one selected contact in the business chat.\n\n",
        )
    )

    configured = db_user.autoreact_target_id is not None
    if configured:
        user_service = UserService(session)
        target = await user_service.get_by_telegram_id(db_user.autoreact_target_id)
        target_label = target.display_name if target else str(db_user.autoreact_target_id)
        b.add_text(L(lang, "Сейчас настроено на: ", "Currently set for: "))
        b.add_text(f"{target_label}\n")
        b.add_text(L(lang, "Реакция: ", "Reaction: "))
        if db_user.autoreact_custom_emoji_id:
            b.add_custom_emoji(db_user.autoreact_emoji, db_user.autoreact_custom_emoji_id)
        else:
            b.add_text(db_user.autoreact_emoji or "")
    else:
        b.add_text(L(lang, "Пока не настроено.", "Not set up yet."))

    text, entities = b.build()
    return text, entities, _autoreact_keyboard(lang, configured=configured)


class AutoReactStates(StatesGroup):
    waiting_target = State()
    waiting_emoji = State()


def _wizard_back_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Назад", "Back"),
                    callback_data="autoreact:back",
                    icon_custom_emoji_id=emoji("back")[1],
                )
            ]
        ]
    )


async def _prompt_target(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AutoReactStates.waiting_target)
    await message.answer(
        L(
            lang,
            "Пришли @username или id пользователя, на сообщения которого нужно "
            "автоматически ставить реакцию.\n\n"
            "Этот человек обязательно должен был хотя бы раз нажать /start в этом боте — "
            "иначе я не смогу его найти.",
            "Send the @username or id of the person whose messages should get an "
            "automatic reaction.\n\n"
            "This person must have pressed /start in this bot at least once — "
            "otherwise I won't be able to find them.",
        ),
        reply_markup=_wizard_back_keyboard(lang),
    )


async def _prompt_emoji(message: Message, state: FSMContext, lang: str) -> None:
    await state.set_state(AutoReactStates.waiting_emoji)
    await message.answer(
        L(
            lang,
            "Теперь пришли эмодзи, которое будет ставиться реакцией (обычное или премиум).",
            "Now send the emoji to use as the reaction (regular or premium).",
        ),
        reply_markup=_wizard_back_keyboard(lang),
    )


@router.callback_query(F.data == "menu:autoreact")
async def cb_menu_autoreact(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    text, entities, keyboard = await autoreact_screen(db_user, session)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "autoreact:setup")
async def cb_autoreact_setup(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    if not db_user.has_premium:
        await callback.answer(L(db_user.language, "Нужен премиум", "Premium required"), show_alert=True)
        return
    await callback.answer()
    await _prompt_target(callback.message, state, db_user.language)


@router.callback_query(F.data == "autoreact:clear")
async def cb_autoreact_clear(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    user_service = UserService(session)
    await user_service.clear_autoreact(db_user)
    await callback.answer(L(db_user.language, "Отключено", "Turned off"))
    text, entities, keyboard = await autoreact_screen(db_user, session)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)


@router.callback_query(F.data == "autoreact:back")
async def cb_autoreact_back(
    callback: CallbackQuery, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    await state.clear()
    await callback.answer()
    text, entities, keyboard = await autoreact_screen(db_user, session)
    await callback.message.edit_text(text, entities=entities, parse_mode=None, reply_markup=keyboard)


@router.message(AutoReactStates.waiting_target, F.text)
async def on_target_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    lang = db_user.language
    raw = message.text.strip()
    user_service = UserService(session)

    target: User | None = None
    if raw.startswith("@"):
        target = await user_service.get_by_username(raw.lstrip("@"))
    elif raw.lstrip("-").isdigit():
        target = await user_service.get_by_telegram_id(int(raw))
    else:
        target = await user_service.get_by_username(raw)

    if target is None:
        await message.answer(
            L(
                lang,
                "Не нашёл такого пользователя среди тех, кто уже нажимал /start в этом боте. "
                "Попроси его сначала запустить бота, потом пришли @username или id ещё раз:",
                "Couldn't find this user among people who have pressed /start in this bot. "
                "Ask them to start the bot first, then send @username or id again:",
            ),
            reply_markup=_wizard_back_keyboard(lang),
        )
        return

    if target.telegram_id == db_user.telegram_id:
        await message.answer(
            L(
                lang,
                "Нельзя настроить авто-реакцию на самого себя. Пришли другого пользователя:",
                "You can't set auto-reactions on yourself. Send a different user:",
            ),
            reply_markup=_wizard_back_keyboard(lang),
        )
        return

    await state.update_data(target_id=target.telegram_id, target_label=target.display_name)
    await _prompt_emoji(message, state, lang)


@router.message(AutoReactStates.waiting_emoji)
async def on_emoji_entered(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession
) -> None:
    lang = db_user.language
    picked_emoji: str | None = None
    custom_emoji_id: str | None = None

    if message.entities:
        for entity in message.entities:
            if entity.type == "custom_emoji":
                picked_emoji = message.text[entity.offset:entity.offset + entity.length]
                custom_emoji_id = entity.custom_emoji_id
                break

    if picked_emoji is None and message.text:
        picked_emoji = message.text.strip()[:8]

    if not picked_emoji:
        await message.answer(
            L(
                lang,
                "Не нашёл эмодзи в сообщении. Пришли ещё раз:",
                "Couldn't find an emoji in the message. Send it again:",
            ),
            reply_markup=_wizard_back_keyboard(lang),
        )
        return

    data = await state.get_data()
    user_service = UserService(session)
    await user_service.set_autoreact(db_user, data["target_id"], picked_emoji, custom_emoji_id)
    await state.clear()

    await message.answer(
        L(
            lang,
            f"Готово! Теперь на сообщения от {data['target_label']} в бизнес-чате будет "
            "автоматически ставиться эта реакция.",
            f"Done! Messages from {data['target_label']} in the business chat will now "
            "automatically get this reaction.",
        )
    )
