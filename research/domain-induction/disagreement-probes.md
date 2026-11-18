# Choosing an input that separates candidate rules

Choosing a measurement from rule disagreements increased correct fresh predictions from **55 to 114** in this synthetic trial. Both methods issued **45 requests and received 38 numeric readings** across 48 worlds. They shared a finite family of 301 candidate functions and one extra-request allowance per world.

| Policy | Correct fresh target answers | Wrong | Withheld |
|---|---:|---:|---:|
| Choose a disagreement | 114 | 2 | 76 |
| Take the next integer | 55 | 4 | 133 |

Each method faced the same 192 fresh target questions. No selected probe coincided with an evaluation input in this case bank, so none required exclusion. The disagreement policy gained 59 correct answers where the next-integer policy held and retained all 55 of its correct answers. It also made **two new wrong predictions where the next-integer policy held**. It withheld the four wrong predictions made by the next-integer policy. These transitions matter when assessing the coverage gain.

For thresholds, disagreement selection crossed four of eight cutoffs. The next integer crossed none. Correct fresh threshold answers increased from **4/32 to 21/32**, with zero wrong answers under both policies. For quadratics, correct answers increased from **24/32 to 32/32**. Affine cases improved from **20/32 to 32/32**, and additive cases from **3/32 to 18/32**. A true additive function can remain ambiguous because an unobserved threshold is still compatible with the observations.

In case `a4af142fc086`, the initial observation −1 → −1 leaves 42 possible rules. BRACE asks for input **64**, observes **63**, and retains four rules. All four agree that fresh input **86 produces 85**, which checks against the independent outcome. Taking the next integer gives 0 → 0 and leaves 27 rules that disagree on that question. The disagreement policy answers all four fresh questions in this world while its exact threshold remains unresolved.

All **720 earlier observations** replay under either policy, and all **336** fresh answers at the seven earlier settings remain correct. Seven unavailable requests retain their evidence and withhold all 28 unresolved target questions. In the eighth unavailable world, `e7607b3581e2`, the initial −6 → 15 already uniquely selects −2*x+3 within the supplied family. Both policies skip a request and correctly answer its four fresh questions. One quadratic world is also identified from its initial observation, and one outside-family world contradicts every candidate immediately. Those three worlds account for the unused request opportunities.

The two disagreement-policy errors occur in worlds with an unmeasured narrow exception. In `c015dbe180b7`, 6 → 4 and the selected −65 → −67 leave nine candidates. They all predict **1** at fresh input **3**, while the actual output is **−4**. The true function subtracts an additional five on inputs 3 through 5, which the supplied family cannot express. The next-integer policy holds this query. Consensus remains conditional on the scope of the candidate family.

The extra selection cost was **289,536 candidate evaluations**. Both methods spent 14,448 evaluations on initial filtering and 984 on incorporating numeric replies. Prediction used 1,388 evaluations for disagreement and 2,640 for the next integer. Total candidate evaluations were **306,356 versus 18,072**, about 17 times as many. Counts measure function evaluations, excluding allocations, arithmetic within each function, receipts, and offline evaluation. This result establishes a tradeoff between more internal work and more informative readings. It supplies no wall-clock speed claim.

The reader and scoring protocol were frozen in commit `cd4158d` before opening the case bank. An independent audit reconstructed all decisions and counts from the fixture's functions without importing the learner or scoring module. This comparison uses zero model calls. The prior affine-only extrapolation experiment has a different rule family and answer policy, so its accuracy totals are a separate comparison.

Run from the repository root with Python 3.12 or later.

```sh
python -I -S -B research/domain-induction/disagreement_trial.py
python -I -S -B research/domain-induction/disagreement_trial.py --case a4af142fc086
python -I -S -B research/domain-induction/disagreement_fixture.py
python -I -S -B research/domain-induction/disagreement_probe_controls.py
```

[Frozen cases](disagreement_cases.json) · [All decisions and costs](disagreement_results.json) · [Reader](disagreement_probe.py) · [Fixture reconstruction](disagreement_fixture.py)

## Frozen protocol

Both methods receive the same earlier observation at one three-bit setting, the same observations at seven other settings, and the same finite rule family. They have one additional instrument request opportunity. The comparison changes how the next input is selected.

The family contains 301 functions. There are 105 polynomials q*x²+a*x+b with q in {−1,0,1}, a in {−2,−1,0,1,2} and b in {−3,…,3}. There are 196 threshold functions x+b+j*[x≥t] with the same b, j in {−3,−1,1,3}, and t in {−64,−16,−4,0,4,16,64}. These are experimental design choices. The reader first retains functions matching the initial observation.

The disagreement policy considers every other integer in [−128,128]. At each possible input, it groups surviving rules by their predicted output and minimizes the size of the largest group. Ties prefer the nearer input, then the smaller integer. This reuses BRACE's existing worst-case partition rule. The next-integer control selects x+1. Both skip a new request if their evidence leaves zero or one candidate. All model evaluations for filtering, selection, update and prediction are counted separately from actual instrument readings.

A granted reply is bound to the action, input and setting. It filters the same candidates for either policy. A new answer requires all remaining candidates to agree. An empty family or competing answers leads to a hold. These answers remain conditional on the declared family containing the true rule. Measured values and the earlier settings retain their own evidence. An unavailable reading spends the request opportunity and adds no observation.

An independent case author prepares 48 worlds, eight each additive, affine, quadratic, threshold, outside-family and unavailable. Each family uses starting inputs [−6,−3,−1,0,1,2,3,6]. Threshold worlds include fresh evaluation inputs on both sides of their trigger. Outside-family worlds include cubic behavior and narrow local exceptions. These controls test the consequences of an incomplete rule family.

Each world has four target evaluation inputs plus seven fresh questions at the other settings. A target input directly queried by either policy is excluded from both methods' fresh scores. Directly observed answers are recorded separately. The reader receives neither evaluator outcomes nor the world kind or true function description. All predictions are committed before scoring.

Report correct, wrong and held fresh answers for both policies, unresolved or contradicted candidate sets, actual requests, threshold crossings and model-evaluation work. Preserve and replay every earlier observation. An independently calculated family and partition choice audit the learner's predictions and selection.

The independent fixture is frozen at SHA-256 `553031a4ef6cc52a4a55a8dfe4c5f1d6205d839fc5d34fd14aca645c64538464`. It has 672 historical readings, 48 initial target readings, 12,336 instrument entries and 528 evaluation questions. The cubic controls use floor(x³/4)+b to stay within the inherited output bound of 1,000,000.
