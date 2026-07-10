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

_PAYLOAD_PLUS = "qqrp_premium_plus"
_PAYLOAD_PLUS_DISCOUNT = "qqrp_premium_plus_discount50"
_PAYLOAD_BASIC = "qqrp_premium_basic"

_TIER_NAMES = {
    "plus": ("Премиум+", "Premium+"),
    "basic": ("Премиум", "Premium"),
}


def _plus_price(user: User) -> int:
    if user.discount_active:
        return max(1, settings.premium_price_stars // 2)
    return settings.premium_price_stars


def _buy_keyboard(user: User) -> InlineKeyboardMarkup:
    lang = user.language
    plus_price = _plus_price(user)
    plus_label = (
        L(lang, f"Премиум+ со скидкой 50% — {plus_price} ⭐️", f"Premium+ with 50% off — {plus_price} ⭐️")
        if user.discount_active
        else L(lang, f"Купить Премиум+ за {plus_price} ⭐️", f"Buy Premium+ for {plus_price} ⭐️")
    )
    basic_label = L(
        lang,
        f"Купить Премиум за {settings.basic_premium_price_stars} ⭐️",
        f"Buy Premium for {settings.basic_premium_price_stars} ⭐️",
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=plus_label,
                    callback_data="premium:buy:plus",
                    icon_custom_emoji_id=emoji("premium")[1],
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text=basic_label,
                    callback_data="premium:buy:basic",
                )
            ],
        ]
    )


def _status_text(user: User) -> tuple[str, list]:
    lang = user.language
    b = EntityTextBuilder()
    if user.has_premium:
        tier_ru, tier_en = _TIER_NAMES.get(user.premium_tier or "basic", _TIER_NAMES["basic"])
        tier_name = L(lang, tier_ru, tier_en)
        until = user.premium_until.strftime("%d.%m.%Y %H:%M UTC")
        g, gid = emoji("premium")
        b.add_custom_emoji(g, gid)
        b.add_text(" ")
        b.add_bold(L(lang, f"У тебя активен {tier_name}!", f"Your {tier_name} is active!"))
        b.add_text(L(lang, f"\n\nДействует до: {until}\n\n", f"\n\nValid until: {until}\n\n"))

        if user.premium_tier == "plus":
            b.add_text(
                L(
                    lang,
                    "Доступно: безлимит своих RP-действий через /addrp + "
                    f"{settings.command_prefix}typing.",
                    "Included: unlimited custom RP actions via /addrp + "
                    f"{settings.command_prefix}typing.",
                )
            )
        else:
            b.add_text(
                L(
                    lang,
                    f"Доступно: до {settings.basic_premium_max_custom_rp} своих RP-действий через "
                    "/addrp. Апгрейд до Премиум+ снимет это ограничение и добавит "
                    f"{settings.command_prefix}typing.",
                    f"Included: up to {settings.basic_premium_max_custom_rp} custom RP actions via "
                    "/addrp. Upgrading to Premium+ removes this limit and adds "
                    f"{settings.command_prefix}typing.",
                )
            )

        if user.discount_active:
            b.add_text(
                L(
                    lang,
                    "\n\n🎁 У тебя есть скидка 50% на Премиум+ — сработает автоматически при покупке.",
                    "\n\n🎁 You have a 50% discount on Premium+ — it applies automatically on purchase.",
                )
            )
        return b.build()

    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Премиум-функции", "Premium features"))
    b.add_text(L(lang, "\n\nДва уровня на выбор:\n\n", "\n\nTwo tiers to choose from:\n\n"))

    b.add_bold(L(lang, f"💎 Премиум+ — {settings.premium_price_stars} ⭐️", f"💎 Premium+ — {settings.premium_price_stars} ⭐️"))
    b.add_text(L(lang, f" ({settings.premium_duration_days} дней)\n", f" ({settings.premium_duration_days} days)\n"))
    b.add_text(L(lang, "• Безлимит своих RP-действий через ", "• Unlimited custom RP actions via "))
    b.add_code("/addrp")
    b.add_text(L(lang, "\n• ", "\n• "))
    b.add_code(f"{settings.command_prefix}typing")
    b.add_text(
        L(lang, " — постепенное \"печатание\" сообщения по буквам\n\n", " — gradually \"typing out\" a message letter by letter\n\n")
    )

    b.add_bold(
        L(
            lang,
            f"✨ Премиум — {settings.basic_premium_price_stars} ⭐️",
            f"✨ Premium — {settings.basic_premium_price_stars} ⭐️",
        )
    )
    b.add_text(L(lang, f" ({settings.premium_duration_days} дней)\n", f" ({settings.premium_duration_days} days)\n"))
    b.add_text(
        L(
            lang,
            f"• До {settings.basic_premium_max_custom_rp} своих RP-действий через ",
            f"• Up to {settings.basic_premium_max_custom_rp} custom RP actions via ",
        )
    )
    b.add_code("/addrp")
    b.add_text(L(lang, "\n\n", "\n\n"))

    b.add_text(
        L(
            lang,
            "Оплата происходит прямо в Telegram, без банковских карт и комиссий.",
            "Payment happens right inside Telegram, no bank cards or fees.",
        )
    )
    if user.discount_active:
        b.add_text(
            L(
                lang,
                "\n\n🎁 У тебя есть скидка 50% на Премиум+ — сработает автоматически.",
                "\n\n🎁 You have a 50% discount on Premium+ — it applies automatically.",
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


@router.callback_query(F.data == "premium:buy:plus")
async def cb_buy_plus(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    price = _plus_price(db_user)
    payload = _PAYLOAD_PLUS_DISCOUNT if db_user.discount_active else _PAYLOAD_PLUS
    await callback.answer()
    await callback.message.answer_invoice(
        title=L(lang, "qqRP Премиум+", "qqRP Premium+"),
        description=L(
            lang,
            f"Безлимит своих RP-действий + {settings.command_prefix}typing на "
            f"{settings.premium_duration_days} дней.",
            f"Unlimited custom RP actions + {settings.command_prefix}typing for "
            f"{settings.premium_duration_days} days.",
        ),
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label=L(lang, "Премиум+", "Premium+"), amount=price)],
    )


@router.callback_query(F.data == "premium:buy:basic")
async def cb_buy_basic(callback: CallbackQuery, db_user: User) -> None:
    lang = db_user.language
    await callback.answer()
    await callback.message.answer_invoice(
        title=L(lang, "qqRP Премиум", "qqRP Premium"),
        description=L(
            lang,
            f"До {settings.basic_premium_max_custom_rp} своих RP-действий через /addrp на "
            f"{settings.premium_duration_days} дней.",
            f"Up to {settings.basic_premium_max_custom_rp} custom RP actions via /addrp for "
            f"{settings.premium_duration_days} days.",
        ),
        payload=_PAYLOAD_BASIC,
        currency="XTR",
        prices=[
            LabeledPrice(label=L(lang, "Премиум", "Premium"), amount=settings.basic_premium_price_stars)
        ],
    )


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # Проверяем, что это наш payload, а не что-то постороннее — и подтверждаем оплату.
    ok = pre_checkout_query.invoice_payload in (_PAYLOAD_PLUS, _PAYLOAD_PLUS_DISCOUNT, _PAYLOAD_BASIC)
    await pre_checkout_query.answer(ok=ok, error_message="Unknown product. Try again via /premium.")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, db_user: User, session: AsyncSession) -> None:
    lang = db_user.language
    payload = message.successful_payment.invoice_payload
    user_service = UserService(session)

    tier = "basic" if payload == _PAYLOAD_BASIC else "plus"
    until = await user_service.grant_premium(db_user, settings.premium_duration_days, tier=tier)

    if payload == _PAYLOAD_PLUS_DISCOUNT:
        await user_service.consume_discount(db_user)

    tier_ru, tier_en = _TIER_NAMES[tier]
    tier_name = L(lang, tier_ru, tier_en)
    extra = (
        L(lang, "Теперь тебе доступна команда <code>.typing текст</code> и безлимит своих RP.", "You now have access to <code>.typing text</code> and unlimited custom RPs.")
        if tier == "plus"
        else L(
            lang,
            f"Теперь можно создать до {settings.basic_premium_max_custom_rp} своих RP-действий через /addrp.",
            f"You can now create up to {settings.basic_premium_max_custom_rp} custom RP actions via /addrp.",
        )
    )
    await message.answer(
        L(
            lang,
            f"✅ <b>Оплата прошла!</b>\n\n{tier_name} активен до "
            f"{until.strftime('%d.%m.%Y %H:%M UTC')}.\n{extra}",
            f"✅ <b>Payment successful!</b>\n\n{tier_name} is active until "
            f"{until.strftime('%d.%m.%Y %H:%M UTC')}.\n{extra}",
        )
    )
