"""Integration tests for Repository — uses in-memory SQLite."""

import pytest

from shad_poker_bot.db.repository import EloHistoryDTO, Repository


# ── Players ────────────────────────────────────────────────────────


class TestPlayerCRUD:
    async def test_add_and_get_player(self, repo: Repository):
        p = await repo.add_player(telegram_id=42, display_name="Тест", username="test_user")
        assert p.telegram_id == 42
        assert p.display_name == "Тест"
        assert p.username == "test_user"
        assert p.elo == 1200.0
        assert p.games_played == 0

    async def test_get_player_by_tg(self, repo: Repository):
        await repo.add_player(telegram_id=42, display_name="Тест")
        p = await repo.get_player_by_tg(42)
        assert p is not None
        assert p.display_name == "Тест"

    async def test_get_nonexistent_player(self, repo: Repository):
        assert await repo.get_player_by_tg(999999) is None
        assert await repo.get_player(999999) is None

    async def test_get_player_by_id(self, repo: Repository):
        added = await repo.add_player(telegram_id=42, display_name="Тест")
        p = await repo.get_player(added.id)
        assert p is not None
        assert p.telegram_id == 42

    async def test_duplicate_telegram_id_raises(self, repo: Repository):
        await repo.add_player(telegram_id=42, display_name="Первый")
        with pytest.raises(Exception):
            await repo.add_player(telegram_id=42, display_name="Второй")

    async def test_custom_initial_elo(self, repo: Repository):
        p = await repo.add_player(telegram_id=42, display_name="Тест", initial_elo=1500.0)
        assert p.elo == 1500.0


class TestPlayerUpdates:
    async def test_update_elo_increments_games(self, repo: Repository):
        p = await repo.add_player(telegram_id=42, display_name="Тест")
        await repo.update_player_elo(p.id, 1250.0)
        updated = await repo.get_player(p.id)
        assert updated.elo == 1250.0
        assert updated.games_played == 1

    async def test_update_elo_without_increment(self, repo: Repository):
        p = await repo.add_player(telegram_id=42, display_name="Тест")
        await repo.update_player_elo(p.id, 1300.0, increment_games=False)
        updated = await repo.get_player(p.id)
        assert updated.elo == 1300.0
        assert updated.games_played == 0

    async def test_increment_knockouts(self, repo: Repository):
        p = await repo.add_player(telegram_id=42, display_name="Тест")
        await repo.increment_knockouts(p.id)
        await repo.increment_knockouts(p.id, count=3)
        updated = await repo.get_player(p.id)
        assert updated.total_knockouts == 4

    async def test_update_attend_streak(self, repo: Repository):
        p = await repo.add_player(telegram_id=42, display_name="Тест")
        await repo.update_attend_streak(p.id, 5)
        updated = await repo.get_player(p.id)
        assert updated.attend_streak == 5


class TestLeaderboard:
    async def test_empty_leaderboard(self, repo: Repository):
        lb = await repo.get_leaderboard()
        assert lb == []

    async def test_leaderboard_only_played(self, repo: Repository):
        """Players with 0 games should not appear on leaderboard."""
        p = await repo.add_player(telegram_id=42, display_name="Тест")
        lb = await repo.get_leaderboard()
        assert len(lb) == 0

        # Now give them a game
        await repo.update_player_elo(p.id, 1300.0)
        lb = await repo.get_leaderboard()
        assert len(lb) == 1

    async def test_leaderboard_ordered_by_elo(self, repo: Repository):
        p1 = await repo.add_player(telegram_id=1, display_name="Слабый")
        p2 = await repo.add_player(telegram_id=2, display_name="Сильный")
        await repo.update_player_elo(p1.id, 1100.0)
        await repo.update_player_elo(p2.id, 1400.0)
        lb = await repo.get_leaderboard()
        assert lb[0].display_name == "Сильный"
        assert lb[1].display_name == "Слабый"

    async def test_leaderboard_limit(self, repo: Repository):
        for i in range(25):
            p = await repo.add_player(telegram_id=i + 100, display_name=f"Player{i}")
            await repo.update_player_elo(p.id, 1200.0 + i)
        lb = await repo.get_leaderboard(limit=10)
        assert len(lb) == 10

    async def test_get_all_active_players(self, populated_repo: Repository):
        players = await populated_repo.get_all_active_players()
        assert len(players) == 6


# ── Seasons ────────────────────────────────────────────────────────


class TestSeasons:
    async def test_create_and_get_season(self, repo: Repository):
        sid = await repo.create_season(number=1)
        active = await repo.get_active_season()
        assert active == sid

    async def test_no_active_season(self, repo: Repository):
        assert await repo.get_active_season() is None


# ── Games ──────────────────────────────────────────────────────────


class TestGames:
    async def test_create_game(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p.id)
        game = await populated_repo.get_game(gid)
        assert game is not None
        assert game.status == "registration"

    async def test_get_active_game(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        await populated_repo.create_game(p.id)
        active = await populated_repo.get_active_game()
        assert active is not None
        assert active.status == "registration"

    async def test_no_active_game(self, repo: Repository):
        assert await repo.get_active_game() is None

    async def test_set_game_status(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p.id)
        await populated_repo.set_game_status(gid, "active")
        game = await populated_repo.get_game(gid)
        assert game.status == "active"

    async def test_finished_game_sets_timestamp(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p.id)
        await populated_repo.set_game_status(gid, "finished")
        game = await populated_repo.get_game(gid)
        assert game.status == "finished"
        assert game.finished_at is not None

    async def test_finished_game_not_active(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p.id)
        await populated_repo.set_game_status(gid, "finished")
        assert await populated_repo.get_active_game() is None

    async def test_get_nonexistent_game(self, repo: Repository):
        assert await repo.get_game(9999) is None


# ── Game players ───────────────────────────────────────────────────


class TestGamePlayers:
    async def test_add_and_get_game_players(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)
        gid = await populated_repo.create_game(p1.id)

        await populated_repo.add_game_player(gid, p1.id)
        await populated_repo.add_game_player(gid, p2.id)

        players = await populated_repo.get_game_players(gid)
        assert len(players) == 2

    async def test_duplicate_join_ignored(self, populated_repo: Repository):
        """INSERT OR IGNORE — second join for same player should be no-op."""
        p1 = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p1.id)

        await populated_repo.add_game_player(gid, p1.id)
        await populated_repo.add_game_player(gid, p1.id)  # duplicate

        players = await populated_repo.get_game_players(gid)
        assert len(players) == 1

    async def test_late_join_flag(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p1.id)
        await populated_repo.add_game_player(gid, p1.id, is_late=True)

        players = await populated_repo.get_game_players(gid)
        assert players[0].is_late_join is True

    async def test_record_elimination(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)
        gid = await populated_repo.create_game(p1.id)
        await populated_repo.add_game_player(gid, p1.id)
        await populated_repo.add_game_player(gid, p2.id)

        await populated_repo.record_elimination(gid, p2.id, p1.id, position=2)

        players = await populated_repo.get_game_players(gid)
        eliminated = next(gp for gp in players if gp.player_id == p2.id)
        assert eliminated.finish_position == 2
        assert eliminated.eliminated_by_id == p1.id

    async def test_count_alive_players(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)
        p3 = await populated_repo.get_player_by_tg(1003)
        gid = await populated_repo.create_game(p1.id)
        await populated_repo.add_game_player(gid, p1.id)
        await populated_repo.add_game_player(gid, p2.id)
        await populated_repo.add_game_player(gid, p3.id)

        assert await populated_repo.count_alive_players(gid) == 3

        await populated_repo.record_elimination(gid, p3.id, p1.id, position=3)
        assert await populated_repo.count_alive_players(gid) == 2

    async def test_get_alive_players(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)
        gid = await populated_repo.create_game(p1.id)
        await populated_repo.add_game_player(gid, p1.id)
        await populated_repo.add_game_player(gid, p2.id)

        await populated_repo.record_elimination(gid, p2.id, p1.id, position=2)

        alive = await populated_repo.get_alive_players(gid)
        assert len(alive) == 1
        assert alive[0].player_id == p1.id

    async def test_set_finish_position(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p1.id)
        await populated_repo.add_game_player(gid, p1.id)

        await populated_repo.set_finish_position(gid, p1.id, 1)
        players = await populated_repo.get_game_players(gid)
        assert players[0].finish_position == 1


# ── Elo history ────────────────────────────────────────────────────


class TestEloHistory:
    async def test_save_and_get_history(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        gid = await populated_repo.create_game(p.id)

        await populated_repo.save_elo_record(EloHistoryDTO(
            player_id=p.id, game_id=gid, elo_before=1200.0,
            elo_after=1250.0, elo_change=50.0, bounty_bonus=5.0,
            finish_position=1, players_count=5,
        ))

        history = await populated_repo.get_player_history(p.id)
        assert len(history) == 1
        assert history[0]["elo_before"] == 1200.0
        assert history[0]["elo_after"] == 1250.0

    async def test_get_game_results(self, populated_repo: Repository):
        p1 = await populated_repo.get_player_by_tg(1001)
        p2 = await populated_repo.get_player_by_tg(1002)
        gid = await populated_repo.create_game(p1.id)
        await populated_repo.add_game_player(gid, p1.id)
        await populated_repo.add_game_player(gid, p2.id)
        await populated_repo.set_finish_position(gid, p1.id, 1)
        await populated_repo.set_finish_position(gid, p2.id, 2)
        await populated_repo.record_elimination(gid, p2.id, p1.id, 2)

        await populated_repo.save_elo_record(EloHistoryDTO(
            player_id=p1.id, game_id=gid, elo_before=1200.0,
            elo_after=1230.0, elo_change=30.0, bounty_bonus=2.0,
            finish_position=1, players_count=2,
        ))

        results = await populated_repo.get_game_results(gid)
        assert len(results) == 2

    async def test_history_limit(self, populated_repo: Repository):
        p = await populated_repo.get_player_by_tg(1001)
        for i in range(15):
            gid = await populated_repo.create_game(p.id)
            await populated_repo.set_game_status(gid, "finished")
            await populated_repo.save_elo_record(EloHistoryDTO(
                player_id=p.id, game_id=gid, elo_before=1200.0 + i,
                elo_after=1200.0 + i + 10, elo_change=10.0, bounty_bonus=0.0,
                finish_position=1, players_count=5,
            ))

        history = await populated_repo.get_player_history(p.id, limit=5)
        assert len(history) == 5
