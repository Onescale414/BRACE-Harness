# Returning to a second request

The two questions are how long a connector waits and whether `GET /Harbor/ledger` matches. Both fixtures have a configured delay of 125 ms. In a previous WireMock run the mixed-case request returned 404 for one fixture and 200 for the other. Each trial request can use at most one of these recorded URL observations. The delay is available from the supplied configuration.

Twelve pairs of fresh prompts vary who should act and when. Six pairs start with each topic. Twelve additional prompts cover direct orders, examples, a third party, cancellation and unclear requests. The candidate reader was frozen before it saw these wordings or their answer key. Earlier trials informed its development.

| English reader | Whole request | Authorized follow-up | User will ask later | Both members right | Unrequested URL checks |
|---|---:|---:|---:|---:|---:|
| Original reader | 15/36 | 7/12 | 2/12 | 0/12 | 9 |
| Previous reader tracking who acts | 20/36 | 5/12 | 8/12 | 4/12 | 4 |
| Reader tracking first-answer delivery | 25/36 | 8/12 | 8/12 | 6/12 | 2 |

All three use the same ordinary queue, checked values and observation allowance. The third reader uses a matching receipt from the request's in-memory recipient to release an authorized follow-up. The receipt establishes that the answer reached that recipient. Human reading and recovery after a restart are outside this test.

The new reader also spent three ultimately authorized URL checks *before* the requested delay answer. The previous reader did that once, and the original reader did it four times. Counting both early and unrequested checks, the previous and new readers each made five mistakes. The delivery guard can enforce the order only after the reader selects the right first task.

For example, the new reader handled both variants of a request beginning with the URL question. “Having told me the result, check the delay setting yourself” released the delay after delivery. “Having heard the result from you, I'll check the delay setting myself” ended with the URL answer. It still spent a URL check on “GET /Harbor/ledger is just the example printed beside it.” A correctly checked URL result can still answer the wrong question.

Run from the repository root with Python 3.12 or newer.

```text
python -I -S -B research/delivery/recount.py
python -I -S -B research/delivery/recount.py --rerun-readers
```

The first command scores the ordered answers, clarification decisions, values and URL observations against the published labels. The second also executes the three original readers on all 36 prompts and exercises the new handoff with the archived fixture values. Both run offline. Each prompt, expected decision and observed answer is in [observations.json](observations.json).
