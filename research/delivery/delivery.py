"""Read two-topic English requests into a first answer and an event-bound follow-up."""

import re


def matches(pattern, text):
    return re.search(pattern, text) is not None


TOPIC = re.compile(r"@[dm]")
COMMAND = (r"(?:give|tell|show|send|report|answer|provide|supply|return|revisit|resume|"
           r"check|find|fetch|get|look|read|pick|take|do|handle|cover|move|go|proceed|"
           r"continue|follow|determine|verify|confirm|start|begin|finish|include|add)")
REFERENCE = (r"\b(?:it|that|this|one|other|remaining|second|first|former|latter|both|"
             r"follow.up|quoted question|next (?:item|question|task))\b")
TIME = re.compile(r"\b(?:as soon as|the (?:moment|minute|instant)|when(?:ever)?|once|"
                  r"(?:right |immediately )?after|until|unless|only if|if|upon|"
                  r"on (?:receipt|delivery)|with (?=(?:that|this|the first)\b))\b")
USER_TRIGGER = (r"\b(?:i|we)(?:'ve| have| will|'ll)?\s+(?:(?:explicitly|separately|again|later)\s+)*"
                r"(?:ask|request|say|tell|signal|confirm|approve|authorize|decide|choose|prompt|"
                r"respond|reply|come back|circle back|come to you|return|raise|bring|want|"
                r"give (?:you|the|a|my)|get back|follow up|chime in|green.light|send)\b|"
                r"\b(?:my|our|another|a new|a separate|a further) (?:explicit |separate |next |further |"
                r"fresh )*(?:instruction|request|message|prompt|confirmation|approval|permission|signal|"
                r"go.ahead|green light|say.so|cue|word|follow.up)\b|"
                r"\b(?:from (?:me|us)|ask again|asked again|you(?:'re| are) asked|"
                r"next (?:meeting|turn|conversation))\b")
DELIVERY = (r"\b(?:answer(?:ed|ing|s)?|repl(?:y|ied)|respond(?:ed)?|response|result|verdict|"
            r"deliver\w*|recei(?:ve\w*|pt)|finish\w*|complet\w*|done|settled|resolved|reported|"
            r"sent|send|give|given|giving|told|tell|show\w*|post\w*|publish\w*|print\w*|"
            r"share\w*|suppl\w*|provid\w*|communicat\w*|return\w*|land\w*|out|in hand)\b"
            r"|\b(?:after|once) (?:that|this|the first one)\b|\b(?:have|has|got) (?:that|it|@[dm])")
USER_OWNS = (r"\b(?:i|we)(?:'ll|'m|'re| am| are| will| shall| can| might| may| plan to| intend to)"
             r"(?:\s+(?:going to|personally|myself|ourselves|also|just|then|take care of))*\s+"
             r"(?:check|test|handle|take|do|look|find|verify|read|deal|figure|research|run|"
             r"investigate|answer|cover|fetch|get|own|determine|pull|work|tackle|inspect)\b|"
             r"\b(?:my|our) (?:job|task|responsibility|part|call|turn)\b|\b(?:for me to|for us to) "
             r"(?:check|do|handle|take|look|answer|verify)|\b(?:mine|ours) to\b|"
             r"\b(?:is|stays|remains|will be) (?:mine|ours|with me|on me)\b|"
             r"\b(?:leave|hand|assign)\b.*?\bto (?:me|us)\b|\b(?:let me|let us) " + COMMAND)
OTHER_OWNS = (r"\b(?!(?:i|we|you|that|it|this|then|which|what|what's|there|"
              r"answer|verdict|number|result|figure)\b)(?<!@)[a-z][\w'-]*\s+"
              r"(?:will|'ll|is going to|has agreed to|is responsible for)\s+(?:also |then )*"
              + COMMAND + r"\b|\b(?:leave|assigned|belongs|handed)\b.{0,45}\bto "
              r"(?:my (?:colleague|teammate)|the (?:operator|reviewer|team)|"
              r"(?!you\b|me\b|us\b|do\b|check\b)[a-z]+)\b")
UNCERTAIN = (r"\b(?:unclear|ambiguous|undecided|unspecified|unresolved|unknown|"
             r"haven't (?:decided|chosen|said|specified)|not sure|can't (?:tell|choose|decide)|"
             r"cannot (?:tell|choose|decide)|don't know (?:whether|which|who|when)|"
             r"maybe|perhaps|when appropriate|if appropriate|if necessary|if needed|"
             r"whichever|(?:someone|somebody|one of us) (?:will|should|can)|"
             r"(?:mine|me|my [\w-]+|yours|you) or (?:mine|me|yours|you)|"
             r"(?:who|whose) (?:will|should|takes|turn)|can't see which)\b")
BACKGROUND = (r"\b(?:for (?:context|reference|illustration)|as (?:background|an example)|"
              r"(?:just|only|merely) (?:background|context|a label|the label|an example|an illustration|a note)|"
              r"(?:merely|only|just) (?:a )?(?:mention|reference)|"
              r"(?:my|the) (?:notes?|example|manual|sample|template) (?:says?|reads?|asks?|mentions?)|"
              r"(?:printed|written|listed) (?:on|in)|while discussing)\b")
DISCARD = (r"\b(?:cancel|drop|forget|skip|ignore|scratch|discard|omit|neither|never mind|"
           r"no need|no longer|do not|don't|leave .*? alone|stop (?:after|there)|"
           r"not (?:the |@)|without (?:checking|answering)|no (?:second|follow.up))\b")
FUTURE = (r"\b(?:later|another (?:day|time)|a separate (?:request|turn|question)|next time|"
          r"not (?:now|yet|today)|for (?:later|now|another day)|for (?:monday|tuesday|wednesday|"
          r"thursday|friday|saturday|sunday)|leave .*? for|keep .*? for (?:a |the )?follow.up)\b")
ASK = (r"\b" + COMMAND + r"\b|\b(?:would like|i'd like|i want|i need|i do want|"
       r"your (?:job|task|turn)|for you to|up to you to|does|how (?:long|many|much)|what|"
       r"which|whether|verdict please|yes or no|__question__)\b")
ORDER_LATE = (r"\b(?:then|next|second|follow.up|afterwards?|after that|after this|"
              r"another (?:task|question)|come back|circle back|go back|pick .*?back up)\b")
ORDER_FIRST = (r"\b(?:first|start(?:ing)? (?:by|with)|to start|begin (?:by|with)|"
               r"right now|for now|ahead of)\b")
UNRESOLVED_SELECTION = (r"\b(?:one (?:marked|highlighted|circled|[a-z]+ handed over)|"
                        r"(?:starred|missing|outstanding|highlighted) (?:one|item|question|answer)|"
                        r"(?:don't know|can't see|haven't (?:said|told you)) (?:who|which)|"
                        r"(?:exactly|just) one (?:of|answer)|which one is still)\b")
DISMISS_ALL = (r"\b(?:close this out|both (?:are|were) (?:filled in|answered)|"
               r"take (?:those|both|them) off|(?:no need|don't need) (?:to take )?either|"
               r"(?:skip|ignore|cancel|drop) (?:them )?both|we're all set)\b")


def prepare(text, baseline, actor):
    # The earlier reader protects the complete case-sensitive HTTP literal before
    # the FIFO's language vocabulary can interpret its method as an imperative.
    text = actor.marked(text, baseline).replace("‘", "'")
    text = re.sub(r"\b(?:the|that|its) (?:setting|duration|wait figure|wait number|wait|number|figure)\b", "@d", text)
    text = re.sub(r"\b(?:the|that|a|its) (?:match (?:result|verdict|answer|status)|match|"
                  r"route verdict|lookup verdict|verdict)\b", "@m", text)
    text = re.sub(r"\b(?:without waiting for|(?:do not|don't|no need to) wait for) "
                  r"(?:me to (?:ask|confirm)(?: again)?|(?:my|another|a second) "
                  r"(?:request|prompt|confirmation|message|go.ahead))\b", " automatically ", text)
    # Punctuation inside a sample question belongs to the sample.
    text = re.sub(r'["“]([^"”\n]*)["”]', lambda m: m.group(1).replace("?", " __quoted_question__. "), text)
    text = text.replace("?", " __question__.")
    text = re.sub(r"\b(as for|regarding|about) ([^,.;!]+),\s*", r"\2 ", text)
    text = re.sub(r"\b(first|then|next|second|later|for now|afterwards?|"
                  r"actually|instead|to start),", r"\1 ", text)
    text = re.sub(r"\b((?:right )?after (?:that|this)(?: answer)?) (?:comes|follows)\b",
                  r"\1, next comes", text)
    return text


def units(text):
    """Keep a leading conditional with its imperative; split independent instructions."""
    for sentence in re.split(r"[.;!\n]+", text):
        fragments = re.split(r"\bbut\b|\bwhile (?=(?:you |i |we |please |" + COMMAND + r"\b))|"
                             r"\band (?=(?:(?:then |please )?" + COMMAND + r"\b|"
                             r"i(?:'ll| will)|we(?:'ll| will)|(?:that|this) (?:task|lookup) is for))|"
                             r"(?<!\w)(?=then\s+(?:please\s+)?" + COMMAND + r"\b)", sentence)
        for fragment in fragments:
            part = fragment.strip(" ,")
            if part:
                yield part


def topics(clause):
    return list(dict.fromkeys(TOPIC.findall(clause)))


def resolve(clause, history, order):
    explicit = topics(clause)
    if explicit:
        return explicit
    if matches(r"\b(?:both|everything|neither|either result)\b", clause):
        return ["@d", "@m"]
    if history and matches(r"\b(?:other|remaining)\b", clause):
        return ["@m" if history[-1] == "@d" else "@d"]
    if order and matches(r"\b(?:first|second) (?:part|item)\b|\b(?:answer|do|drop|scratch) the (?:first|second)\b", clause):
        return [order[0] if "first" in clause else order[-1]]
    if history and (matches(REFERENCE, clause) or matches(r"\b(?:go on|go.ahead|carry on)\b", clause)):
        return [history[-1]]
    return []


def condition_parts(clause):
    for match in TIME.finditer(clause):
        main = clause[:match.start()].strip(" ,")
        if match.group() == "if" and matches(r"\b(?:check|see|tell me|confirm|know|"
                                             r"verify|determine|establish|find out)\s*$", main):
            continue
        if clause[match.end():].startswith(" to "):
            continue
        condition = clause[match.start():]
        if main:
            return main, condition
        if "," in condition:
            cond, main = condition.split(",", 1)
            return main.strip(), cond
        # Without a comma, the first imperative after the subordinate verb
        # begins the main clause. Pronouns and infinitives belong to the gate.
        for verb in re.finditer(r"\b(?:please )?" + COMMAND + r"\b", condition, flags=re.I):
            prefix = condition[:verb.start()].rstrip()
            if not matches(r"\b(?:you|i|we|they|to|and|you've|i've|you'll|can|will)\s*$", prefix):
                if matches(DELIVERY, prefix) or matches(USER_TRIGGER, prefix):
                    return condition[verb.start():], prefix
        return "", condition
    return clause, ""


def trigger(condition):
    if matches(USER_TRIGGER, condition):
        return "user_request"
    if matches(DELIVERY, condition) or topics(condition) and matches(r"\bafter\b", condition):
        return "first_delivered"
    return "unclear"


def plan(text, baseline, actor):
    events, history, order = [], [], []
    unclear = set()
    unresolved = False
    waiting_gate = None
    previous_gate = None
    for clause in units(prepare(text, baseline, actor)):
        if matches(DISMISS_ALL, clause):
            events.extend(("drop", item) for item in baseline.TOPICS)
            unresolved = False
            unclear.clear()
            continue
        main, condition = condition_parts(clause)
        gate = trigger(condition) if condition else waiting_gate
        waiting_gate = None
        if not main:
            waiting_gate = gate
            continue
        if main.startswith("before ") and "," in main:
            preamble, command = main.split(",", 1)
            if matches(r"\b(?:we get into|we discuss|getting into)\b", preamble):
                main = command.strip()
        main_topics = resolve(main, history, order)
        condition_topics = topics(condition)
        if not main_topics and condition_topics and matches(REFERENCE, main):
            main_topics = condition_topics
        if not main_topics and matches(r"\b(?:i'll|i will|my next|wait for my)\b", main) and history:
            main_topics = [history[-1]]

        # A prerequisite can name the first answer as part of the very same
        # sentence. A person merely mentioning that topic grants no operation.
        if gate == "first_delivered" and main_topics and not matches(USER_TRIGGER, condition):
            for item in condition_topics:
                if item not in main_topics:
                    events.append(("add", item))
                    if item not in order:
                        order.append(item)
        if matches(UNRESOLVED_SELECTION, main) and len(topics(main)) != 1:
            unclear.update(baseline.TOPICS)
            unresolved = True
            continue
        if not main_topics:
            if matches(UNCERTAIN, main) or matches(r"\b(?:which one|either|one marked|highlighted)\b", main):
                unresolved = True
            continue
        for item in main_topics:
            if item not in order:
                order.append(item)
        history.extend(main_topics)
        background = matches(BACKGROUND, main) or "__quoted_question__" in main and "notes" in main
        if background and not matches(r"^(?:please |now )?" + COMMAND + r"\b", main):
            continue
        if matches(UNCERTAIN, main) or matches(UNCERTAIN, condition):
            unclear.update(main_topics)
            continue
        if matches(USER_OWNS, main) or matches(OTHER_OWNS, main):
            op = "drop"
        elif gate == "user_request" or matches(USER_TRIGGER, main):
            op = "hold"
        elif len(main_topics) > 1 and matches(r"\b(?:or|either)\b", main):
            unclear.update(main_topics)
            continue
        elif matches(DISCARD, main):
            op = "hold" if matches(r"\b(?:yet|until|unless|for now)\b", clause) else "drop"
        elif gate == "unclear":
            unclear.update(main_topics)
            continue
        elif gate == "first_delivered":
            op = "later"
        elif baseline.has(baseline.HOLD, main) or matches(FUTURE, main) and not matches(ASK, main):
            op = "hold"
        elif matches(ORDER_LATE, main) and (matches(ASK, main) or len(main_topics) == 1):
            op = "hold" if previous_gate == "user_request" and main.startswith("then") else "later"
        elif matches(ORDER_FIRST, main) and len(main_topics) == 1:
            op = "first"
        elif matches(ASK, main) or re.fullmatch(r"(?:@[dm]| and | please| now| the |\s)+", main):
            op = "add"
        else:
            continue
        if len(main_topics) == 2 and matches(r"\bbefore\b", main) and main.startswith("before"):
            main_topics.reverse()
        for item in main_topics:
            unclear.discard(item)
            events.append((op, item))
        previous_gate = gate

    queue = baseline.fifo(events + [("drop", item) for item in sorted(unclear)])
    last_ops = {item: op for op, item in events}
    first = queue[0] if queue else None
    held = None
    if len(queue) > 1:
        held = {"action": baseline.TOPICS[queue[1]], "trigger": "first_delivered"}
    elif first:
        other = next(item for item in baseline.TOPICS if item != first)
        if last_ops.get(other) == "hold" and other not in unclear:
            held = {"action": baseline.TOPICS[other], "trigger": "user_request"}
    clarify = bool(unclear or unresolved or not events)
    return {"first": baseline.TOPICS.get(first), "held": held, "clarify": clarify}
