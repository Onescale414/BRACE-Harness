"""Compare a reusable probe design and empirically learned context partitions."""
from collections import Counter
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from context_cases import worlds
from context_reader import certify, rules
from partition import learn, verify
from probe_design import design_probes
from trial import context, visible

SEED = 584321


def bits(probe, keys):
    return tuple(probe["features"][k] for k in keys)


def check(candidate, entries, world):
    """Confirm a sealed candidate before exposing its predictions on new inputs."""
    stats = Counter(worlds=0, correct=0, wrong=0, held=8, validation_reads=0, accepted_entries=0)
    if candidate is None:
        return stats
    confirmations = [row["x"] + candidate(visible(row)) == row["y"] for row in world["validation"]]
    stats["validation_reads"] = len(confirmations)
    if all(confirmations):
        stats.update(worlds=1, held=-8, accepted_entries=entries)
        for row in world["tests"]:
            correct = row["x"] + candidate(visible(row)) == row["y"]
            stats["correct" if correct else "wrong"] += 1
    return stats


def run():
    bank = worlds(SEED)
    # Build one canonical design. Names, starting values and observed outcomes are absent.
    axes = ["a", "b", "c"]
    menu = [dict(features=dict(zip(axes, v))) for v in product((0, 1), repeat=3)]
    plan = design_probes(axes, rules(axes), menu)
    patterns = plan["patterns"]
    if patterns is None or len(patterns) > 3:
        raise ValueError("Design cannot be run within the prespecified three-probe budget")
    by_method = {}
    examples = []
    for w in bank:
        keys = w["keys"]
        inputs = {bits(r,keys): r for r in w["menu"]}
        training = [inputs[p] for p in patterns]
        remaining = [r for r in w["menu"] if bits(r,keys) not in patterns]
        first = certify(keys,training)
        # Commit before the instrument reveals any confirmation outcomes.
        unseen = [(r, r["x"] + first.delta(visible(r))) for r in w["tests"]
                  if first is not None and bits(r,keys) not in patterns]
        for arm in ("fixed", "active"):
            prior = context(w,3,arm)
            by_method.setdefault(arm+"_3",Counter()).update(
                worlds=prior["admitted"],correct=prior["tested"]-prior["wrong"], wrong=prior["wrong"],
                held=8-prior["tested"],validation_reads=prior["validation_reads"],
                selection_evaluations=prior["selection_evaluations"])
        result = check(first.delta if first else None, 0, w)
        result["unseen_predictions"] = len(unseen)
        result["unseen_predicted_correctly"] = sum(value == r["y"] for r,value in unseen)
        result["unseen_correct_in_confirmed_worlds"] = (result["unseen_predicted_correctly"]
                                                         if result["worlds"] else 0)
        by_method.setdefault("designed_3",Counter()).update(result)

        refuted = first is None or any(r["x"]+first.delta(visible(r)) != r["y"] for r in remaining)
        full = training+remaining
        one = certify(keys,full)
        by_method.setdefault("single_8",Counter()).update(check(one.delta if one else None,0,w))
        # The full lookup table and the wider representation receive exactly the same observations.
        cells = {bits(r,keys): r["y"]-r["x"] for r in full}
        lookup = check(lambda p:cells[bits(p,keys)],len(cells),w)
        by_method.setdefault("lookup_8",Counter()).update(lookup)
        if refuted:
            derived = learn(keys,full,max_size=2)
            if derived is not None and not verify(keys,full,derived,max_size=2):
                raise ValueError("Independent partition verification failed")
            if derived is None:
                answer = check(None, 0, w)
            else:
                answer = check(lambda p: derived.table[bits(p,derived.keys)], len(derived.table), w)
                examples.append(dict(world=w["id"],kind=w["kind"],axes=list(derived.keys),
                                     table=[dict(bits=list(k),effect=v) for k,v in sorted(derived.table.items())],
                                     confirmed=bool(answer["worlds"])))
        else:
            answer = check(first.delta, 1 if first.key is None else 2, w)
        answer["expanded"] = int(refuted)
        by_method.setdefault("repair_8",Counter()).update(answer)
    return dict(patterns=[list(p) for p in patterns],certificate=plan["certificate"],
                cold_design_predictions=len(menu)*len(rules(axes)),
                cold_subsets_tried=sum(plan["certificate"]["attempts_by_size"]),methods=by_method,
                recovered_partitions=examples)


if __name__ == "__main__":
    result = run()
    saved = json.loads((HERE/"extension_results.json").read_bytes())
    if json.loads(json.dumps(result)) != saved:
        raise ValueError("Follow-up replay differs from recorded results")
    print(json.dumps(result,indent=2))
