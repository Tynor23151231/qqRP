from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import L
from app.models import User
from app.utils.premium_emoji import emoji


def _mark_icon(flag: bool) -> str:
    return emoji("check")[1] if flag else emoji("cross")[1]


def settings_keyboard(user: User) -> InlineKeyboardMarkup:
    lang = user.language
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=L(lang, "Сменить пол", "Change gender"),
                    callback_data="settings:change_gender",
                    icon_custom_emoji_id=emoji("change_gender")[1],
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{L(lang, 'Имя', 'Name')}: {user.display_name}",
                    callback_data="settings:change_name",
                    icon_custom_emoji_id=emoji("edit_name")[1],
                )
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Случайные анимации", "Random animations"),
                    callback_data="settings:toggle:random_animations",
                    icon_custom_emoji_id=_mark_icon(user.random_animations),
                    style="success" if user.random_animations else "danger",
                )
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Компактный режим", "Compact mode"),
                    callback_data="settings:toggle:compact_mode",
                    icon_custom_emoji_id=_mark_icon(user.compact_mode),
                    style="success" if user.compact_mode else "danger",
                )
            ],
            [
                InlineKeyboardButton(
                    text=L(lang, "Случайные шаблоны", "Random templates"),
                    callback_data="settings:toggle:random_templates",
                    icon_custom_emoji_id=_mark_icon(user.random_templates),
                    style="success" if user.random_templates else "danger",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{L(lang, 'Язык', 'Language')}: {user.language.upper()}",
                    callback_data="settings:language",
                    icon_custom_emoji_id=emoji("language")[1],
                )
            ],
        ]
    )
