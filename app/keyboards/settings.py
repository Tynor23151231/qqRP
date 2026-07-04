from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import User


def _mark(flag: bool) -> str:
    return "✅" if flag else "❌"


def settings_keyboard(user: User) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚻 Сменить пол", callback_data="settings:change_gender")],
            [
                InlineKeyboardButton(
                    text=f"{_mark(user.random_animations)} Случайные анимации",
                    callback_data="settings:toggle:random_animations",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{_mark(user.compact_mode)} Компактный режим",
                    callback_data="settings:toggle:compact_mode",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{_mark(user.random_templates)} Случайные шаблоны",
                    callback_data="settings:toggle:random_templates",
                )
            ],
            [InlineKeyboardButton(text=f"🌐 Язык: {user.language.upper()}", callback_data="settings:language")],
        ]
    )
