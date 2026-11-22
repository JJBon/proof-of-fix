# Hypothesis register

The hypotheses behind the paper (#158), each tested under [the protocol](protocol.md). The judge thresholds below were **confirmed by the owner on 2026-11-13**; the pre-registration that tests them fixes them with its hash.

## AI judges as payment oracles (the paid judge check, #160)

Data: the frozen judge set in [`reports/judges-v1.md`](../../reports/judges-v1.md), plan `9ed6768c875c4516` (50 SWE-bench Verified issues, each with a good and a bad fix, 7 families), extended as the pre-registration below describes.

| ID | Hypothesis | Measure | Threshold (owner, 2026-11-13) | Status |
|---|---|---|---|---|
| H1 | A panel of judges from different families catches a meaningful share of **passing-but-wrong** fixes, which tests alone accept. | The share of passing-but-wrong fixes a 2-of-3 cross-family panel fails | ≥ 50 %, by the lower bound of a 95 % interval | pre-registered in [`judges-v2.prereg.md`](../../reports/judges-v2.prereg.md), awaiting the owner's approval of its hash |
| H2 | A majority of three judges from three families has fewer false passes than the best single family. | False passes, panel against the best family, on the same cases | Fewer, by an exact McNemar test at α = 0.05 | pre-registered (judges-v2), awaiting approval |
| H3 | Judges' errors are more correlated within a family than across families. This is what the family caps (D6) rely on. | The phi correlation of errors, for pairs of models within a family and pairs across families | The cross-family mean is lower; report both with intervals | pre-registered (judges-v2), awaiting approval: v2 adds a second model in two families (Gemma 3 for Google, gpt-oss for OpenAI) |
| H4 | Prompt injection in the diff moves a panel's false-pass rate by at most a few points. | Panel false passes, injected against clean, paired | At most +10 points, by the upper bound of a 95 % interval | pre-registered as **exploratory** in judges-v2 (owner, 2026-11-13): 50 injected bad fixes per kind give it little power; a confirmatory injection run comes later |
| H9 | A judge passes its own family's bad fixes no more often than other families' bad fixes. | False passes by judge family and solver family | Within ±10 points, by a TOST at α = 0.05 | pre-registered (judges-v2), awaiting approval. The owner replaced "no significant difference" with this equivalence margin on 2026-11-13. |
| H12 | A feature of a fix on its repository's code graph, computed with no model, separates good fixes from bad ones. | The chance a bad fix scores higher than a good one, per feature | Above chance with a 95 % interval, and it flags Opus's false passes without flagging good fixes | **exploratory, not supported:** ten features fixed in advance on #160's 228 cases; the graph features separate 38–58 % of the time, the two that looked strong are artefacts of who wrote the patch, and only size (no graph) carries a weak signal ([`graph-test-v1.md`](../../reports/graph-test-v1.md), #241). The graph as context for a judge or a contender is untested. |
| H13 | A judge that reads notes on earlier rejected fixes (same issue, or same file on an earlier commit) passes fewer bad fixes without rejecting more good ones. | Bad fixes passed with memory against the stored baseline, paired by case; good fixes passed as the guard | Fewer bad fixes passed (one-sided sign test, 0.05) and good fixes passed drop by at most 3 of 50 | **GPT, pre-registered (plan `f01c8ad9144ff58a`): not supported:** 21 to 17 of 101 bad fixes passed, 4 to reject and 0 to pass, p = 0.0625; good fixes 35 to 36 of 50 ([`reports/judges-memory-v1.md`](../../reports/judges-memory-v1.md)). **Opus, exploratory pilot in Claude Code:** 25 to 16–18 of 28 bad fixes it had passed, good fixes unchanged ([`reports/memory-pilot-v1.md`](../../reports/memory-pilot-v1.md)); not confirmed through the gateway. |

**What #160's pre-registration adds to the v1 plan:**
- **H1's arm:** at least 40 passing-but-wrong fixes. These are patches the hidden tests accept but the full developer tests or reference behaviour reject, taken from Wang, Pradel and Liu's data and UTBoost's. They get their own manifest and hashes.
- **Stronger ground truth for every case:** the repository's full developer tests, run in the pinned sandbox, recorded beside the hidden-test label. Wherever the two disagree, a person reviews the case.
- **Power:** with 50 bad fixes, a false-pass rate near 20 % has a 95 % interval of about ±11 points. That's enough for H2's paired test, but not to tell 5 % from 10 %. **The owner's rule (2026-11-13):** 100 bad fixes (about ±8 points) if the pre-registration's cost estimate fits the $100 budget, otherwise 50; more bad fixes come before more families.
- **H1–H4's thresholds,** as confirmed by the owner, and the multiple-comparison correction across H1–H4 and H9.

## The mechanism (the simulation)

| ID | Hypothesis | Measure | Threshold | Status |
|---|---|---|---|---|
| H6 | No modelled attacker is shown to gain against its honest twin under ADR 0004's parameters. | Each attacker's gain over its twin | D17's "not shown to gain" ($10 tolerance) | **exploratory:** rounds 1–3 (`reports/open-validators-v1…v3.1.md`) reached 13 of 13 only after criteria changed between rounds. It needs a confirmatory run on fresh seeds 41–80 with every criterion frozen. |
| H7 | H6 still holds when the simulation uses #160's measured accuracy, borderline rate and family agreement in place of the assumed values. | As H6 | As H6 | **exploratory, not holding as stated:** on #160's verdicts v3 as designed merges 10–18 bad fixes per 100 paid against 1.1 assumed ([`open-validators-measured-v1.md`](../../reports/open-validators-measured-v1.md)). Of v3's nine open-validator attackers eight still lose and the seed grinder is no longer shown to lose; a solver that only submits bad fixes gains on the flat fee under assumed and measured judges alike (v3's own judged spammer, on the market fee, lost and is not yet re-run) ([`open-validators-measured-v2.md`](../../reports/open-validators-measured-v2.md)). Proof-level and pricing attackers not re-run. Seeds 1–40; a confirmatory run needs the amended rules frozen and seeds 41–80. |
| H8 | The service fee settles within 25 % above the validators' break-even cost. | The fee against break-even, over the last 13 weeks | `FEE_MARGIN`: mean + 2 SE ≤ 1.25 × | exploratory (round 1's re-run: 1.21 ± 0.04 ×) |
| H10 | The conclusions of H6 and H8 don't flip when an *assumed* input moves within a plausible range. | Each criterion across a sweep of each assumed input | No criterion changes outcome inside the stated range, or the report names the flipping range | open |

## Systems

| ID | Hypothesis | Measure | Status |
|---|---|---|---|
| H5 | Batch-invariant decoding gives identical verdicts for identical inputs. | Identical verdicts out of repeats | **exploratory, supported:** 600 of 600 in [`reports/determinism-v1.md`](../../reports/determinism-v1.md), on one model and one setup. A confirmatory run needs a second model or host. |
| H11 | Sealed on-chain panels cost little enough to run every check. | Gas per seal, reveal and receipt, and per draw | open: measured in `reports/contract-v3.md` (#227); the threshold is set against the fee table |

## Retired

None yet.
