"""Tests for GameService — the orchestration layer.

Covers: game lifecycle, join logic, knockouts, finish,
and many edge cases including the scenarios from the project brief:
- player tries to join multiple games
- player joins twice in one evening
- accidental button presses (double join)
- unregistered player tries to join
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

    async def test_cannot_create_two_active_games(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p.id)
        with pytest.raises(GameError, match="Уже есть активная игра"):
            await game_service.create_game(p.id)

    async def test_can_create_after_finishing(
        self, populated_repo: Repository, game_service: GameService
    ):
        """After a game is finished, a new one can be created."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)
        await game_service.finish_game(game.id)

        # Now create a new game
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
    async def test_start_game(self, populated_repo: Repository, game_service: GameService):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        count = await game_service.start_game(game.id)
        assert count == 2

    async def test_cannot_start_with_one_player(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        with pytest.raises(GameError, match="минимум 2 игрока"):
            await game_service.start_game(game.id)

    async def test_cannot_start_with_zero_players(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        with pytest.raises(GameError, match="минимум 2 игрока"):
            await game_service.start_game(game.id)

    async def test_cannot_start_already_active(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)
        with pytest.raises(GameError, match="уже запущена"):
            await game_service.start_game(game.id)


# ── Join game ──────────────────────────────────────────────────────


class TestJoinGame:
    async def test_join_during_registration(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p.id)
        game, player = await game_service.join_game(1001)
        assert player.display_name == "Алиса"
        assert game.status == "registration"

    async def test_late_join_during_active(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Players can join after the game has started (late join)."""
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game.id)

        # Late join
        game_ret, player = await game_service.join_game(1003)
        assert game_ret.status == "active"
        gps = await populated_repo.get_game_players(game.id)
        late = next(gp for gp in gps if gp.player_id == player.id)
        assert late.is_late_join is True

    async def test_no_active_game_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        with pytest.raises(GameError, match="нет активной игры"):
            await game_service.join_game(1001)

    async def test_unregistered_player_cannot_join(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Unregistered Telegram user gets clear error."""
        p = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p.id)
        with pytest.raises(GameError, match="не зарегистрирован"):
            await game_service.join_game(9999)  # unknown telegram_id

    async def test_double_join_same_game_is_safe(
        self, populated_repo: Repository, game_service: GameService
    ):
        """If player accidentally presses /join twice, it's a no-op (INSERT OR IGNORE)."""
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1001)  # accidental second press

        gps = await populated_repo.get_game_players(game.id)
        assert len(gps) == 1  # only one entry

    async def test_player_joins_after_previous_game_finished(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Player from a finished game should be able to join a new game."""
        p = await populated_repo.get_player_by_tg(1001)

        # Game 1
        game1 = await game_service.create_game(p.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(game1.id)
        await game_service.record_knockout(game1.id, 1002, 1001)
        await game_service.finish_game(game1.id)

        # Game 2
        game2 = await game_service.create_game(p.id)
        game_ret, player = await game_service.join_game(1001)
        assert game_ret.id == game2.id


# ── Knockouts ──────────────────────────────────────────────────────


class TestKnockouts:
    async def _setup_active_game(self, repo, svc, tg_ids):
        """Helper: create game, join players, start."""
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
        e_name, k_name, pos = await game_service.record_knockout(game.id, 1003, 1001)
        assert e_name == "Чарли"
        assert k_name == "Алиса"
        assert pos == 3

    async def test_knockout_position_decreases(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Positions should decrease as players are eliminated."""
        game = await self._setup_active_game(
            populated_repo, game_service, [1001, 1002, 1003, 1004]
        )
        _, _, pos1 = await game_service.record_knockout(game.id, 1004, 1001)
        _, _, pos2 = await game_service.record_knockout(game.id, 1003, 1001)
        assert pos1 == 4  # 4 alive → eliminated gets 4th
        assert pos2 == 3  # 3 alive → eliminated gets 3rd

    async def test_knockout_unknown_player_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        game = await self._setup_active_game(
            populated_repo, game_service, [1001, 1002]
        )
        with pytest.raises(GameError, match="не найден"):
            await game_service.record_knockout(game.id, 9999, 1001)

    async def test_knockout_not_active_game_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        # game is in "registration", not "active"
        with pytest.raises(GameError, match="не в активном статусе"):
            await game_service.record_knockout(game.id, 1002, 1001)

    async def test_knockout_nonexistent_game_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        with pytest.raises(GameError, match="не найдена"):
            await game_service.record_knockout(9999, 1001, 1002)


# ── Finish game ────────────────────────────────────────────────────


class TestFinishGame:
    async def test_finish_with_one_survivor(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Standard finish: eliminate until 1 left, then /finish."""
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

        # Winner (Алиса) should have gained Elo
        winner_delta = next(d for d in summary.results if d.player_id == p1.id)
        assert winner_delta.elo_after > winner_delta.elo_before

    async def test_finish_with_multiple_survivors(
        self, populated_repo: Repository, game_service: GameService
    ):
        """If admin finishes with >1 alive, they get ranked positions."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        await game_service.record_knockout(game.id, 1003, 1001)
        # 2 alive: finish without last knockout
        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 3

    async def test_finish_not_active_raises(
        self, populated_repo: Repository, game_service: GameService
    ):
        p = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p.id)
        with pytest.raises(GameError, match="не в активном статусе"):
            await game_service.finish_game(game.id)

    async def test_finish_persists_elo(
        self, populated_repo: Repository, game_service: GameService
    ):
        """After finish, player Elo in DB should be updated."""
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
        """Participants get streak+1, non-participants with streak>0 get reset."""
        p1 = await populated_repo.get_player_by_tg(1001)
        # Give p3 a pre-existing streak and some games
        p3 = await populated_repo.get_player_by_tg(1003)
        await populated_repo.update_attend_streak(p3.id, 3)
        await populated_repo.update_player_elo(p3.id, 1200.0)  # increments games_played

        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)
        await game_service.record_knockout(game.id, 1002, 1001)
        await game_service.finish_game(game.id)

        p1_after = await populated_repo.get_player(p1.id)
        p3_after = await populated_repo.get_player(p3.id)
        assert p1_after.attend_streak == 1  # participated
        assert p3_after.attend_streak == 0  # didn't participate, had streak

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


# ── Full evening scenario ──────────────────────────────────────────


class TestFullEvening:
    async def test_complete_evening_6_players(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Simulate a full evening with 6 players, knockouts, and finish."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)

        # Everyone joins
        for tg in [1001, 1002, 1003, 1004, 1005, 1006]:
            await game_service.join_game(tg)

        count = await game_service.start_game(game.id)
        assert count == 6

        # Knockouts: 1006 → 1005 → 1004 → 1003 → 1002, winner 1001
        await game_service.record_knockout(game.id, 1006, 1005)  # Франк выбыл
        await game_service.record_knockout(game.id, 1005, 1004)  # Ева выбыла
        await game_service.record_knockout(game.id, 1004, 1003)  # Диана выбыла
        await game_service.record_knockout(game.id, 1003, 1001)  # Чарли выбыл
        await game_service.record_knockout(game.id, 1002, 1001)  # Боб выбыл

        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 6
        assert len(summary.results) == 6

        # Check all players got Elo changes
        for d in summary.results:
            assert d.elo_before == 1200.0
            assert d.elo_after != d.elo_before or d.bounty_bonus > 0

    async def test_two_evenings_elo_accumulates(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Elo changes from game 1 carry into game 2."""
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)

        # Game 1: p1 wins
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

        # Game 2: p2 wins
        g2 = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(g2.id)
        await game_service.record_knockout(g2.id, 1001, 1002)
        await game_service.finish_game(g2.id)

        p1_final = await populated_repo.get_player(p1.id)
        p2_final = await populated_repo.get_player(p2.id)

        # p2 should have recovered some Elo
        assert p2_final.elo > p2_after_g1.elo
        assert p1_final.games_played == 2
        assert p2_final.games_played == 2


# ── Edge cases from project brief ──────────────────────────────────


class TestEdgeCases:
    async def test_player_rejoins_same_evening_after_being_knocked_out(
        self, populated_repo: Repository, game_service: GameService
    ):
        """
        Scenario: player is eliminated, game finishes, new game starts same evening.
        Player should be able to join the new game normally.
        """
        p1 = await populated_repo.get_player_by_tg(1001)
        g1 = await game_service.create_game(p1.id)
        await game_service.join_game(1001)
        await game_service.join_game(1002)
        await game_service.start_game(g1.id)
        await game_service.record_knockout(g1.id, 1002, 1001)
        await game_service.finish_game(g1.id)

        # New game same evening
        g2 = await game_service.create_game(p1.id)
        game_ret, player = await game_service.join_game(1002)
        assert game_ret.id == g2.id

    async def test_accidental_double_join_press(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Player hits /join button twice quickly — should not cause errors."""
        p1 = await populated_repo.get_player_by_tg(1001)
        await game_service.create_game(p1.id)

        # First join
        await game_service.join_game(1001)
        # Second join (accidental) — should be silently ignored
        await game_service.join_game(1001)

        gps = await populated_repo.get_game_players(
            (await populated_repo.get_active_game()).id
        )
        assert len(gps) == 1

    async def test_bounty_tracking_through_full_game(
        self, populated_repo: Repository, game_service: GameService
    ):
        """Verify bounty bonuses are correctly attributed in final summary."""
        p1 = await populated_repo.get_player_by_tg(1001)
        game = await game_service.create_game(p1.id)
        for tg in [1001, 1002, 1003]:
            await game_service.join_game(tg)
        await game_service.start_game(game.id)

        # p1 knocks out both p3 and p2
        await game_service.record_knockout(game.id, 1003, 1001)
        await game_service.record_knockout(game.id, 1002, 1001)

        summary = await game_service.finish_game(game.id)
        winner = next(d for d in summary.results if d.player_id == p1.id)
        # Both victims at 1200, hunter at 1200: each bounty = 2.0
        assert abs(winner.bounty_bonus - 4.0) < 0.1

    async def test_nonexistent_game_operations(
        self, populated_repo: Repository, game_service: GameService
    ):
        """All operations on non-existent game should raise GameError."""
        with pytest.raises(GameError):
            await game_service.start_game(9999)
        with pytest.raises(GameError):
            await game_service.finish_game(9999)
        with pytest.raises(GameError):
            await game_service.record_knockout(9999, 1001, 1002)

    async def test_large_game_20_players(
        self, repo: Repository, game_service: GameService
    ):
        """Stress test: 20-player game should compute correctly."""
        for i in range(20):
            await repo.add_player(telegram_id=2000 + i, display_name=f"P{i}")

        p0 = await repo.get_player_by_tg(2000)
        game = await game_service.create_game(p0.id)
        for i in range(20):
            await game_service.join_game(2000 + i)
        await game_service.start_game(game.id)

        # Eliminate all but one
        for i in range(19, 0, -1):
            await game_service.record_knockout(game.id, 2000 + i, 2000)

        summary = await game_service.finish_game(game.id)
        assert summary.player_count == 20
        assert len(summary.results) == 20

        # Verify no crashes and reasonable output
        assert all(d.elo_after >= 100 for d in summary.results)
