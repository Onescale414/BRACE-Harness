"""Run a correct PAT proposal and a BRACE-guided retry using a separate PAT checkout."""
import argparse
from pathlib import Path
import sys


SOURCE = b"Start with 1. Add 1, then multiply by 2."


def run_case(label, multiply_lesson):
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

    first = run(label, pat.propose)
    final = first
    checked = ["checked", "checked"]
    observed = [r.verdict for r in first.receipts]
    if observed and observed[-1] == "different-operation":
        rejected = first.receipts[-1]
        _, rejected_operation, _, _ = pat.proposals[rejected.candidate]

        def retry(ticket, view):
            exclude = rejected_operation if view.step == rejected.step else None
            return pat.propose(ticket, view, exclude=exclude)

        final = run("  Retry (same request)", retry)
    expected = checked if multiply_lesson == "multiply" else ["checked", "different-operation"]
    if observed != expected or (first is not final and first.value is not None):
        raise RuntimeError(f"Unexpected initial result: {first.status}, {observed}")
    if [r.verdict for r in final.receipts] != checked or final.value != 4 or final.status != "checked":
        raise RuntimeError(f"Expected a checked 4, got {final.status} with {final.value}")
    if first is not final:
        original = pat.recall("multiply")
        if (original["word"], original["operation"]) != ("multiplying", multiply_lesson):
            raise RuntimeError("The temporary retry changed the original recall")


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


if __name__ == "__main__":
    main()
