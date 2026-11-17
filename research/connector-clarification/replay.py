"""Run the frozen reply reader and independently replay archived connector previews."""
import hashlib
import json
from pathlib import Path
from types import ModuleType


HERE = Path(__file__).resolve().parent
READER_SHA256 = "72ef61102ef8362a6a5c93837a0db4b5c4bb57e69a1efd11cfdf50f72c301976"
BUDGET = 2
QUESTIONS = {
    frozenset(("list", "search", "details")): ("one_record", "details", "Were you opening one particular record?"),
    frozenset(("status", "export", "changes")): ("download_copy", "export", "Were you trying to download a copy?"),
}


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def require(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def load_reader():
    path = HERE / "reader.py"
    # Git may check out the identical Python source with LF or CRLF.
    source = path.read_bytes().replace(b"\r\n", b"\n")
    require(hashlib.sha256(source).hexdigest() == READER_SHA256, "Frozen reader hash differs")
    module = ModuleType("connector_reply_reader")
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module.read_reply


def catalog(data):
    resources, actions = data["resources"], data["actions"]
    require(len(resources) == len(set(resources)) == len(actions) == len(set(actions)) == 10,
            "Expected ten resources and ten actions")
    by_action = {}
    for group in data["symptom_groups"]:
        for action in group["actions"]:
            require(action not in by_action, "An action belongs to two symptom groups")
            by_action[action] = group["symptom"]
    require(set(by_action) == set(actions), "The symptom groups do not cover the catalog")
    return [(resource, action, by_action[action]) for resource in resources for action in actions]


def choose(routes, resource, symptom, reply, read_reply):
    matches = [(i, action) for i, (r, action, s) in enumerate(routes) if r == resource and s == symptom]
    question, yes_action, prompt = QUESTIONS[frozenset(action for _, action in matches)]
    reading = read_reply(question, reply)
    eligible = [] if reading == "unknown" else [
        i for i, action in matches if (action == yes_action) == (reading == "yes")
    ]
    require(len(eligible) <= BUDGET, "The reply exceeded the check budget")
    return question, prompt, reading, eligible


def translate(source):
    """Expected target for these literal GET fixtures with scalar headers and a fixed delay."""
    request = source["source"]["httpRequest"]
    response = source["source"]["httpResponse"]
    require(response["delay"]["timeUnit"] == "MILLISECONDS" and request["method"] == "GET",
            "Source contract is outside this example")
    headers = response["headers"]
    require(all(isinstance(v, list) and len(v) == 1 for v in headers.values()), "Unsupported source headers")
    return {
        "request": {"method": request["method"], "urlPath": request["path"]},
        "response": {"status": response["statusCode"], "body": response["body"],
                     "fixedDelayMilliseconds": response["delay"]["value"],
                     "headers": {k: v[0] for k, v in headers.items()}},
    }


def replay_check(mapping, path, receipt):
    source, target = mapping["source"], mapping["target"]
    request = target["request"].copy()
    patch = []
    for field, new_value in (("method", "GET"), ("urlPath", path)):
        if request[field] != new_value:
            patch.append({"op": "replace", "path": "/request/" + field, "old": request[field], "value": new_value})
            request[field] = new_value
    candidate = dict(target, request=request)
    accepted = candidate == translate(source)
    candidate_hash = digest(candidate)
    fields = {
        "audits": 1, "patch": patch, "patch_sha256": digest(patch),
        "source_sha256": digest(source), "target_sha256": digest(target), "candidate_sha256": candidate_hash,
        "checked": accepted, "status": "checked" if accepted else "withheld",
        "output_sha256": candidate_hash if accepted else None,
    }
    require(all(receipt[k] == v for k, v in fields.items()), "Archived receipt disagrees with the reconstructed patch")
    return accepted


def replay(routes, mappings, case, read_reply):
    record = case["record"]
    require(digest(record) == case["record_sha256"], "Archived record hash differs")
    mapping = mappings[case["mapping"]]
    question, prompt, reading, eligible = choose(routes, mapping["resource"], mapping["symptom"], case["reply"], read_reply)
    released = None
    spent = 0
    path = None
    for i in eligible:
        resource, action, _ = routes[i]
        path = f"/v2/{resource}/{action}/{mapping['suffix']}"
        require(spent < len(record["checks"]), "Missing archived check")
        passed = replay_check(mapping, path, record["checks"][spent])
        spent += 1
        if passed:
            released = i
            break
    state = "waiting" if reading == "unknown" else ("checked" if released is not None else "withheld")
    observed = {
        "id": case["mapping"], "reply": case["reply"], "question": question, "resolution": reading,
        "eligible": eligible, "state": state, "charged": spent, "remaining": BUDGET - spent, "released": released,
    }
    require(len(record["checks"]) == spent and all(record[k] == v for k, v in observed.items()),
            f"{case['label']}: recorded conversation and replay disagree")

    expected = case["expected"]
    require(expected in {"yes", "no", "unknown"}, "Unknown intended reading")
    outcome = "MATCH" if expected == reading else "READER FAILURE"
    print(f"\n{case['label']} [{outcome}]")
    print(f"  {prompt}\n  Reply: {json.dumps(case['reply'])}")
    print(f"  Expected {expected}. Reader returned {reading}. {spent}/{BUDGET} checks used.")
    if released is not None:
        print(f"  Checked preview: GET {path}")
    elif state == "waiting":
        print("  Waiting for clarification. Both checks are available.")
    else:
        print("  All eligible repairs were withheld.")


def main():
    read_reply = load_reader()
    data = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    routes = catalog(data)
    require(data["cases"], "No conversations to replay")
    print(f"{len(routes)} possible repairs, {BUDGET} checks per conversation. Replaying saved BRACE receipts.")
    for case in data["cases"]:
        replay(routes, data["mappings"], case, read_reply)
    print("\nAll recorded outcomes reproduced.")


if __name__ == "__main__":
    main()
