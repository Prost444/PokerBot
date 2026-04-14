"""Tests for the Elo + bounty rating engine.

Covers: process_game, season_regression, K-factor selection,
actual/expected score, bounty bonus, attendance multiplier,
edge cases (1 player, 2 players, huge Elo gap, Elo floor).
"""

from shad_poker_bot.config import RatingConfig
from shad_poker_bot.services.rating import PlayerResult, RatingEngine

# ── Basic game scenarios ───────────────────────────────────────────


class TestProcessGame:
    def test_10_players_equal_elo(self, engine: RatingEngine):
        """With equal Elo, winner gains and loser loses; total is ~zero-sum."""
        results = [
            PlayerResult(
                player_id=i, elo=1200.0, games_played=5,
                attend_streak=0, position=i, knockouts=[],
            )
            for i in range(1, 11)
        ]
        deltas = engine.process_game(results)

        assert len(deltas) == 10
        winner = next(d for d in deltas if d.player_id == 1)
        loser = next(d for d in deltas if d.player_id == 10)
        assert winner.elo_after > 1200
        assert loser.elo_after < 1200

        total = sum(d.elo_after - d.elo_before for d in deltas)
        assert abs(total) < 1.0, f"Elo should be ~zero-sum, got {total:.2f}"

    def test_2_players_minimal(self, engine: RatingEngine):
        """Minimum viable game: 2 players."""
        results = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=0, position=1, knockouts=[1200]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        deltas = engine.process_game(results)
        assert len(deltas) == 2
        winner = next(d for d in deltas if d.player_id == 1)
        loser = next(d for d in deltas if d.player_id == 2)
        assert winner.elo_after > loser.elo_after

    def test_single_player_returns_empty(self, engine: RatingEngine):
        """A game with < 2 players should produce no deltas."""
        results = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=0, position=1, knockouts=[]),
        ]
        assert engine.process_game(results) == []

    def test_empty_results(self, engine: RatingEngine):
        assert engine.process_game([]) == []

    def test_winner_position_1_gets_highest_elo(self, engine: RatingEngine):
        """Position 1 should always get the best Elo change."""
        results = [
            PlayerResult(player_id=i, elo=1200, games_played=10,
                         attend_streak=0, position=i, knockouts=[])
            for i in range(1, 6)
        ]
        deltas = engine.process_game(results)
        sorted_by_change = sorted(deltas, key=lambda d: d.elo_change, reverse=True)
        assert sorted_by_change[0].player_id == 1

    def test_positions_monotonic_elo_change(self, engine: RatingEngine):
        """Better position → bigger Elo change (with equal starting Elo)."""
        results = [
            PlayerResult(player_id=i, elo=1200, games_played=10,
                         attend_streak=0, position=i, knockouts=[])
            for i in range(1, 8)
        ]
        deltas = engine.process_game(results)
        changes = [next(d for d in deltas if d.player_id == i).elo_change
                   for i in range(1, 8)]
        for i in range(len(changes) - 1):
            assert changes[i] >= changes[i + 1]


# ── Bounty bonus ───────────────────────────────────────────────────


class TestBountyBonus:
    def test_bounty_rewards_upset(self, engine: RatingEngine):
        """Knocking out a stronger player gives more bounty."""
        results = [
            PlayerResult(player_id=1, elo=1100, games_played=5,
                         attend_streak=0, position=1, knockouts=[1500, 1000]),
            PlayerResult(player_id=2, elo=1500, games_played=20,
                         attend_streak=0, position=3, knockouts=[]),
            PlayerResult(player_id=3, elo=1000, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        deltas = engine.process_game(results)
        winner = next(d for d in deltas if d.player_id == 1)
        # 2 + (1500-1100)/200 = 4.0;  2 + (1000-1100)/200 = 1.5;  total = 5.5
        assert abs(winner.bounty_bonus - 5.5) < 0.01

    def test_bounty_floor(self, engine: RatingEngine):
        """Bounty for much weaker opponent is capped at minimum (1.0)."""
        results = [
            PlayerResult(player_id=1, elo=1600, games_played=20,
                         attend_streak=0, position=1, knockouts=[1000]),
            PlayerResult(player_id=2, elo=1000, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        deltas = engine.process_game(results)
        winner = next(d for d in deltas if d.player_id == 1)
        # raw = 2 + (1000-1600)/200 = -1.0 → capped to 1.0
        assert abs(winner.bounty_bonus - 1.0) < 0.01

    def test_no_knockouts_no_bounty(self, engine: RatingEngine):
        """Player with zero knockouts gets zero bounty."""
        results = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        deltas = engine.process_game(results)
        for d in deltas:
            assert d.bounty_bonus == 0.0

    def test_multiple_knockouts_accumulate(self, engine: RatingEngine):
        """Bounty for multiple knockouts should sum up."""
        # All at 1200, so each bounty = 2 + 0 = 2.0
        results = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=0, position=1,
                         knockouts=[1200, 1200, 1200]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
            PlayerResult(player_id=3, elo=1200, games_played=5,
                         attend_streak=0, position=3, knockouts=[]),
            PlayerResult(player_id=4, elo=1200, games_played=5,
                         attend_streak=0, position=4, knockouts=[]),
        ]
        deltas = engine.process_game(results)
        winner = next(d for d in deltas if d.player_id == 1)
        assert abs(winner.bounty_bonus - 6.0) < 0.01


# ── Attendance multiplier ──────────────────────────────────────────


class TestAttendanceMultiplier:
    def test_streak_5_gives_1_25(self, engine: RatingEngine):
        base = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        streak = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=5, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
        ]

        base_d = engine.process_game(base)
        streak_d = engine.process_game(streak)

        bw = next(d for d in base_d if d.player_id == 1)
        sw = next(d for d in streak_d if d.player_id == 1)
        assert abs(sw.elo_change / bw.elo_change - 1.25) < 0.01

    def test_streak_caps_at_1_25(self, engine: RatingEngine):
        """Streak of 100 should still cap at 1.25."""
        mult = engine._attendance_multiplier(100)
        assert mult == 1.25

    def test_zero_streak_no_bonus(self, engine: RatingEngine):
        mult = engine._attendance_multiplier(0)
        assert mult == 1.0

    def test_multiplier_only_on_positive_changes(self, engine: RatingEngine):
        """Loser with a streak should NOT get multiplied losses."""
        base = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=1, knockouts=[]),
        ]
        streak = [
            PlayerResult(player_id=1, elo=1200, games_played=5,
                         attend_streak=5, position=2, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=5,
                         attend_streak=0, position=1, knockouts=[]),
        ]

        base_d = engine.process_game(base)
        streak_d = engine.process_game(streak)

        base_loser = next(d for d in base_d if d.player_id == 1)
        streak_loser = next(d for d in streak_d if d.player_id == 1)
        # Losses should be identical (multiplier not applied to negatives)
        assert abs(base_loser.elo_change - streak_loser.elo_change) < 0.01


# ── K-factor ───────────────────────────────────────────────────────


class TestKFactor:
    def test_new_player_k40(self, engine: RatingEngine):
        assert engine._k_factor(games_played=3, elo=1200) == 40

    def test_developing_k30(self, engine: RatingEngine):
        assert engine._k_factor(games_played=15, elo=1300) == 30

    def test_established_k20(self, engine: RatingEngine):
        assert engine._k_factor(games_played=15, elo=1400) == 20

    def test_boundary_10_games(self, engine: RatingEngine):
        """At exactly 10 games, no longer 'new'."""
        assert engine._k_factor(games_played=10, elo=1200) == 30

    def test_new_player_gains_more(self, engine: RatingEngine):
        """New player (K=40) should gain more for same result."""
        new = [
            PlayerResult(player_id=1, elo=1200, games_played=2,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=2,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        veteran = [
            PlayerResult(player_id=1, elo=1200, games_played=30,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1200, games_played=30,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        new_d = engine.process_game(new)
        vet_d = engine.process_game(veteran)

        nw = next(d for d in new_d if d.player_id == 1)
        vw = next(d for d in vet_d if d.player_id == 1)
        assert nw.elo_change > vw.elo_change


# ── Season regression ──────────────────────────────────────────────


class TestSeasonRegression:
    def test_above_base_pulls_down(self, engine: RatingEngine):
        assert engine.season_regression(1500) == 1440.0

    def test_below_base_pulls_up(self, engine: RatingEngine):
        assert engine.season_regression(1000) == 1040.0

    def test_at_base_no_change(self, engine: RatingEngine):
        assert engine.season_regression(1200) == 1200.0

    def test_custom_config(self):
        cfg = RatingConfig(season_regression_weight=0.5, initial_elo=1000)
        engine = RatingEngine(cfg)
        # 1400 * 0.5 + 1000 * 0.5 = 1200
        assert engine.season_regression(1400) == 1200.0


# ── Elo floor ──────────────────────────────────────────────────────


class TestEloFloor:
    def test_elo_cannot_go_below_100(self, engine: RatingEngine):
        """Even catastrophic loss shouldn't drop below 100."""
        results = [
            PlayerResult(player_id=1, elo=110, games_played=5,
                         attend_streak=0, position=3, knockouts=[]),
            PlayerResult(player_id=2, elo=1800, games_played=20,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=3, elo=1800, games_played=20,
                         attend_streak=0, position=2, knockouts=[]),
        ]
        deltas = engine.process_game(results)
        weak = next(d for d in deltas if d.player_id == 1)
        assert weak.elo_after >= 100.0


# ── Upset rewards ──────────────────────────────────────────────────


class TestUpsetRewards:
    def test_upset_win_gains_more(self, engine: RatingEngine):
        """Weak player beating strong field should gain more than the reverse."""
        upset = [
            PlayerResult(player_id=1, elo=1000, games_played=5,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1400, games_played=20,
                         attend_streak=0, position=2, knockouts=[]),
            PlayerResult(player_id=3, elo=1400, games_played=20,
                         attend_streak=0, position=3, knockouts=[]),
        ]
        expected = [
            PlayerResult(player_id=1, elo=1400, games_played=20,
                         attend_streak=0, position=1, knockouts=[]),
            PlayerResult(player_id=2, elo=1000, games_played=5,
                         attend_streak=0, position=2, knockouts=[]),
            PlayerResult(player_id=3, elo=1000, games_played=5,
                         attend_streak=0, position=3, knockouts=[]),
        ]
        ud = engine.process_game(upset)
        ed = engine.process_game(expected)
        uw = next(d for d in ud if d.player_id == 1)
        ew = next(d for d in ed if d.player_id == 1)
        assert uw.elo_change > ew.elo_change


# ── Internal methods ───────────────────────────────────────────────


class TestActualScore:
    def test_winner_gets_1(self):
        assert RatingEngine._actual_score(1, 10) == 1.0

    def test_last_gets_0(self):
        assert RatingEngine._actual_score(10, 10) == 0.0

    def test_middle_position(self):
        # position 5 out of 9: (9-5)/(9-1) = 4/8 = 0.5
        assert abs(RatingEngine._actual_score(5, 9) - 0.5) < 0.001

    def test_single_player(self):
        assert RatingEngine._actual_score(1, 1) == 1.0


class TestExpectedScore:
    def test_equal_elo_gives_half(self):
        assert abs(RatingEngine._expected_score(1200, [1200, 1200]) - 0.5) < 0.01

    def test_stronger_player_expects_more(self):
        high = RatingEngine._expected_score(1600, [1200, 1200])
        low = RatingEngine._expected_score(1200, [1600, 1600])
        assert high > 0.5
        assert low < 0.5

    def test_no_opponents_returns_half(self):
        assert RatingEngine._expected_score(1200, []) == 0.5
