# Choosing an input that separates candidate rules

Both methods receive the same earlier observation at one three-bit setting, the same observations at seven other settings, and the same finite rule family. They have one additional instrument request opportunity. The comparison changes how the next input is selected.

The family contains 301 functions. There are 105 polynomials q*x²+a*x+b with q in {−1,0,1}, a in {−2,−1,0,1,2} and b in {−3,…,3}. There are 196 threshold functions x+b+j*[x≥t] with the same b, j in {−3,−1,1,3}, and t in {−64,−16,−4,0,4,16,64}. These are experimental design choices. The reader first retains functions matching the initial observation.

The disagreement policy considers every other integer in [−128,128]. At each possible input, it groups surviving rules by their predicted output and minimizes the size of the largest group. Ties prefer the nearer input, then the smaller integer. This reuses BRACE's existing worst-case partition rule. The next-integer control selects x+1. Both skip a new request if their evidence leaves zero or one candidate. All model evaluations for filtering, selection, update and prediction are counted separately from actual instrument readings.

A granted reply is bound to the action, input and setting. It filters the same candidates for either policy. A new answer requires all remaining candidates to agree. An empty family or competing answers leads to a hold. These answers remain conditional on the declared family containing the true rule. Measured values and the earlier settings retain their own evidence. An unavailable reading spends the request opportunity and adds no observation.

An independent case author prepares 48 worlds, eight each additive, affine, quadratic, threshold, outside-family and unavailable. Each family uses starting inputs [−6,−3,−1,0,1,2,3,6]. Threshold worlds include fresh evaluation inputs on both sides of their trigger. Outside-family worlds include cubic behavior and narrow local exceptions. These controls test the consequences of an incomplete rule family.

Each world has four target evaluation inputs plus seven fresh questions at the other settings. A target input directly queried by either policy is excluded from both methods' fresh scores. Directly observed answers are recorded separately. The reader receives neither evaluator outcomes nor the world kind or true function description. All predictions are committed before scoring.

Report correct, wrong and held fresh answers for both policies, unresolved or contradicted candidate sets, actual requests, threshold crossings and model-evaluation work. Preserve and replay every earlier observation. An independently calculated family and partition choice audit the learner's predictions and selection.

The independent fixture is frozen at SHA-256 `553031a4ef6cc52a4a55a8dfe4c5f1d6205d839fc5d34fd14aca645c64538464`. It has 672 historical readings, 48 initial target readings, 12,336 instrument entries and 528 evaluation questions. The cubic controls use floor(x³/4)+b to stay within the inherited output bound of 1,000,000.
