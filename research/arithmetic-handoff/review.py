"""Read an archived proposed calculation back to a person before computing."""
import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from gate import inspect_messages
from replay import FIELDS, calculate, model_frame

INTEGER = r"([+-]?[0-9]{1,7})"
CORRECTION = re.compile(rf"set {INTEGER} {INTEGER} {INTEGER}")


def show_frame(frame, write):
    write(f"Start with {frame['start']}. Add the signed change {frame['add']}. "
          f"Then multiply the new total by {frame['multiply']}.")


def run_review(messages, draft, read=input, write=print):
    """Call the arithmetic harness only after a person confirms the displayed frame."""
    for message in messages:
        write(f"{message['role']}: {message['content']}")
    gate = inspect_messages(messages)
    if gate["kind"] != "unresolved":
        write(f"This example reviews unresolved wording. Reader decision: {gate['kind']}.")
        if gate.get("question"):
            write(gate["question"])
        return None
    frame = model_frame(draft)
    if frame is None or any(abs(n) > 1_000_000 for n in frame.values()):
        write("No supported arithmetic proposal to review.")
        return None
    write("Proposed calculation")
    show_frame(frame, write)
    write("If the requested operation or order differs, cancel.")
    write("Type confirm, cancel, or set START CHANGE FACTOR to replace the three integers.")
    try:
        answer = read()
        if isinstance(answer, str) and (match := CORRECTION.fullmatch(answer)):
            frame = dict(zip(FIELDS, map(int, match.groups())))
            if any(abs(n) > 1_000_000 for n in frame.values()):
                write("Correction exceeds the supported integer range. Review closed.")
                return None
            write("Your corrected calculation")
            show_frame(frame, write)
            write("Type confirm to use this correction, or cancel.")
            answer = read()
    except (EOFError, KeyboardInterrupt):
        answer = None
    if answer != "confirm":
        write("Review closed without running the calculation.")
        return None
    result = calculate(frame)
    if result["decision"] == "compute":
        write(f"Checked result: {result['value']} ({result['checks']} arithmetic checks).")
    else:
        write(f"BRACE withheld the result after {result['checks']} arithmetic checks.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="Fresh arithmetic handoff case ID, for example g02")
    args = parser.parse_args()
    cases = json.loads((HERE / "evidence.json").read_bytes())["cases"]
    case = next((c for c in cases if c["id"] == args.case), None)
    if case is None:
        parser.error("Unknown fresh case ID. See evidence.json.")
    run_review(case["messages"], case["raw_draft"])


if __name__ == "__main__":
    main()
