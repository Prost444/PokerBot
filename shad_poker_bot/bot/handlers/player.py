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
        await message.answer(f"Ты уже зарегистрирован как <b>{existing.display_name}</b>.")
        return

    name = command.args.strip() if command.args else None
    if not name:
        # Fallback: Telegram first_name
        name = user.full_name or user.username or f"Player_{user.id}"

    player = await repo.add_player(
        telegram_id=user.id,
        display_name=name,
        username=user.username,
    )
    await message.answer(
        f"Добро пожаловать, <b>{player.display_name}</b>! 🎉\n"
        f"Твой начальный рейтинг: <code>{player.elo:.0f}</code>\n\n"
        "Жди создания игры или используй /join когда игра откроется."
    )


@router.message(Command("join"))
async def cmd_join(
    message: Message, repo: Repository, game_service: GameService
) -> None:
    user = message.from_user
    if not user:
        return

    try:
        game, player = await game_service.join_game(user.id)
    except GameError as e:
        await message.answer(str(e))
        return

    late = " (поздний вход)" if game.status == "active" else ""
    await message.answer(
        f"<b>{player.display_name}</b> в игре #{game.id}!{late} 🃏"
    )


@router.message(Command("stats"))
async def cmd_stats(
    message: Message, command: CommandObject, repo: Repository
) -> None:
    user = message.from_user
    if not user:
        return

    # /stats or /stats @username — in future we can look up other players
    player = await repo.get_player_by_tg(user.id)
    if not player:
        await message.answer("Ты ещё не зарегистрирован. Используй /register")
        return

    history = await repo.get_player_history(player.id, limit=10)
    await message.answer(player_stats_text(player, history))
