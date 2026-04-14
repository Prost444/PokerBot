"""Table seating algorithms: snake draft and divisional."""

from __future__ import annotations

from dataclasses import dataclass

MAX_TABLE_SIZE = 9


@dataclass
class TableAssignment:
    """One player's table assignment."""
    player_id: int
    table_number: int  # 1-based


def _num_tables(player_count: int) -> int:
    """Calculate the minimum number of tables needed (max 9 per table)."""
    if player_count <= MAX_TABLE_SIZE:
        return 1
    return (player_count + MAX_TABLE_SIZE - 1) // MAX_TABLE_SIZE


def snake_seating(
    players: list[tuple[int, float]],
) -> list[TableAssignment]:
    """Distribute players across tables using snake draft by rating.

    Players are sorted by Elo (descending) and distributed in a zigzag
    pattern across tables so that each table has roughly equal average Elo.

    Example with 3 tables: 1→A, 2→B, 3→C, 4→C, 5→B, 6→A, 7→A, ...

    Args:
        players: list of (player_id, elo) tuples.

    Returns:
        List of TableAssignment objects.
    """
    if not players:
        return []

    n_tables = _num_tables(len(players))
    if n_tables == 1:
        return [TableAssignment(pid, 1) for pid, _ in players]

    sorted_players = sorted(players, key=lambda x: x[1], reverse=True)

    assignments: list[TableAssignment] = []
    for idx, (pid, _elo) in enumerate(sorted_players):
        cycle = idx // n_tables
        pos_in_cycle = idx % n_tables
        if cycle % 2 == 0:
            table = pos_in_cycle + 1
        else:
            table = n_tables - pos_in_cycle
        assignments.append(TableAssignment(pid, table))

    return assignments


def divisional_seating(
    players: list[tuple[int, float]],
) -> list[TableAssignment]:
    """Distribute players across tables by divisions (strong with strong).

    Players are sorted by Elo (descending) and fill tables sequentially.
    Table 1 gets the strongest players, table 2 the next tier, etc.

    Args:
        players: list of (player_id, elo) tuples.

    Returns:
        List of TableAssignment objects.
    """
    if not players:
        return []

    n_tables = _num_tables(len(players))
    if n_tables == 1:
        return [TableAssignment(pid, 1) for pid, _ in players]

    sorted_players = sorted(players, key=lambda x: x[1], reverse=True)

    # Calculate how many players per table (distribute evenly)
    base_size = len(sorted_players) // n_tables
    remainder = len(sorted_players) % n_tables

    assignments: list[TableAssignment] = []
    idx = 0
    for table_num in range(1, n_tables + 1):
        size = base_size + (1 if table_num <= remainder else 0)
        for _ in range(size):
            assignments.append(TableAssignment(sorted_players[idx][0], table_num))
            idx += 1

    return assignments


def find_table_for_late_join(
    table_sizes: dict[int, int],
) -> int:
    """Find the best table for a late-joining player.

    Returns the table_number with the fewest players, as long as it
    has fewer than MAX_TABLE_SIZE. If all tables are full, returns -1
    to signal a new table is needed.

    Args:
        table_sizes: mapping of table_number → current player count
                     (only active tables).
    """
    if not table_sizes:
        return -1

    best_table = -1
    min_size = MAX_TABLE_SIZE + 1

    for table_num, size in sorted(table_sizes.items()):
        if size < MAX_TABLE_SIZE and size < min_size:
            min_size = size
            best_table = table_num

    return best_table
