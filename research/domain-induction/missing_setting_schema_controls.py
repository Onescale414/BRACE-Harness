"""Run with python -I -S -B missing_setting_schema_controls.py."""

from collections import Counter
from itertools import product
from pathlib import Path
from random import Random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from missing_setting import Session


SEED = 461973
CELLS = tuple(product((0, 1), repeat=3))
OUTCOMES = ("exception", "confirms", "unavailable")


def run():
    rng = Random(SEED)
    totals = Counter()
    for gap in rng.sample(CELLS, len(CELLS)):
        verb, *keys = [f"q{n:04d}" for n in rng.sample(range(10000), 4)]
        axis = rng.randrange(3)
        offsets = rng.sample(range(-2, 3), 2)
        exception = rng.choice((-7, -5, 4, 8))
        known = {s: offsets[s[axis]] for s in CELLS if s != gap}
        starts = iter(rng.sample(range(-150, 151), 23))
        history = []
        for setting, delta in known.items():
            for _ in range(2):
                x = next(starts)
                history.append(dict(x=x, y=x + delta, settings=list(setting)))
        rng.shuffle(history)
        calibration = next(starts)
        fresh = {s: next(starts) for s in CELLS}

        # The three outcomes share everything the reader sees before it asks.
        for outcome in OUTCOMES:
            reader = Session(verb, keys, history)
            request = reader.request(x=calibration)
            assert request == dict(verb=verb, x=calibration, settings=list(gap))
            assert reader.spent == 1 and reader.request(x=calibration) is None
            assert reader.predict(fresh[gap], gap) is None
            totals["requests"] += 1

            delta = offsets[gap[axis]] if outcome == "confirms" else exception
            if outcome == "unavailable":
                status = reader.reply(None)
                assert status == "no_reading"
            else:
                status = reader.reply(dict(request, y=calibration + delta))
                assert status == ("accepted_base" if outcome == "confirms" else "local_override")
            totals[status] += 1
            assert reader.request(x=calibration) is None and reader.pending is None
            assert reader.spent == 1

            for row in history:
                assert reader.predict(row["x"], row["settings"]) == row["y"]
                totals["replayed"] += 1
            for setting, x in fresh.items():
                prediction = reader.predict(x, setting)
                if setting == gap and outcome == "unavailable":
                    assert prediction is None
                    totals["held"] += 1
                else:
                    assert prediction == x + known.get(setting, delta)
                    totals["correct"] += 1

    expected = dict(requests=24, local_override=8, accepted_base=8, no_reading=8,
                    replayed=336, correct=184, held=8)
    assert totals == expected, totals
    print(f"PASS seed={SEED}", *(f"{key}={totals[key]}" for key in expected))


if __name__ == "__main__":
    run()
