"""Message formatting helpers — keep handler code clean."""

from shad_poker_bot.db.repository import GameTableDTO, PlayerDTO
from shad_poker_bot.services.rating import RatingDelta


def leaderboard_text(players: list[PlayerDTO], title: str = "Rating") -> str:
    if not players:
        return "Leaderboard is empty. Play at least one game!"

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = [f"<b>🏆 {title}</b>\n"]

    for i, p in enumerate(players, 1):
        medal = medals.get(i, f"{i}.")
        streak = f" 🔥{p.attend_streak}" if p.attend_streak >= 3 else ""
        lines.append(
            f"{medal} <b>{p.display_name}</b> — "
            f"<code>{p.elo:.0f}</code>  "
            f"({p.games_played} games, {p.total_knockouts} KOs{streak})"
        )

    return "\n".join(lines)


def game_summary_text(results: list[RatingDelta], names: dict[int, str]) -> str:
    """Format post-game summary with Elo changes."""
    lines = ["<b>📊 Evening results</b>\n"]

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


def table_summary_text(
    table_number: int,
    results: list[RatingDelta],
    names: dict[int, str],
) -> str:
    """Format per-table results."""
    lines = [f"<b>📊 Table {table_number} results</b>\n"]

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


def seating_text(tables: dict[int, list[str]]) -> str:
    """Format seating assignments."""
    lines = ["<b>🪑 Table seating</b>\n"]
    for table_num in sorted(tables.keys()):
        players = tables[table_num]
        lines.append(f"<b>Table {table_num}</b> ({len(players)} players):")
        for i, name in enumerate(players, 1):
            lines.append(f"  {i}. {name}")
        lines.append("")
    return "\n".join(lines)


def tables_status_text(
    tables: list[GameTableDTO],
    table_players: dict[int, list[tuple[str, bool]]],
) -> str:
    """Format current tables status.

    table_players: table_id → [(display_name, is_alive), ...]
    """
    if not tables:
        return "No tables set up for this game."

    lines = ["<b>🃏 Tables</b>\n"]
    for t in tables:
        status_icon = "🟢" if t.status == "active" else "✅"
        players = table_players.get(t.id, [])
        alive_count = sum(1 for _, is_alive in players if is_alive)
        total = len(players)

        lines.append(
            f"{status_icon} <b>Table {t.table_number}</b>"
            f" — {alive_count}/{total} alive"
            f" ({t.status})"
        )
        for name, is_alive in players:
            mark = "" if is_alive else " ❌"
            lines.append(f"  {name}{mark}")
        lines.append("")

    return "\n".join(lines)


def player_stats_text(player: PlayerDTO, history: list[dict]) -> str:
    lines = [
        f"<b>📋 {player.display_name}</b>\n",
        f"Rating: <code>{player.elo:.0f}</code>",
        f"Games: {player.games_played}",
        f"Knockouts: {player.total_knockouts}",
        f"Attendance streak: {player.attend_streak}",
    ]

    if history:
        lines.append("\n<b>Recent games:</b>")
        for h in history[:5]:
            sign = "+" if h["elo_change"] + h["bounty_bonus"] >= 0 else ""
            total = h["elo_change"] + h["bounty_bonus"]
            lines.append(
                f"  #{h['game_id']}: place {h['finish_position']}/{h['players_count']} "
                f"({sign}{total:.0f})"
            )

    return "\n".join(lines)
