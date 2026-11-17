"""Run the public synthetic controls with python -I -S -B missing_setting_controls.py."""

from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from missing_setting import MAX_INTEGER, Session


VERB = "wex"
KEYS = ("q17", "k03", "j28")
CELLS = tuple(product(range(2), repeat=3))
FIRST, SECOND = (1, 0, 0), (0, 0, 1)
X = -2


def history():
    # The four even-parity settings distinguish the first bit from its peers.
    return [dict(settings=list(cell), x=9, y=9 + cell[0])
            for cell in CELLS if sum(cell) % 2 == 0]


def fresh():
    return Session(VERB, KEYS, history())


def report(**changes):
    return dict({"verb": VERB, "x": X, "settings": list(SECOND), "y": X}, **changes)


def open_request():
    session = fresh()
    assert session.request([FIRST, SECOND, SECOND], x=X) == {
        "verb": VERB, "x": X, "settings": list(SECOND),
    }
    return session


def predictions(session):
    return {cell: session.predict(19, cell) for cell in CELLS}


def selection_and_denial():
    session = fresh()
    assert session.request([SECOND], allowed=False) is None and session.spent == 0
    assert session.reply(report()) == "no_request"
    assert session.request([]) is None
    assert session.request([CELLS[0]] * 3) is None and session.spent == 0
    assert session.request([CELLS[0]] * 5 + [FIRST, SECOND])["settings"] == list(FIRST)
    assert open_request().pending["settings"] == list(SECOND)

    rows = [dict(settings=list(cell), x=5, y=5 + cell[0]) for cell in CELLS]
    full = Session(VERB, KEYS, rows)
    assert full.request(CELLS) is None and full.spent == 0
    assert predictions(full) == {cell: 19 + cell[0] for cell in CELLS}


def replies_and_replay():
    cases = (
        ([report()], "accepted_base", 19),
        ([report(y=X + 4)], "local_override", 23),
        (None, "no_reading", None),
        ([], "no_reading", None),
        ([report(verb="zob")], "unrelated", None),
        ([report(x=X + 1)], "unrelated", None),
        ([report(settings=list(FIRST))], "unrelated", None),
        ([report(settings=[0, False, 1])], "invalid", None),
        ([report(y=True)], "invalid", None),
        ([report(y=MAX_INTEGER + 1)], "invalid", None),
        ([report(), report()], "invalid", None),
        ([report(), report(y=X + 1)], "conflict", None),
        ([report(), report(verb="zob")], "unrelated", None),
    )
    for rows, expected_status, endpoint in cases:
        session = open_request()
        expected = predictions(session)
        assert expected[SECOND] is None and expected[FIRST] is None
        expected[SECOND] = endpoint
        assert session.spent == 1 and session.request([FIRST]) is None
        assert session.reply(rows) == expected_status
        assert session.reply(report(y=X - 2)) == expected_status
        assert session.spent == 1 and session.pending is None
        assert session.request([FIRST]) is None
        assert predictions(session) == expected


def historical_conflict_and_bounds():
    rows = history()
    session = Session(VERB, KEYS, rows + [dict(rows[0], y=99), rows[0]])
    assert session.predict(19, CELLS[0]) is None
    assert session.request([CELLS[0]]) is None
    assert session.predict(MAX_INTEGER, (1, 1, 0)) is None
    assert session.predict(True, (1, 1, 0)) is None
    assert session.request([SECOND])["settings"] == list(SECOND)
    assert session.reply(report(x=0, y=2)) == "accepted_local"
    assert session.predict(19, SECOND) == 21 and session.predict(19, CELLS[0]) is None

    for malformed in (dict(rows[0], x="9"), dict(rows[0], settings=[0, 0]),
                      dict(rows[0], verb="zob"), dict(rows[0], x=-MAX_INTEGER, y=MAX_INTEGER)):
        try:
            Session(VERB, KEYS, [malformed])
        except ValueError:
            continue
        raise AssertionError(f"admitted malformed history: {malformed}")


def mutation_isolation():
    rows = history()
    session = Session(VERB, KEYS, rows)
    rows[0]["settings"][0] = 1
    rows[0]["y"] = 197
    assert session.predict(19, CELLS[0]) == 19
    requested = [list(SECOND)]
    handle = session.request(requested, x=X)
    handle["settings"].clear()
    session.pending["x"] = 8
    requested[0][0] = 1
    assert session.pending == {"verb": VERB, "x": X, "settings": list(SECOND)}
    response = report()
    assert session.reply(response) == "accepted_base"
    response["settings"].clear()
    response["y"] = 51
    assert session.predict(19, SECOND) == 19
    assert fresh().predict(19, SECOND) is None


if __name__ == "__main__":
    for control in (selection_and_denial, replies_and_replay, historical_conflict_and_bounds,
                    mutation_isolation):
        control()
        print(f"PASS {control.__name__}")
