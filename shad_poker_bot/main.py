"""Entry point — wire everything together and start polling."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from shad_poker_bot.bot.handlers import admin_router, common_router, player_router
from shad_poker_bot.config import load_config
from shad_poker_bot.db.models import init_db
from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameService


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        stream=sys.stdout,
    )
    log = logging.getLogger("shad_poker")

    cfg = load_config()
    if not cfg.bot.token:
        log.error("BOT_TOKEN is not set. Export it or add to .env")
        sys.exit(1)

    # ── Database ────────────────────────────────────────────────────
    db = await init_db(cfg.db.path)
    repo = Repository(db)
    game_service = GameService(repo, cfg.rating)

    # ── Bot & dispatcher ────────────────────────────────────────────
    bot = Bot(
        token=cfg.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # Inject dependencies into every handler via middleware-style kwargs
    dp.update.outer_middleware.register(_DependencyMiddleware(repo, game_service, cfg.admin))

    dp.include_router(common_router)
    dp.include_router(player_router)
    dp.include_router(admin_router)

    # ── Command menu (the "/" hint list in Telegram) ─────────────────
    await bot.set_my_commands([
        BotCommand(command="join", description="Join current game"),
        BotCommand(command="rating", description="Leaderboard"),
        BotCommand(command="stats", description="Your statistics"),
        BotCommand(command="game", description="Current game status"),
        BotCommand(command="tables", description="Table seating & status"),
        BotCommand(command="new_game", description="Create a game evening"),
        BotCommand(command="go", description="Start game & generate seating"),
        BotCommand(command="ko", description="Record a knockout"),
        BotCommand(command="chips", description="Record chip count"),
        BotCommand(command="open_table", description="Open a new table"),
        BotCommand(command="close_table", description="Close table & calc ratings"),
        BotCommand(command="finish", description="Finish evening"),
        BotCommand(command="help", description="All commands"),
    ])

    log.info("Bot starting — polling…")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close()


class _DependencyMiddleware:
    """Tiny middleware that puts repo / game_service / admin_cfg into handler kwargs."""

    def __init__(self, repo: Repository, game_service: GameService, admin_cfg) -> None:
        self.repo = repo
        self.game_service = game_service
        self.admin_cfg = admin_cfg

    async def __call__(self, handler, event, data: dict):
        data["repo"] = self.repo
        data["game_service"] = self.game_service
        data["admin_cfg"] = self.admin_cfg
        return await handler(event, data)


if __name__ == "__main__":
    asyncio.run(main())
