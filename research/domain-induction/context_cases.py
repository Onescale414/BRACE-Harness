"""Deterministic synthetic instruments. Only the test driver can see their outcomes."""
from itertools import product
from random import Random


def worlds(seed=742091):
    rng = Random(seed)
    patterns = list(product((0, 1), repeat=3))
    kinds = ["constant"] * 4 + ["single"] * 8 + ["interaction"] * 2 + ["hidden"] * 2
    rng.shuffle(kinds)
    single_count = interaction_count = 0
    result = []
    for n, kind in enumerate(kinds):
        keys = ["tev", "mip", "lusk"]
        rng.shuffle(keys)
        relevant = single_count % 3 if kind == "single" else rng.randrange(3)
        if kind == "single":
            single_count += 1
        other = (relevant + 1) % 3
        left, right = rng.sample(range(-2, 3), 2)
        operation = interaction_count % 2
        if kind == "interaction":
            interaction_count += 1

        def batch(base):
            order = patterns.copy()
            rng.shuffle(order)
            rows = []
            for i, bits in enumerate(order):
                if kind == "constant":
                    branch = 0
                elif kind == "interaction":
                    branch = (bits[relevant] ^ bits[other] if operation == 0
                              else bits[relevant] & bits[other])
                else:
                    branch = bits[relevant]
                x = base + i
                rows.append(dict(verb="kel", features=dict(zip(keys, bits)), x=x,
                                 y=x + (right if branch else left)))
            return rows

        menu, validation, tests = batch(-15), batch(10), batch(50)
        duplicate = dict(validation[0])
        if kind == "hidden":
            # An unobserved binary switch changes this outcome under identical visible inputs.
            duplicate["y"] = duplicate["x"] + (right if duplicate["y"] - duplicate["x"] == left else left)
        validation.append(duplicate)
        result.append(dict(id=f"w{n+1:02}", kind=kind, keys=keys,
                           causal_key=keys[relevant] if kind == "single" else None,
                           menu=menu, validation=validation, tests=tests))
    return result
