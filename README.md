# BRACE

BRACE checks two-step integer instructions. A proposer supplies candidate operations. The host checks each operation against the instruction, tests it on five witness values, and records its verdict. The second operation must refer to the accepted first step.

## Run the harness

From this directory, use Python 3.12 or later. The examples run offline using the standard library.

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

## Research examples

- **Bracket geometry.** Two measured marks admit two possible tip positions, 96 drawing units apart. Reveal the third mark to distinguish them. Open the viewer locally or run `python -I -S -B preview/verify.py` to check the coordinates. [Bracket viewer](preview/bracket.html)
- **Task handoff.** The experimental reader completed 25 of 36 connector requests. It still checked a URL that the user mentioned only as an example. The trial includes all wordings and an offline replay. [Delivery experiment](research/delivery/README.md)

[Sources and measurements](PROVENANCE.md)
