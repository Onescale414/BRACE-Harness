"""Recount the held-out connector requests using only the included evidence."""
import argparse
from collections import defaultdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def source(name, digest):
    file = HERE / (name + ".py")
    require(sha256(file.read_bytes()).hexdigest() == digest, f"Changed reader: {name}")
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rebuild(text, truth, fifo, actor, delivery, host):
    plan = delivery.plan(text, fifo, actor)
    actions = []
    def replay_value(question):
        actions.append(question)
        return host.Answer(question, truth[question], int("mixed_matches" in actions), question == "mixed_matches")
    inbox = host.Inbox()
    handoff = host.Handoff(plan, inbox, replay_value)
    first = handoff.begin()
    before = actions.copy()
    require(handoff.acknowledge(None) is None and actions == before, "Released during delivery pause")
    if first is not None:
        token = inbox.deliver(first)
        require(actions == before, "Released before first delivery acknowledgement")
        second = handoff.acknowledge(token)
        if second:
            inbox.deliver(second)
        require(handoff.acknowledge(token) is None, "Duplicate release")
    return {"fifo": fifo.schedule(text, "fifo"), "actor": actor.schedule(text, fifo),
            "delivery": {"actions": actions, "clarify": plan["clarify"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rerun-readers", action="store_true", help="Also execute all three original language readers")
    options = parser.parse_args()
    bank = json.loads((HERE / "observations.json").read_bytes())
    names = ("fifo", "actor", "delivery")
    readers = [source(n, bank["sourceSHA256"][n]) for n in (*names, "handoff")] if options.rerun_readers else []
    totals = {n:dict(exact=0, first=0, reserved=0, completion=0, unrequested_reads=0,
                     early_reads=0, reads=0) for n in names}
    pairs = defaultdict(lambda: defaultdict(list))
    ids = set()
    for case in bank["cases"]:
        require(case["id"] not in ids, "Duplicate request")
        ids.add(case["id"])
        truth = bank["fixtures"][case["fixture"]]
        expected = case["expected"]
        computed = rebuild(case["wording"], truth, *readers) if readers else None
        for name, total in totals.items():
            row = case["outcomes"][name]
            answers, observations = row["answers"], row["observations"]
            require(len(observations) <= 1, "Observation allowance exceeded")
            topics = [a["question"] for a in answers]
            seen = 0
            for i, answer in enumerate(answers):
                require(same(answer["grantRequested"], answer["question"] == "mixed_matches"),
                        "Recorded grant request differs from the checked topic")
                if answer["question"] == "mixed_matches":
                    require(len(observations) == 1 and observations[0] == {
                        "beforeAnswer": i, "probe":"mixed_get", "value":truth["mixed_matches"]
                    } and same(observations[0]["beforeAnswer"], i)
                            and same(observations[0]["value"], truth["mixed_matches"]), "Unverified URL answer")
                    seen += 1
                require(same(answer["value"], truth[answer["question"]]) and same(answer["checksUsed"], seen),
                        "Answer value or cumulative count differs from its fixture")
            require(seen == len(observations), "Unaccounted observation")
            if computed:
                require(computed[name] == {"actions": topics, "clarify": row["clarify"]},
                        f"Reader no longer matches {case['id']} ({name})")
            correct = topics == expected and row["clarify"] == case["clarify"]
            total["exact"] += int(correct)
            total["reads"] += seen
            total["unrequested_reads"] += seen if "mixed_matches" not in expected else 0
            if expected == ["delay_ms", "mixed_matches"] and observations:
                prior = topics[:observations[0]["beforeAnswer"]]
                total["early_reads"] += int("delay_ms" not in prior)
            if case["primary"]:
                total["first"] += int(topics[:1] == expected[:1])
                total["reserved" if len(expected) == 1 else "completion"] += int(correct)
                pairs[name][case["pair"]].append(correct)
    require(len(ids) == 36, "Incomplete case bank")
    print("Reader   Exact/36  First/24  Reserved/12  Completion/12  Pairs/12  Unrequested  Early  Total URL reads")
    for name, total in totals.items():
        groups = pairs[name].values()
        require(len(groups) == 12 and all(len(g) == 2 for g in groups), "Incomplete primary pairs")
        print(f"{name:8} {total['exact']:8} {total['first']:9} {total['reserved']:12} "
              f"{total['completion']:14} {sum(all(g) for g in groups):9} "
              f"{total['unrequested_reads']:12} {total['early_reads']:6} {total['reads']:16}")
    if readers:
        print("The three original readers reproduced every recorded topic sequence and clarification decision.")


if __name__ == "__main__":
    main()
