"""Shared fixtures for all test modules."""

import aiosqlite
import pytest
import pytest_asyncio

from shad_poker_bot.config import RatingConfig
from shad_poker_bot.db.models import SCHEMA
from shad_poker_bot.db.repository import Repository
from shad_poker_bot.services.game import GameService
from shad_poker_bot.services.rating import RatingEngine


@pytest.fixture
def rating_cfg() -> RatingConfig:
    return RatingConfig()


@pytest.fixture
def engine(rating_cfg: RatingConfig) -> RatingEngine:
    return RatingEngine(rating_cfg)


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite database with schema applied."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    await conn.commit()
    yield conn
    await conn.close()


@pytest_asyncio.fixture
async def repo(db) -> Repository:
    return Repository(db)


@pytest_asyncio.fixture
async def game_service(repo: Repository, rating_cfg: RatingConfig) -> GameService:
    return GameService(repo, rating_cfg)


@pytest_asyncio.fixture
async def populated_repo(repo: Repository) -> Repository:
    """Repo with 6 pre-registered players."""
    players = [
        (1001, "alice", "Alice"),
        (1002, "bob", "Bob"),
        (1003, "charlie", "Charlie"),
        (1004, "diana", "Diana"),
        (1005, "eve", "Eve"),
        (1006, "frank", "Frank"),
    ]
    for tg_id, username, name in players:
        await repo.add_player(tg_id, name, username)
    return repo
