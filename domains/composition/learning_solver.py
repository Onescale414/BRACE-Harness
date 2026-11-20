"""Bounded local proposals, with safe algebraic pruning and exact modular bands.

The compiled index screens necessary conditions and orders proposals.
Independent checks remain mandatory for every publication.
All compiled structures are immutable and derived here, never loaded from data.
"""

import hashlib
import itertools
import json
from pathlib import Path
import time
from types import MappingProxyType

import composition_checker as checker


OPS = ("add1", "sub1", "double", "square")
MAX_STEPS, MAX_CANDIDATES, MAX_SCALARS, MAX_CHECKS = 4, 85, 252, 2
MAX_INPUT, MAX_VALUE = 10**6, 10**48
TIMEOUT_NS = 25_000_000_000
MODULI = (2, 3, 5, 7)
PROBES = (0, -1, 1, -2, 2, -3, 3, -4, 4)
CANONICAL = tuple(p for n in range(MAX_STEPS + 1) for p in itertools.product(OPS, repeat=n))


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def valid_plan(plan):
    return (type(plan) is tuple and len(plan) <= MAX_STEPS
            and all(type(op) is str and op in OPS for op in plan))


def _step(value, op):
    if op == "add1":
        return value + 1
    if op == "sub1":
        return value - 1
    return value * 2 if op == "double" else value * value


def _compile():
    started = time.perf_counter_ns()
    costs = dict.fromkeys(("prefix_transforms", "coefficient_additions", "coefficient_multiplications",
                          "interval_transforms", "candidate_records", "safe_class_lookups",
                          "index_plan_steps", "index_remainders", "cell_bit_insertions"), 0)
    prefixes = {(): ((0, 1), -MAX_INPUT, MAX_INPUT, True)}
    representatives, keys, records, order = {}, {}, [], []
    for plan in CANONICAL:
        if plan:
            poly, lo, hi, safe = prefixes[plan[:-1]]
            out, op = list(poly), plan[-1]
            if op in ("add1", "sub1"):
                delta = 1 if op == "add1" else -1
                out[0] += delta
                lo, hi = lo + delta, hi + delta
                costs["coefficient_additions"] += 1
            elif op == "double":
                out = [2 * c for c in out]
                lo, hi = 2 * lo, 2 * hi
                costs["coefficient_multiplications"] += len(out)
            else:
                product = [0] * (2 * len(out) - 1)
                for i, a in enumerate(out):
                    for j, b in enumerate(out):
                        product[i + j] += a * b
                        costs["coefficient_multiplications"] += 1
                        costs["coefficient_additions"] += 1
                out = product
                a, b = lo * lo, hi * hi
                lo, hi = (0 if lo <= 0 <= hi else min(a, b)), max(a, b)
            while len(out) > 1 and out[-1] == 0:
                out.pop()
            prefixes[plan] = (tuple(out), lo, hi, safe and lo >= -MAX_VALUE and hi <= MAX_VALUE)
            costs["prefix_transforms"] += 1
            costs["interval_transforms"] += 1
        poly, lo, hi, safe = prefixes[plan]
        key = ("polynomial", poly) if safe else ("plan", plan)
        keys[plan] = key
        if safe:
            costs["safe_class_lookups"] += 1
        keep = not safe or poly not in representatives
        if keep:
            order.append(plan)
            if safe:
                representatives[poly] = plan
        records.append((plan, poly, lo, hi, safe, keep, representatives.get(poly) if safe else plan))
        costs["candidate_records"] += 1
    index = []
    for modulus in MODULI:
        cells = [0] * (modulus * modulus)
        for rank, plan in enumerate(order):
            for residue in range(modulus):
                value = residue
                for op in plan:
                    value = _step(value, op) % modulus
                    costs["index_plan_steps"] += 1
                    costs["index_remainders"] += 1
                cells[residue * modulus + value] |= 1 << rank
                costs["cell_bit_insertions"] += 1
        index.append(tuple(cells))
    order, records, index = tuple(order), tuple(records), tuple(index)
    catalog_digest = _sha(_encoded((CANONICAL, records, order, MODULI, index)))
    setup = {"compile_ns": time.perf_counter_ns() - started, "source_plans": len(CANONICAL),
             "retained_plans": len(order), "removed_plans": len(CANONICAL) - len(order),
             "cells": sum(len(cells) for cells in index), "max_mask_bits": len(order),
             "index_serialized_bytes": len(_encoded(index)), "catalog_digest": catalog_digest,
             "work": MappingProxyType(costs)}
    return order, MappingProxyType(keys), records, index, catalog_digest, MappingProxyType(setup)


ORDER, CLASSES, CERTIFICATES, INDEX, CATALOG_DIGEST, SETUP = _compile()
CLASS_RANKS = MappingProxyType({CLASSES[plan]: rank for rank, plan in enumerate(ORDER)})
FULL = (1 << len(ORDER)) - 1
CONTRACT = _sha(_encoded({
    "profile": "bounded-learning-solver-v1", "module": _sha(Path(__file__).read_bytes()),
    "checker": _sha(Path(checker.__file__).read_bytes()), "catalog": CATALOG_DIGEST,
    "limits": (MAX_STEPS, MAX_CANDIDATES, MAX_SCALARS, MAX_CHECKS, MAX_INPUT, MAX_VALUE, TIMEOUT_NS),
    "probes": PROBES, "index_representation": "modulus-row-major-integer-bitmasks-v1",
}))


def setup_metadata():
    return {**SETUP, "work": dict(SETUP["work"])}


def class_key(plan):
    """Only globally safe polynomial aliases share a key; unsafe plans stay exact."""
    return CLASSES[plan] if valid_plan(plan) else None


class Stop(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Budget:
    def __init__(self, clock=time.monotonic_ns):
        self.clock = clock
        self.expires_ns = clock() + TIMEOUT_NS
        self.work = dict.fromkeys(("candidate_slots", "pin_comparisons", "proposal_scalar_operations",
                                  "cache_hits", "full_checks", "checker_scalar_operations"), 0)

    def deadline(self):
        if self.clock() >= self.expires_ns:
            raise Stop("deadline")

    def take_slot(self):
        self.deadline()
        if self.work["candidate_slots"] >= MAX_CANDIDATES:
            raise Stop("proposal-budget")
        self.work["candidate_slots"] += 1

    def scalar(self):
        self.deadline()
        if self.work["proposal_scalar_operations"] >= MAX_SCALARS:
            raise Stop("proposal-budget")
        self.work["proposal_scalar_operations"] += 1

    def check(self, rows, plan):
        self.deadline()
        if self.work["full_checks"] >= MAX_CHECKS:
            raise Stop("check-budget")
        self.work["full_checks"] += 1
        result = checker.check(rows, plan, max_steps=MAX_STEPS)
        self.work["checker_scalar_operations"] += result.scalar_operations
        self.deadline()
        return result


def eval_plan(plan, value, budget):
    if not valid_plan(plan):
        raise Stop("invalid-plan")
    if type(value) is not int or abs(value) > MAX_INPUT:
        raise Stop("integer-limit")
    budget.deadline()
    for op in plan:
        budget.scalar()
        value = _step(value, op)
        if abs(value) > MAX_VALUE:
            raise Stop("integer-limit")
    budget.deadline()
    return value


class Search:
    """Lazy priorities and fallback share a budget and a bounded prefix cache."""
    def __init__(self, rows, budget, bands=True):
        checker._validate_examples(rows)
        if type(bands) is not bool:
            raise ValueError("unsupported-mode")
        self.budget, self.cache = budget, {}
        self.band_constraints = []
        self.bands = bands
        self.filter_witness = None
        self.metadata = dict.fromkeys(("source_rows_inspected", "input_equality_comparisons",
            "feature_rows_read", "remainder_operations", "band_lookups", "mask_intersections",
            "mask_popcounts", "bit_extracts", "bit_operations", "rank_decrements",
            "priority_visits", "fallback_visits", "order_entries_examined", "class_lookups",
            "excluded_entries", "proposal_filter_lookups", "proposal_filter_passes",
            "proposal_filter_rejections", "filter_constraint_reads", "filter_bit_operations"), 0)
        selected = []
        for pair in rows:
            budget.deadline()
            self.metadata["source_rows_inspected"] += 1
            duplicate = False
            for old in selected:
                budget.deadline()
                self.metadata["input_equality_comparisons"] += 1
                if old[0] == pair[0]:
                    duplicate = True
                    break
            if not duplicate:
                selected.append(pair)
                if len(selected) == 3:
                    break
        self.examples = tuple(selected)
        self.priority = 0
        if bands:
            self.priority = FULL
            for modulus, cells in zip(MODULI, INDEX):
                for row, (x, y) in enumerate(rows):
                    self.metadata["feature_rows_read"] += 1
                    budget.scalar()
                    r = x % modulus
                    self.metadata["remainder_operations"] += 1
                    budget.scalar()
                    s = y % modulus
                    self.metadata["remainder_operations"] += 1
                    bucket = cells[r * modulus + s]
                    self.band_constraints.append((modulus, row, r, s, bucket))
                    self.priority &= bucket
                    self.metadata["band_lookups"] += 1
                    self.metadata["mask_intersections"] += 1
            self.metadata["mask_popcounts"] += 1
        self.metadata.update(priority_mask_hex=hex(self.priority), priority_count=self.priority.bit_count())
        budget.deadline()

    def permits(self, plan):
        """One-way rejection for certified-safe plans; None means defer to checker.

        Query residues are already charged in __init__ and reused by fallback.
        A witness records a violated compiled necessary condition, not a check.
        """
        self.budget.deadline()
        if not valid_plan(plan):
            raise Stop('invalid-plan')
        self.filter_witness = None
        key = CLASSES[plan]
        if not self.bands or key[0] != 'polynomial':
            return None
        self.metadata['proposal_filter_lookups'] += 1
        self.metadata['class_lookups'] += 1
        rank = CLASS_RANKS[key]
        bit = 1 << rank
        self.metadata['filter_bit_operations'] += 2  # shift and combined-mask AND
        if self.priority & bit:
            self.metadata['proposal_filter_passes'] += 1
            self.budget.deadline()
            return True
        for modulus, row, r, s, bucket in self.band_constraints:
            self.budget.deadline()
            self.metadata['filter_constraint_reads'] += 1
            self.metadata['filter_bit_operations'] += 1
            if not bucket & bit:
                self.filter_witness = {'modulus': modulus, 'row': row, 'input_residue': r,
                                       'target_residue': s, 'class_rank': rank}
                self.metadata['proposal_filter_rejections'] += 1
                self.budget.deadline()
                return False
        raise Stop('filter-inconsistent')

    def value(self, prefix, row):
        self.budget.deadline()
        if not prefix:
            return self.examples[row][0]
        key = (prefix, row)
        if key in self.cache:
            self.budget.work["cache_hits"] += 1
            return self.cache[key]
        value = self.value(prefix[:-1], row)
        self.budget.scalar()
        value = _step(value, prefix[-1])
        if abs(value) > MAX_VALUE:
            raise Stop("integer-limit")
        self.cache[key] = value
        return value

    def candidates(self, exclude=()):
        self.metadata["bit_operations"] += 1
        for label, mask in (("priority_visits", self.priority), ("fallback_visits", FULL ^ self.priority)):
            while mask:
                self.budget.take_slot()
                bit = mask & -mask
                rank = bit.bit_length() - 1
                mask ^= bit
                self.metadata["bit_extracts"] += 1
                self.metadata["bit_operations"] += 4
                self.metadata["rank_decrements"] += 1
                self.metadata["order_entries_examined"] += 1
                self.metadata[label] += 1
                plan = ORDER[rank]
                self.metadata["class_lookups"] += 1
                if CLASSES[plan] in exclude:
                    self.metadata["excluded_entries"] += 1
                    continue
                for row, (_, target) in enumerate(self.examples):
                    self.budget.work["pin_comparisons"] += 1
                    if self.value(plan, row) != target:
                        break
                else:
                    self.budget.deadline()
                    yield plan
