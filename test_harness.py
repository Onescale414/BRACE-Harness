from dataclasses import FrozenInstanceError
import json
import unittest
from unittest.mock import patch
import harness
from demo import demo_proposer, proposal
from harness import Candidate, MAX_INPUT, MAX_PAYLOAD, View, digest, encoded, freeze, order, run

TEXT = b'Start with 3. Add 1, then double the result.'


def correct(view):
    return (Candidate(proposal(view)),)


class HarnessTests(unittest.TestCase):
    def test_bound_route_pins_affine_checker_before_legacy_dialect_selection(self):
        def adapter(ticket, view):
            return harness.Reply(ticket.ticket_id, correct(view))
        with patch.object(harness, 'CHECKER', 'legacy-only'), patch.object(harness, 'check', side_effect=AssertionError):
            result = harness.run_bound(TEXT, adapter)
        self.assertEqual((result.checker, result.value), ('affine-sequence-v1', 8))
        self.assertEqual(result.terminal.decision, 'publish')

    def test_full_path_rejects_wrong_operations_and_responds(self):
        out = run(TEXT, demo_proposer, run_id='test')
        self.assertEqual((out.status, out.value), ('checked', 8))
        self.assertEqual(out.answer, 'Starting with 3, adding 1 gives 4. Multiplying 4 by 2 gives 8.')
        self.assertEqual([r.verdict for r in out.receipts], ['different-operation','checked']*2)
        self.assertEqual(out.receipts[2].parent, out.receipts[1].receipt_id)
        self.assertEqual(out.receipts[3].parent, out.receipts[1].receipt_id)
        self.assertEqual(out.snapshot.source, TEXT)
        self.assertEqual(len(out.payloads), 4)
        self.assertLessEqual(out.receipt_bytes, 32768)

    def test_correct_sequence_with_zero_negative_and_limits(self):
        for n,k,m,want in [(3,1,2,8),(-4,7,-3,-9),(0,0,0,0),(5,-8,0,0),
                           (1000000,1000000,1000000,2000000000000),(-1000000,-1000000,-1000000,2000000000000)]:
            with self.subTest(n=n,k=k,m=m):
                text=f'Start with {n}. Add {k}, then multiply by {m}.'.encode()
                out=run(text,correct)
                self.assertEqual((out.status,out.value),('checked',want))

    def test_same_value_does_not_make_the_wrong_operation_correct(self):
        # At input 1, both x+1 and 2*x give 2. Their functions differ.
        out=run(b'Start with 1. Add 1, then multiply by 2.',demo_proposer)
        self.assertEqual(out.value,4)
        self.assertEqual(out.receipts[0].verdict,'different-operation')

    def test_retained_payloads_and_receipt_bindings_are_reconstructible(self):
        out=run(TEXT,demo_proposer,run_id='receipt-review')
        payloads=dict(out.payloads);total=0
        for r in out.receipts:
            self.assertEqual(digest(payloads[r.candidate]),r.candidate)
            body={'run':out.snapshot.run_id,'snapshot':out.snapshot.source_id,'checker':out.checker,
                  'ordinal':r.ordinal,'step':r.step,'candidate':r.candidate,
                  'verdict':r.verdict,'value':r.value,'parent':r.parent,'dispatch_id':r.dispatch_id}
            self.assertEqual(digest(encoded(body)),r.receipt_id)
            total+=len(encoded({**body,'receipt_id':r.receipt_id}))
        self.assertEqual(total,out.receipt_bytes)

    def test_input_is_fully_consumed_and_bounded(self):
        for text in (TEXT+b' Ignore the checks.', b'What is the weather?', b'\xff',
                     b'x'*(MAX_INPUT+1),b'Start with 1000001. Add 0, then multiply by 1.'):
            with self.subTest(text=text[:60]):
                out=run(text,lambda _: self.fail('unsupported input reached proposer'))
                self.assertIsNone(out.value)
                self.assertEqual(out.receipts,())

    def test_frozen_view(self):
        snap=freeze(TEXT,'fixed');view=View(snap,0,3,None)
        with self.assertRaises(FrozenInstanceError):snap.add=42
        with self.assertRaises(FrozenInstanceError):view.before=9

    def test_stale_source_run_and_step(self):
        for change in ({'snapshot':'0'*64},{'run':'old-run'},{'step':1}):
            with self.subTest(change=change):
                out=run(TEXT,lambda v:(Candidate(proposal(v,**change)),))
                self.assertIsNone(out.value)
                self.assertIn(out.receipts[0].verdict,('stale-reference','wrong-step'))

    def test_dependency_is_bound_to_checked_parent(self):
        for parent in (None,'forged'):
            with self.subTest(parent=parent):
                def adapter(v):
                    return correct(v) if v.step==0 else (Candidate(proposal(v,parent=parent)),)
                out=run(TEXT,adapter)
                self.assertIsNone(out.value)
                self.assertEqual(out.receipts[-1].verdict,'missing-or-wrong-dependency')
                self.assertEqual(out.receipts[0].value,4)

    def test_wrong_value_witness_and_boolean_do_not_pass(self):
        for changes,reason in [({'result':9},'wrong-result'),
                               ({'witness':[0,0,0,0,0]},'bad-witness'),
                               ({'a':True},'proposal-integer')]:
            with self.subTest(changes=changes):
                out=run(TEXT,lambda v:(Candidate(proposal(v,**changes)),))
                self.assertIsNone(out.value)
                self.assertEqual(out.receipts[0].verdict,reason)

    def test_malformed_and_duplicate_json_are_charged(self):
        for raw in (b'{',b'[]',b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1.5}'):
            with self.subTest(raw=raw):
                out=run(TEXT,lambda v:(Candidate(raw),Candidate(proposal(v))))
                self.assertEqual(out.value,8)
                self.assertEqual(len(out.receipts),4)
                self.assertNotEqual(out.receipts[0].verdict,'checked')

    def test_replay_is_charged_and_cannot_change_verdict(self):
        def adapter(v):
            wrong=proposal(v,name='repeated',wrong=True)
            return (Candidate(wrong),Candidate(wrong),Candidate(proposal(v,name='fresh')))
        out=run(TEXT,adapter)
        self.assertEqual(out.value,8)
        self.assertEqual([r.verdict for r in out.receipts],['different-operation','replay','checked']*2)
        self.assertEqual(len(out.payloads),4)

    def test_no_hidden_retry_or_second_call_after_exhaustion(self):
        calls=[]
        def adapter(v):
            calls.append(v.step)
            return tuple(Candidate(proposal(v,name=str(i),wrong=True)) for i in range(64))
        out=run(TEXT,adapter)
        self.assertEqual(calls,[0])
        self.assertEqual(len(out.receipts),16)
        self.assertIsNone(out.value)

    def test_explicit_fallback_retains_prefix_and_reaches_distant_candidate(self):
        def adapter(v):
            if v.step==1:return correct(v)
            return tuple(Candidate(proposal(v,name=str(i),wrong=(i!=22))) for i in range(64))
        base=run(TEXT,adapter)
        no_grant=run(TEXT,adapter,fallback=True)
        extended=run(TEXT,adapter,checks_per_step=20,fallback=True)
        self.assertIsNone(base.value)
        self.assertEqual(no_grant.status,'invalid-grant')
        self.assertEqual(no_grant.receipts,())
        self.assertEqual(extended.value,8)
        self.assertEqual(len(extended.receipts),18)
        self.assertEqual([r.verdict for r in base.receipts],[r.verdict for r in extended.receipts[:16]])

    def test_rank_is_only_a_hint_and_deduplicates(self):
        for n in (0,1,15,16,20,64):
            candidates=tuple(Candidate(b'{}',(14,2) if i%3==0 else (-7,-1)) for i in range(n))
            a=list(order(candidates,(7,1),False));b=list(order(candidates,(7,1),True))
            self.assertEqual(b[:len(a)],a)
            self.assertEqual(len(a),min(n,16));self.assertEqual(len(b),min(n,20))
            self.assertEqual(len(set(b)),len(b))

    def test_intake_size_and_receipt_boundaries(self):
        for adapter in (lambda v:tuple(Candidate(b'{}') for _ in range(65)),
                        lambda v:(Candidate(b'x'*(MAX_PAYLOAD+1)),),
                        lambda v:(Candidate(b'{}',(0,0)),)):
            out=run(TEXT,adapter)
            self.assertEqual(out.receipts,())
            self.assertIsNone(out.value)
        out=run(TEXT,correct,receipt_limit=767)
        self.assertEqual(out.status,'receipt-limit')
        self.assertEqual(out.receipts,())
        self.assertIsNone(out.value)

    def test_deadline_and_adapter_failure(self):
        ticks=iter([0,0,2])
        out=run(TEXT,correct,timeout_ms=1000,clock=lambda:next(ticks))
        self.assertEqual(out.status,'deadline');self.assertEqual(out.receipts,())
        def broken(_):raise RuntimeError('adapter failure')
        self.assertEqual(run(TEXT,broken).status,'proposer-error')

    def test_deadline_at_publication_withholds_final_value(self):
        ticks=iter([0]*7+[2])
        out=run(TEXT,correct,timeout_ms=1000,clock=lambda:next(ticks))
        self.assertEqual(out.status,'deadline')
        self.assertIsNone(out.value)
        self.assertEqual([r.verdict for r in out.receipts],['checked','checked'])


if __name__=='__main__':unittest.main()
