"""Frozen English scheduling candidates for two read-only actions. No external calls."""

import re


TOPICS = {"@d": "delay_ms", "@m": "mixed_matches"}
DELAY = (r"\b(?:delay[_ -]?ms|delay|latency setting|timer|milliseconds?|millisecond setting|"
         r"(?:programmed|configured|server|intentional|artificial|the) wait|wait (?:time|setting)|"
         r"sleep (?:duration|setting)|time(?:out|r) setting)\b")
MIXED = (r"(?:/harbor/ledger\b|\bmixed[_ -]?(?:matches|case|match)|"
         r"\b(?:capitali[sz]ation|capital h|uppercase|case.sensitiv\w*|route|routing|"
         r"path|endpoint|url|address|http status|status code|mapping)\b)")
HOLD = (r"\b(?:park|shelve|table|defer|postpone|hold|pause|suspend|sideline|set aside|"
        r"wait on|wait with|hold off|put off|can wait|can keep|on hold|on ice|"
        r"back burner|in reserve|pending|next time|not yet|leave .*?(?:alone|aside|later|for now)|"
        r"(?:put|set) .*?(?:aside|on hold|off)|save .*?for later)\b")
DROP = (r"\b(?:cancel|drop|forget|skip|ignore|scratch|discard|omit|neither|never mind|"
        r"don't|do not|no need|no longer|no (?:checks|reads|action)|without|not (?:the |@)|stop)\b|^not\s")
RETURN = r"\b(?:come back|go back|circle back|back to|return|revisit|resume|unpark|pick .*?back up)\b"
DO = (r"\b(?:show|tell|give|check|read|look|see|do|find|fetch|get|want|need|report|"
      r"verify|confirm|answer|handle|start|begin|tackle|run|take|inspect|test|"
      r"determine|resolve|pull|use|what|which|whether|does|how|__ask__)\b")
FIRST = r"\b(?:first|right now|start with|begin with|ahead of|priority|instead)\b"
LATE = r"\b(?:later|second|last|afterwards?|after that|once .*?(?:done|finished)|next time)\b"
CONTINGENT = r"\b(?:if|unless|until|when)\s+(?:i|we|you)\s+(?:ask|say|request|authorize|approve|tell|want|confirm|decide)\b"
VERB = (r"(?:park|shelve|defer|leave|hold|save|show|tell|give|check|read|look|see|do|"
        r"find|fetch|get|report|verify|confirm|handle|start|run|cancel|skip|drop|"
        r"come|go|circle|return|revisit|resume|pick|only|don't|ignore|put|set)")


def has(pattern, text):
    return re.search(pattern, text) is not None


def mark_topics(text):
    text = text.lower().replace("’", "'").replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\bdelay (?=(?:the |that )?(?:route|path|mixed|endpoint|url))", "postpone ", text)
    return re.sub(DELAY, "@d", re.sub(MIXED, "@m", text))


def clauses(text):
    text = text.replace("?", " __ask__.")
    text = re.sub(r"(^|[;,.!]\s*)(actually|instead|first|then|later|for now|after that|afterwards?|second|next),", r"\1\2 ", text)
    text = re.sub(r"(" + CONTINGENT + r"[^.;!?]*?),\s*([^.;!?]+)", r"\1 \2", text)
    for part in re.split(r"[;,.!?\n]+|\b(?:but|and then|then)\b|\band\s+(?=" + VERB + r"\b)", text):
        if part.strip():
            yield part.strip()


def parse(text):
    """Resolve topic aliases, local speech acts, order cues and two-topic references once."""
    events, history, parked = [], [], []
    ambiguous = False
    for clause in clauses(text):
        targets = list(dict.fromkeys(re.findall(r"@[dm]", clause)))
        explicit = bool(targets)
        other = has(r"\b(?:other|remaining)\b", clause)
        back = has(RETURN, clause)
        hold = has(HOLD, clause) or has(CONTINGENT, clause)
        drop = has(DROP, clause)
        if drop and has(r"\b(?:yet|for now|until)\b", clause):
            hold, drop = True, False
        if not targets:
            if has(r"\b(?:both|everything|all of (?:it|them)|either one|nothing|neither)\b", clause):
                targets = list(TOPICS)
            elif other and history:
                targets = [next(topic for topic in TOPICS if topic != history[-1])]
            elif len(parked) == 1 and (back or has(r"\b(?:parked|deferred|held)\b", clause)):
                targets = parked.copy()
            elif history and has(r"\b(?:it|that|this|former|latter|one)\b", clause):
                targets = [history[0] if "former" in clause else history[-1]]
            elif drop:
                targets = list(TOPICS)
        if not drop and not hold and len(targets) != 1 and has(r"\b(?:or|either|whichever)\b", clause):
            ambiguous = True
            continue
        if not targets:
            if back or other:
                ambiguous = True
            continue
        bare = re.fullmatch(r"(?:@[dm]|\s|the\b|and\b|please\b|actually\b|just\b|only\b|both\b|now\b|first\b|second\b|next\b|later\b|instead\b)+", clause)
        requested = back or bare or has(DO, clause) or has(FIRST, clause)
        if not (requested or hold or drop):
            continue
        if (explicit and len(targets) == 1 and re.search(r"\b(?:actually|instead|make that)\b.*\b(?:only|just)\b", clause)
                and not (hold or drop or back)):
            events.append(("drop", next(topic for topic in TOPICS if topic != targets[0])))
        if drop:
            op = "drop"
        elif hold:
            op = "hold"
        elif has(FIRST, clause) or has(r"\bnow\b", clause):
            op = "first"
        elif back or has(LATE, clause) or clause.startswith("before "):
            op = "later"
        else:
            op = "add"
        if len(targets) == 2 and not (hold or drop):
            between = clause.partition(targets[0])[2].partition(targets[1])[0]
            if has(r"\b(?:after|later|second|last)\b", between) or clause.startswith("before "):
                targets.reverse()
            op = "add"
        for topic in targets:
            events.append((op, topic))
            if topic in parked:
                parked.remove(topic)
            if op == "hold":
                parked.append(topic)
            if explicit:
                history.append(topic)
        if explicit:
            ambiguous = False
    return events, ambiguous or not events


def fifo(events):
    """Two FIFO service bands. Explicit 'first' can move a ready item to the front."""
    ready, later = [], []
    for op, topic in events:
        if op == "add" and topic in ready + later:
            continue
        for queue in (ready, later):
            if topic in queue:
                queue.remove(topic)
        if op == "first":
            ready.insert(0, topic)
        elif op == "add":
            ready.append(topic)
        elif op == "later":
            later.append(topic)
    return ready + later


def pendulum(events):
    """One focus, one possible return. A slot carries its explicit later status."""
    focus, reserve = None, None
    for op, topic in events:
        if op == "add" and any(slot and slot[0] == topic for slot in (focus, reserve)):
            continue
        if focus and focus[0] == topic:
            focus, reserve = reserve, None
        elif reserve and reserve[0] == topic:
            reserve = None
        if op in ("hold", "drop"):
            continue
        slot = (topic, op == "later")
        if focus is None or op == "first" or (op == "add" and focus[1]):
            focus, reserve = slot, focus
        else:
            reserve = slot
    return [slot[0] for slot in (focus, reserve) if slot]


def schedule(text, method):
    marked = mark_topics(text)
    if method == "mention":
        topics = list(dict.fromkeys(re.findall(r"@[dm]", marked)))
        clarify = not topics
    else:
        events, clarify = parse(marked)
        schedulers = {"fifo": fifo, "pendulum": pendulum}
        topics = [] if clarify else schedulers[method](events)
    return {"actions": [TOPICS[topic] for topic in topics], "clarify": clarify}
