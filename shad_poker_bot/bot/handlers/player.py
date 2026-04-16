"""Player-facing commands: /register, /join, /stats."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from shad_poker_bot.bot.formatting import player_stats_text
from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameError, GameService

router = Router(name="player")


@router.message(Command("register"))
async def cmd_register(
    message: Message, command: CommandObject, repo: Repository,
) -> None:
    user = message.from_user
    if not user:
        return

    existing = await repo.get_player_by_tg(user.id)
    if existing:
        await message.answer(
            f"You are already registered as <b>{existing.display_name}</b>.",
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
        "Wait for a game to be created or use /join when a game opens.",
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

    # For late join without a table number, show table buttons
    game = await repo.get_active_game()
    if game and game.status == "active" and table_number is None:
        active_tables = await repo.get_active_tables(game.id)
        if active_tables:
            buttons = []
            for t in active_tables:
                t_players = await repo.get_table_players(t.id)
                count = len(t_players)
                if count < 9:
                    buttons.append([InlineKeyboardButton(
                        text=f"Table {t.table_number} ({count}/9)",
                        callback_data=f"jt:{t.table_number}",
                    )])
            if buttons:
                kb = InlineKeyboardMarkup(inline_keyboard=buttons)
                await message.answer(
                    "Choose a table to join:", reply_markup=kb,
                )
                return
            await message.answer(
                "All tables are full. Ask admin to open a new one.",
            )
            return

    try:
        game_ret, player, assigned = await game_service.join_game(
            user.id, table_number,
        )
    except GameError as e:
        await message.answer(str(e))
        return

    late = " (late join)" if game_ret.status == "active" else ""
    table_info = f"\nSeated at table {assigned}" if assigned else ""
    await message.answer(
        f"<b>{player.display_name}</b> joined game #{game_ret.id}!"
        f"{late} 🃏{table_info}",
    )


@router.callback_query(F.data.startswith("jt:"))
async def cb_join_table(
    callback: CallbackQuery,
    repo: Repository,
    game_service: GameService,
) -> None:
    if not callback.from_user:
        return

    table_number = int(callback.data.split(":")[1])  # type: ignore[union-attr]

    try:
        game, player, assigned = await game_service.join_game(
            callback.from_user.id, table_number,
        )
    except GameError as e:
        await callback.answer(str(e), show_alert=True)
        return

    await callback.message.edit_text(  # type: ignore[union-attr]
        f"<b>{player.display_name}</b> joined game #{game.id}!"
        f" (late join) 🃏\nSeated at table {assigned}",
    )
    await callback.answer()


@router.message(Command("stats"))
async def cmd_stats(
    message: Message, command: CommandObject, repo: Repository,
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
