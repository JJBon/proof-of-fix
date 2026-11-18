# A failure memory for judges: exploratory pilot (v1)

**Status: exploratory, not pre-registered, small numbers.** Hypothesis Hb of #241: a judge that sees why earlier
fixes on the same issue or code were rejected judges better. Run on 2026-11-15 with sub-agents inside Claude Code
(no gateway spend, about 25 million tokens of plan usage), not through the judge seats' gateway calls.

## Design

- **Cases:** from #160's set, the 109 cases with at least one earlier rejected fix in the same repository: 28 bad fixes
  Opus had passed, 31 bad fixes Opus had rejected (a seeded sample of 50, of which 31 have history), all 50 good fixes.
- **Earlier failures, in time order:** another bad fix for the same issue, or a bad fix on an earlier base commit that
  changes a non-test file this fix also changes. Up to three notes per case, same issue first.
- **A note** (at most 130 words: changed, outcome, why it failed, lesson) is written by a fresh agent that sees only the
  rejected patch, the issue, the final outcome and, for fixes that failed the tests, the tests that decided the issue.
  It never sees a merged fix or any other case. For the 46 fixes that passed the tests but were wrong there is no
  failing test on record, so the "why" is the writer's inference and says so.
- **Arms**, same judge prompt as #160 (`pof/judges/prompt.py`), one fresh Opus agent per packet, no labels, no tools
  beyond reading its packet: (0) baseline, rerun fresh; (2) baseline plus notes written by the session's stronger
  model ("curated"); (3) baseline plus notes written by Opus itself ("judge-written").
- **Analysis:** paired per case, exact sign test on the cases whose verdict changed. Written before any verdict was read;
  one look per arm.

## Result (passes out of n)

| Cases | n | No notes | Curated notes | Judge-written notes |
|---|---|---|---|---|
| Bad fixes Opus had passed | 28 | 25 | 18 | 16 |
| – with a note on the same issue | 14 | 12 | 8 | 5 |
| – with same-file notes only | 14 | 13 | 10 | 11 |
| Bad fixes Opus had rejected | 31 | 4 | 2 | 3 |
| All bad fixes | 59 | 29 | 20 | 19 |
| Good fixes | 50 | 48 | 49 | 47 |

- No notes against curated, on the 28: 7 to reject, 0 to pass, p = 0.016. Against judge-written: 9 to reject, 0 to pass,
  p = 0.004. Curated against judge-written: 4 to reject, 2 to pass, p = 0.69. None corrected for the number of tests.
- Rerun with no notes, Opus passed 25 of the 28 again: the false passes are stable, not chance flips.
- Good fixes were not rejected more in either memory arm.
- Of the 28, both kinds of note caught 8, only the curated 2, only the judge-written 4.
- Full tables: `data/judges/memory-pilot/result.txt`, `result3.txt`.

## Limits

- 28 cases carry the main result; the splits are smaller still.
- Every good fix had a test-backed note on its own issue. Whether notes about another issue make a judge reject good
  fixes was not tested.
- The sub-agent harness differs from a judge seat's gateway call; both arms shared it, so the comparison holds, the
  absolute rates may not.
- One family judged. Whether other families gain is open.
- The note for a fix that passed the tests uses the benchmark's later verdict that it was wrong, as a dispute would
  reveal it in the protocol; no failing test exists for it here.

## Reading

A memory of final outcomes looks worth a registered test: it cut the top judge's stable false passes by a quarter to a
third without making it stricter, and the judge's own notes did as well as a stronger model's. Structure alone (the
graph features of `reports/graph-test-v1.md`) did not separate fixes; reasons attached to code did.

## Next

A registered run through the gateway on the seated families, with the notes fixed in advance, a control of good fixes
with other-issue notes only, and a size chosen for a moderate effect. Paid: needs the owner's approval.

## Reproduce

`scripts/memory_pilot/`: `prep2.py` (choose earlier failures, writer inputs), `prep3.py` and `prep4.py` (packets),
`analyze.py` and `analyze3.py`. The case files with patches are local only; notes, keys and verdicts are in
`data/judges/memory-pilot/`.
