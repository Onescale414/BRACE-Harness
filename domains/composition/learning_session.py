"""Optional checked learning loop with explicitly selected local lesson storage.

The local host owns acceptance. A model can propose a plan, never a session action.
Checked lessons describe supplied examples, not unrestricted function semantics.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import secrets
import time

import composition_checker as checker
import learning_solver as solver
import lesson_archive
from lesson_store import Store, StoreUncertain
import contradiction_gate
import contradiction_checker

PROFILE = 'checked-learning-session-v1'
MAX_EVENTS = 32
MAX_LESSONS = 8
MAX_RETAINED_BYTES = 65536
MAX_EVENT_BYTES = 4096
TTL_NS = 300_000_000_000
NAME = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,31}\Z')
CLAIM = 'Matches all four supplied examples; no claim of unique or unrestricted meaning.'
MODEL_FAILURES = frozenset({
    'deadline', 'http-error', 'input-token-limit', 'invalid-plan', 'malformed-reply',
    'missing-usage', 'model-unavailable', 'ollama-unavailable', 'proposer-error',
    'reply-byte-limit', 'token-limit', 'truncated-reply',
})


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def contract_id():
    # This pins the session protocol as well as solver, checker and catalog.
    from pathlib import Path
    return sha(encoded({'profile': PROFILE, 'solver': solver.CONTRACT,
                        'session': sha(Path(__file__).read_bytes()),
                        'archive': sha(Path(lesson_archive.__file__).read_bytes()),
                        'storage': sha(Path(__file__).with_name('lesson_store.py').read_bytes()),
                        'contradiction_gate': sha(Path(contradiction_gate.__file__).read_bytes()),
                        'contradiction_checker': sha(Path(contradiction_checker.__file__).read_bytes()),
                        'contradiction_grammar': contradiction_checker.GRAMMAR,
                        'caps': [MAX_EVENTS, MAX_LESSONS, MAX_RETAINED_BYTES,
                                 MAX_EVENT_BYTES, TTL_NS]}))


@dataclass(frozen=True, slots=True)
class Pending:
    id: str
    kind: str
    source: bytes
    plans: tuple
    parent: str
    expires_ns: int
    x: int | None = None
    duplicate: int | None = None
    question: str | None = None
    composition: bytes | None = None


@dataclass(frozen=True, slots=True)
class Lesson:
    id: str
    name: str
    source: bytes
    plan: tuple
    contract: str
    accepted_event: int
    draft: str
    composition: bytes | None = None
    acceptance: bytes | None = None


class Session:
    """Trusted single-owner, single-thread local host. Not an authentication boundary.

    proposer, when supplied by the host, has the existing QwenPlan.propose API.
    It gets admitted rows and a deadline, and returns (plan, transport_event).
    No returned model field can change a grant or accept a lesson.
    """
    def __init__(self, *, clock=None, proposer=None, store=None):
        self.clock = clock or time.monotonic_ns
        self.proposer = proposer
        self.contract = contract_id()
        self.id = secrets.token_hex(16)
        self._pending = None
        self._lessons = {}
        self._records = ()
        self._events = 0
        self._closed = False
        self._store = store
        self._store_id = None
        self._store_revision = 0
        self._restore_work = {}
        if store is not None:
            raw = store.read()
            if raw is None and store.read_previous() is not None:
                raise ValueError('store-missing-current')
            (self._lessons, self._store_id, self._store_revision,
             self._restore_work) = lesson_archive.restore(self, raw)
            if self._retained_bytes() > MAX_RETAINED_BYTES:
                raise ValueError('retained-memory-limit')

    def _retained_bytes(self):
        total = sum(len(record) for record in self._records)
        if self._store is not None:
            total += len(encoded([self._store_id, self._store_revision, self._restore_work]))
        if self._pending is not None:
            p = self._pending
            fields = [p.id, p.kind, p.source.decode('ascii'), p.plans,
                      p.parent, p.expires_ns, p.x, p.duplicate, p.question]
            if p.composition is not None:
                fields.append(p.composition.decode('ascii'))
            total += len(encoded(fields))
        for v in self._lessons.values():
            fields = [v.id, v.name, v.source.decode('ascii'), v.plan,
                      v.contract, v.accepted_event, v.draft]
            if v.composition is not None:
                fields.append(v.composition.decode('ascii'))
            if v.acceptance is not None:
                fields.append(v.acceptance.decode('ascii'))
            total += len(encoded(fields))
        return total

    def handle_bytes(self, source):
        if type(source) is not bytes or len(source) > MAX_EVENT_BYTES:
            return self._invalid_event('event-limit')
        try:
            checker._limit_nesting(source)
            event = json.loads(source, object_pairs_hook=checker._unique_fields,
                               parse_float=checker._reject_number,
                               parse_constant=checker._reject_number)
        except (ValueError, RecursionError, UnicodeError):
            return self._invalid_event('invalid-event', wire_hash=sha(source))
        return self.handle(event, _wire_hash=sha(source))

    def _invalid_event(self, status, *, wire_hash=None):
        return self.handle(None, _invalid_reason=status, _wire_hash=wire_hash)

    def handle(self, event, *, _wire_hash=None, _invalid_reason=None):
        # Copy the boundary object before storing any data or dispatching a proposer.
        if self._closed or self._events >= MAX_EVENTS:
            self._closed = True
            return {'profile': PROFILE, 'decision': 'withhold', 'status': 'session-limit',
                    'session': self.id, 'events_spent': self._events}
        self._events += 1
        self._commit_deadline = None
        previous = self._pending, dict(self._lessons), self._records
        out = {'profile': PROFILE, 'session': self.id, 'event': self._events,
               'contract': self.contract, 'decision': 'withhold', 'status': 'invalid-event',
               'plan': None, 'claim': None, 'draft': None, 'question': None,
               'work': {}, 'attempts': [], 'model_events': []}
        frozen = b'null'
        try:
            if _invalid_reason is not None:
                if _wire_hash is not None:
                    out['event_sha256'] = _wire_hash
                raise ValueError('event-limit' if _invalid_reason == 'event-limit' else 'invalid-event')
            frozen = encoded(event)
            if len(frozen) > MAX_EVENT_BYTES:
                raise ValueError('event-limit')
            event = json.loads(frozen)
            if type(event) is not dict or type(event.get('action')) is not str:
                raise ValueError('invalid-event')
            out['event_sha256'] = _wire_hash or sha(frozen)
            action = event['action']
            if self._pending is not None and self.clock() >= self._pending.expires_ns:
                out['expired_handle'] = self._pending.id
                self._pending = None
                if action in ('answer', 'accept'):
                    raise ValueError('pending-expired')
            if action == 'request':
                self._request(event, out)
            elif action == 'answer':
                self._answer(event, out)
            elif action == 'accept':
                self._accept(event, out)
            elif action == 'discard':
                if set(event) != {'action'}:
                    raise ValueError('invalid-event')
                self._pending = None
                out.update(decision='control', status='discarded')
            elif action == 'status':
                if set(event) != {'action'}:
                    raise ValueError('invalid-event')
                out.update(decision='control', status='session-status',
                           pending=None if self._pending is None else
                           {'id': self._pending.id, 'kind': self._pending.kind},
                           lessons=[{'id': v.id, 'name': v.name, 'plan': list(v.plan)}
                                    for v in self._lessons.values()])
            else:
                raise ValueError('invalid-event')
        except contradiction_gate.CheckedContradiction:
            out['status'] = 'checked-contradiction'
            try:
                # Publish the retained proof only after the complete receipt has fit
                # and its clock check has succeeded. Failure leaves no proof to undo.
                if out['contradiction']['verification']['status'] != 'checked-contradiction':
                    raise ValueError('missing-verified-certificate')
                record = encoded({'event': frozen.decode('ascii'), 'result': out})
                retained = self._retained_bytes() + len(record)
                if retained > MAX_RETAINED_BYTES:
                    raise solver.Stop('retained-memory-limit')
                receipt = dict(out, memory=self._memory(retained))
                if self._store is not None:
                    receipt['storage'] = self._storage_status()
                wire = encoded(receipt)
                if len(wire) > 16384:
                    raise solver.Stop('retained-memory-limit')
                detached = json.loads(wire)
                if self.clock() >= self._commit_deadline:
                    raise solver.Stop('deadline')
                self._records += (record,)
                return detached
            except solver.Stop as exc:
                out['status'] = exc.reason
                if exc.reason == 'retained-memory-limit':
                    self._pending, self._lessons, self._records = previous
                    self._closed = True
            except Exception:
                out['status'] = 'host-error'
            out.pop('contradiction', None)
            out['checked_certificate_withheld'] = True
        except (ValueError, solver.Stop) as exc:
            status = str(exc)
            if status == 'checked-contradiction':
                status = 'host-error'
            out.update(decision='withhold', status=status, plan=None, claim=None,
                       draft=None, question=None)
        except Exception:
            consumed_question = (type(event) is dict and event.get('action') == 'answer'
                                 and previous[0] is not None and previous[0].kind == 'question'
                                 and self._pending is not previous[0])
            self._pending, self._lessons, self._records = previous
            if consumed_question:
                self._pending = None
            out.update(decision='withhold', status='host-error', plan=None, claim=None,
                       draft=None, question=None)
        record = encoded({'event': frozen.decode('ascii'), 'result': out})
        self._records += (record,)
        # Reserve the entire transition including evidence, pending and lesson copy.
        if self._retained_bytes() > MAX_RETAINED_BYTES or len(encoded(out)) > 16384:
            self._pending, self._lessons, self._records = previous
            self._closed = True
            out.update(decision='withhold', status='retained-memory-limit', plan=None,
                       claim=None, draft=None, question=None)
            out.pop('lesson', None)
        out['memory'] = self._memory(self._retained_bytes())
        detached = json.loads(encoded(out))
        if (out['decision'] != 'withhold' and self._commit_deadline is not None
                and self.clock() >= self._commit_deadline):
            # Include evidence serialization in the grant. Consume a pending answer,
            # but never commit a late publication, question or accepted lesson.
            self._pending = None
            self._lessons = previous[1]
            self._records = previous[2]
            detached.update(decision='withhold', status='deadline', plan=None,
                            claim=None, draft=None, question=None)
            detached.pop('lesson', None)
            self._records += (encoded({'event': frozen.decode('ascii'), 'result': detached}),)
            if self._retained_bytes() > MAX_RETAINED_BYTES:
                self._records = previous[2]
                self._closed = True
            detached['memory']['accepted_lessons'] = len(self._lessons)
            detached['memory']['retained_serialized_bytes'] = self._retained_bytes()
        if self._store is not None:
            detached['storage'] = self._storage_status()
            if detached['status'] == 'lesson-accepted' and detached['decision'] == 'control':
                # Publish to disk only AFTER all normal reservation/expiry checks.
                # Atomic replacement is the acceptance commit point; it precedes
                # stdout acknowledgement and is never revoked by a later clock read.
                try:
                    payload = lesson_archive.pack(self)
                    detached['storage'].update(committed=True, revision=self._store_revision + 1,
                                               snapshot_sha256=sha(payload), health='reopen-required')
                    # Reserve the complete persistence receipt before doing I/O.
                    durable_record = encoded({'event': frozen.decode('ascii'), 'result': detached})
                    self._records = self._records[:-1] + (durable_record,)
                    revision_growth = len(encoded(self._store_revision + 1)) - len(encoded(self._store_revision))
                    if self._retained_bytes() + revision_growth > MAX_RETAINED_BYTES or len(encoded(detached)) > 16384:
                        raise ValueError('retained-memory-limit')
                    receipt = self._store.commit(payload, deadline_ns=self._commit_deadline,
                                                 clock=self.clock)
                except Exception as exc:
                    self._pending, self._lessons, self._records = previous
                    self._closed = True
                    detached.update(decision='withhold',
                                    status='store-write-unconfirmed' if isinstance(exc, StoreUncertain) else 'store-commit-failed',
                                    plan=None, claim=None, draft=None, question=None)
                    detached.pop('lesson', None)
                    detached['storage'].update(committed=None if isinstance(exc, StoreUncertain) else False,
                                               revision=self._store_revision, health='reopen-required')
                    detached['storage'].pop('snapshot_sha256', None)
                    detached['storage']['error'] = str(exc)[:160]
                    detached['memory']['accepted_lessons'] = len(self._lessons)
                    detached['memory']['retained_serialized_bytes'] = self._retained_bytes()
                else:
                    self._store_revision += 1
                    detached['storage'].update(committed=True, revision=self._store_revision,
                                               snapshot_sha256=receipt['sha256'])
                    self._closed = bool(receipt.get('warnings'))
                    detached['storage']['health'] = 'reopen-required' if self._closed else 'ready'
                    self._records = self._records[:-1] + (encoded({'event': frozen.decode('ascii'),
                                                                 'result': detached}),)
                    detached['memory']['retained_serialized_bytes'] = self._retained_bytes()
        return detached

    def _memory(self, retained):
        return {'events_spent': self._events, 'event_limit': MAX_EVENTS,
                'accepted_lessons': len(self._lessons), 'lesson_limit': MAX_LESSONS,
                'retained_serialized_bytes': retained, 'retained_limit': MAX_RETAINED_BYTES,
                'persistent': self._store is not None}

    def _storage_status(self):
        return {'store': self._store_id, 'revision': self._store_revision,
                'restore_work': dict(self._restore_work), 'committed': False, 'health': 'ready'}

    def _budget(self, out, phase):
        budget = solver.Budget(clock=self.clock)
        self._commit_deadline = budget.expires_ns
        out['work'] = budget.work
        out['grant'] = {'phase': phase, 'candidate_slots': 85, 'proposal_operations': 252,
                        'full_checks': 2, 'deadline_seconds': 25, 'model_dispatches': 1}
        return budget

    def _check(self, rows, plan, budget, out, origin):
        result = budget.check(rows, plan)
        out['attempts'].append({'origin': origin, 'plan': list(plan), 'status': result.status,
                                'failed_rows': list(result.failed_rows)})
        return result

    def _search_with_contradiction(self, source, rows, budget, out):
        search = solver.Search(rows, budget)
        out['search'] = search.metadata
        contradiction_gate.try_refuse(search, source, out)
        return search

    def _offer(self, source, plan, budget, out, *, parent, question=None, composition=None):
        budget.deadline()
        token = secrets.token_hex(16)
        pending = Pending(token, 'draft', source, (plan,), parent,
                          self.clock() + TTL_NS, question=question, composition=composition)
        budget.deadline()
        self._pending = pending
        out.update(decision='publish', status='checked', plan=list(plan), claim=CLAIM,
                   draft={'id': token, 'request_sha256': sha(source),
                          'acceptance_required': True, 'scope': CLAIM})
        if composition is not None:
            out['draft']['composition_sha256'] = sha(composition)

    def _compose(self, event, source, rows, budget, out):
        """Resolve live accepted primitives, then check exactly that ordered plan."""
        out['grant']['model_dispatches'] = 0
        if event.get('clarify', False):
            raise ValueError('composition-clarification')
        expression = event['composition']
        if type(expression) is not str or not expression.isascii() or len(expression) > 96:
            raise ValueError('invalid-composition')
        text = expression.lower()
        names = text[3:].split(' then ') if text.startswith('do ') else []
        if not 2 <= len(names) <= 3 or any(NAME.fullmatch(n) is None for n in names):
            raise ValueError('unsupported-composition')
        if len(self._lessons) > MAX_LESSONS:
            raise ValueError('lesson-limit')
        selection = {'expression': expression, 'bindings': [], 'comparisons': 0,
                     'limit': 3 * MAX_LESSONS, 'plan': None}
        out['composition_selection'] = selection
        plan = []
        for name in names:
            matches = []
            for handle, lesson in self._lessons.items():
                budget.deadline()
                selection['comparisons'] += 1
                if lesson.name.casefold() == name:
                    matches.append((handle, lesson))
                budget.deadline()
            if not matches:
                raise ValueError('unknown-lesson-name')
            if len(matches) != 1:
                raise ValueError('ambiguous-lesson-name')
            handle, lesson = matches[0]
            if lesson.contract != self.contract:
                raise ValueError('lesson-contract')
            if len(lesson.plan) != 1 or lesson.plan[0] not in checker.OPS:
                raise ValueError('composition-primitive-only')
            plan.append(lesson.plan[0])
            selection['bindings'].append({
                'requested_name': name, 'resolved_name': lesson.name, 'lesson': handle,
                'operation': lesson.plan[0], 'source_sha256': sha(lesson.source),
                'accepted_event': lesson.accepted_event})
            if lesson.acceptance is not None:
                selection['bindings'][-1]['accepted_owner'] = json.loads(lesson.acceptance)['owner']
        plan = tuple(plan)
        selection['plan'] = list(plan)
        provenance = encoded({**selection, 'owner': self.id, 'contract': self.contract,
                              'event_sha256': out['event_sha256']})
        budget.take_slot()
        result = self._check(rows, plan, budget, out, 'accepted-composition')
        if result.status == 'checked':
            self._offer(source, plan, budget, out, parent=sha(source), composition=provenance)
            return
        if result.status == 'different-output':
            out['correction'] = {
                'failed_rows': list(result.failed_rows), 'checked_outputs': list(result.outputs),
                'observed_outputs': [y for _, y in rows],
                'text': 'The named sequence disagrees with these examples. Submit a corrected '
                        'composition or corrected examples as a new request; no lesson was changed.'}
            self._search_with_contradiction(source, rows, budget, out)
            raise solver.Stop('composition-conflict')
        raise solver.Stop(result.status)

    def _request(self, event, out):
        allowed = {'action', 'examples', 'clarify', 'proposal', 'lesson', 'lesson_name', 'composition'}
        if not {'action', 'examples'} <= set(event) or not set(event) <= allowed:
            raise ValueError('invalid-event')
        if self._pending is not None:
            raise ValueError('pending-decision')
        clarify = event.get('clarify', False)
        if type(clarify) is not bool:
            raise ValueError('invalid-event')
        if sum(field in event for field in ('proposal', 'lesson', 'lesson_name', 'composition')) > 1:
            raise ValueError('conflicting-proposers')
        if 'proposal' in event and self.proposer is not None:
            raise ValueError('conflicting-proposers')
        source = encoded({'examples': event['examples']})
        rows = checker.admit(source)
        out.update(request_sha256=sha(source), examples=[list(r) for r in rows])
        budget = self._budget(out, 'request')
        budget.deadline()
        if 'composition' in event:
            self._compose(event, source, rows, budget, out)
            return
        unique = tuple(dict.fromkeys(rows))
        if clarify and len(unique) > 3:
            raise ValueError('four-distinct-clarification-limit')
        seen = set()
        hypotheses = []
        search = None

        def get_search():
            nonlocal search
            if search is None:
                search = self._search_with_contradiction(source, rows, budget, out)
            return search

        def consider(plan, origin):
            budget.take_slot()
            if not solver.valid_plan(plan):
                raise ValueError('invalid-plan')
            key = solver.class_key(plan)
            if key in seen:
                out['attempts'].append({'origin': origin, 'plan': list(plan), 'status': 'no-progress'})
                return False
            seen.add(key)
            if origin in ('qwen', 'supplied-proposal') and key[0] == 'polynomial':
                prepared = get_search()
                if prepared.permits(plan) is False:
                    out['attempts'].append({'origin': origin, 'plan': list(plan),
                        'status': 'modular-reject', 'failed_rows': [], 'check_performed': False,
                        'witness': dict(prepared.filter_witness)})
                    return False
            result = self._check(rows, plan, budget, out, origin)
            if result.status == 'checked':
                hypotheses.append(plan)
                if not clarify:
                    self._offer(source, plan, budget, out, parent=sha(source))
                    return True
            elif result.status != 'different-output':
                raise solver.Stop(result.status)
            return False

        if 'lesson' in event or 'lesson_name' in event:
            if 'lesson_name' in event:
                name = event['lesson_name']
                if type(name) is not str or NAME.fullmatch(name) is None:
                    raise ValueError('invalid-lesson-name')
                selection = {'kind': 'name', 'requested_name': name, 'resolved_name': None,
                             'handle': None, 'comparisons': 0, 'limit': MAX_LESSONS}
                out['lesson_selection'] = selection
                if len(self._lessons) > MAX_LESSONS:
                    raise ValueError('lesson-limit')
                key, matches = name.casefold(), []
                for candidate_handle, candidate in self._lessons.items():
                    budget.deadline()
                    selection['comparisons'] += 1
                    if candidate.name.casefold() == key:
                        matches.append((candidate_handle, candidate))
                    budget.deadline()
                budget.deadline()
                if not matches:
                    raise ValueError('unknown-lesson-name')
                if len(matches) != 1:
                    raise ValueError('ambiguous-lesson-name')
                handle, selected = matches[0]
                selection.update(handle=handle, resolved_name=selected.name)
            else:
                handle = event['lesson']
            if type(handle) is not str or handle not in self._lessons:
                raise ValueError('unknown-lesson')
            lesson = self._lessons[handle]
            if lesson.contract != self.contract:
                raise ValueError('lesson-contract')
            out['reused_lesson'] = handle
            if consider(lesson.plan, 'accepted-lesson'):
                return
        elif 'proposal' in event:
            value = event['proposal']
            if type(value) is not list or len(value) > 4:
                raise ValueError('invalid-plan')
            if consider(tuple(value), 'supplied-proposal'):
                return
        elif self.proposer is not None:
            # A proved contradiction needs no inference. Otherwise the existing
            # proposer protocol and usage/error validation remain authoritative.
            get_search()
            if budget.work['full_checks'] >= solver.MAX_CHECKS:
                raise solver.Stop('check-budget')
            budget.deadline()
            budget.work['model_dispatches'] = 1
            model_event = {'attempted': None, 'status': 'proposer-error',
                           'input_tokens': None, 'output_tokens': None}
            out['model_events'].append(model_event)
            try:
                plan, response = self.proposer.propose(rows, budget.expires_ns)
                if type(response) is not dict:
                    raise ValueError('model-event')
                model_event.update({k: response[k] for k in model_event if k in response})
            except Exception:
                budget.work['unknown_usage_calls'] = 1
                raise solver.Stop('proposer-error')
            budget.work['model_calls'] = int(model_event['attempted'] is True)
            invalid_usage = False
            unknown_usage = False
            for field in ('input_tokens', 'output_tokens'):
                value = model_event[field]
                if value is not None and (type(value) is not int or value < 0):
                    invalid_usage = unknown_usage = True
                    budget.work[field] = 0
                else:
                    budget.work[field] = value or 0
                    unknown_usage |= value is None
            budget.work['unknown_usage_calls'] = int(model_event['attempted'] is not False and unknown_usage)
            if invalid_usage:
                raise solver.Stop('invalid-model-usage')
            budget.deadline()
            if plan is None:
                status = model_event['status']
                if type(status) is not str or status not in MODEL_FAILURES:
                    model_event['status'] = 'invalid-model-event'
                    raise solver.Stop('invalid-model-event')
                raise solver.Stop(status)
            if model_event['input_tokens'] is None or model_event['output_tokens'] is None:
                raise solver.Stop('missing-usage')
            if model_event['input_tokens'] > 256 or model_event['output_tokens'] > 128:
                raise solver.Stop('token-limit')
            if model_event['status'] != 'submitted':
                raise solver.Stop('invalid-model-event')
            if consider(plan, 'qwen'):
                return
        if budget.work['full_checks'] >= 2:
            raise solver.Stop('check-budget')
        search = get_search()
        if budget.work['full_checks'] >= solver.MAX_CHECKS:
            raise solver.Stop('check-budget')
        out['repair'] = bool(out['attempts'])
        for plan in search.candidates(exclude=seen):
            # Search has already charged this candidate slot and screened it.
            seen.add(solver.class_key(plan))
            result = self._check(rows, plan, budget, out, 'bounded-search')
            if result.status == 'checked':
                hypotheses.append(plan)
                if not clarify:
                    self._offer(source, plan, budget, out, parent=sha(source))
                    return
                if len(hypotheses) == 2:
                    self._question(source, rows, hypotheses, budget, out)
                    return
            elif result.status != 'different-output':
                raise solver.Stop(result.status)
            if budget.work['full_checks'] >= 2:
                raise solver.Stop('check-budget')
        raise solver.Stop('insufficient-hypotheses' if clarify else 'exhausted')

    def _question(self, source, rows, plans, budget, out):
        unique = tuple(dict.fromkeys(rows))
        duplicate = next(i for i in range(len(rows) - 1, 0, -1) if rows[i] in rows[:i])
        for x in solver.PROBES:
            budget.deadline()
            if any(x == old for old, _ in unique):
                continue
            predictions = tuple(solver.eval_plan(plan, x, budget) for plan in plans)
            if predictions[0] == predictions[1]:
                continue
            token = secrets.token_hex(16)
            pending = Pending(token, 'question', source, tuple(plans), sha(source),
                              self.clock() + TTL_NS, x, duplicate)
            budget.deadline()
            self._pending = pending
            out.update(decision='clarify', status='question', question={
                'id': token, 'parent_sha256': sha(source), 'x': x,
                'predictions': list(predictions), 'plans': [list(p) for p in plans],
                'text': f'What output should input {x} produce?',
                'scope': 'Two checked hypotheses; neither prediction is an accepted observation.'})
            return
        raise solver.Stop('no-affordable-separator')

    def _answer(self, event, out):
        if set(event) != {'action', 'question', 'y'}:
            raise ValueError('invalid-event')
        p = self._pending
        if p is None or p.kind != 'question' or event['question'] != p.id:
            raise ValueError('question-binding')
        if type(event['y']) is not int or abs(event['y']) > checker.MAX_VALUE:
            raise ValueError('invalid-answer')
        budget = self._budget(out, 'explicit-answer-child')
        self._commit_deadline = min(budget.expires_ns, p.expires_ns)
        out['grant']['model_dispatches'] = 0
        budget.deadline()
        self._pending = None  # An admitted answer consumes its question once.
        original = checker.admit(p.source)
        rows = list(original)
        rows[p.duplicate] = (p.x, event['y'])
        source = encoded({'examples': rows})
        rows = checker.admit(source)
        if not set(original) <= set(rows):
            raise ValueError('lost-parent-observation')
        out.update(parent_sha256=p.parent, question_answered=p.id, answer=event['y'],
                   request_sha256=sha(source), examples=[list(r) for r in rows])
        winners = []
        for index, plan in enumerate(p.plans):
            budget.take_slot()
            result = self._check(rows, plan, budget, out, 'clarified-hypothesis')
            if result.status == 'checked':
                winners.append(plan)
            elif result.status != 'different-output':
                raise solver.Stop(result.status)
            elif index == 0:
                self._search_with_contradiction(source, rows, budget, out)
                if budget.work['full_checks'] >= solver.MAX_CHECKS:
                    raise solver.Stop('check-budget')
        budget.deadline()
        if self.clock() >= p.expires_ns:
            raise ValueError('pending-expired')
        if len(winners) != 1:
            raise ValueError('hypotheses-refuted' if not winners else 'ambiguous-child')
        self._offer(source, winners[0], budget, out, parent=p.parent, question=p.id)

    def _accept(self, event, out):
        if set(event) != {'action', 'draft', 'name'}:
            raise ValueError('invalid-event')
        p = self._pending
        if p is None or p.kind != 'draft' or event['draft'] != p.id:
            raise ValueError('draft-binding')
        name = event['name']
        if type(name) is not str or NAME.fullmatch(name) is None:
            raise ValueError('invalid-lesson-name')
        if any(v.name.casefold() == name.casefold() for v in self._lessons.values()):
            raise ValueError('lesson-name-exists')
        if len(self._lessons) >= MAX_LESSONS:
            raise ValueError('lesson-limit')
        if self.clock() >= p.expires_ns:
            raise ValueError('pending-expired')
        self._commit_deadline = p.expires_ns
        token = secrets.token_hex(16)
        lesson = Lesson(token, name, p.source, p.plans[0], self.contract, self._events, p.id,
                        composition=p.composition,
                        acceptance=None if self._store is None else encoded({
                            'kind': 'explicit-accept', 'owner': self.id, 'event': self._events,
                            'event_sha256': out['event_sha256'], 'draft': p.id, 'lesson': token,
                            'name': name, 'request_sha256': sha(p.source), 'plan': list(p.plans[0]),
                            'contract': self.contract}))
        self._lessons[token] = lesson
        self._pending = None
        out.update(decision='control', status='lesson-accepted', lesson={
            'id': token, 'name': name, 'plan': list(lesson.plan), 'draft': p.id,
            'scope': CLAIM, 'request_sha256': sha(p.source), 'explicitly_accepted': True})
        if p.composition is not None:
            out['lesson']['composition_sha256'] = sha(p.composition)
            out['lesson']['composition'] = json.loads(p.composition)


def _serve(stdin, stdout, *, proposer=None, store=None):
    """Bounded NDJSON stream; only accepted lessons may survive in a chosen store."""
    session = Session(proposer=proposer, store=store)
    for _ in range(MAX_EVENTS):
        line = stdin.readline(MAX_EVENT_BYTES + 2)
        if not line:
            return 0
        if len(line) > MAX_EVENT_BYTES or not line.endswith(b'\n'):
            # Do not drain an unbounded line or interpret its tail as another action.
            result = session._invalid_event('event-limit')
            stdout.write(encoded(result).decode('ascii') + '\n')
            stdout.flush()
            return 1
        result = session.handle_bytes(line)
        stdout.write(encoded(result).decode('ascii') + '\n')
        stdout.flush()
        if session._closed:
            return 1
    return 0


def serve(stdin, stdout, *, proposer=None, store_path=None):
    if store_path is None:
        return _serve(stdin, stdout, proposer=proposer)
    try:
        with Store(store_path) as store:
            return _serve(stdin, stdout, proposer=proposer, store=store)
    except (OSError, ValueError, RuntimeError) as exc:
        stdout.write(encoded({'profile': PROFILE, 'decision': 'withhold',
                              'status': 'store-unavailable', 'error': str(exc)[:160]}).decode('ascii') + '\n')
        stdout.flush()
        return 1


def rollback_store(path):
    """Explicit host action only: validate and restore the previous accepted snapshot."""
    with Store(path) as store:
        current = Session(store=store)  # Refuse unknown/corrupt current state as well.
        raw = store.read_previous()
        if raw is None:
            raise ValueError('store-no-previous')
        lessons, store_id, revision, work = lesson_archive.restore(current, raw)
        if store_id != current._store_id:
            raise ValueError('store-identity')
        current._lessons = lessons
        if current._retained_bytes() > MAX_RETAINED_BYTES:
            raise ValueError('retained-memory-limit')
        receipt = store.commit(raw, deadline_ns=current.clock() + solver.TIMEOUT_NS, clock=current.clock)
        return {'decision': 'control', 'status': 'lessons-rolled-back', 'store': store_id,
                'revision': revision, 'accepted_lessons': len(lessons),
                'restore_work': work, 'snapshot_sha256': receipt['sha256']}
