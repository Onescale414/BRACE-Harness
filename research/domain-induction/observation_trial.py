"""Replay one new measurement versus permission for one additional sensor field."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import observation_reader as fields
from context_reader import certify, choose, rules, update

SINGLE = ("no_grant", "first", "first_informative", "selected")
FIELD = ("first", "selected")


def visible(row):
    return dict(verb=row["verb"], x=row["x"], features=dict(row["features"]))


def contradiction(rows):
    seen = {}
    return any(seen.setdefault(r["x"], r["y"]) != r["y"] for r in rows)


def request_reading(candidates, menu, method):
    if method == "no_grant" or len(candidates) <= 1 or not menu:
        return None
    if method == "first":
        return 0
    if method == "first_informative":
        return next((i for i, r in enumerate(menu) if len({h.delta(r) for h in candidates}) > 1), None)
    if method != "selected":
        raise ValueError("Unknown probe policy")
    i = choose(candidates, menu)
    return i if len({h.delta(menu[i]) for h in candidates}) > 1 else None


def tally(committed, truth):
    return dict(right=sum(v == y for v,y in zip(committed,truth) if v is not None),
                wrong=sum(v != y for v,y in zip(committed,truth) if v is not None),
                held=sum(v is None for v in committed))


def single_case(world, method):
    fit, keys = list(world["fit"]), world["keys"]
    if not contradiction(fit):
        raise ValueError("Missing scalar contradiction")
    candidates = rules(keys)
    for row in fit:
        candidates = update(candidates, row)
    before = len(candidates)
    menu = [visible(row) for row in world["menu"]]
    i = request_reading(candidates, menu, method)
    question = answer = None
    possible = []
    if i is not None:
        p = menu[i]
        controls = ", ".join(f"{k}={p['features'][k]}" for k in keys)
        question = f"What output does {p['verb']} produce at x={p['x']} with {controls}?"
        possible = sorted({p["x"] + h.delta(p) for h in candidates})
        # One grant opens exactly this result. No feedback loop or second acquisition.
        answer = world["menu"][i]["y"]
        fit.append(dict(p, y=answer))
        candidates = update(candidates, fit[-1])
    model = candidates[0] if len(candidates) == 1 else None
    if model != certify(keys, fit):
        raise ValueError("Independent fit disagrees with learned rule")
    def cell(row):
        return tuple(row["features"][k] for k in keys)
    witnessed = {cell(r):r["y"]-r["x"] for r in fit}
    future = [visible(r) for r in world["tests"]]
    whole = [r["x"] + model.delta(r) if model else None for r in future]
    local = [r["x"] + witnessed[cell(r)] if candidates and cell(r) in witnessed else None for r in future]
    truth = [r["y"] for r in world["tests"]]
    return dict(id=world["id"], kind=world["kind"], before=before, after=len(candidates),
                question=question, anticipated_outputs=possible, observed=answer, rule=model,
                reads=int(i is not None), whole=tally(whole,truth), local=tally(local,truth))


def receipt_rows(world, phase):
    return [dict(id=f"{world['id']}/{phase}/{i}", x=r["x"], y=r["y"])
            for i,r in enumerate(world[phase])]


def field_case(world, method):
    fit = receipt_rows(world,"fit")
    if not contradiction(fit):
        raise ValueError("Missing scalar contradiction")
    names = world["channels"]
    if method == "selected":
        catalog = fields.summarize_catalog(fit,names,world["fit_channels"])
        key = fields.choose(fit,catalog)
    else:
        catalog, key = [], names[0]
    archived = sum(r["archived_cells"] for r in catalog)
    column = world["fit_channels"].get(key) if key is not None else None
    fitted = fields.bind(key,fit,column)
    audit = None
    if fitted:
        audit = fields.confirm(fitted,receipt_rows(world,"validation"),
                               [r["channels"].get(key) for r in world["validation"]])
    answers = [fields.predict(audit,r["x"],r["channels"].get(key)) if audit else None
               for r in world["tests"]]
    truth = [r["y"] for r in world["tests"]]
    return dict(id=world["id"], kind=world["class"], field=key,
                question=f"Can I use {key} on this action's receipts?" if key else None,
                archived_cells=archived, fit_rereads=len(column) if column is not None else 0,
                validation_reads=len(world["validation"]) if fitted else 0,
                query_reads=len(answers) if audit else 0,
                fit=bool(fitted), confirmed=bool(audit), scores=tally(answers,truth))


def summary(single, field_bank):
    result = {"one_read":{}, "one_field":{}}
    for method in SINGLE:
        by_kind = {}
        for w in single:
            r = single_case(w,method)
            c = by_kind.setdefault(r["kind"],Counter())
            c.update(reads=r["reads"], unique=int(r["after"]==1), contradicted=int(r["after"]==0),
                     ambiguous=int(r["after"]>1), **r["whole"])
            c.update({"local_"+k:v for k,v in r["local"].items()})
        result["one_read"][method] = by_kind
    for method in FIELD:
        by_kind = {}
        for w in field_bank:
            r = field_case(w,method)
            c = by_kind.setdefault(r["kind"],Counter())
            c.update(requests=int(r["field"] is not None),fits=int(r["fit"]),confirmed=int(r["confirmed"]),
                     **r["scores"])
            c.update({k:r[k] for k in ("archived_cells","fit_rereads","validation_reads","query_reads")})
        result["one_field"][method] = by_kind
    return result


def source(name, digest):
    raw = (HERE / name).read_bytes().replace(b"\r\n",b"\n")
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"Fixture differs from freeze: {name}")
    return json.loads(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", help="see the exact question, evidence and result for one world")
    args = parser.parse_args()
    bank = source("observation_cases.json","a4ab19f1a50facd7b93798f7a930d516a127c094a3a94958f959a0b39f7cf8f6")
    sensor = source("field_cases.json","91c5c2d46c8565b1ddd3816a0fd9d79e298f5fb0b379eaad3eceee4436a83227")["worlds"]
    result = summary(bank,sensor)
    if result != json.loads((HERE/"observation_results.json").read_bytes()):
        raise ValueError("Replay differs from archived scores")
    if args.case:
        chosen = [(w,single_case) for w in bank if w["id"]==args.case]
        chosen += [(w,field_case) for w in sensor if w["id"]==args.case]
        if len(chosen) != 1:
            parser.error("expected one matching world")
        w,run = chosen[0]
        result = run(w,"selected")
    print(json.dumps(result,indent=2))
