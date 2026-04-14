"""Message formatting helpers — keep handler code clean."""

from shad_poker_bot.db.repository import PlayerDTO
from shad_poker_bot.services.rating import RatingDelta


def leaderboard_text(players: list[PlayerDTO], title: str = "Рейтинг") -> str:
    if not players:
        return "Таблица рейтинга пока пуста. Сыграйте хотя бы одну игру!"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [f"<b>🏆 {title}</b>\n"]

    for i, p in enumerate(players, 1):
        medal = medals.get(i, f"{i}.")
        streak = f" 🔥{p.attend_streak}" if p.attend_streak >= 3 else ""
        lines.append(
            f"{medal} <b>{p.display_name}</b> — "
            f"<code>{p.elo:.0f}</code>  "
            f"({p.games_played} игр, {p.total_knockouts} нокаутов{streak})"
        )

    return "\n".join(lines)


def game_summary_text(results: list[RatingDelta], names: dict[int, str]) -> str:
    """Format post-game summary with Elo changes."""
    lines = ["<b>📊 Итоги вечера</b>\n"]

    sorted_results = sorted(results, key=lambda d: d.elo_after, reverse=True)
    for d in sorted_results:
        name = names.get(d.player_id, "???")
        sign = "+" if d.elo_change + d.bounty_bonus >= 0 else ""
        total = d.elo_change + d.bounty_bonus
        bounty_part = f" +{d.bounty_bonus:.0f}🎯" if d.bounty_bonus > 0 else ""

        lines.append(
            f"  <b>{name}</b>: {d.elo_before:.0f} → {d.elo_after:.0f} "
            f"({sign}{total:.0f}{bounty_part})"
        )

    return "\n".join(lines)


def player_stats_text(player: PlayerDTO, history: list[dict]) -> str:
    lines = [
        f"<b>📋 {player.display_name}</b>\n",
        f"Рейтинг: <code>{player.elo:.0f}</code>",
        f"Игр: {player.games_played}",
        f"Нокаутов: {player.total_knockouts}",
        f"Серия посещений: {player.attend_streak}",
    ]

    if history:
        lines.append("\n<b>Последние игры:</b>")
        for h in history[:5]:
            sign = "+" if h["elo_change"] + h["bounty_bonus"] >= 0 else ""
            total = h["elo_change"] + h["bounty_bonus"]
            lines.append(
                f"  #{h['game_id']}: место {h['finish_position']}/{h['players_count']} "
                f"({sign}{total:.0f})"
            )

    return "\n".join(lines)
