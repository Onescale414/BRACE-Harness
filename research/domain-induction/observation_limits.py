"""Inspect two information limits using the frozen cases, after the primary trial."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from context_reader import rules, update
from observation_trial import field_case, request_reading, single_case, tally, visible


def indistinguishable_pairs(worlds):
    groups = defaultdict(list)
    for w in worlds:
        # Even an unlimited menu budget would reveal only this signature.
        signature = [w["keys"], w["fit"], w["menu"], [visible(r) for r in w["tests"]]]
        groups[json.dumps(signature, sort_keys=True)].append(w)
    results = []
    for matches in groups.values():
        if len(matches) != 2:
            continue
        a, b = matches
        differences = [(left, right) for left, right in zip(a["tests"],b["tests"])
                       if left["y"] != right["y"]]
        left_run, right_run = single_case(a,"selected"), single_case(b,"selected")
        if (left_run["question"], left_run["observed"], left_run["rule"]) != (
                right_run["question"], right_run["observed"], right_run["rule"]):
            raise ValueError("Policy distinguished worlds by information outside the receipts")
        for left, right in differences:
            if any(r["features"] == left["features"] for r in a["fit"] + a["menu"]):
                raise ValueError("Unexpected witnessed exceptional setting")
            results.append(dict(pair=[a["id"],b["id"]],unoffered_setting=visible(left),
                                actual_outputs=[left["y"],right["y"]]))
    return results


def one_historical_bit(worlds):
    # Deliberately generous oracle: gift the identity of a separately confirmed, correct sensor.
    # Strip every archived sensor value before estimating its orientation from a single read.
    counts = Counter()
    for w in worlds:
        if w["class"] != "unique":
            continue
        full = field_case(w,"selected")
        if not full["confirmed"]:
            raise ValueError("Expected correct oracle field")
        key = full["field"]
        d0, d1 = sorted({r["y"]-r["x"] for r in w["fit"]})
        first = w["fit"][0]
        bit = w["fit_channels"][key][0]
        mappings = [offsets for offsets in [(d0,d1),(d1,d0)] if first["x"]+offsets[bit]==first["y"]]
        if len(mappings) != 1:
            raise ValueError("One bit failed to orient an already known binary discriminator")
        offsets = mappings[0]
        counts.update(worlds=1,historical_reads=1)
        for r in w["tests"]:
            possible = {r["x"]+d for d in offsets}
            counts["unresolved_without_new_bit"] += len(possible)>1
            # Counterfactual control: explicitly pay for a fresh bit on each request.
            counts["extra_current_reads"] += 1
            counts["correct_with_current_bit"] += r["x"]+offsets[r["channels"][key]]==r["y"]
    return counts


def keep_consistent_cells(worlds):
    """A failed domain-wide law may coexist with usable evidence at other settings."""
    totals = {}
    for method in ("no_grant", "selected"):
        counts = Counter()
        for w in worlds:
            readings = list(w["fit"])
            candidates = rules(w["keys"])
            for row in readings:
                candidates = update(candidates,row)
            index = request_reading(candidates,[visible(r) for r in w["menu"]],method)
            if index is not None:
                readings.append(w["menu"][index])
                counts["reads"] += 1
            effects = defaultdict(set)
            def cell(row):
                return tuple(row["features"][k] for k in w["keys"])
            for row in readings:
                effects[cell(row)].add(row["y"]-row["x"])
            predictions = []
            for row in w["tests"]:
                observed = effects.get(cell(row),set())
                predictions.append(row["x"]+next(iter(observed)) if len(observed)==1 else None)
            counts.update(tally(predictions,[r["y"] for r in w["tests"]]))
        totals[method] = counts
    return totals


if __name__ == "__main__":
    cases = json.loads((HERE/"observation_cases.json").read_bytes())
    sensor = json.loads((HERE/"field_cases.json").read_bytes())["worlds"]
    print(json.dumps(dict(pairs=indistinguishable_pairs(cases),one_bit=one_historical_bit(sensor),
                          witnessed_cells=keep_consistent_cells(cases)),indent=2))
