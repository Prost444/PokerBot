"""Elo + bounty + chip-performance rating engine.

Pure functions — no I/O, no side effects. Easy to test and reason about.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shad_poker_bot.config import RatingConfig


@dataclass
class PlayerResult:
    """Input for rating calculation: one player's game outcome."""

    player_id: int
    elo: float
    games_played: int
    attend_streak: int
    position: int            # 1 = winner, N = first eliminated
    knockouts: list[float] = field(default_factory=list)
    chip_factor: float = 1.0  # >1 = above-average chips, <1 = below


@dataclass
class RatingDelta:
    """Output: how a player's rating should change."""

    player_id: int
    elo_before: float
    elo_change: float
    bounty_bonus: float
    attendance_mult: float
    elo_after: float


class RatingEngine:
    """Stateless calculator — inject RatingConfig, call .process_game()."""

    def __init__(self, cfg: RatingConfig | None = None) -> None:
        self.cfg = cfg or RatingConfig()

    # ── public API ──────────────────────────────────────────────────

    def process_game(self, results: list[PlayerResult]) -> list[RatingDelta]:
        """Compute rating changes for every participant of a finished game."""
        n = len(results)
        if n < 2:
            return []

        all_elos = [r.elo for r in results]
        deltas: list[RatingDelta] = []

        for r in results:
            opponents = [e for pid, e in zip(
                [x.player_id for x in results], all_elos
            ) if pid != r.player_id]

            elo_change = self._elo_change(
                player_elo=r.elo,
                opponents_elos=opponents,
                position=r.position,
                total=n,
                games_played=r.games_played,
            )

            bounty = self._bounty_bonus(r.elo, r.knockouts)
            att_mult = self._attendance_multiplier(r.attend_streak)

            # Apply chip factor to base Elo change
            elo_change *= r.chip_factor

            # Attendance multiplier only boosts positive Elo changes
            adjusted = elo_change * att_mult if elo_change > 0 else elo_change
            total_change = adjusted + bounty
            elo_after = max(100.0, r.elo + total_change)  # floor at 100

            deltas.append(RatingDelta(
                player_id=r.player_id,
                elo_before=r.elo,
                elo_change=round(adjusted, 2),
                bounty_bonus=round(bounty, 2),
                attendance_mult=att_mult,
                elo_after=round(elo_after, 2),
            ))

        return deltas

    def season_regression(self, current_elo: float) -> float:
        """Soft reset between seasons: pull towards initial Elo."""
        w = self.cfg.season_regression_weight
        base = self.cfg.initial_elo
        return round(current_elo * w + base * (1 - w), 2)

    # ── internals ───────────────────────────────────────────────────

    def _k_factor(self, games_played: int, elo: float) -> int:
        if games_played < self.cfg.new_player_threshold:
            return self.cfg.k_new_player
        if elo < 1400:
            return self.cfg.k_developing
        return self.cfg.k_established

    @staticmethod
    def _actual_score(position: int, total: int) -> float:
        """Position 1 (winner) → 1.0, position N (first out) → 0.0."""
        if total <= 1:
            return 1.0
        return (total - position) / (total - 1)

    @staticmethod
    def _expected_score(player_elo: float, opponents: list[float]) -> float:
        """Mean pairwise win probability against all opponents."""
        if not opponents:
            return 0.5
        total = sum(
            1.0 / (1.0 + 10.0 ** ((opp - player_elo) / 400.0))
            for opp in opponents
        )
        return total / len(opponents)

    def _elo_change(
        self,
        player_elo: float,
        opponents_elos: list[float],
        position: int,
        total: int,
        games_played: int,
    ) -> float:
        s = self._actual_score(position, total)
        e = self._expected_score(player_elo, opponents_elos)
        k = self._k_factor(games_played, player_elo)
        n = len(opponents_elos)
        return k * n * (s - e)

    def _bounty_bonus(self, hunter_elo: float, victims: list[float]) -> float:
        if not victims:
            return 0.0
        bonus = 0.0
        for v_elo in victims:
            raw = self.cfg.bounty_base + (v_elo - hunter_elo) / self.cfg.bounty_elo_divisor
            bonus += max(self.cfg.bounty_min, raw)
        return bonus

    def _attendance_multiplier(self, streak: int) -> float:
        return min(
            1.0 + self.cfg.attendance_bonus_step * streak,
            self.cfg.attendance_bonus_cap,
        )
