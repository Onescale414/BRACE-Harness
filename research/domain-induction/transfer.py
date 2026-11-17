"""Measure the price of reusing an induced partition for a second opaque verb."""
from collections import Counter
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from context_cases import worlds
from partition import learn, verify


def measure():
    # Deliberately paired counterfactuals on the two already learned interaction worlds.
    # Each exception in turn is placed in one of the six cells the teacher did not show.
    records = []
    for world in (w for w in worlds(584321) if w["kind"] == "interaction"):
        keys, rows = world["keys"], world["menu"]
        learned = learn(keys, rows)
        if learned is None or not verify(keys, rows, learned):
            raise ValueError("Missing learned partition")
        cells = list(product((0,1),repeat=len(keys)))
        block_of = {cell: block for block,members in learned.blocks.items() for cell in members}
        representatives = [min(group) for group in learned.blocks.values()]
        if len(representatives) != 2:
            raise ValueError("Expected exactly two inherited categories")
        rest = [cell for cell in cells if cell not in representatives]
        # The second verb has two new effects, each learned from a single demonstration.
        effects = {block_of[cell]: effect for cell,effect in zip(representatives,(-2,2))}
        for exception in [None, *rest]:
            def instrument(x, cell):
                change = effects[block_of[cell]] if cell != exception else 0
                return x+change

            by_block = {block_of[cell]:instrument(-10,cell)+10 for cell in representatives}
            for grants in (0,1,3,6):
                extra = rest[:grants]
                confirmed = {cell:instrument(20,cell)-20 for cell in extra}
                passes = all(delta == by_block[block_of[cell]] for cell,delta in confirmed.items())
                seen = {cell:by_block[block_of[cell]] for cell in representatives}
                seen.update(confirmed)
                correct = wrong = retained_correct = retained_wrong = 0
                for cell in cells:
                    prediction = 80+by_block[block_of[cell]]
                    truth = instrument(80,cell)
                    if passes:
                        correct += prediction == truth
                        wrong += prediction != truth
                    if cell in seen and 80+seen[cell] != truth:
                        raise ValueError("Lookup extrapolated beyond the measured effect")
                    # Exploratory fallback: a refuted global rule need not erase local evidence.
                    retained = None
                    if passes:
                        retained = prediction
                    elif cell in seen:
                        retained = 80+seen[cell]
                    if retained is not None:
                        retained_correct += retained == truth
                        retained_wrong += retained != truth
                records.append(dict(world=world["id"],grants=grants,exception=exception is not None,
                                    passes=passes,correct=correct,wrong=wrong,
                                    retained_correct=retained_correct,retained_wrong=retained_wrong,
                                    lookup_correct=len(seen),lookup_held=len(cells)-len(seen)))
    totals = {}
    for grants in (0,1,3,6):
        counts = Counter()
        for r in (r for r in records if r["grants"] == grants):
            counts.update(clean_accepted=int(r["passes"] and not r["exception"]),
                          exceptions_missed=int(r["passes"] and r["exception"]),
                          exceptions_caught=int(not r["passes"] and r["exception"]),
                          reuse_correct=r["correct"], reuse_wrong=r["wrong"],
                          reuse_held=8-r["correct"]-r["wrong"],lookup_correct=r["lookup_correct"],
                          lookup_held=r["lookup_held"],retained_correct=r["retained_correct"],
                          retained_wrong=r["retained_wrong"])
        totals[str(grants)] = counts
    return totals


if __name__ == "__main__":
    observed = measure()
    if observed != json.loads((HERE/"transfer_results.json").read_bytes()):
        raise ValueError("Transfer replay differs from archived observation")
    print(json.dumps(observed,indent=2))
