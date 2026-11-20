"""Optional direct connector selection and independently checked repair preview.

Four immutable bound sources, one exact selection policy, no model or file writes.
Saved arithmetic lessons and their acceptance contracts are not changed.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import time

import wiremock_preview as preview

gate = preview.gate
IDS = ('c0', 'c1', 'c2', 'c3')
POLICY = 'minimum-delay-then-path'
PROFILE = 'connector-selection-v1'
MAX_CASE_BYTES = 160 * 1024  # existing mapping-case transport ceiling
MAX_SECONDS = 60


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise gate.Withheld(reason)


def bundle_payload(case):
    return {name: case[name] for name in ('requirements', 'candidates', 'target',
            'baseTargetSHA256', 'currentTargetSHA256')}


def bound_case(case, candidate):
    return {'source': candidate['source'], 'target': case['target'],
            **{k: candidate[k] for k in ('baseSourceSHA256', 'currentSourceSHA256')},
            **{k: case[k] for k in ('baseTargetSHA256', 'currentTargetSHA256')}}


def prepare(case, work=None):
    """Validate every source and normalize units, without choosing or filtering."""
    work = work if work is not None else {}
    require(type(case) is dict and set(case) == {'id', 'requirements', 'candidates',
            'target', 'baseTargetSHA256', 'currentTargetSHA256',
            'baseBundleSHA256', 'currentBundleSHA256'}, 'invalid-case-envelope')
    require(type(case['id']) is str and len(case['id']) <= 64, 'invalid-case-id')
    req = case['requirements']
    require(type(req) is dict and set(req) == {'firstSegment', 'policy'} and
            req['policy'] == POLICY and type(req['firstSegment']) is str and
            re.fullmatch(r'[A-Za-z0-9_-]{1,32}', req['firstSegment']) is not None,
            'unsupported-selection-contract')
    require(type(case['candidates']) is list and len(case['candidates']) == 4,
            'exactly-four-sources-required')
    digest = sha(encoded(bundle_payload(case)))
    require(case['baseBundleSHA256'] == digest and case['currentBundleSHA256'] == digest,
            'stale-bundle-binding')
    oracle = gate.load_oracle()
    target = gate.bound_document(case, 'target')
    original = gate.parse_document(oracle, target, 'existing target')
    options = []
    for index, candidate in enumerate(case['candidates']):
        require(type(candidate) is dict and set(candidate) == {'id', 'source',
                'baseSourceSHA256', 'currentSourceSHA256'} and candidate['id'] == IDS[index],
                'invalid-candidate-envelope')
        source = gate.bound_document(bound_case(case, candidate), 'source')
        work['catalogSourceValidations'] = work.get('catalogSourceValidations', 0) + 1
        expected = gate.source_contract(oracle, source)
        for row in oracle.diffs(expected, original):
            require(row['path'] in gate.SCALAR_EDITS and not isinstance(row['actual'], (dict, list)),
                    'target-needs-structural-change')
        options.append({'id': candidate['id'], 'path': expected['request']['urlPath'],
                        'delayMs': expected['response']['fixedDelayMilliseconds']})
    return {'requirements': copy.deepcopy(req), 'options': options}


def choose_direct(public):
    winner = None
    for option in public['options']:
        if option['path'].split('/')[1] != public['requirements']['firstSegment']:
            continue
        key = (option['delayMs'], option['path'], option['id'])
        if winner is None or key < winner[0]:
            winner = (key, option['id'])
    return {'candidate': 'none' if winner is None else winner[1]}


def check_selection(case, proposal, work=None):
    """Re-derive from bound sources and compare independently of choose_direct."""
    work = work if work is not None else {}
    work['selectionChecks'] = work.get('selectionChecks', 0) + 1
    public = prepare(case, work)
    require(type(proposal) is dict and set(proposal) == {'candidate'} and
            type(proposal['candidate']) is str and proposal['candidate'] in (*IDS, 'none'),
            'invalid-selection-proposal')
    eligible = [o for o in public['options']
                if o['path'].split('/')[1] == public['requirements']['firstSegment']]
    selected_id = proposal['candidate']
    if selected_id == 'none':
        require(not eligible, 'eligible-option-exists')
        return {'status': 'checked-no-match', 'selectedId': None}
    selected = next((o for o in eligible if o['id'] == selected_id), None)
    require(selected is not None, 'ineligible-route')
    require(not any(o['delayMs'] < selected['delayMs'] for o in eligible), 'not-minimum-delay')
    require(not any(o['delayMs'] == selected['delayMs'] and o['path'] < selected['path']
                    for o in eligible), 'path-tie-break')
    require(not any(o['delayMs'] == selected['delayMs'] and o['path'] == selected['path'] and
                    o['id'] < selected_id for o in eligible), 'id-tie-break')
    chosen = next(c for c in case['candidates'] if c['id'] == selected_id)
    return {'status': 'checked', 'selectedId': selected_id,
            'sourceSHA256': sha(chosen['source'].encode('utf-8')),
            'targetSHA256': sha(case['target'].encode('utf-8')),
            'bundleSHA256': case['currentBundleSHA256']}


def check_handoff(bound, selection, case):
    """Bind converter inputs to the checked choice without reusing the adapter."""
    require(type(bound) is dict and set(bound) == {'source', 'target',
            'baseSourceSHA256', 'currentSourceSHA256',
            'baseTargetSHA256', 'currentTargetSHA256'}, 'converter-handoff-envelope')
    require(selection['bundleSHA256'] == sha(encoded(bundle_payload(case))),
            'converter-handoff-bundle')
    for name in ('source', 'target'):
        expected = selection[name + 'SHA256']
        require(type(bound[name]) is str and sha(bound[name].encode('utf-8')) == expected
                and bound['base' + name.title() + 'SHA256'] == expected
                and bound['current' + name.title() + 'SHA256'] == expected,
                'converter-handoff-mismatch')


def checked_choice(case, *, deadline=None):
    """Public in-memory counterpart to the CLI; never return a partial preview."""
    deadline = time.monotonic() + MAX_SECONDS if deadline is None else deadline
    work = {'selectionChecks': 0, 'mappingChecks': 0, 'catalogSourceValidations': 0,
            'selectorVisits': 0}
    base = {'profile': PROFILE, 'previewOnly': True, 'modelCalls': 0}
    try:
        # Detach the entire call boundary and enforce the same transport ceiling.
        frozen = encoded(case)
        require(len(frozen) <= MAX_CASE_BYTES, 'case-byte-limit')
        case = json.loads(frozen)
        require(time.monotonic() < deadline, 'deadline')
        public = prepare(case, work)
        work['selectorVisits'] = 4
        # The selector gets its own copy; it cannot rewrite the checked bundle.
        proposal = choose_direct(copy.deepcopy(public))
        selection = check_selection(case, proposal, work)
        if selection['status'] == 'checked-no-match':
            result = {**selection, 'patch': [], 'explanation': 'No supplied route has the required first segment.'}
        else:
            chosen = next(c for c in case['candidates'] if c['id'] == selection['selectedId'])
            bound = bound_case(case, chosen)
            check_handoff(bound, selection, case)
            work['mappingChecks'] = 1
            result = preview.checked_preview(gate.load_oracle(), bound)
            require(result.get('status') == 'checked', 'mapping-not-checked')
            result = {**result, 'selectedId': selection['selectedId']}
        result.update(base, decision='publish', bundleSHA256=case['currentBundleSHA256'], work=work)
        # Include detached response construction in the deadline before release.
        detached = json.loads(encoded(result))
        require(time.monotonic() < deadline, 'deadline')
        return detached
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OSError) as exc:
        return {**base, 'decision': 'withhold', 'status': 'withheld',
                'reason': str(exc)[:256], 'work': work}


def run_file(path):
    deadline = time.monotonic() + MAX_SECONDS
    try:
        # Reuse the existing strict-keys, bounded case reader; paths are read only.
        case = gate.read_case(Path(path), gate.load_oracle())
        result = checked_choice(case, deadline=deadline)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError, OSError) as exc:
        result = {'profile': PROFILE, 'previewOnly': True, 'modelCalls': 0,
                  'decision': 'withhold', 'status': 'withheld', 'reason': str(exc)[:256],
                  'work': {'selectionChecks': 0, 'mappingChecks': 0,
                           'catalogSourceValidations': 0, 'selectorVisits': 0}}
    return (0 if result['status'] in ('checked', 'checked-no-match') else 1), result
