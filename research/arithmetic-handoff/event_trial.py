"""Compare event attachment, relationship decisions and actual arithmetic receipts."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from event_reader import read_events
from repeat_reader import NUMBERS, integer_runs, read_repeat
from replay import calculate

LABELS = ("same", "distinct", "uncertain", "outside")
OLD = {"one": "same", "two": "distinct", "ask": "uncertain", "pass": "pass"}
WORD = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
STOP = set("""a an the this that those these my your his her our their it its for of on at in by to
from with as and then but or is are was were be been had has have did do does i we he she they
add adds added adding subtract minus negative plus gain gained credit credits point points
amount total number multiply multiplied double twice same again another first second""".split())


def valid(span, text):
    return (isinstance(span, (tuple, list)) and len(span) == 2 and all(type(x) is int for x in span)
            and 0 <= span[0] < span[1] <= len(text))


def nearest(text, amount):
    if not valid(amount, text):
        return None
    options = []
    for word in WORD.finditer(text):
        term = word[0].lower()
        if not any(ch.isalpha() for ch in term) or term in STOP or term in NUMBERS:
            continue
        if word.end() <= amount[0]:
            gap, side = text[word.end():amount[0]], 1
        elif word.start() >= amount[1]:
            gap, side = text[amount[1]:word.start()], 0
        else:
            continue
        if not re.search(r"[.;!?\n]", gap):
            options.append((len(gap), side, word.span()))
    return list(min(options)[2]) if options else None


def link_matches(text, actual, expected):
    if actual.get("amount_span") != expected["amount_span"]:
        return False
    span = actual.get("event_span")
    if not valid(span, text):
        return False
    words = len(WORD.findall(text[slice(*span)]))
    return 1 <= words <= 6 and any(
        span[0] <= lo < hi <= span[1] and words <= len(WORD.findall(text[lo:hi])) + 2
        for lo, hi in expected["event_spans"])


def run_reader(text, old=False):
    if old:
        raw = read_repeat(text)
        reading = dict(decision=OLD[raw["decision"]], frame=raw["frame"], mentions=[], question=None)
    else:
        reading = read_events(text)
    if reading["decision"] not in {"same", "distinct", "uncertain", "pass"}:
        raise ValueError("Unexpected relationship decision")
    result = calculate(reading["frame"]) if reading["decision"] == "same" else None
    return dict(reading=reading, result=result)


def evaluate(case):
    text = case["text"]
    old, new = run_reader(text, old=True), run_reader(text)
    found = new["reading"]["mentions"]
    nearby = [dict(amount_span=m["amount_span"], event_span=nearest(text, m["amount_span"])) for m in found]
    swapped = ([dict(m, event_span=other["event_span"]) for m, other in zip(found, reversed(found))]
               if len(found) == 2 else [])
    run = bool(integer_runs(text))
    choices = dict(merge="same" if run else "pass", count="distinct" if run else "pass",
                   ask="uncertain" if run else "pass", previous=old["reading"]["decision"],
                   candidate=new["reading"]["decision"])
    gold = case["mentions"]
    known = [dict(amount_span=g["amount_span"], event_span=nearest(text, g["amount_span"])) for g in gold]
    links = {name: [any(link_matches(text, m, g) for m in spans) for g in gold]
             for name, spans in (("candidate", found), ("proximity", nearby), ("swapped", swapped),
                                 ("proximity_given_amounts", known))}
    amounts = sum(any(m["amount_span"] == g["amount_span"] for m in found) for g in gold)
    return dict(id=case["id"], label=case["label"], old=old, new=new, choices=choices, links=links,
                amounts=amounts, proximity=nearby)


def validate(cases, boundaries):
    if Counter(c["label"] for c in cases) != {k: 6 for k in LABELS}:
        raise ValueError("Unexpected primary bank counts")
    for key in ("id", "text"):
        if len({c[key] for c in cases + boundaries}) != len(cases + boundaries):
            raise ValueError("Duplicate " + key)
    for c in cases:
        gold, text = c["mentions"], c["text"]
        if c["label"] == "outside":
            if gold:
                raise ValueError("Outside example has event links")
            continue
        if len(gold) != 2 or not all(type(c[k]) is int for k in ("start", "amount", "multiplier")):
            raise ValueError("Missing gold operands or links")
        if not all(valid(m["amount_span"], text) and m["event_spans"] and
                   all(valid(s, text) for s in m["event_spans"]) for m in gold):
            raise ValueError("Invalid source annotation")
        if gold[0]["amount_span"][1] > gold[1]["amount_span"][0]:
            raise ValueError("Gold amount occurrences overlap")


def summarize(cases, boundaries):
    validate(cases, boundaries)
    by_label, links, decisions, arithmetic = {}, Counter(), Counter(), {}
    for case in cases:
        row = evaluate(case)
        label = case["label"]
        expected = "pass" if label == "outside" else label
        by_label.setdefault(label, Counter()).update({k: int(v == expected) for k, v in row["choices"].items()})
        decisions[row["choices"]["candidate"]] += 1
        links["amounts"] += row["amounts"]
        for method, flags in row["links"].items():
            both = len(flags) == 2 and all(flags)
            links[method + "_links"] += sum(flags)
            links[method + "_pairs"] += both
        both_correct = len(case["mentions"]) == 2 and all(row["links"]["candidate"])
        links["pairs_and_relation"] += both_correct and row["choices"]["candidate"] == expected
        for name in ("old", "new"):
            counts = arithmetic.setdefault(name, Counter())
            result = row[name]["result"]
            issued = result is not None and result["decision"] == "compute"
            correct = (issued and label == "same" and result["frame"] ==
                       dict(start=case["start"], add=case["amount"], multiply=case["multiplier"]) and
                       result["value"] == (case["start"] + case["amount"]) * case["multiplier"] and
                       result["verdicts"] == ["checked", "checked"])
            counts.update(correct=int(correct), grounded=int(correct and name == "new" and both_correct),
                          wrong=int(issued and not correct and label != "outside"),
                          outside=int(issued and label == "outside"), checks=result["checks"] if result else 0)
    edges = []
    for case in boundaries:
        old = run_reader(case["text"], old=True)
        new = run_reader(case["text"])
        edges.append(dict(id=case["id"], expected=case["expected_value"],
                          previous_value=old["result"]["value"] if old["result"] else None,
                          candidate_value=new["result"]["value"] if new["result"] else None,
                          decision=new["reading"]["decision"], checks=new["result"]["checks"] if new["result"] else 0))
    return dict(correct_by_label=by_label, decisions=decisions, attachment=links, arithmetic=arithmetic,
                boundaries=edges)


def digest(rows):
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="show one request with its source spans and checked outcome")
    args = parser.parse_args()
    bank = json.loads((HERE / "event_trial.json").read_bytes())
    for key in ("cases", "boundaries"):
        if digest(bank[key]) != bank["hashes"][key]:
            raise ValueError("Frozen fixture mismatch")
    output = summarize(bank["cases"], bank["boundaries"])
    if output != bank["observed"]:
        raise ValueError("Observed scores differ from archived scores")
    if args.case:
        case = next((c for c in bank["cases"] + bank["boundaries"] if c["id"] == args.case), None)
        if case is None:
            parser.error("unknown case ID")
        detail = evaluate(case) if "label" in case else run_reader(case["text"])
        reading = detail["new"]["reading"] if "label" in case else detail["reading"]
        text = case["text"]
        evidence = [{"amount": text[slice(*m["amount_span"])], "describes": text[slice(*m["event_span"])]}
                    for m in reading["mentions"]
                    if valid(m.get("amount_span"), text) and valid(m.get("event_span"), text)]
        output = dict(source=case, attached_words=evidence, detail=detail)
    print(json.dumps(output, indent=2))
