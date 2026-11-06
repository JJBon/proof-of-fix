# Checking acceptance run v5: the contributor pays for its checks, proof-of-fix#49 (2026-10-25)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-checking-v5.json` (verdicts on 100 seeds, sweeps on 20; about 58 minutes). The baseline is checking v4 ([`acceptance-checking-v4.md`](acceptance-checking-v4.md)), the same oracles with the bounty paying for them.

**What's new:** the owner's rule, "the contributor pays for its checks; it's up to the contributor to judge whether a bounty is worth it".
- **Every bid posts a check deposit** worth one full attempt's checks (5.6).
  - The assigned solver's attested runs and AI verdicts are paid from it, and the rest returns.
  - Losing bids get it back.
  - Void bids and late deliveries forfeit the 2-credit evaluation fee from it.
- **The bounty pays no checks:** its price cap uses all it holds again, and the minimum target is gone.
- **Honest solvers price their expected checks** (about 3.6 per attempt) into their bids.
- **A split farmer delivers borderline junk** meant to split the jury, which would get its bond back.

## Result

| Hunting elasticity (100 seeds) | Checking v4 (the bounty pays) | **Checking v5 (the solver pays)** |
|---|---|---|
| **0.5** (default) | ❌ honest solvers +1.5 ± 1.4 | ✅ **every criterion passes** |
| 0 | ❌ the same | ✅ every criterion passes |
| 1 | ❌ the same | ✅ every criterion passes |

**It's the first checking run to pass everything.** Honest solvers now earn **+4.5 ± 1.4**, significantly more than their cost.

**Why:** a solver now prices its own checks into its bid, and the bounty no longer sets the oracle reserve aside from its price cap. So the solver is paid for the checks its work needs, and funders stop paying for checks on other people's failed attempts.

The cost of AI consensus at the assumed model accuracy is unchanged: about a quarter of good fixes are rejected. The model-quality work (#47) still matters.

## v4 vs v5 (default, 100 seeds)

| Criterion | v4 | **v5** |
|---|---|---|
| **Honest solvers earn** | ❌ +1.5 ± 1.4 | ✅ **+4.5 ± 1.4** |
| **Split farmer** (borderline junk) | (new) | ✅ **−322 ± 19** |
| Bad deliveries caught before beta | 98.7 % | ✅ 99.0 % |
| Good fixes wrongly rejected | 24.8 % | 25.1 % |
| **Funders' cost per paid bounty** | 77.1 | **58.7** |
| Mean price | 63.0 | 67.5 (the solver's checks priced in) |
| Bounties paid / unsolved per run | 24.7 / 64.7 | 23.7 / 65.2 |
| Honest evaluators / runners / validators | +1.33 / +0.12 / +10.4 | ✅ +1.30 / +0.06 / +10.7 |
| Forging runner / herder / copy operator / crafter / bug planter / half-fixer | −7 / −1.8 / −284 / −325 / −270 / −250 | ✅ −8 / −1.8 / −303 / −348 / −302 / −234 |
| Hidden bidder / bluffer | +8.5 / 0 | ✅ +1.4 ± 11.8 / −7 ± 12 (neither gains) |
| Rings of 2 / 3 / 4 / 6 | none significant | ✅ none significant (−20 / +1 / −6 / +24) |
| Spam / no-shows / reputation farming / owner defecting | −273 / −422 / −282 / −0.3 | ✅ −254 / −422 / −269 / +1.3 ± 1.1 |

**The solver paying against the bounty paying,** on the same seeds:
- prices rise **4.5 ± 1.4**;
- honest solvers gain +4.5 ± 4.2, not significant on its own;
- funders' cost per paid bounty changes −18 ± 17, not significant;
- about 1 fewer bounty is paid (−0.95 ± 0.5).

## Sweeps (20 seeds)

"Honest solvers earn" fails in most sweep rows: at 20 seeds a mean of about +4 isn't twice its standard error. The rows that teach something:

| Sweep | Finding |
|---|---|
| **Model accuracy +0.05 / +0.1** | **every criterion passes**; good fixes rejected 12 % / 6 %, and honest solvers +20 / +31 |
| Model accuracy −0.05 | good fixes rejected 44 %, and honest solvers −26 |
| Cost per line 0.5 / 2 | cheap work passes everything; at double cost, honest solvers −0.7 and the hidden bidder flags |
| Reserve 50 % | 18 bounties paid (against 24 at 75 %), and a checking attack flags |
| Evaluator cost 0.5 per verdict | above the 0.5 verdict fee: evaluators lose, as expected |
| Runners per delivery 1, planted share 0, first jury of 1 | "checking attacks lose" flags: a single runner, no planted cases, or a one-model jury weakens the checks |

## Still open

1. **Model accuracy:** the real-data measurement (budget), then #47. Better models raise honest solvers' earnings more than any rule here.
2. **Amendments to tests and scope** (#46), and the **oracle desk study** (#44).
3. **The go-live checklist on #15:** accuracy, identity, the oracle provider, and the legal review.
