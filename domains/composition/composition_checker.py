"""Independent checks that a bounded integer plan matches four supplied examples.

A checked result establishes agreement with these observations only. It does
not establish the caller's intended function or behavior on other inputs.
"""

import json
from dataclasses import dataclass


OPS = ("add1", "sub1", "double", "square")
MAX_STEPS = 3
MAX_SOURCE_BYTES = 2048
MAX_INPUT = 10**6
MAX_VALUE = 10**48


@dataclass(frozen=True, slots=True)
class CheckResult:
    status: str
    failed_rows: tuple[int, ...] = ()
    outputs: tuple[int, ...] = ()
    scalar_operations: int = 0


def _unique_fields(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("unsupported-input")
    return result


def _reject_number(_value):
    raise ValueError("unsupported-input")


def _limit_nesting(source: bytes) -> None:
    """Reject nesting beyond the required object/rows/pair shape before parsing."""
    depth = 0
    quoted = escaped = False
    for value in source:
        if quoted:
            if escaped:
                escaped = False
            elif value == 92:
                escaped = True
            elif value == 34:
                quoted = False
        elif value == 34:
            quoted = True
        elif value in (91, 123):
            depth += 1
            if depth > 3:
                raise ValueError("unsupported-input")
        elif value in (93, 125):
            depth -= 1


def _validate_examples(examples, container_type=tuple) -> None:
    if type(examples) is not container_type or len(examples) != 4:
        raise ValueError("unsupported-input")
    seen = {}
    for pair in examples:
        if type(pair) is not container_type or len(pair) != 2:
            raise ValueError("unsupported-input")
        x, y = pair
        if type(x) is not int or type(y) is not int:
            raise ValueError("unsupported-input")
        if abs(x) > MAX_INPUT or abs(y) > MAX_VALUE:
            raise ValueError("integer-limit")
        if x in seen and seen[x] != y:
            raise ValueError("conflicting-examples")
        seen[x] = y


def admit(source: bytes) -> tuple[tuple[int, int], ...]:
    """Admit exactly four JSON example rows and return immutable observations.

The sole object field is ``examples``. Repeated inputs are allowed only when
their targets agree. Admission does not establish that a matching plan exists.
"""
    if type(source) is not bytes:
        raise ValueError("unsupported-input")
    if len(source) > MAX_SOURCE_BYTES:
        raise ValueError("input-limit")
    _limit_nesting(source)
    try:
        obj = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_unique_fields,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (ValueError, RecursionError) as exc:
        raise ValueError("unsupported-input") from exc
    if type(obj) is not dict or obj.keys() != {"examples"}:
        raise ValueError("unsupported-input")
    examples = obj["examples"]
    _validate_examples(examples, list)
    return tuple(tuple(pair) for pair in examples)


def check(examples, plan, *, max_steps=None) -> CheckResult:
    """Independently evaluate a complete plan on all four admitted examples.

Only exact tuple inputs and exact built-in integer/string values are accepted.
Every arithmetic operation and intermediate integer is checked locally. Output
differences are collected across all rows; malformed or oversized values fail
early. A ``checked`` result certifies only the supplied examples.
"""
    try:
        _validate_examples(examples)
    except ValueError as exc:
        status = "integer-limit" if str(exc) == "integer-limit" else "invalid-examples"
        return CheckResult(status)
    depth = MAX_STEPS if max_steps is None else max_steps
    if type(depth) is not int or not 0 <= depth <= 4:
        return CheckResult("invalid-profile")
    if (
        type(plan) is not tuple
        or len(plan) > depth
        or any(type(op) is not str or op not in OPS for op in plan)
    ):
        return CheckResult("invalid-plan")

    outputs = []
    failed_rows = []
    scalar_operations = 0
    for row, (value, target) in enumerate(examples):
        for op in plan:
            scalar_operations += 1
            if op == "add1":
                value += 1
            elif op == "sub1":
                value -= 1
            elif op == "double":
                value *= 2
            else:
                value *= value
            if abs(value) > MAX_VALUE:
                return CheckResult("integer-limit", (row,), tuple(outputs), scalar_operations)
        outputs.append(value)
        if value != target:
            failed_rows.append(row)
    return CheckResult(
        "different-output" if failed_rows else "checked",
        tuple(failed_rows),
        tuple(outputs),
        scalar_operations,
    )
