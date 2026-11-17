"""Interpret one reply to one of the two frozen connector questions."""
import re


ITEM = r"(?:record|item|entry|row|result|job|order|team|invoice|asset|ticket|account|event|file|user)"
OPEN = r"(?:open(?:ed|ing)?|click(?:ed|ing)?(?: on| into)?|select(?:ed|ing)?|view(?:ed|ing)?|inspect(?:ed|ing)?|pull(?:ed|ing)? up|look(?:ed|ing)? at)"
ONE = rf"(?:(?:one|a single|an individual|a particular|a specific|that|this|the selected|the individual|the specific) (?:specific |particular )?{ITEM}|(?:a|the) {ITEM} (?:by|with) (?:its |the )?id|(?:its|the|that {ITEM}'s) details|the detail(?:s)? (?:page|view))"
COLLECTION = r"(?:the |a |my |all |through |through the |the whole |the full )*(?:list|collection|catalog|table|results|matches|records|entries|items|jobs|orders|tickets|invoices|files)"
DOWNLOAD = r"(?:download(?:ed|ing)?|export(?:ed|ing)?|sav(?:e|ed|ing) (?:it|(?:a|the|my) (?:file|copy|report))|get(?:ting)? (?:a|the) (?:local |offline )?copy|tak(?:e|ing) (?:a|the) copy)"
BROWSE = r"(?:brows(?:e|ed|ing)|filter(?:ed|ing)?|search(?:ed|ing)?|scroll(?:ed|ing)?|scan(?:ned|ning)?)"
MONITOR = r"(?:check(?:ed|ing)?|watch(?:ed|ing)?|track(?:ed|ing)?|monitor(?:ed|ing)?|review(?:ed|ing)?|look(?:ed|ing)? (?:at|for)|see(?:ing)?|read(?:ing)?|inspect(?:ed|ing)?|view(?:ed|ing)?)"
STATUS = r"(?:(?:the|its|their|for|recent|any|latest|what|my|job|current) )*(?:status|progress|updates?|changes?|history|changed)"

RULES = {
    "one_record": (
        rf"(?:{OPEN} (?:up )?{ONE}|(?:go|went|going) (?:in)?to {ONE})",
        rf"(?:{BROWSE}|(?:open(?:ed|ing)?|view(?:ed|ing)?|look(?:ed|ing)? at|want(?:ed)?|need(?:ed)?) {COLLECTION})",
    ),
    "download_copy": (
        rf"(?:{DOWNLOAD}|(?:want(?:ed)?|need(?:ed)?) (?:a|the) (?:local|offline|downloadable) copy)",
        rf"(?:{MONITOR} {STATUS}|(?:want(?:ed)?|need(?:ed)?) (?:to know |to see )?{STATUS})",
    ),
}

CAUTION = re.compile(
    r"\b(?:maybe|perhaps|possibly|probably|unsure|uncertain|undecided|might|could|would|if|either|or|both|"
    r"but|then|whether or not|unless|example|option|guess|suppose|think|someone|someone's|said|says|"
    r"mentioned|quote|message|button said|don't know|can't recall|not sure|not certain|not decided)\b"
)
ACTOR = r"^(?:i|we) (?:actually |just |only |simply )?"
INTENT = (
    r"(?:(?:was|were|am|are) (?:only |just )?(?:(?:trying|looking|hoping) to )?|"
    r"(?:want(?:ed)?|need(?:ed)?|meant|tried|chose|decided) to |did )?"
)
DENIAL = r"(?:(?:did|was|were|am|are) not |didn't |wasn't |weren't |never )(?:(?:trying|looking) to |(?:want|mean|need) to )?"


def read_reply(question_id, text):
    """Return yes, no or unknown. An unknown reply never grants a check."""
    if question_id not in RULES or not isinstance(text, str) or len(text) > 350:
        return "unknown"
    s = " ".join(text.lower().replace("’", "'").split()).strip(" .!,")
    if not s or CAUTION.search(s) or re.search(r'["“”‘`?;]|(?:^|\s)\'|\'(?:\s|$)', s):
        return "unknown"
    lead = re.match(r"^(yes|yeah|yep|yup|no|nope|nah)\b[ ,.\-]*", s)
    vote = None
    if lead:
        vote = "yes" if lead[1] in ("yes", "yeah", "yep", "yup") else "no"
        s = s[lead.end():]
        if not s or s in ("that's right", "that is right"):
            return vote
    if re.search(r"[,;.!]|\b(?:and|instead of|without)\b", s):
        return "unknown"
    positive, alternative = RULES[question_id]
    subject = re.match(ACTOR, s)
    if not subject:
        return "unknown"
    phrase = s[subject.end():]
    denial = re.match(DENIAL, phrase)
    phrase = phrase[denial.end():] if denial else re.sub(r"^" + INTENT, "", phrase, count=1)
    phrase = re.sub(r"^(?:just|only|simply|actually) ", "", phrase)
    if re.search(r"\b(?:not|never|didn't|wasn't|weren't)\b", phrase):
        return "unknown"
    # An event must begin with a supported act. Conflicting evidence anywhere
    # else in the reply keeps the question pending.
    yes = re.match(positive + r"\b", phrase)
    no = re.match(alternative + r"\b", phrase)
    if yes and not re.search(r"\b" + alternative + r"\b", phrase[yes.end():]):
        reading = "no" if denial else "yes"
    elif no and not denial and not re.search(r"\b" + positive + r"\b", phrase[no.end():]):
        reading = "no"
    else:
        return "unknown"
    return reading if vote in (None, reading) else "unknown"
