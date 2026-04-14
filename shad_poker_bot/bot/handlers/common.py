"""Public commands available to everyone: /start, /help, /rating."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from shad_poker_bot.bot.formatting import leaderboard_text
from shad_poker_bot.db.repository import Repository

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, repo: Repository) -> None:
    player = await repo.get_player_by_tg(message.from_user.id)  # type: ignore[union-attr]
    if player:
        await message.answer(
            f"С возвращением, <b>{player.display_name}</b>! "
            f"Твой рейтинг: <code>{player.elo:.0f}</code>\n\n"
            "Используй /help для списка команд."
        )
    else:
        await message.answer(
            "Добро пожаловать в <b>ШАД Покер</b>! 🃏\n\n"
            "Зарегистрируйся: /register Твоё_Имя\n"
            "Полный список команд: /help"
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>🃏 ШАД Покер — команды</b>\n\n"
        "<b>Для всех:</b>\n"
        "/register Имя — регистрация\n"
        "/join — присоединиться к текущей игре\n"
        "/rating — таблица рейтинга\n"
        "/stats — твоя статистика\n"
        "/game — статус текущей игры\n\n"
        "<b>Для админа:</b>\n"
        "/new_game — создать игровой вечер\n"
        "/go — запустить игру (закрыть регистрацию)\n"
        "/ko @выбывший @выбивший — записать нокаут\n"
        "/finish — завершить игру и подвести итоги\n"
        "/cancel — отменить текущую игру"
    )


@router.message(Command("rating"))
async def cmd_rating(message: Message, repo: Repository) -> None:
    players = await repo.get_leaderboard(limit=20)
    await message.answer(leaderboard_text(players))


@router.message(Command("game"))
async def cmd_game_status(message: Message, repo: Repository) -> None:
    game = await repo.get_active_game()
    if not game:
        await message.answer("Сейчас нет активной игры.")
        return

    players = await repo.get_game_players(game.id)
    alive = [gp for gp in players if gp.finish_position is None]

    status_label = {"registration": "📝 Регистрация", "active": "🎮 Идёт игра"}
    names: list[str] = []
    for gp in players:
        p = await repo.get_player(gp.player_id)
        if p:
            mark = "" if gp.finish_position is None else " ❌"
            names.append(f"  {p.display_name} (<code>{p.elo:.0f}</code>){mark}")

    await message.answer(
        f"<b>{status_label.get(game.status, game.status)}</b>  •  "
        f"Игра #{game.id}\n"
        f"Игроков: {len(players)} (в игре: {len(alive)})\n\n"
        + "\n".join(names)
    )
