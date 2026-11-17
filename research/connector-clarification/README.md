# Which request did the caller mean?

Suppose an API client fails while retrieving a job. Its error fits three routes. The caller might want to list jobs, search jobs, or open one job. BRACE can afford to check two repairs, so it asks, “Were you opening one particular record?” Each accepted repair produces a patch preview for a reviewer.

## Compare the two readers

Run this command from the repository root with Python 3.12 or later.

```sh
python -I -S -B research/connector-clarification/comparison.py
```

Both readers get the same question and reply. A yes or no selects candidates to check. A hold preserves both checks. An ask also preserves both checks and supplies a follow-up question about the action. The offline replay runs both readers, rebuilds each proposed patch, and checks that the resulting mapping and verdict match what BRACE recorded in the original trial. It prints the matched-pair score and examples of individual decisions. Add `--case ID` to inspect a specific reply. [Labeled cases and receipts](comparison.json)

The test used 24 matched pairs. Replacing “this request” with “another request” was the only change within each pair. Six additional replies made the action ambiguous. Eight controls included negation and cases where the scope of one action was already explicit. A separate agent generated all 62 synthetic replies without seeing the candidate reader. The reader and the labels were frozen before scoring.

| On the same fresh replies | Published reader | Candidate |
|---|---:|---:|
| Checked the current action | 4/24 | 6/24 |
| Kept both checks on another request | 20/24 | 24/24 |
| Correct on both members, including holding quietly on the other request | 0/24 | 6/24 |
| Asked which action to check when ambiguous | 0/6 | 5/6 |
| Matched the expected decision on the additional controls | 2/8 | 2/8 |

The candidate held quietly on 19 unrelated replies and asked an unnecessary question on five. It still missed clear instructions such as “Please open ticket 974 for this request.” A separate deliberate exclusion, “I downloaded a copy for every ticket except for this request,” triggered a preview. Replay it with `--case X01`. That counterexample is outside the table. [Exclusion probe and receipts](limit.json)

After the freeze, one person supplied a new instruction with three actions. The scope phrase immediately preceded the download action. Changing that phrase from the current request to another request produced one matched pair. Asked about downloading, the published reader waited on both versions. The candidate asked for confirmation on both and spent zero checks. It still needed help binding a scope phrase to one action in a sequence. This human pair is separate from the 62 synthetic replies.

## Reproduce the original scope failure

Run this command from the repository root with Python 3.12 or later.

```sh
python -I -S -B research/connector-clarification/replay.py
```

| Synthetic reply | Expected | Observed | Checks spent |
|---|---|---|---:|
| I viewed the selected job for this request. | Proceed | Produced a checked preview | 1 of 2 |
| I haven't decided yet. | Wait | Kept both checks available | 0 of 2 |
| I viewed the selected job for another request. | Wait | Produced the same preview | 1 of 2 |

The third row is a known reader failure. The proposed patch changes the stale request to the required GET and jobs/details path. The patch satisfies the connector contract in both the first and third rows. Only the first reply selects that action for the current request.

The replay runs the frozen reader and reconstructs the proposals from the original catalog of 10 resources and 10 actions. For each issued check it rebuilds the patch, compares the resulting whole mapping with the source contract, and verifies it against the archived BRACE receipt. It runs offline with the Python standard library. The original receipts came from the research connector checker on a synthetic mapping served by WireMock 3.13.2. Running the original checker against a live service is a separate experiment. No mapping is modified by this example.

In a separate small test, a person wrote two fresh instructions. Changing only “this request” to “another request” produced two matched pairs. The reader waited on all four sentences and spent zero checks. It distinguished neither pair. One instruction contained two actions, so the trailing scope phrase could also be read as applying only to the second action. The three synthetic examples above illustrate behavior and are excluded from that result.

The command exits successfully when the recorded outcomes, including the known failure, reproduce. A discrepancy with the recorded evidence raises an error. [Cases and receipts](cases.json) · [Frozen reader](reader.py) · [Replay](replay.py)
