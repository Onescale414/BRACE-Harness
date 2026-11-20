# Inspect original receipt evidence

Find the latest two records matching an exact request action, receipt status and
receipt decision. The command returns their original request/receipt text and
positions, bound to the identity of the complete supplied capture. It helps a
reviewer locate prior outcomes and open the evidence that explains them.

Run the complete offline example from the repository root, using Python 3.12+:

```sh
python -I -S -B examples/receipt_inspector/demo.py
python -I -S -B examples/receipt_inspector/test_inspector.py
```

The demo obtains six fresh receipts from the public composition CLI: a correct
plan, a repaired plan, an unknown lesson, an unsupported plan and two explicit
host discards of the checked drafts. It queries the
checked responses and a refusal, checks a no-match, compares all three strategies
and verifies clean rejection of excessive JSON nesting. It writes no files and
uses no model, private store or account. The underlying composition requests use
three full checks; inspection adds none.

## Inspect your capture

Create a UTF-8 JSON file with exactly `version` and `records`:

```json
{
  "version": 1,
  "records": [
    {
      "request_wire": "{\"action\":\"request\"}\n",
      "receipt_wire": "{\"status\":\"checked\",\"decision\":\"publish\"}\n"
    }
  ]
}
```

That minimal object illustrates the capture format; its receipt is not evidence
of a real computation. In actual use, retain the exact sent and received text,
including newlines. The demo shows capture from the real public entry.

```sh
python -I -S -B examples/receipt_inspector/cli.py capture.json --query request checked publish
```

Repeat `--query ACTION STATUS DECISION` for additional queries. Use `-` instead of
a filename to read the capture from stdin. The default strategy is `scan`;
`--strategy memoized` or `--strategy indexed` is explicit and optional. Scan is
appropriate for occasional lookups. Cache/index setup can help repeated queries
against the same capture, with additional memory and setup costs. No general
speedup is promised.

On success, exit code is zero and stdout is one JSON object:

- `kind` is `receipt-inspection`; `status` is `inspected`.
- `source.id` identifies exact ordered wire pairs; `source.record_count` gives
  the number of supplied records.
- `queries` retains query order. Each `positions` list has at most two zero-based
  positions, newest first. An empty list is a valid no-match.
- `records` contains the selected original wire pairs once each, in their
  original ascending position order. Queries refer to these positions.

For example, a query returning `[7, 3]` selects the records at positions seven and
three. The `records` array lists position three before seven. Neither execution
order nor the original wire text is rewritten.

The entire source and every query are validated before any evidence is output.
Unsupported input exits with code two and one structured refusal, such as:

```json
{"kind":"receipt-inspection","status":"withheld","reason":"json-too-deep"}
```

Errors do not include exception traces, local filenames or partial results.
`--help` prints ordinary usage text and exits zero. A closed output pipe may
prevent delivery of a refusal. Source files are read only; the command has no
write, patch, lesson acceptance or model-dispatch option. Every invocation starts
without a previously loaded source or cache.

## Supported input and limits

| Boundary | Limit |
|---|---:|
| Entire capture file/stdin | 1 MiB |
| Records | 1–32 |
| Original request / receipt UTF-8 bytes per record | 4,096 / 65,536 |
| Combined original wire bytes | 1 MiB |
| JSON nesting, in the capture and inside each wire | 32 |
| Queries per invocation | 1–64 |
| Each action/status/decision string | 1–128 characters |
| Memoized queries retained | 32 |
| Encoded result | 2 MiB |

The capture version must be integer `1`. Unknown outer/record fields, duplicate
JSON keys, nonstandard numeric constants, invalid UTF-8 and excessive sizes are
refused. Each wire must decode to an object. Requests may omit `action`, which
uses the literal query label `<missing>`; otherwise action must be a supported
string. Receipts must supply string `status` and `decision` fields. Other inner
fields are preserved. This first format does not admit raw malformed/non-object
requests, even when BRACE has emitted a valid refusal for them. It does not
silently reinterpret those lines.

`inspected` means matching records were retrieved. It is not `checked`, a new
computation verdict or permission to use an answer. The command does not
authenticate the capture or prove that a claimed receipt came from BRACE. A hash
binds the displayed source bytes; it does not establish authorship. Ordinary
domain checks and explicit host acceptance still govern computation and lessons.

This example is separate from the checker and saved-lesson runtime. Its byte and
record limits bound this inspection interface, not total Python process memory.
