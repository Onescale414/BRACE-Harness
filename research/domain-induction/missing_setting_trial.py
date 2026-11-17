"""Replay a one-reading request for a previously unmeasured control setting."""
import argparse
from collections import Counter, defaultdict
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from missing_setting import Session

CUBE = tuple(product((0, 1), repeat=3))


def offsets(receipts):
    evidence = defaultdict(set)
    for row in receipts:
        evidence[tuple(row["settings"])].add(row["y"] - row["x"])
    return evidence


def local(evidence, x, cell):
    values = evidence.get(tuple(cell), ())
    return x + next(iter(values)) if len(values) == 1 else None


def global_predictions(evidence):
    """All fully determined constant or single-control effects consistent with receipts."""
    tables = set()
    for axis in range(3):
        by_bit = [set(), set()]
        for cell, deltas in evidence.items():
            by_bit[cell[axis]].update(deltas)
        if all(len(values) == 1 for values in by_bit):
            pair = [next(iter(values)) for values in by_bit]
            tables.add(tuple(pair[cell[axis]] for cell in CUBE))
    return dict(zip(CUBE, next(iter(tables)))) if len(tables) == 1 else {}


def grade(predictions, actual):
    return dict(correct=sum(v == y for v, y in zip(predictions, actual) if v is not None),
                wrong=sum(v != y for v, y in zip(predictions, actual) if v is not None),
                held=sum(v is None for v in predictions))


def run_case(world):
    history = world["history"]
    original = offsets(history)
    session = Session(world["verb"], world["keys"], history)
    x = world["probe_x"]
    seen_inputs = {row["x"] for row in history}
    fresh_inputs = {row["x"] for row in world["tests"]}
    if x in seen_inputs or x in fresh_inputs or seen_inputs & fresh_inputs:
        raise ValueError("Teaching, instrument and evaluation inputs must be disjoint")
    before = {cell: session.predict(x, cell) for cell in CUBE}
    old_law = global_predictions(original)
    request = session.request(list(CUBE), x=x)
    missing = [cell for cell in CUBE if cell not in original]
    if bool(request) != bool(missing):
        raise ValueError("Request did not match presence of a gap")

    observed = expected = directly_measured = None
    cell = None
    receipt = None
    question = None
    status = "already_covered"
    if request is not None:
        cell = tuple(request["settings"])
        if cell != missing[0] or request["verb"] != world["verb"] or request["x"] != x:
            raise ValueError("Misbound request or tie-break")
        names = ", ".join(f"{k}={bit}" for k, bit in zip(world["keys"], cell))
        question = f"What output does {request['verb']} produce at {x} with {names}?"
        expected = x + old_law[cell] if cell in old_law else None
        # Open only this entry. All new predictions are committed before their truth is read.
        matches = [entry for entry in world["oracle"] if tuple(entry["settings"]) == cell]
        if len(matches) != 1:
            raise ValueError("The synthetic instrument must have a unique response")
        observed = matches[0]["value"]
        if observed is not None:
            receipt = dict(request, y=observed)
        status = session.reply([receipt] if receipt is not None else None)
        directly_measured = session.predict(x, cell)
        if directly_measured != observed or session.request(list(CUBE), x=x) is not None:
            raise ValueError("A reading was lost, invented, or requested twice")

    merged = offsets(history + ([receipt] if receipt else []))
    if session.spent != int(bool(missing)):
        raise ValueError("Grant accounting differs from actual requests")
    if any(session.predict(row["x"], row["settings"]) != row["y"] for row in history):
        raise ValueError("An original reading no longer replays")
    after = {c: session.predict(x, c) for c in CUBE}
    if any(before[c] != after[c] for c in original):
        raise ValueError("An existing setting was overwritten")
    changed = [list(c) for c in CUBE if before[c] != after[c]]
    if changed != ([list(cell)] if observed is not None else []):
        raise ValueError("The update escaped the intended setting")
    policies = {name: [] for name in ("no_read","old_rule","targeted","exact_only")}
    retained = 0
    for test in world["tests"]:
        u, target = test["x"], tuple(test["settings"])
        prior = local(original,u,target)
        prediction = session.predict(u,target)
        if prediction != local(merged,u,target):
            raise ValueError("Reader differs from receipt lookup")
        if prior is not None:
            if prediction != prior:
                raise ValueError("A previously supported endpoint changed")
            retained += 1
        policies["no_read"].append(prior)
        policies["old_rule"].append(u + old_law[target] if target in old_law else prior)
        policies["targeted"].append(prediction)
        policies["exact_only"].append(observed if target == cell and u == x else prior)
    actual = [t["y"] for t in world["tests"]]
    return dict(id=world["id"],kind=world["kind"],missing=[list(c) for c in missing],
                request=request,question=question,predicted_by_prior_rule=expected,observed=observed,
                direct_replay=directly_measured,status=status,changed=changed,retained=retained,
                predictions=policies["targeted"],truth=actual,
                scores={name:grade(values,actual) for name,values in policies.items()})


def summarize(cases):
    kinds = ("exception","agrees","unavailable","two_gaps","already_complete","unstable")
    if Counter(w["kind"] for w in cases) != {k:4 for k in kinds} or len({w["id"] for w in cases}) != 24:
        raise ValueError("Unexpected case bank")
    groups, policies = {}, {}
    for world in cases:
        r = run_case(world)
        counts = groups.setdefault(r["kind"], Counter())
        counts.update(requests=int(r["request"] is not None), readings=int(r["observed"] is not None),
                      unavailable=int(r["request"] is not None and r["observed"] is None),
                      retained=r["retained"], changed=len(r["changed"]), **r["scores"]["targeted"])
        for name, scores in r["scores"].items():
            policies.setdefault(name,Counter()).update(scores)
    return dict(by_kind=groups,policies=policies)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="show the requested controls, measured value and endpoint predictions")
    args = parser.parse_args()
    source = (HERE/"missing_setting_cases.json").read_bytes().replace(b"\r\n",b"\n")
    archive = json.loads((HERE/"missing_setting_results.json").read_bytes())
    if hashlib.sha256(source).hexdigest() != archive["case_sha256"]:
        raise ValueError("Case bank differs from freeze")
    cases = json.loads(source)
    result = summarize(cases)
    if result != archive["observed"]:
        raise ValueError("Replay differs from archived scores")
    if args.case:
        choice = next((w for w in cases if w["id"] == args.case),None)
        if choice is None:
            parser.error("unknown case ID")
        result = run_case(choice)
    print(json.dumps(result,indent=2))
