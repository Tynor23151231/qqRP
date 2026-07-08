from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import L
from app.keyboards.menu import back_only_keyboard
from app.models import User
from app.services.user_service import UserService
from app.utils.entity_builder import EntityTextBuilder
from app.utils.premium_emoji import emoji

router = Router(name="referral")


async def _referral_payload(message_bot, db_user: User) -> tuple[str, list]:
    lang = db_user.language
    me = await message_bot.get_me()
    link = f"https://t.me/{me.username}?start={db_user.telegram_id}"

    threshold = UserService.REFERRAL_THRESHOLD
    reward_days = UserService.REFERRAL_REWARD_DAYS
    count = min(db_user.referral_count, threshold)

    b = EntityTextBuilder()
    g, gid = emoji("premium")
    b.add_custom_emoji(g, gid)
    b.add_text(" ")
    b.add_bold(L(lang, "Реферальная программа", "Referral program"))
    b.add_text(
        L(
            lang,
            f"\n\nПригласи {threshold} друзей по своей ссылке — и получишь {reward_days} дней "
            "премиума плюс одноразовую скидку 50% на покупку премиума. Засчитываются только "
            "те, кто реально начал пользоваться ботом (выбрал пол в /start).\n\n",
            f"\n\nInvite {threshold} friends with your link and get {reward_days} days of premium "
            "plus a one-time 50% discount on a premium purchase. Only people who actually start "
            "using the bot (pick a gender in /start) count.\n\n",
        )
    )
    b.add_text(L(lang, "Твоя ссылка:\n", "Your link:\n"))
    b.add_code(link)

    b.add_text(L(lang, f"\n\nПрогресс: {count}/{threshold}", f"\n\nProgress: {count}/{threshold}"))

    if db_user.referral_reward_claimed:
        b.add_text(
            L(
                lang,
                "\n✅ Награда уже получена — акция одноразовая, но приглашать друзей можно и дальше.",
                "\n✅ Reward already claimed — it's a one-time promo, but you can keep inviting friends.",
            )
        )
    if db_user.discount_pending:
        b.add_text(
            L(
                lang,
                "\n🎁 У тебя есть неиспользованная скидка 50% — сработает автоматически при покупке в /premium.",
                "\n🎁 You have an unused 50% discount — it will apply automatically when buying in /premium.",
            )
        )

    return b.build()


@router.message(Command("invite"))
async def cmd_invite(message: Message, db_user: User) -> None:
    text, entities = await _referral_payload(message.bot, db_user)
    await message.answer(
        text, entities=entities, parse_mode=None, reply_markup=back_only_keyboard(db_user.language)
    )


@router.callback_query(F.data == "menu:referral")
async def cb_menu_referral(callback: CallbackQuery, db_user: User) -> None:
    text, entities = await _referral_payload(callback.bot, db_user)
    await callback.message.edit_text(
        text, entities=entities, parse_mode=None, reply_markup=back_only_keyboard(db_user.language)
    )
    await callback.answer()
