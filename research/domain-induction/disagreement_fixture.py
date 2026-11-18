"""Reconstruct frozen worlds for selecting a measurement from a bounded rule family."""

from collections import Counter
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from random import Random


SEED = 483197206
KINDS = ("additive", "affine", "quadratic", "threshold", "outside_family", "unavailable")
STARTS = (-6, -3, -1, 0, 1, 2, 3, 6)
CELLS = tuple(product((0, 1), repeat=3))
INPUTS = tuple(range(-128, 129))
THRESHOLDS = (-64, -16, -4, 0, 4, 16, 64)


def evaluate(truth, x):
    kind = truth["kind"]
    if kind == "polynomial":
        return truth["q"] * x * x + truth["a"] * x + truth["b"]
    if kind == "threshold":
        return x + truth["b"] + (truth["j"] if x >= truth["t"] else 0)
    if kind == "cubic_floor":
        return x ** 3 // truth["divisor"] + truth["b"]
    if kind == "local_exception":
        return x + truth["b"] + (truth["change"] if truth["lo"] <= x <= truth["hi"] else 0)
    raise ValueError("unknown instrument definition")


def definition(rng, kind, index, threshold):
    """Choose effects before any measurement-selection policy is consulted."""
    b = rng.randint(-3, 3)
    if kind == "unavailable":
        kind = "affine" if index < 4 else "threshold"
    if kind == "additive":
        return dict(kind="polynomial", q=0, a=1, b=b)
    if kind == "affine":
        return dict(kind="polynomial", q=0, a=rng.choice((-2, -1, 0, 2)), b=b)
    if kind == "quadratic":
        return dict(kind="polynomial", q=rng.choice((-1, 1)), a=rng.randint(-2, 2), b=b)
    if kind == "threshold":
        return dict(kind="threshold", b=b, j=rng.choice((-3, -1, 1, 3)), t=threshold)
    if index < 4:
        return dict(kind="cubic_floor", divisor=4, b=b)
    center = rng.choice(THRESHOLDS)
    radius = rng.choice((1, 2))
    return dict(kind="local_exception", b=b, change=rng.choice((-7, -5, 5, 7)),
                lo=center - radius, hi=center + radius)


def fresh_target_inputs(rng, truth, x0):
    available = [x for x in INPUTS if x != x0]
    if truth["kind"] == "threshold":
        below = [x for x in available if x < truth["t"]]
        above = [x for x in available if x >= truth["t"]]
        chosen = rng.sample(below, 2) + rng.sample(above, 2)
    elif truth["kind"] == "local_exception":
        inside = [x for x in available if truth["lo"] <= x <= truth["hi"]]
        outside = [x for x in available if x < truth["lo"] or x > truth["hi"]]
        chosen = [rng.choice(inside)] + rng.sample(outside, 3)
    else:
        chosen = []
        for lower, upper in ((-128, -65), (-64, -1), (0, 63), (64, 128)):
            chosen.append(rng.choice([x for x in available if lower <= x <= upper]))
    rng.shuffle(chosen)
    return chosen


def build():
    rng = Random(SEED)
    worlds = []
    for kind in KINDS:
        starts = rng.sample(STARTS, len(STARTS))
        thresholds = list(THRESHOLDS) + [rng.choice(THRESHOLDS)]
        rng.shuffle(thresholds)
        for index, x0 in enumerate(starts):
            truth = definition(rng, kind, index, thresholds[index])
            world_id = f"{rng.getrandbits(48):012x}"
            verb, *keys = [f"c{n:05d}" for n in rng.sample(range(100000), 4)]
            target = rng.choice(CELLS)
            old_effects = {s: rng.randint(-9, 9) for s in CELLS if s != target}
            target_inputs = fresh_target_inputs(rng, truth, x0)
            history_inputs = rng.sample([x for x in INPUTS if x not in {x0, *target_inputs}], 14)
            history = []
            for position, (setting, delta) in enumerate(old_effects.items()):
                for x in history_inputs[2 * position:2 * position + 2]:
                    history.append(dict(x=x, y=x + delta, settings=list(setting)))
            rng.shuffle(history)
            tests = [dict(x=x, y=evaluate(truth, x), settings=list(target)) for x in target_inputs]
            taken = {x0, *target_inputs, *history_inputs}
            for setting, delta in old_effects.items():
                x = rng.choice([value for value in INPUTS if value not in taken])
                taken.add(x)
                tests.append(dict(x=x, y=x + delta, settings=list(setting)))
            rng.shuffle(tests)
            oracle = [dict(x=x, y=None if kind == "unavailable" else evaluate(truth, x)) for x in INPUTS]
            worlds.append(dict(id=world_id, kind=kind, verb=verb, keys=keys, setting=list(target),
                               history=history, initial=dict(x=x0, y=evaluate(truth, x0), settings=list(target)),
                               oracle=oracle, tests=tests, truth=truth))
    rng.shuffle(worlds)
    return dict(seed=SEED, worlds=worlds)


def declared_family():
    polynomials = [dict(kind="polynomial", q=q, a=a, b=b)
                   for q, a, b in product((-1, 0, 1), (-2, -1, 0, 1, 2), range(-3, 4))]
    thresholds = [dict(kind="threshold", b=b, j=j, t=t)
                  for b, j, t in product(range(-3, 4), (-3, -1, 1, 3), THRESHOLDS)]
    return polynomials + thresholds


def validate(bank):
    worlds = bank["worlds"]
    assert len(worlds) == len({w["id"] for w in worlds}) == 48
    assert Counter(w["kind"] for w in worlds) == {kind: 8 for kind in KINDS}
    assert Counter(w["truth"]["kind"] for w in worlds if w["kind"] == "outside_family") == {
        "cubic_floor": 4, "local_exception": 4}
    family = declared_family()
    assert len(family) == 301
    signatures = {tuple(evaluate(rule, x) for x in INPUTS) for rule in family}
    for kind in KINDS:
        assert sorted(w["initial"]["x"] for w in worlds if w["kind"] == kind) == sorted(STARTS)
    for world in worlds:
        initial, history, oracle, tests = (world[k] for k in ("initial", "history", "oracle", "tests"))
        target, truth = tuple(world["setting"]), world["truth"]
        assert len(world["keys"]) == len(set(world["keys"])) == 3
        assert initial["settings"] == world["setting"] and initial["y"] == evaluate(truth, initial["x"])
        assert len(history) == 14 and len(tests) == 11 and len(oracle) == 257
        assert len({r["x"] for r in history}) == 14 and len({r["x"] for r in tests}) == 11
        assert [r["x"] for r in oracle] == list(INPUTS)
        cells = Counter(tuple(r["settings"]) for r in history)
        assert cells == {s: 2 for s in CELLS if s != target}
        old_effects = {}
        for row in history:
            setting = tuple(row["settings"])
            delta = row["y"] - row["x"]
            assert old_effects.setdefault(setting, delta) == delta
        assert not ({r["x"] for r in tests} & ({r["x"] for r in history} | {initial["x"]}))
        target_tests = [r for r in tests if tuple(r["settings"]) == target]
        assert len(target_tests) == 4
        for row in tests:
            setting = tuple(row["settings"])
            assert row["y"] == (evaluate(truth, row["x"]) if setting == target else row["x"] + old_effects[setting])
        if truth["kind"] == "threshold":
            assert sum(r["x"] < truth["t"] for r in target_tests) == 2
        if truth["kind"] == "local_exception":
            assert sum(truth["lo"] <= r["x"] <= truth["hi"] for r in target_tests) == 1
        for row in oracle:
            assert row["y"] == (None if world["kind"] == "unavailable" else evaluate(truth, row["x"]))
        signature = tuple(evaluate(truth, x) for x in INPUTS)
        assert (signature in signatures) == (world["kind"] != "outside_family")
        for row in history + [initial] + tests + oracle:
            assert type(row["x"]) is int and -128 <= row["x"] <= 128
            assert row["y"] is None or type(row["y"]) is int and abs(row["y"]) <= 1_000_000


if __name__ == "__main__":
    bank = build()
    validate(bank)
    data = (json.dumps(bank, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    destination = Path(__file__).with_name("disagreement_cases.json")
    if destination.read_bytes() != data:
        raise ValueError("reconstruction differs from the frozen case bank")
    print("worlds=48 history=672 initial=48 oracle=12336 fresh=528")
    print("SHA256", sha256(data).hexdigest())
