"""Public command tests: bounded inspection preserves evidence, never authorizes it."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
COMMAND = HERE / 'cli.py'
MAX_SOURCE = 1024 * 1024
HIT = ('request', 'checked', 'publish')
MISS = ('request', 'absent', 'withhold')


def encode(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def record(tag='a', status='checked', decision='publish', action='request'):
    return {'request_wire': json.dumps({'action': action, 'tag': tag}) + '\n',
            'receipt_wire': json.dumps({'status': status, 'decision': decision, 'tag': tag}) + '\n'}


def source(records=None):
    return {'version': 1, 'records': records if records is not None else [record()]}


class InspectorCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='brace-receipt-command-test-')
        cls.directory = Path(cls.temporary.name).resolve()
        cls.temp_root = Path(tempfile.gettempdir()).resolve()
        cls.serial = 0

    @classmethod
    def tearDownClass(cls):
        # Verify the exact generated directory before recursive temporary cleanup.
        if (cls.directory.parent != cls.temp_root or
                not cls.directory.name.startswith('brace-receipt-command-test-')):
            raise AssertionError('Unexpected temporary cleanup target')
        cls.temporary.cleanup()

    def invoke(self, raw=None, *, queries=(HIT,), extra=(), stdin=False, path=None):
        if raw is None:
            raw = encode(source())
        command = [sys.executable, '-I', '-S', '-B', str(COMMAND)]
        before = None
        if stdin:
            command.append('-')
        else:
            if path is None:
                type(self).serial += 1
                path = self.directory / f'source-{self.serial}.json'
                path.write_bytes(raw)
            path = Path(path)
            if path.is_file():
                before = path.read_bytes()
            command.append(str(path))
        for query in queries:
            command.extend(['--query', *query])
        command.extend(extra)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        result = subprocess.run(command, input=raw if stdin else None,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=15, creationflags=flags, check=False)
        if before is not None:
            self.assertEqual(path.read_bytes(), before, 'Inspector altered its source')
        self.assertNotIn(b'Traceback', result.stdout + result.stderr)
        return result

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', 'replace'))
        self.assertEqual(result.stderr, b'')
        value = json.loads(result.stdout)
        self.assertEqual(value['kind'], 'receipt-inspection')
        self.assertEqual(value['status'], 'inspected')
        self.assertRegex(value['source']['id'], r'^[0-9a-f]{64}$')
        return value

    def refusal(self, result):
        self.assertEqual(result.returncode, 2, result.stdout.decode('utf-8', 'replace'))
        value = json.loads(result.stdout)
        self.assertEqual(value['kind'], 'receipt-inspection')
        self.assertEqual(value['status'], 'withheld')
        self.assertIsInstance(value['reason'], str)
        self.assertTrue(value['reason'])
        self.assertNotIn('records', value)
        self.assertNotIn('queries', value)
        self.assertNotIn('source', value)
        output = (result.stdout + result.stderr).decode('utf-8', 'replace')
        self.assertNotIn(str(self.directory), output)
        self.assertNotIn(str(HERE), output)
        self.assertNotIn('receipt_secret_marker', output)
        return value

    def test_newest_two_and_exact_wires(self):
        rows = [record(str(i)) for i in range(4)]
        rows[2]['request_wire'] = '{ "action" : "request", "tag" : "two" }\r\n'
        rows[2]['receipt_wire'] = '{"status":"checked","decision":"publish","text":"λ"}\n'
        value = self.success(self.invoke(encode(source(rows))))
        self.assertEqual(value['strategy'], 'scan')
        self.assertEqual(value['source']['record_count'], 4)
        self.assertEqual(value['queries'], [{'key': list(HIT), 'positions': [3, 2]}])
        self.assertEqual(value['records'], [dict(position=i, **rows[i]) for i in (2, 3)])

    def test_no_match_and_multiple_queries_deduplicate_evidence(self):
        value = self.success(self.invoke(queries=(MISS, HIT, HIT)))
        self.assertEqual([q['positions'] for q in value['queries']], [[], [0], [0]])
        self.assertEqual(len(value['records']), 1)
        absent = self.success(self.invoke(queries=(MISS,)))
        self.assertEqual(absent['records'], [])

    def test_strategies_return_identical_evidence(self):
        rows = [record(str(i), status='checked' if i % 2 else 'refused',
                       decision='publish' if i % 2 else 'withhold') for i in range(12)]
        baseline = None
        for strategy in ('scan', 'memoized', 'indexed'):
            with self.subTest(strategy=strategy):
                value = self.success(self.invoke(encode(source(rows)),
                                                queries=(MISS, HIT, HIT),
                                                extra=('--strategy', strategy)))
                self.assertEqual(value.pop('strategy'), strategy)
                if baseline is None:
                    baseline = value
                else:
                    self.assertEqual(value, baseline)

    def test_stdin_and_file_have_identical_identity(self):
        raw = encode(source())
        file_value = self.success(self.invoke(raw))
        pipe_value = self.success(self.invoke(raw, stdin=True))
        self.assertEqual(pipe_value, file_value)

    def test_source_identity_binds_exact_wires_and_order(self):
        a, b = record('a'), record('b')
        values = [self.success(self.invoke(encode(source(rows))))
                  for rows in ([a, b], [b, a], [a, record('changed')])]
        self.assertEqual(len({v['source']['id'] for v in values}), 3)
        spaced = dict(a, request_wire=a['request_wire'] + ' ')
        value = self.success(self.invoke(encode(source([spaced, b]))))
        self.assertNotEqual(value['source']['id'], values[0]['source']['id'])

    def test_same_path_replacement_and_append_cannot_reuse_stale_hits(self):
        path = self.directory / 'replaced.json'
        for strategy in ('scan', 'memoized', 'indexed'):
            path.write_bytes(encode(source([record('a')])))
            first = self.success(self.invoke(path=path, extra=('--strategy', strategy)))
            path.write_bytes(encode(source([record('b')])))
            second = self.success(self.invoke(path=path, extra=('--strategy', strategy)))
            self.assertNotEqual(first['source']['id'], second['source']['id'])
            self.assertNotEqual(first['records'], second['records'])
            path.write_bytes(encode(source([record('b'), record('c')])))
            third = self.success(self.invoke(path=path, extra=('--strategy', strategy)))
            self.assertEqual(third['queries'][0]['positions'], [1, 0])

    def test_miss_becomes_hit_and_many_cache_keys(self):
        path = self.directory / 'miss-then-hit.json'
        path.write_bytes(encode(source()))
        self.assertEqual(self.success(self.invoke(path=path, queries=(MISS,),
                         extra=('--strategy', 'memoized')))['records'], [])
        path.write_bytes(encode(source([record('new', 'absent', 'withhold')])))
        self.assertEqual(self.success(self.invoke(path=path, queries=(MISS,),
                         extra=('--strategy', 'memoized')))['queries'][0]['positions'], [0])
        queries = tuple(('request', f'absent-{i}', 'withhold') for i in range(40)) + (HIT,)
        value = self.success(self.invoke(queries=queries, extra=('--strategy', 'memoized')))
        self.assertTrue(all(not q['positions'] for q in value['queries'][:-1]))
        self.assertEqual(value['queries'][-1]['positions'], [0])

    def test_record_and_query_boundaries(self):
        self.success(self.invoke(encode(source([record(str(i)) for i in range(32)])), queries=(HIT,) * 64))
        for rows in ([], [record()] * 33):
            self.refusal(self.invoke(encode(source(rows))))
        self.refusal(self.invoke(queries=(HIT,) * 65))

    def test_invalid_last_query_withholds_whole_batch(self):
        rows = [record('receipt_secret_marker')]
        self.refusal(self.invoke(encode(source(rows)), queries=(HIT, ('request', '', 'publish'))))
        self.refusal(self.invoke(encode(source(rows)), queries=(HIT, ('request', 'x' * 129, 'publish'))))

    def test_source_schema_wrong_types_and_unexpected_fields(self):
        bad = [None, [], True, {'version': True, 'records': [record()]},
               {'version': 2, 'records': [record()]}, {'version': 1},
               dict(source(), extra=1), source([True]), source([{'request_wire': '{}'}]),
               source([dict(record(), extra='x')]), source([dict(record(), receipt_wire=True)])]
        for value in bad:
            with self.subTest(value=repr(value)[:70]):
                self.refusal(self.invoke(encode(value)))

    def test_unsupported_request_and_receipt_shapes(self):
        bad_wires = [('', record()['receipt_wire']), ('[]', record()['receipt_wire']),
                     ('null', record()['receipt_wire']), ('{"action":true}', record()['receipt_wire']),
                     ('{"action":""}', record()['receipt_wire']), ('{}', '[]'),
                     ('{}', '{}'), ('{}', '{"status":false,"decision":"publish"}'),
                     ('{}', '{"status":"checked","decision":""}')]
        for request_wire, receipt_wire in bad_wires:
            with self.subTest(request=request_wire, receipt=receipt_wire):
                self.refusal(self.invoke(encode(source([{'request_wire': request_wire,
                                                        'receipt_wire': receipt_wire}]))))
        value = self.success(self.invoke(encode(source([dict(record(), request_wire='{}')])),
                                        queries=(('<missing>', 'checked', 'publish'),)))
        self.assertEqual(value['queries'][0]['positions'], [0])

    def test_invalid_json_utf8_duplicates_and_nonfinite_numbers(self):
        malformed = [b'{', b'\xff', b'\xef\xbb\xbf{}',
                     b'{"version":1,"version":1,"records":[]}',
                     b'{"version":NaN,"records":[]}',
                     b'{"version":Infinity,"records":[]}']
        for raw in malformed:
            with self.subTest(raw=raw[:60]):
                self.refusal(self.invoke(raw, stdin=True))
        for request_wire, receipt_wire in [
                ('{"action":"request","action":"accept"}', record()['receipt_wire']),
                ('{}', '{"status":"checked","status":"refused","decision":"publish"}'),
                ('{}', '{"status":"checked","decision":"publish","value":NaN}'),
                ('{}', '{"status":"checked","decision":"publish","value":Infinity}'),
                ('{}', '{"status":"checked","decision":"publish","value":-Infinity}')]:
            self.refusal(self.invoke(encode(source([{'request_wire': request_wire,
                                                    'receipt_wire': receipt_wire}]))))

    def test_deep_json_and_large_integer_are_clean_refusals(self):
        self.refusal(self.invoke(b'[' * 40 + b'0' + b']' * 40))
        nested = '{"status":"checked","decision":"publish","nested":' + '[' * 40 + '0' + ']' * 40 + '}'
        self.refusal(self.invoke(encode(source([dict(record(), receipt_wire=nested)]))))
        huge_number = '{"status":"checked","decision":"publish","value":' + '9' * 5000 + '}'
        self.refusal(self.invoke(encode(source([dict(record(), receipt_wire=huge_number)]))))
        # A JSON escape is legal source text; a decoded surrogate in the wire
        # string itself is not representable as valid UTF-8 and must be refused.
        self.refusal(self.invoke(encode(source([dict(record(), receipt_wire='\ud800')]))))
        self.refusal(self.invoke(encode(source([dict(record(), request_wire='\ud800')]))))

    def test_byte_limits(self):
        self.refusal(self.invoke(b' ' * (MAX_SOURCE + 1), stdin=True))
        self.refusal(self.invoke(b' ' * (MAX_SOURCE + 1)))
        self.refusal(self.invoke(encode(source([dict(record(), request_wire='x' * 4097)]))))
        self.refusal(self.invoke(encode(source([dict(record(), receipt_wire='x' * 65537)]))))

    def test_exact_wire_limits_and_quoted_structural_characters(self):
        request = {'action': 'request', 'padding': ''}
        request['padding'] = 'x' * (4096 - len(encode(request)))
        receipt = {'status': 'checked', 'decision': 'publish', 'padding': ''}
        receipt['padding'] = 'x' * (65536 - len(encode(receipt)))
        pair = {'request_wire': encode(request).decode('ascii'),
                'receipt_wire': encode(receipt).decode('ascii')}
        self.assertEqual(len(pair['request_wire'].encode('utf-8')), 4096)
        self.assertEqual(len(pair['receipt_wire'].encode('utf-8')), 65536)
        value = self.success(self.invoke(encode(source([pair]))))
        self.assertEqual(value['records'], [dict(position=0, **pair)])
        quoted = dict(record(), receipt_wire=json.dumps(
            {'status': 'checked', 'decision': 'publish', 'text': '[{' * 80 + '\\"'}))
        self.success(self.invoke(encode(source([quoted]))))

    def test_large_ascii_output_withholds_without_partial_evidence(self):
        rows = []
        queries = []
        for i in range(16):
            receipt_wire = json.dumps({'status': f'case-{i}', 'decision': 'publish',
                                       'padding': '😀' * 15000}, ensure_ascii=False)
            rows.append(dict(record(), receipt_wire=receipt_wire))
            queries.append(('request', f'case-{i}', 'publish'))
            self.assertLessEqual(len(receipt_wire.encode('utf-8')), 65536)
        raw = json.dumps(source(rows), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.assertLessEqual(len(raw), MAX_SOURCE)
        self.assertEqual(self.refusal(self.invoke(raw, queries=queries))['reason'], 'output-too-large')

    def test_cli_errors_are_structured_and_do_not_expose_paths(self):
        for extra, queries in [(('--strategy', 'unknown'), (HIT,)),
                               (('--write',), (HIT,)), ((), ())]:
            with self.subTest(extra=extra, queries=queries):
                self.refusal(self.invoke(extra=extra, queries=queries))
        self.refusal(self.invoke(path=self.directory / 'not-present.json'))
        self.refusal(self.invoke(path=self.directory))

    def test_help_and_input_files_remain_unchanged(self):
        before = hashlib.sha256(COMMAND.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, '-I', '-S', '-B', str(COMMAND), '--help'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'--query', result.stdout)
        self.assertEqual(result.stderr, b'')
        self.assertEqual(hashlib.sha256(COMMAND.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
