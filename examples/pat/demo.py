"""Show a checked PAT proposal and one retry for each of two BRACE rejection reasons."""
import argparse
import json
from pathlib import Path
import sys


SOURCE = b"Start with 1. Add 1, then multiply by 2."


def run_case(label, multiply_lesson, *, misreport=False):
    from adapter import PATProposer
    from harness import run_bound

    pat = PATProposer([("adding", "add"), ("multiplying", multiply_lesson), ("doubling", "multiply")])

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

    def initial(ticket, view):
        reply = pat.propose(ticket, view)
        if misreport and view.step == 1:
            draft = reply.candidates[0].payload
            return pat.with_result(ticket, view, draft, json.loads(draft)["result"] + 1)
        return reply

    first = run(label, initial)
    final = first
    checked = ["checked", "checked"]
    observed = [r.verdict for r in first.receipts]
    if observed and observed[-1] in ("different-operation", "wrong-result"):
        rejected = first.receipts[-1]
        original_choice = pat.proposals[rejected.candidate][:3]
        draft = dict(first.payloads)[rejected.candidate]

        def retry(ticket, view):
            if view.step != rejected.step:
                return pat.propose(ticket, view)
            if rejected.verdict == "different-operation":
                return pat.propose(ticket, view, exclude=original_choice[1])
            previous = json.loads(draft)
            result = previous["a"] * view.before + previous["b"]
            return pat.with_result(ticket, view, draft, result)

        final = run("  Retry (same request)", retry)
    expected = checked if multiply_lesson == "multiply" else ["checked", "different-operation"]
    if misreport:
        expected = ["checked", "wrong-result"]
    if observed != expected or (first is not final and first.value is not None):
        raise RuntimeError(f"Unexpected initial result: {first.status}, {observed}")
    if [r.verdict for r in final.receipts] != checked or final.value != 4 or final.status != "checked":
        raise RuntimeError(f"Expected a checked 4, got {final.status} with {final.value}")
    if first is not final:
        original = pat.recall("multiply")
        if (original["word"], original["operation"]) != ("multiplying", multiply_lesson):
            raise RuntimeError("The temporary retry changed the original recall")
    if misreport:
        repaired = final.receipts[-1].candidate
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


if __name__ == "__main__":
    main()
