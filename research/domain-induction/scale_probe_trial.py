"""Replay doubling versus the next integer with one additional observation."""

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scale_probe import OUTPUT_LIMIT, ScaleSession

POLICIES = ("double", "next")
KINDS = ("additive", "affine", "quadratic", "threshold", "local_exception", "unavailable")
CUBE = set(product((0, 1), repeat=3))


def encoded(value):
    if value is None:
        return None
    value = Fraction(value)
    return [value.numerator, value.denominator]


def score(predictions, tests):
    counts = Counter(correct=0, wrong=0, held=0)
    for prediction, row in zip(predictions, tests):
        outcome = "held" if prediction is None else "correct" if prediction == row["y"] else "wrong"
        counts[outcome] += 1
    return dict(counts)


def evaluate(world, policy):
    history, initial = world["history"], world["initial"]
    original = deepcopy(history + [initial])
    cell = tuple(initial["settings"])
    if cell != tuple(world["setting"]):
        raise ValueError("Initial reading differs from the selected setting")
    if {tuple(row["settings"]) for row in history} != CUBE - {cell}:
        raise ValueError("The historical settings differ from the declared scope")
    x0, y0 = initial["x"], initial["y"]
    possible_probes = {2 * x0, x0 + 1}
    old_inputs = {row["x"] for row in original}
    tests = world["tests"]
    if any(row["x"] in possible_probes | old_inputs for row in tests):
        raise ValueError("Fresh questions reuse a teaching or instrument input")
    if len(tests) != 11 or sum(tuple(row["settings"]) == cell for row in tests) != 4:
        raise ValueError("Unexpected evaluation questions")
    reader = ScaleSession(world["verb"], world["keys"], history, initial, policy)
    before = [reader.predict(row["x"], row["settings"]) for row in tests]
    request = reader.request()
    proposed_x = 2 * x0 if policy == "double" else x0 + 1
    eligible = proposed_x != x0 and -128 <= proposed_x <= 128
    if (request is not None) != eligible:
        raise ValueError("Probe admission differs from the frozen rule")
    observation = None
    if request is not None:
        expected = dict(verb=world["verb"], x=proposed_x, settings=list(cell))
        if request != expected:
            raise ValueError("The reading was requested at the wrong input or setting")
        matches = [row for row in world["oracle"] if row["x"] == proposed_x]
        if len(matches) != 1:
            raise ValueError("The instrument has no unique response")
        observation = matches[0]["y"]
        reader.reply(None if observation is None else dict(request, y=observation))

    # Save every prediction before evaluation reads the corresponding answer.
    predictions = [reader.predict(row["x"], row["settings"]) for row in tests]
    status = reader.status
    if reader.request() is not None or reader.spent != int(eligible):
        raise ValueError("The one-request allowance was violated")
    if reader.receipts[:len(original)] != original:
        raise ValueError("A prior observation was changed")
    if history + [initial] != original:
        raise ValueError("Caller evidence was mutated")
    for row in original:
        if reader.predict(row["x"], row["settings"]) != row["y"]:
            raise ValueError("An original reading failed to replay")
    preserved = 0
    for index, row in enumerate(tests):
        if tuple(row["settings"]) != cell:
            if predictions[index] != before[index] or predictions[index] != row["y"]:
                raise ValueError("Previously verified behavior changed")
            preserved += 1
    fit = observation is not None
    slope = intercept = None
    if fit:
        slope = Fraction(observation - y0, proposed_x - x0)
        intercept = y0 - slope * x0
        if reader.coefficients != (slope, intercept) or status != "fitted":
            raise ValueError("Fit receipt disagrees with its two observations")
        if reader.predict(proposed_x, cell) != observation:
            raise ValueError("The new measurement cannot be replayed")
    target_predictions, target_tests = [], []
    regions = defaultdict(lambda: Counter(correct=0, wrong=0, held=0))
    for prediction, row in zip(predictions, tests):
        if tuple(row["settings"]) != cell:
            continue
        expected_prediction = None
        if fit:
            expected_prediction = Fraction(
                y0 * (proposed_x - row["x"]) + observation * (row["x"] - x0),
                proposed_x - x0,
            )
            if abs(expected_prediction) > OUTPUT_LIMIT:
                expected_prediction = None
        if prediction != expected_prediction:
            raise ValueError("Prediction differs from independent interpolation")
        target_predictions.append(prediction)
        target_tests.append(row)
        region = "unfitted"
        if fit:
            region = "inside_span" if min(x0, proposed_x) < row["x"] < max(x0, proposed_x) else "outside_span"
        regions[region].update(score([prediction], [row]))
    return dict(
        id=world["id"], kind=world["kind"], policy=policy, initial=initial,
        proposed_x=proposed_x, request=request, observed=observation, status=status,
        requests=int(eligible), readings=int(fit), fits=int(fit),
        offset_changed=int(fit and observation - proposed_x != y0 - x0),
        preserved=preserved, replays=len(original),
        slope=encoded(slope), intercept=encoded(intercept),
        predictions=[encoded(value) for value in predictions],
        target=score(target_predictions, target_tests),
        all_endpoints=score(predictions, tests), regions=dict(regions),
    )


def summarize(bank):
    worlds = bank["worlds"]
    if Counter(w["kind"] for w in worlds) != Counter({kind: 8 for kind in KINDS}):
        raise ValueError("Unexpected family counts")
    if len({w["id"] for w in worlds}) != 48:
        raise ValueError("Repeated world identifier")
    groups = {policy: {} for policy in POLICIES}
    totals = {policy: Counter() for policy in POLICIES}
    paired = {policy: Counter(correct=0, wrong=0, held=0) for policy in POLICIES}
    paired_worlds = 0
    details = []
    for world in worlds:
        results = [evaluate(world, policy) for policy in POLICIES]
        details.extend(results)
        for result in results:
            counts = Counter({key: result[key] for key in
                              ("requests", "readings", "fits", "offset_changed", "preserved", "replays")})
            counts["worlds"] = 1
            counts[result["status"]] += 1
            counts.update(result["target"])
            groups[result["policy"]].setdefault(result["kind"], Counter()).update(counts)
            totals[result["policy"]].update(counts)
        if all(result["fits"] for result in results):
            paired_worlds += 1
            for result in results:
                paired[result["policy"]].update(result["target"])
    return dict(by_kind=groups, totals=totals,
                both_readings_available=dict(worlds=paired_worlds, target=paired)), details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="show both measurements and predictions for one world")
    args = parser.parse_args()
    source = (HERE / "scale_probe_cases.json").read_bytes().replace(b"\r\n", b"\n")
    archive = json.loads((HERE / "scale_probe_results.json").read_bytes())
    if sha256(source).hexdigest() != archive["case_sha256"]:
        raise ValueError("The case bank differs from the archived fixture")
    summary, details = summarize(json.loads(source))
    if summary != archive["summary"] or details != archive["details"]:
        raise ValueError("Replay differs from the archived decisions")
    result = summary
    if args.case:
        result = [row for row in details if row["id"] == args.case]
        if not result:
            parser.error("unknown case ID")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
