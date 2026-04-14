"""Game session orchestrator — ties together DB and rating engine."""

from __future__ import annotations

from dataclasses import dataclass

from shad_poker_bot.config import RatingConfig
from shad_poker_bot.db.repository import (
    EloHistoryDTO,
    GameDTO,
    PlayerDTO,
    Repository,
)
from shad_poker_bot.services.rating import PlayerResult, RatingDelta, RatingEngine


@dataclass
class GameSummary:
    game_id: int
    player_count: int
    results: list[RatingDelta]


class GameError(Exception):
    """Raised when a game-flow rule is violated."""


class GameService:
    """High-level commands used by Telegram handlers."""

    def __init__(self, repo: Repository, rating_cfg: RatingConfig | None = None) -> None:
        self.repo = repo
        self.engine = RatingEngine(rating_cfg)

    # ── Game lifecycle ──────────────────────────────────────────────

    async def create_game(self, admin_player_id: int) -> GameDTO:
        existing = await self.repo.get_active_game()
        if existing:
            raise GameError("Уже есть активная игра. Заверши её перед созданием новой.")

        season_id = await self.repo.get_active_season()
        game_id = await self.repo.create_game(admin_player_id, season_id)
        return await self.repo.get_game(game_id)  # type: ignore[return-value]

    async def start_game(self, game_id: int) -> int:
        """Move from registration → active. Returns player count."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "registration":
            raise GameError("Игра уже запущена или завершена.")
        players = await self.repo.get_game_players(game_id)
        if len(players) < 2:
            raise GameError("Нужно минимум 2 игрока, чтобы начать.")
        await self.repo.set_game_status(game_id, "active")
        return len(players)

    async def join_game(self, telegram_id: int) -> tuple[GameDTO, PlayerDTO]:
        """Player joins the current active/registration game."""
        game = await self.repo.get_active_game()
        if not game:
            raise GameError("Сейчас нет активной игры. Попроси админа создать.")

        player = await self.repo.get_player_by_tg(telegram_id)
        if not player:
            raise GameError("Ты ещё не зарегистрирован. Используй /register")

        is_late = game.status == "active"
        await self.repo.add_game_player(game.id, player.id, is_late)
        return game, player

    # ── During game ─────────────────────────────────────────────────

    async def record_knockout(
        self,
        game_id: int,
        eliminated_tg: int,
        eliminator_tg: int,
    ) -> tuple[str, str, int]:
        """Record a player elimination. Returns (eliminated_name, eliminator_name, position)."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "active":
            raise GameError("Игра не в активном статусе.")

        eliminated = await self.repo.get_player_by_tg(eliminated_tg)
        eliminator = await self.repo.get_player_by_tg(eliminator_tg)
        if not eliminated or not eliminator:
            raise GameError("Один из игроков не найден.")

        alive = await self.repo.count_alive_players(game_id)
        position = alive  # the eliminated player gets current alive count as position

        await self.repo.record_elimination(game_id, eliminated.id, eliminator.id, position)
        await self.repo.increment_knockouts(eliminator.id)

        return eliminated.display_name, eliminator.display_name, position

    # ── Finish game ─────────────────────────────────────────────────

    async def finish_game(self, game_id: int) -> GameSummary:
        """End the game, compute ratings for everyone, persist results."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "active":
            raise GameError("Игра не в активном статусе.")

        # Assign position 1 to the last player standing
        alive = await self.repo.get_alive_players(game_id)
        if len(alive) == 1:
            await self.repo.set_finish_position(game_id, alive[0].player_id, 1)
        elif len(alive) > 1:
            # Multiple survivors — rank them equally at position 1
            # (in practice admin should knockout until 1 remains)
            for i, gp in enumerate(alive, start=1):
                await self.repo.set_finish_position(game_id, gp.player_id, i)

        # Build PlayerResult list
        all_gps = await self.repo.get_game_players(game_id)
        n = len(all_gps)

        player_results: list[PlayerResult] = []
        for gp in all_gps:
            player = await self.repo.get_player(gp.player_id)
            if not player:
                continue

            # Collect Elo of victims knocked out by this player
            knockouts_elos = [
                (await self.repo.get_player(other.player_id)).elo  # type: ignore[union-attr]
                for other in all_gps
                if other.eliminated_by_id == player.id
            ]

            player_results.append(PlayerResult(
                player_id=player.id,
                elo=player.elo,
                games_played=player.games_played,
                attend_streak=player.attend_streak,
                position=gp.finish_position or n,
                knockouts=knockouts_elos,
            ))

        # Compute deltas
        deltas = self.engine.process_game(player_results)

        # Persist everything
        for d in deltas:
            await self.repo.update_player_elo(d.player_id, d.elo_after)
            await self.repo.save_elo_record(EloHistoryDTO(
                player_id=d.player_id,
                game_id=game_id,
                elo_before=d.elo_before,
                elo_after=d.elo_after,
                elo_change=d.elo_change,
                bounty_bonus=d.bounty_bonus,
                finish_position=next(
                    gp.finish_position or n
                    for gp in all_gps if gp.player_id == d.player_id
                ),
                players_count=n,
            ))

        # Update attendance streaks
        all_active = await self.repo.get_all_active_players()
        participant_ids = {gp.player_id for gp in all_gps}
        for p in all_active:
            if p.id in participant_ids:
                await self.repo.update_attend_streak(p.id, p.attend_streak + 1)
            else:
                # Only reset if they had a streak (don't penalise those who never played)
                if p.attend_streak > 0 and p.games_played > 0:
                    await self.repo.update_attend_streak(p.id, 0)

        await self.repo.set_game_status(game_id, "finished")

        return GameSummary(game_id=game_id, player_count=n, results=deltas)

    # ── Helpers ─────────────────────────────────────────────────────

    async def _get_game_or_raise(self, game_id: int) -> GameDTO:
        game = await self.repo.get_game(game_id)
        if not game:
            raise GameError("Игра не найдена.")
        return game
