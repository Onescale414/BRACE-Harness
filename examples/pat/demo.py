"""Show how PAT proposals fare with a single retry per two-step BRACE request."""
import argparse
import json
from pathlib import Path
import sys


SOURCE = b"Start with 1. Add 1, then multiply by 2."


def verify_run(outcome, expected_steps):
    expected = expected_steps if expected_steps[0] == "checked" else expected_steps[:1]
    observed = [r.verdict for r in outcome.receipts]
    if observed != expected or outcome.terminal is None:
        raise RuntimeError(f"Expected {expected}, got {observed} ({outcome.status})")
    if len(observed) == 2 and outcome.receipts[1].parent != outcome.receipts[0].receipt_id:
        raise RuntimeError("Step two must use the first checked receipt from this run")
    terminal = ("checked", 4, "publish") if observed[-1] == "checked" else (
        f"no-checked-proposal-step-{len(observed)}", None, "withhold"
    )
    if (outcome.status, outcome.value, outcome.terminal.decision) != terminal:
        raise RuntimeError(f"Unexpected terminal decision: {outcome.terminal}")


def run_case(label, multiply_lesson, *, misreport=False, wrong_first=False):
    from adapter import PATProposer
    from harness import run_bound

    lessons = [("adding", "multiply" if wrong_first else "add"),
               ("multiplying", multiply_lesson), ("doubling", "multiply")]
    if wrong_first:
        lessons.append(("sum", "add"))
    pat = PATProposer(lessons)

    def run(title, proposer):
        outcome = run_bound(SOURCE, proposer, checks_per_step=2)
        print(title)
        for receipt in outcome.receipts:
            word, operation, operand, result = pat.proposals[receipt.candidate]
            print(f"  Step {receipt.step + 1}: {word} -> {operation} {operand}, claimed {result}: {receipt.verdict}")
        if outcome.status == "checked":
            print(f"  Released {outcome.value}")
        else:
            print(f"  Withheld ({outcome.status})")
        return outcome

    def ordinary(ticket, view):
        reply = pat.propose(ticket, view)
        if misreport and view.step == 1:
            draft = reply.candidates[0].payload
            return pat.with_result(ticket, view, draft, json.loads(draft)["result"] + 1)
        return reply

    first = run(label, ordinary)
    expected = ["different-operation" if wrong_first else "checked", "checked"]
    if multiply_lesson != "multiply":
        expected[1] = "different-operation"
    elif misreport:
        expected[1] = "wrong-result"
    verify_run(first, expected)
    if first.status == "checked":
        return

    rejected = first.receipts[-1]
    original_choice = pat.proposals[rejected.candidate][:3]
    draft = dict(first.payloads)[rejected.candidate]

    def retry(ticket, view):
        if view.step != rejected.step:
            return ordinary(ticket, view)
        if rejected.verdict == "different-operation":
            return pat.propose(ticket, view, exclude=original_choice[1])
        previous = json.loads(draft)
        result = previous["a"] * view.before + previous["b"]
        return pat.with_result(ticket, view, draft, result)

    final = run("  Retry (same request)", retry)
    expected[rejected.step] = "checked"
    verify_run(final, expected)
    original = pat.recall(("add", "multiply")[rejected.step])
    if (original["word"], original["operation"]) != original_choice[:2]:
        raise RuntimeError("The temporary retry changed the original recall")
    if final.terminal.decision == "withhold":
        print("  Retry spent. No final answer released.")
    if rejected.verdict == "wrong-result":
        repaired = final.receipts[rejected.step].candidate
        before = json.loads(draft)
        after = json.loads(dict(final.payloads)[repaired])
        # A new run and a rechecked first step give the retry fresh run and parent IDs.
        changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
        if changed != {"run", "parent", "result"} or pat.proposals[repaired][:3] != original_choice:
            raise RuntimeError("Expected only the claimed number to change in the calculation")
        print(f'  Claim corrected from {before["result"]} to {after["result"]} with the same lesson, operation and five witnesses.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pat", required=True, type=Path, help="root of the downloaded PAT repository")
    args = parser.parse_args()
    pat = args.pat.resolve()
    entries = ("a_mem/amem/__init__.py", "mirror/mirror/__init__.py", "Elfix/elfix/substrate/features.py")
    if not all((pat / name).is_file() for name in entries):
        parser.error("--pat must point to the full PAT download containing a_mem, mirror and Elfix")
    sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(pat / "a_mem"), str(pat / "mirror")]
    print(SOURCE.decode())
    run_case("Correct lesson", "multiply")
    run_case("Mislabeled lesson", "add")
    run_case("Correct operation, deliberately wrong result", "multiply", misreport=True)
    run_case("Two faults, one retry", "multiply", wrong_first=True, misreport=True)


if __name__ == "__main__":
    main()
