"""Independent protocol controls for the one-extra-reading scale comparison."""

from fractions import Fraction
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scale_probe import ScaleSession


TARGET = (1, 0, 1)
VERB = "zel"
KEYS = ("first", "second", "third")


def history():
    return [dict(x=x, y=x + sum(cell), settings=list(cell))
            for cell in product((0, 1), repeat=3) if cell != TARGET for x in (-3, 9)]


def initial(x=4):
    return dict(x=x, y=3 * x - 5, settings=list(TARGET))


def session(policy="double", x=4):
    return ScaleSession(VERB, KEYS, history(), initial(x), policy)


def check_boundaries():
    for policy, x, status in (("double", 0, "duplicate_probe"),
                              ("double", 80, "out_of_bounds"),
                              ("double", -80, "out_of_bounds"),
                              ("next", 128, "out_of_bounds")):
        reader = session(policy, x)
        assert reader.request() is None and reader.spent == 0
        assert reader.status == status and reader.reply(None) == "no_request"
        assert reader.predict(x, TARGET) == 3 * x - 5
        assert reader.predict(1, TARGET) is None
    for policy, x, expected in (("double", -64, -128), ("double", 64, 128),
                               ("next", -128, -127), ("next", 0, 1)):
        reader = session(policy, x)
        assert reader.request()["x"] == expected and reader.spent == 1


def check_affine_fit_and_preservation():
    for policy in ("double", "next"):
        reader = session(policy)
        request = reader.request()
        assert reader.predict(13, TARGET) is None
        assert reader.reply(dict(request, y=3 * request["x"] - 5)) == "fitted"
        assert reader.coefficients == (3, -5) and reader.offset_changed is True
        assert reader.predict(13, TARGET) == 34
        for row in history() + [initial()]:
            assert reader.predict(row["x"], row["settings"]) == row["y"]
        assert reader.receipts[:15] == history() + [initial()]
        assert reader.request() is None and reader.spent == 1
        assert reader.reply(dict(request, y=999)) == "fitted"
        assert reader.predict(13, TARGET) == 34

    reader = session()
    request = reader.request()
    assert reader.reply(dict(request, y=8)) == "fitted"
    assert reader.coefficients == (Fraction(1, 4), 6)
    assert reader.predict(5, TARGET) == Fraction(29, 4)


def check_invalid_and_unavailable():
    modifiers = (
        (lambda r: None, "unavailable"),
        (lambda r: dict(r, verb="different"), "unrelated"),
        (lambda r: dict(r, x=r["x"] + 1), "unrelated"),
        (lambda r: dict(r, settings=[0, 0, 0]), "unrelated"),
        (lambda r: dict(r, settings=[True, 0, 1]), "invalid"),
        (lambda r: dict(r, y=True), "invalid"),
        (lambda r: dict(r, y=1_000_001), "invalid"),
        (lambda r: {k: v for k, v in r.items() if k != "verb"}, "invalid"),
        (lambda r: [r, r], "invalid"),
    )
    for modify, expected in modifiers:
        reader = session()
        request = reader.request()
        assert reader.reply(modify(dict(request, y=19))) == expected
        assert reader.reply(dict(request, y=19)) == expected
        assert reader.coefficients is None and reader.offset_changed is None
        assert reader.predict(13, TARGET) is None and reader.predict(4, TARGET) == 7
        assert reader.receipts == history() + [initial()]
        assert reader.request() is None and reader.spent == 1


def check_isolation_and_zero():
    rows, first = history(), initial()
    reader = ScaleSession(VERB, KEYS, rows, first, "next")
    rows[0]["settings"].clear()
    first["y"] = 999
    request = reader.request()
    reply = dict(request, y=0)
    request["settings"].clear()
    reply["settings"] = list(TARGET)
    assert reader.reply(reply) == "fitted"
    reply["y"] = 999
    reader.receipts[-1]["settings"].clear()
    assert reader.predict(5, TARGET) == 0 and reader.predict(4, TARGET) == 7
    assert reader.receipts[0]["settings"] == [0, 0, 0]
    for change in (dict(x=True), dict(y=1_000_001), dict(settings=[1, 0, False])):
        try:
            ScaleSession(VERB, KEYS, history(), dict(initial(), **change), "next")
        except ValueError:
            continue
        raise AssertionError("malformed starting evidence was admitted")


if __name__ == "__main__":
    for check in (check_boundaries, check_affine_fit_and_preservation,
                  check_invalid_and_unavailable, check_isolation_and_zero):
        check()
        print(f"PASS {check.__name__}")
