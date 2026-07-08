from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.i18n import L
from app.keyboards.menu import with_back_button
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="premium")

_PAYLOAD = "qqrp_premium_month"
_PAYLOAD_DISCOUNT = "qqrp_premium_month_discount50"


def _price_for(user: User) -> int:
    if user.discount_pending:
        return max(1, settings.premium_price_stars // 2)
    return settings.premium_price_stars


def _buy_keyboard(user: User) -> InlineKeyboardMarkup:
    lang = user.language
    price = _price_for(user)
    if user.discount_pending:
        label = L(
            lang,
            f"Купить со скидкой 50% за {price} ⭐️",
            f"Buy with 50% off for {price} ⭐️",
        )
    else:
        label = L(lang, f"Купить премиум за {price} ⭐️", f"Buy premium for {price} ⭐️")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data="premium:buy",
                    icon_custom_emoji_id=emoji("premium")[1],
                    style="success",
                )
            ]
        ]
    )


def _status_text(user: User) -> tuple[str, list]:
    lang = user.language
    b = EntityTextBuilder()
    if user.has_premium:
        until = user.premium_until.strftime("%d.%m.%Y %H:%M UTC")
        g, gid = emoji("premium")
        b.add_custom_emoji(g, gid)
        b.add_text(" ")
        b.add_bold(L(lang, "У тебя активен премиум!", "Your premium is active!"))
        b.add_text(
            L(
                lang,
                f"\n\nДействует до: {until}\n\n"
                f"Продлить ещё на {settings.premium_duration_days} дней можно уже сейчас — "
                "дни просто добавятся к текущему сроку.",
                f"\n\nValid until: {until}\n\n"
                f"You can extend it by another {settings.premium_duration_days} days right now — "
                "the days will simply be added to the current period.",
            )
        )
        if user.discount_pending:
            b.add_text(
                L(
                    lang,
                    f"\n\n🎁 У тебя есть скидка 50% на следующую покупку (сработает автоматически).",
                    f"\n\n🎁 You have a 50% discount on your next purchase (applied automatically).",
                )
            )
        return b.build()

    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Премиум-функции", "Premium features"))
    b.add_text(
        L(
            lang,
            f"\n\nЗа {settings.premium_price_stars} ⭐️ (Telegram Stars) на "
            f"{settings.premium_duration_days} дней открывается:\n• ",
            f"\n\nFor {settings.premium_price_stars} ⭐️ (Telegram Stars) you unlock for "
            f"{settings.premium_duration_days} days:\n• ",
        )
    )
    b.add_code(f"{settings.command_prefix}typing")
    b.add_text(
        L(
            lang,
            " — постепенное \"печатание\" сообщения по буквам\n• создание и переопределение своих RP-действий через ",
            " — gradually \"typing out\" a message letter by letter\n• creating and overriding your own RP actions via ",
        )
    )
    b.add_code("/addrp")
    b.add_text(
        L(
            lang,
            "\n\nОплата происходит прямо в Telegram, без банковских карт и комиссий.",
            "\n\nPayment happens right inside Telegram, no bank cards or fees.",
        )
    )
    if user.discount_pending:
        b.add_text(
            L(
                lang,
                "\n\n🎁 У тебя есть скидка 50% на покупку — сработает автоматически.",
                "\n\n🎁 You have a 50% discount on your purchase — it applies automatically.",
            )
        )
    return b.build()


@router.message(Command("premium"))
async def cmd_premium(message: Message, db_user: User) -> None:
    lang = db_user.language
    text, entities = _status_text(db_user)
    await message.answer(
        text, entities=entities, parse_mode=None, reply_markup=with_back_button(_buy_keyboard(db_user), lang)
    )


@router.callback_query(F.data == "premium:buy")
async def cb_buy_premium(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    price = _price_for(db_user)
    payload = _PAYLOAD_DISCOUNT if db_user.discount_pending else _PAYLOAD
    await callback.answer()
    await callback.message.answer_invoice(
        title=L(lang, "qqRP Premium — 1 месяц", "qqRP Premium — 1 month"),
        description=L(
            lang,
            f"Открывает платные функции бота (например .typing) на "
            f"{settings.premium_duration_days} дней.",
            f"Unlocks the bot's paid features (e.g. .typing) for "
            f"{settings.premium_duration_days} days.",
        ),
        payload=payload,
        currency="XTR",
        prices=[
            LabeledPrice(
                label=L(lang, "Премиум на месяц", "Premium for a month"),
                amount=price,
            )
        ],
    )


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # Проверяем, что это наш payload, а не что-то постороннее — и подтверждаем оплату.
    ok = pre_checkout_query.invoice_payload in (_PAYLOAD, _PAYLOAD_DISCOUNT)
    await pre_checkout_query.answer(ok=ok, error_message="Unknown product. Try again via /premium.")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    user_service = UserService(session)
    until = await user_service.grant_premium(db_user, settings.premium_duration_days)
    if message.successful_payment.invoice_payload == _PAYLOAD_DISCOUNT:
        await user_service.consume_discount(db_user)
    await message.answer(
        L(
            lang,
            f"✅ <b>Оплата прошла!</b>\n\n"
            f"Премиум активен до {until.strftime('%d.%m.%Y %H:%M UTC')}.\n"
            "Теперь тебе доступна команда <code>.typing текст</code>.",
            f"✅ <b>Payment successful!</b>\n\n"
            f"Premium is active until {until.strftime('%d.%m.%Y %H:%M UTC')}.\n"
            "You now have access to <code>.typing text</code>.",
        )
    )
