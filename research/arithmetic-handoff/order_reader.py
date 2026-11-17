"""Optional pre-check clarification for a signed change and a multiplier."""
import re

from gate import normalize


SCALAR = r"(?<![\w.])([+-]?\d{1,7})(?!\w|[.,]\d)"
START = (r"\b(?:start(?:s|ed|ing)?|begin(?:s|ning)?|began) (?:with |at |from )?|"
         r"\b(?:balance|count(?:er)?|score|total|tally|pile|jar)(?:'s| is| was| stands| sits| reads)? (?:at |of )?|"
         r"\b(?:initial(?:ly)?|starting (?:value|number)|i have|i had|i've got|there are) ")
ADD = r"\b(?:add(?:ing)?|gain(?:ing)?|increase (?:it |the total )?by|plus) "
SUB = r"\b(?:subtract(?:ing)?|deduct(?:ing)?|remov(?:e|ing)|take away|lose) "
MULT = r"(?:(?:[×*]|\bx)\s*|\b(?:times|multipl(?:y|ied|ying)(?: (?:it|that|the total|the score))?(?: by)?|factor of) )"
FACTOR = r"\b(double[sd]?|doubling|triple[sd]?|tripling)\b"
ORDER = r"(?:\b(?:order|sequence|priority|precedence)\b|(?:which|what)\b[^.!?;]{0,65}?\b(?:first|before|after))"
UNCERTAIN = (r"(?:(?:doesn't|does not|don't|do not|didn't|did not|can't|cannot|couldn't|never) "
             r"(?:say|specify|know|tell|decide|settle|state|explain|remember|mention|show|indicate|give)|"
             r"nobody knows|unsure|unclear|uncertain|not (?:sure|clear|specified|given)|no idea)")
GAP = r"[^.!?;]{0,55}?"
MISSING_ORDER = re.compile(
    rf"{UNCERTAIN}{GAP}{ORDER}|{ORDER}{GAP}(?:unclear|unspecified|unknown|undecided|ambiguous|missing|"
    r"not (?:clear|specified|given|stated|defined|decided)|isn't (?:clear|specified|given|stated|defined))|"
    r"\b(?:no (?:particular |specified |stated )?order|in either order|"
    r"(?:could|can|might) (?:come|go|happen|apply) (?:before or after|first or second))\b"
)
DISQUALIFY = re.compile(
    r'["“”‘]|(?:^|\s)\'[^\n]*?\'(?:\s|[.,?!]|$)|\b(?:example|hypothetical|suppose|imagine|yesterday|'
    r'square|divide|split|cube|ignore|instead|actually|decided|choose|chosen)\b|'
    r"\b(?:never|don't|doesn't|didn't|do not|did not|without|no|skip|avoid|not)\b|"
    r"\b(?:doubl(?:e|ing)|tripl(?:e|ing)|multiply(?:ing)?) (?:the |my |that )?(?:bonus|penalty|increment)\b"
)
GOAL = re.compile(r"\b(?:what(?:'s| is| do| would| will| should)|how (?:many|much)|"
                  r"where (?:will|do|would)|calculate|compute|find|work out|give me|tell me)\b")


def frame_from(text):
    fields = {}
    used = set()
    patterns = (
        ("start", rf"(?:{START}){SCALAR}", 1),
        ("add", ADD + SCALAR, 1), ("add", SUB + SCALAR, -1),
        ("add", rf"{SCALAR}(?:[- ](?:point|token|credit|unit)s?)?\s*(?:bonus|boost|increment|addition)\b", 1),
        ("add", rf"{SCALAR}(?:[- ](?:point|token|credit|unit)s?)?\s*(?:penalty|deduction)\b", -1),
        ("add", rf"\b(?:bonus|increment|boost) of {SCALAR}", 1),
        ("multiply", MULT + r"([+-]?\d{1,7})(?!\w|[.,]\d)", 1),
        ("multiply", r"(?<![\w.])([+-]?\d{1,7})\s*[x×](?!\w)", 1),
        ("multiply", FACTOR, 1),
    )
    for role, pattern, sign in patterns:
        for match in re.finditer(pattern, text):
            token = match[1]
            value = (2 if token.startswith("doubl") else 3) if token.isalpha() else sign * int(token)
            # A signed penalty has two possible readings ("-3 penalty").
            if sign == -1 and token[0] in "+-":
                return None
            if abs(value) > 1_000_000 or role in fields and fields[role] != value:
                return None
            if any(c.isdigit() for c in token):
                used.update(range(*match.span(1)))
            fields[role] = value
    if set(fields) == {"start", "add", "multiply"} and all(i in used for i, c in enumerate(text) if c.isdigit()):
        return fields
    return None


def order_question(frame):
    a, m = frame["add"], frame["multiply"]
    change = f"add {a}" if a >= 0 else f"subtract {-a}"
    return f"Which should I do first, {change} or multiply by {m}?"


def inspect_order(messages):
    skip = dict(decision="pass", frame=None, question=None)
    if not isinstance(messages, list) or len(messages) != 1 or not isinstance(messages[0], dict):
        return skip
    turn = messages[0]
    raw = turn.get("content")
    if turn.get("role") != "user" or not isinstance(raw, str) or len(raw) > 500:
        return skip
    text = normalize(re.sub(r"\bwhich one\b", "which", raw, flags=re.I))
    if re.search(r'["“”‘]|(?:^|\s)\'[^\n]*?\'(?:\s|[.,?!]|$)', raw):
        return skip
    if not GOAL.search(text) or not MISSING_ORDER.search(text):
        return skip
    remainder = MISSING_ORDER.sub(" ", text)
    if DISQUALIFY.search(remainder) or re.search(r"\b(?:before|after|first|then|followed by|prior to)\b", remainder):
        return skip
    frame = frame_from(text)
    if frame and frame["add"] * (frame["multiply"] - 1) != 0:
        return dict(decision="ask_order", frame=frame, question=order_question(frame))
    return skip


def continue_order(pending, reply_text):
    hold = dict(decision="clarify", frame=None)
    if not isinstance(pending, dict) or pending.get("decision") != "ask_order":
        return hold
    frame = pending.get("frame")
    if (not isinstance(frame, dict) or set(frame) != {"start", "add", "multiply"}
            or any(type(n) is not int or abs(n) > 1_000_000 for n in frame.values())
            or not frame["add"] or frame["multiply"] == 1 or pending.get("question") != order_question(frame)
            or not isinstance(reply_text, str) or len(reply_text) > 160):
        return hold
    a, m = frame["add"], frame["multiply"]
    amount = str(abs(a))
    change = (rf"add(?:ing)?(?: {a})?|addition|bonus|increase|change" if a >= 0 else
              rf"subtract(?:ing)?(?: {amount})?|deduct(?:ing)?(?: {amount})?|subtraction|deduction|penalty|change|add {a}")
    factor = rf"multiply(?:ing)?(?: (?:it |the total )?by {m})?|multiplication|multiplier|[×*x]\s*{m}(?: card)?"
    if m in (2, 3):
        factor += r"|doubl(?:e|ing)(?: it)?" if m == 2 else r"|tripl(?:e|ing)(?: it)?"
    text = normalize(reply_text).strip(" .!")
    text = re.sub(r"^(?:please |i (?:choose|mean|want) (?:to )?)", "", text)
    role = lambda terms: rf"(?:(?:apply|use|do) )?(?:(?:the|my) )?(?:{terms})"
    for first, second, decision in ((role(change), role(factor), "compute"),
                                    (role(factor), role(change), "unsupported")):
        alternatives = (rf"{first}(?: (?:goes|comes))? first|first[, ]+{first}|start with {first}|"
                        rf"{first}(?: (?:goes|comes))? before {second}|{second}(?: (?:goes|comes))? after {first}|"
                        rf"{first}(?: first)?\s*,?\s+(?:and )?then {second}")
        if re.fullmatch(alternatives, text):
            return dict(decision=decision, frame=dict(frame) if decision == "compute" else None)
    return hold
