# Domain-specific bounded verification

BRACE's practical model is: define a domain contract, admit a bounded request,
produce a candidate, check it, and return either a checked result or an explicit
reason it could not be accepted. The host application owns the contract, budgets
and release path. A proposer is useful only when choosing a candidate is difficult;
direct construction is the baseline when the contract already determines it.

## What is available

| Surface | What a developer can run | What acceptance establishes |
| --- | --- | --- |
| [Integer harness](../README.md#run-the-harness) | Two ordered integer operations, optional proposer and receipts | The submitted operation/witness/result satisfies that supported instruction and chain contract. |
| [Connector domain](../domains/connector/README.md) | Direct selection, source/target-bound handoff and minimal repair preview | The chosen one of four supplied mappings meets the declared rule and its complete translation fits the fixed subset. |
| [Composition and lessons](../domains/composition/README.md) | Bounded plan repair, explicit acceptance, ordered lesson composition and persistent checked reuse | A plan matches four supplied examples; reopening rechecks saved evidence and reuse checks fresh examples. |
| [Geometry example](../preview/bracket.html) | Local viewer and independent coordinate reconstruction | The supplied measurements distinguish the listed geometric alternatives in that example. |
| [Domain-induction research](../research/domain-induction/README.md) | Replay finite-family learning, extra observations and exception repairs | Experimental performance under the documented hypothesis families and observation limits, including wrong predictions. |

The integer, connector and composition domains have different APIs. This repository does not
yet expose a universal domain plugin interface or automatically generate reliable
checkers from English. Research scripts are executable evidence, not a general
verification guarantee for their learned hypotheses.

## The developer's boundary

A new domain needs the following concrete decisions before it can release answers:

1. **What is the task?** Specify fields, units, types, supported semantics and the
   meaning of success. Resolve or refuse ambiguous intent before spending a check.
2. **What evidence is bound?** Capture the exact source state and expected target
   version. A hash binds bytes; it does not establish that a snapshot is current
   or that the supplied observation is true.
3. **What may change?** List permitted edits/actions and preserve everything else.
   Validate the whole result and intermediate transitions where relevant.
4. **What is the independent acceptance rule?** The checker must not trust the
   proposer's own assertion of success. A valid conversion can still be the wrong
   selected source; a correct final number can still use the wrong operation.
5. **What is the budget and failure outcome?** Count admissions, retries and external
   readings; include selection overhead. Distinguish checked absence, uncertainty,
   unsupported input, stale state and exhausted work. Withhold partial changes.
6. **What survives reuse?** Store accepted evidence only under an explicit policy.
   Recheck it under changed contracts or new requests. Give code rollback and data
   rollback their own verified paths.

Keep the smallest useful implementation. The connector example uses a linear scan
and a separate pairwise check rather than a model for four explicit options. Both
share trusted parsing and contract components, so independent checking here means
separate acceptance logic, not independent implementations of every dependency.

## How to evaluate another domain

Freeze representative valid, invalid, stale and ambiguous cases before comparing
methods. Include at least one case where a superficially correct answer violates
the actual task. Start with an ordinary deterministic baseline, keep the same check
allowance, and count the proposer's additional work. Preserve failed trials.

Test the public entry from a clean checkout with no chat history or local services.
Verify exact no-op preservation, complete refusal, handoff bindings, reopening and
rollback as applicable. Record what was checked and what remains assumed. A finite
test set supports that test result; it does not prove behavior outside its scope.

For a learned domain, agreeing with the observations is weaker than knowing the
true rule. If remaining evidence-consistent rules disagree about the requested
answer, return it conditionally, request an allowed distinguishing observation,
or withhold. Even unanimous candidates can be wrong when the true rule is missing;
the research examples retain such counterexamples.

## Current direction

The immediate public goal is useful, inspectable domain verifiers with reproducible
failure cases. Candidate extensions such as richer connector policies, learned
selection or a common multi-domain interface need their own contracts and tests.
There is no demonstrated need to make the four-option connector selector depend
on an LLM. Geometry and learned-domain research remain available as evidence for
future designs, with their measured limits intact.

Bounded program composition and explicitly accepted, independently rechecked
lessons now have a separate public session entry and disposable teaching example.
They do not add persistence or learned selection to the connector command. No
private lesson store is included. Further domains still need explicit contracts,
independent checks and examples that expose their failure boundaries.
