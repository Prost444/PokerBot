"""Player-facing commands: /register, /join, /stats."""

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from shad_poker_bot.bot.formatting import player_stats_text
from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameError, GameService

router = Router(name="player")


@router.message(Command("register"))
async def cmd_register(
    message: Message, command: CommandObject, repo: Repository
) -> None:
    user = message.from_user
    if not user:
        return

    existing = await repo.get_player_by_tg(user.id)
    if existing:
        await message.answer(
            f"You are already registered as <b>{existing.display_name}</b>."
        )
        return

    name = command.args.strip() if command.args else None
    if not name:
        name = user.full_name or user.username or f"Player_{user.id}"

    player = await repo.add_player(
        telegram_id=user.id,
        display_name=name,
        username=user.username,
    )
    await message.answer(
        f"Welcome, <b>{player.display_name}</b>! 🎉\n"
        f"Your starting rating: <code>{player.elo:.0f}</code>\n\n"
        "Wait for a game to be created or use /join when a game opens."
    )


@router.message(Command("join"))
async def cmd_join(
    message: Message,
    command: CommandObject,
    repo: Repository,
    game_service: GameService,
) -> None:
    user = message.from_user
    if not user:
        return

    # Parse optional table number: /join or /join 2
    table_number: int | None = None
    args = (command.args or "").strip()
    if args and args.isdigit():
        table_number = int(args)

    try:
        game, player, assigned = await game_service.join_game(
            user.id, table_number,
        )
    except GameError as e:
        await message.answer(str(e))
        return

    late = " (late join)" if game.status == "active" else ""
    table_info = f"\nSeated at table {assigned}" if assigned else ""
    await message.answer(
        f"<b>{player.display_name}</b> joined game #{game.id}!"
        f"{late} 🃏{table_info}"
    )


@router.message(Command("stats"))
async def cmd_stats(
    message: Message, command: CommandObject, repo: Repository
) -> None:
    user = message.from_user
    if not user:
        return

    player = await repo.get_player_by_tg(user.id)
    if not player:
        await message.answer("You are not registered yet. Use /register")
        return

    history = await repo.get_player_history(player.id, limit=10)
    await message.answer(player_stats_text(player, history))
