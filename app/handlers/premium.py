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
from app.keyboards.menu import with_back_button
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="premium")

_PAYLOAD = "qqrp_premium_month"


def _buy_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Купить премиум за {settings.premium_price_stars} ⭐️",
                    callback_data="premium:buy",
                    icon_custom_emoji_id=emoji("premium")[1],
                    style="success",
                )
            ]
        ]
    )


def _status_text(user: User) -> tuple[str, list]:
    b = EntityTextBuilder()
    if user.has_premium:
        until = user.premium_until.strftime("%d.%m.%Y %H:%M UTC")
        g, gid = emoji("premium")
        b.add_custom_emoji(g, gid)
        b.add_text(" ")
        b.add_bold("У тебя активен премиум!")
        b.add_text(
            f"\n\nДействует до: {until}\n\n"
            f"Продлить ещё на {settings.premium_duration_days} дней можно уже сейчас — "
            "дни просто добавятся к текущему сроку."
        )
        return b.build()

    g, gid = emoji("lock")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold("Премиум-функции")
    b.add_text(
        f"\n\nЗа {settings.premium_price_stars} ⭐️ (Telegram Stars) на "
        f"{settings.premium_duration_days} дней открывается:\n"
        "• "
    )
    b.add_code(f"{settings.command_prefix}typing")
    b.add_text(" — постепенное \"печатание\" сообщения по буквам\n")
    b.add_text("• создание и переопределение своих RP-действий через ")
    b.add_code("/addrp")
    b.add_text("\n\nОплата происходит прямо в Telegram, без банковских карт и комиссий.")
    return b.build()


@router.message(Command("premium"))
async def cmd_premium(message: Message, db_user: User) -> None:
    text, entities = _status_text(db_user)
    await message.answer(
        text, entities=entities, parse_mode=None, reply_markup=with_back_button(_buy_keyboard())
    )


@router.callback_query(F.data == "premium:buy")
async def cb_buy_premium(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer_invoice(
        title="qqRP Premium — 1 месяц",
        description=(
            f"Открывает платные функции бота (например .typing) на "
            f"{settings.premium_duration_days} дней."
        ),
        payload=_PAYLOAD,
        currency="XTR",
        prices=[LabeledPrice(label="Премиум на месяц", amount=settings.premium_price_stars)],
    )


@router.pre_checkout_query()
async def on_pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    # Проверяем, что это наш payload, а не что-то постороннее — и подтверждаем оплату.
    ok = pre_checkout_query.invoice_payload == _PAYLOAD
    await pre_checkout_query.answer(ok=ok, error_message="Неизвестный товар. Попробуй ещё раз через /premium.")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, db_user: User, session: AsyncSession) -> None:
    user_service = UserService(session)
    until = await user_service.grant_premium(db_user, settings.premium_duration_days)
    await message.answer(
        "✅ <b>Оплата прошла!</b>\n\n"
        f"Премиум активен до {until.strftime('%d.%m.%Y %H:%M UTC')}.\n"
        "Теперь тебе доступна команда <code>.typing текст</code>."
    )
