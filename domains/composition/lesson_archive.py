"""Strict bounded accepted-lesson snapshots; local integrity, not authentication."""
import json
import re
import secrets

import composition_checker as checker
import learning_solver as solver

FORMAT = 'brace-accepted-lessons-v1'
# The offline transfer checks the source snapshot before changing its active
# contract. This digest identifies its original acceptance protocol only.
TRANSFER_ORIGIN_CONTRACT = '94bb74e07eadc8cb68f5fd4fa940b68f6842ad588bb7cc05848ba74ca0aec146'
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')


def require(condition, reason='store-invalid'):
    if not condition:
        raise ValueError(reason)


def parse(raw, limit=65536):
    require(type(raw) is bytes and 0 < len(raw) <= limit, 'store-size')
    depth = 0
    quoted = escaped = False
    for ch in raw:
        if quoted:
            if escaped:
                escaped = False
            elif ch == 92:
                escaped = True
            elif ch == 34:
                quoted = False
        elif ch == 34:
            quoted = True
        elif ch in (91, 123):
            depth += 1
            require(depth <= 10)
        elif ch in (93, 125):
            depth -= 1
    def integer(text):
        require(len(text) <= 50)
        return int(text)
    try:
        return json.loads(raw, object_pairs_hook=checker._unique_fields,
                          parse_int=integer, parse_float=checker._reject_number,
                          parse_constant=checker._reject_number)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError('store-invalid') from exc


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()))


def token(value, pattern=HEX32):
    require(type(value) is str and pattern.fullmatch(value) is not None)


def text_bytes(value, limit):
    require(type(value) is str and value.isascii() and len(value) <= limit)
    return value.encode('ascii')


def lesson_record(lesson):
    return dict(id=lesson.id, name=lesson.name, source=lesson.source.decode('ascii'),
                plan=list(lesson.plan), contract=lesson.contract,
                accepted_event=lesson.accepted_event, draft=lesson.draft,
                composition=None if lesson.composition is None else lesson.composition.decode('ascii'),
                acceptance=lesson.acceptance.decode('ascii'))


def pack(host):
    from learning_session import encoded, sha, MAX_RETAINED_BYTES, MAX_LESSONS
    require(len(host._lessons) <= MAX_LESSONS, 'lesson-limit')
    require(type(host._store_revision) is int and 0 <= host._store_revision < 2**63-1,
            'store-revision-limit')
    body = dict(format=FORMAT, contract=host.contract, store=host._store_id,
                revision=host._store_revision + 1,
                lessons=[lesson_record(v) for v in host._lessons.values()])
    raw = encoded(dict(body=body, sha256=sha(encoded(body))))
    require(len(raw) <= MAX_RETAINED_BYTES, 'store-size')
    return raw


def restore(host, raw):
    """All-or-nothing restore; one independent check per saved lesson, no search."""
    from learning_session import encoded, sha, Lesson, NAME, MAX_EVENTS, MAX_LESSONS, MAX_RETAINED_BYTES
    expires = host.clock() + solver.TIMEOUT_NS
    work = dict(full_checks=0, checker_scalar_operations=0, max_checks=MAX_LESSONS,
                max_scalar_operations=MAX_LESSONS * 4 * solver.MAX_STEPS,
                deadline_seconds=25, model_calls=0)
    def deadline():
        require(host.clock() < expires, 'store-open-deadline')
    if raw is None:
        return {}, secrets.token_hex(16), 0, work
    obj = parse(raw, MAX_RETAINED_BYTES)
    fields(obj, 'body sha256')
    body = obj['body']
    fields(body, 'format contract store revision lessons')
    token(obj['sha256'], HEX64)
    require(encoded(obj) == raw and sha(encoded(body)) == obj['sha256'], 'store-integrity')
    require(body['format'] == FORMAT, 'store-version')
    require(body['contract'] == host.contract, 'store-contract')
    token(body['store'])
    require(type(body['revision']) is int and 1 <= body['revision'] <= 2**63-1)
    require(type(body['lessons']) is list and 1 <= len(body['lessons']) <= MAX_LESSONS, 'lesson-limit')
    lessons, names = {}, set()
    for record in body['lessons']:
        deadline()
        fields(record, 'id name source plan contract accepted_event draft composition acceptance')
        token(record['id']); token(record['draft'])
        require(record['contract'] == host.contract, 'store-contract')
        require(type(record['name']) is str and NAME.fullmatch(record['name']) is not None)
        require(record['id'] not in lessons and record['name'].casefold() not in names, 'store-duplicate')
        require(type(record['accepted_event']) is int and 1 <= record['accepted_event'] <= MAX_EVENTS)
        source = text_bytes(record['source'], checker.MAX_SOURCE_BYTES)
        rows = checker.admit(source)
        require(type(record['plan']) is list and solver.valid_plan(tuple(record['plan'])))
        plan = tuple(record['plan'])
        acceptance = text_bytes(record['acceptance'], 4096)
        origin = parse(acceptance, 4096)
        fields(origin, 'kind owner event event_sha256 draft lesson name request_sha256 plan contract')
        require(encoded(origin) == acceptance and origin['kind'] == 'explicit-accept')
        token(origin['owner']); token(origin['event_sha256'], HEX64)
        require(type(origin['event']) is int and origin['event'] == record['accepted_event'])
        require(origin['contract'] in (host.contract, TRANSFER_ORIGIN_CONTRACT), 'store-origin-contract')
        for key in ('draft', 'name', 'plan'):
            require(origin[key] == record[key])
        require(origin['lesson'] == record['id'] and origin['request_sha256'] == sha(source))
        composition = None
        if record['composition'] is not None:
            composition = text_bytes(record['composition'], 16384)
            p = parse(composition, 16384)
            fields(p, 'expression bindings comparisons limit plan owner contract event_sha256')
            require(encoded(p) == composition and p['owner'] == origin['owner'])
            require(p['contract'] == origin['contract'], 'store-origin-contract')
            token(p['event_sha256'], HEX64)
            require(type(p['expression']) is str and p['expression'].isascii() and len(p['expression']) <= 96)
            expr = p['expression'].lower()
            requested = expr[3:].split(' then ') if expr.startswith('do ') else []
            require(2 <= len(requested) <= 3 and all(NAME.fullmatch(n) for n in requested))
            require(type(p['bindings']) is list and len(p['bindings']) == len(requested))
            require(type(p['comparisons']) is int and len(requested) <= p['comparisons'] <= 3 * MAX_LESSONS)
            require(type(p['limit']) is int and p['limit'] == 3 * MAX_LESSONS)
            bound_plan = []
            for name, binding in zip(requested, p['bindings']):
                fields(binding, 'requested_name resolved_name lesson operation source_sha256 accepted_event accepted_owner')
                token(binding['lesson'])
                require(binding['lesson'] in lessons, 'store-provenance')
                old = lessons[binding['lesson']]
                old_origin = parse(old.acceptance, 4096)
                # An earlier composition cannot cite a later contract's acceptance.
                if origin['contract'] == TRANSFER_ORIGIN_CONTRACT:
                    require(old_origin['contract'] == origin['contract'], 'store-provenance')
                require(len(old.plan) == 1 and binding['operation'] == old.plan[0], 'store-provenance')
                require(binding['requested_name'] == name == old.name.casefold())
                require(binding['resolved_name'] == old.name and binding['source_sha256'] == sha(old.source))
                require(type(binding['accepted_event']) is int and binding['accepted_event'] == old.accepted_event)
                require(binding['accepted_owner'] == old_origin['owner'], 'store-provenance')
                bound_plan.append(old.plan[0])
            require(type(p['plan']) is list and p['plan'] == bound_plan == list(plan), 'store-provenance')
        # Never trust a saved result or a checksum as arithmetic evidence.
        deadline()
        result = checker.check(rows, plan, max_steps=solver.MAX_STEPS)
        work['full_checks'] += 1
        work['checker_scalar_operations'] += result.scalar_operations
        deadline()
        require(result.status == 'checked', 'store-check-failed')
        lessons[record['id']] = Lesson(record['id'], record['name'], source, plan,
            record['contract'], record['accepted_event'], record['draft'], composition, acceptance)
        names.add(record['name'].casefold())
    deadline()
    return lessons, body['store'], body['revision'], work
