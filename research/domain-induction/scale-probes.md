# Doubling or taking the next integer

Doubling the input showed no accuracy advantage on this fresh synthetic set. On the 25 worlds where both policies obtained a distinct numeric reading, both gave **69 correct and 31 wrong** conditional predictions across the same 100 target questions. Each policy had one extra-request allowance after the shared initial reading. All errors were on nonlinear cases.

| Policy across all 48 worlds | Requests issued | Numeric readings | Correct target predictions | Wrong | Withheld |
|---|---:|---:|---:|---:|---:|
| Double the initial input | 30 | 25 | 69 | 31 | 92 |
| Take the next integer | 48 | 40 | 109 | 51 | 32 |

There are four fresh target questions per world, giving 192 per policy. The next integer reaches more cases in this bounded input interval. Doubling is skipped at zero in six worlds and leaves the allowed range at ±80 in 12 worlds. Five issued doubling requests and eight next-integer requests return unavailable. All eight unavailable worlds withhold their four fresh target answers under both policies.

Every arm preserves **672 historical readings and 48 initial target readings**, and all **336** fresh predictions at the seven earlier settings remain correct. Repairs add a local candidate and retain the original observations. The new target numbers are predictions conditional on affine behavior. Their fresh ground truth is used only by the evaluation process.

Both policies recover every additive and affine case for which they receive a usable reading. This is 40/40 fresh answers for doubling and 64/64 for the next integer. In affine case `70824650b30d`, the initial observation is 17 → 79. Doubling obtains 34 → 147 and the next integer obtains 18 → 83. Both recover `4*x+11` and correctly predict 26 → 115.

The quadratic cases expose the limit of fitting a line through two points. In case `3da8fec7e0ce`, the initial reading is 3 → −12. Doubling measures 6 → −45 and fits `−11*x+21`. The next integer measures 4 → −21 and fits `−9*x+15`. At fresh input 18 they predict −177 and −147. The independent outcome is −357. Every fresh quadratic prediction is wrong for both policies, giving 20 such errors for doubling and 32 for the next integer.

**A sampling limitation matters here.** Neither policy crosses a threshold or samples inside a local exceptional interval in this cohort. Both therefore miss those changes. Across the 25 worlds with usable readings for both policies, the coefficients agree in 21 worlds. They differ in four quadratic worlds where both still miss all fresh target outcomes. The result does not resolve which spacing discovers a threshold more often when the threshold lies between one pair of probes.

Only three doubling predictions interpolate between its two measured inputs, and all three are correct. Its other 97 numeric predictions extrapolate beyond that interval, with 66 correct and 31 wrong. Every next-integer prediction extrapolates, since there is no integer strictly between consecutive integers. Its 160 numeric predictions contain 109 correct and 51 wrong. These counts describe this fixture's input distribution.

The experiment supports a bounded next-integer probe as a simple way to obtain a second distinct observation here. It also shows why a fitted line needs a stated domain assumption before use at new inputs. An informative wider probe should be selected because competing explanations predict different readings there. For example, an untested threshold between the near and far probe would supply such a distinction. A follow-up should freeze crossing cases and candidate explanations before scoring.

The reader, scorer and protocol were committed before opening the held-out case bank at `d285071`. A separate replay reconstructed the frozen functions and interpolation results without importing the reader or scorer. Both numeric readings and original evidence are checked for bounds and exact request identity. The result uses zero model calls.

Run from the repository root with Python 3.12 or later.

```sh
python -I -S -B research/domain-induction/scale_probe_trial.py
python -I -S -B research/domain-induction/scale_probe_trial.py --case 70824650b30d
python -I -S -B research/domain-induction/scale_probe_fixture.py
python -I -S -B research/domain-induction/scale_probe_controls.py
```

[Frozen cases](scale_probe_cases.json) · [All decisions and totals](scale_probe_results.json) · [Reader](scale_probe.py) · [Independent fixture reconstruction](scale_probe_fixture.py)

## Frozen protocol

Compare two choices for one additional measurement at a fixed three-bit control setting. Both receive the same earlier exact observation x0 → y0 at that setting and verified observations at the seven other settings. The proposed inputs are 2*x0 and x0+1. Both have one instrument request opportunity. An unavailable reply consumes it. A proposed input equal to x0 or outside the allowed interval [−128,128] causes a hold before dispatch. There is no fallback within this comparison.

The same reader fits y=a*x+b through two distinct observations using exact rational arithmetic. A new slope is a conditional proposal under the affine assumption. Its accuracy on fresh inputs is measured independently. The reader preserves the original target observation and the entire evidence for the other settings. The directly measured values remain available even when the reader cannot make a new prediction.

The case bank is prepared independently of the reader. It contains 48 synthetic worlds, eight each with an additive effect, an affine effect with slope other than one, a quadratic effect, a threshold, a local exception and unavailable additional readings. Each family uses the same initial input schedule [−80,−7,−2,0,1,3,17,80]. For each world, the seven other settings have two historical readings with a stable offset. Four fresh target inputs and one fresh input per other setting give 11 evaluation questions. Teaching inputs, the proposed probe inputs and fresh inputs are kept separate. The learner receives only the action name, control names, historical readings, initial observation and policy.

The evaluator gives each policy only the response at its chosen input. It commits all predictions before scoring against the fresh outcomes. Both conditional candidates face the same fresh questions. Neither policy receives world IDs, family labels, function parameters, another policy's reading, or held-out outcomes.

Report all 48 worlds, including skipped and unavailable probes. Also report the subset where both policies receive a distinct valid numeric reading, and distinguish within-span interpolation from outside-span extrapolation. Count instrument requests, valid numeric readings, fitted candidates, rejected constant-offset assumptions, correct and wrong target predictions, holds, old predictions preserved and exact historical replays. Audit requests against the policy formula and control identity. Ordinary two-point interpolation independently reconstructs every proposed coefficient.

For exact affine functions two distinct readings determine the same line whichever policy chooses them. Nonlinear functions can agree at two points and differ elsewhere. Larger spacing alone supplies no universal guarantee. At x0=1 the two proposed inputs coincide, and at x0=0 doubling repeats the existing input. These cases remain in the denominator.

The primary comparison measures observation choice under an equal maximum grant. Skips can reduce actual instrument work. Each selection computes one multiplication or one addition. Each successful fit stores two rational coefficients. This trial measures requests and predictions and makes no wall-clock speed claim.

The independently authored fixture is frozen at SHA-256 `3dfc23e3c7a09f06205d5a7ac1cac63d63b604eb41bcb06c5dc57e8d9775b584`. It contains 672 historical readings, 48 initial target readings and 528 fresh endpoints. The local-exception family includes one fresh query inside its exceptional region and other queries outside. This is a deliberate stress test of those exceptions.
