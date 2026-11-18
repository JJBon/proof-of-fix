# Judges with a failure memory: GPT (v1)

**Status: run complete, analysed once.** Plan `f01c8ad9144ff58a`
([`judges-memory-v1.prereg.md`](judges-memory-v1.prereg.md), [`judges-memory-v1.plan.json`](judges-memory-v1.plan.json)).
230 of 230 calls on 2026-11-15, no invalid verdict, $4.46 of real spend (1.64 million tokens) against a worst case of
$26.73. `scripts/judge_memory_run.py report --final` ran once, after the last call.

## Result

**H1 is not supported for GPT.** With notes on earlier rejected fixes, GPT passed 17 of 101 bad fixes against 21 at
baseline: 4 verdicts went to reject and none to pass (one-sided exact sign test p = 0.0625, alpha 0.05).

| | Baseline (stored v2) | Memory | Other-issue memory |
|---|---|---|---|
| Bad fixes passed (of 101) | 21 | 17 | – |
| Good fixes passed (of 50) | 35 | 36 | – |
| Good fixes passed (of 49 with such a note) | 35 | – | 35 |

- **H2 (guard) holds:** good fixes passed did not drop with memory (35 to 36) or with notes from another issue only
  (35 to 35).
- **H3 (secondary) is not supported:** on the good fixes 4 went to pass and 3 to reject (p = 0.50). The memory did not
  cure GPT's rejections of good fixes.
- **Drift check:** 3 of 30 baseline reruns differed from the stored verdict (limit 5), so the stored baseline was used.

Reported, not tested (bad fixes passed, baseline to memory):

| Split | n | Baseline | Memory |
|---|---|---|---|
| A note on the same issue | 26 | 5 | 3 |
| Same-file notes only | 75 | 16 | 14 |
| Passes the tests but wrong | 58 | 9 | 7 |
| Fails the hidden tests | 43 | 12 | 10 |

## Reading

- The direction matches the pilot (every changed verdict on a bad fix went to reject, good fixes untouched), but the
  effect is small and does not pass the registered test. On these 101 bad fixes GPT's baseline was already 21 passes,
  so at most 21 verdicts could improve; 4 did.
- The pilot's larger effect was for Opus, measured on cases chosen because Opus had passed them, inside Claude Code.
  It has not been confirmed through the gateway. This run neither confirms nor refutes it.
- A rerun of an unchanged prompt flips about 1 verdict in 10 here (3 of 30), which is the same size as the effect
  seen. A larger case set, or repeated calls per case, is needed to resolve an effect of this size.

## Limits

- One seat. The notes were written by Opus; GPT may use another family's notes differently from its own.
- 101 bad fixes with history, 26 of them with a note on the same issue, where the pilot saw most of its effect.
- The limits stated in the pre-registration (who wrote the fixes, inferred reasons for fixes that passed the tests).

## Data

`data/judges/memory-v1/`: `notes.json`, `set.json`, `verdicts-openai.json` (pass, fail or invalid per call; no text).
