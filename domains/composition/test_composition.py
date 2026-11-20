"""Public composition/lesson regressions using only synthetic local examples."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import learning_session as session
from lesson_store import Store
sys.path.pop(0)


def rows(function, inputs=(-11, -3, 4, 13)):
    """Expected values come from independent ordinary Python arithmetic."""
    return [[value, function(value)] for value in inputs]


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now


class SessionChecks(unittest.TestCase):
    def request(self, host, function, *, inputs=(-11, -3, 4, 13), **options):
        result = host.handle({'action': 'request', 'examples': rows(function, inputs), **options})
        work = result.get('work', {})
        self.assertLessEqual(work.get('full_checks', 0), 2)
        self.assertLessEqual(work.get('candidate_slots', 0), 85)
        self.assertLessEqual(work.get('proposal_scalar_operations', 0), 252)
        self.assertEqual(result.get('model_events', []), [])
        return result

    def accept(self, host, draft, name):
        self.assertEqual(draft['status'], 'checked', draft)
        result = host.handle({'action': 'accept', 'draft': draft['draft']['id'], 'name': name})
        self.assertEqual(result['status'], 'lesson-accepted', result)
        return result

    def teach(self, host, name='Lift', operation='add1', function=lambda x: x + 1):
        return self.accept(host, self.request(host, function, proposal=[operation]), name)

    def lessons(self, host):
        return host.handle({'action': 'status'})['lessons']

    def withheld(self, result, status):
        self.assertEqual(result['status'], status, result)
        self.assertEqual(result['decision'], 'withhold', result)
        self.assertIsNone(result.get('plan'))
        self.assertIsNone(result.get('draft'))

    def test_wrong_supplied_proposal_is_repaired_within_grant(self):
        host = session.Session()
        result = self.request(host, lambda x: x + 1, proposal=['double'])
        self.assertEqual(result['status'], 'checked', result)
        self.assertEqual(result['plan'], ['add1'])
        self.assertTrue(result['repair'])
        self.assertEqual(result['attempts'][0]['plan'], ['double'])
        self.assertIn(result['attempts'][0]['status'], ('modular-reject', 'different-output'))
        self.assertEqual(result['attempts'][-1]['origin'], 'bounded-search')
        self.assertEqual(result['attempts'][-1]['status'], 'checked')
        self.assertEqual(self.lessons(host), [])

    def test_residue_filter_pass_is_not_a_full_check(self):
        # x and x*x agree modulo 2, 3, 5 and 7 here, but not as integers.
        host = session.Session()
        result = self.request(host, lambda x: x * x, inputs=(-210, 0, 1, 211), proposal=[])
        self.assertEqual(result['status'], 'checked', result)
        self.assertEqual(result['plan'], ['square'])
        self.assertEqual(result['attempts'][0]['status'], 'different-output')
        self.assertEqual(result['attempts'][0]['failed_rows'], [0, 3])
        self.assertEqual(result['work']['full_checks'], 2)

    def test_two_failed_checks_withhold_instead_of_taking_a_third(self):
        host = session.Session()
        result = host.handle({'action': 'request',
                              'examples': [[-1, 1], [0, 0], [1, 1], [-2, 214]],
                              'proposal': ['square']})
        self.withheld(result, 'check-budget')
        self.assertEqual(result['work']['full_checks'], 2)
        self.assertEqual(len(result['attempts']), 2)
        self.assertTrue(all(attempt['status'] == 'different-output' for attempt in result['attempts']))
        self.assertEqual(self.lessons(host), [])

    def test_wrong_accepted_lesson_is_checked_then_repaired_without_overwrite(self):
        host = session.Session()
        self.teach(host)
        original = self.lessons(host)
        result = self.request(host, lambda x: 2 * x, lesson_name='Lift')
        self.assertEqual(result['status'], 'checked', result)
        self.assertEqual(result['plan'], ['double'])
        self.assertEqual(result['attempts'][0]['origin'], 'accepted-lesson')
        self.assertEqual(result['attempts'][0]['status'], 'different-output')
        self.assertEqual(result['work']['full_checks'], 2)
        self.assertEqual(self.lessons(host), original)
        self.accept(host, result, 'Stretch')
        self.assertEqual(self.lessons(host)[0], original[0])

    def test_named_composition_is_exact_order_and_requires_its_own_acceptance(self):
        host = session.Session()
        self.teach(host)
        self.teach(host, 'Stretch', 'double', lambda x: 2 * x)
        original = self.lessons(host)
        result = self.request(host, lambda x: 2 * (x + 1), composition='do Lift then Stretch')
        self.assertEqual(result['status'], 'checked', result)
        self.assertEqual(result['plan'], ['add1', 'double'])
        self.assertEqual(result['work']['full_checks'], 1)
        self.assertEqual(self.lessons(host), original)
        self.accept(host, result, 'Combined')
        reused = self.request(host, lambda x: 2 * (x + 1), inputs=(-17, -5, 8, 21), lesson_name='combined')
        self.assertEqual(reused['status'], 'checked', reused)
        self.assertEqual(reused['work']['full_checks'], 1)
        host.handle({'action': 'discard'})
        wrong = self.request(host, lambda x: 2 * (x + 1), composition='do Stretch then Lift')
        self.withheld(wrong, 'composition-conflict')
        self.assertEqual(wrong['attempts'][0]['plan'], ['double', 'add1'])
        self.assertEqual(wrong['correction']['checked_outputs'], [2 * x + 1 for x in (-11, -3, 4, 13)])
        self.assertFalse(any(attempt['origin'] == 'bounded-search' for attempt in wrong['attempts']))
        self.assertEqual(self.lessons(host)[:2], original)

    def test_unknown_name_and_compound_as_primitive_are_withheld(self):
        host = session.Session()
        self.withheld(self.request(host, lambda x: x + 1, lesson_name='Unknown'), 'unknown-lesson-name')
        draft = self.request(host, lambda x: 2 * (x + 1), proposal=['add1', 'double'])
        self.accept(host, draft, 'Combined')
        self.teach(host)
        result = self.request(host, lambda x: 2 * (x + 1) + 1, composition='do Combined then Lift')
        self.withheld(result, 'composition-primitive-only')
        self.assertEqual(result['work']['full_checks'], 0)

    def test_foreign_discarded_and_replayed_acceptance_cannot_create_lessons(self):
        first, second = session.Session(), session.Session()
        draft = self.request(first, lambda x: x + 1, proposal=['add1'])
        event = {'action': 'accept', 'draft': draft['draft']['id'], 'name': 'Lift'}
        self.withheld(second.handle(event), 'draft-binding')
        first.handle({'action': 'discard'})
        self.withheld(first.handle(event), 'draft-binding')
        fresh = self.request(first, lambda x: x + 1, proposal=['add1'])
        accepted = self.accept(first, fresh, 'Lift')
        self.withheld(first.handle({'action': 'accept', 'draft': fresh['draft']['id'], 'name': 'Again'}), 'draft-binding')
        self.assertEqual(len(self.lessons(first)), 1)
        self.assertEqual(self.lessons(second), [])
        self.assertTrue(accepted['lesson']['explicitly_accepted'])

    def test_duplicate_name_preserves_original_and_pending_draft(self):
        host = session.Session()
        self.teach(host)
        original = self.lessons(host)
        draft = self.request(host, lambda x: 2 * x, proposal=['double'])
        self.withheld(host.handle({'action': 'accept', 'draft': draft['draft']['id'], 'name': 'LIFT'}), 'lesson-name-exists')
        self.assertEqual(self.lessons(host), original)
        self.accept(host, draft, 'Stretch')
        self.assertEqual(self.lessons(host)[0], original[0])

    def test_contradiction_has_checked_certificate_but_no_plan(self):
        host = session.Session()
        result = host.handle({'action': 'request', 'examples': [[-9, 81], [-7, 50], [2, 4], [4, 16]]})
        self.withheld(result, 'checked-contradiction')
        self.assertEqual(result['contradiction']['verification']['status'], 'checked-contradiction')
        self.assertEqual(result['work']['full_checks'], 1)
        self.assertEqual(self.lessons(host), [])

    def test_invalid_wire_and_conflicting_inputs_are_not_accepted(self):
        malformed = [b'{', b'{"action":"status","action":"discard"}',
                     b'{"action":"request","examples":[[0,0],[1,1],[2,2],[3,3.0]]}',
                     b'x' * 4097]
        for wire in malformed:
            with self.subTest(wire=wire[:90]):
                host = session.Session()
                result = host.handle_bytes(wire)
                self.assertEqual(result['decision'], 'withhold', result)
                self.assertEqual(result['work'], {})
                self.assertEqual(self.lessons(host), [])
        host = session.Session()
        result = host.handle({'action': 'request', 'examples': [[2, 3], [2, 4], [3, 4], [4, 5]]})
        self.assertEqual(result['decision'], 'withhold')
        self.assertEqual(result['work'], {})

    def test_step_event_and_pending_expiry_limits(self):
        host = session.Session()
        self.withheld(self.request(host, lambda x: x + 1, proposal=['add1'] * 5), 'invalid-plan')
        host = session.Session()
        for _ in range(32):
            self.assertEqual(host.handle({'action': 'status'})['status'], 'session-status')
        self.assertEqual(host.handle({'action': 'status'})['status'], 'session-limit')
        clock = Clock()
        host = session.Session(clock=clock)
        draft = self.request(host, lambda x: x + 1, proposal=['add1'])
        clock.now = 300_000_000_000
        self.withheld(host.handle({'action': 'accept', 'draft': draft['draft']['id'], 'name': 'Late'}), 'pending-expired')
        self.assertEqual(self.lessons(host), [])

    def test_eighth_lesson_is_last_and_retained_bytes_stay_bounded(self):
        host = session.Session()
        for index in range(8):
            self.teach(host, name='Lift' + str(index))
        draft = self.request(host, lambda x: x + 1, proposal=['add1'])
        result = host.handle({'action': 'accept', 'draft': draft['draft']['id'], 'name': 'Ninth'})
        self.withheld(result, 'lesson-limit')
        self.assertEqual(result['memory']['accepted_lessons'], 8)
        self.assertLessEqual(result['memory']['retained_serialized_bytes'], 65536)
        host = session.Session()
        for _ in range(32):
            result = host.handle({'action': 'status', 'unsupported_padding': 'x' * 3500})
            self.assertLessEqual(result['memory']['retained_serialized_bytes'], 65536)
            if result['status'] == 'retained-memory-limit':
                break
        self.withheld(result, 'retained-memory-limit')
        self.assertEqual(host.handle({'action': 'status'})['status'], 'session-limit')

    def test_persistence_only_after_acceptance_and_recheck_on_reopen(self):
        with tempfile.TemporaryDirectory(prefix='brace-public-test-') as directory:
            path = Path(directory).resolve() / 'lessons'
            with Store(path) as store:
                host = session.Session(store=store)
                self.request(host, lambda x: x + 1, proposal=['add1'])
                self.assertIsNone(store.read())
            with Store(path) as store:
                host = session.Session(store=store)
                self.assertEqual(self.lessons(host), [])
                self.teach(host)
                accepted_bytes = store.read()
            with Store(path) as store:
                host = session.Session(store=store)
                status = host.handle({'action': 'status'})
                self.assertEqual(status['storage']['restore_work']['full_checks'], 1)
                result = self.request(host, lambda x: x + 1, inputs=(-29, -8, 6, 31), lesson_name='Lift')
                self.assertEqual(result['status'], 'checked', result)
                self.assertEqual(result['work']['full_checks'], 1)
                self.assertEqual(store.read(), accepted_bytes)

    def test_rehashed_false_arithmetic_is_refused_on_reopen(self):
        with tempfile.TemporaryDirectory(prefix='brace-public-test-') as directory:
            path = Path(directory).resolve() / 'lessons'
            with Store(path) as store:
                host = session.Session(store=store)
                self.teach(host)
            current = path / 'lessons.json'
            envelope = json.loads(current.read_bytes())
            record = envelope['body']['lessons'][0]
            source = json.loads(record['source'])
            source['examples'][0][1] += 1
            record['source'] = session.encoded(source).decode('ascii')
            acceptance = json.loads(record['acceptance'])
            acceptance['request_sha256'] = hashlib.sha256(record['source'].encode('ascii')).hexdigest()
            record['acceptance'] = session.encoded(acceptance).decode('ascii')
            envelope['sha256'] = hashlib.sha256(session.encoded(envelope['body'])).hexdigest()
            tampered = session.encoded(envelope)
            current.write_bytes(tampered)
            with Store(path) as store:
                with self.assertRaisesRegex(ValueError, 'store-check-failed'):
                    session.Session(store=store)
            self.assertEqual(current.read_bytes(), tampered)

    def test_rollback_reopens_previous_checked_generation(self):
        with tempfile.TemporaryDirectory(prefix='brace-public-test-') as directory:
            path = Path(directory).resolve() / 'lessons'
            with Store(path) as store:
                host = session.Session(store=store)
                self.teach(host)
                previous = store.read()
                self.teach(host, 'Stretch', 'double', lambda x: 2 * x)
            result = session.rollback_store(path)
            self.assertEqual(result['status'], 'lessons-rolled-back')
            self.assertEqual(result['accepted_lessons'], 1)
            with Store(path) as store:
                host = session.Session(store=store)
                self.assertEqual(store.read(), previous)
                self.assertEqual([item['name'] for item in self.lessons(host)], ['Lift'])
                result = self.request(host, lambda x: x + 1, inputs=(-23, -2, 9, 37), lesson_name='Lift')
                self.assertEqual(result['status'], 'checked', result)


class CliChecks(unittest.TestCase):
    def command(self, *args):
        return [sys.executable, '-I', '-S', '-B', str(HERE / 'cli.py'), *map(str, args)]

    def run_cli(self, payload=b'', *args):
        return subprocess.run(self.command(*args), input=payload, capture_output=True,
                              cwd=tempfile.gettempdir(), timeout=30)

    def test_memory_cli_fresh_process_checks_a_proposal(self):
        event = {'action': 'request', 'examples': rows(lambda x: 2 * (x + 1)), 'proposal': ['add1', 'double']}
        result = self.run_cli(session.encoded(event) + b'\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['status'], 'checked')
        self.assertEqual(receipt['plan'], ['add1', 'double'])
        self.assertEqual(receipt['memory']['accepted_lessons'], 0)
        self.assertEqual(receipt['work']['full_checks'], 1)

    def test_cli_invalid_flags_and_oversized_or_duplicate_events(self):
        for args in [('--rollback',), ('--model', 'anything'), ('--unknown',)]:
            with self.subTest(args=args):
                result = self.run_cli(b'', *args)
                self.assertEqual(result.returncode, 2, result.stderr)
        oversized = self.run_cli(b'x' * 4097 + b'\n' + b'{"action":"status"}\n')
        self.assertEqual(oversized.returncode, 1)
        self.assertEqual(len(oversized.stdout.splitlines()), 1)
        self.assertEqual(json.loads(oversized.stdout)['status'], 'event-limit')
        duplicate = self.run_cli(b'{"action":"status","action":"discard"}\n')
        self.assertEqual(json.loads(duplicate.stdout)['decision'], 'withhold')
        self.assertEqual(json.loads(duplicate.stdout)['status'], 'invalid-event')

    def test_cli_accept_reopen_and_rollback_across_processes(self):
        with tempfile.TemporaryDirectory(prefix='brace-public-cli-') as directory:
            path = Path(directory).resolve() / 'lessons'
            process = subprocess.Popen(self.command('--store', path), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       cwd=tempfile.gettempdir())
            def exchange(event):
                process.stdin.write(session.encoded(event) + b'\n')
                process.stdin.flush()
                return json.loads(process.stdout.readline())
            try:
                for name, operation, function in [('Lift', 'add1', lambda x: x + 1),
                                                   ('Stretch', 'double', lambda x: 2 * x)]:
                    draft = exchange({'action': 'request', 'examples': rows(function), 'proposal': [operation]})
                    self.assertEqual(draft['status'], 'checked', draft)
                    accepted = exchange({'action': 'accept', 'draft': draft['draft']['id'], 'name': name})
                    self.assertEqual(accepted['status'], 'lesson-accepted', accepted)
                process.stdin.close()
                process.wait(timeout=30)
                self.assertEqual(process.returncode, 0, process.stderr.read())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe and not pipe.closed:
                        pipe.close()
            event = {'action': 'request', 'examples': rows(lambda x: 2 * (x + 1), (-19, -6, 7, 25)),
                     'composition': 'do Lift then Stretch'}
            reopened = self.run_cli(session.encoded(event) + b'\n', '--store', path)
            self.assertEqual(reopened.returncode, 0, reopened.stderr)
            receipt = json.loads(reopened.stdout)
            self.assertEqual(receipt['status'], 'checked', receipt)
            self.assertEqual(receipt['storage']['restore_work']['full_checks'], 2)
            self.assertEqual(receipt['work']['full_checks'], 1)
            rolled = self.run_cli(b'', '--rollback', '--store', path)
            self.assertEqual(rolled.returncode, 0, rolled.stderr)
            self.assertEqual(json.loads(rolled.stdout)['accepted_lessons'], 1)
            reopened = self.run_cli(b'{"action":"status"}\n', '--store', path)
            self.assertEqual(reopened.returncode, 0, reopened.stderr)
            self.assertEqual([item['name'] for item in json.loads(reopened.stdout)['lessons']], ['Lift'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
