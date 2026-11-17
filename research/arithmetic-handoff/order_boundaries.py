"""Replay the earlier Qwen drafts and probe replies to the original bonus question."""
from pathlib import Path
import json
import sys
from itertools import permutations

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from order_reader import continue_order, inspect_order, order_question
from prospective import evaluate_case
from replay import calculate, grade, response


def saved_trial(cases):
    changes = []
    totals = {"before": {}, "after": {}}
    for case in cases:
        _, outcomes = evaluate_case(case)
        before = outcomes["conflict_only"]
        reading = inspect_order(case["messages"])
        after = response("clarify") if reading["decision"] == "ask_order" else before
        if after != before:
            changes.append({"id": case["id"], "before": before, "after": after})
        for arm, outcome in (("before", before), ("after", after)):
            scored = grade(case, outcome)
            for metric in ("faithful_clear", "wrong_releases", "checks"):
                totals[arm][metric] = totals[arm].get(metric, 0) + scored[metric]
    return {"totals": totals, "changes": changes}


# These are alternatives to the same pending question, not successive turns.
REPLIES = (
    ("addition first", "Add first.", "compute"),
    ("multiplication first", "Double first.", "unsupported"),
    ("undecided", "I haven't decided.", "clarify"),
    ("hypothetical", "Suppose we add first. Would that be allowed?", "clarify"),
    ("negated choice", "Don't add first. I want to double first.", "unsupported"),
    ("changed amount", "Add first, but use a bonus of 5.", "clarify"),
    ("earlier round", "Last round we added first. For this round we haven't chosen.", "clarify"),
    ("quoted suggestion", "\"Add first\" was someone else's suggestion. I haven't chosen.", "clarify"),
)


def reply_probes(seed):
    results = []
    for label, reply, expected in REPLIES:
        pending = inspect_order(seed["messages"])
        if pending["decision"] != "ask_order":
            results.append(dict(label=label, expected=expected, actual="no pending question"))
            continue
        decision = continue_order(pending, reply)
        actual = decision["decision"]
        checked = calculate(decision["frame"]) if actual == "compute" else response(actual)
        correct = (actual == expected and
                   (actual != "compute" or (checked["frame"] == {"start": 7, "add": 3, "multiply": 2}
                                            and checked["value"] == 20)))
        results.append(dict(label=label, reply=reply, expected=expected, actual=actual,
                            checks=checked["checks"], released=checked["value"], correct=correct))
    return results


def replies_given_exact_frame(cases):
    """Bypass only the initial recognition, using the labeled quantities for diagnosis."""
    rows = []
    for case in cases:
        if case["label"] != "ask_order":
            continue
        frame = {key: case[key] for key in ("start", "add", "multiply")}
        pending = dict(decision="ask_order", frame=frame, question=order_question(frame))
        row = {"id": case["id"]}
        for branch, text in case["replies"].items():
            decision = continue_order(pending, text)
            actual = decision["decision"]
            if actual == "compute":
                checked = calculate(decision["frame"])
                row[branch] = "correct checked" if (branch == "add_first" and
                        checked["value"] == case["add_first_value"] and checked["frame"] == frame
                        and checked["verdicts"] == ["checked", "checked"]) else "wrong release"
            else:
                row[branch] = actual
        rows.append(row)
    return rows


def fixed_choices(cases):
    """Post-trial control: simulate two explicit selections with known quantities."""
    checked = unsupported = 0
    for case in cases:
        if case["label"] != "ask_order":
            continue
        frame = {k: case[k] for k in ("start", "add", "multiply")}
        pending = dict(decision="ask_order", frame=frame, question=order_question(frame))
        choice = "Subtract first." if frame["add"] < 0 else "Add first."
        add = continue_order(pending, choice)
        if add["decision"] == "compute":
            outcome = calculate(add["frame"])
            checked += (outcome["frame"] == frame and outcome["value"] == case["add_first_value"]
                        and outcome["verdicts"] == ["checked", "checked"])
        unsupported += continue_order(pending, "Multiply first.")["decision"] == "unsupported"
    return dict(checked_addition_first=checked, withheld_multiplication_first=unsupported)


def changed_meaning():
    """Post-trial counterexamples to the reader's binding of arithmetic roles."""
    rows = []
    for request in ("Start with 5, add 3, add 3 and double.",
                    "Start with 5 books, add 3 days and double."):
        request += " I'm not sure of the order. What's the total?"
        pending = inspect_order([dict(role="user", content=request)])
        reply = continue_order(pending, "Add 3 first.")
        result = calculate(reply["frame"]) if reply["decision"] == "compute" else response(reply["decision"])
        rows.append(dict(request=request, pending=pending, reply="Add 3 first.", outcome=result))

    # Enumerate every order consistent with the supplied choice on the first request.
    endpoints = set()
    for order in permutations(("add", "add", "double")):
        if order[0] == "add":
            value = 5
            for op in order:
                value = value + 3 if op == "add" else value * 2
            endpoints.add(value)
    return dict(probes=rows, repeated_add_possible_after_reply=sorted(endpoints))


if __name__ == "__main__":
    cases = json.loads((HERE / "prospective.json").read_bytes())["cases"]
    fresh = json.loads((HERE / "order_gap.json").read_bytes())["cases"]
    seed = next(case for case in cases if case["id"] == "c15")
    print(json.dumps({"saved_drafts": saved_trial(cases), "teaching_example": reply_probes(seed),
                      "diagnostic_given_exact_frame": replies_given_exact_frame(fresh),
                      "post_trial_fixed_choices": fixed_choices(fresh),
                      "post_trial_counterexamples": changed_meaning()}, indent=2))
