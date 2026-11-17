# Prospective test of conflict-only feedback

Freeze the feedback policy from commit `09a788d9718ad50edbf52ac0647bb83dd176c0eb` and test it on 32 new, independently written, synthetic conversations. The earlier 16 conversations were used to choose the policy. They are excluded from this test.

## Primary comparison

Both policies start from the same Qwen draft. The separate wording rule reads the original conversation. The host compares its reading with the draft, before any reread or arithmetic check.

- **Reminder alone.** Ask Qwen to reread the quantities and their order. Allow it to keep or revise the draft.
- **Conflict-only feedback.** Use that same reminder. Add the frozen conflict notice only when the independent reading explicitly contradicts the first draft. Send no verifier message on agreement or unresolved wording. The notice gives no corrected field or answer.

The policy earns a positive result on this set if it preserves every clear answer the reminder released, preserves every correct interpretation and answer among them, and reduces the total number of wrong or unwarranted numeric releases. Report ties and tradeoffs. A reduction in wrong releases from withholding a previously correct answer fails the preservation criterion. This is a descriptive replication on a small fixed set.

## Cases and scoring

The case author supplies 16 clear add-then-multiply requests, eight needing clarification and eight asking for unsupported arithmetic. Case selection is independent of rule recognition and model output. Count all cases, including unresolved wording and malformed outputs. A faithful clear answer must match all three intended fields and the final number. For the other 16 cases, any numeric release is unwarranted. Also record whether the chosen disposition was specifically clarification or unsupported.

Report clear releases, faithful clear answers, wrong clear releases, unwarranted releases, and actual step checks. Track gains and losses by case ID. Report how many times the verifier agreed, found a conflict, or could not decide. If a signal category has no cases, no conclusion about that category follows.

## Equal budgets

Use the same pinned local Qwen 2.5 0.5B model, prompts and output schema as in the earlier feedback experiment. Each reviewed policy gets one initial translation and at most one reread with the same 96-token generation cap, 45-second timeout, temperature 0 and seed 0. Score at most two arithmetic step checks per policy per case. There are no repair retries. Only the dialogue and that policy's own allowed messages reach the model.

Capture the neutral, reminder-only, and signalled alternatives independently so all policies can be replayed on the same original proposal. A conflict-only run uses exactly one reread. Original drafts, neutral rereads, always sending a signal, and requiring agreement are secondary comparisons. Record the case and code hashes before the first generation. The case labels enter only after the policies commit their decisions.

## Freeze record

All identifiers below are SHA-256. The 32 conversations have no exact wording duplicates in the earlier 16-case test, 12-case pilot, or their controls and probes.

| Frozen artifact | SHA-256 |
|---|---|
| Case bank, original bytes | `ea2fd5627922bfa7e16092a7ba7f310c105c6f92cf0ae9024145bd370f2afafa` |
| Case bank, canonical JSON | `68beb2a9025b8d17db37dc89909f7685bde806a0eb4104681bd8929f811b893a` |
| Wording rule, LF-normalized | `7f3d61f5021be84209cdb03315cb4858d2022dbf32d14d4c846c2401f01f5261` |
| Signal comparison, LF-normalized | `55224fa8216e87438f78c82f2073c05de7cb519025cf9e0313a57e354030389d` |
| Published feedback data including prompts, LF-normalized | `160f62d4d189fde2d3bceb10925b982dd984d265167cd1f9ace9ebc921095379` |
| Local collection script, original bytes | `e8321565f6f6dbbf7ea13c9f84305fd8d8c007705bd5c9c73461e5363920349a` |
| Prospective scorer, LF-normalized | `9b7f33587465c70448ff33eca86b68802e55b11b9ae1bd895eeac653008c0670` |
| Ollama model digest | `a8b0c51577010a279d933d14c2a8ab4b268079d44c5c8830c0a93900f1827c67` |

To reproduce the canonical bank hash from the eventual evidence, remove the `record` field from each case in order and serialize the list as UTF-8 JSON with sorted keys, literal Unicode, no whitespace between tokens and no trailing newline.
