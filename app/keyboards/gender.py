from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨 Мужчина", callback_data="gender:male"),
                InlineKeyboardButton(text="👩 Женщина", callback_data="gender:female"),
            ]
        ]
    )
