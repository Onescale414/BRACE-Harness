"""Request one binary source field after identical scalar inputs disagree.

Rows belong to one domain and one action. Each has an independent receipt
ID, integer x, and measured integer y. The caller acquires aligned readings
of the selected field and accounts for each fit, confirmation, and query read.
"""

from collections.abc import Mapping
from typing import NamedTuple


class Candidate(NamedTuple):
    field: str
    offsets: tuple[int, int]
    fit_ids: frozenset


class Confirmed(NamedTuple):
    candidate: Candidate
    confirmation_ids: frozenset


def _receipt_ids(rows):
    ids = set()
    for row in rows:
        if not isinstance(row, Mapping) or row.get("id") is None:
            return None
        if type(row.get("x")) is not int or type(row.get("y")) is not int:
            return None
        try:
            if row["id"] in ids:
                return None
            ids.add(row["id"])
        except TypeError:
            return None
    return frozenset(ids)


def _has_conflict(rows):
    outputs = {}
    for row in rows:
        if outputs.setdefault(row["x"], row["y"]) != row["y"]:
            return True
    return False


def _binary(value):
    return type(value) in (int, bool) and value in (0, 1)


def _offsets(rows, values):
    if len(rows) != len(values):
        return None
    offsets = {}
    for row, bit in zip(rows, values):
        if not _binary(bit):
            return None
        delta = row["y"] - row["x"]
        if offsets.setdefault(bit, delta) != delta:
            return None
    if len(offsets) != 2 or offsets[0] == offsets[1]:
        return None
    return offsets[0], offsets[1]


def summarize_catalog(rows, channels, fit_channels):
    """Summarize archived field columns, in menu order, for this history.

    A present column supplies one reading per row, including None for an
    unavailable reading. Count every supplied cell inspected, including
    missing markers. An absent column has no cells to inspect.
    """
    rows = tuple(rows)
    has_conflict = _receipt_ids(rows) is not None and _has_conflict(rows)
    catalog = []
    if fit_channels is None:
        fit_channels = {}
    for field in dict.fromkeys(channels):
        column = fit_channels.get(field)
        values = [] if column is None else list(column)
        catalog.append({
            "field": field,
            "archived_cells": len(values),
            "discriminates": has_conflict and _offsets(rows, values) is not None,
        })
    return catalog


def choose(rows, catalog):
    """Choose the first complete discriminator for the supplied history."""
    rows = tuple(rows)
    if _receipt_ids(rows) is None or not _has_conflict(rows):
        return None
    for entry in catalog or ():
        if (entry.get("discriminates") is True and entry.get("archived_cells") == len(rows)
                and isinstance(entry.get("field"), str) and entry["field"]):
            return entry["field"]
    return None


def bind(field, rows, values):
    """Fit one field from aligned source readings. The result is provisional."""
    if not isinstance(field, str) or not field or values is None:
        return None
    rows = tuple(rows)
    ids = _receipt_ids(rows)
    if ids is None or not _has_conflict(rows):
        return None
    offsets = _offsets(rows, tuple(values))
    if offsets is None:
        return None
    return Candidate(field, offsets, ids)


def confirm(candidate, rows, values):
    """Check every fresh source receipt and require support for both levels."""
    if not isinstance(candidate, Candidate) or values is None:
        return None
    rows, values = tuple(rows), tuple(values)
    ids = _receipt_ids(rows)
    if ids is None or not ids.isdisjoint(candidate.fit_ids) or len(rows) != len(values):
        return None
    levels = set()
    for row, bit in zip(rows, values):
        if not _binary(bit) or row["x"] + candidate.offsets[bit] != row["y"]:
            return None
        levels.add(bit)
    if len(levels) != 2:
        return None
    return Confirmed(candidate, ids)


def predict(confirmed, x, bit):
    """Return an endpoint for a confirmed field reading, or None to hold."""
    if not isinstance(confirmed, Confirmed) or type(x) is not int or not _binary(bit):
        return None
    return x + confirmed.candidate.offsets[bit]
