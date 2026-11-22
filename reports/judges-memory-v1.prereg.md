# Judges with a failure memory: pre-registration (draft v1)

**Status: run complete on 2026-11-15; result in [`judges-memory-v1.md`](judges-memory-v1.md).** Before the run: Plan hash `f01c8ad9144ff58a`
([`judges-memory-v1.plan.json`](judges-memory-v1.plan.json)): 230 calls on one seat (GPT), worst case $26.73. The runner
(`scripts/judge_memory_run.py`) passed its fake run and its tests against the stub gateway (approval, budget stop,
resume, no interim report). Refs #241 (Hb). Follows the exploratory pilot in
[`memory-pilot-v1.md`](memory-pilot-v1.md).

## Question

Does a judge that reads notes on earlier rejected fixes (same issue, or same file on an earlier commit) pass fewer bad
fixes, without rejecting more good ones, and does this hold for each family on the gateway?

## Cases

- All of #160's cases that have at least one earlier rejected fix in the same repository: **151 cases (101 bad, 50
  good)**, chosen by history alone, never by any judge's verdict. The rule is the pilot's (`scripts/memory_pilot/`):
  up to two bad fixes for the same issue, then bad fixes on an earlier base commit that change a non-test file this
  fix also changes, three notes at most.
- The 77 cases with no history are out: both arms would be identical.

## Notes (fixed before any judging)

- 126 notes, all written by Opus with the pilot's prompt, one fresh sub-agent per note inside Claude Code: 116 in the
  pilot and the 10 missing ones on 2026-11-15, before the plan was hashed. They are in
  `data/judges/memory-v1/notes.json`; which case reads which note is in `set.json` beside it.
- The note file is frozen and hashed into the plan. Every seat reads the same notes; a changed note changes the
  hash and needs a new approval.
- A note's writer sees the rejected patch, the issue, the final outcome and, for a fix that failed the tests, the
  tests that decided the issue. It never sees a merged fix or another case.

## Arms

| Arm | Prompt | Cases | Source |
|---|---|---|---|
| Baseline | #160's judge prompt | 151 | **Stored** v2 verdicts (same prompt, same gateway), not rerun |
| Memory | Baseline plus the notes | 151 | New calls |
| Other-issue memory | Baseline plus notes from a different issue only | 49 good (one has no such note) | New calls |
| Drift check | Baseline, rerun | 30 per seat, seeded | New calls |

- **Why the stored baseline is valid here and was not in the pilot:** the pilot picked cases by Opus's errors, so a
  rerun was needed to rule out chance flips. Here cases are picked by history alone.
- **Drift check:** if more than 5 of a seat's 30 reruns differ from the stored verdict, that seat's stored baseline is
  not used and the seat is reported as inconclusive (a full baseline rerun needs a new approval).
- **Other-issue memory** uses a same-file note where one exists (15 good fixes), otherwise the most recent earlier
  failure in the same repository among the 126 notes. It tests whether any memory makes a judge stricter.

## Hypotheses and decision rules

- **H1 (primary, per family):** on the bad fixes, fewer pass with memory than at baseline. Paired by case, exact
  one-sided sign test on the cases whose verdict changed, alpha 0.05, Holm-corrected across the primary families.
- **One seat (owner, 2026-11-15): GPT.** It is the strict judge of v2 (it passed 40 % of the ordinary bad fixes and
  rejected 15 of 50 good ones), so a memory has room to help on both sides. With one seat the Holm correction changes
  nothing. Opus has only the exploratory pilot; Gemini is untested. Either needs its own plan and approval
  (`plan --seats`).
- **H3 (secondary, GPT):** on the good fixes, more pass with memory than at baseline (one-sided exact sign test,
  alpha 0.05, reported beside H1 and not a condition of it).
- **H2 (guard, per family):** good fixes passed with memory, and with other-issue memory, are each no fewer than the
  baseline minus 3 (of 50). A family that meets H1 and fails H2 is reported as "stricter, not better informed".
- **Reported, not tested:** the split by same-issue and same-file notes, by test-backed and inferred notes, and by pool.
- Invalid verdicts drop the pair and are counted. One analysis, after the last call; no interim looks.

## Cost (from stored token counts and v2's real spend; the notes add about 5 % input)

Per seat, memory arm on 151 cases:

| Seat | Expected | Worst case (every answer at its limit) |
|---|---|---|
| Opus | $9.97 | $31.41 |
| GPT | $2.95 | $17.29 |
| Gemini | $4.06 | $17.38 |
| DeepSeek, Qwen, Mistral, Nemotron, Gemma, gpt-oss | $4.70 | $20.04 |

The other-issue arm and the drift check add 53 % (80 more calls per seat on 151).

**Chosen (owner, 2026-11-15): GPT only.** 230 calls. The plan's worst case, counted as the runner counts it, is
**$26.73**; the expected spend is about $4.50, from v2's real cost per call. The three-seat plan (690 calls, worst
case $102.06) was prepared and not chosen.

The budget check counts the worst case. The gateway had about $15 of counted headroom under its $160 cap on
2026-11-15, so the worst case does not fit. The owner either raises the cap by about $12 or, as for v2, lets the run start with `--max-usd` set to the real headroom: it stops cleanly before a call that could pass it, and resumes.

## Before any paid call

1. The owner approves the worst case and chooses how it fits the gateway cap (above).
2. This document and the plan are merged.
3. The owner sets `POF_JUDGE_RUN_APPROVED=f01c8ad9144ff58a`; the run is
   `scripts/judge_memory_run.py run --execute --max-usd <the approved limit>`, then `report --final` once.

## Limits known in advance

- The good fixes are the projects' own and the bad ones were written by models (as in #160).
- For a fix that passed the tests, the note's "why" is the writer's inference; the benchmark has no failing test for it.
- Notes were written by one family. A family may read its own family's notes differently from another's.
- **The three seats are not on equal terms** (as in v2): Opus and GPT run at their API defaults, Gemini at
  `reasoning_effort: "low"` because at its default it spent its output limit thinking. Opus costs twice as much per
  token as the other two. Each seat is compared with itself, so its own result stands; comparisons between seats
  do not.
