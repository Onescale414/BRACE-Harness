# A missing order in a two-operation score

Freeze the candidate reader, scoring code and independently worded case bank before running the comparison. The seven-point counter with a three-point bonus and a doubling card is a development example. Exclude it from fresh-case totals.

Run the published wording gate and the candidate on the same messages. The candidate can intercept a request to ask which of two operations goes first. Otherwise the published gate handles it. Both use the existing add-then-multiply checker and its two-check ceiling. Clarification consumes zero arithmetic checks. A reply selecting multiplication first is outside this checker's grammar.

The 32 new conversations cover eight order gaps with different endpoints, eight explicit addition-first requests, six explicit multiplication-first requests, four unspecified orders with equal endpoints, three missing operands and three other requests. Every order gap has two independently worded alternative replies. Count a grounded question only when the three operand roles match the case key. Score both replies from the same pending state and include missed interceptions in the denominator. Also try an undecided reply. Evaluate unnecessary order questions and changes to the existing handling of all 24 controls.

Look for more correctly grounded order questions, no added inappropriate questions on controls, and at least one fresh case that both releases the checked addition-first answer and withholds the unsupported reverse. Report wrong releases, coverage and missed cases even if these conditions fail. The saved Qwen conversations can be replayed separately to see whether the question would have intercepted a previously released answer. They are regression evidence, outside the fresh-case score.

As a diagnostic, supply the correct pending quantities for each of the eight order gaps and try its original replies. This isolates reading the caller's choice from recognizing the initial question. These supplied quantities never enter the primary comparison.

The original case bank SHA-256 is `8b19b52a2bce6814ee83263804de08310b7c6acb4a669a66e7adf392008e7beb`. The frozen reader and scorer hashes are `9432cb217cbd935c2b0de977facc3541f219443f2b7ffce2a483f97d6ee87389` and `882c02bf371f46e95713e6f3e96a5ce616908137d3f34ffe3ec744dffdcc28e4`, respectively (SHA-256, LF line endings).

Recover the original bank bytes from the published archive by serializing its `cases` array in the archived key order with Python's `json.dumps(cases, ensure_ascii=False, indent=2)`, appending one LF and encoding as UTF-8.
