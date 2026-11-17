"""Bind a reply to the current connector question before interpreting its action."""
import re

from reader import ITEM, read_reply


ASK = {
    "one_record": "Should I check opening one particular record for the current request?",
    "download_copy": "Should I check downloading a copy for the current request?",
}
SCOPE = re.compile(
    r"\b(?:(?:as part of|during|under|for|in|on|with) )?"
    r"(?:(?P<current>this|(?:the |my )?current)|"
    r"(?P<other>another|(?:(?:an?|the|some) )?(?:other|unrelated|different|previous|prior|earlier|next))) request\b"
)
CLAUSE_BREAK = re.compile(r"\b(?:and|or|then|but|also|while|instead)\b|;|[.!?]\s+")
ACTION = re.compile(
    r"\b(?:open|click|view|inspect|select|download|export|sav|search|list|filter|brows|check|monitor|"
    r"track|fix|repair|edit|upload|send|read|find|review|copy|detail|status|change)\w*\b"
)
DIRECTIVE = re.compile(r"^(?:(?:can|could|would|will) you (?:please )?|(?:i|we) (?:want|need) you to |please )")
IMPERATIVE = re.compile(r"^(?:open|click|select|view|inspect|download|export|save|browse|filter|check)\b")
NUMBERED = re.compile(rf"\b(?:the |a )?({ITEM}) (?:label(?:l)?ed |number(?:ed)? |id |#)\s*#?\d+(?:,\d{{3}})*\b")


def interpret(question_id, text):
    """Return (reading, optional follow-up). Unknown always leaves both checks available."""
    if question_id not in ASK or not isinstance(text, str) or len(text) > 350:
        return "unknown", None
    words = " ".join(text.lower().replace("’", "'").split())
    scopes = list(SCOPE.finditer(words))
    clauses = CLAUSE_BREAK.split(words)
    if sum(bool(ACTION.search(clause)) for clause in clauses) > 1 or len(scopes) > 1:
        return "unknown", ASK[question_id]
    if not scopes:
        if re.search(r"\brequests?\b", words):
            return "unknown", ASK[question_id]
        return read_reply(question_id, text), None
    scope, = scopes
    if scope["other"]:
        return "unknown", None

    # Normalize a single selected action. Keep the original reader's guards on
    # negation, possibilities, quotation, and unsupported wording.
    if re.search(r"\b(?:not|never) (?:for |during |in |on )?(?:this|the current) request\b", words):
        return "unknown", None
    stripped = (words[:scope.start()] + " " + words[scope.end():]).strip(" ,:-")
    stripped = " ".join(stripped.split())
    directive = DIRECTIVE.match(stripped)
    if directive:
        stripped = stripped[directive.end():].removeprefix("use to ").removesuffix("?")
    stripped = NUMBERED.sub(r"a specific \1", stripped)
    if IMPERATIVE.match(stripped):
        stripped = "i want to " + stripped
    return read_reply(question_id, stripped), None
