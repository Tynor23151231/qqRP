from __future__ import annotations

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User
from app.services.user_service import UserService

router = Router(name="admin")

_HELP_TEXT = (
    "🛠 <b>Админ-консоль qqRP Bot</b>\n\n"
    "<code>/grant_premium @username [дней]</code> — выдать/продлить премиум "
    "(по умолчанию 30 дней, дни прибавляются к текущим, если премиум уже активен)\n"
    "<code>/grant_premium 123456789 [дней]</code> — то же самое по числовому ID\n"
    "<code>/revoke_premium @username</code> — снять премиум досрочно\n"
    "<code>/premium_list</code> — список всех активных премиум-пользователей\n"
    "<code>/find_user @username</code> — быстрая информация о пользователе"
)


async def _resolve_target_user(bot, session: AsyncSession, raw: str) -> User | None:
    """
    Находит пользователя по '@username' или числовому telegram_id.
    Если пользователя ещё нет в нашей БД, пробуем создать запись через bot.get_chat —
    но это сработает только если пользователь уже хоть раз взаимодействовал с ботом
    или @username публичный (иначе Telegram не отдаст chat по ID постороннему боту).
    """
    raw = raw.strip()
    user_service = UserService(session)

    if raw.startswith("@"):
        username = raw.lstrip("@")
        user = await user_service.get_by_username(username)
        if user is not None:
            return user
        try:
            chat = await bot.get_chat(f"@{username}")
        except TelegramBadRequest:
            return None
        user, _ = await user_service.get_or_create(
            telegram_id=chat.id,
            first_name=getattr(chat, "first_name", None) or username,
            username=chat.username or username,
        )
        return user

    if raw.isdigit():
        telegram_id = int(raw)
        user = await user_service.get_by_telegram_id(telegram_id)
        if user is not None:
            return user
        try:
            chat = await bot.get_chat(telegram_id)
        except TelegramBadRequest:
            return None
        user, _ = await user_service.get_or_create(
            telegram_id=chat.id,
            first_name=getattr(chat, "first_name", None) or str(telegram_id),
            username=chat.username,
        )
        return user

    return None


def _not_found_text() -> str:
    return (
        "❌ Не удалось найти пользователя.\n"
        "Работает по @username или по ID, но по ID — только если человек уже "
        "хоть раз написал этому боту (иначе Telegram не даёт ботам искать чаты по ID)."
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    await message.answer(_HELP_TEXT)


@router.message(Command("grant_premium"))
async def cmd_grant_premium(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not settings.is_admin(message.from_user.id):
        return

    if not command.args:
        await message.answer("Использование: /grant_premium @username_или_id [дней]")
        return

    parts = command.args.split()
    target_raw = parts[0]
    days = settings.premium_duration_days
    if len(parts) > 1 and parts[1].isdigit():
        days = int(parts[1])

    target = await _resolve_target_user(message.bot, session, target_raw)
    if target is None:
        await message.answer(_not_found_text())
        return

    user_service = UserService(session)
    until = await user_service.grant_premium(target, days)
    await message.answer(
        f"✅ Премиум выдан пользователю {target.display_name} "
        f"(id {target.telegram_id}) до {until.strftime('%d.%m.%Y %H:%M UTC')}."
    )


@router.message(Command("revoke_premium"))
async def cmd_revoke_premium(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not settings.is_admin(message.from_user.id):
        return

    if not command.args:
        await message.answer("Использование: /revoke_premium @username_или_id")
        return

    target = await _resolve_target_user(message.bot, session, command.args.split()[0])
    if target is None:
        await message.answer(_not_found_text())
        return

    user_service = UserService(session)
    await user_service.revoke_premium(target)
    await message.answer(f"🗑 Премиум снят у {target.display_name} (id {target.telegram_id}).")


@router.message(Command("premium_list"))
async def cmd_premium_list(message: Message, session: AsyncSession) -> None:
    if not settings.is_admin(message.from_user.id):
        return

    user_service = UserService(session)
    users = await user_service.list_premium_users()
    if not users:
        await message.answer("Премиум-пользователей с активной подпиской пока нет.")
        return

    lines = [
        f"• {u.display_name} (@{u.username or '—'}, id {u.telegram_id}) — "
        f"до {u.premium_until.strftime('%d.%m.%Y %H:%M UTC')}"
        for u in users
    ]
    await message.answer("💎 <b>Активные премиум-пользователи:</b>\n" + "\n".join(lines))


@router.message(Command("find_user"))
async def cmd_find_user(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not settings.is_admin(message.from_user.id):
        return

    if not command.args:
        await message.answer("Использование: /find_user @username_или_id")
        return

    target = await _resolve_target_user(message.bot, session, command.args.split()[0])
    if target is None:
        await message.answer(_not_found_text())
        return

    premium_line = (
        f"до {target.premium_until.strftime('%d.%m.%Y %H:%M UTC')}" if target.has_premium else "нет"
    )
    await message.answer(
        f"👤 <b>{target.display_name}</b>\n"
        f"ID: <code>{target.telegram_id}</code>\n"
        f"Username: @{target.username or '—'}\n"
        f"Пол: {target.gender.value}\n"
        f"Премиум: {premium_line}\n"
        f"Действий выполнено: {target.total_actions}\n"
        f"Зарегистрирован: {target.registered_at.strftime('%d.%m.%Y')}"
    )
