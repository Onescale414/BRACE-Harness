"""Reconstruct and independently validate the frozen two-input instrument cases."""

from collections import Counter
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from random import Random


SEED = 716283905
KINDS = ("additive", "affine", "quadratic", "threshold", "local_exception", "unavailable")
STARTS = (-80, -7, -2, 0, 1, 3, 17, 80)
CELLS = tuple(product((0, 1), repeat=3))
INPUTS = tuple(range(-128, 129))


def effect(rng, kind):
    """Sample a world definition without consulting a probe or starting input."""
    if kind == "unavailable":
        kind = rng.choice(("additive", "affine"))
    if kind == "additive":
        delta = rng.choice((-9, -7, -4, -1, 2, 5, 8))
        return lambda x: x + delta, None
    if kind == "affine":
        slope = rng.choice((-3, -2, -1, 0, 2, 3, 4))
        intercept = rng.randint(-11, 11)
        return lambda x: slope * x + intercept, None
    if kind == "quadratic":
        square = rng.choice((-2, -1, 1, 2))
        linear = rng.randint(-3, 3)
        intercept = rng.randint(-11, 11)
        return lambda x: square * x * x + linear * x + intercept, None
    if kind == "threshold":
        threshold = rng.choice((-64, -32, -8, -1, 2, 8, 24, 64))
        delta = rng.randint(-9, 9)
        change = rng.choice((-11, -7, -4, 3, 6, 10))
        return lambda x: x + delta + (change if x >= threshold else 0), None
    center = rng.choice((-64, -16, -4, 0, 5, 12, 48, 96))
    radius = rng.choice((1, 2))
    delta = rng.randint(-9, 9)
    change = rng.choice((-13, -8, -5, 4, 7, 12))
    interval = set(range(center - radius, center + radius + 1))
    return lambda x: x + delta + (change if x in interval else 0), interval


def build():
    rng = Random(SEED)
    worlds, definitions = [], {}
    for kind in KINDS:
        starts = rng.sample(STARTS, len(STARTS))
        for x0 in starts:
            target_function, exceptional_inputs = effect(rng, kind)
            world_id = f"{rng.getrandbits(48):012x}"
            names = [f"v{n:05d}" for n in rng.sample(range(100000), 4)]
            target = rng.choice(CELLS)
            old_effects = {s: rng.randint(-9, 9) for s in CELLS if s != target}
            probe_inputs = {2 * x0, x0 + 1}
            unavailable_inputs = {x0} | probe_inputs

            # Reserve a fresh in-exception evaluation point before drawing the
            # histories. The exception itself was chosen independently above.
            reserved = None
            if exceptional_inputs:
                options = sorted(exceptional_inputs - unavailable_inputs)
                if not options:
                    raise ValueError("no fresh point in the sampled exception")
                reserved = rng.choice(options)
                unavailable_inputs.add(reserved)
            history_inputs = rng.sample([x for x in INPUTS if x not in unavailable_inputs], 14)
            history = []
            for index, (setting, delta) in enumerate(old_effects.items()):
                for x in history_inputs[index * 2:index * 2 + 2]:
                    history.append(dict(x=x, y=x + delta, settings=list(setting)))
            rng.shuffle(history)

            taken = set(history_inputs) | {x0} | probe_inputs
            fresh = []
            if reserved is not None:
                fresh.append(reserved)
                taken.add(reserved)
            bands = [(-120, -40), (-35, -3), (4, 40), (50, 120)]
            rng.shuffle(bands)
            for lower, upper in bands:
                if len(fresh) == 4:
                    break
                choices = [x for x in range(lower, upper + 1) if x not in taken]
                x = rng.choice(choices)
                fresh.append(x)
                taken.add(x)
            tests = [dict(x=x, y=target_function(x), settings=list(target)) for x in fresh]
            for setting, delta in old_effects.items():
                x = rng.choice([value for value in INPUTS if value not in taken])
                taken.add(x)
                tests.append(dict(x=x, y=x + delta, settings=list(setting)))
            rng.shuffle(tests)
            oracle = [dict(x=x, y=None if kind == "unavailable" else target_function(x))
                      for x in sorted(probe_inputs) if x in INPUTS]
            world = dict(id=world_id, kind=kind, verb=names[0], keys=names[1:],
                         setting=list(target), history=history,
                         initial=dict(x=x0, y=target_function(x0), settings=list(target)),
                         oracle=oracle, tests=tests)
            worlds.append(world)
            definitions[world_id] = (target_function, old_effects, exceptional_inputs)
    rng.shuffle(worlds)
    return dict(seed=SEED, worlds=worlds), definitions


def validate(bank, definitions):
    worlds = bank["worlds"]
    assert len(worlds) == len({w["id"] for w in worlds}) == 48
    assert Counter(w["kind"] for w in worlds) == {kind: 8 for kind in KINDS}
    for kind in KINDS:
        assert sorted(w["initial"]["x"] for w in worlds if w["kind"] == kind) == sorted(STARTS)
    for world in worlds:
        function, old_effects, exceptional_inputs = definitions[world["id"]]
        target = tuple(world["setting"])
        initial, history, oracle, tests = (world[k] for k in ("initial", "history", "oracle", "tests"))
        x0 = initial["x"]
        assert len(world["keys"]) == len(set(world["keys"])) == 3
        assert initial["settings"] == world["setting"] and initial["y"] == function(x0)
        assert len(history) == 14 and len(tests) == 11
        assert Counter(tuple(r["settings"]) for r in history) == {s: 2 for s in old_effects}
        assert len({r["x"] for r in history}) == 14
        assert len({r["x"] for r in tests}) == 11
        expected_probes = {x for x in (2 * x0, x0 + 1) if -128 <= x <= 128}
        assert len(oracle) == len(expected_probes) and {r["x"] for r in oracle} == expected_probes
        for row in oracle:
            assert row["y"] == (None if world["kind"] == "unavailable" else function(row["x"]))
        for row in history:
            assert row["y"] == row["x"] + old_effects[tuple(row["settings"])]
        assert not ({r["x"] for r in tests} & ({r["x"] for r in history} | {x0, 2 * x0, x0 + 1}))
        target_tests = [r for r in tests if tuple(r["settings"]) == target]
        assert len(target_tests) == 4
        for row in tests:
            setting = tuple(row["settings"])
            expected = function(row["x"]) if setting == target else row["x"] + old_effects[setting]
            assert row["y"] == expected
        if exceptional_inputs:
            assert any(r["x"] in exceptional_inputs for r in target_tests)
            assert any(r["x"] not in exceptional_inputs for r in target_tests)
        for row in history + [initial] + tests + oracle:
            assert type(row["x"]) is int and -128 <= row["x"] <= 128
            assert row["y"] is None or type(row["y"]) is int and abs(row["y"]) <= 1_000_000


if __name__ == "__main__":
    bank, definitions = build()
    validate(bank, definitions)
    data = (json.dumps(bank, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    destination = Path(__file__).with_name("scale_probe_cases.json")
    if destination.read_bytes() != data:
        raise ValueError("reconstruction differs from the frozen case bank")
    print("worlds=48 history=672 initial=48 fresh=528")
    print("SHA256", sha256(data).hexdigest())
