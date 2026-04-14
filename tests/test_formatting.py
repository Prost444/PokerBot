"""Tests for message formatting helpers."""

from shad_poker_bot.bot.formatting import (
    game_summary_text,
    leaderboard_text,
    player_stats_text,
    seating_text,
    table_summary_text,
)
from shad_poker_bot.db.repository import PlayerDTO
from shad_poker_bot.services.rating import RatingDelta


def _make_player(
    id: int = 1, elo: float = 1200, games: int = 5,
    knockouts: int = 2, streak: int = 0, name: str = "Test",
) -> PlayerDTO:
    return PlayerDTO(
        id=id, telegram_id=100 + id, username=f"user{id}",
        display_name=name, elo=elo, games_played=games,
        total_knockouts=knockouts, attend_streak=streak,
    )


class TestLeaderboardText:
    def test_empty_leaderboard(self):
        text = leaderboard_text([])
        assert "empty" in text

    def test_single_player(self):
        text = leaderboard_text([_make_player(name="Alice", elo=1300)])
        assert "Alice" in text
        assert "1300" in text
        assert "🥇" in text

    def test_medals_for_top_3(self):
        players = [
            _make_player(id=1, name="First", elo=1500),
            _make_player(id=2, name="Second", elo=1400),
            _make_player(id=3, name="Third", elo=1300),
        ]
        text = leaderboard_text(players)
        assert "🥇" in text
        assert "🥈" in text
        assert "🥉" in text

    def test_fire_emoji_for_streak(self):
        player = _make_player(streak=3)
        text = leaderboard_text([player])
        assert "🔥" in text

    def test_no_fire_below_3(self):
        player = _make_player(streak=2)
        text = leaderboard_text([player])
        assert "🔥" not in text

    def test_custom_title(self):
        text = leaderboard_text([_make_player()], title="Top")
        assert "Top" in text

    def test_fourth_place_number(self):
        players = [_make_player(id=i, name=f"P{i}", elo=1500 - i * 50) for i in range(1, 6)]
        text = leaderboard_text(players)
        assert "4." in text


class TestGameSummaryText:
    def test_basic_summary(self):
        results = [
            RatingDelta(player_id=1, elo_before=1200, elo_change=30,
                        bounty_bonus=4, attendance_mult=1.0, elo_after=1234),
            RatingDelta(player_id=2, elo_before=1200, elo_change=-30,
                        bounty_bonus=0, attendance_mult=1.0, elo_after=1170),
        ]
        names = {1: "Alice", 2: "Bob"}
        text = game_summary_text(results, names)
        assert "Alice" in text
        assert "Bob" in text
        assert "results" in text

    def test_bounty_marker(self):
        results = [
            RatingDelta(player_id=1, elo_before=1200, elo_change=30,
                        bounty_bonus=5, attendance_mult=1.0, elo_after=1235),
        ]
        text = game_summary_text(results, {1: "Alice"})
        assert "🎯" in text

    def test_no_bounty_no_marker(self):
        results = [
            RatingDelta(player_id=1, elo_before=1200, elo_change=30,
                        bounty_bonus=0, attendance_mult=1.0, elo_after=1230),
        ]
        text = game_summary_text(results, {1: "Alice"})
        assert "🎯" not in text

    def test_sorted_by_elo_descending(self):
        results = [
            RatingDelta(player_id=1, elo_before=1200, elo_change=-30,
                        bounty_bonus=0, attendance_mult=1.0, elo_after=1170),
            RatingDelta(player_id=2, elo_before=1200, elo_change=30,
                        bounty_bonus=0, attendance_mult=1.0, elo_after=1230),
        ]
        names = {1: "Weak", 2: "Strong"}
        text = game_summary_text(results, names)
        assert text.index("Strong") < text.index("Weak")

    def test_unknown_player_shows_question_marks(self):
        results = [
            RatingDelta(player_id=99, elo_before=1200, elo_change=0,
                        bounty_bonus=0, attendance_mult=1.0, elo_after=1200),
        ]
        text = game_summary_text(results, {})
        assert "???" in text


class TestTableSummaryText:
    def test_table_summary(self):
        results = [
            RatingDelta(player_id=1, elo_before=1200, elo_change=20,
                        bounty_bonus=0, attendance_mult=1.0, elo_after=1220),
        ]
        text = table_summary_text(1, results, {1: "Alice"})
        assert "Table 1" in text
        assert "Alice" in text


class TestSeatingText:
    def test_seating_display(self):
        tables = {1: ["Alice", "Bob"], 2: ["Charlie", "Diana"]}
        text = seating_text(tables)
        assert "Table 1" in text
        assert "Table 2" in text
        assert "Alice" in text
        assert "Diana" in text


class TestPlayerStatsText:
    def test_basic_stats(self):
        player = _make_player(name="Alice", elo=1350, games=12, knockouts=8, streak=4)
        text = player_stats_text(player, [])
        assert "Alice" in text
        assert "1350" in text
        assert "12" in text
        assert "8" in text
        assert "4" in text

    def test_with_history(self):
        player = _make_player()
        history = [
            {"game_id": 1, "finish_position": 1, "players_count": 5,
             "elo_change": 30.0, "bounty_bonus": 2.0},
            {"game_id": 2, "finish_position": 3, "players_count": 8,
             "elo_change": -10.0, "bounty_bonus": 0.0},
        ]
        text = player_stats_text(player, history)
        assert "Recent games" in text
        assert "#1" in text
        assert "#2" in text

    def test_no_history(self):
        player = _make_player()
        text = player_stats_text(player, [])
        assert "Recent" not in text

    def test_history_capped_at_5(self):
        player = _make_player()
        history = [
            {"game_id": i, "finish_position": 1, "players_count": 5,
             "elo_change": 10.0, "bounty_bonus": 0.0}
            for i in range(10)
        ]
        text = player_stats_text(player, history)
        count = text.count("place")
        assert count == 5
