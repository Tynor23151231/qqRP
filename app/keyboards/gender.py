from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import L
from app.utils.premium_emoji import emoji


def gender_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Мужчина", "Man"), callback_data="gender:male", icon_custom_emoji_id=emoji("male")[1]
                ),
                InlineKeyboardButton(
                    text=L(lang, "Женщина", "Woman"),
                    callback_data="gender:female",
                    icon_custom_emoji_id=emoji("female")[1],
                ),
            ]
        ]
    )
