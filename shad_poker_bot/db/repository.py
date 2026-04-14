"""Data access layer — all SQL lives here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import aiosqlite

# ── lightweight DTOs ────────────────────────────────────────────────

@dataclass
class PlayerDTO:
    id: int
    telegram_id: int
    username: Optional[str]
    display_name: str
    elo: float
    games_played: int
    total_knockouts: int
    attend_streak: int


@dataclass
class GameDTO:
    id: int
    season_id: Optional[int]
    status: str
    created_at: str
    finished_at: Optional[str]
    game_type: str      # 'regular' or 'tournament'
    seating_type: str   # 'snake' or 'divisional'


@dataclass
class GameTableDTO:
    id: int
    game_id: int
    table_number: int
    status: str           # 'active' or 'finished'
    finished_at: Optional[str]


@dataclass
class GamePlayerDTO:
    id: int
    game_id: int
    player_id: int
    table_id: Optional[int]
    finish_position: Optional[int]
    final_chips: Optional[int]
    is_late_join: bool
    eliminated_by_id: Optional[int]


@dataclass
class EloHistoryDTO:
    player_id: int
    game_id: int
    elo_before: float
    elo_after: float
    elo_change: float
    bounty_bonus: float
    finish_position: int
    players_count: int
    table_id: Optional[int] = None


# ── Repository ──────────────────────────────────────────────────────

class Repository:
    """Thin async wrapper around SQLite queries."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    # ── Players ─────────────────────────────────────────────────────

    async def add_player(
        self,
        telegram_id: int,
        display_name: str,
        username: Optional[str] = None,
        initial_elo: float = 1200.0,
    ) -> PlayerDTO:
        await self._db.execute(
            """INSERT INTO players (telegram_id, username, display_name, elo)
               VALUES (?, ?, ?, ?)""",
            (telegram_id, username, display_name, initial_elo),
        )
        await self._db.commit()
        return await self.get_player_by_tg(telegram_id)  # type: ignore[return-value]

    async def get_player_by_tg(self, telegram_id: int) -> Optional[PlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM players WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cur.fetchone()
        return self._to_player(row) if row else None

    async def get_player(self, player_id: int) -> Optional[PlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM players WHERE id = ?", (player_id,)
        )
        row = await cur.fetchone()
        return self._to_player(row) if row else None

    async def get_leaderboard(self, limit: int = 20) -> list[PlayerDTO]:
        cur = await self._db.execute(
            """SELECT * FROM players
               WHERE is_active = 1 AND games_played > 0
               ORDER BY elo DESC LIMIT ?""",
            (limit,),
        )
        return [self._to_player(r) for r in await cur.fetchall()]

    async def update_player_elo(
        self, player_id: int, new_elo: float, increment_games: bool = True
    ) -> None:
        if increment_games:
            await self._db.execute(
                "UPDATE players SET elo = ?, games_played = games_played + 1 WHERE id = ?",
                (new_elo, player_id),
            )
        else:
            await self._db.execute(
                "UPDATE players SET elo = ? WHERE id = ?", (new_elo, player_id)
            )
        await self._db.commit()

    async def increment_knockouts(self, player_id: int, count: int = 1) -> None:
        await self._db.execute(
            "UPDATE players SET total_knockouts = total_knockouts + ? WHERE id = ?",
            (count, player_id),
        )
        await self._db.commit()

    async def update_attend_streak(self, player_id: int, streak: int) -> None:
        await self._db.execute(
            "UPDATE players SET attend_streak = ? WHERE id = ?",
            (streak, player_id),
        )
        await self._db.commit()

    async def get_all_active_players(self) -> list[PlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM players WHERE is_active = 1 ORDER BY elo DESC"
        )
        return [self._to_player(r) for r in await cur.fetchall()]

    # ── Seasons ─────────────────────────────────────────────────────

    async def get_active_season(self) -> Optional[int]:
        cur = await self._db.execute(
            "SELECT id FROM seasons WHERE is_active = 1 ORDER BY number DESC LIMIT 1"
        )
        row = await cur.fetchone()
        return row["id"] if row else None

    async def create_season(self, number: int) -> int:
        cur = await self._db.execute(
            "INSERT INTO seasons (number) VALUES (?)", (number,)
        )
        await self._db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    # ── Games ───────────────────────────────────────────────────────

    async def create_game(
        self,
        created_by: int,
        season_id: Optional[int] = None,
        game_type: str = "regular",
        seating_type: str = "snake",
    ) -> int:
        cur = await self._db.execute(
            "INSERT INTO games (season_id, created_by, game_type, seating_type)"
            " VALUES (?, ?, ?, ?)",
            (season_id, created_by, game_type, seating_type),
        )
        await self._db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    async def get_active_game(self) -> Optional[GameDTO]:
        cur = await self._db.execute(
            "SELECT * FROM games WHERE status IN ('registration', 'active')"
            " ORDER BY id DESC LIMIT 1"
        )
        row = await cur.fetchone()
        return self._to_game(row) if row else None

    async def get_game(self, game_id: int) -> Optional[GameDTO]:
        cur = await self._db.execute("SELECT * FROM games WHERE id = ?", (game_id,))
        row = await cur.fetchone()
        return self._to_game(row) if row else None

    async def set_game_status(self, game_id: int, status: str) -> None:
        extra = ", finished_at = datetime('now')" if status == "finished" else ""
        await self._db.execute(
            f"UPDATE games SET status = ?{extra} WHERE id = ?", (status, game_id)
        )
        await self._db.commit()

    # ── Game tables ─────────────────────────────────────────────────

    async def create_game_table(self, game_id: int, table_number: int) -> int:
        cur = await self._db.execute(
            "INSERT INTO game_tables (game_id, table_number) VALUES (?, ?)",
            (game_id, table_number),
        )
        await self._db.commit()
        return cur.lastrowid  # type: ignore[return-value]

    async def get_game_tables(self, game_id: int) -> list[GameTableDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_tables WHERE game_id = ? ORDER BY table_number",
            (game_id,),
        )
        return [self._to_table(r) for r in await cur.fetchall()]

    async def get_game_table(self, table_id: int) -> Optional[GameTableDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_tables WHERE id = ?", (table_id,)
        )
        row = await cur.fetchone()
        return self._to_table(row) if row else None

    async def get_game_table_by_number(
        self, game_id: int, table_number: int
    ) -> Optional[GameTableDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_tables WHERE game_id = ? AND table_number = ?",
            (game_id, table_number),
        )
        row = await cur.fetchone()
        return self._to_table(row) if row else None

    async def get_active_tables(self, game_id: int) -> list[GameTableDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_tables WHERE game_id = ? AND status = 'active'"
            " ORDER BY table_number",
            (game_id,),
        )
        return [self._to_table(r) for r in await cur.fetchall()]

    async def set_table_status(self, table_id: int, status: str) -> None:
        extra = ", finished_at = datetime('now')" if status == "finished" else ""
        await self._db.execute(
            f"UPDATE game_tables SET status = ?{extra} WHERE id = ?",
            (status, table_id),
        )
        await self._db.commit()

    # ── Game players ────────────────────────────────────────────────

    async def add_game_player(
        self, game_id: int, player_id: int, is_late: bool = False,
        table_id: Optional[int] = None,
    ) -> None:
        await self._db.execute(
            "INSERT OR IGNORE INTO game_players"
            " (game_id, player_id, is_late_join, table_id) VALUES (?, ?, ?, ?)",
            (game_id, player_id, int(is_late), table_id),
        )
        await self._db.commit()

    async def set_player_table(
        self, game_id: int, player_id: int, table_id: int
    ) -> None:
        await self._db.execute(
            "UPDATE game_players SET table_id = ? WHERE game_id = ? AND player_id = ?",
            (table_id, game_id, player_id),
        )
        await self._db.commit()

    async def get_game_players(self, game_id: int) -> list[GamePlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_players WHERE game_id = ? ORDER BY finish_position ASC NULLS LAST",
            (game_id,),
        )
        return [self._to_gp(r) for r in await cur.fetchall()]

    async def get_table_players(self, table_id: int) -> list[GamePlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_players WHERE table_id = ?"
            " ORDER BY finish_position ASC NULLS LAST",
            (table_id,),
        )
        return [self._to_gp(r) for r in await cur.fetchall()]

    async def record_elimination(
        self, game_id: int, eliminated_id: int, eliminated_by_id: int, position: int
    ) -> None:
        await self._db.execute(
            """UPDATE game_players
               SET finish_position = ?, eliminated_by_id = ?
               WHERE game_id = ? AND player_id = ?""",
            (position, eliminated_by_id, game_id, eliminated_id),
        )
        await self._db.commit()

    async def set_finish_position(
        self, game_id: int, player_id: int, position: int
    ) -> None:
        await self._db.execute(
            "UPDATE game_players SET finish_position = ? WHERE game_id = ? AND player_id = ?",
            (position, game_id, player_id),
        )
        await self._db.commit()

    async def count_alive_players(self, game_id: int) -> int:
        cur = await self._db.execute(
            "SELECT COUNT(*) as cnt FROM game_players"
            " WHERE game_id = ? AND finish_position IS NULL",
            (game_id,),
        )
        row = await cur.fetchone()
        return row["cnt"]

    async def count_alive_at_table(self, table_id: int) -> int:
        cur = await self._db.execute(
            "SELECT COUNT(*) as cnt FROM game_players"
            " WHERE table_id = ? AND finish_position IS NULL",
            (table_id,),
        )
        row = await cur.fetchone()
        return row["cnt"]

    async def get_alive_players(self, game_id: int) -> list[GamePlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_players WHERE game_id = ? AND finish_position IS NULL",
            (game_id,),
        )
        return [self._to_gp(r) for r in await cur.fetchall()]

    async def get_alive_at_table(self, table_id: int) -> list[GamePlayerDTO]:
        cur = await self._db.execute(
            "SELECT * FROM game_players WHERE table_id = ? AND finish_position IS NULL",
            (table_id,),
        )
        return [self._to_gp(r) for r in await cur.fetchall()]

    async def find_player_table(self, game_id: int, player_id: int) -> Optional[int]:
        """Return the table_id for a player in a game, or None."""
        cur = await self._db.execute(
            "SELECT table_id FROM game_players WHERE game_id = ? AND player_id = ?",
            (game_id, player_id),
        )
        row = await cur.fetchone()
        return row["table_id"] if row else None

    async def set_final_chips(
        self, game_id: int, player_id: int, chips: int
    ) -> None:
        await self._db.execute(
            "UPDATE game_players SET final_chips = ?"
            " WHERE game_id = ? AND player_id = ?",
            (chips, game_id, player_id),
        )
        await self._db.commit()

    # ── Elo history ─────────────────────────────────────────────────

    async def save_elo_record(self, rec: EloHistoryDTO) -> None:
        await self._db.execute(
            """INSERT INTO elo_history
               (player_id, game_id, table_id, elo_before, elo_after, elo_change,
                bounty_bonus, finish_position, players_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rec.player_id, rec.game_id, rec.table_id,
                rec.elo_before, rec.elo_after,
                rec.elo_change, rec.bounty_bonus, rec.finish_position,
                rec.players_count,
            ),
        )
        await self._db.commit()

    async def get_player_history(
        self, player_id: int, limit: int = 20
    ) -> list[dict]:
        cur = await self._db.execute(
            """SELECT eh.*, g.created_at as game_date
               FROM elo_history eh
               JOIN games g ON g.id = eh.game_id
               WHERE eh.player_id = ?
               ORDER BY eh.recorded_at DESC LIMIT ?""",
            (player_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_game_results(self, game_id: int) -> list[dict]:
        cur = await self._db.execute(
            """SELECT gp.finish_position, p.display_name, p.elo,
                      eh.elo_change, eh.bounty_bonus,
                      eliminator.display_name as eliminated_by_name
               FROM game_players gp
               JOIN players p ON p.id = gp.player_id
               LEFT JOIN elo_history eh ON eh.game_id = gp.game_id AND eh.player_id = gp.player_id
               LEFT JOIN players eliminator ON eliminator.id = gp.eliminated_by_id
               WHERE gp.game_id = ?
               ORDER BY gp.finish_position ASC""",
            (game_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    # ── private helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_player(row: aiosqlite.Row) -> PlayerDTO:
        return PlayerDTO(
            id=row["id"],
            telegram_id=row["telegram_id"],
            username=row["username"],
            display_name=row["display_name"],
            elo=row["elo"],
            games_played=row["games_played"],
            total_knockouts=row["total_knockouts"],
            attend_streak=row["attend_streak"],
        )

    @staticmethod
    def _to_game(row: aiosqlite.Row) -> GameDTO:
        return GameDTO(
            id=row["id"],
            season_id=row["season_id"],
            status=row["status"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            game_type=row["game_type"],
            seating_type=row["seating_type"],
        )

    @staticmethod
    def _to_table(row: aiosqlite.Row) -> GameTableDTO:
        return GameTableDTO(
            id=row["id"],
            game_id=row["game_id"],
            table_number=row["table_number"],
            status=row["status"],
            finished_at=row["finished_at"],
        )

    @staticmethod
    def _to_gp(row: aiosqlite.Row) -> GamePlayerDTO:
        return GamePlayerDTO(
            id=row["id"],
            game_id=row["game_id"],
            player_id=row["player_id"],
            table_id=row["table_id"],
            finish_position=row["finish_position"],
            final_chips=row["final_chips"],
            is_late_join=bool(row["is_late_join"]),
            eliminated_by_id=row["eliminated_by_id"],
        )
