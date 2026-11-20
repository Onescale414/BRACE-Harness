"""Audit a proposed WireMock mapping against a bound G2 snapshot, offline."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from types import ModuleType


ORACLE = Path(__file__).resolve().parent / "vendor" / "tv4c.py"
ORACLE_SHA256 = "828eb4f3fba5d5c6af683e72760b49994f8e89f0840057d31dd7f09c3988e8c6"
MAX_FINDINGS = 64
MAX_MAPPING_BYTES = 8192
UNRESERVED = re.compile(r"[A-Za-z0-9._~-]+")
SCALAR_EDITS = {
    "/request/method", "/request/urlPath", "/response/status", "/response/body",
    "/response/headers/Content-Type", "/response/fixedDelayMilliseconds",
}


class Withheld(ValueError):
    """The input or proposal failed an audit check."""


def load_oracle():
    # Use exactly the source pinned in G2's solver-freeze.json, including under
    # isolated Python. Read it once and avoid reading or writing a bytecode cache.
    raw = ORACLE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORACLE_SHA256:
        raise Withheld("The bundled TV4c checker differs from the G2 pin.")
    module = ModuleType("tv4c")
    exec(compile(raw, str(ORACLE), "exec"), module.__dict__)
    return module


def read_case(path, oracle):
    # Three 8192-byte documents fit even when every byte is JSON-escaped.
    limit = 160 * 1024
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise Withheld("The case file exceeds 160 KiB.")
    try:
        case = json.loads(raw.decode("utf-8"), object_pairs_hook=oracle.pairs,
                          parse_constant=oracle.reject)
    except (ValueError, RecursionError) as exc:
        raise Withheld("The case file must be UTF-8 JSON with unique keys.") from exc
    if not isinstance(case, dict):
        raise Withheld("The case file must contain a JSON object.")
    return case


def document(case, name):
    raw = case.get(name)
    if not isinstance(raw, str):
        raise Withheld(f"The case must supply the {name} as UTF-8 JSON text.")
    try:
        return raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Withheld(f"The {name} contains invalid Unicode.") from exc


def bound_document(case, name):
    raw = document(case, name)
    digest = hashlib.sha256(raw).hexdigest()
    for prefix in ("base", "current"):
        key = f"{prefix}{name.title()}SHA256"
        if case.get(key) != digest:
            raise Withheld(f"The {name} bytes do not match the {key} binding.")
    return raw


def parse_document(oracle, raw, name):
    try:
        return oracle.parse(raw)
    except (ValueError, RecursionError) as exc:
        raise Withheld(f"The {name} is outside the contract's strict JSON format ({exc}).") from exc


def source_contract(oracle, raw):
    try:
        expected, matching = oracle.original(raw)
    except (ValueError, TypeError, RecursionError) as exc:
        if str(exc) == "settings":
            # The oracle groups malformed declarations and unsupported versions.
            # Name the declared version without changing the bound source.
            settings = oracle.parse(raw)["serverSettings"]
            for key, product, version in (("mockServerVersion", "MockServer", "8.0.0"),
                                          ("wireMockVersion", "WireMock", "3.13.2")):
                declared = settings[key]
                if isinstance(declared, str) and declared not in (version, "unknown"):
                    raise Withheld(f"Declared {product} version {json.dumps(declared)} is unsupported. "
                                   f'This contract supports "{version}".') from exc
        raise Withheld(f"The source is outside the literal GET, plain-text contract ({exc}).") from exc
    if matching["pathCase"] == "unknown":
        raise Withheld("Path matching is unknown. Declare both supported versions and "
                       "the effective MockServer matchExactCase setting.")
    if matching["pathCase"] == "different":
        raise Withheld(f'Declared path matching differs. MockServer also matches GET '
                       f'{matching["contrastPath"]}, which the required literal WireMock path excludes.')
    return expected


def visible(value):
    # Compact JSON already escapes controls. Spell every space, including the
    # spaces at the start or end of a body, as a reversible JSON escape.
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).replace(" ", r"\u0020")


def describe_finding(path, expected, proposed):
    pointer = json.dumps(path)[1:-1]
    # TV4c uses "/" for both a root mismatch and a field named "". The
    # required target is an object, so a non-object proposal differs at root.
    if isinstance(proposed, dict):
        keys = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
        # All parents in this target schema are objects. The differ stops at
        # the first absent key or type mismatch, so both parents exist.
        for key in keys[:-1]:
            expected = expected[key]
            proposed = proposed[key]
        key = keys[-1]
        if key not in expected:
            return f"{pointer} unexpected field, observed {visible(proposed[key])}."
        if key not in proposed:
            return f"{pointer} missing field, expected {visible(expected[key])}."
        expected, proposed = expected[key], proposed[key]
    return f"{pointer} expected {visible(expected)}, observed {visible(proposed)}."


def audit(oracle, case):
    source = bound_document(case, "source")
    target = bound_document(case, "target")
    expected = source_contract(oracle, source)
    original = parse_document(oracle, target, "existing target")
    initial_diffs = oracle.diffs(expected, original)
    for row in initial_diffs:
        # TV4c represents a missing leaf with an object. G2 grants only
        # replacement at an existing scalar, so this also rules out additions.
        if row["path"] not in SCALAR_EDITS or isinstance(row["actual"], (dict, list)):
            raise Withheld(f'The existing target needs a structural edit at '
                           f'{json.dumps(row["path"])} outside the six permitted scalar replacements.')

    candidate = document(case, "candidate")
    proposed = parse_document(oracle, candidate, "proposed target")
    findings = oracle.diffs(expected, proposed)
    if len(findings) > MAX_FINDINGS:
        raise Withheld(f"The proposed mapping exceeds the {MAX_FINDINGS}-finding limit (finding-capacity).")
    if findings:
        lines = ["The proposed mapping differs from the mapping required by the source."]
        lines.extend(describe_finding(row["path"], expected, proposed) for row in findings)
        raise Withheld("\n".join(lines))
    if initial_diffs:
        return "The proposed mapping corrects the original mismatches and matches the source."
    if candidate != target:
        raise Withheld("The existing target already matches. A no-op must preserve its original bytes.")
    return "The proposed mapping matches the source and preserves the original target bytes."


def query_check(raw, oracle):
    """Check only the target's literal GET URL and required query equalities."""
    receipt = {"check": "wiremock-url-query-v1", "wiremock_version": "3.13.2",
               "scope": "target URL and query only"}
    if len(raw) > MAX_MAPPING_BYTES:
        return {**receipt, "status": "unsupported", "reason": "Mapping exceeds 8192 bytes."}
    receipt["target_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        # The response may contain ordinary JSON decimals. Its bytes are never regenerated.
        mapping = json.loads(raw.decode("utf-8"), object_pairs_hook=oracle.pairs, parse_constant=oracle.reject)
    except (ValueError, RecursionError):
        return {**receipt, "status": "unsupported", "reason": "Expected UTF-8 JSON with unique keys."}
    try:
        return {**receipt, **query_finding(mapping)}
    except Withheld as exc:
        return {**receipt, "status": "unsupported", "reason": str(exc)}


def token(value):
    return isinstance(value, str) and UNRESERVED.fullmatch(value) is not None


def literal_parts(literal, kind):
    if not isinstance(literal, str):
        raise Withheld("Expected a literal URL string.")
    path, separator, query = literal.partition("?")
    if not path.startswith("/") or (path != "/" and any(
            not token(s) or s in (".", "..") for s in path[1:].split("/"))):
        raise Withheld("Expected an absolute path of unescaped, non-traversing segments.")
    pairs = {}
    if separator:
        if kind == "urlPath":
            raise Withheld("A literal urlPath must contain only a path.")
        for item in query.split("&"):
            key, _, value = item.partition("=")
            if not token(key) or not token(value) or key in pairs:
                raise Withheld("Expected unique, unescaped query names and nonempty literal values.")
            pairs[key] = value
    return path, pairs


def query_finding(mapping):
    request = mapping.get("request") if isinstance(mapping, dict) else None
    if not isinstance(request, dict) or request.get("method") != "GET":
        raise Withheld("Expected one WireMock mapping with an explicit GET request.")
    kind = "url" if "url" in request else "urlPath"
    if set(request) != {"method", kind, "queryParameters"}:
        raise Withheld("Expected one literal url or urlPath and queryParameters as the only GET matchers.")
    literal = request[kind]
    path, fixed = literal_parts(literal, kind)
    matchers = request["queryParameters"]
    if not isinstance(matchers, dict) or not matchers:
        raise Withheld("Expected at least one required query parameter.")
    required = {}
    for key, matcher in matchers.items():
        if (not token(key) or not isinstance(matcher, dict) or set(matcher) != {"equalTo"}
                or not token(matcher["equalTo"])):
            raise Withheld("Expected only literal equalTo matchers with unescaped query names and values.")
        required[key] = matcher["equalTo"]

    # A whole-URL equality admits exactly one request target. Its parameter values
    # therefore decide satisfiability. A path equality leaves those values free.
    conflicts = [name for name, value in required.items() if fixed.get(name) != value] if kind == "url" else []
    if kind == "url" and not conflicts:
        target = literal  # Preserve the query's original order, including extra keys.
    else:
        pairs = {**fixed, **required}
        target = path + "?" + "&".join(f"{name}={value}" for name, value in pairs.items())
    witness = {"method": "GET", "target": target, "url_matches": not conflicts, "query_matches": True}
    if conflicts:
        name = conflicts[0]
        fixed_value = f"fixes {name}={fixed[name]}" if name in fixed else f"omits {name}"
        return {"status": "conflict", "matcher": kind,
                "reason": f"The exact URL {fixed_value}. The query requires {name}={required[name]}.",
                "conflicting_parameters": conflicts, "witness": witness,
                "literal_control": {"method": "GET", "target": literal, "url_matches": True, "query_matches": False}}
    return {"status": "compatible", "matcher": kind,
            "reason": "The witness satisfies the URL and every required query equality.", "witness": witness}


def audit_case(oracle, case):
    try:
        return audit(oracle, case)
    except Withheld as original:
        # Only annotate the same, currently bound submitted bytes. Findings here
        # cannot change the verdict consumed by the repair preview.
        try:
            bound_document(case, "source")
            target = bound_document(case, "target")
            candidate = document(case, "candidate")
        except Withheld:
            raise original
        if target == candidate and len(target) <= MAX_MAPPING_BYTES:
            detail = query_check(target, oracle)
            if detail["status"] == "conflict":
                witness = detail["witness"]["target"]
                raise Withheld(f"{original}\nTarget URL/query conflict. {detail['reason']} "
                               f"GET {witness} satisfies the query but misses the exact URL.") from original
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url-query", action="store_true",
                        help="Read a raw WireMock mapping and show a literal GET request testing its URL and query.")
    parser.add_argument("case", type=Path, help="G2 snapshot, or a raw WireMock mapping with --url-query.")
    args = parser.parse_args()
    try:
        oracle = load_oracle()
        if args.url_query:
            with args.case.open("rb") as stream:
                finding = query_check(stream.read(MAX_MAPPING_BYTES + 1), oracle)
            print(json.dumps(finding, ensure_ascii=True))
            return {"compatible": 0, "conflict": 1, "unsupported": 2}[finding["status"]]
        verdict = audit_case(oracle, read_case(args.case, oracle))
    except (OSError, Withheld) as exc:
        if args.url_query:
            print(json.dumps({"check": "wiremock-url-query-v1", "status": "unsupported",
                              "reason": "Could not read the mapping or verify the audit dependency."}))
            return 2
        print(f"Withheld. {exc}")
        return 1
    print(f"Pass. {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
