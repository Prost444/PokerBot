"""Tests for seating algorithms: snake draft and divisional."""

from shad_poker_bot.services.seating import (
    MAX_TABLE_SIZE,
    divisional_seating,
    find_table_for_late_join,
    snake_seating,
)


class TestSnakeSeating:
    def test_single_table_under_9(self):
        players = [(i, 1200.0 + i * 10) for i in range(1, 8)]
        result = snake_seating(players)
        assert len(result) == 7
        assert all(a.table_number == 1 for a in result)

    def test_two_tables_for_10_players(self):
        players = [(i, 1200.0 + i * 10) for i in range(1, 11)]
        result = snake_seating(players)
        tables = {a.table_number for a in result}
        assert len(tables) == 2

    def test_three_tables_for_20_players(self):
        players = [(i, 1200.0 + i * 10) for i in range(1, 21)]
        result = snake_seating(players)
        tables = {a.table_number for a in result}
        assert len(tables) == 3

    def test_snake_balances_elo(self):
        """Snake draft should make table averages roughly equal."""
        players = [(i, 1000.0 + i * 50) for i in range(1, 19)]
        result = snake_seating(players)

        table_elos: dict[int, list[float]] = {}
        player_elo_map = {pid: elo for pid, elo in players}
        for a in result:
            table_elos.setdefault(a.table_number, []).append(
                player_elo_map[a.player_id]
            )

        averages = [sum(elos) / len(elos) for elos in table_elos.values()]
        # Averages should be within ~100 of each other
        assert max(averages) - min(averages) < 100

    def test_snake_zigzag_pattern(self):
        """First player goes to table 1, second to table 2, third stays at 2, etc."""
        players = [(i, 2000.0 - i * 100) for i in range(1, 7)]
        result = snake_seating(players)
        # With 6 players and max 9, only 1 table
        assert all(a.table_number == 1 for a in result)

        # With 10 players, 2 tables
        players10 = [(i, 2000.0 - i * 100) for i in range(1, 11)]
        result10 = snake_seating(players10)
        # Sorted by elo desc: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
        # Snake: 1→T1, 2→T2, 3→T2, 4→T1, 5→T1, 6→T2, ...
        sorted_by_elo = sorted(players10, key=lambda x: x[1], reverse=True)
        assignment_map = {a.player_id: a.table_number for a in result10}

        # First player (highest elo) → table 1
        assert assignment_map[sorted_by_elo[0][0]] == 1
        # Second player → table 2
        assert assignment_map[sorted_by_elo[1][0]] == 2

    def test_empty_input(self):
        assert snake_seating([]) == []

    def test_max_table_size_respected(self):
        players = [(i, 1200.0) for i in range(1, 28)]
        result = snake_seating(players)
        table_counts: dict[int, int] = {}
        for a in result:
            table_counts[a.table_number] = table_counts.get(a.table_number, 0) + 1
        assert all(c <= MAX_TABLE_SIZE for c in table_counts.values())

    def test_all_players_assigned(self):
        for n in [1, 5, 9, 10, 18, 27]:
            players = [(i, 1200.0) for i in range(1, n + 1)]
            result = snake_seating(players)
            assert len(result) == n
            assigned_ids = {a.player_id for a in result}
            expected_ids = {i for i in range(1, n + 1)}
            assert assigned_ids == expected_ids


class TestDivisionalSeating:
    def test_single_table_under_9(self):
        players = [(i, 1200.0 + i * 10) for i in range(1, 8)]
        result = divisional_seating(players)
        assert len(result) == 7
        assert all(a.table_number == 1 for a in result)

    def test_divisional_groups_by_strength(self):
        """Divisional seating should put strong players together."""
        players = [(i, 1000.0 + i * 50) for i in range(1, 19)]
        result = divisional_seating(players)

        table_elos: dict[int, list[float]] = {}
        player_elo_map = {pid: elo for pid, elo in players}
        for a in result:
            table_elos.setdefault(a.table_number, []).append(
                player_elo_map[a.player_id]
            )

        averages = sorted(
            [(tnum, sum(elos) / len(elos)) for tnum, elos in table_elos.items()],
            key=lambda x: x[0],
        )
        # Table 1 should have the highest average (strongest players)
        assert averages[0][1] > averages[-1][1]

    def test_empty_input(self):
        assert divisional_seating([]) == []

    def test_all_players_assigned(self):
        for n in [1, 5, 9, 10, 18, 27]:
            players = [(i, 1200.0) for i in range(1, n + 1)]
            result = divisional_seating(players)
            assert len(result) == n


class TestFindTableForLateJoin:
    def test_returns_smallest_table(self):
        table_sizes = {1: 5, 2: 3, 3: 7}
        assert find_table_for_late_join(table_sizes) == 2

    def test_all_tables_full(self):
        table_sizes = {1: 9, 2: 9}
        assert find_table_for_late_join(table_sizes) == -1

    def test_empty_input(self):
        assert find_table_for_late_join({}) == -1

    def test_single_table_with_room(self):
        table_sizes = {1: 4}
        assert find_table_for_late_join(table_sizes) == 1

    def test_single_table_full(self):
        table_sizes = {1: 9}
        assert find_table_for_late_join(table_sizes) == -1

    def test_tie_breaks_by_table_number(self):
        table_sizes = {3: 4, 1: 4, 2: 4}
        assert find_table_for_late_join(table_sizes) == 1
