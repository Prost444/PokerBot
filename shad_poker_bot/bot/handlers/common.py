"""Public commands available to everyone: /start, /help, /rating, /game, /tables."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from shad_poker_bot.bot.formatting import leaderboard_text, tables_status_text
from shad_poker_bot.db.repository import Repository

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, repo: Repository) -> None:
    player = await repo.get_player_by_tg(message.from_user.id)  # type: ignore[union-attr]
    if player:
        await message.answer(
            f"Welcome back, <b>{player.display_name}</b>! "
            f"Your rating: <code>{player.elo:.0f}</code>\n\n"
            "Use /help for a list of commands."
        )
    else:
        await message.answer(
            "Welcome to <b>YSDA Poker</b>! 🃏\n\n"
            "Register: /register YourName\n"
            "Full command list: /help"
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>🃏 YSDA Poker — commands</b>\n\n"
        "<b>For everyone:</b>\n"
        "/register Name — register\n"
        "/join [N] — join current game (N = table number for late join)\n"
        "/rating — leaderboard\n"
        "/stats — your statistics\n"
        "/game — current game status\n"
        "/tables — table status and seating\n\n"
        "<b>Admin only:</b>\n"
        "/new_game [regular|tournament] [snake|divisional] — create a game\n"
        "/go — start the game (generate seating)\n"
        "/ko @eliminated @eliminator — record a knockout\n"
        "/chips @player amount — record chip count\n"
        "/open_table — open a new table\n"
        "/close_table N — close table N and calculate ratings\n"
        "/finish — finish the game and show results\n"
        "/cancel — cancel the current game"
    )


@router.message(Command("rating"))
async def cmd_rating(message: Message, repo: Repository) -> None:
    players = await repo.get_leaderboard(limit=20)
    await message.answer(leaderboard_text(players))


@router.message(Command("game"))
async def cmd_game_status(message: Message, repo: Repository) -> None:
    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game right now.")
        return

    players = await repo.get_game_players(game.id)
    alive = [gp for gp in players if gp.finish_position is None]

    type_label = "🏆 Tournament" if game.game_type == "tournament" else "🃏 Regular"
    status_label = {"registration": "📝 Registration", "active": "🎮 In progress"}
    names: list[str] = []
    for gp in players:
        p = await repo.get_player(gp.player_id)
        if p:
            mark = "" if gp.finish_position is None else " ❌"
            names.append(f"  {p.display_name} (<code>{p.elo:.0f}</code>){mark}")

    await message.answer(
        f"<b>{status_label.get(game.status, game.status)}</b>  •  "
        f"Game #{game.id} ({type_label})\n"
        f"Seating: {game.seating_type}  •  "
        f"Players: {len(players)} (alive: {len(alive)})\n\n"
        + "\n".join(names)
    )


@router.message(Command("tables"))
async def cmd_tables(message: Message, repo: Repository) -> None:
    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game right now.")
        return

    tables = await repo.get_game_tables(game.id)
    if not tables:
        await message.answer("No tables set up for this game yet.")
        return

    table_players: dict[int, list[tuple[str, bool]]] = {}
    for t in tables:
        t_gps = await repo.get_table_players(t.id)
        plist: list[tuple[str, bool]] = []
        for gp in t_gps:
            p = await repo.get_player(gp.player_id)
            if p:
                plist.append((p.display_name, gp.finish_position is None))
        table_players[t.id] = plist

    await message.answer(tables_status_text(tables, table_players))
