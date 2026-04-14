"""Custom aiogram filters."""

from aiogram.filters import BaseFilter
from aiogram.types import Message

from shad_poker_bot.config import AdminConfig


class IsAdmin(BaseFilter):
    """Pass only if sender's telegram_id is in the admin list."""

    def __init__(self, admin_cfg: AdminConfig) -> None:
        self.admin_ids = admin_cfg.admin_ids

    async def __call__(self, message: Message) -> bool:
        return message.from_user is not None and message.from_user.id in self.admin_ids
