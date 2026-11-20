"""Capture fresh public composition receipts and inspect them through the CLI."""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def command(script, arguments=(), data=b''):
    result = subprocess.run([sys.executable, '-I', '-S', '-B', str(script), *arguments],
                            input=data, capture_output=True, timeout=30)
    if result.stderr:
        raise RuntimeError('Unexpected stderr from public command')
    return result


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def run():
    events = [
        {'action': 'request', 'proposal': ['add1'],
         'examples': [[-8,-7],[0,1],[13,14],[27,28]]},
        {'action': 'discard'},
        {'action': 'request', 'proposal': [],
         'examples': [[0,0],[1,1],[420,176400],[421,177241]]},
        {'action': 'discard'},
        {'action': 'request', 'lesson_name': 'Missing',
         'examples': [[-3,-2],[2,3],[8,9],[19,20]]},
        {'action': 'request', 'proposal': ['divide'],
         'examples': [[-6,-5],[2,3],[11,12],[23,24]]},
    ]
    request_lines = [json.dumps(e, separators=(',', ':'))+'\n' for e in events]
    captured = command(ROOT/'domains/composition/cli.py', data=''.join(request_lines).encode('ascii'))
    require(captured.returncode == 0, 'Public composition command failed')
    receipt_lines = captured.stdout.decode('ascii').splitlines(keepends=True)
    require(len(receipt_lines) == len(events), 'Receipt count differs')
    receipts = [json.loads(line) for line in receipt_lines]
    require([r['status'] for r in receipts] ==
            ['checked','discarded','checked','discarded','unknown-lesson-name','invalid-plan'],
            'Unexpected outcomes')
    require(receipts[2]['repair'] and receipts[2]['work']['full_checks'] == 2, 'Repair absent')
    require(all(r.get('work',{}).get('full_checks',0) <= 2 for r in receipts), 'Check cap exceeded')
    full_checks = sum(r.get('work',{}).get('full_checks',0) for r in receipts)
    require(full_checks == 3, 'Unexpected total checker work')
    capture = {'version': 1, 'records': [
        {'request_wire': request, 'receipt_wire': receipt}
        for request,receipt in zip(request_lines,receipt_lines)]}
    raw = json.dumps(capture, separators=(',', ':')).encode('ascii')
    query = ['-', '--query','request','checked','publish',
             '--query','request','unknown-lesson-name','withhold',
             '--query','request','never-seen','withhold']
    reference = None
    for strategy in ('scan','memoized','indexed'):
        reply = command(HERE/'cli.py', query+['--strategy',strategy], raw)
        require(reply.returncode == 0, 'Inspection failed')
        result = json.loads(reply.stdout)
        require(result['status'] == 'inspected', 'Wrong inspection status')
        require([q['positions'] for q in result['queries']] == [[2,0],[4],[]], 'Wrong selected positions')
        for record in result['records']:
            i = record['position']
            require(record['request_wire'] == request_lines[i] and record['receipt_wire'] == receipt_lines[i],
                    'Evidence changed')
        result.pop('strategy')
        if reference is not None:
            require(result == reference, 'Strategies disagree')
        reference = result
    unsupported = command(HERE/'cli.py', query, b'['*40+b'0'+b']'*40)
    require(unsupported.returncode == 2 and json.loads(unsupported.stdout) ==
            {'kind':'receipt-inspection','status':'withheld','reason':'json-too-deep'},
            'Unsupported input did not withhold cleanly')
    return {'passed': True, 'captured_records': 6, 'default_strategy': 'scan',
            'checked_positions': [2,0], 'withheld_positions': [4], 'no_match_positions': [],
            'strategies_agree': True, 'exact_wires_preserved': True,
            'unsupported_input': 'json-too-deep', 'composition_full_checks': full_checks,
            'inspector_checker_calls': 0, 'model_calls': 0, 'files_written': 0,
            'scope': 'Fresh synthetic public-CLI receipts; inspection is not a new check or authorization.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
