"""Bounded research reader for two additive mentions in an English request.

Positions are Python string offsets into the original input (half-open).
The prior reader supplies its bounded integer lexer, never its decisions.
"""
import re

from repeat_reader import _LEXEME, _value


def rx(pattern):
    return re.compile(pattern, re.I | re.X)


# The character substitutions all preserve the length of the source string.
_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ’‘“”−",
                      "abcdefghijklmnopqrstuvwxyz''\"\"-")
_START = rx(r"""(?:\b(?:start(?:ed|ing|s)?|beg[ai]n|beginning|open(?:ed|ing)?)
                (?:\s+(?:the\s+)?[\w-]+\s+(?:counter|balance|score|tally))?\s+(?:at|with|from|on)
              |\b(?:i|we|you)\s+(?:have|had|were\s+at)
              |\b(?:balance|tally|score|counter|count|total|figure|value|number|amount|register|till)
                \s*(?:[:=]|\s+(?:was|is|reads|stood\s+at|stands\s+at))
              |\b(?:use|take|from)|\b(?:opening|starting|initial)\s+(?:balance|total|score)\s*(?::|of))
              \s*[$£€]?\s*$""")
_FACTOR = rx(r"\b(?:doubl(?:e[sd]?|ing)|tripl(?:e[sd]?|ing)|multiply|multiplying|multiplied|scale|times)\b")
_OBJECT = rx(r"\b(?:total|figure|thing|result|amount|balance|number|tally|score|count|till|points|everything|sum)\b")
_WRONG_OBJECT = rx(r"\b(?:starting|original|initial|opening|unchanged|each|only|fee|bonus|adjustment|credit|deposit|charge|payment|increase|instead)\b")
_END_CLAUSE = re.compile(r"[.?!;\n]")
_JOIN = rx(r"\b(?:and|then|but)\s+(?=(?:(?:i|we|you)\s+)?(?:add|put|increase|credit|apply|post|award|receive|subtract|double|triple|multiply)\b)")
_NP = r"[\w'-]+(?:\s+[\w'-]+){0,4}"
_STOP = rx(r"""\b(?:and|or|but|so|if|unless|then|before|after|because|again|also|too|as\s+well|
               is|was|were|had|has|gets?|earns?|add(?:ed)?|says?|reads?|states?|shows?|lists?|
               according|while|in\s+(?:my|the|our)\s+(?:log|notes?|ledger))\b""")
_EVENT_NOUN = (r"(?:adjustment|addition|increase|credit|refund|rebate|bonus|tip|deposit|fee|"
               r"payment|charge|entry|posting|award|transfer|delivery|pickup|return|booking|"
               r"order|job|shift|scan|trip|run|sale|callout|task|crate|carton|visit|step|instruction)")
_ACTION = rx(r"""\b(?P<verb>add(?:s|ed|ing)?|put(?:\s+(?:on|in|back))?|credit(?:ed)?|post(?:ed)?|
                 earn(?:s|ed)?|gain(?:s|ed)?|apply|applied|award(?:ed)?|pay|paid|receive(?:d)?|
                 authori[sz](?:ed|e)|increase(?:\s+(?:the\s+)?(?:running\s+)?(?:total|count|balance))?\s+by)
                 (?:\s+(?:a|an|the|another|separate|additional|second|further|extra|new|same|approved|of))*[\s:'"$£€]*$""")
_BEFORE_NOUN = rx(rf"\b(?P<label>(?:[\w'-]+\s+)?{_EVENT_NOUN})\s*(?:of|is|was|equals|added|posted|credited|reads|shows|:|=)?\s*[:'\x22$£€]*\s*$")
_UNIT = rx(r"^\s*[- ]?\s*(?P<unit>points?|tokens?|coins?|dollars?|cents?|penn(?:y|ies)|pounds?|euros?|credits?|units?|items?|tickets?|packs?|kilograms?|grams?|boxes|marbles?|chips?|stamps?|stickers?|beads?|buttons?|books?|cards?|blocks?|miles?|hours?)\b")
_PURPOSE = rx(rf"""^[\s'":-]*(?:(?:back|extra|more|too)\s+)?(?:on\s+(?:the\s+)?(?:tally|total)\s+)?
                   (?:for|as|when|upon|at|after|if|toward|towards)\s+(?:(?:the|a|an|my|our)\s+)?
                   (?P<label>{_NP})""")
_REFERENCE = rx(rf"\b(?P<label>(?:that|this|same|original|earlier|previous|first|very)\s+(?:[\w'-]+\s+)?{_EVENT_NOUN}|{_EVENT_NOUN}(?=\s+(?:you|we|i)\s+(?:already|just)))\b")
_DESIGNATOR = rx(r"""\b(?P<type>transaction|reference|ref|ticket|job|order|voucher|receipt|batch|invoice|
                                  entry|posting|customer|account|counter|customer\s+id)
                   (?:\s+(?:id|number|no\.?|reference))?\s*[#:\-]?\s*
                   (?P<code>(?=[a-z\d-]*\d)[a-z\d]+(?:-[a-z\d]+)*)\b""")
_SOURCE_UNCLEAR = rx(r"""\b(?:unknown|unclear|unconfirmed|unverified|unreadable|illegible|undated|unidentified|
                        maybe|might|possibly|perhaps|whether|sometimes|could\s+(?:be|have)|cannot\s+tell|
                        can'?t\s+tell|no\s+(?:record|date|reference|transaction|proof|confirmation)|
                        neither\s+(?:has|gives|identifies)|torn\s+off|if|unless|unconfirmed)\b""")
_OCCURRENCE = rx(r"\b(?:if|unless|ran|shipped|fulfilled|occurred|did\s+it\s+happen|posted\s+box)\b")
_BLOCK = rx(r"""\b(?:example|sample|hypothetical|simulation|pretend|suppose|imagine|practice|illustration|
                     demo|template|draft|proposed|tentative|fictional|append|digit|subtract\w*|deduct\w*|decrease\w*|remove\w*|minus\s+from|
                     divide\w*|halve\w*|percent|twice\s+the\s+bonus|reverse[ds]?|cancel(?:led|ed)?|
                     void(?:ed)?|retract(?:ed)?|denied|rejected|unauthori[sz]ed|supersed(?:ed|es)|
                     corrected\s+(?:number|quantity|amount)|changes?\s+the\s+(?:quantity|amount)|
                     instead\s+of|except\s+for)\b""")
_NEGATION = rx(r"\b(?:never|no\s+longer|do\s+not|don'?t|did\s+not|didn'?t|was\s+not|wasn'?t|not|no)\b")
_HARMLESS_NEGATION = rx(r"\b(?:not\s+(?:a|an)\s+(?:second|new|additional|separate|extra)|no\s+(?:new|additional|extra|second|other)|nothing\s+else)\b")
_SAME = rx(rf"""\b(?:in\s+other\s+words|to\s+(?:be\s+clear|rephrase|restate)|i\s+meant|
                 read[-\s]?back|reads?\s+(?:it\s+)?back|read(?:ing)?\s+back|restat(?:es?|ed|ement|ing)|
                 rephras(?:es?|ed|ing)|(?:duplicate|copy|reprint|echo|confirmation)\s+of\s+(?:the|that|my|our|this)|
                 (?:repeats?|confirms?|describes?)\s+(?:the|that)\s+(?:very\s+)?(?:first|original|same|earlier)|
                 (?:that\s+)?same\s+(?:[\w'-]+\s+)?{_EVENT_NOUN}|
                 (?:one|single)\s+(?:and\s+the\s+same\s+)?(?:adjustment|entry|posting|credit|transaction)|
                 (?:already\s+(?:covered|included|counted)|you\s+just\s+entered|i\s+just\s+told\s+you\s+about)|
                 (?:size|amount|value)\s+of\s+that\s+{_EVENT_NOUN}|
                 just\s+to\s+confirm|put\s+(?:another\s+way|differently))\b""")
_DIFFERENT = rx(rf"""\b(?:another|additional|a\s+further|once\s+more|again|on\s+top\s+of\s+that|
                      (?:a\s+)?(?:second|different|separate|new)\s+(?:[\w'-]+\s+)?{_EVENT_NOUN}|
                      (?:authori[sz]ed|add(?:ed)?)\s+a\s+separate|both\s+(?:happened|occurred|were\s+posted))\b""")
_REPORT = rx(r"\b(?:says?|reads?|notes?|slips?|messages?|screens?|mail|log|reports?|list(?:s|ed)?|sometimes|reminder)\b")
_PRE_PURPOSE = rx(rf"\b(?:for|at|upon|when|after)\s+(?:(?:the|a|an|my|our)\s+)?(?P<label>{_NP})")
_COUNT = rx(r"^[-\s]+(?:person|messages?|mentions?|adjustments?|postings?|entries|copies|instructions?|events?|lines?|visitors?)\b")
_COMMITTED = rx(r"\b(?:authori[sz]ed|approved|posted|applied|entered|counted|credited|accepted|received|granted|booked|confirmed)\b")
_OBJECT_TARGET = rx(r"\b(?P<name>[\w'-]+)\s+(?P<kind>account|counter|register|tally|ledger|balance)\b")
_GENERIC = set("the a an my our its their this that original actual corrected revised updated closing final new opening initial starting running resulting adjusted whole previous current".split())


def _result(decision="pass", frame=None, mentions=None, question=None):
    return dict(decision=decision, frame=frame, mentions=mentions or [], question=question)


def _number(match):
    try:
        return _value(match)
    except (KeyError, ValueError):
        return None


def _factor(words, numbers):
    operators = list(_FACTOR.finditer(words))
    if len(operators) != 1:
        return None
    op, = operators
    rest = words[op.end():]
    phrase = re.split(r"[.?!;]", rest, maxsplit=1)[0].strip(" ,")
    obj = re.split(r"\b(?:after|once|when)\b", phrase, maxsplit=1)[0]
    if _WRONG_OBJECT.search(obj):
        return None
    if op[0].startswith(("doubl", "tripl")):
        if phrase and not (_OBJECT.search(phrase) or re.match(r"(?:it|that|what i should actually have)\b", phrase)):
            return None
        return op.start(), 2 if op[0].startswith("doubl") else 3, None
    for num in numbers:
        if num.start() < op.end():
            continue
        obj = words[op.end():num.start()].strip()
        if op[0] == "times":
            valid = not obj
        else:
            valid = obj.endswith("by") and (obj == "by" or _OBJECT.search(obj) or obj in {"it by", "that by"})
        if valid and _number(num) is not None:
            return op.start(), _number(num), num.span()
        break
    return None


def _label(words, match, offset):
    start, end = match.span("label")
    value = match["label"]
    stop = _STOP.search(value)
    if stop:
        end = start + stop.start()
    start += offset
    end += offset
    while end > start and words[end - 1] in " '-":
        end -= 1
    return (start, end) if end > start else None


def _bind(words, span, limits):
    """Attach a quantity using its local predicate and argument positions."""
    a, b = span
    low, high = limits
    breaks = list(_END_CLAUSE.finditer(words, low, a)) + list(_JOIN.finditer(words, low, a))
    left = max((m.end() for m in breaks), default=low)
    ends = list(_END_CLAUSE.finditer(words, b, high)) + list(_JOIN.finditer(words, b, high))
    right = min((m.start() for m in ends), default=high)
    before = words[left:a]
    after = words[b:right]
    action = _ACTION.search(before)
    noun = _BEFORE_NOUN.search(before)
    unit = _UNIT.match(after)
    offset = b + (unit.end() if unit else 0)
    purpose = _PURPOSE.match(words[offset:right])
    label = _label(words, purpose, offset) if purpose else None
    refs = list(_DESIGNATOR.finditer(words, left, right))
    ref = min(refs, key=lambda m: min(abs(m.start()-b), abs(m.end()-a)), default=None)
    if ref and ref.span("code") != span and (not label or label[0] <= ref.start() <= label[1]):
        label = ref.span()
    if not label:
        references = list(_REFERENCE.finditer(words, left, right))
        if references:
            label = min(references, key=lambda m: min(abs(m.start()-b), abs(m.end()-a))).span("label")
    if not label and action:
        earlier = list(_PRE_PURPOSE.finditer(words, left, left + action.start()))
        if earlier:
            label = _label(words, earlier[-1], 0)
        else:
            marked = re.search(rf"\b(?:first|second|other|new|separate)\s+{_EVENT_NOUN}\b", before)
            if marked:
                label = (left+marked.start(), left+marked.end())
    if not label and noun:
        label = _label(words, noun, left)
    nominal = re.match(rf"^[\s-]+(?P<label>{_EVENT_NOUN})\b", words[offset:right])
    if not label and nominal:
        label = _label(words, nominal, offset)
    if not label and action:
        label = (left+action.start("verb"), left+action.end("verb"))
    explicit = bool(action or noun or nominal or purpose or _REFERENCE.search(after))
    currency = words[a-1:a] if a and words[a-1] in "$£€" else None
    unit_name = unit["unit"].rstrip("s") if unit else {"$":"dollar", "£":"pound", "€":"euro"}.get(currency)
    direct = bool(action and re.search(r"(?:^|[,;]|\b(?:and|then|please|can you|could you|i|we))\s*$", before[:action.start()]))
    return dict(span=span, label=label, unit=unit_name, explicit=explicit, direct=direct,
                action=bool(action), purpose=bool(purpose), ref=ref)


def read_events(text):
    """Return an event decision, operand frame, grounded mentions and any question."""
    if not isinstance(text, str) or len(text) > 2500:
        return _result()
    words = text.translate(_FOLD)
    nums = list(_LEXEME.finditer(words))
    start = next((n for n in nums if _START.search(words[:n.start()])), None)
    factor = _factor(words, nums)
    if start is None or _number(start) is None:
        return _result()
    stop = factor[0] if factor else len(words)
    identifiers = [m.span("code") for m in _DESIGNATOR.finditer(words)]
    candidates = []
    counts = set()
    for num in nums:
        if not start.end() <= num.start() < stop or _number(num) is None:
            continue
        if any(a <= num.start() < b for a, b in identifiers):
            continue
        if _number(num) in (1, 2) and not _ACTION.search(words[:num.start()]):
            if _COUNT.match(words[num.end():]) or words[:num.start()].endswith("that "):
                counts.add(num.span())
                continue
        candidates.append((num.span(), _number(num)))
    amount_refs = list(re.compile(r"\b(?:the\s+)?same\s+amount\b").finditer(words, start.end(), stop))
    for ref in amount_refs:
        if candidates and ref.start() > candidates[0][0][1] and _ACTION.search(words[:ref.start()]):
            candidates.append((ref.span(), candidates[0][1]))
    candidates.sort()
    bound = []
    for i, (span, value) in enumerate(candidates):
        low = candidates[i-1][0][1] if i else start.end()
        high = candidates[i+1][0][0] if i+1 < len(candidates) else stop
        event = _bind(words, span, (low, high))
        if event["explicit"] and event["label"]:
            bound.append((value, event))
    if len(bound) != 2 or bound[0][0] != bound[1][0]:
        return _result()
    amount, first = bound[0]
    _, second = bound[1]
    mentions = [dict(amount_span=list(e["span"]), event_span=list(e["label"])) for _, e in bound]
    def answer(decision="pass", frame=None, question=None):
        return _result(decision, frame, mentions, question)

    if not factor or stop < second["span"][1] or _BLOCK.search(words):
        return answer()
    unit = _UNIT.match(words[start.end():])
    units = {e["unit"] for _, e in bound if e["unit"]}
    if unit:
        units.add(unit["unit"].rstrip("s"))
    if len(units) > 1:
        return answer()

    # Operands, IDs and explicit record counts have separate numerical roles.
    used = counts | {start.span(), factor[2], first["span"], second["span"]}
    for n in nums:
        if n.span() in used or any(a <= n.start() < b for a, b in identifiers):
            continue
        return answer()
    middle = words[start.end():stop]
    label1, label2 = (words[slice(*e["label"])] for _, e in bound)
    common_question = f"Do the two mentions of {amount} describe the same adjustment or two separate adjustments?"
    if _SOURCE_UNCLEAR.search(middle) or _NEGATION.search(_HARMLESS_NEGATION.sub(" ", middle)):
        if _OCCURRENCE.search(middle) or re.search(r"\b(?:never|applied|posted|authorized)\b", middle):
            return answer("uncertain", question=f"Was the adjustment of {amount} in the second mention actually authorized or applied?")
        return answer("uncertain", question=common_question)

    # The evidence tying the second mention to the first must apply locally.
    # An event name, matching figure, timestamp or customer alone proves little.
    point = second["span"][0]
    punctuation = list(_END_CLAUSE.finditer(words, first["span"][1], point))
    clause_start = punctuation[-1].end() if punctuation else first["span"][1]
    second_context = words[clause_start:stop]
    subsequent = words[second["span"][1]:stop]
    same = bool(_SAME.search(second_context))
    demonstrative = re.search(rf"\bthat\s+(?:[\w'-]+\s+)?{_EVENT_NOUN}\s+(?:was|is|of)\s*$", words[clause_start:point])
    if demonstrative or re.search(r"\b(?:that\s+is|meaning|namely|i\s+mean)\b", words[first["span"][1]:point]):
        same = True
    ref1, ref2 = first["ref"], second["ref"]
    separate_ids = False
    if ref1 and ref2 and ref1["type"] == ref2["type"] and ref1["type"] in {"entry", "transaction", "posting", "voucher"}:
        separate_ids = ref1["code"] != ref2["code"]
        if not separate_ids and re.search(r"\b(?:posted|credited|applied|approved|authorized|copy|duplicate|confirmation)\b", middle):
            same = True
    different = separate_ids or bool(_DIFFERENT.search(second_context))
    if first["purpose"] and second["purpose"] and label1 != label2 and second["action"] and not _REPORT.search(second_context):
        different = True
    if (re.search(r"\b(?:inbound|incoming)\b", label1) and re.search(r"\b(?:outbound|outgoing)\b", label2)):
        different = True
    if re.search(r"\b(?:then|next)\s+(?:please\s+)?(?:add|put|credit|apply)\b", words[first["span"][1]:point]):
        different = True
    if same and different:
        # Explicitly linked aliases can use different wording for one purpose.
        linked = re.search(r"\bboth\s+(?:descriptions|mentions|lines)\s+(?:refer\s+to|describe)\s+(?:the\s+)?same\b", subsequent)
        if linked and not separate_ids and not _DIFFERENT.search(second_context):
            different = False
        else:
            return answer("uncertain", question=common_question)
    frame = dict(start=_number(start), add=amount, multiply=factor[1])
    if same:
        if not first["direct"] and not _COMMITTED.search(middle):
            return answer("uncertain", question=f"Was the original adjustment of {amount} authorized or applied?")
        targets = {m["name"] for m in _OBJECT_TARGET.finditer(words) if m["name"] not in _GENERIC}
        if len(targets) > 1 or re.search(r"\b(?:other|different|another)\s+(?:account|counter|register|customer|ledger)\b", middle):
            return answer("uncertain", question=f"Do both mentions of {amount} apply to the total being multiplied?")
        if re.search(r"\b(?:add|put|increase|credit|apply|multiply|triple|double)\b", words[stop+len(_FACTOR.search(words)[0]):]):
            return answer()
        return answer("same", frame)
    if different:
        return answer("distinct", frame)
    return answer("uncertain", question=common_question)
