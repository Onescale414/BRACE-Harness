"""One domain, one named action, and one optional measurement of an unseen setting.

Predictions assume a constant integer offset at a fixed three-bit setting.
Only agreeing measurements of that exact setting authorize a numeric answer.
"""

from collections import Counter
from collections.abc import Mapping
from itertools import product

from context_reader import certify


# Exact integer interchange with JSON consumers that store numbers as doubles.
MAX_INTEGER = 2**53 - 1


def _integer(value):
    return type(value) is int and -MAX_INTEGER <= value <= MAX_INTEGER


def _setting(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    if any(type(bit) is not int or bit not in (0, 1) for bit in value):
        return None
    return tuple(value)


def _receipt(row):
    if not isinstance(row, Mapping):
        raise ValueError("a measurement must be a record")
    setting = _setting(row.get("settings"))
    x, y = row.get("x"), row.get("y")
    if setting is None or not _integer(x) or not _integer(y) or not _integer(y - x):
        raise ValueError("a measurement requires three bits and exact integer endpoints and offset")
    return setting, x, y - x


class Session:
    """Keep measurements within this instance. An opening history is caller-verified."""

    def __init__(self, verb, keys, receipts):
        if not isinstance(verb, str) or not verb:
            raise ValueError("expected a named verb")
        if isinstance(keys, (str, bytes)):
            raise ValueError("expected three coordinate names")
        self._keys = tuple(keys)
        if (len(self._keys) != 3 or any(not isinstance(k, str) or not k for k in self._keys)
                or len(set(self._keys)) != 3):
            raise ValueError("expected three distinct coordinate names")
        self._verb = verb
        self._offsets = {}
        self._target = None
        self._result = None
        for row in receipts:
            setting, _, delta = _receipt(row)
            if row.get("verb", verb) != verb:
                raise ValueError("history contains another verb")
            if self._offsets.setdefault(setting, delta) != delta:
                self._offsets[setting] = None

    @property
    def spent(self):
        """A request consumes the one opportunity even if no reading arrives."""
        return int(self._target is not None)

    @property
    def pending(self):
        if self._target is None or self._result is not None:
            return None
        setting, x = self._target
        return {"verb": self._verb, "x": x, "settings": list(setting)}

    def predict(self, x, settings):
        """Return an exact endpoint for an agreeing witnessed cell, else None."""
        delta = self._offsets.get(_setting(settings))
        if delta is None or not _integer(x) or not _integer(x + delta):
            return None
        return x + delta

    def request(self, requested_settings=None, x=0, allowed=True):
        """Choose an unseen setting. With no demand list, enumerate the binary controls."""
        if self.spent or allowed is not True or not _integer(x):
            return None
        if requested_settings is None:
            requested_settings = product((0, 1), repeat=len(self._keys))
        counts = Counter()
        for value in requested_settings:
            setting = _setting(value)
            if setting is None:
                raise ValueError("requested settings must each contain three bits")
            if setting not in self._offsets:
                counts[setting] += 1
        if counts:
            self._target = max(counts, key=counts.get), x
        return self.pending

    def _accept(self, receipts):
        if receipts is None:
            return "no_reading"
        if isinstance(receipts, Mapping):
            receipts = [receipts]
        if isinstance(receipts, (str, bytes)):
            return "invalid"
        deltas = set()
        count = 0
        try:
            for row in receipts:
                setting, x, delta = _receipt(row)
                if not isinstance(row.get("verb"), str) or not row["verb"]:
                    return "invalid"
                if row.get("verb") != self._verb or (setting, x) != self._target:
                    return "unrelated"
                deltas.add(delta)
                count += 1
        except (ValueError, TypeError):
            return "invalid"
        if not deltas:
            return "no_reading"
        setting, _ = self._target
        if len(deltas) > 1:
            self._offsets[setting] = None
            return "conflict"
        if count != 1:
            return "invalid"
        delta = deltas.pop()
        # The narrower reader can label an observed exception. Its extrapolation
        # never grants permission to answer an unwitnessed query.
        base = None
        if None not in self._offsets.values():
            rows = ({"x": 0, "y": old, "features": dict(zip(self._keys, cell))}
                    for cell, old in self._offsets.items())
            base = certify(self._keys, rows)
        self._offsets[setting] = delta
        if base is None:
            return "accepted_local"
        expected = base.delta({"features": dict(zip(self._keys, setting))})
        return "accepted_base" if expected == delta else "local_override"

    def reply(self, receipts):
        """Resolve the request once. Repeated replies return the same terminal result."""
        if self._target is None:
            return "no_request"
        if self._result is None:
            self._result = self._accept(receipts)
        return self._result
