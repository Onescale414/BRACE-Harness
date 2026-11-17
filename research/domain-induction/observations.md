# One observation after a contradiction

Two recorded runs of an action started at the same integer and ended differently. Could BRACE ask for one measurement that helps explain the difference, commit to a repair, and predict fresh outcomes? We ran two frozen comparisons. One pays for a **single output reading** at a chosen control setting. The other pays for **one kind of sensor** and accounts for every reading of it. The synthetic instruments provide the answers. No language model runs in either experiment. [Frozen protocol](observation-protocol.md)

## One new reading

In `cgxxmdn`, two explanations fit the historical commands. BRACE asked the instrument to run the action at **57** with controls `hv3=1, q6s=1, xr8=0`. One law predicted **55**, the other **58**. The instrument returned **58**. BRACE selected the law that adds one when `xr8` is off and subtracts two when it is on. It got all eight fresh outputs right. The three controls were part of every command, so future requests needed no additional sensor reads.

Each of 24 worlds had eight tests at fresh starting values. The reader could open at most one offered output in each world. It committed its predicted outputs before their answers were revealed. A domain-wide prediction required a unique candidate and agreement with an independent fit to the receipts. This proves uniqueness within the supplied constant and one-control rules. The table measures how often that supported prediction also matched the actual instrument.

| Whole-domain policy | New readings | Correct | Wrong | Withheld |
|---|---:|---:|---:|---:|
| No new reading | 0 | 0 | 0 | 192 |
| First offered | 20 | 38 | 2 | 152 |
| First that separates any candidates | 16 | 68 | 4 | 120 |
| Minimize the worst remaining candidate group | 16 | 68 | 4 | 120 |

All four identifiable worlds were repaired, giving **32/32** correct endpoints. In four outside-family worlds, the selected output contradicted every remaining rule. BRACE withheld all 32 endpoints. In four other worlds the old data already contradicted every candidate even with all control settings visible. It withheld without spending a reading. Four restricted menus offered no separating reading. Of the four partially distinguishable worlds, one became unique and three remained ambiguous.

**Where one reading can still fool the reader.** Each identifiable world had a partner with identical archived receipts, identical menu settings and outputs, and identical test inputs. Every pair differed at exactly one unoffered setting. For example, at **−80** with `hv3=0, q6s=1, xr8=0` the two instruments returned **−79** and **−82**. Even opening the entire offered menu could not settle that difference. These four designed exceptions account for all four wrong whole-domain predictions. Their frequency here is set by the fixture. [Cases](observation_cases.json) · [Scores by world type](observation_results.json)

**Preserving local results.** An exploratory fallback kept an effect only at a control configuration where the receipts all agreed, assuming a stable additive offset there. A counterexample invalidated the general law while leaving agreeing receipts at other settings available. With no new readings, that policy returned 84 correct and withheld 108. With the same 16 selected readings, it returned **100 correct, 0 wrong, 92 withheld**. It only generalized to new starting integers at witnessed control settings. The prespecified conservative policy also required the global candidate set to be nonempty; that stricter rule discarded locally usable receipts and returned 68 correct, 0 wrong, 124 withheld.

## One additional sensor field

In a separate 24-world bank, each historical row initially exposed only its starting and ending values. The selector could inspect an archive of three possible binary fields on eight old receipts. It requested a field only if its two levels accounted for both observed effects. It then had to confirm the fitted offsets on all six reserved receipts, covering both levels, before making fresh predictions. There was no second field grant.

| Policy | Fields requested | Fields confirmed | Fresh outputs correct | Wrong | Withheld |
|---|---:|---:|---:|---:|---:|
| First catalogued field | 24 | 1 | 6 | 0 | 138 |
| Select using archived contradictions | 12 | 6 | 36 | 0 | 108 |

The selected field fit the past in 12 worlds. Six survived confirmation and predicted **36/36** fresh outputs. All six misleading fields failed confirmation and released nothing. In six unresolved worlds and six with missing historical field readings the selector spent no field grant. Across all 24 worlds, selection inspected **576 archive cells**, including missing markers, reread **96** selected historical cells, and used **72** confirmation and **36** fresh sensor readings. The first-field control inspected no catalog cells, reread 192 selected cells, and used 18 confirmation and six fresh sensor readings. [Field cases](field_cases.json)

An additional diagnostic gifted the correct sensor name in each of the six successful worlds and assumed its two levels map one-to-one to the two known effects. Reading one historical bit fixed that mapping, but the fresh bit was still unknown in **36/36** requests. Paying for each request's current bit resolved all 36. A sensor that changes between requests needs a source for its current value.

Run from the repository root using Python 3.12 or later. Add `--case cgxxmdn` to the first command to see the exact question, competing predictions and answer. The second command checks the indistinguishable pairs and runs the exploratory diagnostics.

```sh
python -I -S -B research/domain-induction/observation_trial.py
python -I -S -B research/domain-induction/observation_limits.py
```
