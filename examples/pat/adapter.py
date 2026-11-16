"""Use a lesson recalled by PAT to propose one affine operation to BRACE."""
from hashlib import sha256
import json
from string import ascii_lowercase

from amem import EpisodeHooks, Memory, NumpyEmbeddingIndex
from mirror import BigramSpace

from harness import Candidate, Reply, encoded


class PATProposer:
    def __init__(self, lessons):
        self.memory = Memory(seed=7, path=None, autosave=False)
        self.hooks = EpisodeHooks(self.memory)
        self.space = BigramSpace(ascii_lowercase)
        self.proposals = {}
        for word, operation in lessons:
            if operation not in ("add", "multiply"):
                raise ValueError(f"Unknown operation: {operation}")
            self.hooks.write_episode(self.space.vec(word), payload_meta={"word": word, "operation": operation})

    def recall(self, cue, exclude=None):
        vector = self.space.vec(cue)
        library = self.memory.library
        if exclude is None:
            recovered = self.hooks.recall_context(vector)
        else:
            # Filter a temporary index. The original episodes stay available for future requests.
            eligible = NumpyEmbeddingIndex()
            for mid in library.mids():
                lesson = library.get(mid).meta
                if lesson["operation"] != exclude:
                    eligible.add(mid, lesson["embedding"])
            if not len(eligible):
                return None
            mid, _ = eligible.nearest(vector)
            recovered = self.memory.recall(mid=mid)
        return library.get(recovered.identity).meta

    def propose(self, ticket, view, *, exclude=None):
        # BRACE has already parsed the request. Read the verb from the active clause.
        first, second = view.snapshot.source.decode().split(".", 1)[1].split(",", 1)
        cue = (first.split()[0] if view.step == 0 else second.split()[1]).lower()
        lesson = self.recall(cue, exclude)
        if lesson is None:
            return Reply(ticket.ticket_id, ())
        operation = lesson["operation"]
        operand = (view.snapshot.add, view.snapshot.multiply)[view.step]
        a, b = (1, operand) if operation == "add" else (operand, 0)
        payload = {
            "id": f"pat-{view.step}", "run": ticket.run, "snapshot": ticket.snapshot,
            "step": view.step, "parent": view.parent, "a": a, "b": b,
            "witness": [a * x + b for x in range(-2, 3)], "result": a * view.before + b,
        }
        return self._reply(ticket, payload, (lesson["word"], operation, operand))

    def with_result(self, ticket, view, previous, result):
        """Reissue this step's draft with a revised claim and current run bindings."""
        payload = json.loads(previous)
        if (payload["snapshot"], payload["step"]) != (ticket.snapshot, view.step):
            raise ValueError("The previous draft belongs to another request or step")
        description = self.proposals[sha256(previous).hexdigest()][:3]
        payload.update(run=ticket.run, parent=view.parent, result=result)
        return self._reply(ticket, payload, description)

    def _reply(self, ticket, payload, description):
        raw = encoded(payload)
        self.proposals[sha256(raw).hexdigest()] = (*description, payload["result"])
        return Reply(ticket.ticket_id, (Candidate(raw),))
