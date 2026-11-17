# Which request did the caller mean?

A stale jobs connector and a decoder error leave three possible repairs. The caller might want to list jobs, search jobs, or open one job. With two checks available, the reader asks, “Were you opening one particular record?”

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
