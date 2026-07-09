from aiogram import Router

from app.handlers import admin, custom_rp, group_actions, name_badge, premium, profile, referral, settings, start, stats
from app.handlers.business import actions as business_actions
from app.handlers.business import connection as business_connection


def get_root_router() -> Router:
    """Единая точка сборки всех роутеров бота в правильном порядке."""
    root = Router(name="root")

    # Обычные приватные чаты с ботом
    root.include_router(start.router)
    root.include_router(profile.router)
    root.include_router(stats.router)
    root.include_router(settings.router)
    root.include_router(custom_rp.router)
    root.include_router(premium.router)
    root.include_router(referral.router)
    root.include_router(name_badge.router)
    root.include_router(admin.router)

    # Обычные группы, где бот состоит участником
    root.include_router(group_actions.router)

    # Business API — подключение и dot-команды
    root.include_router(business_connection.router)
    root.include_router(business_actions.router)

    return root
