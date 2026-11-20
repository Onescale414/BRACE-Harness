"""Offline, synthetic host journey: repair, explicitly accept, compose and reuse.

Acceptance in this demonstration is a separate scripted host decision. A model
does not authorize it. All examples and lesson storage are created for this run.
"""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from learning_session import Session, rollback_store
from lesson_store import Store


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rows(inputs, function):
    """Expected outputs come from the example's formula, not the BRACE evaluator."""
    return [[x, function(x)] for x in inputs]


def summary(stage, receipt):
    work = receipt.get('work', {})
    require(work.get('full_checks', 0) <= 2, 'Exceeded the full-check grant')
    require(work.get('candidate_slots', 0) <= 85, 'Exceeded candidate slots')
    require(work.get('proposal_scalar_operations', 0) <= 252,
            'Exceeded proposal arithmetic')
    require(work.get('model_calls', 0) == 0 and not receipt.get('model_events'),
            'The offline demo dispatched a model')
    return {
        'stage': stage,
        'status': receipt['status'],
        'decision': receipt['decision'],
        'plan': receipt.get('plan'),
        'full_checks': work.get('full_checks', 0),
        'candidate_slots': work.get('candidate_slots', 0),
        'proposal_operations': work.get('proposal_scalar_operations', 0),
        'attempts': [{key: attempt[key] for key in ('origin', 'plan', 'status')}
                     for attempt in receipt.get('attempts', ())],
    }


def send(host, event, expected_status):
    # Exercise the serialized boundary used by the CLI, without another process.
    result = host.handle_bytes(json.dumps(event, separators=(',', ':')).encode('ascii'))
    require(result['status'] == expected_status,
            f"Expected {expected_status}, received {result['status']}")
    return result


def accept(host, draft, name):
    require(draft['draft']['acceptance_required'], 'Draft bypassed acceptance')
    return send(host, {'action': 'accept', 'draft': draft['draft']['id'], 'name': name},
                'lesson-accepted')


def snapshot_bytes(store):
    return store.read(), store.read_previous()


def lesson_view(host):
    return send(host, {'action': 'status'}, 'session-status')


def run():
    stages = []
    with tempfile.TemporaryDirectory(prefix='brace-composition-demo-') as folder:
        directory = str(Path(folder).resolve() / 'lessons')
        with Store(directory) as store:
            host = Session(store=store)
            empty = snapshot_bytes(store)
            # For these x, x*x and x agree modulo 2, 3, 5 and 7. The wrong
            # identity proposal reaches the independent full arithmetic check.
            repaired = send(host, {
                'action': 'request', 'examples': rows((0, 1, 210, 211), lambda x: x * x),
                'proposal': [],
            }, 'checked')
            require(repaired['plan'] == ['square'] and repaired['repair'], 'Repair failed')
            require([a['status'] for a in repaired['attempts']] ==
                    ['different-output', 'checked'], 'Expected rejection then repair')
            require(repaired['work']['full_checks'] == 2, 'Repair did not use two checks')
            require(repaired['memory']['accepted_lessons'] == 0,
                    'Checked draft was accepted implicitly')
            require(snapshot_bytes(store) == empty, 'Draft changed persistent storage')
            stages.append(summary('reject_wrong_proposal_then_repair', repaired))
            stages.append(summary('host_explicitly_accepts_Fold', accept(host, repaired, 'Fold')))

            first_snapshot = store.read()
            nudge = send(host, {'action': 'request', 'proposal': ['add1'],
                               'examples': rows((-17, -4, 8, 23), lambda x: x + 1)}, 'checked')
            require(store.read() == first_snapshot, 'Unaccepted teaching changed Fold')
            stages.append(summary('host_explicitly_accepts_Nudge', accept(host, nudge, 'Nudge')))
            primitive_lessons = lesson_view(host)['lessons']

            prior = snapshot_bytes(store)
            combined = send(host, {
                'action': 'request', 'composition': 'do Nudge then Fold',
                'examples': rows((-11, -2, 6, 29), lambda x: (x + 1) ** 2),
            }, 'checked')
            require(combined['plan'] == ['add1', 'square'], 'Composition changed order')
            require(combined['work']['full_checks'] == 1, 'Composition should use one check')
            require(snapshot_bytes(store) == prior, 'Composition draft changed storage')
            stages.append(summary('check_ordered_composition', combined))
            stages.append(summary('host_explicitly_accepts_Lift', accept(host, combined, 'Lift')))
            accepted_lessons = lesson_view(host)['lessons']
            require(accepted_lessons[:2] == primitive_lessons, 'Composition overwrote primitives')
            require(len(accepted_lessons) == 3, 'Expected exactly three accepted lessons')

        # Closing and opening the store creates a new session. Restore independently
        # rechecks every saved lesson against its retained examples.
        with Store(directory) as store:
            host = Session(store=store)
            reopened = lesson_view(host)
            require(reopened['lessons'] == accepted_lessons, 'Reopen changed lesson identities')
            require(reopened['storage']['restore_work']['full_checks'] == 3,
                    'Reopen did not recheck all three lessons')
            saved = snapshot_bytes(store)
            stages.append({'stage': 'reopen_and_recheck', 'accepted_lessons': 3,
                           'restore_full_checks': 3, 'lesson_identity_preserved': True})

            reused = send(host, {
                'action': 'request', 'lesson_name': 'Lift',
                'examples': rows((-19, -5, 9, 37), lambda x: (x + 1) ** 2),
            }, 'checked')
            require(reused['plan'] == ['add1', 'square'] and
                    reused['work']['full_checks'] == 1, 'Reuse was not independently checked')
            require(reused['attempts'][0]['origin'] == 'accepted-lesson', 'Lesson was not reused')
            stages.append(summary('recheck_Lift_on_fresh_examples', reused))
            send(host, {'action': 'discard'}, 'discarded')

            wrong_order = send(host, {
                'action': 'request', 'composition': 'do Fold then Nudge',
                'examples': rows((-23, -3, 7, 31), lambda x: (x + 1) ** 2),
            }, 'composition-conflict')
            require(wrong_order['decision'] == 'withhold' and wrong_order['draft'] is None,
                    'Wrong-order request released a draft')
            require(wrong_order['correction']['checked_outputs'] ==
                    [x * x + 1 for x in (-23, -3, 7, 31)], 'Wrong-order evidence differs')
            stages.append(summary('withhold_wrong_order', wrong_order))
            require(lesson_view(host)['lessons'] == accepted_lessons,
                    'Reuse or conflict overwrote an accepted lesson')
            require(snapshot_bytes(store) == saved, 'Read/reuse/conflict changed snapshots')

        rolled_back = rollback_store(directory)
        require(rolled_back['status'] == 'lessons-rolled-back' and
                rolled_back['accepted_lessons'] == 2, 'Rollback did not select previous snapshot')
        stages.append({'stage': 'host_rolls_back', 'status': rolled_back['status'],
                       'accepted_lessons': 2})
        with Store(directory) as store:
            host = Session(store=store)
            reopened = lesson_view(host)
            require(reopened['lessons'] == primitive_lessons, 'Rollback changed original primitives')
            require(reopened['storage']['restore_work']['full_checks'] == 2,
                    'Rollback reopen did not recheck primitives')
            absent = send(host, {'action': 'request', 'lesson_name': 'Lift',
                                'examples': rows((-9, -2, 4, 13), lambda x: (x + 1) ** 2)},
                          'unknown-lesson-name')
            require(absent['work']['full_checks'] == 0, 'Unknown lesson spent a check')
            stages.append(summary('rolled_back_Lift_is_unavailable', absent))
            require(lesson_view(host)['lessons'] == primitive_lessons,
                    'Missing-name lookup changed original lessons')

    # An independent optional clarification example, without persistent storage.
    # The caller supplies y=x*x at the requested x; it does not pick a model's
    # prediction merely because it was offered.
    host = Session()
    original = [[0, 0], [1, 1], [0, 0], [1, 1]]
    question = send(host, {'action': 'request', 'examples': original, 'clarify': True}, 'question')
    stages.append(summary('ask_for_distinguishing_observation', question))
    x = question['question']['x']
    answer = send(host, {'action': 'answer', 'question': question['question']['id'], 'y': x * x},
                  'checked')
    require(answer['plan'] == ['square'], 'Clarification did not select square')
    require(set(map(tuple, original)) <= set(map(tuple, answer['examples'])),
            'Clarification discarded an earlier observation')
    require(answer['memory']['accepted_lessons'] == 0, 'Answer implicitly accepted a lesson')
    stages.append(summary('host_supplies_observation_then_rechecks', answer))

    return {'passed': True, 'model_calls': 0,
            'acceptance': 'Three separate scripted host decisions; never automatic acceptance.',
            'scope': 'Plans match supplied examples; no claim of unique or unrestricted meaning.',
            'storage': 'Disposable store created for this run; no private lessons imported.',
            'request_limit': {'full_checks': 2, 'candidate_slots': 85, 'proposal_operations': 252},
            'clarification': 'The explicit answer receives its own bounded child grant.',
            'stages': stages}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
