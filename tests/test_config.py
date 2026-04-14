"""Tests for configuration module."""

from shad_poker_bot.config import AdminConfig, RatingConfig


class TestRatingConfig:
    def test_defaults(self):
        cfg = RatingConfig()
        assert cfg.initial_elo == 1200.0
        assert cfg.k_new_player == 40
        assert cfg.k_developing == 30
        assert cfg.k_established == 20
        assert cfg.bounty_base == 2.0
        assert cfg.bounty_min == 1.0
        assert cfg.attendance_bonus_cap == 1.25
        assert cfg.season_regression_weight == 0.8

    def test_frozen(self):
        """Config should be immutable."""
        cfg = RatingConfig()
        import dataclasses
        assert dataclasses.fields(cfg)  # is a dataclass
        # frozen=True means we can't assign
        try:
            cfg.initial_elo = 999  # type: ignore
            assert False, "Should have raised FrozenInstanceError"
        except (AttributeError, dataclasses.FrozenInstanceError):
            pass


class TestAdminConfig:
    def test_empty_by_default(self):
        cfg = AdminConfig()
        assert cfg.admin_ids == []

    def test_with_ids(self):
        cfg = AdminConfig(admin_ids=[123, 456])
        assert 123 in cfg.admin_ids
        assert 789 not in cfg.admin_ids
