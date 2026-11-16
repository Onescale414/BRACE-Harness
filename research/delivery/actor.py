"""Two English readers over the previous experiment's unchanged FIFO."""

import re


HTTP_RESOURCE = re.compile(r"(?<![\w/])GET[ \t]+/Harbor/ledger\b")
TEMPORAL = re.compile(r"\b(?:as soon as|whenever|when|once|until|unless|if|after)\b")
COMPLETE = re.compile(
    r"\b(?:answer(?:ed|ing)?|finish(?:ed|ing)?|complet(?:e|ed|ing|ion)|done|"
    r"result|response|reply|replied|reported|resolved|settled|delivered|provided)\b"
)
PERMISSION = re.compile(
    r"\b(?:i|we)\s+(?:ask|request|say|signal|tell|approve|confirm|decide|want|return|"
    r"bring|come|give)\b|\b(?:permission|approval|go.ahead|next (?:turn|message))\b"
)
OWN_ACTION = re.compile(
    r"\b(?:(?:i|we)(?:'ll|'m going to|'re going to|\s+(?:will|shall|can|might|may|am going to|are going to|"
    r"plan to|intend to))\s+(?:\w+\s+){0,2}(?:ask|request|check|handle|take|do|look|tell|let you know|"
    r"bring|raise|return|revisit|come|circle|follow|deal|test|read|verify|decide|give)|"
    r"let me (?:handle|check|ask|deal|do)|leave .+? to (?:me|us)|(?:my|our) (?:job|call))\b"
)
MENTION = re.compile(
    r"\b(?:just|only|merely) (?:an? (?:example|reference|note)|for (?:context|reference)|mentioned|mentioning|identif\w*)"
    r"|\b(?:for (?:reference|context)|as (?:background|context)|in my notes)\b"
)
CHOICE = re.compile(r"\b(?:undecided|undetermined|can't choose|cannot choose|haven't (?:chosen|decided)|not sure which)\b")
COMMAND = re.compile(r'\s+(?:(?:you (?:can|should|may|must)|please)\s+)?(?:give|tell|show|answer|report|send|check|fetch|revisit|return|resume|read|handle)\b')


def marked(text, previous):
    # Recognize the HTTP method and exact resource before lowercasing English verbs.
    return previous.mark_topics(HTTP_RESOURCE.sub('@m', text))


def result(events, ambiguous, previous):
    queue = [] if ambiguous else previous.fifo(events)
    return {'actions': [previous.TOPICS[topic] for topic in queue], 'clarify': ambiguous}


def schedule_resource(text, previous):
    return result(*previous.parse(marked(text, previous)), previous)


def is_completion(condition):
    if re.match(r'(?:if|unless)\b', condition) or PERMISSION.search(condition):
        return False
    return bool(COMPLETE.search(condition) or re.match(r'after (?:that|this|the first one)\b', condition))


def condition_in(clause):
    for match in TEMPORAL.finditer(clause):
        left = clause[:match.start()].strip()
        if clause[match.end():].startswith(' to '):
            continue
        # In an indirect question, 'if' introduces what BRACE should find out.
        if match.group() == 'if' and re.search(r'\b(?:see|check|tell me|know|determine|verify|confirm|find out)\s*$', left):
            continue
        return left, clause[match.start():]
    return clause, ''


def subjects(clause):
    return ' and '.join(dict.fromkeys(re.findall(r'@[dm]', clause))) or clause


def normalize(marked_text, previous):
    text = re.sub(r'\b(?:the|that|its) (?:setting|duration)\b', '@d', marked_text)
    text = re.sub(r'\b(?:the|that) (?:match|lookup)\b', '@m', text)
    text = re.sub(r"\b(?:i'd like|fill in|send|provide|supply|cover|move on to|go on to)\b", 'give', text)
    text = text.replace('?', ' __ask__.')
    text = re.sub(r'\b(after that|afterwards?|instead|actually|for now|then|first),', r'\1 ', text)
    text = re.sub(r'\b(?:as for|regarding|about)\s+([^,.;!?]+),\s*', r'\1 ', text)
    text = re.sub(r'\b(?:and then|then)\b', ',__then__ ', text)
    output = []
    preceding_gate = None
    for sentence in re.split(r'[.;!\n]+|\bbut\b', text):
        gate = None
        gate_topics = []
        parts = re.split(r',|\band\s+(?=(?:i|we|you|please|' + previous.VERB + r')\b)', sentence)
        for part in parts:
            part = re.sub(r'^and\s+', '', part.strip())
            if not part:
                continue
            if part.startswith('__then__ '):
                part = part[len('__then__ '):]
                if gate is None:
                    gate = preceding_gate
            main, condition = condition_in(part)
            if condition and not main:
                # A comma is optional in "once you're done give me ...".
                cue = PERMISSION.search(condition) or COMPLETE.search(condition) or re.match(r'after (?:that|this)\b', condition)
                command = COMMAND.search(condition, cue.end()) if cue else None
                if command:
                    main, condition = condition[command.start():].strip(), condition[:command.start()]
                gate = is_completion(condition)
                gate_topics = re.findall(r'@[dm]', condition)
                if not main:
                    continue
            elif condition:
                gate = is_completion(condition)

            if OWN_ACTION.search(main) or gate is False:
                target = subjects(main)
                if gate is False and '@' not in main and len(set(gate_topics)) == 1 and not re.search(r'\b(?:other|remaining)\b', main):
                    target = gate_topics[0]
                output.append('hold ' + target)
            elif CHOICE.search(main):
                output.append('either @d or @m')
            elif MENTION.search(main) and not re.match(r'(?:please |now )?(?:check|tell|show|give|answer|read)\b', main):
                pass
            else:
                # A correction with a single replacement topic withdraws the old one.
                topics = set(re.findall(r'@[dm]', main))
                if (len(topics) == 1 and not previous.has(previous.HOLD, main)
                        and re.search(r'\b(?:only|instead|make that|i meant)\b', main)
                        and not re.search(r'\b(?:first|before|second)\b', main)):
                    output.append('cancel ' + next(t for t in previous.TOPICS if t not in topics))
                if gate is True and not previous.has(previous.HOLD, main):
                    main = 'later ' + main
                output.append(main)
            preceding_gate = gate
            gate = None
            gate_topics = []
    return '. '.join(output)


def schedule(text, previous):
    return result(*previous.parse(normalize(marked(text, previous), previous)), previous)
