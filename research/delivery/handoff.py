"""A request-local delivery boundary for a two-topic connector experiment."""
from dataclasses import dataclass


TOPICS = ("delay_ms", "mixed_matches")


@dataclass(frozen=True, eq=False)
class Answer:
    question: str
    value: object
    checks: int
    granted: bool


class Inbox:
    def __init__(self):
        self.delivered = {}

    def deliver(self, answer):
        if answer not in self.delivered:
            self.delivered[answer] = object()
        return self.delivered[answer]

    def confirms(self, answer, receipt):
        return answer in self.delivered and self.delivered[answer] is receipt


class Handoff:
    """Run a checked task and release a held task on a matching delivery receipt."""
    def __init__(self, plan, inbox, check):
        first, held = plan["first"], plan["held"]
        if first is not None and first not in TOPICS:
            raise ValueError("Unknown first question")
        if held is not None and (first is None or held["action"] not in TOPICS
                or held["action"] == first or held["trigger"] not in ("first_delivered", "user_request")):
            raise ValueError("Invalid held task")
        self.first = first
        self.held = dict(held) if held else None
        self.check = check
        self.inbox = inbox
        self.prepared = None
        self.started = False
        self.acknowledged = False
 
    def begin(self):
        if not self.started:
            self.started = True
            if self.first is not None:
                self.prepared = self.check(self.first)
        return self.prepared

    def acknowledge(self, receipt):
        if self.acknowledged or self.prepared is None or not self.inbox.confirms(self.prepared, receipt):
            return None
        self.acknowledged = True
        if self.held and self.held["trigger"] == "first_delivered":
            return self.check(self.held["action"])
        return None


class Delivery(Handoff):
    """Bind the handoff to the existing one-observation connector session."""
    def __init__(self, plan, engine, case_id, receipt_reader, inbox, permit=True):
        super().__init__(plan, inbox, self._check)
        self.permit = permit
        self.questions = []
        self.observations = []

        def read(received_id, probe):
            if received_id != case_id or probe != "mixed_get" or self.observations:
                raise AssertionError("Unexpected connector read")
            value = receipt_reader(received_id, probe)
            self.observations.append({"probe": probe, "value": value, "beforeAnswer": len(self.inbox.delivered)})
            return value

        self.session = engine.Session(engine.load_adapter("connector").case(case_id), read)

    def _check(self, question):
        self.questions.append(question)
        decision = self.session.ask(question)
        waited = decision["status"] == "waiting"
        if waited:
            if question != "mixed_matches" or decision["probe"] != "mixed_get":
                raise AssertionError("Unexpected observation request")
            if not self.permit:
                self.session.deny(decision["ticket"])
                return None
            decision = self.session.grant(decision["ticket"])
        if decision["status"] != "answered" or decision["checksUsed"] != len(self.observations):
            raise RuntimeError("No checked answer")
        return Answer(question, decision["value"], decision["checksUsed"], waited)

