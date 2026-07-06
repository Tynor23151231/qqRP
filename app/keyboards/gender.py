from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.utils.premium_emoji import emoji


def gender_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Мужчина", callback_data="gender:male", icon_custom_emoji_id=emoji("male")[1]
                ),
                InlineKeyboardButton(
                    text="Женщина", callback_data="gender:female", icon_custom_emoji_id=emoji("female")[1]
                ),
            ]
        ]
    )
