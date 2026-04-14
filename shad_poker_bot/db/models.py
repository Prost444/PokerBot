"""Database schema definitions and initialisation."""

from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER UNIQUE NOT NULL,
    username        TEXT,
    display_name    TEXT NOT NULL,
    elo             REAL    DEFAULT 1200.0,
    games_played    INTEGER DEFAULT 0,
    total_knockouts INTEGER DEFAULT 0,
    attend_streak   INTEGER DEFAULT 0,
    registered_at   TEXT    DEFAULT (datetime('now')),
    is_active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS seasons (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    number      INTEGER UNIQUE NOT NULL,
    started_at  TEXT DEFAULT (datetime('now')),
    ended_at    TEXT,
    is_active   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id   INTEGER REFERENCES seasons(id),
    created_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT,
    status      TEXT DEFAULT 'registration',
    created_by  INTEGER REFERENCES players(id)
);

CREATE TABLE IF NOT EXISTS game_players (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id             INTEGER NOT NULL REFERENCES games(id),
    player_id           INTEGER NOT NULL REFERENCES players(id),
    finish_position     INTEGER,
    joined_at           TEXT DEFAULT (datetime('now')),
    is_late_join        INTEGER DEFAULT 0,
    eliminated_by_id    INTEGER REFERENCES players(id),
    UNIQUE(game_id, player_id)
);

CREATE TABLE IF NOT EXISTS elo_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    game_id         INTEGER NOT NULL REFERENCES games(id),
    elo_before      REAL    NOT NULL,
    elo_after       REAL    NOT NULL,
    elo_change      REAL    NOT NULL,
    bounty_bonus    REAL    DEFAULT 0,
    finish_position INTEGER,
    players_count   INTEGER,
    recorded_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_game_players_game   ON game_players(game_id);
CREATE INDEX IF NOT EXISTS idx_game_players_player ON game_players(player_id);
CREATE INDEX IF NOT EXISTS idx_elo_history_player   ON elo_history(player_id);
CREATE INDEX IF NOT EXISTS idx_elo_history_game     ON elo_history(game_id);
CREATE INDEX IF NOT EXISTS idx_games_status         ON games(status);
"""


async def init_db(db_path: Path) -> aiosqlite.Connection:
    """Create tables if needed and return an open connection."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.executescript(SCHEMA)
    await db.commit()
    return db
