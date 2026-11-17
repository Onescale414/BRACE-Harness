# Can a small model hand off the right calculation?

Let a language model interpret the conversation. Give a deterministic backend the starting integer, signed change and multiplier. The backend calculates `(start + change) × multiplier`, and BRACE checks each step before releasing the number. This experiment measures how often the submitted fields express what the caller meant.

From the repository root with Python 3.12 or later, run the offline replay. It uses archived Qwen proposals, recomputes the reader decisions, and runs the public arithmetic checker. You can inspect an individual conversation with `--case g02`.

```sh
python -I -S -B research/arithmetic-handoff/replay.py
```

## What the reader has to catch

| Caller’s instruction | Qwen submitted | Arithmetic for the caller’s instruction |
|---|---|---|
| Start at 13, add 4, then triple. | `(13 + 4) × 3` | 51 |
| Start at 13, triple first, then add 4. | `(13 + 4) × 3` | 43, with an operation order outside this harness’s contract |

In the unguarded runs both proposals passed the arithmetic checker. The stricter reader asked for clarification on both. The replay IDs are `g01` and `g13`.

## Results

**First trial.** On eight clear conversations, Qwen answered one correctly on its own. When asked to supply only the three fields, it supplied four correct interpretations and the backend delivered four correct answers. Entering the intended fields directly produced all eight correct answers. On four additional requests that needed clarification or an unsupported operation, both model paths released a number every time. In one case Qwen turned “a few extra” booklets into exactly one.

**Fresh trial.** A separate author supplied 16 new conversations without seeing the reader. Eight had a supported answer, four needed clarification, and four requested unsupported arithmetic. Each policy reused the same initial model draft and could spend up to two arithmetic checks per conversation.

| Policy | Correct calculations on 8 clear requests | Wrong or unwarranted numbers released, out of 16 | Clear requests withheld |
|---|---:|---:|---:|
| Check the calculation Qwen proposed | 5 | 11 | 0 |
| Require the wording rule and Qwen to agree | 0 | 0 | 8 |
| Allow one Qwen retry on a disagreement | 0 | 0 | 8 |
| Use the wording rule alone | 0 | 0 | 8 |

The 11 releases comprise three arithmetic requests with a misread operand and eight requests for which a number was premature or outside scope. The stricter reader could identify a full calculation on **none of the eight clear requests**. It asked for clarification on all four ambiguous requests and declined three of the four unsupported requests. An unrecognized phrase can produce a generic clarification. The scoring counts that as a hold and records whether the expected disposition was actually given.

**Repair.** A retry is available only when the rule can independently recover a complete calculation and the model disagrees. Feedback names the conflicting fields. It supplies no replacement values. None of the 16 fresh conversations qualified. Three separate controls used phrasing the rule supports. On two, Qwen and the rule agreed immediately. On the third, the caller said **−8**, Qwen submitted **+8**, and Qwen repeated **+8** on its single retry. BRACE withheld the answer. Using the independently read fields directly solved all three controls. Four additional scope and negation probes admitted no calculation. These controls and probes are separate from the fresh totals.

## When should the verifier speak?

We replayed the same 16 conversations to distinguish an explicit contradiction from a reader simply failing to recognize a phrase. The independent reader made its assessment from the original dialogue. The host compared that assessment with Qwen’s first draft. Each reread could receive one of three signals, **agree**, **conflict** or **unresolved**. Replacement operands and expected answers stayed out of the prompt. The reader found **3 conflicts and 13 unresolved cases**. This set had no agreements.

| How the first draft was reviewed | Clear requests answered, out of 8 | Clear requests interpreted and answered correctly | Wrong or unwarranted numbers released, out of 16 |
|---|---:|---:|---:|
| Require the reader to agree before releasing | 0 | 0 | 0 |
| Ask Qwen to reread once | 7 | 5 | 7 |
| Cue Qwen to look for the quantities and their order | 8 | 5 | 9 |
| Give that cue and send the reader’s signal every time | 4 | 3 | 4 |
| Give the cue and interrupt only on an explicit conflict | 8 | 5 | 6 |

The final row is an exploratory comparison chosen after the initial scores. For each case we selected the already recorded reply produced by that policy, using only the reader’s signal to select it. On the three explicit conflicts Qwen asked for clarification instead of releasing a number. All three requests actually specified unsupported arithmetic. Keeping the reader silent on unresolved wording preserved the original five correct answers and still let six wrong or unwarranted numbers through. A quiet verifier supplies no independent confirmation of the interpretation.

Reproduce the table, including the original draft and a host-only conflict policy, from the repository root. The replay checks the archived proposals against the same two-step arithmetic contract.

```sh
python -I -S -B research/arithmetic-handoff/feedback.py
```

## Try a caller correction

```sh
python -I -S -B research/arithmetic-handoff/review.py g02
```

The caller asks to take 8 off a starting score of 3, then double what remains. Qwen proposes a positive change of 8. Enter `set 3 -8 2` to correct it. Review the displayed calculation, then enter `confirm` to release **−10** after two checks. Confirming the original proposal instead releases **22**. Cancelling spends zero checks. The operator supplies the correction here. The live retry results above measure what the model corrected on its own.

## Reproduction

The local model was `qwen2.5:0.5b`. Each model call had a 96-token output cap, temperature 0 and seed 0. The second trial reused the first trial’s translation prompt. The rule and fresh test set were frozen before scoring. The interactive example replays an archived proposal; it starts no model and writes no changes. These invented conversations test one arithmetic contract. [Cases, model settings, prompts and proposals](evidence.json) · [Wording rule](gate.py) · [Offline replay](replay.py)
