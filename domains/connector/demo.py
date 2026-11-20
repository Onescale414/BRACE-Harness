"""Run all bundled connector cases and verify their complete expected results."""
import copy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import connector_selection as selection
sys.path.pop(0)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    fixtures = ROOT / "fixtures"
    cases = json.loads((fixtures / "cases.json").read_bytes())["cases"]
    labels = json.loads((fixtures / "labels.json").read_bytes())["labels"]
    expected_ids = ["q%02d" % number for number in range(1, 19)]
    require([case["id"] for case in cases] == expected_ids, "Unexpected case IDs")
    require([label["id"] for label in labels] == expected_ids, "Unexpected label IDs")
    counts = {"checked": 0, "checked-no-match": 0, "withheld": 0}
    outcomes = []
    noops = 0
    for case, label in zip(cases, labels):
        before = copy.deepcopy(case)
        result = selection.checked_choice(case)
        case_id = case["id"]
        require(case == before, case_id + ": input changed")
        require(result["status"] == label["expectedStatus"], case_id + ": status mismatch")
        require(result["modelCalls"] == 0 and result["previewOnly"] is True,
                case_id + ": unexpected dispatch or execution")
        status = result["status"]
        counts[status] += 1
        if status == "checked":
            require(result["decision"] == "publish", case_id + ": decision mismatch")
            require(result["selectedId"] == label["expectedWinnerId"], case_id + ": winner mismatch")
            require(json.loads(result["proposedTarget"]) == json.loads(label["expectedTarget"]),
                    case_id + ": complete target mismatch")
            require(result["patch"] == label["expectedPatch"], case_id + ": patch mismatch")
            if not result["patch"]:
                require(result["proposedTarget"].encode("utf-8") == case["target"].encode("utf-8"),
                        case_id + ": no-op changed target bytes")
                require(result["proposedTarget"] == label["expectedTarget"],
                        case_id + ": no-op differs from expected bytes")
                noops += 1
        elif status == "checked-no-match":
            require(result["decision"] == "publish", case_id + ": decision mismatch")
            require(result["selectedId"] is None and result["patch"] == [],
                    case_id + ": no-match released a choice or patch")
            require("proposedTarget" not in result, case_id + ": no-match released a target")
        else:
            require(result["decision"] == "withhold", case_id + ": decision mismatch")
            require(all(key not in result for key in ("selectedId", "patch", "proposedTarget")),
                    case_id + ": refusal released a partial result")
        outcomes.append({"id": case_id, "status": status, "selectedId": result.get("selectedId")})
    require(counts == {"checked": 14, "checked-no-match": 2, "withheld": 2},
            "Unexpected outcome counts")
    require(noops == 2, "Unexpected no-op count")
    print(json.dumps({"profile": selection.PROFILE, "cases": len(cases),
                      "counts": counts, "byteExactNoops": noops,
                      "modelCalls": 0, "outcomes": outcomes}, indent=2))


if __name__ == "__main__":
    main()
