"""Bounded lookup in supplied receipt logs; no checker or release authority."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json

MAX_SOURCE_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 4096
MAX_RECEIPT_BYTES = 65536
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_RECORDS = 32
MAX_QUERIES = 64
MAX_DEPTH = 32
CACHE_ENTRIES = 32
STRATEGIES = ('scan', 'memoized', 'indexed')


class InputError(ValueError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def encoded(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'),
                      allow_nan=False).encode('ascii')


def unique(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise InputError('duplicate-json-key')
    return result


def no_constant(_):
    raise InputError('invalid-json')


def parse(raw):
    """Bound nesting before invoking the recursive standard-library decoder."""
    if type(raw) is not bytes:
        raise InputError('source-schema')
    try:
        text = raw.decode('utf-8')
    except UnicodeError:
        raise InputError('invalid-utf8') from None
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > MAX_DEPTH:
                raise InputError('json-too-deep')
        elif char in ']}':
            depth -= 1
    try:
        return json.loads(text, object_pairs_hook=unique, parse_constant=no_constant)
    except InputError:
        raise
    except (ValueError, RecursionError, OverflowError):
        raise InputError('invalid-json') from None


def key(value):
    if (type(value) not in (list, tuple) or len(value) != 3 or
            any(type(part) is not str or not 1 <= len(part) <= 128 for part in value)):
        raise InputError('query-key')
    return tuple(value)


@dataclass(frozen=True, slots=True)
class Record:
    position: int
    key: tuple
    request_wire: str
    receipt_wire: str


def read_source(raw):
    if type(raw) is not bytes:
        raise InputError('source-schema')
    if len(raw) > MAX_SOURCE_BYTES:
        raise InputError('source-too-large')
    source = parse(raw)
    if (type(source) is not dict or set(source) != {'version', 'records'} or
            type(source['version']) is not int or source['version'] != 1):
        raise InputError('source-schema')
    entries = source['records']
    if type(entries) is not list or not 1 <= len(entries) <= MAX_RECORDS:
        raise InputError('source-record-count')
    digest = hashlib.sha256(b'brace-inspector-wire-pairs-v1\0')
    records, total = [], 0
    for position, entry in enumerate(entries):
        if (type(entry) is not dict or set(entry) != {'request_wire', 'receipt_wire'} or
                type(entry['request_wire']) is not str or type(entry['receipt_wire']) is not str):
            raise InputError('wire-pair')
        request_wire, receipt_wire = entry['request_wire'], entry['receipt_wire']
        try:
            request_bytes, receipt_bytes = request_wire.encode('utf-8'), receipt_wire.encode('utf-8')
        except UnicodeError:
            raise InputError('invalid-utf8') from None
        total += len(request_bytes) + len(receipt_bytes)
        if (len(request_bytes) > MAX_REQUEST_BYTES or len(receipt_bytes) > MAX_RECEIPT_BYTES or
                total > MAX_SOURCE_BYTES):
            raise InputError('source-byte-limit')
        request, receipt = parse(request_bytes), parse(receipt_bytes)
        if type(request) is not dict or type(receipt) is not dict:
            raise InputError('wire-object')
        pattern = key((request.get('action', '<missing>'), receipt.get('status'), receipt.get('decision')))
        for chunk in (request_bytes, receipt_bytes):
            digest.update(len(chunk).to_bytes(4, 'big'))
            digest.update(chunk)
        records.append(Record(position, pattern, request_wire, receipt_wire))
    return digest.hexdigest(), tuple(records)


def inspect_source(raw, queries, strategy='scan'):
    """One immutable source per invocation; no state can survive replacement."""
    if type(strategy) is not str or strategy not in STRATEGIES:
        raise InputError('invalid-arguments')
    if type(queries) not in (list, tuple) or not 1 <= len(queries) <= MAX_QUERIES:
        raise InputError('query-count')
    queries = [key(query) for query in queries]
    identity, records = read_source(raw)
    index, cache = {}, OrderedDict()
    if strategy == 'indexed':
        for record in records:
            index.setdefault(record.key, []).append(record.position)
    answers, selected = [], set()
    for query in queries:
        if strategy == 'indexed':
            found = tuple(index.get(query, ())[-2:][::-1])
        elif strategy == 'memoized' and query in cache:
            found = cache[query]
            cache.move_to_end(query)
        else:
            found = []
            for record in reversed(records):
                if record.key == query:
                    found.append(record.position)
                    if len(found) == 2:
                        break
            found = tuple(found)
            if strategy == 'memoized':
                if len(cache) == CACHE_ENTRIES:
                    cache.popitem(last=False)
                cache[query] = found
        selected.update(found)
        answers.append({'key': list(query), 'positions': list(found)})
    result = {'kind': 'receipt-inspection', 'status': 'inspected',
              'source': {'id': identity, 'record_count': len(records)}, 'strategy': strategy,
              'queries': answers,
              'records': [{'position': r.position, 'request_wire': r.request_wire,
                           'receipt_wire': r.receipt_wire} for r in records if r.position in selected]}
    if len(encoded(result)) > MAX_OUTPUT_BYTES:
        raise InputError('output-too-large')
    return result
