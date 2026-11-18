"""Protocol, selection and accounting controls without evaluation fixtures."""

from collections import Counter
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from disagreement_probe import Session, rules


VERB = "jel"
KEYS = ("north", "east", "west")
CELL = (1, 0, 1)


def history():
    return [dict(x=x, y=x + sum(cell), settings=list(cell))
            for cell in product((0, 1), repeat=3) if cell != CELL for x in (-3, 9)]


def first(x=-5, y=-5):
    return dict(x=x, y=y, settings=list(CELL))


def reader(policy="disagreement", x=-5, y=-5):
    return Session(VERB, KEYS, history(), first(x, y), policy)


def evaluate(rule, x):
    q, a, b, jump, threshold = rule
    return q * x ** 2 + a * x + b + (jump if x >= threshold else 0)


def check_family_and_selection():
    family = rules()
    assert len(family) == 301
    assert len({tuple(evaluate(rule, x) for x in range(-128, 129)) for rule in family}) == 301
    session = reader()
    candidates = session.survivors
    assert candidates == tuple(rule for rule in family if evaluate(rule, -5) == -5)
    assert len(candidates) == 29 and session.counts["fit_evaluations"] == 301
    ordered = sorted((x for x in range(-128, 129) if x != -5), key=lambda x: (abs(x + 5), x))
    costs = {x: max(Counter(evaluate(rule, x) for rule in candidates).values()) for x in ordered}
    expected = min(ordered, key=costs.get)
    request = session.request()
    assert request == dict(verb=VERB, x=expected, settings=list(CELL))
    assert request["x"] == 64 and session.counts["selection_evaluations"] == 29 * 256
    assert session.request() is None and session.spent == 1
    session.counts["selection_evaluations"] = 0
    assert session.counts["selection_evaluations"] == 29 * 256


def check_threshold_and_evidence():
    for policy, remaining in (("disagreement", 5), ("next", 25)):
        session = reader(policy)
        request = session.request()
        prior = session.survivors
        x = request["x"]
        response = dict(request, y=x + (x >= 0))
        assert session.reply(response) == "ambiguous"
        expected = tuple(rule for rule in prior if evaluate(rule, x) == response["y"])
        assert session.survivors == expected and len(expected) == remaining
        assert session.counts["update_evaluations"] == 29
        for row in history() + [first(), response]:
            assert session.predict(row["x"], row["settings"]) == row["y"]
        assert session.counts["prediction_evaluations"] == 0
        assert session.receipts == history() + [first(), response]
        assert session.predict(100, CELL) == (101 if policy == "disagreement" else None)
        assert session.counts["prediction_evaluations"] == remaining
        assert session.predict(0, CELL) is None
        assert session.counts["prediction_evaluations"] == 2 * remaining
        assert session.reply(dict(response, y=777)) == "ambiguous"
        assert session.survivors == expected and session.request() is None


def check_denial_and_invalid():
    cases = (
        (lambda r: None, "unavailable"),
        (lambda r: dict(r, verb="other"), "unrelated"),
        (lambda r: dict(r, x=r["x"] - 1), "unrelated"),
        (lambda r: dict(r, settings=[0, 0, 0]), "unrelated"),
        (lambda r: dict(r, settings=[1, False, 1]), "invalid"),
        (lambda r: dict(r, y=True), "invalid"),
        (lambda r: dict(r, y=1_000_001), "invalid"),
        (lambda r: {k: v for k, v in r.items() if k != "verb"}, "invalid"),
        (lambda r: [r, r], "invalid"),
    )
    for transform, status in cases:
        session = reader()
        request = session.request()
        original, candidates = session.receipts, session.survivors
        counts = session.counts
        assert session.reply(transform(dict(request, y=65))) == status
        assert session.survivors == candidates and session.receipts == original
        assert session.counts == counts
        assert session.reply(dict(request, y=65)) == status
        assert session.request() is None and session.spent == 1


def check_contradiction_and_early_stop():
    session = reader()
    request = session.request()
    assert session.reply(dict(request, y=100_000)) == "contradicted"
    assert session.survivors == () and session.predict(1, CELL) is None
    assert session.predict(request["x"], CELL) == 100_000
    assert session.predict(-5, CELL) == -5
    assert session.predict(7, (0, 0, 0)) == 7
    assert session.counts["update_evaluations"] == 29
    assert session.counts["prediction_evaluations"] == 0
    for policy in ("disagreement", "next"):
        unique = reader(policy, 8, 80)
        assert len(unique.survivors) == 1 and unique.request() is None
        assert unique.status == "identified" and unique.spent == 0
        assert unique.predict(6, CELL) == 48
        absent = reader(policy, 0, 999_999)
        assert absent.request() is None and absent.status == "no_model"
        assert absent.predict(0, CELL) == 999_999 and absent.predict(1, CELL) is None
        assert absent.spent == 0 and absent.reply(None) == "no_request"
    edge = reader("next", 128, 128)
    assert edge.request() is None and edge.status == "out_of_bounds" and edge.spent == 0
    assert reader("disagreement", 128, 128).request() is not None


def check_isolation():
    rows, initial = history(), first()
    session = Session(VERB, KEYS, rows, initial, "disagreement")
    rows[0]["settings"].clear()
    initial["y"] = 99
    request = session.request()
    request["settings"].clear()
    response = dict(verb=VERB, settings=list(CELL), x=request["x"], y=65)
    assert session.reply(response) == "ambiguous"
    response["y"] = 99
    session.receipts[-1]["settings"].clear()
    assert session.predict(-5, CELL) == -5 and session.predict(64, CELL) == 65
    assert session.predict(-3, (0, 0, 0)) == -3
    assert session.predict(True, CELL) is None
    assert session.predict(129, CELL) is None


if __name__ == "__main__":
    for check in (check_family_and_selection, check_threshold_and_evidence,
                  check_denial_and_invalid, check_contradiction_and_early_stop, check_isolation):
        check()
        print(f"PASS {check.__name__}")
