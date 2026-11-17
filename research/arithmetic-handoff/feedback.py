"""Replay bounded feedback on the 16 archived conversational requests."""
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from replay import baseline, gate_decision, grade, inspect_messages, model_frame, response


def compare(reading, draft):
    kind = reading["kind"]
    if kind == "unresolved":
        return "unresolved"
    if kind == "compute":
        agrees = model_frame(draft) == reading["frame"]
    else:
        agrees = draft.get("action") == kind
    return "agree" if agrees else "conflict"


def replay_case(messages, draft, record):
    reading = inspect_messages(messages)
    signal = compare(reading, draft)
    if signal != record["reader_signal"] or json.loads(record["original_assistant_text"]) != draft:
        raise ValueError("Archived original proposal or comparison signal differs")
    initial = baseline(draft)
    reviewed = {arm: baseline(json.loads(record[arm])) for arm in ("neutral", "advisory", "signal")}
    blocked = initial
    if signal == "conflict":
        blocked = response("unsupported" if reading["kind"] == "unsupported" else "clarify")
    outcomes = {
        "original": initial,
        "require agreement": gate_decision(reading, draft),
        "neutral reread": reviewed["neutral"],
        "advisory reread": reviewed["advisory"],
        "always signal": reviewed["signal"],
        "block conflict": blocked,
        "advise on conflict": reviewed["signal"] if signal == "conflict" else reviewed["advisory"],
    }
    return signal, outcomes


def main():
    bank = json.loads((HERE / "evidence.json").read_bytes())["cases"]
    observed = json.loads((HERE / "feedback.json").read_bytes())
    records = {row["id"]: row for row in observed["cases"]}
    case_ids = {c["id"] for c in bank}
    if len(bank) != 16 or len(observed["cases"]) != 16 or set(records) != case_ids:
        raise ValueError("Expected one review record per original case")
    counts = Counter(agree=0, conflict=0, unresolved=0)
    totals = {}
    for case in bank:
        signal, outcomes = replay_case(case["messages"], case["raw_draft"], records[case["id"]])
        counts[signal] += 1
        for policy, result in outcomes.items():
            scored = grade(case, result)
            clear = bool(scored["clear"])
            issued = bool(scored["releases"])
            totals.setdefault(policy, Counter()).update(
                clear_answered=int(clear and issued), clear_faithful=scored["faithful_clear"],
                noncompute_releases=int(not clear and issued), wrong_releases=scored["wrong_releases"],
                step_checks=scored["checks"])
    if dict(counts) != observed["expected_signal_counts"] or totals != observed["observed"]:
        raise ValueError("Replayed outcomes differ from the archived counts")
    print(f"Verifier signals: {counts['agree']} agree, {counts['conflict']} conflict, "
          f"{counts['unresolved']} unresolved. Same 16 conversations.")
    print("Policy                Clear answered  Clear correct  Premature/unsupported  All wrong  Checks")
    for policy, row in totals.items():
        print(f"{policy:20}  {row['clear_answered']:7}/8  {row['clear_faithful']:9}/8  "
              f"{row['noncompute_releases']:18}/8  {row['wrong_releases']:9}  {row['step_checks']:6}")
    print("Advise on conflict is a post-result combination of archived replies. No case tested agreement.")


if __name__ == "__main__":
    main()
