"""One probe selected from disagreements in a declared 301-rule family.

Consensus at an unmeasured input is conditional on this family containing the
true rule. Instrument readings remain exact evidence if the family fails.
"""

from collections.abc import Mapping
from copy import deepcopy
from typing import NamedTuple

from context_reader import choose, predict_consensus, update
from missing_setting import Session as EvidenceSession, _setting
from scale_probe import INPUT_LIMIT, OUTPUT_LIMIT, _bounded_integer, _measurement


class Rule(NamedTuple):
    q: int
    a: int
    b: int
    j: int = 0
    t: int = 0

    def delta(self, probe):
        x = probe["x"]
        return self.q * x * x + (self.a - 1) * x + self.b + self.j * (x >= self.t)


def rules():
    polynomials = tuple(Rule(q, a, b) for q in (-1, 0, 1)
                        for a in (-2, -1, 0, 1, 2) for b in range(-3, 4))
    thresholds = tuple(Rule(0, 1, b, j, t) for b in range(-3, 4)
                       for j in (-3, -1, 1, 3) for t in (-64, -16, -4, 0, 4, 16, 64))
    return polynomials + thresholds


class _CountedRule:
    def __init__(self, rule, counts, metric):
        self.rule = rule
        self.counts = counts
        self.metric = metric

    def delta(self, probe):
        self.counts[self.metric] += 1
        return self.rule.delta(probe)


class Session:
    """Preserve old settings and spend at most one new instrument request."""

    def __init__(self, verb, keys, history, initial, policy):
        if policy not in ("disagreement", "next"):
            raise ValueError("unknown observation policy")
        rows = deepcopy(list(history))
        first = deepcopy(initial)
        self._cell, self._x, self._y = _measurement(first, verb)
        for row in rows:
            cell, _, _ = _measurement(row, verb)
            if cell == self._cell:
                raise ValueError("target setting must be separate from history")
        self._baseline = EvidenceSession(verb, keys, rows)
        self._verb = verb
        self._policy = policy
        self._receipts = rows + [first]
        self._observed = {self._x: self._y}
        self._counts = dict(fit_evaluations=0, selection_evaluations=0,
                            update_evaluations=0, prediction_evaluations=0)
        self._survivors = rules()
        self._survivors = self._filter(first, "fit_evaluations")
        self._request = None
        self._status = "ready"

    def _counted(self, metric):
        return tuple(_CountedRule(rule, self._counts, metric) for rule in self._survivors)

    def _filter(self, reading, metric):
        return tuple(candidate.rule for candidate in update(self._counted(metric), reading))

    @property
    def receipts(self):
        return deepcopy(self._receipts)

    @property
    def spent(self):
        return int(self._request is not None)

    @property
    def status(self):
        return self._status

    @property
    def survivors(self):
        return self._survivors

    @property
    def counts(self):
        return dict(self._counts)

    def request(self):
        if self._status != "ready":
            return None
        if len(self._survivors) <= 1:
            self._status = "identified" if self._survivors else "no_model"
            return None
        if self._policy == "disagreement":
            inputs = sorted((x for x in range(-INPUT_LIMIT, INPUT_LIMIT + 1) if x != self._x),
                            key=lambda x: (abs(x - self._x), x))
            menu = tuple(dict(x=x) for x in inputs)
            x = menu[choose(self._counted("selection_evaluations"), menu)]["x"]
        else:
            x = self._x + 1
        if not _bounded_integer(x, INPUT_LIMIT):
            self._status = "out_of_bounds"
            return None
        self._request = dict(verb=self._verb, x=x, settings=list(self._cell))
        self._status = "pending"
        return deepcopy(self._request)

    def reply(self, reading):
        if self._request is None:
            return "no_request"
        if self._status != "pending":
            return self._status
        if reading is None:
            self._status = "unavailable"
            return self._status
        if isinstance(reading, Mapping) and reading.get("verb") != self._verb:
            self._status = "unrelated" if "verb" in reading else "invalid"
            return self._status
        try:
            cell, x, y = _measurement(reading, self._verb, require_verb=True)
        except ValueError:
            self._status = "invalid"
            return self._status
        if cell != self._cell or x != self._request["x"]:
            self._status = "unrelated"
            return self._status
        self._survivors = self._filter(reading, "update_evaluations")
        self._observed[x] = y
        self._receipts.append(deepcopy(reading))
        self._status = "identified" if len(self._survivors) == 1 else "ambiguous"
        if not self._survivors:
            self._status = "contradicted"
        return self._status

    def predict(self, x, settings):
        """Return observed truth or family consensus, keeping an unresolved query held."""
        cell = _setting(settings)
        if cell is None or not _bounded_integer(x, INPUT_LIMIT):
            return None
        if cell != self._cell:
            value = self._baseline.predict(x, cell)
        elif x in self._observed:
            value = self._observed[x]
        else:
            delta = predict_consensus(self._counted("prediction_evaluations"), dict(x=x))
            value = None if delta is None else x + delta
        return value if value is not None and abs(value) <= OUTPUT_LIMIT else None
