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
from shad_poker_bot.services.seating import (
    divisional_seating,
    snake_seating,
)


@dataclass
class GameSummary:
    game_id: int
    player_count: int
    results: list[RatingDelta]


@dataclass
class TableSummary:
    table_id: int
    table_number: int
    player_count: int
    results: list[RatingDelta]


@dataclass
class SeatingResult:
    """Result of auto-seating: table_number -> list of player display names."""
    tables: dict[int, list[str]]


class GameError(Exception):
    """Raised when a game-flow rule is violated."""


class GameService:
    """High-level commands used by Telegram handlers."""

    def __init__(self, repo: Repository, rating_cfg: RatingConfig | None = None) -> None:
        self.repo = repo
        self.rating_cfg = rating_cfg or RatingConfig()
        self.engine = RatingEngine(self.rating_cfg)

    # ── Game lifecycle ──────────────────────────────────────────────

    async def create_game(
        self,
        admin_player_id: int,
        game_type: str = "regular",
        seating_type: str = "snake",
    ) -> GameDTO:
        existing = await self.repo.get_active_game()
        if existing:
            raise GameError(
                "There is already an active game. "
                "Finish it before creating a new one."
            )

        if game_type not in ("regular", "tournament"):
            raise GameError("Game type must be 'regular' or 'tournament'.")
        if seating_type not in ("snake", "divisional"):
            raise GameError("Seating type must be 'snake' or 'divisional'.")

        season_id = await self.repo.get_active_season()
        game_id = await self.repo.create_game(
            admin_player_id, season_id, game_type, seating_type,
        )
        return await self.repo.get_game(game_id)  # type: ignore[return-value]

    async def start_game(self, game_id: int) -> SeatingResult:
        """Move from registration -> active. Generate seating and return it."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "registration":
            raise GameError("Game is already started or finished.")
        players = await self.repo.get_game_players(game_id)
        if len(players) < 2:
            raise GameError("Need at least 2 players to start.")

        await self.repo.set_game_status(game_id, "active")

        # Build seating
        player_data: list[tuple[int, float]] = []
        player_names: dict[int, str] = {}
        for gp in players:
            p = await self.repo.get_player(gp.player_id)
            if p:
                player_data.append((p.id, p.elo))
                player_names[p.id] = p.display_name

        if game.seating_type == "divisional":
            assignments = divisional_seating(player_data)
        else:
            assignments = snake_seating(player_data)

        # Create tables and assign players
        table_numbers = sorted({a.table_number for a in assignments})
        table_id_map: dict[int, int] = {}
        for tn in table_numbers:
            tid = await self.repo.create_game_table(game_id, tn)
            table_id_map[tn] = tid

        for a in assignments:
            await self.repo.set_player_table(
                game_id, a.player_id, table_id_map[a.table_number],
            )

        # Build result
        tables: dict[int, list[str]] = {}
        for a in assignments:
            tables.setdefault(a.table_number, []).append(
                player_names.get(a.player_id, "???")
            )

        return SeatingResult(tables=tables)

    async def join_game(
        self, telegram_id: int, table_number: int | None = None,
    ) -> tuple[GameDTO, PlayerDTO, int | None]:
        """Player joins the current active/registration game.

        Args:
            telegram_id: Telegram user ID.
            table_number: For late join, the player's chosen table number.
                          If None during an active game, returns available
                          tables info instead of auto-assigning.

        Returns (game, player, assigned_table_number_or_None).
        """
        game = await self.repo.get_active_game()
        if not game:
            raise GameError(
                "No active game right now. Ask an admin to create one."
            )

        player = await self.repo.get_player_by_tg(telegram_id)
        if not player:
            raise GameError("You are not registered yet. Use /register")

        is_late = game.status == "active"
        table_id: int | None = None
        assigned_table: int | None = None

        if is_late:
            active_tables = await self.repo.get_active_tables(game.id)
            if not active_tables:
                raise GameError("No active tables available.")

            if table_number is not None:
                # Player chose a specific table
                tbl = await self.repo.get_game_table_by_number(
                    game.id, table_number,
                )
                if not tbl or tbl.status != "active":
                    raise GameError(
                        f"Table {table_number} not found or already closed."
                    )
                t_players = await self.repo.get_table_players(tbl.id)
                if len(t_players) >= 9:
                    raise GameError(
                        f"Table {table_number} is full (9 players)."
                    )
                table_id = tbl.id
                assigned_table = table_number
            else:
                # No table chosen — list available tables
                lines: list[str] = []
                for t in active_tables:
                    t_players = await self.repo.get_table_players(t.id)
                    count = len(t_players)
                    if count < 9:
                        lines.append(
                            f"  Table {t.table_number}: "
                            f"{count}/9 players"
                        )
                if lines:
                    raise GameError(
                        "Choose a table to join:\n"
                        + "\n".join(lines)
                        + "\n\nUse: /join <table_number>"
                    )
                else:
                    raise GameError(
                        "All tables are full. Ask admin to open a new one."
                    )

        await self.repo.add_game_player(game.id, player.id, is_late, table_id)
        return game, player, assigned_table

    # ── During game ─────────────────────────────────────────────────

    async def record_chips(
        self,
        game_id: int,
        player_tg: int,
        chips: int,
    ) -> tuple[str, int]:
        """Record final chip count for a player. Returns (name, chips)."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "active":
            raise GameError("Game is not in active status.")

        player = await self.repo.get_player_by_tg(player_tg)
        if not player:
            raise GameError("Player not found.")

        if chips < 0:
            raise GameError("Chip count cannot be negative.")

        await self.repo.set_final_chips(game_id, player.id, chips)
        return player.display_name, chips

    async def record_knockout(
        self,
        game_id: int,
        eliminated_tg: int,
        eliminator_tg: int,
    ) -> tuple[str, str, int, int | None]:
        """Record a player elimination.

        Returns (eliminated_name, eliminator_name, position, table_number).
        """
        game = await self._get_game_or_raise(game_id)
        if game.status != "active":
            raise GameError("Game is not in active status.")

        eliminated = await self.repo.get_player_by_tg(eliminated_tg)
        eliminator = await self.repo.get_player_by_tg(eliminator_tg)
        if not eliminated or not eliminator:
            raise GameError("One of the players was not found.")

        # Determine table context for position calculation
        table_id = await self.repo.find_player_table(
            game_id, eliminated.id,
        )
        table_number: int | None = None

        if table_id:
            alive = await self.repo.count_alive_at_table(table_id)
            tbl = await self.repo.get_game_table(table_id)
            if tbl:
                table_number = tbl.table_number
        else:
            alive = await self.repo.count_alive_players(game_id)

        position = alive

        await self.repo.record_elimination(
            game_id, eliminated.id, eliminator.id, position,
        )
        await self.repo.increment_knockouts(eliminator.id)
        # Eliminated player's chips are 0
        await self.repo.set_final_chips(game_id, eliminated.id, 0)

        return (
            eliminated.display_name,
            eliminator.display_name,
            position,
            table_number,
        )

    # ── Close a single table ────────────────────────────────────────

    async def close_table(
        self, game_id: int, table_number: int,
    ) -> TableSummary:
        """Close a specific table and calculate ratings for its players."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "active":
            raise GameError("Game is not in active status.")

        tbl = await self.repo.get_game_table_by_number(game_id, table_number)
        if not tbl:
            raise GameError(f"Table {table_number} not found.")
        if tbl.status != "active":
            raise GameError(f"Table {table_number} is already closed.")

        # Assign positions to remaining alive players based on chip count
        alive = await self.repo.get_alive_at_table(tbl.id)
        if len(alive) == 1:
            await self.repo.set_finish_position(
                game_id, alive[0].player_id, 1,
            )
        elif len(alive) > 1:
            # Sort by chip count (descending) — more chips = better position
            alive_with_chips: list[tuple[int, int]] = []
            for gp in alive:
                chips = gp.final_chips if gp.final_chips is not None else 0
                alive_with_chips.append((gp.player_id, chips))
            alive_with_chips.sort(key=lambda x: x[1], reverse=True)
            for i, (pid, _) in enumerate(alive_with_chips, start=1):
                await self.repo.set_finish_position(game_id, pid, i)

        # Calculate ratings for this table
        all_gps = await self.repo.get_table_players(tbl.id)
        n = len(all_gps)

        is_tournament = game.game_type == "tournament"
        player_results = await self._build_player_results(
            all_gps, n, is_tournament,
        )

        deltas = self.engine.process_game(player_results)

        # Persist rating changes
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
                table_id=tbl.id,
            ))

        await self.repo.set_table_status(tbl.id, "finished")

        return TableSummary(
            table_id=tbl.id,
            table_number=table_number,
            player_count=n,
            results=deltas,
        )

    # ── Finish game ─────────────────────────────────────────────────

    async def finish_game(self, game_id: int) -> GameSummary:
        """End the game: close remaining tables, update attendance."""
        game = await self._get_game_or_raise(game_id)
        if game.status != "active":
            raise GameError("Game is not in active status.")

        # Close any remaining active tables
        active_tables = await self.repo.get_active_tables(game_id)
        all_deltas: list[RatingDelta] = []

        if active_tables:
            for atbl in active_tables:
                ts = await self.close_table(game_id, atbl.table_number)
                all_deltas.extend(ts.results)
        else:
            all_deltas = await self._finish_single_table(game_id, game)

        # Update attendance streaks
        all_gps = await self.repo.get_game_players(game_id)
        all_active = await self.repo.get_all_active_players()
        participant_ids = {gp.player_id for gp in all_gps}
        for p in all_active:
            if p.id in participant_ids:
                await self.repo.update_attend_streak(
                    p.id, p.attend_streak + 1,
                )
            else:
                if p.attend_streak > 0 and p.games_played > 0:
                    await self.repo.update_attend_streak(p.id, 0)

        await self.repo.set_game_status(game_id, "finished")

        return GameSummary(
            game_id=game_id,
            player_count=len(all_gps),
            results=all_deltas,
        )

    async def _finish_single_table(
        self, game_id: int, game: GameDTO,
    ) -> list[RatingDelta]:
        """Legacy path: finish a game with no explicit tables."""
        alive = await self.repo.get_alive_players(game_id)
        if len(alive) == 1:
            await self.repo.set_finish_position(
                game_id, alive[0].player_id, 1,
            )
        elif len(alive) > 1:
            alive_with_chips = []
            for gp in alive:
                chips = gp.final_chips if gp.final_chips is not None else 0
                alive_with_chips.append((gp.player_id, chips))
            alive_with_chips.sort(key=lambda x: x[1], reverse=True)
            for i, (pid, _) in enumerate(alive_with_chips, start=1):
                await self.repo.set_finish_position(game_id, pid, i)

        all_gps = await self.repo.get_game_players(game_id)
        n = len(all_gps)

        is_tournament = game.game_type == "tournament"
        player_results = await self._build_player_results(
            all_gps, n, is_tournament,
        )

        deltas = self.engine.process_game(player_results)

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

        return deltas

    # ── Helpers ─────────────────────────────────────────────────────

    async def _build_player_results(
        self, all_gps, n: int, is_tournament: bool,
    ) -> list[PlayerResult]:
        """Build PlayerResult list with chip factors."""
        # Compute average chips among players who have chip data
        chip_values = [
            gp.final_chips for gp in all_gps
            if gp.final_chips is not None and gp.final_chips > 0
        ]
        avg_chips = (
            sum(chip_values) / len(chip_values)
            if chip_values else float(self.rating_cfg.starting_chips)
        )

        player_results: list[PlayerResult] = []
        for gp in all_gps:
            player = await self.repo.get_player(gp.player_id)
            if not player:
                continue

            knockouts_elos: list[float] = []
            if is_tournament:
                knockouts_elos = [
                    (await self.repo.get_player(other.player_id)).elo  # type: ignore[union-attr]
                    for other in all_gps
                    if other.eliminated_by_id == player.id
                ]

            # Compute chip factor
            chip_factor = 1.0
            if gp.final_chips is not None and gp.final_chips > 0:
                raw = 1.0 + self.rating_cfg.chip_weight * (
                    gp.final_chips / avg_chips - 1.0
                )
                chip_factor = max(0.5, min(1.5, raw))
            # Eliminated players (chips=0 or None) get factor 1.0

            player_results.append(PlayerResult(
                player_id=player.id,
                elo=player.elo,
                games_played=player.games_played,
                attend_streak=player.attend_streak,
                position=gp.finish_position or n,
                knockouts=knockouts_elos,
                chip_factor=chip_factor,
            ))

        return player_results

    async def _get_game_or_raise(self, game_id: int) -> GameDTO:
        game = await self.repo.get_game(game_id)
        if not game:
            raise GameError("Game not found.")
        return game
