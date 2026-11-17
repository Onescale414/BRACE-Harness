"""Exact, outcome-blind probe design for single-feature binary rules."""

from itertools import combinations
from math import comb


_cache = {}


def _menu_patterns(keys, menu):
    patterns = set()
    for row in menu:
        if "y" in row:
            raise ValueError("probe design requires visible rows without y")
        pattern = tuple(row["features"][key] for key in keys)
        if any(type(bit) not in (int, bool) or bit not in (0, 1) for bit in pattern):
            raise ValueError("each visible coordinate must be binary")
        patterns.add(tuple(map(int, pattern)))
    return tuple(sorted(patterns))


def _search(patterns, rules):
    # Pay once for each candidate delta on each distinct offered pattern.
    predictions = []
    cost = 0
    for key, zero, one in rules:
        row = []
        for pattern in patterns:
            row.append(zero if key == -1 or pattern[key] == 0 else one)
            cost += 1
        predictions.append(row)

    # Each rejected subset has a witness: two rules predicting the same vector.
    attempts = []
    collisions = []
    selected = None
    distinct = 0
    for size in range(len(patterns) + 1):
        tried = 0
        for subset in combinations(range(len(patterns)), size):
            tried += 1
            signatures = {}
            for index, row in enumerate(predictions):
                signature = tuple(row[column] for column in subset)
                if signature in signatures:
                    collisions.append((subset, signatures[signature], index))
                    break
                signatures[signature] = index
            else:
                selected = tuple(patterns[column] for column in subset)
                distinct = len(signatures)
                break
        attempts.append(tried)
        if selected is not None:
            break

    # Count required smaller subsets independently of the enumeration above.
    cutoff = len(patterns) + 1 if selected is None else len(selected)
    smaller_expected = sum(comb(len(patterns), size) for size in range(cutoff))
    smaller_witnessed = sum(len(subset) < cutoff for subset, _, _ in collisions)
    if selected is None:
        distinct = len({tuple(row) for row in predictions})
    certificate = {
        "rule_count": len(rules),
        "distinct_signatures": distinct,
        "attempts_by_size": tuple(attempts),
        "smaller_subsets_expected": smaller_expected,
        "smaller_subsets_witnessed": smaller_witnessed,
        "minimal": selected is not None and smaller_expected == smaller_witnessed,
        "collisions": tuple(collisions),
    }
    return selected, sum(attempts), cost, certificate


def design_probes(keys, candidates, menu):
    """Find the shortest identifying pattern sequence in the visible menu.

    Patterns use the supplied coordinate order. Certificate witnesses refer to
    lexicographically sorted patterns and rules (coordinate index, zero, one),
    where a constant rule uses index -1. An infeasible menu returns patterns=None.
    Work counters charge only computations actually performed on this call.
    """
    keys = tuple(keys)
    if len(keys) != 3 or len(set(keys)) != 3 or None in keys:
        raise ValueError("three distinct feature keys are required")
    positions = {key: i for i, key in enumerate(keys)}
    rules = tuple(sorted(
        (-1 if key is None else positions[key], zero, one)
        for key, zero, one in candidates
    ))
    patterns = _menu_patterns(keys, menu)
    cache_key = (patterns, rules)
    hit = cache_key in _cache
    if not hit:
        _cache[cache_key] = _search(patterns, rules)
    selected, attempts, cost, certificate = _cache[cache_key]
    return {
        "patterns": selected,
        "subset_attempts": 0 if hit else attempts,
        "predicted_deltas": 0 if hit else cost,
        "cache_hit": hit,
        "certificate": dict(certificate),
    }
