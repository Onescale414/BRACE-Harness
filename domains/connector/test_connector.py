"""Offline connector tests using only this directory and its bundled fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
sys.path.insert(0, str(ROOT))
import connector_selection as selection
import wiremock_preview as preview
sys.path.pop(0)

CASES = json.loads((FIXTURES / "cases.json").read_bytes())["cases"]
LABELS = {row["id"]: row for row in json.loads((FIXTURES / "labels.json").read_bytes())["labels"]}


def dump(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def bind_bundle(case):
    body = {name: case[name] for name in ("requirements", "candidates", "target",
                                        "baseTargetSHA256", "currentTargetSHA256")}
    digest = sha(dump(body).encode())
    case["baseBundleSHA256"] = case["currentBundleSHA256"] = digest
    return case


def bind(case):
    for option in case["candidates"]:
        digest = sha(option["source"].encode())
        option["baseSourceSHA256"] = option["currentSourceSHA256"] = digest
    digest = sha(case["target"].encode())
    case["baseTargetSHA256"] = case["currentTargetSHA256"] = digest
    return bind_bundle(case)


def change_source(case, index, **changes):
    source = json.loads(case["candidates"][index]["source"])
    for name, value in changes.items():
        if name == "path":
            source["source"]["httpRequest"]["path"] = value
        elif name == "method":
            source["source"]["httpRequest"]["method"] = value
        elif name == "settings":
            source["serverSettings"].update(value)
        else:
            source["source"]["httpResponse"][name] = value
    case["candidates"][index]["source"] = dump(source)
    return bind(case)


class ConnectorSelectionTests(unittest.TestCase):
    def setUp(self):
        self.case = copy.deepcopy(CASES[0])
        self.network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network dispatch forbidden"))
        self.process = patch.object(subprocess, "Popen", side_effect=AssertionError("Model subprocess forbidden"))
        self.network.start()
        self.process.start()

    def tearDown(self):
        self.process.stop()
        self.network.stop()

    def assert_withheld(self, case, proposal=None):
        before = copy.deepcopy(case)
        with patch.object(preview, "checked_preview", side_effect=AssertionError("Builder reached before admission")) as builder:
            if proposal is None:
                result = selection.checked_choice(case)
                self.assertEqual(result["status"], "withheld")
                for key in ("patch", "selectedId", "proposedTarget"):
                    self.assertNotIn(key, result)
            else:
                with self.assertRaises(preview.gate.Withheld):
                    selection.check_selection(case, proposal)
            builder.assert_not_called()
        self.assertEqual(case, before)

    def test_modules_are_local(self):
        self.assertEqual(Path(selection.__file__).resolve(), ROOT / "connector_selection.py")
        self.assertEqual(Path(preview.__file__).resolve(), ROOT / "wiremock_preview.py")

    def test_all_frozen_labels_and_input_immutability(self):
        expected_ids = ["q%02d" % number for number in range(1, 19)]
        self.assertEqual([case["id"] for case in CASES], expected_ids)
        self.assertEqual(list(LABELS), expected_ids)
        statuses = {"checked": 0, "checked-no-match": 0, "withheld": 0}
        for case in CASES:
            with self.subTest(case=case["id"]):
                before = copy.deepcopy(case)
                label = LABELS[case["id"]]
                if label["expectedStatus"] == "withheld":
                    self.assert_withheld(case)
                    statuses["withheld"] += 1
                    continue
                result = selection.checked_choice(case)
                self.assertEqual(result["status"], label["expectedStatus"])
                statuses[result["status"]] += 1
                self.assertEqual(case, before)
                if result["status"] == "checked":
                    self.assertEqual(result["selectedId"], label["expectedWinnerId"])
                    self.assertEqual(json.loads(result["proposedTarget"]), json.loads(label["expectedTarget"]))
                    self.assertEqual(result["patch"], label["expectedPatch"])
                    if not result["patch"]:
                        self.assertEqual(result["proposedTarget"].encode(), case["target"].encode())
                else:
                    self.assertIsNone(result["selectedId"])
                    self.assertNotIn("proposedTarget", result)
                    self.assertEqual(result["patch"], [])
        self.assertEqual(statuses, {"checked": 14, "checked-no-match": 2, "withheld": 2})

    def test_wrong_selector_and_invalid_proposals_never_build(self):
        proposals = [None, [], {}, {"candidate": True}, {"candidate": 0},
                     {"candidate": []}, {"candidate": "C0"}, {"candidate": "c4"},
                     {"winner": "c0"}, {"candidate": "c0", "edits": []},
                     {"candidate": "c1"}, {"candidate": "c2"},
                     {"candidate": "c3"}, {"candidate": "none"}]
        for proposal in proposals:
            with self.subTest(proposal=proposal):
                with patch.object(selection, "choose_direct", return_value=proposal):
                    self.assert_withheld(self.case)

    def test_wrong_source_handoff_is_refused_before_builder(self):
        # A valid conversion of c1 is still the wrong selected source. Inject the
        # handoff fault after the independent gate, leaving its reads untouched.
        original_gate = selection.check_selection
        original_bound = selection.bound_case
        for fault in ("source", "target"):
            admitted = False

            def admit(*args, **kwargs):
                nonlocal admitted
                receipt = original_gate(*args, **kwargs)
                admitted = True
                return receipt

            def wrong_handoff(case, candidate):
                if admitted and fault == "source":
                    return original_bound(case, case["candidates"][1])
                handoff = original_bound(case, candidate)
                if admitted:
                    target = json.loads(handoff["target"])
                    target["response"]["body"] = "Other bound target snapshot"
                    handoff["target"] = dump(target)
                    digest = sha(handoff["target"].encode())
                    handoff["baseTargetSHA256"] = handoff["currentTargetSHA256"] = digest
                return handoff

            with self.subTest(fault=fault), patch.object(selection, "check_selection", side_effect=admit), \
                    patch.object(selection, "bound_case", side_effect=wrong_handoff), \
                    patch.object(preview, "checked_preview", wraps=preview.checked_preview) as builder:
                result = selection.checked_choice(self.case)
                self.assertEqual(result["status"], "withheld")
                builder.assert_not_called()
                self.assertNotIn("proposedTarget", result)

    def test_exact_case_prefix_units_path_and_id_ties(self):
        public = selection.prepare(self.case)
        self.assertEqual([option["delayMs"] for option in public["options"]], [1873, 1, 2000, 0])
        self.assertEqual(selection.choose_direct(public), {"candidate": "c0"})
        change_source(self.case, 0, path="/Aster/z", delay={"timeUnit": "MILLISECONDS", "value": 2000})
        change_source(self.case, 2, path="/Aster/A", delay={"timeUnit": "SECONDS", "value": 2})
        self.assert_withheld(self.case, {"candidate": "c0"})
        self.assertEqual(selection.checked_choice(self.case)["selectedId"], "c2")
        change_source(self.case, 0, path="/Aster/A")
        self.assert_withheld(self.case, {"candidate": "c2"})
        self.assertEqual(selection.checked_choice(self.case)["selectedId"], "c0")
        self.case["requirements"]["firstSegment"] = "Absent"
        bind(self.case)
        with patch.object(preview, "checked_preview", side_effect=AssertionError("No-match must not build")):
            result = selection.checked_choice(self.case)
        self.assertEqual(result["status"], "checked-no-match")

    def test_every_binding_and_catalog_shape_fails_closed(self):
        invalid = []
        for name in ("baseBundleSHA256", "currentBundleSHA256", "baseTargetSHA256", "currentTargetSHA256"):
            case = copy.deepcopy(self.case)
            case[name] = "0" * 64
            invalid.append(bind_bundle(case) if "Target" in name else case)
        for index in range(4):
            for name in ("baseSourceSHA256", "currentSourceSHA256"):
                case = copy.deepcopy(self.case)
                case["candidates"][index][name] = "0" * 64
                invalid.append(bind_bundle(case))
        for field, value in (("id", "x" * 65), ("id", True), ("candidates", []),
                             ("candidates", self.case["candidates"][:3]),
                             ("candidates", self.case["candidates"] + [self.case["candidates"][0]])):
            case = copy.deepcopy(self.case)
            case[field] = copy.deepcopy(value)
            invalid.append(bind(case))
        for transform in (lambda c: c["candidates"].reverse(),
                          lambda c: c["candidates"][1].update(id="c0"),
                          lambda c: c["candidates"][0].update(extra="unknown"),
                          lambda c: c["requirements"].update(policy="fastest-service"),
                          lambda c: c["requirements"].update(firstSegment="Aster/x"),
                          lambda c: c["requirements"].update(firstSegment=""),
                          lambda c: c["requirements"].update(extra="unknown"),
                          lambda c: c.update(extra="unknown")):
            case = copy.deepcopy(self.case)
            transform(case)
            invalid.append(bind(case))
        for case in invalid:
            with self.subTest(case=case):
                self.assert_withheld(case)

    def test_document_and_scalar_caps(self):
        invalid = []
        for changes in ({"body": "X" * 129}, {"path": "/" + "a" * 33},
                        {"path": "/a/b/c/d/e/f/g/h/i"}, {"method": "POST"},
                        {"delay": {"timeUnit": "SECONDS", "value": 61}},
                        {"delay": {"timeUnit": "MILLISECONDS", "value": 60001}},
                        {"delay": {"timeUnit": "MILLISECONDS", "value": True}},
                        {"settings": {"wireMockVersion": "unknown"}}):
            invalid.append(change_source(copy.deepcopy(self.case), 3, **changes))
        for field in ("target", "source"):
            case = copy.deepcopy(self.case)
            holder = case if field == "target" else case["candidates"][0]
            holder[field] += " " * 8193
            invalid.append(bind(case))
        for raw in ('{"request":{},"request":{}}', '{"request":NaN}', '[' * 20 + '0' + ']' * 20):
            case = copy.deepcopy(self.case)
            case["target"] = raw
            invalid.append(bind(case))
        for case in invalid:
            with self.subTest(case=case):
                self.assert_withheld(case)

    def test_corrupted_builder_body_path_and_delay_are_audited(self):
        original_apply = preview._apply_patch
        for location, wrong in ((["response", "body"], "corrupted body"),
                                (["request", "urlPath"], "/Aster/incorrect"),
                                (["response", "fixedDelayMilliseconds"], 1874)):
            def corrupt(original, target, patch_value, location=location, wrong=wrong):
                result = json.loads(original_apply(original, target, patch_value))
                result[location[0]][location[1]] = wrong
                return dump(result).encode()
            with self.subTest(location=location), patch.object(preview, "_apply_patch", side_effect=corrupt), \
                    patch.object(preview.gate, "audit", wraps=preview.gate.audit) as audit:
                result = selection.checked_choice(self.case)
                self.assertEqual(result["status"], "withheld")
                self.assertNotIn("proposedTarget", result)
                audit.assert_called_once()

    def test_noop_bytes_and_noop_reformat_refusal(self):
        cases = [case for case in CASES if LABELS[case["id"]]["expectedStatus"] == "checked"
                 and not LABELS[case["id"]]["expectedPatch"]]
        self.assertEqual(len(cases), 2)
        for case in cases:
            result = selection.checked_choice(case)
            self.assertEqual(result["proposedTarget"].encode(), case["target"].encode())
            with patch.object(preview, "_apply_patch", return_value=dump(json.loads(case["target"])).encode()):
                result = selection.checked_choice(case)
                self.assertEqual(result["status"], "withheld")
                self.assertNotIn("proposedTarget", result)

    def test_hidden_body_target_and_same_case_binding(self):
        original_public = selection.prepare(self.case)
        changed = copy.deepcopy(self.case)
        target = json.loads(changed["target"])
        target["response"]["body"] = "Hidden target value"
        changed["target"] = dump(target)
        change_source(changed, 0, body="Hidden source value")
        self.assertEqual(selection.prepare(changed), original_public)
        result = selection.checked_choice(changed)
        self.assertEqual(json.loads(result["proposedTarget"])["response"]["body"], "Hidden source value")
        self.assertIn({"op": "replace", "path": "/response/body", "old": "Hidden target value",
                       "value": "Hidden source value"}, result["patch"])
        changed["target"] += " "
        self.assert_withheld(changed)

    def test_selector_cannot_rewrite_checked_public_data(self):
        def malicious(public):
            public["requirements"]["firstSegment"] = "aster"
            public["options"][1]["delayMs"] = 0
            return {"candidate": "c1"}
        with patch.object(selection, "choose_direct", side_effect=malicious):
            self.assert_withheld(self.case)

    def test_expired_deadline_releases_no_preview(self):
        with patch.object(selection, "choose_direct", side_effect=AssertionError("Expired request selected")), \
                patch.object(preview, "checked_preview", side_effect=AssertionError("Expired request built")):
            result = selection.checked_choice(self.case, deadline=0)
        self.assertEqual(result["status"], "withheld")
        self.assertEqual(result["reason"], "deadline")
        self.assertEqual(result["modelCalls"], 0)
        self.assertNotIn("proposedTarget", result)

    def test_repeated_calls_are_direct_without_retained_state_or_dispatch(self):
        expected = selection.checked_choice(self.case)
        with patch.object(selection, "choose_direct", wraps=selection.choose_direct) as selector:
            for _ in range(8):
                self.assertEqual(selection.checked_choice(self.case), expected)
            self.assertEqual(selector.call_count, 8)


class ConnectorCLITests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="connector-tests-")
        self.addCleanup(self.scratch.cleanup)
        self.directory = Path(self.scratch.name)

    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(ROOT / "cli.py"), *map(str, args)],
            cwd=self.directory, capture_output=True, text=True,
            encoding="utf-8", timeout=15, check=False)

    def write(self, raw, name="case.json"):
        path = self.directory / name
        path.write_bytes(raw)
        return path

    def assert_result(self, completed, case, label):
        status = label["expectedStatus"]
        self.assertEqual(completed.returncode, 1 if status == "withheld" else 0,
                         completed.stderr)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], status)
        self.assertEqual(result["modelCalls"], 0)
        self.assertIs(result["previewOnly"], True)
        if status == "withheld":
            self.assertEqual(result["decision"], "withhold")
            for key in ("selectedId", "patch", "proposedTarget"):
                self.assertNotIn(key, result)
        else:
            self.assertEqual(result["decision"], "publish")
            self.assertEqual(result["selectedId"], label["expectedWinnerId"])
            if status == "checked":
                self.assertEqual(json.loads(result["proposedTarget"]), json.loads(label["expectedTarget"]))
                self.assertEqual(result["patch"], label["expectedPatch"])
                if not result["patch"]:
                    self.assertEqual(result["proposedTarget"].encode("utf-8"), case["target"].encode("utf-8"))
            else:
                self.assertEqual(result["patch"], [])
                self.assertNotIn("proposedTarget", result)
        return result

    def assert_refused(self, completed):
        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "withheld")
        self.assertEqual(result["decision"], "withhold")
        self.assertEqual(result["modelCalls"], 0)
        self.assertIs(result["previewOnly"], True)
        for key in ("selectedId", "patch", "proposedTarget"):
            self.assertNotIn(key, result)

    def test_cli_all_18_cases_from_an_unrelated_directory(self):
        counts = {"checked": 0, "checked-no-match": 0, "withheld": 0}
        for case in CASES:
            with self.subTest(case=case["id"]):
                raw = dump(case).encode("utf-8")
                path = self.write(raw)
                result = self.assert_result(self.invoke(path), case, LABELS[case["id"]])
                counts[result["status"]] += 1
                self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(counts, {"checked": 14, "checked-no-match": 2, "withheld": 2})
        self.assertEqual([path.name for path in self.directory.iterdir()], ["case.json"])

    def test_cli_malformed_and_duplicate_keys(self):
        valid = dump(CASES[0])
        invalid = [b"{", b"[]", b'{"value":NaN}', b"\xff", b"\x00",
                   (valid[:-1] + ',"id":"q01"}').encode("utf-8"),
                   valid.replace('"id":"c0"', '"id":"c0","id":"c0"', 1).encode("utf-8")]
        for raw in invalid:
            with self.subTest(raw=raw[:80]):
                self.assert_refused(self.invoke(self.write(raw)))

    def test_cli_oversize_and_missing_file(self):
        raw = dump(CASES[0]).encode("utf-8")
        raw += b" " * (selection.MAX_CASE_BYTES + 1 - len(raw))
        path = self.write(raw)
        self.assert_refused(self.invoke(path))
        self.assertEqual(path.read_bytes(), raw)
        missing = self.directory / "missing.json"
        self.assert_refused(self.invoke(missing))
        self.assertFalse(missing.exists())

    def test_cli_rejects_unknown_flags_and_model_options(self):
        path = self.write(dump(CASES[0]).encode("utf-8"))
        for flags in (("--unknown",), ("--qwen",), ("--model", "unused"), ("--backend", "qwen")):
            with self.subTest(flags=flags):
                completed = self.invoke(path, *flags)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                self.assertIn("unrecognized arguments", completed.stderr)
        missing_argument = self.invoke()
        self.assertEqual(missing_argument.returncode, 2)
        self.assertEqual(missing_argument.stdout, "")

    def test_cli_example_is_repeatable_and_read_only(self):
        example = FIXTURES / "example.json"
        raw = example.read_bytes()
        case = json.loads(raw)
        first = self.invoke(example)
        second = self.invoke(example)
        self.assert_result(first, case, LABELS[case["id"]])
        self.assert_result(second, case, LABELS[case["id"]])
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(example.read_bytes(), raw)
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
