"""Replaceable deterministic proposer and the pilot's single CLI entry point."""
import argparse
from dataclasses import asdict
import json
from harness import Candidate, Reply, View, encoded, run_bound


def proposal(view: View, *, name='candidate', wrong=False, **changes) -> bytes:
    if view.step == 0:
        a, b = (view.snapshot.multiply, 0) if wrong else (1, view.snapshot.add)
    else:
        a, b = (1, view.snapshot.add) if wrong else (view.snapshot.multiply, 0)
    body = {'id': f'{view.step}-{name}', 'run': view.snapshot.run_id,
            'snapshot': view.snapshot.source_id, 'step': view.step, 'parent': view.parent,
            'a': a, 'b': b, 'witness': [a*x+b for x in (-2, -1, 0, 1, 2)],
            'result': a*view.before+b}
    body.update(changes)
    return encoded(body)


def demo_proposer(view: View):
    # Deliberately put an internally consistent but wrong operation at the
    # shared bearing. It receives priority, never permission to bypass checking.
    return (Candidate(proposal(view, name='wrong', wrong=True), (7, 1)),
            Candidate(proposal(view, name='correct'), (1, 0)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Small in-memory BRACE next pilot; no model calls.')
    parser.add_argument('--text', default='Start with 3. Add 1, then double the result.')
    parser.add_argument('--json', action='store_true', help='Show compact receipts as well as the answer.')
    args = parser.parse_args()
    def local_demo(ticket, view):
        return Reply(ticket.ticket_id, demo_proposer(view))
    outcome = run_bound(args.text.encode('utf-8'), local_demo)
    if args.json:
        print(json.dumps({'status': outcome.status, 'answer': outcome.answer, 'value': outcome.value,
                          'source_id': outcome.snapshot.source_id if outcome.snapshot else None,
                          'run_id': outcome.snapshot.run_id if outcome.snapshot else None,
                          'checker': outcome.checker, 'receipts': [asdict(r) for r in outcome.receipts],
                          'receipt_bytes': outcome.receipt_bytes,
                          'grant': asdict(outcome.grant),
                          'attempts': [asdict(a) for a in outcome.attempts],
                          'attempt_bytes': outcome.attempt_bytes,
                          'terminal': asdict(outcome.terminal) if outcome.terminal else None,
                          'publication_bytes': outcome.publication_bytes}, indent=2))
    else:
        print(outcome.answer)
        print(f'{len(outcome.receipts)} checks; {outcome.receipt_bytes} receipt bytes; no stored memory changes.')
