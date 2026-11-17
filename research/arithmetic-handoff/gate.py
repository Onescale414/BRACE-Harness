"""Small read-only specification for English add-then-multiply requests."""
import re


SMALL = ("zero one two three four five six seven eight nine ten eleven twelve "
         "thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
NUMBERS = {word: n for n, word in enumerate(SMALL)}
for n, word in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2):
    NUMBERS[word] = 10 * n
    NUMBERS.update({f"{word} {unit}": 10 * n + value for value, unit in enumerate(SMALL[1:10], 1)})
WORDS = re.compile(r"\b(?:" + "|".join(sorted(NUMBERS, key=len, reverse=True)) + r")\b")
NUMBER = r"(?:-?[0-9]{1,7})"
MISSING = r"(?:a few|some|an unknown amount|some number)"
UNIT = r"(?:points?|tokens?|marbles?|tickets?|coins?|dollars?|beads?|cards?|items?|books?|buttons?|blocks?|stamps?|stickers?|units?|credits?|chips?|counters?|booklets?)"
OBJECT = r"(?:(?:the |that |my |our )?(?:new |whole |updated |running )?(?:amount|total|result|balance|score|lot|number)|it|that|what i have|whatever score i've got)"
SEP = r"(?:\s*[,.;]\s*(?:(?:and )?(?:then |next )?|and )|\s+(?:and then |and |then |before ))"
START = (rf"(?:(?:(?:i |we |(?:my|our) (?:jar|box|score|balance|pile) )?(?:start|starts|started|begin|began|starting) (?:with|at)|"
         rf"i (?:have|had)|i've got|there (?:are|were)|(?:my |the )?(?:balance|score|total|starting number) (?:is|was)(?: at)?) "
         rf"(?P<start>{NUMBER})(?: (?P<start_unit>{UNIT}))?)")
ADD = (rf"(?:(?:i |we )?(?P<verb>add|added|adding|put in|toss in|gain|gained|subtract|subtracting|take away|remove|lose|lost|knocked) "
       rf"(?P<add>{NUMBER}|{MISSING})(?: (?P<add_unit>{UNIT}))?(?: more| extra| extras| off)?|"
       rf"(?:it |my score )(?:goes|went) (?P<direction>up|down) by (?P<change>{NUMBER}|{MISSING})|"
       rf"(?P<unchanged>add nothing|leave (?:it|the total) unchanged|make no change))")
MULT = (rf"(?:(?:i |we |the game )?(?:multiply|multiplying|times|scale)(?: {OBJECT})?(?: by)? (?P<multiply>{NUMBER}|{MISSING})|"
        rf"(?:i |we |the game )?(?P<factor>double|doubles|doubling|triple|triples|tripling)(?: {OBJECT})?)")
DIALOGUE = re.compile(START + SEP + ADD + SEP + MULT)
REVERSED = re.compile(START + SEP + MULT + SEP + ADD)
# The arithmetic roles stay the same when the change is mentioned before the balance.
CHANGE_FIRST = re.compile(rf"take (?P<n>{NUMBER}) off (?:my |the )?(?:balance|score) of (?P<s>{NUMBER})"
                          rf"[.,;] (?:what do i get if i |then )multiply (?:the new (?:balance|score)|it) by (?P<m>{NUMBER})")
TAIL = re.compile(r"[.!?]\s*(?:what(?:'s| is) (?:my |the )?(?:final |new )?(?:total|answer|score|balance|count)|"
                  rf"how many(?: {UNIT})? is that|what do i get|where do i land)\??$")
QUESTIONS = {"start": "What number should I start with?", "add": "What's the exact amount to add?",
             "multiply": "What multiplier should I use?"}


def result(kind, reason, frame=None, question=None):
    return dict(kind=kind, reason=reason, frame=frame, question=question)


def normalize(text):
    text = text.lower().replace("’", "'").replace("−", "-")
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", " ", text)
    text = WORDS.sub(lambda m: str(NUMBERS[m[0]]), text)
    text = re.sub(r"\b(?:minus|negative) (?=\d)", "-", text)
    return " ".join(text.split())


def read_turn(text, answers=None):
    text = TAIL.sub("", text).strip(" .!?")
    text = re.sub(r"^(?:please |can you |could you )", "", text, count=1)
    if re.search(r"\b(?:which (?:comes|came) first|in what order|not sure (?:of |about )?the order)\b", text):
        return result("clarify", "missing-order", question="Which should come first, the change or the multiplication?")
    if REVERSED.fullmatch(text) or re.search(r"\b(?:divide|divided|dividing|split|square|cube)\b", text):
        return result("unsupported", "outside-add-then-multiply")
    reverse_mention = CHANGE_FIRST.fullmatch(text)
    if reverse_mention:
        text = (f"start with {reverse_mention['s']}, subtract {reverse_mention['n']}, "
                f"then multiply by {reverse_mention['m']}")
    match = DIALOGUE.fullmatch(text)
    if not match:
        if re.search(rf"\b(?:add|adding|printing|print|put in) {MISSING}\b", text):
            return result("clarify", "missing-add", question=QUESTIONS["add"])
        return result("unresolved", "wording-outside-grammar",
                      question="What starting number, change, and multiplier should I use, in that order?")
    fields = match.groupdict()
    if fields["start_unit"] and fields["add_unit"] and fields["start_unit"].rstrip("s") != fields["add_unit"].rstrip("s"):
        return result("unresolved", "units-differ", question="Which units should the calculation use?")
    subtract = fields["verb"] in {"subtract", "subtracting", "remove", "take away", "lose", "lost", "knocked"} or fields["direction"] == "down"
    changed = fields["add"] or fields["change"] or "0"
    factor = fields["multiply"] or ("2" if fields["factor"].startswith("doubl") else "3")
    raw = dict(start=fields["start"], add=changed, multiply=factor)
    for name, value in raw.items():
        if not re.fullmatch(NUMBER, value):
            if name == "add" and subtract:
                return result("clarify", "missing-subtraction", question="What amount should I subtract?")
            if answers and name in answers:
                raw[name] = answers[name]
            else:
                return result("clarify", "missing-" + name, question=QUESTIONS[name])
    frame = {k: int(v) for k, v in raw.items()}
    if subtract:
        frame["add"] = -frame["add"]
    if any(abs(v) > 1_000_000 for v in frame.values()):
        return result("unsupported", "operand-limit")
    return result("compute", "explicit-ordered-roles", frame=frame)


def inspect_messages(messages):
    if not isinstance(messages, list) or len(messages) not in {1, 3}:
        return result("unresolved", "unrecognized-conversation")
    roles = ["user"] if len(messages) == 1 else ["user", "assistant", "user"]
    if any(not isinstance(m, dict) or m.get("role") != role or
           not isinstance(m.get("content"), str) or len(m["content"]) > 500 for m, role in zip(messages, roles)):
        return result("unresolved", "unrecognized-conversation")
    text = normalize(messages[0]["content"])
    first = read_turn(text)
    if len(messages) == 1:
        return first
    # A follow-up can fill one known hole if the preceding question identifies it.
    answer = re.fullmatch(rf"({NUMBER})(?: this time| please)?[.!]?", normalize(messages[2]["content"]))
    slot = first["reason"].removeprefix("missing-")
    if first["kind"] == "clarify" and slot in QUESTIONS and answer:
        question = normalize(messages[1]["content"])
        prompts = {"add": r"what(?:'s| is) the exact amount to add\?|how (?:much|many) (?:should i|do i) add\?",
                   "multiply": r"what (?:multiplier|factor) should i use\?|what should i multiply (?:it|the total) by\?"}
        if re.fullmatch(prompts.get(slot, r"(?!)"), question):
            return read_turn(text, {slot: answer[1]})
    return result("unresolved", "unbound-follow-up", question="Could you restate the complete calculation?")
