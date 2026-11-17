"""Research learner for named transitions x -> a*x + b on integer scalars."""


def _simplicity(rule):
    a, b = rule
    return (abs(a - 1) + abs(b), abs(b), abs(a), a, b)


CANDIDATES = tuple(sorted(
    ((a, b) for a in range(-3, 4) for b in range(-5, 6)), key=_simplicity
))


def _name(value):
    return type(value) is str and bool(value.strip())


def _reading(verb, before, after):
    if not _name(verb) or type(before) is not int or type(after) is not int:
        raise ValueError("a reading needs a verb name and two integer scalar states")


def _request(start, moves):
    return (type(start) is int and type(moves) in (list, tuple)
            and 1 <= len(moves) <= 3 and all(_name(move) for move in moves))


class _Concept:
    def __init__(self):
        self.evidence = []
        self.validation = []
        self.candidates = CANDIDATES

    def fit(self, before, after):
        if self.validation:
            raise ValueError("fitting evidence is sealed after validation begins")
        self.evidence.append((before, after))
        self.candidates = tuple((a, b) for a, b in self.candidates
                                if a * before + b == after)

    def status(self):
        if not self.candidates:
            return "quarantined"
        if len(self.candidates) != 1:
            # A holdout may refute every rule. It cannot decide between rules.
            if self.validation and not any(
                all(a * x + b == y for x, y in self.validation)
                for a, b in self.candidates
            ):
                return "quarantined"
            return "ambiguous"
        a, b = self.candidates[0]
        if any(a * x + b != y for x, y in self.validation):
            return "quarantined"
        training_inputs = {x for x, _ in self.evidence}
        fresh_confirmation = any(x not in training_inputs for x, _ in self.validation)
        if len(training_inputs) >= 2 and fresh_confirmation:
            return "validated"
        return "unvalidated"


class Domain:
    """Own the fitting and confirmation readings for one private vocabulary."""

    def __init__(self, name):
        if not _name(name):
            raise ValueError("a domain needs a name")
        self.name = name
        self._verbs = {}

    def teach(self, verb, before, after):
        """Introduce a verb or add fitting evidence before its validation phase."""
        _reading(verb, before, after)
        if verb not in self._verbs:
            self._verbs[verb] = _Concept()
        self._verbs[verb].fit(before, after)

    def observe(self, verb, before, after):
        """Apply feedback to an existing verb, retaining all consistent rules."""
        _reading(verb, before, after)
        if verb not in self._verbs:
            raise ValueError("feedback needs a previously taught verb")
        self._verbs[verb].fit(before, after)

    def validate(self, verb, before, after):
        """Seal fitting and check a held-out reading. A failed rule stays withheld."""
        _reading(verb, before, after)
        concept = self._verbs.get(verb)
        if concept is None:
            return False
        concept.validation.append((before, after))
        return concept.status() == "validated"

    def diagnose(self, verb):
        """Return a detached record. The simplest fitting rule is diagnostic only."""
        concept = self._verbs.get(verb) if _name(verb) else None
        if concept is None:
            return dict(status="unknown", provisional=None, candidates=(),
                        evidence=(), validation=())
        rules = concept.candidates
        return dict(status=concept.status(), provisional=rules[0] if rules else None,
                    candidates=rules, evidence=tuple(concept.evidence),
                    validation=tuple(concept.validation))

    def snapshot(self):
        """Return a JSON-serializable receipt containing only source readings."""
        return {"name": self.name, "verbs": {
            verb: {"evidence": list(concept.evidence), "validation": list(concept.validation)}
            for verb, concept in self._verbs.items()
        }}

    @classmethod
    def from_snapshot(cls, receipt):
        """Replay source readings to rederive the candidates and release decisions."""
        domain = cls(receipt["name"])
        for verb, readings in receipt["verbs"].items():
            for before, after in readings["evidence"]:
                domain.teach(verb, before, after)
            for before, after in readings["validation"]:
                domain.validate(verb, before, after)
        return domain

    def execute(self, start, moves):
        """Release a checked trace for one to three moves, or return None."""
        if not _request(start, moves):
            return None
        state = start
        trace = []
        for verb in moves:
            concept = self._verbs.get(verb)
            if concept is None or concept.status() != "validated":
                return None
            a, b = concept.candidates[0]
            after = a * state + b
            trace.append({"verb": verb, "before": state, "after": after})
            state = after
        return trace if check_trace(self, start, moves, trace) else None


def _verified_rule(concept):
    """Derive an integer line from two fitting inputs and check every receipt."""
    x0, y0 = concept.evidence[0]
    second = next(((x, y) for x, y in concept.evidence if x != x0), None)
    if second is None:
        return None
    x1, y1 = second
    a, remainder = divmod(y1 - y0, x1 - x0)
    b = y0 - a * x0
    if remainder or not (-3 <= a <= 3 and -5 <= b <= 5):
        return None
    fitting_inputs = {x for x, _ in concept.evidence}
    if not any(x not in fitting_inputs for x, _ in concept.validation):
        return None
    for x, y in (*concept.evidence, *concept.validation):
        if a * x + b != y:
            return None
    return a, b


def check_trace(domain, start, moves, trace):
    """Pure research checker. Reconstruct each step directly from raw readings."""
    if not isinstance(domain, Domain) or not _request(start, moves):
        return False
    if type(trace) not in (list, tuple) or len(trace) != len(moves):
        return False
    state = start
    for verb, step in zip(moves, trace):
        concept = domain._verbs.get(verb)
        if concept is None or type(step) is not dict:
            return False
        if set(step) != {"verb", "before", "after"} or step["verb"] != verb:
            return False
        if type(step["before"]) is not int or type(step["after"]) is not int:
            return False
        rule = _verified_rule(concept)
        if rule is None:
            return False
        a, b = rule
        next_state = a * state + b
        if step["before"] != state or step["after"] != next_state:
            return False
        state = next_state
    return True
