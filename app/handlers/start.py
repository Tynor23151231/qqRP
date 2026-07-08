from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.keyboards.gender import gender_keyboard
from app.keyboards.menu import back_only_keyboard, main_menu_keyboard, with_back_button
from app.keyboards.profile import profile_keyboard
from app.keyboards.settings import settings_keyboard
from app.keyboards.subscription import subscription_keyboard
from app.models import Gender, User
from app.services.action_service import ActionService
from app.services.subscription_service import is_subscribed, notify_channel, subscription_required_payload
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="start")

_NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


def _onboarding_text(lang: str) -> str:
    return L(
        lang,
        (
            '<tg-emoji emoji-id="5233599134019100925">👋</tg-emoji> <b>Привет! Это qqRP Bot.</b>\n\n'
            "Я умею красиво оформлять RP-действия по коротким командам с точкой — например "
            f"<code>{settings.command_prefix}муа</code>, <code>{settings.command_prefix}обнять</code>, "
            f"<code>{settings.command_prefix}цветы</code>.\n\n"
            f"Также поддерживаю стили печатания <code>{settings.command_prefix}typing</code>, и в будущем "
            f"будут только добавляться — следи за новостями в @{settings.required_channel_username}.\n\n"
            "<b>Как это работает:</b>\n"
            '<tg-emoji emoji-id="5447584416274595624">1️⃣</tg-emoji> Подключаешь меня как Telegram Business '
            "Bot к своему аккаунту\n"
            '<tg-emoji emoji-id="5447569199205468152">2️⃣</tg-emoji> Пишешь в любом чате (личном или группе) '
            f"команду вида <code>{settings.command_prefix}муа</code> (в ответ на сообщение человека, или с "
            "<code>@username</code> после команды)\n"
            '<tg-emoji emoji-id="5438196446694228650">3️⃣</tg-emoji> Я удаляю твоё сообщение-команду и '
            "отправляю красивое RP-действие с кликабельными именами вместо него\n\n"
            "Для начала выбери свой пол — это нужно, чтобы правильно склонять действия "
            "(«поцеловал» / «поцеловала»):"
        ),
        (
            '<tg-emoji emoji-id="5233599134019100925">👋</tg-emoji> <b>Hi! This is qqRP Bot.</b>\n\n'
            "I turn short dot-commands into nicely formatted RP actions — for example "
            f"<code>{settings.command_prefix}muah</code>, <code>{settings.command_prefix}hug</code>, "
            f"<code>{settings.command_prefix}flowers</code>.\n\n"
            f"I also support letter-by-letter typing via <code>{settings.command_prefix}typing</code>, and "
            f"more is on the way — follow updates in @{settings.required_channel_username}.\n\n"
            "<b>How it works:</b>\n"
            '<tg-emoji emoji-id="5447584416274595624">1️⃣</tg-emoji> Connect me as a Telegram Business '
            "Bot to your account\n"
            '<tg-emoji emoji-id="5447569199205468152">2️⃣</tg-emoji> Write a command like '
            f"<code>{settings.command_prefix}muah</code> in any chat (in reply to someone's message, or "
            "followed by <code>@username</code>)\n"
            '<tg-emoji emoji-id="5438196446694228650">3️⃣</tg-emoji> I delete your command message and post '
            "a nicely formatted RP action with clickable names instead\n\n"
            "First, pick your gender — it's needed to conjugate actions correctly:"
        ),
    )


def _howto_text(lang: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("howto")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold(L(lang, "Как подключить Telegram Business", "How to connect Telegram Business"))
    b.add_text(
        L(
            lang,
            "\n\nНужен Telegram Premium — без него бизнес-функции недоступны.\n\n"
            "1. Открой Настройки → Telegram для бизнеса → Чат-боты\n"
            "2. Введи имя этого бота и подключи его\n"
            "3. Обязательно включи права:\n"
            "   • Читать сообщения\n"
            "   • Отправлять сообщения\n"
            "   • Удалять отправленные сообщения ⚠️ без этого права команды "
            "не будут удаляться после срабатывания\n\n"
            f"После подключения просто пиши команды вроде {settings.command_prefix}муа "
            "в любом чате — я отвечу от твоего имени.",
            "\n\nYou need Telegram Premium — business features aren't available without it.\n\n"
            "1. Open Settings → Telegram Business → Chatbots\n"
            "2. Enter this bot's username and connect it\n"
            "3. Make sure to enable these rights:\n"
            "   • Read messages\n"
            "   • Send messages\n"
            "   • Delete sent messages ⚠️ without this right, command messages "
            "won't be deleted after triggering\n\n"
            f"Once connected, just write commands like {settings.command_prefix}muah "
            "in any chat — I'll reply on your behalf.",
        )
    )
    return b.build()


def _format_commands_list(action_service: ActionService, lang: str) -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("commands")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold(L(lang, "Список команд", "Commands list"))
    b.add_text(
        L(
            lang,
            "\n\nПиши в чате в ответ на сообщение человека или с @username:\n\n",
            "\n\nWrite in chat in reply to someone's message, or with @username:\n\n",
        )
    )
    for key, aliases, action_emoji in sorted(action_service.builtin_display_list(), key=lambda x: x[0]):
        names = f"{settings.command_prefix}{key}"
        if aliases:
            names += " / " + " / ".join(f"{settings.command_prefix}{a}" for a in aliases)
        b.add_text(f"{action_emoji} ")
        b.add_code(names)
        b.add_text("\n")
    b.add_text(
        L(
            lang,
            f"\n➕ Плюс можно создать свои действия через {settings.command_prefix}addrp (премиум).",
            f"\n➕ You can also create your own actions via {settings.command_prefix}addrp (premium).",
        )
    )
    return b.build()


def _menu_home_payload(lang: str, name: str | None = None) -> tuple[str, list]:
    b = EntityTextBuilder()
    glyph, cid = emoji("home")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold(L(lang, "Главное меню", "Main menu"))
    if name:
        b.add_text(L(lang, f"\n\nС возвращением, {name}! ", f"\n\nWelcome back, {name}! "))
        wg, wid = emoji("wave")
        b.add_custom_emoji(wg, wid)
    return b.build()


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, session: AsyncSession, command: CommandObject) -> None:
    lang = db_user.language
    if not await is_subscribed(message.bot, message.from_user.id):
        text, entities = subscription_required_payload(lang)
        await message.answer(
            text, entities=entities, parse_mode=None, reply_markup=subscription_keyboard(lang)
        )
        return

    if command.args and command.args.startswith("rp_") and command.args[3:].isdigit():
        from app.handlers.custom_rp import shared_rp_preview  # локальный импорт во избежание циклов

        preview = await shared_rp_preview(int(command.args[3:]), db_user, session)
        if preview is not None:
            text, entities, keyboard = preview
            await message.answer(text, entities=entities, parse_mode=None, reply_markup=keyboard)
            return

    if not db_user.is_configured and command.args and command.args.isdigit():
        referrer_id = int(command.args)
        service = UserService(session)
        await service.set_referrer(db_user, referrer_id)

    if db_user.is_configured:
        text, entities = _menu_home_payload(lang, db_user.display_name)
        await message.answer(
            text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
            reply_markup=main_menu_keyboard(db_user),
        )
        return

    await message.answer(_onboarding_text(lang), reply_markup=gender_keyboard(lang))


@router.callback_query(F.data == "check_subscription")
async def cb_check_subscription(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    if not await is_subscribed(callback.bot, callback.from_user.id):
        await callback.answer(
            L(lang, "Пока не вижу подписку — подпишись и попробуй ещё раз 🙂", "I still don't see a subscription — subscribe and try again 🙂"),
            show_alert=True,
        )
        return

    await callback.answer(L(lang, "Подписка подтверждена ✅", "Subscription confirmed ✅"))

    if db_user.is_configured:
        text, entities = _menu_home_payload(lang, db_user.display_name)
        await callback.message.edit_text(
            text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
            reply_markup=main_menu_keyboard(db_user),
        )
    else:
        await callback.message.edit_text(_onboarding_text(lang), reply_markup=gender_keyboard(lang))


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User) -> None:
    lang = db_user.language
    if not await is_subscribed(message.bot, message.from_user.id):
        text, entities = subscription_required_payload(lang)
        await message.answer(
            text, entities=entities, parse_mode=None, reply_markup=subscription_keyboard(lang)
        )
        return

    text, entities = _menu_home_payload(lang)
    await message.answer(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=main_menu_keyboard(db_user),
    )


@router.callback_query(F.data.startswith("gender:"))
async def on_gender_chosen(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    gender_value = callback.data.split(":", 1)[1]
    gender = Gender.MALE if gender_value == "male" else Gender.FEMALE

    is_first_registration = not db_user.is_configured

    service = UserService(session)
    await service.set_gender(db_user, gender)

    if is_first_registration:
        username_part = f"@{db_user.username}" if db_user.username else "без username"
        await notify_channel(
            callback.bot,
            f"🆕 Новый пользователь: {db_user.first_name} ({username_part}, id {db_user.telegram_id}), "
            f"пол: {'мужской' if gender == Gender.MALE else 'женский'}",
        )

        if db_user.invited_by_id is not None:
            referrer = await service.get_by_telegram_id(db_user.invited_by_id)
            if referrer is not None:
                reward_granted = await service.register_referral_completion(referrer)
                if reward_granted:
                    ref_lang = referrer.language
                    ref_b = EntityTextBuilder()
                    g, gid = emoji("premium")
                    ref_b.add_custom_emoji(g, gid)
                    ref_b.add_text(" ")
                    ref_b.add_bold(
                        L(
                            ref_lang,
                            f"Ты пригласил(а) {UserService.REFERRAL_THRESHOLD} человек!",
                            f"You've invited {UserService.REFERRAL_THRESHOLD} people!",
                        )
                    )
                    ref_b.add_text(
                        L(
                            ref_lang,
                            f"\n\nВ награду начислено {UserService.REFERRAL_REWARD_DAYS} дней премиума, "
                            "плюс скидка 50% на следующую покупку премиума (одноразово). "
                            "Посмотреть — команда /premium.",
                            f"\n\nAs a reward you got {UserService.REFERRAL_REWARD_DAYS} days of premium, "
                            "plus a one-time 50% discount on your next premium purchase. "
                            "Check it out via /premium.",
                        )
                    )
                    ref_text, ref_entities = ref_b.build()
                    try:
                        await callback.bot.send_message(
                            chat_id=referrer.telegram_id,
                            text=ref_text,
                            entities=ref_entities,
                            parse_mode=None,
                        )
                    except Exception:
                        pass  # пользователь мог заблокировать бота — не критично

    b = EntityTextBuilder()
    b.add_text(L(lang, "Готово! Пол установлен: ", "Done! Gender set to: "))
    key = "male" if gender == Gender.MALE else "female"
    glyph, cid = emoji(key)
    b.add_custom_emoji(glyph, cid)
    label = (
        L(lang, " Мужчина", " Man") if gender == Gender.MALE else L(lang, " Женщина", " Woman")
    )
    b.add_bold(label)
    b.add_text(
        L(
            lang,
            ".\n\nОсталось подключить меня как Telegram Business Bot — жми «Как подключить Business» "
            f"ниже, а потом пробуй команды вроде {settings.command_prefix}муа в ответ на сообщение.",
            ".\n\nNow connect me as a Telegram Business Bot — tap \"How to connect Business\" "
            f"below, then try a command like {settings.command_prefix}muah in reply to a message.",
        )
    )
    text, entities = b.build()

    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=main_menu_keyboard(db_user),
    )
    await callback.answer(L(lang, "Пол сохранён", "Gender saved"))


@router.callback_query(F.data == "menu:home")
async def cb_menu_home(callback: CallbackQuery, db_user: User) -> None:
    text, entities = _menu_home_payload(db_user.language)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=main_menu_keyboard(db_user),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:profile")
async def cb_menu_profile(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.profile import _format_profile_entities  # локальный импорт во избежание циклов

    lang = db_user.language
    service = UserService(session)
    stats = await service.get_stats(db_user)
    favorite = stats["favorite"] or L(lang, "ещё нет", "none yet")

    text, entities = _format_profile_entities(db_user, favorite)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=with_back_button(profile_keyboard(lang), lang),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:settings")
async def cb_menu_settings(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    b = EntityTextBuilder()
    glyph, cid = emoji("settings2")
    b.add_custom_emoji(glyph, cid)
    b.add_text(" ")
    b.add_bold(L(lang, "Настройки", "Settings"))
    text, entities = b.build()
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None,
        reply_markup=with_back_button(settings_keyboard(db_user), lang),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:commands")
async def cb_menu_commands(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    action_service = ActionService(session)
    text, entities = _format_commands_list(action_service, lang)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=back_only_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:howto")
async def cb_menu_howto(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    text, entities = _howto_text(lang)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW,
        reply_markup=back_only_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "menu:addrp")
async def cb_menu_addrp(callback: CallbackQuery, db_user: User, session: AsyncSession) -> None:
    from app.handlers.custom_rp import my_rp_screen  # локальный импорт во избежание циклов

    text, entities, keyboard = await my_rp_screen(db_user, session)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, link_preview_options=_NO_PREVIEW, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "menu:premium")
async def cb_menu_premium(callback: CallbackQuery, db_user: User) -> None:
    from app.handlers.premium import _buy_keyboard, _status_text  # локальный импорт во избежание циклов

    lang = db_user.language
    text, entities = _status_text(db_user)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, reply_markup=with_back_button(_buy_keyboard(db_user), lang)
    )
    await callback.answer()
