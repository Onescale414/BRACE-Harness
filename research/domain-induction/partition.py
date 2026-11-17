"""Find the smallest sufficient coordinate subset for one domain and one verb."""

from itertools import combinations, product
from typing import NamedTuple


class Partition(NamedTuple):
    keys: tuple
    table: dict  # Projected binary cell -> observed delta.
    blocks: dict  # Delta -> sorted original cells with that delta.


def _schema(keys, max_size):
    keys = tuple(keys)
    if len(set(keys)) != len(keys) or max_size not in (0, 1, 2):
        raise ValueError("Use distinct feature keys and a maximum size of 0, 1 or 2")
    return keys


def _observed_cells(keys, observations):
    cells = {}
    for row in observations:
        cell = tuple(row["features"][key] for key in keys)
        delta = row["y"] - row["x"]
        if any(bit not in (0, 1) for bit in cell):
            return {}
        if cell in cells and cells[cell] != delta:
            return {}
        cells[cell] = delta
    return cells


def _smallest_tables(keys, cells, max_size):
    for size in range(min(max_size, len(keys)) + 1):
        choices = []
        for indexes in combinations(range(len(keys)), size):
            table = {}
            for cell, delta in cells.items():
                projected = tuple(cell[i] for i in indexes)
                if projected in table and table[projected] != delta:
                    break
                table[projected] = delta
            else:
                if len(table) == 2 ** size:
                    choices.append((tuple(keys[i] for i in indexes), table))
        if choices:
            return choices
    return []


def minimal_projections(keys, observations, max_size=2):
    """Return all smallest covered, consistent feature subsets in schema order."""
    keys = _schema(keys, max_size)
    cells = _observed_cells(keys, observations)
    return tuple(subset for subset, _ in _smallest_tables(keys, cells, max_size))


def learn(keys, observations, max_size=2):
    """Return a unique complete-cube Partition, or None without full evidence."""
    keys = _schema(keys, max_size)
    cells = _observed_cells(keys, observations)
    if len(cells) != 2 ** len(keys):
        return None
    choices = _smallest_tables(keys, cells, max_size)
    if len(choices) != 1:
        return None
    subset, table = choices[0]
    groups = {}
    for cell in sorted(cells):
        groups.setdefault(cells[cell], []).append(cell)
    return Partition(subset, table, {value: tuple(group) for value, group in groups.items()})


def verify(keys, observations, result, max_size=2):
    """Check a reported partition using full-cube single-coordinate contrasts."""
    keys = _schema(keys, max_size)
    if not isinstance(result, Partition):
        return False
    evidence = {}
    for row in observations:
        cell = tuple(row["features"][key] for key in keys)
        evidence.setdefault(cell, set()).add(row["y"] - row["x"])
    cube = tuple(product((0, 1), repeat=len(keys)))
    if set(evidence) != set(cube) or any(len(values) != 1 for values in evidence.values()):
        return False

    # On a full cube, each coordinate with an unequal opposite-edge pair
    # is necessary. Any two cells agreeing on these coordinates are connected
    # by flips of the remaining coordinates, each of which preserves the delta.
    essential = []
    for i in range(len(keys)):
        if any(evidence[cell] != evidence[cell[:i] + (1,) + cell[i + 1:]]
               for cell in cube if cell[i] == 0):
            essential.append(i)
    if len(essential) > max_size or tuple(keys[i] for i in essential) != result.keys:
        return False
    expected_table = {}
    expected_groups = {}
    for cell in cube:
        delta, = evidence[cell]
        expected_table[tuple(cell[i] for i in essential)] = delta
        expected_groups.setdefault(delta, []).append(cell)
    return (result.table == expected_table
            and result.blocks == {delta: tuple(group) for delta, group in expected_groups.items()})
