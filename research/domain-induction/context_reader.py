"""Induce action effects. Keep a separate candidate tuple per domain and verb."""

from collections import Counter
from itertools import permutations
from typing import NamedTuple


DELTAS = range(-2, 3)


class Rule(NamedTuple):
    key: str | None
    zero: int
    one: int

    def delta(self, probe):
        if self.key is None:
            return self.zero
        return (self.zero, self.one)[probe["features"][self.key]]


def rules(keys, conditional=True):
    """Enumerate distinct functions on the supplied binary coordinates."""
    candidates = [Rule(None, delta, delta) for delta in DELTAS]
    if conditional:
        for key in dict.fromkeys(keys):
            candidates.extend(Rule(key, a, b) for a, b in permutations(DELTAS, 2))
    return tuple(candidates)


def update(candidates, row):
    delta = row["y"] - row["x"]
    return tuple(rule for rule in candidates if rule.delta(row) == delta)


def choose(candidates, menu):
    """Index in an unused, single-verb menu. Ties retain the menu order."""
    def worst_case(index):
        buckets = Counter(rule.delta(menu[index]) for rule in candidates)
        return max(buckets.values(), default=0)

    return min(range(len(menu)), key=worst_case)


def predict_consensus(candidates, probe):
    """Return the agreed delta, or None for disagreement or an empty set."""
    predictions = {rule.delta(probe) for rule in candidates}
    return predictions.pop() if len(predictions) == 1 else None


def feature_used(candidates):
    """Return the feature key if all surviving rules require the same one."""
    keys = {rule.key for rule in candidates}
    return keys.pop() if len(keys) == 1 else None


def certify(keys, observations, conditional=True):
    """Refit from one verb's observations and return the unique rule, if any."""
    rows = tuple(observations)
    deltas = [row["y"] - row["x"] for row in rows]
    effects = set(deltas)
    if not effects or not effects.issubset(DELTAS):
        return None

    if len(effects) == 1:
        # An unobserved binary level could still carry a different effect.
        if conditional and any({row["features"][key] for row in rows} != {0, 1}
                               for key in keys):
            return None
        return Rule(None, deltas[0], deltas[0])

    if not conditional:
        return None
    fitted = []
    for key in dict.fromkeys(keys):
        by_level = (set(), set())
        for row, delta in zip(rows, deltas):
            by_level[row["features"][key]].add(delta)
        # With variable observed effects, a viable coordinate must have
        # observations at both levels and exactly one effect at each level.
        zero, one = by_level
        if len(zero) == len(one) == 1:
            fitted.append(Rule(key, next(iter(zero)), next(iter(one))))
    return fitted[0] if len(fitted) == 1 else None
