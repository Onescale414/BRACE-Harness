# Requesting the missing setting

The earlier trial only let BRACE choose from an offered menu. Two instruments could agree on the entire menu and disagree at a setting it omitted. Here the host lets the reader construct its own request for one precise combination of three named binary controls. It may ask once for an output at a specified starting integer. Only the returned output at the requested setting is available. A missing reading stays missing.

## Frozen comparison

Use 24 independently authored synthetic worlds. Four matched groups each include a stable exception, agreement with the old rule, and an unavailable reading. Other cases have two missing settings, a fully measured domain, or an offset that changes with the scalar input. Give the reader the action, control names, old receipts, calibration input and requested control configurations. For the main comparison the requested domain is the full eight-cell cube in binary order; the reader has no access to test inputs, outputs, world IDs, labels, or the instrument's response table. Whole-number outputs may be zero. A null instrument response means that the reading is unavailable.

Compare retaining the old local evidence, extending an ordinary single-control rule across the whole cube, and using the new reading only at its requested setting. Distinguish a **directly measured value** at the calibration input from a **prediction at a new integer** assuming a stable offset at that setting. Count requests, successful numeric readings, unavailable responses, previously covered predictions changed, new correct and wrong predictions, and remaining holds. Compare each prediction with an independent per-setting receipt calculation. In a conservative control the new reading can answer an exact replay but cannot by itself release a prediction at a different starting integer. The eight original control combinations are available to all policies, even when the earlier probe menu would have omitted one.

A successful repair must request the actual gap, return the independently expected values at fresh inputs in the stable cases, preserve every previously supported prediction, and leave the gap unresolved after a denial. Report unstable worlds and any wrong predictions. A single agreeing observation cannot establish input-independent behavior.

The synthetic fixture was prepared separately from the reader and frozen at SHA-256 `0f29774ad51e11bb02c946f61cc65d8804ca783869c6202cd0c035402c7d09eb` (UTF-8, LF). The targeted and exact-replay policies share one request opportunity. An unavailable reply consumes it. The old-rule and witnessed-only controls use zero new readings. For equal evidence, score an independent lookup that adds the same single receipt and carries its offset forward at the same setting. This exposes whether the inference itself adds anything beyond a table lookup.

## Results

The reader requested the missing setting in all 16 worlds with one gap and one of the two missing settings in each of four more worlds. The four fully measured worlds triggered no request. Of 20 requests, 16 produced a number and four returned unavailable. Every one of 336 historical readings replayed correctly after the trial. All 168 fresh predictions supported by old readings were preserved.

| Policy on 196 fresh endpoints | Numeric readings | Correct | Wrong | Withheld |
|---|---:|---:|---:|---:|
| Keep witnessed settings | 0 | 168 | 0 | 28 |
| Extend the old single-control rule | 0 | 172 | 24 | 0 |
| Request the gap and reuse its measured offset | 16 | 180 | 8 | 8 |
| Independent lookup with the same receipts | 16 | 180 | 8 | 8 |
| Use the new reading only at its exact starting input | 16 | 168 | 0 | 28 |

The last policy could replay all 16 new readings. Each evaluation question used a fresh starting number. Choosing the gap gained evidence, and ordinary lookup matched BRACE given that evidence. [Frozen cases](missing_setting_cases.json) · [Replay totals](missing_setting_results.json)

In case `7db8337d7d`, the same 14 earlier readings supported adding five whenever `biben=0`. BRACE asked **“What output does pimav produce at 51 with biben=0, kavuk=1, vubiv=0?”** The broad rule predicted 56. The instrument returned 44, an offset of −7. At a fresh input of 67 the repair predicted **60** and the independent outcome was **60**. The other seven settings kept their earlier offsets. Each of the four exception worlds shared its entire pre-reading history with an agreement world and an unavailable world. The question was the same across each trio.

| Condition (four worlds each) | Fresh correct | Wrong | Withheld |
|---|---:|---:|---:|
| Stable exception | 32 | 0 | 0 |
| Reading confirms the old rule | 32 | 0 | 0 |
| Requested reading unavailable | 28 | 0 | 4 |
| Two settings missing, one reading allowed | 28 | 0 | 4 |
| All settings already covered | 32 | 0 | 0 |
| Offset varies with the starting input at the gap | 28 | 8 | 0 |

All eight errors were fresh predictions at the measured setting in the four unstable worlds. For example, 51 → 44 fits both `y = x − 7` and `y = 2x − 58`. They predict 60 and 76 respectively at 67. A host that knows the effect at a fixed setting is additive can use the repaired offset. A host that lacks that guarantee can release the observed endpoint and keep extrapolations conditional.

The old single-control comparison allows arbitrary integer offsets. The reader's existing rule-labeling routine recognizes only offsets from −2 to +2. It recorded all 16 grants as `accepted_local`. Agreement and exception in the tables come from the independent comparison with the old rule and held-out outcomes. The reader did not identify those two classes by name.

## Asking without a menu

The frozen trial supplied the eight settings as the scope of the questions. In a separate follow-up, we made the demand list optional. Calling `session.request(x=calibration)` now enumerates the eight settings from three known binary controls and selects the first unseen one. The host supplies the control names, their binary domain, the prior readings and the calibration input. It supplies no list of settings or hint about which one is missing.

A fresh fixed-seed test omitted every possible setting in turn and tried three outcomes for each omission. The reader named the gap **24/24** times, labeled **8/8** stable exceptions and **8/8** confirmations in its supported labeling range, and withheld at the gap on **8/8** unavailable readings. It replayed all **336** old readings. Across **192** fresh questions it gave **184 correct, zero wrong, eight withheld**. These follow-up cases used stable effects at each setting. The input-dependent stress cases in the main trial still apply. [Schema-only diagnostic](missing_setting_schema_controls.py)

A subsequent trial supplied one additional reading at the same setting to test doubling the input against the next integer. It preserved the earlier evidence and exposed nonlinear failures of the two-point fit. [Scale probe comparison](scale-probes.md)

## Reproduce

From the repository root with Python 3.12 or later:

```sh
python -I -S -B research/domain-induction/missing_setting_trial.py
python -I -S -B research/domain-induction/missing_setting_trial.py --case 7db8337d7d
python -I -S -B research/domain-induction/missing_setting_controls.py
python -I -S -B research/domain-induction/missing_setting_schema_controls.py
```

The protocol controls exercise misbound, malformed, duplicate and conflicting replies, missing grants, and attempts to overwrite a completed reading. The experiment uses a simulated instrument and consumes no model calls.
