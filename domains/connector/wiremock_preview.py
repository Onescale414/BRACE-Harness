"""Preview checked replacements for a bound MockServer to WireMock mapping."""

import argparse
import copy
import json
import sys
from pathlib import Path


# Isolated Python omits the script directory. Load the standalone audit beside us.
sys.path.insert(0, str(Path(__file__).resolve().parent))
previous_bytecode_setting = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    import wiremock_audit as gate
finally:
    sys.dont_write_bytecode = previous_bytecode_setting
    sys.path.pop(0)


FIELD_NAMES = {
    "/request/method": "request method",
    "/request/urlPath": "URL path",
    "/response/status": "response status",
    "/response/body": "body",
    "/response/headers/Content-Type": "Content-Type",
    "/response/fixedDelayMilliseconds": "delay in milliseconds",
}


def _replacements(oracle, expected, original):
    patch = []
    for difference in oracle.diffs(expected, original):
        path = difference["path"]
        old = difference["actual"]
        # TV4c represents absence with an object. Missing keys, actual objects
        # and arrays all require a structural edit rather than a scalar replace.
        if path not in gate.SCALAR_EDITS or isinstance(old, (dict, list)):
            raise gate.Withheld(f"The existing target needs a structural edit at {json.dumps(path)}.")
        patch.append({"op": "replace", "path": path, "old": old, "value": difference["expected"]})
    return sorted(patch, key=lambda edit: edit["path"])


def _validate_patch(patch, original):
    if type(patch) is not list:
        raise gate.Withheld("The generated patch must be a list of replace operations.")
    prior_values = {}
    for index, edit in enumerate(patch, start=1):
        if type(edit) is not dict or edit.keys() != {"op", "path", "old", "value"}:
            raise gate.Withheld(f"Edit {index} must be an object with exactly op, path, old and value.")
        if edit["op"] != "replace":
            raise gate.Withheld(f"Edit {index} must use the replace operation.")
        path = edit["path"]
        if type(path) is not str or path not in gate.SCALAR_EDITS:
            raise gate.Withheld(f"Edit {index} must name a permitted scalar path.")
        node = original
        for key in path[1:].split("/"):
            if type(node) is not dict or key not in node:
                raise gate.Withheld(f"Edit {index} cannot resolve {path} in the bound target at key {json.dumps(key)}.")
            node = node[key]
        if isinstance(node, (dict, list)):
            raise gate.Withheld(f"Edit {index} destination {path} must be a scalar in the bound target.")
        for field in ("old", "value"):
            value = edit[field]
            if type(value) not in (str, int, bool, type(None)):
                raise gate.Withheld(f"Edit {index} must use a scalar {field} admitted by the contract.")
            if type(value) is int and not 0 <= value <= 99_999:
                raise gate.Withheld(f"Edit {index} has an integer {field} outside the TV4c range.")

        # A repeated destination would contain the preceding replacement.
        current = prior_values.get(path, node)
        old = edit["old"]
        if type(old) is not type(current) or old != current:
            raise gate.Withheld(f"Edit {index} at {path} declares old {gate.visible(old)} "
                                f"but would replace {gate.visible(current)}.")
        prior_values[path] = edit["value"]


def _apply_patch(original, target_bytes, patch):
    if not patch:
        return target_bytes
    scratch = copy.deepcopy(original)
    for edit in patch:
        # The six authorized pointers contain only literal object keys.
        *parents, key = edit["path"][1:].split("/")
        node = scratch
        for parent in parents:
            node = node[parent]
        node[key] = edit["value"]
    return json.dumps(scratch, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _patch_matches_targets(patch, original, audited):
    # The whole-target audit has established that every permitted leaf exists
    # in both trees. Read them in the required patch order.
    changes = []
    for path in sorted(gate.SCALAR_EDITS):
        old, value = original, audited
        for key in path[1:].split("/"):
            old, value = old[key], value[key]
        if type(old) is not type(value) or old != value:
            changes.append((path, old, value))

    if not isinstance(patch, list) or len(patch) != len(changes):
        return False
    for edit, (path, old, value) in zip(patch, changes):
        if edit != {"op": "replace", "path": path, "old": old, "value": value}:
            return False
        # Dict equality alone accepts False for 0 and True for 1.
        if type(edit["old"]) is not type(old) or type(edit["value"]) is not type(value):
            return False
    return True


def checked_preview(oracle, case):
    source = gate.bound_document(case, "source")
    target = gate.bound_document(case, "target")
    expected = gate.source_contract(oracle, source)
    original = gate.parse_document(oracle, target, "existing target")
    # Keep the bound tree used for destination checks separate from the proposer.
    patch = _replacements(oracle, expected, copy.deepcopy(original))
    _validate_patch(patch, original)
    candidate_bytes = _apply_patch(original, target, patch)
    candidate = candidate_bytes.decode("utf-8")

    # The gate rechecks the original snapshot and the complete scratch result.
    # The exact string it accepts is the one published in the preview.
    verdict = gate.audit(oracle, {**case, "candidate": candidate})
    checked = gate.parse_document(oracle, candidate_bytes, "audited target")
    # Compare against the bound bytes, independent of the proposer's mutable tree.
    bound_original = gate.parse_document(oracle, target, "existing target")
    if not _patch_matches_targets(patch, bound_original, checked):
        raise gate.Withheld("The patch differs from the changes in the audited target.")

    explanation = verdict
    if patch:
        changes = [f'the {FIELD_NAMES[edit["path"]]} to {json.dumps(edit["value"])}' for edit in patch]
        last = changes.pop()
        description = ", ".join(changes) + " and " + last if changes else last
        explanation = f"Set {description}."
    return {"status": "checked", "patch": patch, "proposedTarget": candidate, "explanation": explanation}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="G2 source, existing target and four binding hashes.")
    args = parser.parse_args(argv)
    try:
        oracle = gate.load_oracle()
        result = checked_preview(oracle, gate.read_case(args.snapshot, oracle))
    except (OSError, UnicodeError, gate.Withheld) as exc:
        print(json.dumps({"status": "withheld", "reason": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
