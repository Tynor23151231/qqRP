from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import User


def main_menu_keyboard(user: User) -> InlineKeyboardMarkup:
    premium_label = "💎 Премиум ✅" if user.has_premium else "💎 Премиум"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="menu:profile"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings"),
            ],
            [
                InlineKeyboardButton(text="📋 Список команд", callback_data="menu:commands"),
                InlineKeyboardButton(text="➕ Своё RP", callback_data="menu:addrp"),
            ],
            [
                InlineKeyboardButton(text=premium_label, callback_data="menu:premium"),
            ],
            [
                InlineKeyboardButton(text="📲 Как подключить Business", callback_data="menu:howto"),
            ],
        ]
    )


def back_to_menu_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:home")]


def with_back_button(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Добавляет строку с кнопкой возврата в главное меню к уже готовой клавиатуре."""
    return InlineKeyboardMarkup(
        inline_keyboard=[*keyboard.inline_keyboard, back_to_menu_row()]
    )


def back_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[back_to_menu_row()])
