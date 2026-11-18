"""Compare a rule-disagreement probe with the next integer under one extra reading."""

import argparse
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from disagreement_probe import Session

POLICIES = ("disagreement", "next")
KINDS = ("additive", "affine", "quadratic", "threshold", "outside_family", "unavailable")
CUBE = set(product((0, 1), repeat=3))


def audit_family():
    polynomials = [("polynomial", q, a, b)
                   for q in (-1, 0, 1) for a in (-2, -1, 0, 1, 2) for b in range(-3, 4)]
    thresholds = [("threshold", b, jump, cutoff)
                  for b in range(-3, 4) for jump in (-3, -1, 1, 3)
                  for cutoff in (-64, -16, -4, 0, 4, 16, 64)]
    return polynomials + thresholds


def output(rule, x):
    kind, first, second, third = rule
    if kind == "polynomial":
        return (first * x + second) * x + third
    return x + first + second * int(x >= third)


def consensus(rules, x):
    values = {output(rule, x) for rule in rules}
    return values.pop() if len(values) == 1 else None


def grade(predictions, rows):
    scores = Counter(correct=0, wrong=0, held=0)
    for value, row in zip(predictions, rows):
        status = "held" if value is None else "correct" if value == row["y"] else "wrong"
        scores[status] += 1
    return dict(scores)


def evaluate(world, policy):
    history, initial = world["history"], world["initial"]
    original = deepcopy(history + [initial])
    cell = tuple(initial["settings"])
    x0, y0 = initial["x"], initial["y"]
    if cell != tuple(world["setting"]):
        raise ValueError("The starting observation is at the wrong setting")
    if {tuple(row["settings"]) for row in history} != CUBE - {cell}:
        raise ValueError("The historical scope differs")
    reader = Session(world["verb"], world["keys"], history, initial, policy)
    candidates = [rule for rule in audit_family() if output(rule, x0) == y0]
    before = len(candidates)
    if len(reader.survivors) != before:
        raise ValueError("Initial candidate filtering differs from the audit")
    expected_x = None
    if before > 1:
        expected_x = x0 + 1
        if policy == "disagreement":
            menu = [x for x in range(-128, 129) if x != x0]
            expected_x = min(menu, key=lambda x: (
                max(Counter(output(rule, x) for rule in candidates).values()),
                abs(x - x0), x))
        if not -128 <= expected_x <= 128:
            expected_x = None
    request = reader.request()
    expected = None
    if expected_x is not None:
        expected = dict(verb=world["verb"], x=expected_x, settings=list(cell))
    if request != expected:
        raise ValueError("Request differs from the frozen policy or setting")
    observed = None
    partition = []
    if request is not None:
        partition = sorted(Counter(output(rule, expected_x) for rule in candidates).items())
        matches = [row for row in world["oracle"] if row["x"] == expected_x]
        if len(matches) != 1:
            raise ValueError("The instrument response is not uniquely bound")
        observed = matches[0]["y"]
        reader.reply(None if observed is None else dict(request, y=observed))
        if observed is not None:
            candidates = [rule for rule in candidates if output(rule, expected_x) == observed]
    if len(reader.survivors) != len(candidates):
        raise ValueError("Updated candidates differ from the independent family")
    # The reader sees only question inputs at this stage, never evaluator outcomes.
    predictions = [reader.predict(row["x"], row["settings"]) for row in world["tests"]]
    work = reader.counts
    expected_selection = before * 256 if policy == "disagreement" and expected_x is not None else 0
    if work["fit_evaluations"] != 301 or work["selection_evaluations"] != expected_selection:
        raise ValueError("Candidate selection work differs from the charge")
    if work["update_evaluations"] != (before if observed is not None else 0):
        raise ValueError("Candidate update work differs from the charge")
    if reader.request() is not None or reader.spent != int(request is not None):
        raise ValueError("The request opportunity was reused")
    if reader.receipts[:len(original)] != original or history + [initial] != original:
        raise ValueError("Old evidence was changed")
    for row in original:
        if reader.predict(row["x"], row["settings"]) != row["y"]:
            raise ValueError("An original observation failed to replay")
    if observed is not None and reader.predict(expected_x, cell) != observed:
        raise ValueError("A new observation failed to replay")
    for value, row in zip(predictions, world["tests"]):
        if tuple(row["settings"]) != cell:
            if value != row["y"]:
                raise ValueError("Behavior at an earlier setting changed")
        else:
            expected_value = observed if observed is not None and row["x"] == expected_x else consensus(candidates, row["x"])
            if value != expected_value:
                raise ValueError("Fresh prediction differs from independent consensus")
    return dict(
        id=world["id"], kind=world["kind"], policy=policy,
        initial=initial, request=request, observed=observed,
        before=before, after=len(candidates), status=reader.status,
        predictions=predictions, work=work,
        requests=int(request is not None), readings=int(observed is not None),
        changed_offset=int(observed is not None and observed - expected_x != y0 - x0),
        partitions=[list(pair) for pair in partition],
        preserved=7, replays=len(original),
    )


def summarize(bank):
    worlds = bank["worlds"]
    if Counter(world["kind"] for world in worlds) != Counter({kind: 8 for kind in KINDS}):
        raise ValueError("Unexpected case families")
    if len({world["id"] for world in worlds}) != 48:
        raise ValueError("Repeated world identity")
    groups = {policy: {} for policy in POLICIES}
    totals = {policy: Counter() for policy in POLICIES}
    details = []
    pairs = Counter()
    for world in worlds:
        tests = world["tests"]
        cell = tuple(world["setting"])
        if len(tests) != 11 or sum(tuple(row["settings"]) == cell for row in tests) != 4:
            raise ValueError("Unexpected question set")
        if any(row["x"] == world["initial"]["x"] for row in tests):
            raise ValueError("The fresh questions repeat the initial input")
        results = [evaluate(world, policy) for policy in POLICIES]
        queried = {result["request"]["x"] for result in results if result["request"] is not None}
        indices = [i for i, row in enumerate(tests) if tuple(row["settings"]) == cell and row["x"] not in queried]
        for result in results:
            fresh_scores = grade([result["predictions"][i] for i in indices], [tests[i] for i in indices])
            result["fresh_indices"] = indices
            result["fresh"] = fresh_scores
            excluded = [i for i, row in enumerate(tests) if tuple(row["settings"]) == cell and row["x"] in queried]
            result["excluded_indices"] = excluded
            counts = Counter({key: result[key] for key in
                              ("requests", "readings", "changed_offset", "preserved", "replays")})
            counts.update(fresh_scores)
            counts.update(result["work"])
            counts["worlds"] = 1
            counts["excluded_questions"] = len(excluded)
            counts["unique"] = int(result["after"] == 1)
            counts["unresolved"] = int(result["after"] > 1)
            counts["contradicted"] = int(result["after"] == 0)
            groups[result["policy"]].setdefault(world["kind"], Counter()).update(counts)
            totals[result["policy"]].update(counts)
        a, b = results
        for i in indices:
            actual = tests[i]["y"]
            a_right = a["predictions"][i] == actual
            b_right = b["predictions"][i] == actual
            pairs["disagreement_only_correct"] += int(a_right and not b_right)
            pairs["next_only_correct"] += int(b_right and not a_right)
        details.extend(results)
    return dict(by_kind=groups, totals=totals, paired_questions=pairs), details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="show each requested input and surviving rule counts")
    args = parser.parse_args()
    source = (HERE / "disagreement_cases.json").read_bytes().replace(b"\r\n", b"\n")
    archive = json.loads((HERE / "disagreement_results.json").read_bytes())
    if sha256(source).hexdigest() != archive["case_sha256"]:
        raise ValueError("The case bank differs from its freeze")
    summary, details = summarize(json.loads(source))
    if summary != archive["summary"] or details != archive["details"]:
        raise ValueError("Replay differs from the recorded decisions")
    result = summary
    if args.case:
        result = [row for row in details if row["id"] == args.case]
        if not result:
            parser.error("unknown case ID")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
