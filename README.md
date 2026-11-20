# BRACE

BRACE provides small, domain-specific verifiers for developers who need checked computations and repair previews. Each domain declares its supported inputs, acceptance rules and work limits. It returns a checked result or an explicit refusal. Direct code handles work the contract already determines; the integer harness also accepts proposals from an AI or another program.

At an input of 2, `2 + 2` and `2 × 2` both give **4**. In the PAT example, a mislabeled lesson proposes addition when the instruction calls for multiplication. A check on the final number alone would pass. BRACE records `different-operation` and withholds the answer. [Run the PAT example](#try-pat-as-a-proposer)

## Available now

| Capability | Try it | Boundary |
| --- | --- | --- |
| Checked integer steps and bounded retries | `python -B demo.py --json` | Supported add-then-multiply instructions; host-owned release. |
| Connector selection and repair preview | `python -I -S -B domains/connector/demo.py` | Four supplied mappings, explicit selection rule and a fixed MockServer-to-WireMock subset; read-only. |
| Bounded composition and accepted lessons | `python -I -S -B domains/composition/demo.py` | Four-example integer plans; explicit host acceptance, checked reuse, reopening and rollback. |
| Read-only receipt inspection | `python -I -S -B examples/receipt_inspector/demo.py` | Exact lookups in bounded supplied captures; returns original evidence without rechecking or authorizing it. |
| Geometry reconstruction | `python -I -S -B preview/verify.py` | The supplied bracket measurements and listed alternatives. |
| Learned local rules and informative observations | [Research replay commands](research/domain-induction/README.md#reproduce) | Finite hypothesis families; reports include errors when the true rule is missing. |

The first five commands run offline with Python 3.12 or later and the standard
library. No model download or account is required. Research replays also document
their own assumptions and budgets; they are not a general reasoning guarantee.

The new connector command independently checks **which mapping was selected**,
then binds that choice to the exact source and target before building and auditing
the complete patch. A correct conversion alone cannot establish that the right
mapping was chosen. The example suite produces 14 checked mappings, two verified
no-matches and two refusals. It applies no changes.

[Connector contract and runnable CLI](domains/connector/README.md) ·
[How bounded domains fit together](docs/DOMAINS.md)

## Propose, repair, accept and reuse

The [composition example](domains/composition/README.md) supplies a wrong identity
plan for four squaring examples. A full check rejects it; bounded deterministic
repair finds `square` on the second check. A separate host action accepts that
checked draft as `Fold`. After accepting `Nudge` as `add1`, the host can request
`do Nudge then Fold`, check the ordered plan and explicitly save it as `Lift`.

Reopening independently rechecks all saved lessons. Reusing `Lift` on fresh
examples requires another check; reversing the named order is withheld without
changing the lessons. The one-command demo also rehearses rollback and a bounded
clarification. It uses disposable synthetic storage and no model calls.

A checked lesson means the plan matches its supplied observations. Reuse requires
new expected outputs; it does not establish an unrestricted learned rule or
certify unknown predictions. The host owns acceptance, observations and storage.
The CLI accepts structured events, not unrestricted chat.

To inspect captured outcomes, the optional [receipt inspector](examples/receipt_inspector/README.md)
finds the latest two records matching an exact action, status and decision. It
returns original request/receipt text with source identity and event positions.
Scan is the default; cache and index options are explicit. Unsupported captures
receive a structured refusal. This is a read-only evidence viewer, not another
checker or a lesson-acceptance path.

## From conversation to checked arithmetic

A caller says, “The counter reads 13. Bump it up by 4, then triple the new reading.” Reverse those last two operations and the answer changes from **51** to **43**. Qwen 2.5 0.5B submitted the same calculation both times. BRACE verified the submitted arithmetic both times. What evidence would justify accepting the model’s interpretation?

In an initial trial, Qwen alone answered **1 of 8** clear requests correctly. Having Qwen translate the request and handing off the arithmetic raised that to **4 of 8**. The backend answered **8 of 8** when given the intended inputs. On a fresh set, a stricter reader prevented all 11 wrong or unwarranted releases, but it also withheld all eight clear requests. You can reproduce both results and try confirming or correcting a handoff yourself. [Run the handoff experiment](research/arithmetic-handoff/README.md)

An exploratory replay on those same 16 conversations suggested interrupting only on an explicit conflict. On a subsequent, preregistered test of **32 new conversations**, the verifier could not resolve any of them. It sent no conflict notices. The reminder alone and the conflict-only policy both got **8 of 16** clear requests right and released **20** wrong or unwarranted numbers overall. [See the prospective test and replay](research/arithmetic-handoff/README.md#did-conflict-only-feedback-help-on-new-conversations)

A follow-up rule asked which operation came first in the original bonus example, then missed all eight fresh cases with the same ambiguity. A separate probe showed why the handoff matters. The reader dropped one of two requested additions, and BRACE correctly checked the shortened calculation. [See the missing-order trial and counterexample](research/arithmetic-handoff/README.md#can-the-reader-ask-which-operation-goes-first)

## Where BRACE fits

- **Require a check before using an answer.** Route the task through `run_bound` and let the host application release the value only when `outcome.status == "checked"`. The application must own that release path. The proposer adapter runs as trusted Python code.
- **Offer a check when an AI asks for one.** Expose the same call as a tool. The caller can inspect the receipts, revise a rejected step and submit it again under the host's retry policy. Skipping the call produces no BRACE verdict.

The integer API supports adding an integer and then multiplying by an integer. It can do the arithmetic directly. Plugging in your own proposer lets you measure which steps it gets wrong and whether a retry helps. BRACE checks the operation and five witness values, and the second step must cite the receipt for the accepted first step. The connector profile uses a direct selector because it outperformed the model in the bounded comparison. These are separate domain APIs; a new task type needs its own contract and checker.

The connector experiment asks whether the caller requested the action that passed the technical check. Its offline replay includes a valid patch preview for a request the caller explicitly excluded. You can reproduce the failure and inspect the evidence. [Try the connector replay](research/connector-clarification/README.md)

## Run the harness

From this directory, use Python 3.12 or later. The built-in demo and tests run offline using the standard library.

```sh
python -B demo.py --json
python -B -m unittest -q test_harness
```

The demo runs `Start with 3. Add 1, then double the result.` It tries a wrong operation first at each step. Four checks yield the final value **8**. Changing `Start` to `Begin` returns `unsupported-input`. The suite covers 18 cases. [Demo](demo.py) · [Tests](test_harness.py)

Both operands may be negative. For `Start with 6. Add -11, then multiply by -3.`, the checked values are `-5` after addition and `15` after multiplication.

## Write a proposer

Extract the release and put your script beside `harness.py`. Import `Candidate`, `Reply`, `encoded`, and `run_bound` from `harness`. Call `run_bound(instruction.encode("utf-8"), adapter)`. The host calls your trusted synchronous Python function `adapter(ticket, view)` for each step.

Return `Reply(ticket.ticket_id, (Candidate(encoded(payload)),))` to submit one candidate. Build `payload` as a Python dictionary with exactly these nine keys.

| Keys | Values |
|---|---|
| `id`, `run`, `snapshot` | Choose a candidate ID unique within the run, such as `f"op-{view.step}"` for one candidate per step. Copy `ticket.run` and `ticket.snapshot` into the other two fields. |
| `step`, `parent` | Copy `view.step` and `view.parent`. At step 0 the parent is `None`. At step 1 the host supplies the first accepted receipt's ID. |
| `a`, `b` | Each operation maps `x` to `a*x+b`. At step 0 use `(1, view.snapshot.add)`. At step 1 use `(view.snapshot.multiply, 0)`. The host has already parsed both operands, including a factor of 2 for “double the result.” |
| `witness`, `result` | Send a list of the five outputs of `a*x+b` for inputs `[-2, -1, 0, 1, 2]`, in that order. Send the output for `x = view.before` as `result`. |

Candidate IDs accept 1–64 ASCII letters, digits, underscores, periods, or hyphens. Coefficients, witness outputs, and results must be integers with absolute value at most `10**15`. The returned outcome exposes `outcome.status`, `outcome.value`, and `outcome.receipts`. Each receipt has a `step`, `verdict`, and `value`. A successful two-step run has status `checked` and a checked receipt for each step.

## Try PAT as a proposer

Download and unzip [BRACE-Harness](https://github.com/Onescale414/BRACE-Harness/archive/refs/heads/main.zip) and [PAT](https://github.com/Onescale414/PAT/archive/refs/heads/main.zip) into the same parent directory. From inside `BRACE-Harness-main`, run these commands with Python 3.12 or later. If your PAT directory has another name, pass its path to `--pat`.

```sh
python -m pip install "numpy>=1.24"
python -B examples/pat/demo.py --pat ../PAT-main
```

Each case starts with its own in-memory PAT lessons. In the first case PAT recalls “multiplying” as multiplication and BRACE releases **4**. In the second case that word was deliberately labeled addition. At an input of 2, both adding 2 and multiplying by 2 give 4. BRACE returns `different-operation` and withholds the answer. On one retry, the adapter excludes addition only at the rejected step. PAT recalls “doubling,” BRACE rechecks both steps and releases **4**. The original lesson is still available afterward.

In the third case PAT recalls multiplication correctly, and the demo deliberately changes the reported result from **4** to **5**. BRACE returns `wrong-result` and withholds the answer. On one retry, the adapter takes the rejected draft and recalculates `2 × 2` from its original coefficients and the checked input. BRACE releases **4**. The demo compares both submitted drafts and verifies that the lesson, operation, operand and five witness values match. The new run has its own run ID and first-step receipt.

The fourth case gives the whole request one retry. PAT recalls “adding” as multiplication, so step one proposes `1 × 1 = 1`. BRACE returns `different-operation` and stops before step two. On retry, PAT recalls an alternative lesson, “sum,” and BRACE checks `1 + 1 = 2`. Step two now runs for the first time. It proposes multiplication but reports **5** for `2 × 2`. BRACE returns `wrong-result`. The retry is spent, so the final answer is withheld.

The example submits one candidate per step. The correct case spends two checks, each single-fault case spends four, and the two-fault case spends three. After NumPy and both repositories are available, the example runs offline. [Adapter](examples/pat/adapter.py) · [Runnable example](examples/pat/demo.py)

## Research examples

- **Learning a domain from observations.** BRACE learned local action meanings and requested measurements to test them. With the same finite rule family and 38 readings, choosing inputs where rules disagreed yielded 114 correct fresh answers versus 55 from the next integer. Two errors remained when the true rule was absent, and selection required more internal computation. [Domain induction and transfer](research/domain-induction/README.md) · [Missing-setting repair](research/domain-induction/missing-settings.md) · [Choosing the next observation](research/domain-induction/disagreement-probes.md)
- **Repeated additions.** A consecutive-integer detector flagged 22 of 24 fresh cases involving possible repeated additions and 6 of 8 outside controls. A later reader linked both amounts to their event text on 4 of 18 relevant requests, including a penalty that had been copied into a second record. [Repeat detection](research/arithmetic-handoff/README.md#does-a-repeated-integer-mean-a-repeated-operation) · [Event attachment and replay](research/arithmetic-handoff/README.md#can-the-reader-attach-each-amount-to-its-event)
- **Bracket geometry.** Two measured marks admit two possible tip positions, 96 drawing units apart. Reveal the third mark to distinguish them. Open the viewer locally or run `python -I -S -B preview/verify.py` to check the coordinates. [Bracket viewer](preview/bracket.html)
- **Task handoff.** The experimental reader completed 25 of 36 connector requests. It still checked a URL that the user mentioned only as an example. The trial includes all wordings and an offline replay. [Delivery experiment](research/delivery/README.md)
- **Which request did the caller mean?** When one API error fits three routes and a tool can only check two, it can ask which action the caller meant. Compare two readers on “this request,” “another request,” and replies that mention multiple actions. Run `python -I -S -B research/connector-clarification/comparison.py`. [Connector clarification example](research/connector-clarification/README.md)

[Sources and measurements](PROVENANCE.md)
