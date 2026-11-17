# Building a domain from observations

In one world, an action called `vush` takes −1 to −5. BRACE provisionally guessed `3x − 2`. The next observation took 2 to 1; the guess predicted 4. BRACE revised the binding to `2x − 3` and confirmed it on two reserved observations. Asked about 10, it returned **17**. In another world the same word meant `−2x + 1`, so 10 became **−19**. The bindings stay local when the domains are reopened.

This optional Python experiment gives BRACE integer states, observable action names or binary readings, a finite family of candidate rules, and an instrument that supplies outcomes. BRACE infers which distinctions predict behavior. The test driver owns the world boundaries, observation budgets and acceptance conditions. Independent checks here are specific to the research task. [First protocol](protocol.md) · [Follow-up protocol](extension-protocol.md)

## Learning and repairing action meanings

Six synthetic worlds supplied three verbs each. BRACE saw one teaching and one feedback observation per verb. Two reserved observations per verb could veto a proposed rule. Forty-eight fresh requests asked for up to three operations in order. A correct answer required every intermediate value. [Worlds and expected traces](scalar_cases.json) · [Results](results.json)

| Method | Correct full traces | Wrong traces | Withheld |
|---|---:|---:|---:|
| Exact example lookup | 0 | 0 | 48 |
| Provisional first guess | 4 | 44 | 0 |
| Revised guess without confirmation | 43 | 5 | 0 |
| Direct two-point fit plus confirmation | 38 | 0 | 10 |
| Learned domain plus independent step checks | 38 | 0 | 10 |

Feedback contradicted and revised **14 of 18** first guesses. Sixteen bindings survived confirmation. The nonlinear action and the action with a conflicting observation were withheld. Other verbs in those worlds stayed usable. The checked path got all **32/32** traces in the four wholly supported worlds. Direct interpolation tied enumeration on this rule family. An altered intermediate was rejected on all 28 released multi-step traces, including when the proposed final number stayed the same. Reopening each domain from its saved observations reproduced all 48 decisions.

## Choosing what to observe

Sixteen worlds applied the same opaque verb to an integer. Four had a constant effect, eight depended on one unknown binary reading, two depended on an interaction and two included incompatible observations for identical visible inputs. With four paid training observations per world, choosing the most discriminating next probe confirmed **12/12** representable worlds, versus **10/12** for fixed order. At three probes the two methods tied at **6/12**. At four, active choice used 10,064 internal candidate-effect evaluations and 135 confirmation readings, versus 108 confirmation readings for fixed order.

On a **new seed**, BRACE designed a sequence it could reuse across worlds by asking which input patterns distinguish all 65 candidate effects. It found `000`, `011`, `101`. The design made 520 internal effect predictions once and tried 50 subsets. All 37 smaller subsets left at least two candidates indistinguishable. This minimality holds for the supplied eight-cell menu and candidate family.

| Fresh follow-up, three training readings per world | Worlds confirmed, out of 16 | Correct endpoints, out of 128 | Wrong releases | Confirmation readings |
|---|---:|---:|---:|---:|
| Fixed order | 7 | 56 | 0 | 72 |
| Choose the next probe each time | 5 | 40 | 0 | 45 |
| Reuse the three-probe design | 12 | 96 | 0 | 144 |

Each policy had the same validation allowance and spent it only on a unique candidate. The three-probe design used more confirmations because it put forward more candidates. Before confirmation, it predicted the five unmeasured feature patterns per world correctly **74/80** times. Six wrong predictions would have escaped if a unique fit had counted as verification. [Design certificate and follow-up results](extension_results.json)

## Inventing a distinction after a counterexample

With all eight feature patterns available for training, BRACE checked its three-probe hypothesis against the remaining five. When a counterexample appeared, it searched for the smallest subset of up to two coordinates that grouped equal measured effects together. An independent check varied one coordinate at a time to verify which changes mattered. The learner received no named Boolean operations.

In `w01`, the resulting partition ignored the third reading. When `mip` and `tev` matched, the action subtracted one; when they differed, it left the state alone. In `w06`, the action added two when both readings were on and one otherwise. Both partitions survived confirmation. Under the same eight training readings per world, the single-feature learner answered **96/128**, and partition repair answered **112/128** with zero wrong releases. The two hidden worlds each supplied different outcomes for the exact same visible input. No deterministic rule on that input can satisfy both.

Full-context lookup also answered **112/128** correctly. The learned representations used **28 effect-table entries** across the 14 accepted worlds, compared with **112** for lookup. This counts table entries, excluding stored observations and implementation costs. The test starting integers were fresh; the eight binary configurations had all been observed.

## Reusing a category for a second verb

For each of the two learned partitions, a second verb showed a new effect on one representative of each learned group. A clean version respected those groups. Six matched alternatives differed from it at exactly one unmeasured cell apiece. Each alternative agreed with both teaching examples. These deliberate exceptions measure detectability; their frequency is set by the experiment. [Transfer observations](transfer_results.json)

| Extra cells checked per verb | Exception cases detected, out of 12 | Wrong endpoints from whole-domain reuse | Correct endpoints from measured-cell lookup, out of 112 |
|---|---:|---:|---:|
| 0 | 0 | 12 | 28 |
| 1 | 2 | 10 | 42 |
| 3 | 6 | 6 | 70 |
| 6 | 12 | 0 | 112 |

Both clean transfers passed at every budget. With an unrestricted single-cell exception, the remaining unobserved cell can always disagree. The global-reuse policy withheld the entire candidate on contradiction. At full coverage that discarded 96 individually answerable endpoints. An exploratory fallback retained the measured local effects after a contradiction. With the same full evidence it answered **112/112** correctly, matching local lookup. At three extra readings it answered 88 correctly and still released six wrong predictions where an exception had escaped detection. At that budget, releasing only measured cells returned 70 correct answers with zero wrong releases.

## Asking for one extra observation

When two possible rules predicted 55 and 58 for the same proposed experiment, BRACE asked the instrument and observed 58. The repair predicted all eight fresh endpoints in that world. Four matched exception worlds exposed the limit of this strategy. A separate local fallback increased correct answers from 84 to 100 with 16 new readings across 24 worlds and withheld 92. [One-reading trial, sensor costs and counterexamples](observations.md)

On 24 fresh worlds the reader could request one previously unmeasured control setting. It repaired all four stable exceptions and kept all 168 previously supported predictions. Its eight errors came from assuming that a single measured offset would transfer to new starting numbers at an unstable setting. [Missing-setting trial and replay](missing-settings.md)

## Reproduce

From the repository root with Python 3.12 or later. The commands run offline using the standard library. Add `--world m42` to the first to see both guesses and the confirmed meanings, or `--world w01` for the first context trial's probe trace.

```sh
python -I -S -B research/domain-induction/trial.py
python -I -S -B research/domain-induction/extension.py
python -I -S -B research/domain-induction/transfer.py
```
