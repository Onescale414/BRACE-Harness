"""Independent, source-bound impossibility certificates for one integer grammar.

No solver, proposal index or product imports. Each allowed operation preserves
congruence, so any finite legal composition does. Overflow only narrows that set.
"""
import hashlib
import json

OPS = ('add1', 'sub1', 'double', 'square')
MODULI = (2, 3, 5, 7)
PROFILE = 'integer-congruence-contradiction-v1'
SPEC = dict(profile=PROFILE, operations=['x+1','x-1','2*x','x*x'],
            domain='exact integers', max_steps=4, max_input=10**6, max_value=10**48)

def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')

def sha(source):
    return hashlib.sha256(source).hexdigest()

GRAMMAR = sha(encoded(SPEC))

def unique(pairs):
    out = dict(pairs)
    if len(out) != len(pairs):
        raise ValueError('duplicate-key')
    return out

def no_number(_):
    raise ValueError('non-integer')

def admit(source):
    if type(source) is not bytes or len(source) > 2048:
        raise ValueError('source-limit')
    depth = 0
    quoted = escaped = False
    for byte in source:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91,123):
            depth += 1
            if depth > 3:
                raise ValueError('source-depth')
        elif byte in (93,125):
            depth -= 1
    obj = json.loads(source, object_pairs_hook=unique, parse_float=no_number, parse_constant=no_number)
    if type(obj) is not dict or obj.keys() != {'examples'}:
        raise ValueError('source-schema')
    rows = obj['examples']
    if type(rows) is not list or len(rows) != 4:
        raise ValueError('source-rows')
    seen = {}
    for row in rows:
        if type(row) is not list or len(row) != 2 or any(type(v) is not int for v in row):
            raise ValueError('source-values')
        x,y = row
        if abs(x)>10**6 or abs(y)>10**48:
            raise ValueError('source-bounds')
        if x in seen and seen[x] != y:
            raise ValueError('source-conflict')
        seen[x]=y
    return rows

def verify(source, witness):
    result = dict(status='invalid-certificate', scalar_operations=0,
                  source_bytes_parsed=0, source_bytes_hashed=0)
    if type(witness) is not dict or witness.keys() != {'profile','grammar','source_sha256','modulus','rows'}:
        return result
    if witness['profile'] != PROFILE or witness['grammar'] != GRAMMAR:
        return result
    modulus, indices = witness['modulus'], witness['rows']
    if type(modulus) is not int or modulus not in MODULI:
        return result
    if (type(indices) is not list or len(indices)!=2 or
        any(type(i) is not int for i in indices) or not 0<=indices[0]<indices[1]<4):
        return result
    digest = witness['source_sha256']
    if type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        return result
    if type(source) is not bytes or len(source)>2048:
        return result
    result['source_bytes_hashed'] = len(source)
    if sha(source) != digest:
        return result
    result['source_bytes_parsed'] = len(source)
    try:
        rows = admit(source)
    except (ValueError, UnicodeError, RecursionError):
        return result
    a,b = indices
    xa,ya = rows[a]
    xb,yb = rows[b]
    # Recompute all remainders; no detector or cached-index residue is trusted.
    residues = [xa % modulus, xb % modulus, ya % modulus, yb % modulus]
    result['scalar_operations'] = 4
    if residues[0] != residues[1] or residues[2] == residues[3]:
        result['status'] = 'not-a-contradiction'
        return result
    result.update(status='checked-contradiction', rows=[a,b], modulus=modulus,
        input_residues=residues[:2], output_residues=residues[2:],
        claim='No permitted add1/sub1/double/square composition matches these observations.')
    return result
