"""Tests for custom aiogram filters."""

from unittest.mock import MagicMock

from shad_poker_bot.bot.filters import IsAdmin
from shad_poker_bot.config import AdminConfig


class TestIsAdmin:
    async def test_admin_passes(self):
        cfg = AdminConfig(admin_ids=[12345])
        flt = IsAdmin(cfg)

        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = 12345

        assert await flt(msg) is True

    async def test_non_admin_fails(self):
        cfg = AdminConfig(admin_ids=[12345])
        flt = IsAdmin(cfg)

        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = 99999

        assert await flt(msg) is False

    async def test_no_user_fails(self):
        cfg = AdminConfig(admin_ids=[12345])
        flt = IsAdmin(cfg)

        msg = MagicMock()
        msg.from_user = None

        assert await flt(msg) is False

    async def test_empty_admin_list(self):
        cfg = AdminConfig(admin_ids=[])
        flt = IsAdmin(cfg)

        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = 12345

        assert await flt(msg) is False

    async def test_multiple_admins(self):
        cfg = AdminConfig(admin_ids=[111, 222, 333])
        flt = IsAdmin(cfg)

        msg = MagicMock()
        msg.from_user = MagicMock()
        msg.from_user.id = 222

        assert await flt(msg) is True
