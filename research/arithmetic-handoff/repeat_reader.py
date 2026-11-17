"""Experimental English reader for two mentions of an additive change.

The run counter is lexical. It preserves every occurrence, including operands
with different roles. The event reader separately requires a starting quantity,
two compatible change descriptions and a final multiplier in that order.
Neither entry point performs arithmetic or issues a receipt.
"""
import re
from itertools import groupby

from gate import NUMBERS, UNIT


_CARDINAL = "|".join(word.replace(" ", r"[ -]") for word in sorted(NUMBERS, key=len, reverse=True))
_ATOM = rf"(?:[0-9]+|{_CARDINAL})"
_SCALE = r"(?:hundred|thousand|million|billion|trillion)s?"
_SCALE_PHRASE = rf"(?:(?:{_ATOM}|a) )?{_SCALE}(?: (?:and )?(?:{_ATOM}|{_SCALE}))*"
_NONINTEGER = (
    rf"{_SCALE_PHRASE}|(?:{_ATOM} )?point (?:{_ATOM})(?: (?:{_ATOM}))*|"
    r"\d+(?:[./:]\d+|,\d{3}(?!\d)|[-–—]\d+)+(?:e[+-]?\d+)?|"
    r"\.\d+(?:e[+-]?\d+)?|\d+e[+-]?\d+|\d+(?:st|nd|rd|th)|"
    rf"(?:{_ATOM}) (?:and a (?:half|quarter)|halves|thirds|quarters|fourths|fifths|tenths)"
)
_LEXEME = re.compile(
    rf"(?<![\w])(?:(?P<sign>minus |negative |plus |positive |[-+]\s*)?)"
    rf"(?:(?P<other>{_NONINTEGER})|(?P<integer>{_ATOM}))(?!\w)"
)
_LIMIT = 1_000_000


def _lexical_text(text):
    return " ".join(text.casefold().replace("’", "'").replace("−", "-").split())


def _value(match):
    token = match["integer"]
    if token is None:
        return None
    if token.isascii() and token.isdigit():
        digits = token.lstrip("0") or "0"
        if len(digits) > 7:
            return None
        value = int(digits)
    else:
        value = NUMBERS[token.replace("-", " ")]
    if value > _LIMIT:
        return None
    return -value if (match["sign"] or "").startswith(("-", "negative", "minus")) else value


def integer_runs(text):
    """Maximal runs of equal adjacent integer mentions, ordered by occurrence.

    Intervening words and punctuation do not break a run. Accept digits up to
    magnitude 1,000,000 and English cardinals zero through ninety-nine, including
    spaced and hyphenated compounds. A leading sign, plus/positive or minus/
    negative belongs to its number. Recognized decimals, fractions, scientific
    notation, grouped digits, numeric ranges and larger English compounds break
    runs. This is a bounded lexer, not a general number or unit parser.
    """
    if not isinstance(text, str):
        return []
    values = (_value(match) for match in _LEXEME.finditer(_lexical_text(text)))
    runs = []
    for value, occurrences in groupby(values):
        count = sum(1 for _ in occurrences)
        if value is not None and count >= 2:
            runs.append([value, count])
    return runs


_INT = r"(?<![\w.])-?[0-9]+(?!\w)"
_U = rf"(?:[ -](?:(?:extra|more) )?{UNIT}\b)?"
_OBJECT = r"(?:(?:the |my |our |this |that )?(?:new |updated |running |whole |final )?(?:total|score|balance|count|amount|result|number|tally)|it|that|everything)"
_CHANGE = r"(?:bonus|boost|increase|increment|addition|gain|change|award|penalty|deduction)"
_START = re.compile(
    rf"^(?:please |can you |could you )?(?:(?:(?:i|we|you|(?:the |my |a )?(?:score|counter|balance|tally)) )?"
    rf"(?:start(?:s|ed|ing)?|begin(?:s|ning)?|began) (?:with|at|from)|(?:i|we) (?:have|had)|"
    rf"(?:my |the |a )?(?:starting |initial |opening )?(?:value|balance|counter|score|tally|total|number) "
    rf"(?:is|was|reads|stands at|sits at)) (?P<start>{_INT})(?:[ -](?P<unit>{UNIT})\b)?"
)
_TAIL = (rf"(?:[.!?;,]*\s*(?:what(?:'s| is) (?:my |our |the )?(?:final |new )?"
         rf"(?:total|score|balance|count|result|answer)|what do (?:i|we|you) get|"
         rf"how many(?: {UNIT})? (?:is that|do i (?:have|end (?:up )?with)))\s*)?[.!?\s]*$")
_MULTIPLY = re.compile(
    rf"\b(?:(?:double[sd]?|doubling|triple[sd]?|tripling)(?: {_OBJECT})?|"
    rf"(?:multiply|multiplying|scale)(?: {_OBJECT})? by (?P<factor>{_INT})|"
    rf"(?:times|a factor of) (?P<times>{_INT}))" + _TAIL
)
_DET = r"(?:(?:the|a|an|my|that|this|another|a second|a further|an additional|the same|same) )?"
_VERB = (r"(?:add(?:ed|ing)?|gain(?:ed|ing)?|put in|receive(?:d)?|get|give|award(?:ed)?|"
         r"increase(?: it| the total)? by|take away|subtract(?:ed|ing)?|deduct(?:ed|ing)?|"
         r"remove(?:d)?|lose|lost|decrease(?: it| the total)? by)")
_EVENT = re.compile(
    rf"(?<!\w)(?:{_VERB} {_DET}{_INT}{_U}(?: (?:more|extra))?(?: {_CHANGE}\b)?|"
    rf"{_DET}{_INT}{_U}(?: (?:more|extra))? {_CHANGE}\b|"
    rf"{_DET}{_CHANGE} (?:of|is|was|equals) {_INT}{_U}|{_DET}{_INT}{_U})"
)
_NEGATIVE = re.compile(r"\b(?:subtract\w*|deduct\w*|remov\w*|take away|lose|lost|decrease|penalty)\b")
_UNIT_WORD = re.compile(rf"\b{UNIT}\b")
_PUNCT = re.compile(r"[\s.,;:!()—–]+")


def _words(fragment):
    return _PUNCT.sub(" ", fragment).strip()


_LEAD = re.compile(r"(?:(?:i|we|you|please|and|then|next|first|apply|use|with|now)\b *)*")
_EXIT = re.compile(r"(?:(?:and|then|next|finally|last|before|we|i|you|now|please|and lastly)\b *)*")
_RESTATED = re.compile(
    r"\b(?:in other words|that is(?: to say)?|that's(?: to say)?|i e|i mean|meaning|"
    r"to (?:be clear|clarify|rephrase|restate)|put (?:another way|differently)|"
    r"said another way|namely|which (?:is|means)|aka|the same|same|restated)\b"
)
_NEW_EVENT = re.compile(r"\b(?:another|additional|a second|a further|again|once more|a second time|"
                        r"on top of that|separately|after that|then|next|followed by)\b")
_UNCERTAIN = re.compile(r"\b(?:maybe|perhaps|possibly|or|unclear whether|(?:i'm |i am )?not sure (?:if|whether))\b")
_LINK = re.compile(r"(?:(?:and|but|i|we|you|it|is|it's|as|apply|use|with|please|also|plus)\b *)*")


def _event(match):
    words = match[0]
    token = re.search(_INT, words)[0]
    amount = int(token)
    if _NEGATIVE.search(words):
        if token.startswith("-") or len(_NEGATIVE.findall(words)) > 1:
            return None
        amount = -amount
    unit = _UNIT_WORD.search(words)
    explicit = re.search(_VERB + rf"\b|\b{_CHANGE}\b", words) is not None
    return amount, unit[0].rstrip("s") if unit else None, explicit


def read_repeat(text):
    """Classify two change mentions; a 'two' frame retains the single amount."""
    skip = {"decision": "pass", "frame": None}
    if not isinstance(text, str) or len(text) > 500:
        return skip

    def canonical(match):
        value = _value(match)
        return str(value) if value is not None else "~unsupported~"

    words = _LEXEME.sub(canonical, _lexical_text(text))
    start = _START.match(words)
    factor = _MULTIPLY.search(words)
    if not start or not factor or factor.start() <= start.end():
        return skip
    body = words[start.end():factor.start()]
    events = list(_EVENT.finditer(body))
    if len(events) != 2:
        return skip
    first, second = events
    left, right = _event(first), _event(second)
    if not left or not right or left[0] != right[0] or not left[2]:
        return skip
    units = {unit for unit in ((start["unit"] or "").rstrip("s"), left[1], right[1]) if unit}
    if len(units) > 1 or not _LEAD.fullmatch(_words(body[:first.start()])):
        return skip

    between = body[first.end():second.start()]
    after = body[second.end():]
    link = _words(between)
    tail = _words(after)
    # A complete parenthetical nominal can rename the amount just introduced.
    apposition = (between.strip() == "(" and after.lstrip().startswith(")")
                  and re.search(rf"\b{_CHANGE}\b", second[0]) and not re.match(_VERB + " ", second[0]))
    restated = bool(apposition or _RESTATED.search(link) or re.search(r"\b(?:the )?same\b", second[0]))
    second_event = bool(_NEW_EVENT.search(link) or _NEW_EVENT.search(second[0]))
    uncertain = bool(_UNCERTAIN.search(link))
    # "Again" after the second quantity modifies the addition; "then double"
    # orders the multiplier and supplies no evidence for counting additions.
    repeat_tail = re.match(r"(?:again|once more|a second time)\b", tail)
    if repeat_tail:
        second_event = True
        tail = tail[repeat_tail.end():].strip()
    remainder = _words(_UNCERTAIN.sub(" ", _NEW_EVENT.sub(" ", _RESTATED.sub(" ", link))))
    if not _LINK.fullmatch(remainder) or not _EXIT.fullmatch(tail):
        return skip
    if not right[2] and not (restated or second_event or uncertain):
        return skip
    if not right[2] and second_event and not (_NEW_EVENT.search(second[0]) or repeat_tail):
        uncertain = True
    if uncertain or restated == second_event:
        return {"decision": "ask", "frame": None}
    multiplier = factor["factor"] or factor["times"]
    if multiplier is None:
        multiplier = 2 if factor[0].startswith("doubl") else 3
    frame = {"start": int(start["start"]), "add": left[0], "multiply": int(multiplier)}
    return {"decision": "one" if restated else "two", "frame": frame}
