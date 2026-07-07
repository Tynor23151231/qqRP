from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.utils.premium_emoji import emoji


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подписаться на канал",
                    url=f"https://t.me/{settings.required_channel_username}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Я подписался, проверить",
                    callback_data="check_subscription",
                    icon_custom_emoji_id=emoji("check")[1],
                )
            ],
        ]
    )
