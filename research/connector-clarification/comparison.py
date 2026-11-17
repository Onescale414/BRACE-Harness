"""Replay both readers on the same frozen utterances and independently check their previews."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import replay


def run_case(case, arm, interpret, routes, mapping, evidence):
    question = case["question_id"]
    value, prompt = interpret(question, case["reply"])
    replay.require(value in {"yes", "no", "unknown"}, "Invalid reader value")
    replay.require(prompt is None or (value == "unknown" and isinstance(prompt, str) and prompt.strip()),
                   "Clarification must keep the original check budget")
    decision = value if value != "unknown" else ("ask" if prompt else "hold")
    recorded = case[arm]
    replay.require((decision, prompt) == (recorded["decision"], recorded["prompt"]), "Reader decision changed")
    inferred_question, _, _, eligible = replay.choose(routes, mapping["resource"], mapping["symptom"],
                                                       case["reply"], lambda q, text: value)
    replay.require(question == inferred_question, "Mapping does not lead to the recorded question")
    issued = recorded["checks"]
    spent, released = 0, None
    for i in eligible:
        replay.require(spent < len(issued), "Missing archived check")
        resource, action, _ = routes[i]
        path = f"/v2/{resource}/{action}/{mapping['suffix']}"
        passed = replay.replay_check(mapping, path, evidence[issued[spent]])
        spent += 1
        if passed:
            released = path
            break
    replay.require(spent == len(issued) and spent <= replay.BUDGET, "Budget or receipt count differs")
    replay.require(recorded["released"] is (released is not None), "Release differs from archived outcome")
    return {"decision": decision, "prompt": prompt, "spent": spent, "released": released}


def show(case, outcomes):
    print(f"\n{case['id']}  {case['reply']}")
    print(f"  Expected {case['expected']}.")
    for arm, result in outcomes.items():
        print(f"  {arm:9} {result['decision']:4}  {result['spent']}/2 checks", end="")
        if result["released"]:
            print(f"  checked GET {result['released']}", end="")
        if result["prompt"]:
            print(f"  {result['prompt']}", end="")
        print()


def report(cases, outcomes):
    groups = defaultdict(list)
    for case in cases:
        if case["group"] == "scope_pair":
            groups[case["pair"]].append(case)
    for pair in groups.values():
        replay.require(len(pair) == 2 and {c["expected"] for c in pair} == {"yes", "hold"},
                       "Scope pairs must contain a current instruction and its other-request partner")
        current, other = sorted(pair, key=lambda c: c["expected"] != "yes")
        replay.require(current["mapping"] == other["mapping"] and current["question_id"] == other["question_id"]
                       and current["reply"].count("this request") == 1
                       and current["reply"].replace("this request", "another request") == other["reply"],
                       "Matched pair differs outside the scope marker")
    for arm in ("baseline", "candidate"):
        counts = Counter()
        for c in cases:
            result = outcomes[c["id"]][arm]
            counts["matches"] += c["expected"] == result["decision"]
            counts["checks"] += result["spent"]
        both, preserved, extra_questions = 0, 0, 0
        for pair in groups.values():
            current, other = sorted(pair, key=lambda c: c["expected"] != "yes")
            yes, hold = outcomes[current["id"]][arm], outcomes[other["id"]][arm]
            both += bool(yes["decision"] == "yes" and yes["released"]
                         and hold["decision"] == "hold" and hold["spent"] == 0)
            preserved += hold["spent"] == 0
            extra_questions += hold["decision"] == "ask"
        print(f"{arm:9}  decisions matched {counts['matches']}/{len(cases)},"
              f"  scope pairs both correct {both}/{len(groups)},  checks spent {counts['checks']}")
        print(f"           unrelated replies with both checks intact {preserved}/{len(groups)},"
              f" including {extra_questions} unnecessary questions")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="show the decisions, question and checks for one case ID")
    args = parser.parse_args()
    data = json.loads((HERE / "comparison.json").read_bytes())
    routes = replay.catalog(json.loads((HERE / "cases.json").read_bytes()))
    published = replay.load_reader()
    code = (HERE / "reader_candidate.py").read_bytes().replace(b"\r\n", b"\n")
    replay.require(hashlib.sha256(code).hexdigest() == data["reader_sha256"], "Candidate fingerprint changed")
    from reader_candidate import interpret

    limit = json.loads((HERE / "limit.json").read_bytes())
    limit_case = limit["case"]
    evidence = data["receipts"] | limit["receipts"]
    for key, receipt in evidence.items():
        replay.require(replay.digest(receipt) == key, "Archived receipt fingerprint changed")
    readers = {"baseline": lambda q, text: (published(q, text), None), "candidate": interpret}
    cases, outcomes = data["cases"], {}
    for case in [*cases, limit_case]:
        replay.require(case["id"] not in outcomes and case["expected"] in {"yes", "no", "hold", "ask"},
                       "Duplicate case ID or unsupported label")
        mapping = data["mappings"][case["mapping"]]
        outcomes[case["id"]] = {
            arm: run_case(case, arm, reader, routes, mapping, evidence)
            for arm, reader in readers.items()
        }
    print(f"{len(cases)} synthetic replies. {len(routes)} possible repairs. Two checks per conversation.")
    report(cases, outcomes)
    if args.case:
        if args.case not in outcomes:
            parser.error(f"Unknown case {args.case}. See the IDs in comparison.json and limit.json.")
        chosen = [c for c in [*cases, limit_case] if c["id"] == args.case]
    else:
        chosen = []
        for expected in ("yes", "hold", "ask"):
            correct = next((c for c in cases if c["expected"] == expected
                            and outcomes[c["id"]]["candidate"]["decision"] == expected), None)
            if correct:
                chosen.append(correct)
        miss = next((c for c in cases if outcomes[c["id"]]["candidate"]["decision"] != c["expected"]), None)
        if miss:
            chosen.append(miss)
        chosen.append(limit_case)
    for case in chosen:
        if case is limit_case:
            print("\nSeparate exclusion probe, outside the totals above.")
        show(case, outcomes[case["id"]])


if __name__ == "__main__":
    main()
