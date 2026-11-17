"""Replay two bounded domain-building experiments, without a model or network."""
import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from context_cases import worlds
from context_reader import certify, choose, feature_used, rules, update
from learner import Domain, check_trace


def outcomes(start, verbs, transition):
    values = []
    for verb in verbs:
        start = transition(verb, start)
        if start is None:
            return None
        values.append(start)
    return values


def apply(rule, x):
    return None if rule is None else rule[0] * x + rule[1]


def direct_fit(rows, reserved):
    x, y = rows[0]
    u, v = rows[1]
    slope, remainder = divmod(v-y, u-x)
    bias = y - slope*x
    if remainder or abs(slope) > 3 or abs(bias) > 5:
        return None
    if any(slope*i+bias != j for i,j in reserved):
        return None
    return slope, bias


def scalar(world):
    domain = Domain(world["id"])
    verbs = [r["verb"] for r in world["teaching"]]
    memory, initial, direct = {}, {}, {}
    for r in world["teaching"]:
        domain.teach(r["verb"], r["x"], r["y"])
        initial[r["verb"]] = domain.diagnose(r["verb"])["provisional"]
        memory[r["verb"], r["x"]] = r["y"]
    feedback_misses = 0
    for r in world["feedback"]:
        verb, x, y = r["verb"], r["x"], r["y"]
        feedback_misses += apply(initial[verb], x) != y
        domain.observe(verb, x, y)
        memory[verb, x] = y
    revised = {v: domain.diagnose(v)["provisional"] for v in verbs}
    for r in world["validation"]:
        domain.validate(r["verb"], r["x"], r["y"])
    for v in verbs:
        readings = domain.diagnose(v)
        direct[v] = direct_fit(readings["evidence"], readings["validation"])
    reopened = Domain.from_snapshot(json.loads(json.dumps(domain.snapshot())))
    binding = {v:dict(first=initial[v], revised=revised[v], status=domain.diagnose(v)["status"])
               for v in verbs}
    scores, altered = {}, 0
    for case in world["tests"]:
        start, moves, truth = case["x"], case["verbs"], case["trace"]
        if len(truth) != len(moves) or truth[-1] != case["y"]:
            raise ValueError("Inconsistent held-out trace")
        trace = domain.execute(start, moves)
        if trace != reopened.execute(start, moves):
            raise ValueError("Reopened domain changed its decision")
        predictions = {
            "exact_lookup": outcomes(start, moves, lambda v,x: memory.get((v,x))),
            "initial_guess": outcomes(start, moves, lambda v,x: apply(initial[v],x)),
            "after_feedback_unchecked": outcomes(start, moves, lambda v,x: apply(revised[v],x)),
            "direct_two_point": outcomes(start, moves, lambda v,x: apply(direct[v],x)),
            "checked": [s["after"] for s in trace] if trace is not None else None,
        }
        for arm, values in predictions.items():
            count = scores.setdefault(arm, Counter(right=0, wrong=0, held=0))
            count["held" if values is None else "right" if values == truth else "wrong"] += 1
        if trace and len(trace) > 1:
            fake = deepcopy(trace)
            fake[0]["after"] += 1
            fake[1]["before"] = fake[0]["after"]
            if check_trace(domain,start,moves,fake):
                raise ValueError("Checker missed altered intermediate with original endpoint")
            altered += 1
    return dict(id=world["id"], kind=world["kind"], bindings=binding, feedback_misses=feedback_misses,
                revised=sum(initial[v] != revised[v] for v in verbs), scores=scores,
                tampered_traces_rejected=altered)


def visible(row, use_features=True):
    probe = dict(verb=row["verb"], x=row["x"])
    if use_features:
        probe["features"] = dict(row["features"])
    return probe


def context(world, budget, method):
    conditional = method != "constant"
    candidates = rules(world["keys"], conditional)
    unused = list(world["menu"])
    readings, counts = [], [len(candidates)]
    score_evaluations = 0
    for _ in range(budget):
        if method == "active" and len(candidates) > 1:
            menu = [visible(r) for r in unused]
            score_evaluations += len(menu)*len(candidates)
            idx = choose(candidates, menu)
        else:
            idx = 0
        chosen = unused.pop(idx)
        observed = dict(visible(chosen, conditional), y=chosen["y"])
        readings.append(observed)
        candidates = update(candidates, observed)
        counts.append(len(candidates))
    candidate = candidates[0] if len(candidates) == 1 else None
    fitted = certify(world["keys"], readings, conditional)
    if fitted != candidate:
        raise ValueError("Independent empirical fit disagrees with enumeration")
    confirmation = []
    if fitted:
        for row in world["validation"]:
            confirmation.append(row["x"] + fitted.delta(visible(row, conditional)) == row["y"])
    admitted = bool(confirmation) and all(confirmation)
    checked = 0
    wrong = 0
    for row in world["tests"]:
        if admitted:
            checked += 1
            wrong += row["x"] + fitted.delta(visible(row, conditional)) != row["y"]
    return dict(id=world["id"], kind=world["kind"], arm=method, budget=budget,
                probes=[a["x"] for a in readings], counts=counts, admitted=admitted,
                identified_feature=feature_used(candidates) if admitted else None,
                feature_correct=admitted and world["kind"]=="single" and fitted.key==world["causal_key"],
                tested=checked, wrong=wrong, validation_reads=len(confirmation),
                validation_veto=bool(confirmation) and not admitted, selection_evaluations=score_evaluations)


def summary(scalar_bank, context_bank):
    scalars = [scalar(w) for w in scalar_bank]
    if len(scalars) != 6 or sum(len(w["tests"]) for w in scalar_bank) != 48:
        raise ValueError("Unexpected scalar bank")
    totals = {}
    for w in scalars:
        for name, stats in w["scores"].items():
            totals.setdefault(name,Counter()).update(stats)
    summary_rows = []
    for budget in (2,3,4):
        for method in ("constant","fixed","active"):
            rows = [context(w,budget,method) for w in context_bank]
            summary_rows.append(dict(arm=method,budget=budget, worlds=sum(r["admitted"] for r in rows),
                supported=sum(r["admitted"] and r["kind"] in ("constant","single") for r in rows),
                features=sum(r["feature_correct"] for r in rows),
                tested=sum(r["tested"] for r in rows), wrong=sum(r["wrong"] for r in rows),
                validation_reads=sum(r["validation_reads"] for r in rows),
                validation_vetoes=sum(r["validation_veto"] for r in rows),
                selection_evaluations=sum(r["selection_evaluations"] for r in rows)))
    return dict(scalar_scores=totals,feedback_misses=sum(r["feedback_misses"] for r in scalars),
                revised=sum(r["revised"] for r in scalars),
                validated=sum(v["status"]=="validated" for r in scalars for v in r["bindings"].values()),
                tampered_traces_rejected=sum(r["tampered_traces_rejected"] for r in scalars),
                context_scores=summary_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", help="show a fitted scalar domain or contextual probe trace")
    args = parser.parse_args()
    source = (HERE/"scalar_cases.json").read_bytes().replace(b"\r\n", b"\n")
    archive = json.loads((HERE/"results.json").read_bytes())
    if hashlib.sha256(source).hexdigest() != archive["scalar_sha256_lf"]:
        raise ValueError("Frozen bank mismatch")
    s, c = json.loads(source), worlds()
    data = summary(s,c)
    if data != archive["observed"]:
        raise ValueError("Replay differs from archived observation")
    if args.world:
        world = next((w for w in s+c if w["id"]==args.world),None)
        if world is None:
            parser.error("unknown world")
        data = scalar(world) if "teaching" in world else [context(world,4,m) for m in ("constant","fixed","active")]
    print(json.dumps(data,indent=2))


if __name__ == "__main__":
    main()
