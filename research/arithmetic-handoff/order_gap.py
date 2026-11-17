"""Replay the frozen operation-order reader comparison using the public arithmetic checker."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gate import inspect_messages
from order_reader import continue_order, inspect_order
from replay import FIELDS, calculate, response

COUNTS = dict(ask_order=8, add_first=8, multiply_first=6, equivalent=4, missing_operand=3, other=3)
UNDECIDED = "I'm still deciding which operation to apply first."


def validate(case):
    label = case['label']
    if label not in COUNTS or not isinstance(case['id'], str) or not case['id'].strip():
        raise ValueError('Expected a known label and a nonempty case ID')
    messages = case['messages']
    if not isinstance(messages, list) or not messages or any(
        m['role'] not in ('assistant', 'user') or not isinstance(m['content'], str)
        or not m['content'].strip() for m in messages
    ):
        raise ValueError(f"{case['id']}: expected nonempty message turns")
    operands = [case[k] for k in FIELDS]
    values = [case['add_first_value'], case['multiply_first_value']]
    if any(v is not None and type(v) is not int for v in operands + values):
        raise ValueError(f"{case['id']}: expected integers or null")
    if None not in operands:
        start, add, factor = operands
        expected = [(start + add) * factor, start * factor + add]
        if values != expected or label == 'missing_operand':
            raise ValueError(f"{case['id']}: inconsistent arithmetic oracle")
        if label == 'ask_order' and values[0] == values[1] or label == 'equivalent' and values[0] != values[1]:
            raise ValueError(f"{case['id']}: order sensitivity differs from label")
    elif label not in ('missing_operand', 'other') or values != [None, None]:
        raise ValueError(f"{case['id']}: incomplete arithmetic oracle")
    replies = case.get('replies')
    if label == 'ask_order':
        if not isinstance(replies, dict) or set(replies) != {'add_first', 'multiply_first'} or any(
            not isinstance(v, str) or not v.strip() for v in replies.values()
        ) or replies['add_first'].strip().casefold() == replies['multiply_first'].strip().casefold():
            raise ValueError(f"{case['id']}: expected two distinct counterfactual replies")
    elif replies is not None:
        raise ValueError(f"{case['id']}: unexpected follow-up probes")


def resolve(decision, frame, question=None):
    if decision == 'compute':
        if not isinstance(frame, dict) or set(frame) != set(FIELDS) or any(type(frame[k]) is not int for k in FIELDS):
            raise ValueError('Reader offered an invalid frame to the arithmetic checker')
        result = calculate(frame)
    else:
        result = response(decision)
        result['frame'] = frame
    return dict(result, question=question)


def focused(question):
    if not isinstance(question, str) or '?' not in question:
        return False
    return bool(re.search(r'\b(before|after|first)\b|\b(which|what)\s+order\b', question, re.I))


def run_readers(messages, replies):
    # The decision functions receive only conversation text and their own pending state.
    old = inspect_messages(deepcopy(messages))
    baseline = resolve(old['kind'], old['frame'], old['question'])
    baseline['focused'] = old['kind'] == 'clarify' and old['reason'] == 'missing-order' and focused(old['question'])
    pending = inspect_order(deepcopy(messages))
    if pending['decision'] == 'pass':
        return baseline, baseline.copy(), {}
    if pending['decision'] != 'ask_order':
        raise ValueError('Unexpected initial order-reader decision')
    candidate = resolve('ask_order', pending['frame'], pending['question'])
    candidate['focused'] = focused(pending['question'])
    followups = {}
    for branch, text in replies.items():
        reply = continue_order(deepcopy(pending), text)
        if reply['decision'] not in ('compute', 'clarify', 'unsupported'):
            raise ValueError('Unexpected continuation decision')
        followups[branch] = resolve(reply['decision'], reply['frame'])
    return baseline, candidate, followups


def matches_frame(result, case):
    frame = result['frame']
    return isinstance(frame, dict) and set(frame) == set(FIELDS) and all(
        type(frame[k]) is int and frame[k] == case[k] for k in FIELDS)


def exact_release(result, case):
    return (result['decision'] == 'compute' and matches_frame(result, case)
            and result['value'] == case['add_first_value'] and result['verdicts'] == ['checked', 'checked'])


def grade_initial(result, case):
    gap = case['label'] == 'ask_order'
    supported = case['label'] in ('add_first', 'equivalent')
    issued = result['decision'] == 'compute'
    asked = result['focused']
    retained = gap and result['decision'] in ('ask_order', 'clarify', 'unresolved') and matches_frame(result, case)
    return dict(gap_questions=gap and asked, gap_pending_exact=retained,
                gap_question_and_frame=gap and asked and retained,
                gap_generic_clarifications=gap and not asked and result['decision'] in ('ask_order', 'clarify', 'unresolved'),
                false_order_questions=not gap and asked, correct_initial_releases=supported and exact_release(result, case),
                wrong_or_extra_initial_releases=issued and not (supported and exact_release(result, case)),
                initial_checks=result['checks'])


def evaluate_case(case):
    validate(case)
    probes = case.get('replies') or {}
    if probes:
        probes = dict(probes, undecided=UNDECIDED)
    baseline, candidate, followups = run_readers(case['messages'], probes)
    grades = {name: grade_initial(result, case) for name, result in [('baseline', baseline), ('candidate', candidate)]}
    scores = dict(probed=bool(followups), add_first_checked=False, reverse_unsupported=False,
                  undecided_clarifies=False, both_orders_correct=False, wrong_or_extra_releases=0, checks=0)
    if followups:
        add = followups['add_first']
        reverse = followups['multiply_first']
        undecided = followups['undecided']
        scores['add_first_checked'] = exact_release(add, case)
        scores['reverse_unsupported'] = reverse['decision'] == 'unsupported' and reverse['checks'] == 0
        scores['undecided_clarifies'] = undecided['decision'] == 'clarify' and undecided['checks'] == 0
        scores['both_orders_correct'] = scores['add_first_checked'] and scores['reverse_unsupported']
        scores['wrong_or_extra_releases'] = (int(add['decision'] == 'compute' and not scores['add_first_checked'])
            + int(reverse['decision'] == 'compute') + int(undecided['decision'] == 'compute'))
        scores['checks'] = sum(v['checks'] for v in followups.values())
    return dict(id=case['id'], label=case['label'], baseline=baseline, candidate=candidate, grades=grades,
                changed_control_response=case['label'] != 'ask_order' and baseline != candidate,
                followups=followups, followup_grades=scores)


def summarize(cases):
    if Counter(c['label'] for c in cases) != COUNTS or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Expected the frozen 32-case composition and distinct IDs')
    totals = {key: Counter() for key in ('baseline', 'candidate', 'followups')}
    changed = 0
    for case in cases:
        detail = evaluate_case(case)
        for arm in ('baseline', 'candidate'):
            totals[arm].update({k: int(v) for k, v in detail['grades'][arm].items()})
        totals['followups'].update({k: int(v) for k, v in detail['followup_grades'].items()})
        changed += int(detail['changed_control_response'])
    return dict(case_counts=COUNTS.copy(), changed_control_responses=changed, **{k: dict(v) for k, v in totals.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', metavar='ID', help='show reader decisions, follow-up branches and checker receipts')
    args = parser.parse_args()
    bank = json.loads((HERE / 'order_gap.json').read_text(encoding='utf-8'))
    totals = summarize(bank['cases'])
    if totals != bank['observed']:
        raise ValueError('Replay differs from the recorded totals')
    output = totals
    if args.case:
        case = next((c for c in bank['cases'] if c['id'] == args.case), None)
        if case is None:
            parser.error('unknown case ID')
        output = dict(input=case, result=evaluate_case(case))
    print(json.dumps(output, indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
