from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.i18n import L
from app.utils.premium_emoji import emoji


def subscription_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Подписаться на канал", "Subscribe to the channel"),
                    url=f"https://t.me/{settings.required_channel_username}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Я подписался, проверить", "I subscribed, check"),
                    callback_data="check_subscription",
                    icon_custom_emoji_id=emoji("check")[1],
                )
            ],
        ]
    )
