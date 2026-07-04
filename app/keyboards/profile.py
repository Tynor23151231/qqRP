from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚻 Изменить пол", callback_data="profile:change_gender")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="profile:stats")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="profile:settings")],
        ]
    )
