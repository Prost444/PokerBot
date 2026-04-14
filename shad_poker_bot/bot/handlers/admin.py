"""Admin-only commands: /new_game, /go, /ko, /finish, /cancel."""

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from shad_poker_bot.bot.filters import IsAdmin
from shad_poker_bot.bot.formatting import game_summary_text
from shad_poker_bot.config import AdminConfig
from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameError, GameService

router = Router(name="admin")

# Filter is applied per-handler (not on the whole router) so that
# non-admin users get a friendly error instead of silent ignore.


def _admin_filter(admin_cfg: AdminConfig) -> IsAdmin:
    return IsAdmin(admin_cfg)


@router.message(Command("new_game"))
async def cmd_new_game(
    message: Message, repo: Repository, game_service: GameService, admin_cfg: AdminConfig
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Только админ может создавать игры.")
        return

    player = await repo.get_player_by_tg(message.from_user.id)  # type: ignore[union-attr]
    if not player:
        await message.answer("Сначала зарегистрируйся: /register Имя")
        return

    try:
        game = await game_service.create_game(player.id)
    except GameError as e:
        await message.answer(str(e))
        return

    await message.answer(
        f"🃏 <b>Игра #{game.id} создана!</b>\n\n"
        "Игроки, присоединяйтесь: /join\n"
        "Админ запускает игру командой /go"
    )


@router.message(Command("go"))
async def cmd_go(
    message: Message, repo: Repository, game_service: GameService, admin_cfg: AdminConfig
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Только админ может запускать игру.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("Нет активной игры. Создай: /new_game")
        return

    try:
        count = await game_service.start_game(game.id)
    except GameError as e:
        await message.answer(str(e))
        return

    await message.answer(
        f"🎮 <b>Игра #{game.id} началась!</b>  Игроков: {count}\n\n"
        "Нокауты: /ko @выбывший @выбивший\n"
        "Завершить: /finish\n\n"
        "Опоздавшие могут присоединиться через /join"
    )


@router.message(Command("ko"))
async def cmd_knockout(
    message: Message,
    command: CommandObject,
    repo: Repository,
    game_service: GameService,
    admin_cfg: AdminConfig,
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Только админ может записывать нокауты.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("Нет активной игры.")
        return

    # Parse: /ko @eliminated @eliminator  OR  /ko eliminated_name eliminator_name
    args = (command.args or "").split()
    if len(args) < 2:
        await message.answer(
            "Формат: /ko @выбывший @выбивший\n"
            "Пример: /ko @ivan @petr"
        )
        return

    # Resolve players — support @username or display_name lookup
    eliminated = await _resolve_player(repo, args[0])
    eliminator = await _resolve_player(repo, args[1])

    if not eliminated:
        await message.answer(f"Игрок «{args[0]}» не найден.")
        return
    if not eliminator:
        await message.answer(f"Игрок «{args[1]}» не найден.")
        return

    try:
        e_name, k_name, pos = await game_service.record_knockout(
            game.id, eliminated.telegram_id, eliminator.telegram_id
        )
    except GameError as e:
        await message.answer(str(e))
        return

    alive = await repo.count_alive_players(game.id)
    await message.answer(
        f"💀 <b>{e_name}</b> выбывает (место {pos})!\n"
        f"🎯 Нокаут засчитан: <b>{k_name}</b>\n"
        f"Осталось в игре: {alive}"
    )

    # Auto-finish if only 1 player left
    if alive == 1:
        await message.answer(
            "🏆 Остался последний игрок! Завершаю игру...\n"
            "Используй /finish для подведения итогов."
        )


@router.message(Command("finish"))
async def cmd_finish(
    message: Message, repo: Repository, game_service: GameService, admin_cfg: AdminConfig
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Только админ может завершать игру.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("Нет активной игры.")
        return

    try:
        summary = await game_service.finish_game(game.id)
    except GameError as e:
        await message.answer(str(e))
        return

    # Build name lookup
    names: dict[int, str] = {}
    for d in summary.results:
        p = await repo.get_player(d.player_id)
        if p:
            names[d.player_id] = p.display_name

    await message.answer(game_summary_text(summary.results, names))

    # Also show updated leaderboard
    top = await repo.get_leaderboard(10)
    from shad_poker_bot.bot.formatting import leaderboard_text
    await message.answer(leaderboard_text(top))


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message, repo: Repository, admin_cfg: AdminConfig
) -> None:
    if not await _admin_filter(admin_cfg)(message):
        await message.answer("Только админ может отменять игру.")
        return

    game = await repo.get_active_game()
    if not game:
        await message.answer("Нет активной игры для отмены.")
        return

    await repo.set_game_status(game.id, "cancelled")
    await message.answer(f"❌ Игра #{game.id} отменена.")


# ── helper ──────────────────────────────────────────────────────────

async def _resolve_player(repo: Repository, token: str):
    """Resolve @username or display name to a PlayerDTO."""
    clean = token.lstrip("@")

    # Try by username first
    all_players = await repo.get_all_active_players()
    for p in all_players:
        if p.username and p.username.lower() == clean.lower():
            return p
        if p.display_name.lower() == clean.lower():
            return p
    return None
