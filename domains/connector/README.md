# Checked connector selection and repair previews

Choose among four supplied MockServer mappings under an explicit rule, then produce
an independently checked WireMock repair preview. Everything runs offline with
Python 3.12 or later and the standard library. There are no model calls or writes
to the supplied mapping.

## Try it

From the repository root:

```sh
python -I -S -B domains/connector/cli.py domains/connector/fixtures/example.json
python -I -S -B domains/connector/demo.py
python -I -S -B domains/connector/test_connector.py
```

The first command selects `c0` and proposes replacing `SEARCH` with `GET`. It
prints the typed old/new patch and the complete checked `proposedTarget`. The
example is synthetic: its required route family is `Aster`; the eligible 1,873 ms
mapping beats the 2,000 ms mapping, while faster mappings for other families do
not qualify. `previewOnly:true` means nothing was applied.

The demo checks all 18 saved cases: 12 repairs, two byte-preserving no-ops, two
verified no-matches and two withheld inputs. It verifies selected IDs, complete
targets and minimal patches, not only outcome counts. No model is needed to
reproduce these results.

## What is verified

The default is direct selection and construction:

1. Validate every source, the existing target and their supplied byte bindings.
2. Select the exact first path segment requested, then the smallest configured
   delay in milliseconds. Break ties by complete ASCII path, then candidate ID.
3. Independently recheck the choice against all eligible alternatives.
4. Bind that selection to the exact source and target passed to the converter.
5. Build a minimal replacement patch and audit the entire proposed mapping.

A correct conversion can still be the wrong choice. The selection gate handles
that distinction. The handoff check also rejects an adapter that substitutes a
different valid source or target after selection. The builder and final audit
share trusted parsing/contract code; this is not an independently developed formal
proof system.

This can serve as a preflight step for a migration tool or a CI review of this
specific mapping subset. The calling application must obtain the source/target
snapshots, own the selection requirement and decide whether to apply a preview.
There is no natural-language intent reader in this profile.

## Supported contract and limits

- Exactly four sources, in order `c0`, `c1`, `c2`, `c3`. **All four must be valid**,
  even an option that would lose. No eligible source produces a checked no-match.
- Policy `minimum-delay-then-path`. Required first segment: 1–32 ASCII letters,
  digits, underscores or hyphens. Matching is case sensitive and segment exact.
- Declared MockServer `8.0.0` and WireMock `3.13.2` semantics; literal `GET`, status
  `200`, `Content-Type: text/plain; charset=utf-8`. This is a local subset checker,
  not a claim of compatibility with arbitrary server versions or configurations.
- `serverSettings.mockServerMatchExactCase` is required. `"true"` supplies exact
  case matching; `"false"` is compatible only for paths containing no letters.
  Unknown or incompatible case semantics withhold the preview.
- Paths: `/` or 1–8 nonempty segments of 1–32 ASCII letters/digits/underscore/hyphen,
  at most 128 characters total. No queries, regex paths or URL decoding.
- Bodies: at most 128 printable ASCII characters, copied exactly. Delays: integer
  seconds 0–60 or milliseconds 0–60,000. Seconds are multiplied by 1,000 by the host.
- At most six replacements of **existing scalar leaves**: request method/path;
  response status/body/content type/delay. No additions, deletions or structural edits.
- Case transport and detached canonical envelope: 160 KiB each. Each inner JSON
  document: 8,192 bytes, depth at most 8 and at most 256 nodes. Unique literal keys;
  canonical unsigned integer tokens 0–99,999; no floats or non-JSON numbers.
- One direct selection/check admission, within the studied two-admission ceiling.
  A 60-second deadline is checked before work and before returning a result. It
  prevents late publication when checked; it is **not a preemptive process timeout**.

Configured delay is a mapping value, not measured service latency. No HTTP request
is sent. Supported version declarations and source data are supplied by the caller.

## Case format and bindings

Copy [the complete example](fixtures/example.json) as the format reference. The
outer object has exactly `id`, `requirements`, `candidates`, `target`,
`baseTargetSHA256`, `currentTargetSHA256`, `baseBundleSHA256`, `currentBundleSHA256`.
`id` is at most 64 characters. Requirements contain exactly `firstSegment` and
`policy`. Each candidate contains exactly `id`, `source`, `baseSourceSHA256` and
`currentSourceSHA256`. `source` and `target` are JSON **strings**, retaining the
exact inner document bytes, rather than embedded parsed objects.

Source and target hashes are SHA-256 of each inner string's UTF-8 bytes. The
bundle binds requirements, all four candidates and the target:

```python
import hashlib
import json

payload = {key: case[key] for key in (
    "requirements", "candidates", "target",
    "baseTargetSHA256", "currentTargetSHA256",
)}
raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                 ensure_ascii=True, allow_nan=False).encode("ascii")
bundle_hash = hashlib.sha256(raw).hexdigest()
```

Both base and current bindings must match the supplied bytes. A trusted host must
capture the actual current snapshot; recomputing both hashes from a stale snapshot
does not make it current. These bindings detect inconsistencies, not a malicious
host or an authenticated origin. No signing or external freshness check is implied.

## Result handling

| Exit | Status | Meaning |
| --- | --- | --- |
| 0 | `checked` | The selected mapping and whole repair preview passed. `patch` may be empty for a no-op. |
| 0 | `checked-no-match` | None of the four supplied routes qualifies. No `proposedTarget` is returned. |
| 1 | `withheld` | Input, selection, handoff or complete mapping could not be accepted. No partial patch/target is returned. |
| 2 | CLI usage error | Invalid invocation; no checking is performed. |

**Do not treat exit 0 alone as permission to apply a mapping.** Require `status ==
"checked"`, inspect the receipt, and retain host control of any later write.
Repairs use canonical sorted JSON; no-ops retain the original target bytes,
including whitespace and line endings. A fresh process reruns the checks; an old
preview is not restored as authority. No lessons or pending actions are persisted.

The trusted-Python interface is `checked_choice(case)` in `connector_selection.py`;
the CLI is the portable process boundary. An in-process caller is not sandboxed.

## Evidence and scope

This package carries the four runtime files from a separately qualified local
candidate without altering their bytes. The public CLI, portable fixtures and
tests are validated separately. [Source hashes and provenance](provenance.json)
identify the runtime and the synthetic fixture bank. BRACE's bundled `tv4c.py`
is project code, not a MockServer or WireMock vendor library.

The tests cover wrong selections, substituted source/target handoffs, corrupted
body/path/delay output, stale bindings, malformed catalogs, refusal, exact no-op
bytes, deadlines and repeated read-only calls. These are bounded synthetic tests,
not a production failure-rate estimate or a guarantee over all possible inputs.

The preceding Qwen 2.5 0.5B trial found 10/14 supported mappings, compared with
8/14 for fixed two-candidate enumeration and 14/14 for direct selection. Qwen used
25 calls and 8,914 tokens; direct selection also identified both no-match cases.
Those historical observations motivate the direct default, not a model-performance
claim for this package. The demo runs direct checking and does not rerun Qwen.

[How to add another bounded domain](../../docs/DOMAINS.md)
