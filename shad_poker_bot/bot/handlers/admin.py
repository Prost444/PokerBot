"""Admin-only commands: /new_game, /go, /ko, /chips, /close_table, /finish, /cancel."""

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from shad_poker_bot.bot.filters import IsAdmin
from shad_poker_bot.bot.formatting import (
    game_summary_text,
    leaderboard_text,
    seating_text,
    table_summary_text,
)
from shad_poker_bot.config import AdminConfig
from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameError, GameService

router = Router(name="admin")


def _admin_filter(admin_cfg: AdminConfig) -> IsAdmin:
    return IsAdmin(admin_cfg)


@router.message(Command("new_game"))
async def cmd_new_game(
    message: Message,
    command: CommandObject,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can create games.")
        return

    player = await repo.get_player_by_tg(message.from_user.id)  # type: ignore[union-attr]
    if not player:
        await message.answer("Register first: /register Name")
        return

    # Parse optional args: /new_game [regular|tournament] [snake|divisional]
    args = (command.args or "").split()
    game_type = "regular"
    seating_type = "snake"

    for arg in args:
        arg_lower = arg.lower()
        if arg_lower in ("regular", "tournament"):
            game_type = arg_lower
        elif arg_lower in ("snake", "divisional"):
            seating_type = arg_lower

    try:
        game = await game_service.create_game(
            player.id, game_type, seating_type,
        )
    except GameError as e:
        await message.answer(str(e))
        return

    type_label = "🏆 Tournament" if game_type == "tournament" else "🃏 Regular"
    bounty_note = "\nBounty chips are active!" if game_type == "tournament" else ""
    await message.answer(
        f"{type_label} <b>Game #{game.id} created!</b>\n"
        f"Seating: {seating_type}{bounty_note}\n\n"
        "Players, join up: /join\n"
        "Admin starts the game with /go"
    )


@router.message(Command("go"))
async def cmd_go(
    message: Message,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can start the game.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game. Create one: /new_game")
        return

    try:
        seating_result = await game_service.start_game(game.id)
    except GameError as e:
        await message.answer(str(e))
        return

    total = sum(len(v) for v in seating_result.tables.values())
    await message.answer(
        f"🎮 <b>Game #{game.id} started!</b>  Players: {total}\n\n"
        "Knockouts: /ko @eliminated @eliminator\n"
        "Record chips: /chips @player amount\n"
        "Close a table: /close_table N\n"
        "Finish evening: /finish\n\n"
        "Latecomers can join via /join <table_number>"
    )
    await message.answer(seating_text(seating_result.tables))


@router.message(Command("ko"))
async def cmd_knockout(
    message: Message,
    command: CommandObject,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can record knockouts.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game.")
        return

    args = (command.args or "").split()
    if len(args) < 2:
        await message.answer(
            "Format: /ko @eliminated @eliminator\n"
            "Example: /ko @ivan @petr"
        )
        return

    eliminated = await _resolve_player(repo, args[0])
    eliminator = await _resolve_player(repo, args[1])

    if not eliminated:
        await message.answer(f"Player \"{args[0]}\" not found.")
        return
    if not eliminator:
        await message.answer(f"Player \"{args[1]}\" not found.")
        return

    try:
        e_name, k_name, pos, table_num = await game_service.record_knockout(
            game.id, eliminated.telegram_id, eliminator.telegram_id,
        )
    except GameError as e:
        await message.answer(str(e))
        return

    table_id = await repo.find_player_table(game.id, eliminated.id)
    if table_id:
        alive = await repo.count_alive_at_table(table_id)
    else:
        alive = await repo.count_alive_players(game.id)

    table_info = f" (table {table_num})" if table_num else ""
    await message.answer(
        f"💀 <b>{e_name}</b> eliminated (place {pos})!{table_info}\n"
        f"🎯 Knockout credited: <b>{k_name}</b>\n"
        f"Remaining alive{table_info}: {alive}"
    )

    if alive == 1 and table_num:
        await message.answer(
            f"🏆 Last player standing at table {table_num}!\n"
            f"Use /close_table {table_num} to finalize this table."
        )
    elif alive == 1 and not table_num:
        await message.answer(
            "🏆 Last player standing!\n"
            "Use /finish to finalize results."
        )


@router.message(Command("chips"))
async def cmd_chips(
    message: Message,
    command: CommandObject,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can record chip counts.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game.")
        return

    args = (command.args or "").split()
    if len(args) < 2:
        await message.answer(
            "Format: /chips @player amount\n"
            "Example: /chips @ivan 12500"
        )
        return

    player = await _resolve_player(repo, args[0])
    if not player:
        await message.answer(f"Player \"{args[0]}\" not found.")
        return

    try:
        chips = int(args[1])
    except ValueError:
        await message.answer("Chip count must be a number.")
        return

    try:
        name, amount = await game_service.record_chips(
            game.id, player.telegram_id, chips,
        )
    except GameError as e:
        await message.answer(str(e))
        return

    await message.answer(
        f"💰 <b>{name}</b>: {amount} chips recorded."
    )


@router.message(Command("close_table"))
async def cmd_close_table(
    message: Message,
    command: CommandObject,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can close tables.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game.")
        return

    args = (command.args or "").strip()
    if not args or not args.isdigit():
        await message.answer(
            "Format: /close_table N\n"
            "Example: /close_table 1"
        )
        return

    table_number = int(args)

    try:
        summary = await game_service.close_table(game.id, table_number)
    except GameError as e:
        await message.answer(str(e))
        return

    names: dict[int, str] = {}
    for d in summary.results:
        p = await repo.get_player(d.player_id)
        if p:
            names[d.player_id] = p.display_name

    await message.answer(
        table_summary_text(table_number, summary.results, names),
    )

    active_tables = await repo.get_active_tables(game.id)
    if not active_tables:
        await message.answer(
            "All tables are closed! Use /finish to finalize the evening."
        )


@router.message(Command("finish"))
async def cmd_finish(
    message: Message,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can finish the game.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game.")
        return

    try:
        summary = await game_service.finish_game(game.id)
    except GameError as e:
        await message.answer(str(e))
        return

    names: dict[int, str] = {}
    for d in summary.results:
        p = await repo.get_player(d.player_id)
        if p:
            names[d.player_id] = p.display_name

    await message.answer(game_summary_text(summary.results, names))

    top = await repo.get_leaderboard(10)
    await message.answer(leaderboard_text(top))


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, repo: Repository, admin_cfg: AdminConfig
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Only admins can cancel the game.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("No active game to cancel.")
        return

    await repo.set_game_status(game.id, "cancelled")
    await message.answer(f"❌ Game #{game.id} cancelled.")


# ── helper ──────────────────────────────────────────────────────────

async def _resolve_player(repo: Repository, token: str):
    """Resolve @username or display name to a PlayerDTO."""
    clean = token.lstrip("@")

    all_players = await repo.get_all_active_players()
    for p in all_players:
        if p.username and p.username.lower() == clean.lower():
            return p
        if p.display_name.lower() == clean.lower():
            return p
    return None
