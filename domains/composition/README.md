# Bounded composition and accepted lessons

Run a small integer-plan learner with a host-owned acceptance step:

**Propose → check → bounded repair or clarification → explicitly accept → recheck and reuse.**

The supported operations are `add1` (`x+1`), `sub1` (`x-1`), `double` (`2*x`)
and `square` (`x*x`). A request supplies four input/output examples. BRACE checks
a proposed plan against all four, or searches within fixed limits. A successful
draft does not become a saved lesson until the host explicitly accepts it.

This is useful for experimenting with reusable checked plans, rejecting a bad
proposal, and inspecting exactly what survives teaching and reopening. It does
not learn an unrestricted function from four observations. Fresh reuse also
requires expected outputs; the checker does not certify an unknown prediction.

## Run the complete example

From the repository root, with Python 3.12 or later:

```sh
python -I -S -B domains/composition/demo.py
python -I -S -B domains/composition/test_composition.py
```

The example uses fresh synthetic data and a temporary lesson store. Its explicit
acceptances are scripted host decisions, not model-generated approvals. It shows
rejection and repair, ordered composition, fresh checked reuse after reopening,
refusal without changing earlier lessons, and rollback. It needs no model,
account, existing lesson files or third-party dependency. The temporary store
is discarded at the end.

## Use the session entry

```sh
python -I -S -B domains/composition/cli.py
```

Send one JSON object per line on stdin; each produces one JSON receipt on stdout.
For example, supply a wrong identity proposal for squaring:

```json
{"action":"request","examples":[[0,0],[1,1],[210,44100],[211,44521]],"proposal":[]}
```

The empty plan means identity. On these examples it passes the cheap remainder
filter but fails the full arithmetic check. Bounded search can then propose
`["square"]`, using the second full check. On success, inspect `decision`,
`status`, `plan`, `attempts`, `work` and `draft.id`. Copy the returned draft ID
into a **separate host action in the same session**:

```json
{"action":"accept","draft":"COPY_THE_RETURNED_DRAFT_ID","name":"Fold"}
```

Never forward arbitrary model output as session events. A proposer may supply an
operation list; only the trusted host chooses `accept`, `answer`, storage and
rollback. A draft ID binds an action to this session; it is not authentication.

| Action | Fields besides `action` | Effect |
| --- | --- | --- |
| `request` | `examples`; optionally one of `proposal`, `lesson`, `lesson_name`, `composition`; optionally `clarify` | Check or propose a plan under one request grant. |
| `accept` | `draft`, `name` | Accept the current checked draft under a new unique name. |
| `discard` | None | Clear the pending draft or question without changing lessons. |
| `status` | None | List accepted lesson IDs/names/plans and the pending handle. |
| `answer` | `question`, integer `y` | Supply the requested observation under a new bounded grant. |

`examples` is exactly four `[input, expected_output]` pairs of JSON integers.
Repeated inputs must agree. `proposal` is an array of zero to four supported
operation strings. A lesson selector is either its returned ID (`lesson`) or its
case-insensitive accepted name (`lesson_name`). Names match
`[A-Za-z][A-Za-z0-9_-]{0,31}`. Unknown fields, floats, booleans as integers and
duplicate JSON keys are refused.

Once `Fold` and an `add1` lesson named `Nudge` have been accepted, this checks
their new ordered combination:

```json
{"action":"request","examples":[[-3,4],[0,1],[2,9],[5,36]],"composition":"do Nudge then Fold"}
```

Composition accepts exactly `do NAME then NAME` or `do NAME then NAME then NAME`,
case-insensitively, at most 96 ASCII characters. Each name must bind an accepted
**single-operation** lesson. A compound lesson can be accepted and later selected
as a whole, but cannot be nested inside another named composition. Order is
preserved: a conflict is withheld, never silently reordered to fit the examples.

A failed ordinary proposal or lesson reuse can trigger deterministic bounded
search. A repaired result is a new draft; the original lesson is unchanged.
There is at most one supplied or external proposal per request, not a second
LLM call. Cheap modular rejection is reported separately from full checking.

With `"clarify":true`, use at most three distinct pairs among the four rows.
BRACE tries to find two checked hypotheses and an input where they disagree.
Answer using the returned question ID and a measured/host-supplied output. The
answer replaces a duplicate row, preserves every distinct earlier observation,
and consumes the question once. If both hypotheses fail, the answer is withheld.
The two hypotheses are not claimed to exhaust all possible rules.

## Persistence and rollback

Pass `--store ABSOLUTE_DIRECTORY` to the same command to retain accepted lessons.
Choose a local directory outside the checkout with existing parents; the final
directory may be created. On the next invocation with that path, the reader
checks the entire snapshot, its contract and acceptance records, then independently
checks every stored plan against its saved examples before opening the session.
Drafts, failed proposals and pending questions are not persisted.

```sh
python -I -S -B domains/composition/cli.py --store ABSOLUTE_DIRECTORY
python -I -S -B domains/composition/cli.py --rollback --store ABSOLUTE_DIRECTORY
```

Replace `ABSOLUTE_DIRECTORY` with your chosen path. Rollback is a separate explicit
host action: it verifies current and previous generations, then restores the
previous accepted snapshot. It does not uninstall code. Reopening is all-or-nothing;
an invalid lesson, mismatched contract or damaged history prevents the store from
opening. No existing private store or public migration utility is included.
Rollback uses two separate restore allowances (up to eight checks each for current
and previous), followed by a separately bounded storage commit.

Store files use a cooperating-process lock and checked replacements. Their hashes
are consistency checks, not proof of authorship or protection from a hostile
writer. Multi-file power-loss durability is not promised. An uncertain write
requires reopening; never retry an acceptance blindly after an interrupted reply.

## Limits and interpretation

| Boundary | Limit |
| --- | --- |
| Each request or explicit answer grant | 85 candidate visits, 252 proposal arithmetic operations, two full checks, 25-second cooperative deadline |
| Plan | At most four operations; every intermediate absolute value ≤ `10**48` |
| Examples | Four rows; input absolute value ≤ `10**6`, output absolute value ≤ `10**48`; encoded examples ≤ 2,048 bytes |
| Session | 32 events, eight accepted lessons, 64 KiB retained serialized data |
| Wire and pending work | 4,096 bytes per newline-terminated event; five-minute draft/question lifetime |
| Reopening | Separate allowance: at most eight full checks and 128 checker operations, within 25 seconds |

The compiled 341-plan catalog and remainder index have separate setup costs;
receipts count proposal work, checker work and relevant selection/filter overhead.
The 64 KiB limit measures retained serialized state, not total Python process RAM.
Deadlines are checked cooperatively, not enforced by an OS process timeout.
An explicit clarification answer receives a new grant, not unlimited continuation.

Use **both** `decision == "publish"` and `status == "checked"` for a checked plan;
`lesson-accepted` acknowledges a host control action. A checked contradiction is
a verified refusal within this operation grammar, not a valid plan. An empty
search result alone is not an impossibility proof. Ordinary exhaustion, unknown
names and unsupported events also withhold. CLI exit zero means the bounded stream
was handled; it can contain refusals. Inspect each receipt.

The checker recomputes each operation and intermediate value, separately from the
proposal search. Both rely on trusted Python code and a declared contract. This is
not sandboxing untrusted Python or formally verified software. A correct plan for
the supplied examples can still be wrong for the user's intended general rule.

The seven runtime modules are extracted unchanged from the qualified local reader.
Their [source hashes](provenance.json) and Git attributes preserve the contract's
exact bytes. The demo and public-entry tests use new synthetic data and no private
history. This module has its own API; it does not change the integer or connector
entry points.
