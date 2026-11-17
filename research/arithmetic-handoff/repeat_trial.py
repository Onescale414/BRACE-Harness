"""Replay the repeated-addition comparison and its separate boundary probes."""
import argparse
from collections import Counter
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from order_reader import continue_order, inspect_order
from repeat_reader import integer_runs, read_repeat
from replay import calculate


def exercise(text):
    runs = integer_runs(text)
    reading = read_repeat(text)
    decision = reading["decision"]
    if decision not in {"one", "two", "ask", "pass"}:
        raise ValueError("Unexpected reader decision")
    # This research path can hand off exactly one addition before multiplication.
    result = calculate(reading["frame"]) if decision == "one" else None
    if result and result["checks"] > 2:
        raise ValueError("Step-check budget exceeded")
    return {"runs": runs, "reading": reading, "result": result}


def evaluate(case):
    # Only the caller's text reaches the readers.
    detail = exercise(case["text"])
    result = detail["result"]
    label = case["label"]
    has_run = bool(detail["runs"])
    choices = {name: choice if has_run else "pass" for name, choice in
               (("merge", "one"), ("count", "two"), ("ask_on_repeat", "ask"))}
    choices["wording"] = detail["reading"]["decision"]
    expected_choice = "pass" if label == "outside" else label
    frame = {k: case[col] for k, col in (("start", "start"), ("add", "amount"), ("multiply", "multiplier"))}
    issued = result is not None and result["decision"] == "compute"
    right = (issued and label == "one" and result["frame"] == frame and
             result["value"] == (frame["start"] + frame["add"]) * frame["multiply"]
             and result["verdicts"] == ["checked", "checked"])
    exact = label in {"one", "two"} and choices["wording"] == label and detail["reading"]["frame"] == frame
    return dict(id=case["id"], label=label, **detail, choices=choices, exact_event_frame=exact,
                correct={k: v == expected_choice for k, v in choices.items()},
                checked_correct=int(right), wrong_release=int(issued and not right and label != "outside"),
                outside_release=int(issued and label == "outside"))


def summarize(cases, boundaries):
    if Counter(c["label"] for c in cases) != {k: 8 for k in ("one", "two", "ask", "outside")}:
        raise ValueError("Expected the prespecified balanced case bank")
    combined = cases + boundaries
    if len({c["id"] for c in combined}) != len(combined) or len({c["text"] for c in combined}) != len(combined):
        raise ValueError("Expected distinct case IDs and conversations")
    rows = [evaluate(case) for case in cases]
    counts = {}
    for label in ("one", "two", "ask", "outside"):
        group = [r for r in rows if r["label"] == label]
        counts[label] = {"flagged": sum(bool(r["runs"]) for r in group),
                         "correct": {k: sum(r["correct"][k] for r in group) for k in group[0]["correct"]},
                         "exact_event_frames": sum(r["exact_event_frame"] for r in group),
                         "wording_decisions": dict(Counter(r["reading"]["decision"] for r in group))}
    boundary_rows = []
    for case in boundaries:
        outcome = exercise(case["text"])
        result = outcome["result"]
        issued = result is not None and result["decision"] == "compute"
        matches = issued and case["permitted_release"] and case["expected_value"] == result["value"]
        boundary_rows.append(dict(id=case["id"], permitted=case["permitted_release"],
                                  decision=outcome["reading"]["decision"], checked_correct=bool(matches),
                                  wrong_release=bool(issued and not matches)))
    return dict(by_label=counts, correct_releases=sum(r["checked_correct"] for r in rows),
                wrong_releases=sum(r["wrong_release"] for r in rows),
                outside_releases=sum(r["outside_release"] for r in rows),
                total_checks=sum(r["result"]["checks"] for r in rows if r["result"]),
                boundaries=boundary_rows)


def development():
    originals = {
        "again": "Start with 5. Add 3, then add 3 again. Double the result.",
        "restatement": "Start with 5. Add 3. To be clear, that's a three-point bonus. Double the result.",
        "previous_failure": "Start with 5, add 3, add 3 and double. I'm not sure of the order. What's the total?",
    }
    results = {name: exercise(text) for name, text in originals.items()}
    text = originals["previous_failure"]
    turn = [dict(role="user", content=text)]
    pending = inspect_order(turn)
    reply = continue_order(pending, "Add 3 first.")
    results["previous_reader_after_reply"] = (calculate(reply["frame"]) if reply["decision"] == "compute"
                                               else reply)
    return results


def check_integer_runs():
    """Independent check of signed integer runs, with no arithmetic instructions."""
    matches = total = 0
    first_miss = None
    for size in range(5):
        for sequence in product((-2, 0, 2), repeat=size):
            text = "; ".join(str(n) for n in sequence)
            expected = []
            for start, value in enumerate(sequence):
                if start > 0 and sequence[start - 1] == value:
                    continue
                end = start + 1
                while end < size and sequence[end] == value:
                    end += 1
                if end - start >= 2:
                    expected.append((value, end - start))
            actual = [tuple(pair) for pair in integer_runs(text)]
            total += 1
            matches += actual == expected
            if actual != expected and first_miss is None:
                first_miss = dict(text=text, expected=expected, actual=actual)
    return dict(sequences=total, matched=matches, first_miss=first_miss)


def load_bank(file, digest):
    content = (HERE / file).read_bytes().replace(b"\r\n", b"\n")
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError(f"Unexpected frozen bank: {file}")
    return json.loads(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="show the source wording, gold label, reader and check receipts")
    args = parser.parse_args()
    archive = json.loads((HERE / "repeat_results.json").read_bytes())
    cases = load_bank("repeat_cases.json", archive["cases_sha256"])
    boundaries = load_bank("repeat_boundaries.json", archive["boundaries_sha256"])
    summary = summarize(cases, boundaries)
    if summary != archive["observed"]:
        raise ValueError("Replay differs from the saved observation")
    output = dict(fresh=summary, development=development(), integer_runs=check_integer_runs())
    if args.case:
        for case in cases + boundaries:
            if case["id"] == args.case:
                output = dict(source=case, outcome=evaluate(case) if case in cases else exercise(case["text"]))
                break
        else:
            parser.error("unknown case ID")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
