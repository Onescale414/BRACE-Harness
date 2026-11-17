"""Run archived model proposals through the current public two-step arithmetic checker."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[1])]
from demo import proposal
from gate import inspect_messages
from harness import Candidate, Reply, run_bound

FIELDS = ("start", "add", "multiply")
ARMS = ("baseline", "gate_only", "gate_retry", "rule_only")


def model_frame(draft):
    if not isinstance(draft, dict) or draft.get("action") != "compute":
        return None
    if set(draft) != {"action", *FIELDS} or any(type(draft[k]) is not int for k in FIELDS):
        return None
    return {k: draft[k] for k in FIELDS}


def retry_needed(gate, draft):
    return gate["kind"] == "compute" and model_frame(draft) != gate["frame"]


def response(decision):
    return dict(decision=decision, frame=None, value=None, checks=0, verdicts=[])


def calculate(frame):
    instruction = "Start with {start}. Add {add}, then multiply by {multiply}.".format(**frame)

    def host_proposer(ticket, view):
        return Reply(ticket.ticket_id, (Candidate(proposal(view)),))

    outcome = run_bound(instruction.encode("ascii"), host_proposer, checks_per_step=2)
    checked = outcome.status == "checked" and outcome.terminal.decision == "publish"
    verdicts = [r.verdict for r in outcome.receipts]
    if len(verdicts) > 2 or (checked and verdicts != ["checked", "checked"]):
        raise ValueError("Unexpected arithmetic check budget or receipt sequence")
    return dict(decision="compute" if checked else "withhold", frame=frame,
                value=outcome.value if checked else None, checks=len(verdicts), verdicts=verdicts)


def baseline(draft):
    frame = model_frame(draft)
    if frame is not None:
        return calculate(frame)
    if (isinstance(draft, dict) and set(draft) == {"action", *FIELDS}
            and all(type(draft[k]) is int for k in FIELDS)
            and draft.get("action") in ("clarify", "unsupported")):
        return response(draft["action"])
    return response("withhold")


def gate_decision(gate, draft):
    if gate["kind"] == "unsupported":
        return response("unsupported")
    if gate["kind"] in ("unresolved", "clarify") or retry_needed(gate, draft):
        return response("clarify")
    return calculate(gate["frame"])


def evaluate_case(case):
    gate = inspect_messages(case["messages"])
    if gate != case["gate"] or gate["kind"] not in ("compute", "clarify", "unsupported", "unresolved"):
        raise ValueError(f"{case['id']}: recorded gate decision differs")
    if gate["kind"] == "compute" and model_frame(dict(action="compute", **gate["frame"])) is None:
        raise ValueError("Gate returned invalid numeric fields")
    initial = case["raw_draft"]
    retry = retry_needed(gate, initial)
    if case["retry_issued"] is not retry or (not retry and case["retry"] is not None):
        raise ValueError(f"{case['id']}: retry issued outside the declared policy")
    rule_draft = dict(action="compute", **gate["frame"]) if gate["kind"] == "compute" else None
    return {"baseline": baseline(initial), "gate_only": gate_decision(gate, initial),
            "gate_retry": gate_decision(gate, case["retry"] if retry else initial),
            "rule_only": gate_decision(gate, rule_draft)}


def grade(case, result):
    # Labels first enter after all four arms have committed their decisions.
    expected = case["kind"]
    actual = result["decision"]
    if expected not in ("compute", "clarify", "unsupported"):
        raise ValueError("Unknown gold action")
    clear = expected == "compute"
    issued = actual == "compute"
    exact = False
    number = False
    if clear:
        frame = {k: case[k] for k in FIELDS}
        if any(type(v) is not int for v in frame.values()):
            raise ValueError("Missing gold operand")
        if (frame["start"] + frame["add"]) * frame["multiply"] != case["expected"]:
            raise ValueError("Gold number differs from labeled operation")
        exact = issued and result["frame"] == frame
        number = issued and result["value"] == case["expected"]
    faithful = exact and number
    return dict(cases=1, clear=int(clear), appropriate=int(faithful if clear else actual == expected),
                faithful_clear=int(faithful), correct_clear_number=int(number),
                wrong_releases=int(issued and not faithful), releases=int(issued),
                safe_noncompute_holds=int(not clear and not issued), unnecessary_holds=int(clear and not issued),
                correct_clarifications=int(expected == actual == "clarify"),
                correct_unsupported=int(expected == actual == "unsupported"), checks=result["checks"])


def summarize(cases, outcomes=None):
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Expected distinct case IDs")
    outcomes = outcomes if outcomes is not None else {c["id"]: evaluate_case(c) for c in cases}
    totals = {arm: {} for arm in ARMS}
    for case in cases:
        for arm in ARMS:
            for key, value in grade(case, outcomes[case["id"]][arm]).items():
                totals[arm][key] = totals[arm].get(key, 0) + value
    return totals


def summarize_first(cases):
    """Original language/compute separation trial, scored using the archived two model calls."""
    totals = dict(clear=0, noncompute=0, direct_right_number=0, tool_right_number=0,
                  oracle_right_number=0, direct_right_disposition=0, tool_right_disposition=0)
    for case in cases:
        direct = case["direct"] or {}
        tool = baseline(case["raw_draft"])
        result = grade(case, tool)
        if case["kind"] == "compute":
            oracle = calculate({k: case[k] for k in FIELDS})
            totals["clear"] += 1
            totals["direct_right_number"] += int(direct.get("action") == "compute"
                and type(direct.get("answer")) is int and direct["answer"] == case["expected"])
            totals["tool_right_number"] += result["correct_clear_number"]
            totals["oracle_right_number"] += int(oracle["decision"] == "compute" and oracle["value"] == case["expected"])
        else:
            totals["noncompute"] += 1
            totals["direct_right_disposition"] += int(direct.get("action") == case["kind"])
            totals["tool_right_disposition"] += result["appropriate"]
    return totals


def replay_group(cases, expected_totals):
    outcomes = {c["id"]: evaluate_case(c) for c in cases}
    totals = summarize(cases, outcomes)
    if totals != expected_totals:
        raise ValueError("Results differ from the archived totals")
    for case in cases:
        if case["observed"] != outcomes[case["id"]]:
            raise ValueError(f"{case['id']}: archived outcome differs")
    return totals, outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="Show the evidence for one fresh case, control, or boundary probe")
    args = parser.parse_args()
    data = json.loads((HERE / "evidence.json").read_bytes())
    first = summarize_first(data["first_trial"])
    if first != data["first_totals"]:
        raise ValueError("Original language/compute totals differ")
    cases = data["cases"]
    totals, outcomes = replay_group(cases, data["observed_totals"])
    print(f"Earlier trial: right number on {first['clear']} clear requests: "
          f"direct {first['direct_right_number']}, model + tool {first['tool_right_number']}, "
          f"tool given correct inputs {first['oracle_right_number']}.")
    print(f"Appropriate response on {first['noncompute']} incomplete or unsupported requests: "
          f"direct {first['direct_right_disposition']}, model + tool {first['tool_right_disposition']}.\n")
    print(f"{len(cases)} conversations. Each arm has up to two arithmetic checks per conversation.")
    print("policy       correct  faithful clear  wrong releases  unnecessary holds  checks")
    for arm, t in totals.items():
        print(f"{arm:11}  {t['appropriate']:2}/{t['cases']:<2}    {t['faithful_clear']:2}/{t['clear']:<2}"
              f"          {t['wrong_releases']:3}              {t['unnecessary_holds']:3}         {t['checks']:3}")
    print(f"Retry policy requested {sum(c['retry_issued'] for c in cases)} additional model calls (archived).")
    controls = data["controls"]
    control_totals, control_outcomes = replay_group(controls, data["control_totals"])
    print(f"\nSeparate live controls using supported wording ({len(controls)}; excluded from fresh totals)")
    for arm, t in control_totals.items():
        print(f"  {arm}: {t['faithful_clear']}/{t['clear']} faithful answers,"
              f" {t['wrong_releases']} wrong releases, {t['checks']} checks.")
    print(f"  Retry policy requested {sum(c['retry_issued'] for c in controls)} additional model calls (archived).")
    probes = data["probes"]
    probe_outcomes = {}
    for probe in probes:
        actual = inspect_messages(probe["messages"])
        if actual != probe["gate"]:
            raise ValueError(f"{probe['id']}: archived boundary decision differs")
        probe_outcomes[probe["id"]] = actual
    allowed = sum(p["kind"] == "compute" for p in probe_outcomes.values())
    print(f"\nSeparate scope and negation probes (reader only; excluded from fresh totals)")
    print(f"  {allowed}/{len(probes)} admitted a numeric frame.")
    all_cases = [*cases, *controls, *probes]
    if len({c["id"] for c in all_cases}) != len(all_cases):
        raise ValueError("A case ID repeats within or across groups")
    if args.case:
        all_outcomes = {**outcomes, **control_outcomes, **probe_outcomes}
        if args.case not in all_outcomes:
            parser.error("Unknown case ID. See evidence.json for available conversations.")
        case = next(c for c in all_cases if c["id"] == args.case)
        print(json.dumps({**case, "replayed": all_outcomes[args.case]}, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
