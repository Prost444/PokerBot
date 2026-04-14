"""Application configuration — loaded from environment variables."""

from dataclasses import dataclass, field
from os import getenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BotConfig:
    token: str = ""


@dataclass(frozen=True)
class DBConfig:
    path: Path = BASE_DIR / "data" / "poker.db"


@dataclass(frozen=True)
class RatingConfig:
    """Tuneable constants for the Elo + bounty system."""

    initial_elo: float = 1200.0
    k_new_player: int = 40       # first 10 games
    k_developing: int = 30       # elo < 1400
    k_established: int = 20      # elo >= 1400
    new_player_threshold: int = 10

    bounty_base: float = 2.0
    bounty_elo_divisor: float = 200.0
    bounty_min: float = 1.0

    attendance_bonus_step: float = 0.05
    attendance_bonus_cap: float = 1.25

    chip_weight: float = 0.3        # how much chip count influences rating
    starting_chips: int = 5000

    season_regression_weight: float = 0.8  # R_new = R*0.8 + 1200*0.2
    season_length_weeks: int = 8
    season_best_of: int = 6


@dataclass(frozen=True)
class AdminConfig:
    admin_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    bot: BotConfig
    db: DBConfig
    rating: RatingConfig
    admin: AdminConfig


def load_config() -> Config:
    """Build config from environment / .env file."""
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")

    admin_raw = getenv("ADMIN_IDS", "")
    admin_ids = [int(x.strip()) for x in admin_raw.split(",") if x.strip()]

    return Config(
        bot=BotConfig(token=getenv("BOT_TOKEN", "")),
        db=DBConfig(path=Path(getenv("DB_PATH", str(BASE_DIR / "data" / "poker.db")))),
        rating=RatingConfig(),
        admin=AdminConfig(admin_ids=admin_ids),
    )
