"""In-memory affine pilot. Python 3.12+, standard library only.

Trusted Python adapters return untrusted JSON data. This is not a sandbox for
arbitrary Python callbacks. Deadlines are cooperative at controller boundaries.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time
import uuid

CHECKER = 'affine-sequence-v1'
MAX_INPUT = 2048
MAX_PAYLOAD = 1024
MAX_CANDIDATES = 64
RECEIPT_RESERVE = 768
ATTEMPT_RESERVE = 1024
PUBLICATION_RESERVE = 1024
SCOPE = 'local-response'
INTEGER_LIMIT = 10**15
_ID = re.compile(r'[A-Za-z0-9_.-]{1,64}', re.ASCII)
_NUM = r'(-?(?:0|[1-9][0-9]{0,6}))'
_GRAMMAR = re.compile(
    r'\s*Start\s+with\s+' + _NUM + r'\.\s+Add\s+' + _NUM
    + r',\s+then\s+(?:multiply\s+by\s+' + _NUM
    + r'|double\s+the\s+result)\.\s*', re.ASCII | re.IGNORECASE)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


@dataclass(frozen=True, slots=True)
class Snapshot:
    source: bytes
    source_id: str
    run_id: str
    start: int
    add: int
    multiply: int


@dataclass(frozen=True, slots=True)
class View:
    snapshot: Snapshot
    step: int
    before: int
    parent: str | None
    bearing: tuple[int, int] = (7, 1)


@dataclass(frozen=True, slots=True)
class Candidate:
    payload: bytes
    bearing: tuple[int, int] = (1, 0)


@dataclass(frozen=True, slots=True)
class Grant:
    checks_per_step: int
    fallback: bool
    receipt_limit: int
    timeout_ms: int
    attempt_limit: int
    attempt_byte_limit: int
    publication_limit: int
    payload_limit: int


@dataclass(frozen=True, slots=True)
class Ticket:
    request_id: str
    run: str
    snapshot: str
    checker: str
    scope: str
    grant_id: str
    attempt: int
    step: int
    parent: str | None
    expires_ns: int

    @property
    def ticket_id(self):
        return digest(encoded(asdict(self)))


@dataclass(frozen=True, slots=True)
class Reply:
    ticket_id: str
    candidates: tuple[Candidate, ...]


@dataclass(frozen=True, slots=True)
class Attempt:
    ticket: Ticket
    status: str


@dataclass(frozen=True, slots=True)
class Terminal:
    request_id: str
    run: str
    snapshot: str
    checker: str
    scope: str
    grant_id: str
    decision: str
    status: str
    last_receipt: str | None
    value: int | None
    evidence_id: str
    record_id: str


@dataclass(frozen=True, slots=True)
class Receipt:
    ordinal: int
    step: int
    candidate: str
    verdict: str
    value: int | None
    parent: str | None
    receipt_id: str
    dispatch_id: str


@dataclass(frozen=True, slots=True)
class Outcome:
    status: str
    answer: str
    value: int | None
    snapshot: Snapshot | None
    checker: str
    receipts: tuple[Receipt, ...]
    payloads: tuple[tuple[str, bytes], ...]
    receipt_bytes: int
    request_id: str
    grant: Grant
    attempts: tuple[Attempt, ...]
    attempt_bytes: int
    terminal: Terminal | None
    publication_bytes: int


def freeze(source: bytes, run_id: str) -> Snapshot:
    if type(source) is not bytes or len(source) > MAX_INPUT:
        raise ValueError('input-limit')
    if type(run_id) is not str or not _ID.fullmatch(run_id):
        raise ValueError('invalid-run-id')
    try:
        text = source.decode('utf-8', errors='strict')
    except UnicodeError:
        raise ValueError('invalid-utf8') from None
    match = _GRAMMAR.fullmatch(text)
    if not match:
        raise ValueError('unsupported-input')
    start, add = int(match[1]), int(match[2])
    multiply = int(match[3]) if match[3] is not None else 2
    if max(abs(start), abs(add), abs(multiply)) > 1_000_000:
        raise ValueError('operand-limit')
    return Snapshot(source, digest(source), run_id, start, add, multiply)


def _integer(text):
    if len(text.lstrip('-')) > 16:
        raise ValueError('integer-limit')
    return int(text)


def _reject_number(_):
    raise ValueError('integer-required')


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate-key')
        obj[key] = value
    return obj


def parse(payload: bytes) -> dict:
    try:
        obj = json.loads(payload.decode('utf-8'), object_pairs_hook=_pairs,
                         parse_int=_integer, parse_float=_reject_number, parse_constant=_reject_number)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError('invalid-proposal-json') from None
    keys = {'id', 'run', 'snapshot', 'step', 'parent', 'a', 'b', 'witness', 'result'}
    if type(obj) is not dict or set(obj) != keys:
        raise ValueError('proposal-schema')
    for field in ('id', 'run', 'snapshot'):
        if type(obj[field]) is not str or not _ID.fullmatch(obj[field]):
            raise ValueError('proposal-identity')
    if obj['parent'] is not None and (type(obj['parent']) is not str or not _ID.fullmatch(obj['parent'])):
        raise ValueError('proposal-parent')
    if type(obj['step']) is not int or obj['step'] not in (0, 1):
        raise ValueError('proposal-step')
    numbers = [obj['a'], obj['b'], obj['result']]
    if type(obj['witness']) is not list or len(obj['witness']) != 5:
        raise ValueError('proposal-witness')
    numbers += obj['witness']
    if any(type(n) is not int or abs(n) > INTEGER_LIMIT for n in numbers):
        raise ValueError('proposal-integer')
    return obj


def check(obj: dict, view: View) -> tuple[str, int | None]:
    """Independent expected operation comes from frozen input, not the proposer.

    Affine coefficient/witness checks derive from the earlier prepare.py checker;
    step binding, parent binding and a concrete result are additional boundaries.
    """
    if obj['run'] != view.snapshot.run_id or obj['snapshot'] != view.snapshot.source_id:
        return 'stale-reference', None
    if obj['step'] != view.step:
        return 'wrong-step', None
    if obj['parent'] != view.parent:
        return 'missing-or-wrong-dependency', None
    a, b = obj['a'], obj['b']
    if obj['witness'] != [a*x+b for x in (-2, -1, 0, 1, 2)]:
        return 'bad-witness', None
    # These coefficients establish the entire restricted affine operation,
    # not merely its output on the five witness values.
    expected = (1, view.snapshot.add) if view.step == 0 else (view.snapshot.multiply, 0)
    if (a, b) != expected:
        return 'different-operation', None
    value = a*view.before+b
    if obj['result'] != value:
        return 'wrong-result', None
    return 'checked', value


def _bearing(v):
    return (type(v) is tuple and len(v) == 2
            and all(type(x) is int and abs(x) <= 1_000_000 for x in v) and v != (0, 0))


def order(candidates: tuple[Candidate, ...], bearing, fallback: bool):
    x, y = bearing
    shared = [i for i, c in enumerate(candidates)
              if c.bearing[0]*y == c.bearing[1]*x and c.bearing[0]*x+c.bearing[1]*y > 0]
    marked = set(shared)
    ranked = shared + [i for i in range(len(candidates)) if i not in marked]
    head = ranked[:16]
    yield from head
    if fallback:
        used = set(head)
        rest = [i for i in range(len(candidates)) if i not in used]
        n = min(4, len(rest))
        for k in range(n):
            yield rest[(2*k+1)*len(rest)//(2*n)]


_AFFINE_DIALECT = (CHECKER, parse, check)


def run(source: bytes, proposer, **grants) -> Outcome:
    """Compatibility entry for a trusted, synchronous in-process function."""
    def local(ticket, view):
        return Reply(ticket.ticket_id, proposer(view))
    # Historical in-process research adapters may select a dialect before entry.
    return _run(source, local, (CHECKER, parse, check), **grants)


def _preflight(grant):
    limits = (
        (grant.receipt_limit, 65536), (grant.attempt_limit, 2),
        (grant.attempt_byte_limit, 2048), (grant.publication_limit, 1024),
        (grant.payload_limit, 40960),
    )
    if (type(grant.checks_per_step) is not int or grant.checks_per_step not in (2, 16, 20)
            or type(grant.fallback) is not bool or (grant.fallback and grant.checks_per_step != 20)
            or type(grant.timeout_ms) is not int or not 1 <= grant.timeout_ms <= 60000
            or any(type(v) is not int or not 0 <= v <= cap for v, cap in limits)):
        return 'invalid-grant'
    checks = 2 * min(grant.checks_per_step, 20 if grant.fallback else 16)
    reservations = (
        (grant.attempt_limit, 2, 'attempt-limit'),
        (grant.attempt_byte_limit, 2 * ATTEMPT_RESERVE, 'attempt-byte-limit'),
        (grant.publication_limit, PUBLICATION_RESERVE, 'publication-limit'),
        (grant.receipt_limit, checks * RECEIPT_RESERVE, 'receipt-limit'),
        (grant.payload_limit, checks * MAX_PAYLOAD, 'payload-limit'),
    )
    return next((reason for supplied, needed, reason in reservations if supplied < needed), None)


def _reply_status(reply, ticket, catalog_limit):
    if type(reply) is not Reply:
        return 'unbound-reply'
    if type(reply.ticket_id) is not str or reply.ticket_id != ticket.ticket_id:
        return 'wrong-dispatch'
    if type(reply.candidates) is not tuple or len(reply.candidates) > catalog_limit:
        return 'candidate-limit'
    if any(type(c) is not Candidate or type(c.payload) is not bytes
           or len(c.payload) > MAX_PAYLOAD or not _bearing(c.bearing) for c in reply.candidates):
        return 'invalid-catalog'
    return 'returned'


def run_bound(source: bytes, adapter, **grants) -> Outcome:
    """Two sequential legs under one host owner. A transport must return its original ticket.

    Preflight reserves worst-case serialized evidence for both legs. It allocates no buffer.
    The callback is trusted adapter code. The ticket is correlation, not authentication.
    This CPU-only pilot does not authorize network, model billing or durable writes.
    """
    return _run(source, adapter, _AFFINE_DIALECT, **grants)


def _run(source, adapter, dialect, *, run_id=None, checks_per_step=16, fallback=False,
         receipt_limit=32768, timeout_ms=1000, attempt_limit=2, attempt_byte_limit=2048,
         publication_limit=1024, payload_limit=40960, clock=time.monotonic) -> Outcome:
    started_ns = int(clock() * 1_000_000_000)
    request_id = uuid.uuid4().hex
    checker, parse_candidate, check_candidate = dialect
    grant = Grant(checks_per_step, fallback, receipt_limit, timeout_ms, attempt_limit,
                  attempt_byte_limit, publication_limit, payload_limit)
    snapshot = None
    receipts = []
    payloads = {}
    receipt_bytes = 0
    attempts = []
    attempt_bytes = 0
    admitted = False

    def finish(status, value=None):
        terminal = None
        publication_bytes = 0
        if admitted:
            body = dict(request_id=request_id, run=snapshot.run_id, snapshot=snapshot.source_id,
                        checker=checker, scope=SCOPE, grant_id=grant_id,
                        decision='publish' if status == 'checked' else 'withhold', status=status,
                        last_receipt=parent if status == 'checked' else None, value=value,
                        evidence_id=digest(encoded({'attempts': [asdict(a) for a in attempts],
                                                    'receipts': [r.receipt_id for r in receipts]})))
            terminal = Terminal(**body, record_id=digest(encoded(body)))
            publication_bytes = len(encoded(asdict(terminal)))
            if publication_bytes > PUBLICATION_RESERVE:
                raise RuntimeError('terminal exceeds reservation')
        if status == 'checked':
            intermediate = snapshot.start + snapshot.add
            answer = (f'Starting with {snapshot.start}, adding {snapshot.add} gives {intermediate}. '
                      f'Multiplying {intermediate} by {snapshot.multiply} gives {value}.')
        elif status == 'unsupported-input':
            answer = 'Use: Start with 3. Add 1, then multiply by 2.'
        else:
            answer = f'No checked final result: {status}.'
        outcome = Outcome(status, answer, value, snapshot, checker, tuple(receipts),
                          tuple(payloads.items()), receipt_bytes, request_id, grant,
                          tuple(attempts), attempt_bytes, terminal, publication_bytes)
        if status == 'checked' and int(clock() * 1_000_000_000) >= expires_ns:
            return finish('deadline')
        return outcome

    refusal = _preflight(grant)
    if refusal:
        return finish(refusal)
    try:
        snapshot = freeze(source, request_id if run_id is None else run_id)
    except ValueError as exc:
        return finish(str(exc))
    grant_id = digest(encoded(asdict(grant)))
    expires_ns = started_ns + timeout_ms * 1_000_000
    catalog_limit = 2 if checks_per_step == 2 else MAX_CANDIDATES
    admitted = True
    before = snapshot.start
    parent = None
    seen = set()
    for step in (0, 1):
        view = View(snapshot, step, before, parent)
        ticket = Ticket(request_id, snapshot.run_id, snapshot.source_id, checker, SCOPE, grant_id,
                        len(attempts) + 1, step, parent, expires_ns)
        if int(clock() * 1_000_000_000) >= expires_ns:
            return finish('deadline')
        attempts.append(Attempt(ticket, 'dispatched'))
        try:
            reply = adapter(ticket, view)
        except Exception:
            status = 'proposer-error'
        else:
            if int(clock() * 1_000_000_000) >= expires_ns:
                status = 'deadline'
            else:
                status = _reply_status(reply, ticket, catalog_limit)
        attempt = Attempt(ticket, status)
        size = len(encoded(asdict(attempt)))
        if size > ATTEMPT_RESERVE:
            raise RuntimeError('attempt exceeds reservation')
        attempts[-1] = attempt
        attempt_bytes += size
        if status != 'returned':
            return finish(status)
        candidates = reply.candidates
        dispatch_id = ticket.ticket_id
        success = False
        for index in order(candidates, view.bearing, fallback):
            if int(clock() * 1_000_000_000) >= expires_ns:
                return finish('deadline')
            raw = candidates[index].payload
            candidate_id = digest(raw)
            try:
                obj = parse_candidate(raw)
                if obj['id'] in seen:
                    verdict, value = 'replay', None
                else:
                    seen.add(obj['id'])
                    verdict, value = check_candidate(obj, view)
            except ValueError as exc:
                verdict, value = str(exc), None
            ordinal = len(receipts)+1
            body = {'run': snapshot.run_id, 'snapshot': snapshot.source_id, 'checker': checker,
                    'dispatch_id': dispatch_id,
                    'ordinal': ordinal, 'step': step, 'candidate': candidate_id,
                    'verdict': verdict, 'value': value, 'parent': parent}
            rid = digest(encoded(body))
            size = len(encoded({**body, 'receipt_id': rid}))
            if size > RECEIPT_RESERVE:
                # A coding/schema error, not a proposer-granted escape hatch.
                raise RuntimeError('receipt reserve is too small')
            receipt_bytes += size
            payloads.setdefault(candidate_id, raw)
            receipts.append(Receipt(ordinal, step, candidate_id, verdict, value, parent, rid, dispatch_id))
            if verdict == 'checked':
                before, parent, success = value, rid, True
                break
        if not success:
            return finish(f'no-checked-proposal-step-{step+1}')
    return finish('checked', before)
