"""Tests for GameService — the orchestration layer.

Covers: game lifecycle, join logic, knockouts, finish,
multi-table support, tournament vs regular modes,
and many edge cases.
"""

import pytest

from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameError, GameService

# ── Game creation ──────────────────────────────────────────────────


class TestCreateGame:
    async def test_create_game(self, populated_repo: Repository, game_service: GameService):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        assert game.status == "registration"
        assert game.game_type == "regular"
        assert game.seating_type == "snake"

    async def test_create_tournament_game(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id, "tournament", "divisional")
        assert game.game_type == "tournament"
        assert game.seating_type == "divisional"

    async def test_invalid_game_type_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        with pytest.raises(GameError, match="Game type"):
            await game_service.create_game(p.id, "invalid")

    async def test_invalid_seating_type_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        with pytest.raises(GameError, match="Seating type"):
            await game_service.create_game(p.id, "regular", "invalid")

    async def test_cannot_create_two_active_games(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p.id)
        with pytest.raises(GameError, match="already an active game"):
            await game_service.create_game(p.id)

    async def test_can_create_after_finishing(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)
        await game_service.finish_game(game.id)

        game2 = await game_service.create_game(p1.id)
        assert game2.id != game.id

    async def test_can_create_after_cancel(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await populated_repo.set_game_status(game.id, "cancelled")

        game2 = await game_service.create_game(p.id)
        assert game2.id != game.id


# ── Start game ─────────────────────────────────────────────────────


class TestStartGame:
    async def test_start_game_returns_seating(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        seating = await game_service.start_game(game.id)
        assert 1 in seating.tables
        total = sum(len(v) for v in seating.tables.values())
        assert total == 2

    async def test_start_creates_tables(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)
        tables = await populated_repo.get_game_tables(game.id)
        assert len(tables) >= 1

    async def test_cannot_start_with_one_player(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        with pytest.raises(GameError, match="at least 2 players"):
            await game_service.start_game(game.id)

    async def test_cannot_start_with_zero_players(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        with pytest.raises(GameError, match="at least 2 players"):
            await game_service.start_game(game.id)

    async def test_cannot_start_already_active(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)
        with pytest.raises(GameError, match="already started"):
            await game_service.start_game(game.id)


# ── Join game ──────────────────────────────────────────────────────


class TestJoinGame:
    async def test_join_during_registration(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p.id)
        game, player, table_num = await game_service.join_game(1001)
        assert player.display_name == "Alice"
        assert game.status == "registration"
        assert table_num is None

    async def test_late_join_shows_table_choice(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Late join without table number should show available tables."""
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)

        with pytest.raises(GameError, match="Choose a table"):
            await game_service.join_game(1003)

    async def test_late_join_with_table_number(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Late join with explicit table number should work."""
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)

        game_ret, player, table_num = await game_service.join_game(1003, 1)
        assert game_ret.status == "active"
        assert table_num == 1
        gps = await populated_repo.get_game_players(game.id)
        late = next(gp for gp in gps if gp.player_id == player.id)
        assert late.is_late_join is True
        assert late.table_id is not None

    async def test_no_active_game_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        with pytest.raises(GameError, match="No active game"):
            await game_service.join_game(1001)

    async def test_unregistered_player_cannot_join(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p.id)
        with pytest.raises(GameError, match="not registered"):
            await game_service.join_game(9999)

    async def test_double_join_same_game_is_safe(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1001)

        gps = await populated_repo.get_game_players(game.id)
        assert len(gps) == 1

    async def test_player_joins_after_previous_game_finished(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)

        g1 = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(g1.id)
        await game_service.record_knockout(g1.id, 1002, 1001)
        await game_service.finish_game(g1.id)

        g2 = await game_service.create_game(p.id)
        game_ret, player, _ = await game_service.join_game(1001)
        assert game_ret.id == g2.id


# ── Knockouts ──────────────────────────────────────────────────────


class TestKnockouts:
    async def _setup_active_game(self, repo, svc, tg_ids):
        creator = await repo.get_player_by_tg(tg_ids[0])
        game = await svc.create_game(creator.id)
        for tg in tg_ids:
            await svc.join_game(tg)
        await svc.start_game(game.id)
        return game

    async def test_knockout_records_correctly(
        self, populated_repo: Repository, game_service: GameService
    ):
        game = await self._setup_active_game(
            populated_repo, game_service, [1001, 1002, 1003]
        )
        e_name, k_name, pos, _ = await game_service.record_knockout(game.id, 1003, 1001)
        assert e_name == "Charlie"
        assert k_name == "Alice"
        assert pos == 3

    async def test_knockout_position_decreases(
        self, populated_repo: Repository, game_service: GameService
    ):
        game = await self._setup_active_game(
            populated_repo, game_service, [1001, 1002, 1003, 1004]
        )
        _, _, pos1, _ = await game_service.record_knockout(game.id, 1004, 1001)
        _, _, pos2, _ = await game_service.record_knockout(game.id, 1003, 1001)
        assert pos1 == 4
        assert pos2 == 3

    async def test_knockout_unknown_player_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        game = await self._setup_active_game(
            populated_repo, game_service, [1001, 1002]
        )
        with pytest.raises(GameError, match="not found"):
            await game_service.record_knockout(game.id, 9999, 1001)

    async def test_knockout_not_active_game_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        with pytest.raises(GameError, match="not in active status"):
            await game_service.record_knockout(game.id, 1002, 1001)

    async def test_knockout_nonexistent_game_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        with pytest.raises(GameError, match="not found"):
            await game_service.record_knockout(9999, 1001, 1002)


# ── Finish game ────────────────────────────────────────────────────


class TestFinishGame:
    async def test_finish_with_one_survivor(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 3
        assert len(summary.results) == 3

        winner_delta = next(d for d in summary.results if d.player_id == p1.id)
        assert winner_delta.elo_after > winner_delta.elo_before

    async def test_finish_with_multiple_survivors(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 3

    async def test_finish_not_active_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        with pytest.raises(GameError, match="not in active status"):
            await game_service.finish_game(game.id)

    async def test_finish_persists_elo(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        winner_delta = next(d for d in summary.results if d.player_id == p1.id)

        updated = await populated_repo.get_player(p1.id)
        assert abs(updated.elo - winner_delta.elo_after) < 0.01
        assert updated.games_played == 1

    async def test_finish_updates_attendance_streak(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        p3 = await populated_repo.get_player_by_tg(1003)
        await populated_repo.update_attend_streak(p3.id, 3)
        await populated_repo.update_player_elo(p3.id, 1200.0)

        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)
        await game_service.finish_game(game.id)

        p1_after = await populated_repo.get_player(p1.id)
        p3_after = await populated_repo.get_player(p3.id)
        assert p1_after.attend_streak == 1
        assert p3_after.attend_streak == 0

    async def test_finish_saves_elo_history(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)
        await game_service.finish_game(game.id)

        history = await populated_repo.get_player_history(p1.id)
        assert len(history) == 1
        assert history[0]["finish_position"] == 1

    async def test_finish_game_status_becomes_finished(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)
        await game_service.finish_game(game.id)

        g = await populated_repo.get_game(game.id)
        assert g.status == "finished"


# ── Tournament vs Regular mode ────────────────────────────────────


class TestGameTypes:
    async def test_regular_game_no_bounty(
        self, populated_repo: Repository, game_service: GameService
    ):
        """In regular mode, knockouts should NOT generate bounty bonus."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id, "regular")
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        winner = next(d for d in summary.results if d.player_id == p1.id)
        assert winner.bounty_bonus == 0.0

    async def test_tournament_game_has_bounty(
        self, populated_repo: Repository, game_service: GameService
    ):
        """In tournament mode, knockouts should generate bounty bonus."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id, "tournament")
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        winner = next(d for d in summary.results if d.player_id == p1.id)
        assert winner.bounty_bonus > 0


# ── Chip tracking ─────────────────────────────────────────────────


class TestChipTracking:
    async def test_record_chips(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        name, chips = await game_service.record_chips(game.id, 1001, 12000)
        assert name == "Alice"
        assert chips == 12000

    async def test_chip_factor_boosts_winner(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Player with above-average chips should gain more Elo."""
        p1 = await populated_repo.get_player_by_tg(1001)

        # Game without chips
        g1 = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(g1.id)
        await game_service.record_knockout(g1.id, 1003, 1001)
        await game_service.record_knockout(g1.id, 1002, 1001)
        s1 = await game_service.finish_game(g1.id)
        base_gain = next(
            d for d in s1.results if d.player_id == p1.id
        ).elo_change

        # Reset elo
        await populated_repo.update_player_elo(p1.id, 1200.0, False)
        p2 = await populated_repo.get_player_by_tg(1002)
        await populated_repo.update_player_elo(p2.id, 1200.0, False)
        p3 = await populated_repo.get_player_by_tg(1003)
        await populated_repo.update_player_elo(p3.id, 1200.0, False)

        # Game with high chips for winner
        g2 = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(g2.id)
        await game_service.record_knockout(g2.id, 1003, 1001)
        await game_service.record_knockout(g2.id, 1002, 1001)
        # Record high chips for winner
        await game_service.record_chips(g2.id, 1001, 15000)
        s2 = await game_service.finish_game(g2.id)
        chip_gain = next(
            d for d in s2.results if d.player_id == p1.id
        ).elo_change

        # With above-average chips, winner should gain more
        assert chip_gain > base_gain

    async def test_knockout_sets_chips_zero(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Eliminated player should get final_chips = 0."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)

        p2 = await populated_repo.get_player_by_tg(1002)
        gps = await populated_repo.get_game_players(game.id)
        eliminated = next(gp for gp in gps if gp.player_id == p2.id)
        assert eliminated.final_chips == 0


# ── Close table ───────────────────────────────────────────────────


class TestCloseTable:
    async def test_close_table_calculates_ratings(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        tables = await populated_repo.get_game_tables(game.id)
        assert len(tables) >= 1

        summary = await game_service.close_table(game.id, tables[0].table_number)
        assert summary.player_count == 3
        assert len(summary.results) == 3

    async def test_close_nonexistent_table_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)

        with pytest.raises(GameError, match="not found"):
            await game_service.close_table(game.id, 99)

    async def test_close_already_closed_table_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)

        tables = await populated_repo.get_game_tables(game.id)
        await game_service.close_table(game.id, tables[0].table_number)

        with pytest.raises(GameError, match="already closed"):
            await game_service.close_table(game.id, tables[0].table_number)


# ── Full evening scenario ──────────────────────────────────────────


class TestFullEvening:
    async def test_complete_evening_6_players(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)

        for tg in [1001, 1002, 1003, 1004, 1005, 1006]:
            await game_service.join_game(tg)

        seating = await game_service.start_game(game.id)
        total = sum(len(v) for v in seating.tables.values())
        assert total == 6

        await game_service.record_knockout(game.id, 1006, 1005)
        await game_service.record_knockout(game.id, 1005, 1004)
        await game_service.record_knockout(game.id, 1004, 1003)
        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 6
        assert len(summary.results) == 6

        for d in summary.results:
            assert d.elo_before == 1200.0
            assert d.elo_after != d.elo_before or d.bounty_bonus > 0

    async def test_two_evenings_elo_accumulates(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)

        g1 = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(g1.id)
        await game_service.record_knockout(g1.id, 1002, 1001)
        await game_service.finish_game(g1.id)

        p1_after_g1 = await populated_repo.get_player(p1.id)
        p2_after_g1 = await populated_repo.get_player(p2.id)
        assert p1_after_g1.elo > 1200
        assert p2_after_g1.elo < 1200

        g2 = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(g2.id)
        await game_service.record_knockout(g2.id, 1001, 1002)
        await game_service.finish_game(g2.id)

        p1_final = await populated_repo.get_player(p1.id)
        p2_final = await populated_repo.get_player(p2.id)

        assert p2_final.elo > p2_after_g1.elo
        assert p1_final.games_played == 2
        assert p2_final.games_played == 2


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    async def test_player_rejoins_same_evening_after_being_knocked_out(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        g1 = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(g1.id)
        await game_service.record_knockout(g1.id, 1002, 1001)
        await game_service.finish_game(g1.id)

        g2 = await game_service.create_game(p1.id)
        game_ret, player, _ = await game_service.join_game(1002)
        assert game_ret.id == g2.id

    async def test_accidental_double_join_press(
        self, populated_repo: Repository, game_service: GameService
    ):
        p1 = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1001)

        gps = await populated_repo.get_game_players(
            (await populated_repo.get_active_game()).id
        )
        assert len(gps) == 1

    async def test_bounty_tracking_through_full_tournament(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Verify bounty bonuses in tournament mode."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id, "tournament")
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        winner = next(d for d in summary.results if d.player_id == p1.id)
        assert abs(winner.bounty_bonus - 4.0) < 0.1

    async def test_nonexistent_game_operations(
        self, populated_repo: Repository, game_service: GameService
    ):
        with pytest.raises(GameError):
            await game_service.start_game(9999)
        with pytest.raises(GameError):
            await game_service.finish_game(9999)
        with pytest.raises(GameError):
            await game_service.record_knockout(9999, 1001, 1002)

    async def test_large_game_20_players(
        self, repo: Repository, game_service: GameService
    ):
        """Stress test: 20-player game with multiple tables."""
        for i in range(20):
            await repo.add_player(telegram_id=2000 + i, display_name=f"P{i}")

        p0 = await repo.get_player_by_tg(2000)
        game = await game_service.create_game(p0.id)
        for i in range(20):
            await game_service.join_game(2000 + i)
        seating = await game_service.start_game(game.id)

        # Should have multiple tables (20 players, max 9 per table)
        assert len(seating.tables) >= 3

        # Eliminate all but one on each table
        tables = await repo.get_game_tables(game.id)
        for t in tables:
            t_players = await repo.get_table_players(t.id)
            alive_players = [gp for gp in t_players if gp.finish_position is None]
            # Eliminate all but one
            for gp in alive_players[1:]:
                p = await repo.get_player(gp.player_id)
                survivor = await repo.get_player(alive_players[0].player_id)
                await game_service.record_knockout(game.id, p.telegram_id, survivor.telegram_id)

        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 20
        assert len(summary.results) == 20
        assert all(d.elo_after >= 100 for d in summary.results)
