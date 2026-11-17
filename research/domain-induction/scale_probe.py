"""One additional input probe, with affine extrapolation kept conditional.

The instrument returns exact integer readings. A fitted line at the target
setting is a hypothesis for new inputs. Other settings keep their old evidence.
"""

from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction

from missing_setting import Session, _setting


INPUT_LIMIT = 128
OUTPUT_LIMIT = 1_000_000


def _bounded_integer(value, limit):
    return type(value) is int and -limit <= value <= limit


def _measurement(row, verb, require_verb=False):
    if not isinstance(row, Mapping):
        raise ValueError("a reading must be a record")
    setting = _setting(row.get("settings"))
    if (setting is None or not _bounded_integer(row.get("x"), INPUT_LIMIT)
            or not _bounded_integer(row.get("y"), OUTPUT_LIMIT)):
        raise ValueError("a reading requires three bits and bounded integer endpoints")
    if require_verb and "verb" not in row:
        raise ValueError("an instrument reply must name the action")
    if row.get("verb", verb) != verb:
        raise ValueError("a reading belongs to another action")
    return setting, row["x"], row["y"]


class ScaleSession:
    """Use one granted reading to fit a line at one previously observed setting."""

    def __init__(self, verb, keys, history, initial, policy):
        if policy not in ("double", "next"):
            raise ValueError("unknown input selection policy")
        rows = deepcopy(list(history))
        first = deepcopy(initial)
        self._cell, self._x, self._y = _measurement(first, verb)
        for row in rows:
            cell, _, _ = _measurement(row, verb)
            if cell == self._cell:
                raise ValueError("initial target setting must be separate from history")
        self._baseline = Session(verb, keys, rows)
        self._verb = verb
        self._policy = policy
        self._receipts = rows + [first]
        self._observed = {self._x: self._y}
        self._fit = None
        self._request = None
        self._status = "ready"
        self._offset_changed = None

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
    def coefficients(self):
        """Return the immutable (slope, intercept) pair, or None."""
        return self._fit

    @property
    def offset_changed(self):
        return self._offset_changed

    def request(self):
        if self._status != "ready":
            return None
        x = 2 * self._x if self._policy == "double" else self._x + 1
        if x == self._x:
            self._status = "duplicate_probe"
            return None
        if not _bounded_integer(x, INPUT_LIMIT):
            self._status = "out_of_bounds"
            return None
        self._request = dict(verb=self._verb, x=x, settings=list(self._cell))
        self._status = "pending"
        return deepcopy(self._request)

    def reply(self, reading):
        """Bind one terminal reply to the exact request before changing evidence."""
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
        slope = Fraction(y - self._y, x - self._x)
        self._fit = slope, self._y - slope * self._x
        self._observed[x] = y
        self._receipts.append(deepcopy(reading))
        self._offset_changed = y - x != self._y - self._x
        self._status = "fitted"
        return self._status

    def predict(self, x, settings):
        """Return a measured value or an estimate under the setting's model.

Target extrapolations assume an affine effect. Existing settings retain their
previous fixed-offset assumption. Every returned value respects output bounds.
"""
        cell = _setting(settings)
        if cell is None or not _bounded_integer(x, INPUT_LIMIT):
            return None
        if cell != self._cell:
            value = self._baseline.predict(x, cell)
        elif x in self._observed:
            value = self._observed[x]
        elif self._fit is None:
            return None
        else:
            slope, intercept = self._fit
            value = slope * x + intercept
        return value if value is not None and abs(value) <= OUTPUT_LIMIT else None
