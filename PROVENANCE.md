# Sources and measurements

**Composition and accepted lessons.** Seven runtime modules were extracted
byte-for-byte from the qualified active learning reader: session, bounded solver,
arithmetic checker, snapshot archive, local store, contradiction detector and
independent contradiction checker. [Hashes](domains/composition/provenance.json)
pin those exact bytes; Git attributes preserve their line endings. The public CLI,
synthetic teaching demo and public-entry tests are new packaging. No private
lessons, user snapshots, model transcripts, paired launchers or migration tools
are included. Existing acceptance-origin compatibility code is retained unchanged;
it is not a public migration guarantee. [Scope and usage](domains/composition/README.md)

**Connector selection and preview.** Four runtime files were extracted byte-for-byte
from the qualified direct-selector candidate: selection, preview construction,
mapping audit and BRACE's bundled subset checker. Their hashes and those of the
18 synthetic fixtures are [recorded here](domains/connector/provenance.json).
They are project code covered by this repository's MIT license, not vendor code
from MockServer or WireMock. `.gitattributes` preserves their pinned bytes and
fixture bytes across checkout line-ending settings. The public CLI and portable tests are separately
exercised without private stores, local services or chat history. Source/target
handoff substitutions and whole-result corruption are explicit negative controls.
The private installation's lesson/reopen/rollback qualification is not presented
as validation of this public package. [Contract and usage](domains/connector/README.md)

**Arithmetic.** The harness, demo and tests come from BRACE’s two-step integer reference. Its affine coefficient and witness checks derive from the earlier `prepare.py` checker. [Checker](harness.py)

**Geometry.** The viewer contains one matched pair from a 12-cart synthetic study. Undoing the arm rotation in Chromium supplied the reference endpoints. The Python verifier independently reconstructs them from squared distances. [Verifier](preview/verify.py)

**Delivery.** The 36 authored requests use two synthetic connector mappings. Recorded WireMock responses supply the URL verdicts. The evidence includes the labels, observed decisions and source hashes for the three readers and the delivery guard. [Evidence](research/delivery/observations.json)

**Connector clarification.** Three synthetic replies share one stale jobs mapping and an observed decoder error from WireMock 3.13.2. The catalog groups come from 100 previously checked teaching mappings. The offline example executes the frozen reader, reconstructs each proposed patch and checks it against the original research receipts. The accompanying two-pair human wording trial is reported separately. [Evidence](research/connector-clarification/cases.json)

**Request scope.** The side-by-side comparison uses independently written synthetic replies and the same 100-route catalog. Each case includes its intended reading, each reader's decision, and a reference to each original check. Identical receipts are stored once. The replay checks both the selected action and the proposed connector mapping. [Comparison evidence](research/connector-clarification/comparison.json)

**Arithmetic handoff.** Two local Qwen 2.5 0.5B trials used invented conversations. The evidence contains the first 12 conversations, 16 independently authored fresh cases, three controls using supported wording, and four scope probes. It includes the intended interpretations, archived model proposals, prompts, model digest, and observed outcomes. The replay runs the public arithmetic checker again. [Handoff experiment and evidence](research/arithmetic-handoff/README.md)
