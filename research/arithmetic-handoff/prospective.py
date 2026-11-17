"""Replay the prespecified conflict-only policy on a fresh conversational bank."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from feedback import compare
from replay import FIELDS, baseline, gate_decision, grade, inspect_messages, response

ARMS = ("initial", "strict_agreement", "neutral", "advisory", "always_signal", "conflict_only")
PHASES = ("draft", "neutral", "advisory", "signal")


def unique_fields(items):
    fields = dict(items)
    if len(fields) != len(items):
        raise ValueError("Duplicate field in draft")
    return fields


def parse(raw):
    if not isinstance(raw, str):
        return None
    try:
        draft = json.loads(raw, object_pairs_hook=unique_fields)
    except (ValueError, RecursionError):
        return None
    if not isinstance(draft, dict) or set(draft) != {"action", *FIELDS}:
        return None
    if draft["action"] not in ("compute", "clarify", "unsupported"):
        return None
    return draft if all(type(draft[k]) is int for k in FIELDS) else None


def evaluate_case(case):
    reading = inspect_messages(case["messages"])
    record = case["record"]
    drafts = {phase: parse(record[phase]) for phase in PHASES}
    initial = drafts["draft"]
    signal = compare(reading, initial or {})
    if record["reader_signal"] != signal:
        raise ValueError(f"{case['id']}: archived verifier signal differs")
    if initial is None:
        return signal, {arm: response("withhold") for arm in ARMS}

    # Only the original, independently produced signal decides which reply is released.
    reviewed = {phase: baseline(drafts[phase]) for phase in PHASES}
    outcomes = dict(initial=reviewed["draft"], strict_agreement=gate_decision(reading, initial),
                    neutral=reviewed["neutral"], advisory=reviewed["advisory"],
                    always_signal=reviewed["signal"],
                    conflict_only=reviewed["signal"] if signal == "conflict" else reviewed["advisory"])
    if any(r["checks"] > 2 for r in outcomes.values()):
        raise ValueError("A release exceeded the two-step check limit")
    return signal, outcomes


def summarize(cases):
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Case IDs must be distinct")
    if Counter(c["kind"] for c in cases) != {"compute": 16, "clarify": 8, "unsupported": 8}:
        raise ValueError("Expected the predeclared 32-case distribution")
    signals = Counter(agree=0, conflict=0, unresolved=0)
    totals = {arm: Counter() for arm in ARMS}
    paired = {metric: {key: [] for key in ("both", "advisory_only", "conflict_only", "neither")}
              for metric in ("clear_answered", "faithful_clear", "appropriate", "wrong_releases")}
    for case in cases:
        signal, outcomes = evaluate_case(case)
        signals[signal] += 1
        # The request label and expected operands enter only after the policy has committed.
        grades = {arm: grade(case, outcome) for arm, outcome in outcomes.items()}
        for arm, g in grades.items():
            g["clear_answered"] = g["clear"] * g["releases"]
            totals[arm].update(g)
            totals[arm].update(wrong_clear=g["clear"] * g["wrong_releases"],
                               noncompute_releases=(1-g["clear"]) * g["releases"])
        for metric, groups in paired.items():
            if metric in ("clear_answered", "faithful_clear") and case["kind"] != "compute":
                continue
            before, after = (bool(grades[arm][metric]) for arm in ("advisory", "conflict_only"))
            key = { (True, True): "both", (True, False): "advisory_only",
                    (False, True): "conflict_only", (False, False): "neither" }[before, after]
            groups[key].append(case["id"])
    primary_pass = (not paired["clear_answered"]["advisory_only"]
                    and not paired["faithful_clear"]["advisory_only"]
                    and totals["conflict_only"]["wrong_releases"] < totals["advisory"]["wrong_releases"])
    return dict(signals=dict(signals), arms={a:dict(t) for a,t in totals.items()},
                paired=paired, primary_pass=primary_pass)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--case", help="Inspect one dialogue, its recorded proposals and checked outcomes")
    args = cli.parse_args()
    data = json.loads((HERE / "prospective.json").read_bytes())
    cases = data["cases"]
    observed = summarize(cases)
    if observed != data["observed"]:
        raise ValueError("Replayed results differ from the archived observation")
    print("Verifier signals:", dict(observed["signals"]))
    print("Policy              Clear answered  Faithful clear  Wrong clear  Unwarranted  Appropriate  Checks")
    for arm, g in observed["arms"].items():
        print(f"{arm:18} {g['clear_answered']:3}/16         {g['faithful_clear']:3}/16"
              f"           {g['wrong_clear']:3}         {g['noncompute_releases']:3}"
              f"          {g['appropriate']:3}/32     {g['checks']:3}")
    print("Paired outcomes (advisory compared with conflict-only):")
    for name, groups in observed["paired"].items():
        print(" ", name, {key:len(ids) for key, ids in groups.items()})
    print("Prespecified primary criterion passed:", observed["primary_pass"])
    if args.case:
        found = next((c for c in cases if c["id"] == args.case), None)
        if found is None:
            cli.error("Unknown case ID")
        signal, outcomes = evaluate_case(found)
        print(json.dumps({**found, "verified_signal": signal, "outcomes": outcomes}, indent=2))


if __name__ == "__main__":
    main()
