# Open validators with measured judges, v5: three deposit-free mechanisms (proof-of-fix#236; 2026-11-15)

**Status: exploratory.** This report continues [`open-validators-measured-v4.md`](open-validators-measured-v4.md). It uses seeds 1–40, the seeds every earlier round used, so nothing here is confirmatory. Every ± is two standard errors of the mean. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json` (#160).

**Commands:**
- `python3 -m pof.sim.openval.nodeposit --seeds 40 --jobs 15 --out DIR` runs every table (about 80 minutes on 15 cores) and writes the raw results;
- `python3 -m pof.sim.openval.nodeposit --render DIR` prints the appendix from them.

## The question
The owner approved simulating three mechanisms that need no solver's deposit (2026-11-15), each alone and in combination, with **no deposit as the base case**:
1. **Reputation before large claims** (`REP_CAP`, "R").
2. **The shared pot split by an impact weight** (`POT` "impact", "P").
3. **A fee that only covers the judges' cost** (`JUDGE_FEE`, "F").

He said he will reconsider the deposit, or another market mechanism, if the simulations do not hold. This report says plainly where they do not.

## In brief
- **No mechanism holds alone.** Each leaves at least one attacker earning more than its twin with 1 or 3 active honest solvers.
- **The reputation cap with the judges' fee (R+F) holds with 3 and with 10 active honest solvers,** for Opus 5.5 and GPT-6.1 seated alone and both kinds of bad fix: all six attackers earn at or below their twins in all 8 of those conditions (48 attacker-cells).
  - **It does not hold with 1 active honest solver.** The largest gains there are about +$3,000–3,900 a year (the retrier on fixes that pass the tests; the long con under GPT-6.1).
  - **It rests on an assumed find rate.** At 25 % (each honest solver finds a failing test for a bad pass 1 time in 4) it holds from 3 solvers. At 10 % it fails with 3 solvers too (up to +$2,932 ± 540). At 50 % it holds from 3 and nearly holds with 1 (up to +$221).
- **The pot by impact is not recommended now.** At correlation 0.6 it pays:
  - an **inflater** $13,600–15,000 a year more than its twin, at an assumed $20 to raise one fix's signal. Inflating stops paying only between $50 and $100 a fix, at every correlation tried;
  - a **farmer of the cheapest fifth** +$6,575 ± 415 (+$20,461 with equal units, +$967 at correlation 0.9);
  - **the solver of bad fixes more than bounties do** (+$1,554 against +$787 a year, Opus 5.5, 3 solvers), because each unit also pays out the funding of issues nobody fixed.

  What it does well, as v4 found: an honest solver's search of a pass earns $1.07–6.97 gross in the pot, against $0.06–0.37 with bounties.
- **The judges' fee is $5.03 a submission** (measured: 7.6 checks at the market's break-even fee of $0.53 plus $0.13 of usage), against $0.96–1.55 charged now at the fee's floor. Alone it stops the solver of bad fixes only with 3 solvers, Opus 5.5 and fixes the tests fail. With 1 solver the fee would have to be $8.71–62.54.
- **The honest newcomer's cost:** under the cap it may claim a median bounty ($86) within 0.6–0.9 weeks. As first proposed (a reversal resets reputation), its own honest mistakes that pass and are reversed reset it 11–27 times a year: 13–32 % of the issues it wanted are turned away, and it loses $637–773 a year with Opus 5.5. The sweep's alternative, **a reversal takes 2 × its bounty off**, cuts that to 1.6–3.5 % and $58–112 (not significant), with the attackers unchanged at 3 and 10 solvers (post hoc, section 6).
- **Code health, per 100 funded issues** (3 solvers, Opus 5.5, the tests fail them): 58.5 correctly fixed / 1.9 wrongly marked fixed / 39.6 left unfixed with no mechanism; **59.8 / 1.2 / 38.9 with R+F** (the solver of bad fixes leaves); 54.5 / 1.8 / 43.7 with the pot by impact (honest solvers leave 6.8 % of issues as not worth their effort).
- **What still needs a deposit:** with **one** active honest solver, R+F leaves gains of $237 to $3,870 a year per attacker (retrier, long con, free identities, the solver of bad fixes, the reputation sale). In the post hoc rows only a deposit of about **2,500 (25 % of the bounty)** closes all of them; 1,000 leaves six open.

## 1. What was added to the model
Each mechanism is a named field of `Params`, off by default and read only by `nodeposit.NDNet` (a plain `Net` refuses them), so reports measured-v1 to -v4 reproduce. A test checks that `NDNet` with every switch off gives v4's network exactly.

| Switch | Rule | Default | Values run |
|---|---|---|---|
| `REP_CAP`, `REP_BASE`, `REP_MULT` | An identity's **open claims** (the bounties of its fixes not yet final) add up to at most `REP_BASE` + `REP_MULT` × its reputation. Reputation is the sum of the bounties of its fixes paid and never reversed. A claim over the cap is refused before it is judged, and costs nothing | off, $50, ×1 | base $25–200, ×0.5–2 |
| `REP_ON_REVERSAL`, `REP_LOSS_X` | A pass reversed by a test resets reputation to 0 ("zero"), or takes `REP_LOSS_X` × its bounty off ("minus") | "zero", 2 | both |
| `POT`, `POT_WINDOW_WEEKS` | No per-issue bounty. An issue's funding goes into its window's pot; at the window's end the pot is split over the fixes paid in it by weight: 1 ("equal") or the issue's impact signal ("impact"). A reversed fix's weight goes to whoever reversed it. With `REP_CAP`, an identity's share of a window is capped as a claim is | off, 13 weeks | equal; impact |
| `World.impact_corr`, `inflate_sd`, `inflate_cost` | **Assumed:** the signal's correlation with true impact (log space); how far an inflater raises its signal; what that costs a fix | 0.6, 1 SD, $0 | 0.3, 0.6, 0.9; $0–100 |
| `JUDGE_FEE` | Every submission pays it on arrival, never refunded, in place of its panels' per-check charges | 0 | $5.03 |
| `World.effort` | **Assumed:** what an honest fix costs to write, as a share of its bounty (as `potsplit.EFFORT`) | 0.5 | 0.5 |

**The pot is now a network simulation,** not expected values: the windows, the split, the disputes, the judges and the honest solvers who leave an issue all run in `NDNet`. An honest solver leaves an issue when the network's pass rate so far × the unit's value so far × the issue's weight is below its effort (from week 4).

**The base** is v4's primary case: task 10.1's network with **no solver's deposit** and no appeal (`evidence.P0`), the world's contenders disputing passes (finding a failing test 1 time in 2, assumed), and `n` = 1, 3 or 10 active honest solvers, each searching every pass (`World.rival_solvers`; each finds a test for a bad pass 1 time in 4, **assumed**). One family is registered and seated: Opus 5.5 or GPT-6.1 (28 validators, as v4's GPT-alone rows). With no mechanism, v4's solver of bad fixes earns +$1,820 ± 196 here (Opus 5.5, 1 solver, the tests fail them; v4: +$1,902 ± 179 with Opus seated among seven families).

**The attackers, each against its twin on the same seeds:**

| Code | Attacker | Its twin |
|---|---|---|
| B | v4's solver of bad fixes: 5 a week, one identity, a random issue it may claim | submits nothing |
| S | **free identities:** a new identity for each bad fix, the largest issue a new identity may claim (without the cap: the largest of the week's 30 listings) | submits nothing |
| T | v4's retrier: up to 21 tries an issue, one identity | submits nothing |
| Tf | the retrier with a new identity each try (only with the cap) | submits nothing |
| L | **the long con:** farms good fixes on one identity until it may claim $625 (the largest bounty), then submits bad fixes on the largest issues it may claim until a reversal hits it, then farms again | farms all year |
| RS | **the reputation sale:** a buyer cashes in a bought identity of $5,000 with bad fixes until a reversal; the seller farms on a fresh identity | the seller keeps the identity and farms |
| F | **farmer:** good fixes, 6 a week, to the cheapest fifth of listed issues (outside the cap) | good fixes to typical issues, same expected effort |
| SF | the farmer filing its own issues, which nobody funds (only with the pot) | as F's |
| I | **inflater:** good fixes to typical issues, its signal raised 1 SD at $20 a fix in the grid (only with the pot) | does not inflate |

The honest newcomer is measured as an actor too: 5 fixes a week, 75 % of them good (the world's share), effort charged, on a fresh identity (or one of $5,000, "established"), against the same solver with no cap.

**"At or below its twin"** means not significantly above: the difference's mean minus 2 SE is not above zero. Bold cells are the ones above.

**Fixed before any 40-seed run** (committed in `32d205f` and `bf48a21`): the reputation rule and its proposal (base $50, ×1, a reversal resets), the grid, the sweeps, the find-rate rows and the fee's method. A 2-seed smoke test checked the implementation first. One bug was fixed before the run whose numbers are here: the honest twins of the newcomer, the farmer and the inflater had carried a capped identity (`2840354`).

**Post hoc rows** (added after results were seen): section 6's grid with "minus" and its deposit rows.

**What is assumed, measured or chosen:**

| Input | Value | Status |
|---|---|---|
| A judge's verdict | its family's recorded #160 verdict | **measured** |
| A contender finds a failing test for a bad pass | 1 in 2 | assumed (10.1) |
| An active honest solver finds one | 25 %; 10 % and 50 % in section 5 | **assumed** |
| A wrong test accepted against a good fix | 5 % | assumed (10.1) |
| The judges' fee | $5.03 a submission | **measured** in the simulator (break-even fee and usage, section 3) |
| An honest fix's cost to write | half its bounty | **assumed** |
| The impact signal's correlation with true impact | 0.3, 0.6, 0.9 | **assumed**; #247 is not built |
| What raising a fix's signal by 1 SD costs | $0–100 (grid: $20) | **assumed** |
| True impact | the issue's bounty | **assumed** |
| The issues an actor sees when it picks one | 30 (a week's listings) | chosen |
| `REP_BASE`, `REP_MULT`, the reset | $50, ×1, reset | chosen in advance, swept |
| The long con's trigger; the reputation sold | $625; $5,000 | chosen |

## 2. Reputation before large claims (R)
**The rule as proposed:** cap = $50 + 1 × reputation, on the sum of an identity's open claims; a reversal resets reputation to 0.

**Alone (combination R), against each twin ($ a year; bold: above its twin):**

| Attacker | Opus 5.5: 1 / 3 / 10 solvers | GPT-6.1: 1 / 3 / 10 solvers |
|---|---|---|
| B, the tests fail them | **+586** / +5 / −398 | **+1,744** / **+612** / −229 |
| B, pass the tests, wrong | **+1,958** / **+685** / −320 | **+1,210** / **+367** / −259 |
| T, the tests fail them (no mechanism: +16,040 / +7,117 / −13,804 with Opus 5.5) | **+1,157** / −157 / −1,086 | **+4,031** / **+1,272** / −648 |
| Tf, pass the tests, wrong | **+6,681** / **+3,056** / −13,060 | **+4,198** / −451 / −12,481 |
| L, pass the tests, wrong | −95 / −1,986 / −3,371 | **+1,351** / −406 / −1,722 |
| RS, pass the tests, wrong | **+252** / +67 / −129 | **+611** / +118 / +17 |

- **It cuts the retrier's gain by four fifths or more** (+$16,040 → +$1,157, Opus 5.5, 1 solver) and v4's solver of bad fixes' by two thirds. A reversal leaves an identity at $50, so a solver whose passes are often reversed is confined to small issues.
- **It closes nothing alone with 1 or 3 solvers.** With 10 it holds everywhere.
- **Free identities:** the cap bounds what one fresh identity can claim ($50), so free identities gain +$523 to +$1,956 (1 solver) against +$6,455 to +$15,663 with no cap. They still gain: a bad fix to a $50 issue stands often enough to beat its $1.55–2.05 of charges.
- **The long con loses with Opus 5.5 in every cell** (−$95 to −$4,867), and gains with GPT-6.1 only with 1 solver (+$1,351 to +$1,636). An honest fix pays it 0.94 − 0.5 = 0.44 of its bounty under Opus 5.5, while a bad one stands about 1 time in 8. Under GPT-6.1, which rejects 30 % of good fixes, the margin is thin.
- **The reputation sale is close to even** (−$129 to +$611): the buyer gets one round of bad fixes before the first reversal, and the seller loses the reputation's use.

**The sweep** (R alone, 3 solvers, the tests fail them; appendix):
- **A larger base opens the hole the cap is meant to close.** At $100, free identities gain in every cell (+$670 and +$2,075); at $200, more (+$1,767 and +$4,286).
- **A smaller base costs honest solvers more and still does not close GPT-6.1:** at $25 and ×0.5 a newcomer loses $1,894 ± 286 a year with 40 % of its issues turned away, and with GPT-6.1 the solver of bad fixes still gains +$109 to +$190.
- **The multiplier matters less than the base** for attackers, and a larger one helps honest solvers (×2: $565 against $658 at ×1).
- **The reset is what costs honest solvers.** "Minus 2 × the bounty" leaves every attacker within its errors of the reset rule (B +$10 against +$5, T −$117 against −$157 with Opus 5.5; B +$630 against +$612, T +$1,324 against +$1,272 with GPT-6.1) and cuts the newcomer's cost from $658 ± 184 to $100 ± 141, and issues turned away from 15.5 % to 1.7 %.

**The honest newcomer's cost, as proposed** (appendix, "The honest solver"):
- **Time to a typical bounty:** a median bounty ($86) after 0.6–0.9 weeks, a 90th-percentile one ($184) after 1.3–1.9 weeks, in every run. The base is not the obstacle: a few paid fixes lift the cap.
- **Work turned away:** 12.7–17.6 % of the issues it wanted (17–24 % of their value) with Opus 5.5, 21.5–31.6 % (28–41 %) with GPT-6.1. 11–27 of its own honest mistakes a year pass and are then reversed, and each reset sends it back to $50. An established solver ($5,000) is hit the same way ($519–756 a year).
- **In money:** $637 ± 201 to $773 ± 179 a year with Opus 5.5 (13–18 % of an honest solver's $4,383–4,977); $178–269 with GPT-6.1 (not significant).

**Recommendation for R:** adopt the open-claims cap with base $50 and ×1, **with a reversal taking 2 × its bounty off** rather than resetting it (chosen from the sweep after it was seen; section 6 checks it in the grid). Never alone. Do not raise the base: free identities gain from $100.

## 3. The judges' fee (F)
**What it is set to:** every check the network paid for in a year (counted panels, audits, challenge and test panels), priced at the fee at which the mean active validator nets zero (`pricing.settle`: $0.53) plus a judge's usage ($0.13), over the submissions. On seeds 1–10 of the base network with 3 solvers: $4.91 and $5.11 (Opus 5.5 and GPT-6.1, the tests fail them), $5.21 and $4.88 (pass the tests, wrong). **`JUDGE_FEE` = $5.03.** Today's charges are $1.55 and $0.96 a submission, because the market's fee sits at its floor ($0.01) while validators neither enter nor leave (v4, section 11).

**Alone (combination F):**
- **The solver of bad fixes:** +$1,820 → +$946 (Opus 5.5, 1 solver, the tests fail them); +$787 → −$87 with 3 solvers; still +$4,151 on fixes that pass the tests with 1 solver.
- **The retrier:** +$16,040 → +$10,211 with 1 solver; +$7,117 → −$158 with 3 (the tests fail them), but +$14,152 on fixes that pass them.
- **Free identities with no cap** still gain +$5,580 to +$14,789 with 1 solver: they pick the largest issues.
- **The fee each attacker would need to earn nothing** (no cap; linear in the fee): $8.71–21.17 for the solver of bad fixes with 1 solver and $4.69–11.93 with 3; $9.29–21.85 for the retrier; $26.73–62.54 for free identities. At that size it is a deposit that honest solvers pay on every fix.
- **What it costs an honest solver:** $3.48–4.07 more a submission. An honest solver's year falls from $4,977 to $4,088 (Opus 5.5, 1 solver), and from $1,105 to $64 with GPT-6.1. **With GPT-6.1 seated alone and 3 or 10 solvers, an honest solver loses money** (−$448 and −$1,000 a year), because GPT-6.1 rejects 30 % of good fixes and each pays the fee. That is mainly a finding about GPT-6.1's strictness, which the fee makes visible.
- **The farmer** is below its twin (−$1,178 ± 168): it pays the fee on more, smaller fixes.

**Recommendation for F:** adopt at the measured cost, as the price of judging rather than as a defence. It makes the cap work (section 5). Re-measure it as the network grows: the break-even fee falls as each validator does more checks.

## 4. The pot weighted by impact (P)
#247's impact graph is not built. The weight is an assumed noisy signal of the issue's true impact (its bounty): log signal = ρ × standardized log bounty + √(1 − ρ²) × noise, scaled like the bounties.

**The pot alone** (3 solvers, the tests fail them; appendix):

| Split | Seated | B ($ a year) | F − twin | SF − twin | Honest solver's year | Issues not worth an honest fix | …their funding | Fixed / wrong / unfixed per 100 |
|---|---|---|---|---|---|---|---|---|
| bounties (no mechanism) | Opus 5.5 | +787 ± 144 | −527 ± 175 | n/a | 4,706 ± 284 | 0 | 0 | 58.5 / 1.9 / 39.6 |
| equal units | Opus 5.5 | +1,524 ± 217 | +20,461 ± 360 | +18,418 ± 338 | 12,573 ± 366 | 5.1 % | 12.6 % | 55.4 / 1.9 / 42.7 |
| impact, 0.3 | Opus 5.5 | +1,598 ± 250 | +13,271 ± 562 | +11,602 ± 541 | 12,932 ± 467 | 12.0 % | 17.5 % | 51.5 / 1.8 / 46.8 |
| impact, 0.6 | Opus 5.5 | +1,554 ± 238 | +6,575 ± 415 | +5,316 ± 413 | 12,244 ± 450 | 6.8 % | 9.4 % | 54.5 / 1.8 / 43.7 |
| impact, 0.9 | Opus 5.5 | +1,467 ± 221 | +967 ± 294 | −63 ± 294 | 11,001 ± 401 | 0.2 % | 0.3 % | 58.4 / 1.9 / 39.7 |
| equal units | GPT-6.1 | +4,410 ± 326 | +19,091 ± 454 | +17,288 ± 424 | 10,968 ± 488 | 7.7 % | 17.1 % | 40.5 / 3.4 / 56.1 |
| impact, 0.9 | GPT-6.1 | +4,023 ± 303 | +775 ± 347 | −116 ± 344 | 9,418 ± 493 | 1.1 % | 1.4 % | 43.4 / 3.6 / 53.0 |

- **The network confirms v4's expected values for equal units:** the farmer gains $19,000–20,500 a year, and 5–8 % of issues (13–17 % of the funding) are not worth an honest fix.
- **The impact weight fixes the farmer and the neglect only if the signal is good.** At 0.9 the farmer gains under $1,000 and almost no issue is left. At 0.3 a noisy signal leaves more issues than equal units do (12 %): the hard issues it under-weights are the ones that cost most.
- **The inflater wins at every correlation while inflating costs $50 a fix or less** (+$5,055 to +$20,456 a year), and loses at $100 (−$5,451 to −$7,899). The weight is a price, and whoever can move it is paid for moving it. #247 would have to make raising a fix's signal by a standard deviation cost more than about $75, or be caught, before the pot can use it.
- **The solver of bad fixes gains more in the pot than with bounties** at every correlation: a unit is worth $129–185 against a median bounty of $86, because the pot pays out the funding of issues nobody fixed (v4's caveat, now measured). The honest solver's year more than doubles for the same reason.
- **It pays honest solvers to search** ($1.07–6.97 a pass gross, against $0.06–0.37 with bounties; a search costs $0.50, assumed). In the simulation rivals search for free in both, so this shows in no attacker's row.
- **With the cap, the pot confiscates honest income.** The cap on an identity's share of a window, read at the window's close, catches honest solvers just after a reset: an honest solver loses $18,300–19,800 a year to it (R+P rows of the honest-solver table). The solver of bad fixes on one identity then loses too, but only because the same confiscation hits it. **R+P as built is a flaw in combining the two;** a sound combination would cap claims, not window shares.

**Recommendation for P:** **do not adopt now.** Revisit when #247 is built and measured: its signal's correlation with impact must be near 0.9, and raising a fix's signal must cost more than about $75 or be caught. Even then the pot raises the solver of bad fixes' gain, so it needs the cap and the fee beside it, with the cap on claims and not on window shares.

## 5. Combinations
**Does every attacker earn at or below its twin?** Both kinds of bad fix; 25 % find rate. "holds": every attacker in both pools is at or below its twin; otherwise the attackers above it and the largest gain ($ a year).

| Combination | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|
| none | no: B, S, T (up to +23,958) | no: B, S, T (up to +19,230) | no: S (up to +703) | no: B, S, T (up to +23,740) | no: B, S, T (up to +18,132) | no: S (up to +675) |
| R | no: B, S, T, Tf, RS (up to +6,681) | no: B, S, T, Tf (up to +3,056) | holds | no: B, S, T, Tf, L, RS (up to +6,679) | no: B, S, T, Tf (up to +2,732) | holds |
| P | no: B, S, T, F, SF, I (up to +26,467) | no: B, S, T, F, SF, I (up to +18,138) | no: S, F, SF, I (up to +15,022) | no: B, S, T, F, SF, I (up to +33,788) | no: B, S, T, F, SF, I (up to +20,955) | no: B, S, F, SF, I (up to +14,261) |
| F | no: B, S, T (up to +20,267) | no: B, S, T (up to +14,152) | holds | no: B, S, T (up to +18,691) | no: B, S, T (up to +11,130) | holds |
| R+P | no: S, Tf, F, SF, I (up to +14,864) | no: S, Tf, F, SF, I (up to +14,946) | no: F, SF, I (up to +15,022) | no: B, S, Tf, F, SF, I (up to +15,629) | no: S, Tf, F, SF, I (up to +13,974) | no: F, SF, I (up to +14,261) |
| **R+F** | no: B, S, T, Tf, RS (up to +3,045) | **holds** | **holds** | no: B, S, T, Tf, L, RS (up to +1,711) | **holds** | **holds** |
| P+F | no: B, S, T, F, SF, I (up to +22,647) | no: B, S, T, F, SF, I (up to +14,943) | no: F, SF, I (up to +15,019) | no: B, S, T, F, SF, I (up to +27,108) | no: B, S, T, F, SF, I (up to +13,971) | no: F, SF, I (up to +14,259) |
| R+P+F | no: S, Tf, F, SF, I (up to +14,861) | no: S, Tf, F, SF, I (up to +14,943) | no: F, SF, I (up to +15,019) | no: S, Tf, F, SF, I (up to +13,783) | no: S, Tf, F, SF, I (up to +13,971) | no: F, SF, I (up to +14,259) |

**Why R+F works where each fails:** the cap bounds what one identity, fresh or reset, can claim (about $50), and the fee sets what each attempt costs ($5.53 with the attempt fee). A bad fix to a $50 issue must stand more than about 1 time in 9 to pay; with 3 honest solvers searching at 25 % it stands less often.

**R+F with 1 active honest solver** (the cells above their twins; reset rule):
- Opus 5.5, fixes that pass the tests: B +$1,196 ± 141, S +$1,086 ± 103, T +$3,036 ± 255, Tf +$3,045 ± 146, RS +$242 ± 195.
- GPT-6.1: B +$849 ± 157 and +$296 ± 135; S +$722 ± 101; T +$1,628 ± 196 and +$348 ± 239; Tf +$1,711 ± 121; L +$1,670 ± 444 and +$1,373 ± 452; RS +$280 ± 227 and +$568 ± 291.

**Sensitivity to the find rate** (appendix; reset rule):
- **at 10 %, R+F fails with 3 solvers as well** (B up to +$1,132, T +$2,730, Tf +$2,853, L +$1,800, RS +$472) and holds only with 10;
- **at 50 %, R+F holds with 3 and 10,** and fails with 1 only narrowly (B +$147 ± 94, S +$221 ± 84, T +$221 ± 125, Opus 5.5, fixes that pass the tests);
- **with no mechanism, even 50 % does not close it with 3 solvers** (B +$349, S +$2,151, T +$1,075 on fixes that pass them).

**Code health (E2), per 100 funded issues:** correctly fixed / wrongly marked fixed / left unfixed, with v4's solver of bad fixes present while it profits (otherwise its issues count as funded and unfixed). Full table, with "(left)" where it leaves, in the appendix.

| Combination | Opus 5.5, the tests fail them: 1 · 3 · 10 solvers | GPT-6.1, the tests fail them: 1 · 3 · 10 | Opus 5.5, pass the tests, wrong: 1 · 3 · 10 |
|---|---|---|---|
| none | 58.5/3.3/38.1 · 58.5/1.9/39.6 · 58.5/0.2/41.3 | 43.9/6.3/49.7 · 43.9/3.6/52.5 · 43.9/0.3/55.8 | 58.5/7.6/33.9 · 58.5/4.3/37.2 · 58.5/0.3/41.1 |
| R | 59.6/3.2/37.2 · 59.8/1.8/38.3 · 60.0/0.2/39.8 | 44.7/6.1/49.1 · 44.9/3.4/51.7 · 44.9/0.3/54.8 | 59.6/7.4/33.0 · 59.8/4.1/36.1 · 59.9/0.4/39.7 |
| P | 54.7/3.2/42.1 · 54.5/1.8/43.7 · 54.8/0.2/45.0 | 39.8/6.0/54.2 · 39.4/3.4/57.3 · 38.8/0.4/60.7 | 53.5/7.2/39.3 · 52.9/4.1/43.0 · 52.4/0.5/47.1 |
| F | 58.5/3.3/38.1 · 58.5/1.2/40.3 · 58.5/0.2/41.3 | 43.9/6.3/49.7 · 43.9/3.6/52.5 · 43.9/0.3/55.8 | 58.5/7.6/33.9 · 58.5/4.3/37.2 · 58.5/0.3/41.1 |
| **R+F** | 59.6/2.1/38.3 · 59.8/1.2/38.9 · 60.0/0.2/39.8 | 44.7/6.1/49.1 · 44.9/2.2/52.9 · 44.9/0.3/54.8 | 59.6/7.4/33.0 · 59.8/2.6/37.6 · 59.9/0.4/39.7 |
| R+P+F | 56.3/2.0/41.7 · 56.3/1.2/42.6 · 56.2/0.2/43.6 | 41.7/3.6/54.7 · 41.5/2.0/56.5 · 41.2/0.3/58.6 | 55.7/4.4/39.9 · 55.5/2.4/42.1 · 55.1/0.3/44.6 |

- **R+F is at least as good as "none" in every cell:** wrong fixes fall where the solver of bad fixes leaves (1.9 → 1.2 and 4.3 → 2.6 with 3 solvers), and fixed rises slightly because the cap turns away part of its claims.
- **Every pot combination fixes 2–6 fewer issues in 100** than bounties, from honest solvers leaving issues not worth their effort at correlation 0.6.
- **What the measure leaves out,** as in v4: issues no solver takes; honest work the cap turns away (the world's established solvers are not capped in these rows; a capped honest solver's turned-away share is in the honest-solver table); rivals' wrong tests, which are not modelled and would add honest reversals.

## 6. The recommended combination, and what still needs a deposit
**Recommended: the reputation cap with a reversal taking 2 × its bounty off, and the judges' fee** ("R(minus)+F"). The choice of "minus" over the reset was made after the reputation sweep was seen, so its grid below is **post hoc**.

**Every attacker against its twin** ($ a year, ± 2 SE; bold: above its twin):

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity | the tests fail them | −97 ± 148 | −732 ± 52 | −1,120 ± 24 | **+926 ± 172** | −244 ± 77 | −1,089 ± 27 |
| B | pass the tests, wrong | **+1,514 ± 212** | −57 ± 78 | −1,052 ± 33 | **+647 ± 227** | −510 ± 60 | −1,107 ± 28 |
| S, free identities | the tests fail them | −348 ± 71 | −833 ± 50 | −1,342 ± 30 | **+722 ± 101** | −224 ± 69 | −1,261 ± 32 |
| S | pass the tests, wrong | **+1,086 ± 103** | +30 ± 74 | −1,222 ± 40 | −39 ± 73 | −592 ± 59 | −1,316 ± 37 |
| T, retrier | the tests fail them | −718 ± 236 | −2,064 ± 88 | −2,927 ± 65 | **+1,938 ± 220** | −916 ± 133 | −2,821 ± 64 |
| T | pass the tests, wrong | **+3,870 ± 364** | −233 ± 124 | −2,781 ± 72 | **+2,444 ± 912** | −1,619 ± 93 | −2,874 ± 67 |
| Tf, retrier, new identities | the tests fail them | −4,810 ± 327 | −11,839 ± 470 | −26,488 ± 603 | **+1,711 ± 121** | −4,118 ± 280 | −23,943 ± 555 |
| Tf | pass the tests, wrong | **+3,045 ± 146** | −1,949 ± 217 | −22,559 ± 500 | −2,134 ± 211 | −8,625 ± 327 | −25,551 ± 546 |
| L, long con | the tests fail them | −3,165 ± 383 | −4,657 ± 330 | −5,532 ± 232 | **+3,383 ± 700** | +128 ± 378 | −1,386 ± 265 |
| L | pass the tests, wrong | **+1,715 ± 610** | −1,624 ± 339 | −3,535 ± 219 | **+3,047 ± 635** | −25 ± 434 | −1,965 ± 249 |
| RS, reputation sale | the tests fail them | +68 ± 157 | −13 ± 118 | −111 ± 122 | **+237 ± 231** | +75 ± 191 | −27 ± 170 |
| RS | pass the tests, wrong | **+267 ± 206** | +82 ± 159 | −93 ± 113 | **+505 ± 272** | +31 ± 217 | −24 ± 201 |

(The farmer is −$1,178 ± 168 and −$1,237 ± 167 against its twin in R+F; it is unaffected by the reversal rule, being outside the cap.)

- **With 3 and with 10 active honest solvers, every attacker is at or below its twin,** for both seats and both kinds of bad fix (8 conditions × 6 attackers), as with the reset rule.
- **With 1 active honest solver it does not hold:** 6 of 12 attacker-cells are above their twins with Opus 5.5 (all on fixes that pass the tests) and 9 of 12 with GPT-6.1. The largest gains: the retrier, +$3,870 ± 364 (Opus 5.5, fixes that pass the tests), and the long con, +$3,383 ± 700 (GPT-6.1). The long con gains more than under the reset rule (+$1,670), as expected: a reversal no longer sends it back to $50.
- **What it costs an honest solver** (post hoc): a newcomer may claim a median bounty after 0.6–0.9 weeks; 1.6–3.5 % of the issues it wanted are turned away (2.3–4.8 % of their value); it loses $58–112 a year with Opus 5.5 and nothing measurable with GPT-6.1 (+$28 to +$172 ± 213–233); an established solver loses nothing.
- **Code health** is the reset rule's within rounding where the solver of bad fixes leaves (it leaves in the same cells), so the R+F row of section 5 stands: 59.8 fixed / 1.2 wrong / 38.9 unfixed per 100 with Opus 5.5 and 3 solvers.

**The hole that still needs a deposit** (post hoc rows, 1 active honest solver, `SOLVER_DEPOSIT_BPS` added to R(minus)+F):

| Attacker above its twin with no deposit | No deposit | Deposit 500 | 1,000 | 2,500 |
|---|---|---|---|---|
| T, Opus 5.5, pass the tests, wrong | **+3,870 ± 364** | **+3,295 ± 364** | **+2,541 ± 368** | −2,056 ± 697 |
| L, GPT-6.1, the tests fail them | **+3,383 ± 700** | **+2,294 ± 658** | **+1,205 ± 619** | −2,061 ± 527 |
| L, GPT-6.1, pass the tests, wrong | **+3,047 ± 635** | **+799 ± 615** | −1,450 ± 615 | −8,195 ± 722 |
| Tf, Opus 5.5, pass the tests, wrong | **+3,045 ± 146** | **+2,378 ± 155** | **+1,461 ± 185** | −4,715 ± 750 |
| T, GPT-6.1, pass the tests, wrong | **+2,444 ± 912** | **+932 ± 776** | −2,162 ± 585 | −51,586 ± 9,123 |
| T, GPT-6.1, the tests fail them | **+1,938 ± 220** | **+1,306 ± 229** | **+423 ± 256** | −6,006 ± 815 |
| L, Opus 5.5, pass the tests, wrong | **+1,715 ± 610** | +301 ± 564 | −1,114 ± 526 | −5,357 ± 474 |
| Tf, GPT-6.1, the tests fail them | **+1,711 ± 121** | **+810 ± 145** | −562 ± 203 | −12,155 ± 1,136 |
| B, Opus 5.5, pass the tests, wrong | **+1,514 ± 212** | **+1,009 ± 199** | **+505 ± 187** | −1,008 ± 156 |
| S, Opus 5.5, pass the tests, wrong | **+1,086 ± 103** | **+620 ± 106** | **+153 ± 109** | −1,246 ± 127 |
| B, GPT-6.1, the tests fail them | **+926 ± 172** | **+436 ± 167** | −55 ± 163 | −1,527 ± 158 |
| S, GPT-6.1, the tests fail them | **+722 ± 101** | **+237 ± 103** | −248 ± 106 | −1,702 ± 123 |
| B, GPT-6.1, pass the tests, wrong | **+647 ± 227** | −81 ± 198 | −808 ± 174 | −2,991 ± 167 |
| RS, GPT-6.1, pass the tests, wrong | **+505 ± 272** | **+301 ± 256** | +97 ± 255 | −515 ± 331 |
| RS, Opus 5.5, pass the tests, wrong | **+267 ± 206** | **+211 ± 197** | +156 ± 189 | −10 ± 173 |
| RS, GPT-6.1, the tests fail them | **+237 ± 231** | +191 ± 239 | +145 ± 248 | +8 ± 280 |

- **Plainly:** with one active honest solver, the cap and the fee leave gains of $237 to $3,870 a year per attacker, and **only a deposit of about 2,500 (25 % of the bounty) closes all of them** in these rows; 1,000 leaves six above their twins.
- **With 3 or more active honest solvers finding a test 1 time in 4, no deposit is needed** in this simulation.
- **With a find rate of 10 %** (section 5, reset rule), R+F fails with 3 solvers too; the deposit rows were not run there.
- **The owner's choice, as the simulation frames it:** either accept that a repository with a single active honest solver is open to gains of up to about $3,900 a year per attacker, or keep a deposit for that case, for example one that applies only while fewer than three solvers have worked a repository in the last window. That conditional deposit is **not simulated**.

## 7. What this does not show
- **The active honest solvers' find rate and number are assumed,** and the result turns on them: R+F holds from 3 solvers at 25 %, not at 10 %. Measuring them needs real repositories with several solvers, or model calls that write tests for others' fixes (paid; v4's task 10.3).
- **Rivals' wrong tests are not modelled.** With the cap, an accepted wrong test also costs an honest solver reputation.
- **Identities are free in the model.** The cap works by what a fresh identity may claim, not by identities being scarce.
- **Attackers pick from what is listed** (30 issues a week), and their issues add to the funding; the supply of small issues is not limited.
- **No appeal (D24), sponsors (D25) or known-answer issues (D26)** are on in these rows; v4 measured them on the same base.
- **The pot's honest solvers decide on the network's averages** (pass rate, unit value so far), not on their own fix.
- **#247's correlation, the cost of inflating, and "true impact = the bounty" are assumed.**
- **The conditional deposit of section 6 is not simulated.**
- **One family seated, 28 validators, one benchmark, seeds 1–40;** each kind of bad fix run on its own.

## 8. For the owner
| Mechanism | Recommendation | The number that decides it |
|---|---|---|
| R, reputation before large claims | **adopt, with F only**: base $50, ×1, a reversal takes 2 × its bounty off (not a reset) | R+F: every attacker at or below its twin with 3 and 10 active honest solvers at 25 %; the newcomer's cost $58–112 a year with "minus" against $637–773 with the reset |
| F, the judges' fee | **adopt** at the measured cost ($5.03 a submission today), re-measured as the network grows | alone, stopping the solver of bad fixes with 1 solver would need $8.71–62.54 |
| P, the pot by impact | **not now**: wait for #247's measured correlation and inflating cost | inflater +$13,600–15,000 a year at $20 a fix; farmer +$6,575 at 0.6 |
| The deposit (D22) | **still the owner's call, on a narrower question:** R+F needs none with 3 or more active honest solvers at 25 %; with one, only about 2,500 closes every gap in these rows | gains of $237–3,870 a year per attacker with one active solver and no deposit |

## Appendix: the full output
Seeds 1–40; every ± is two standard errors of the mean. Tables in the module's order (`--render`), from one run of each table.

### The judges' cost, and `JUDGE_FEE`

| Seated | Bad fixes | Checks paid a submission | Break-even service fee a check | Market fee (floor) | Judges' cost a submission (fee + usage $0.13) | Charged a submission now |
|---|---|---|---|---|---|---|
| Opus 5.5 | the tests fail them | 7.44 | $0.530 | $0.010 | $4.91 | $1.55 |
| GPT-6.1 | the tests fail them | 7.74 | $0.530 | $0.010 | $5.11 | $0.96 |
| Opus 5.5 | pass the tests, wrong | 7.89 | $0.530 | $0.010 | $5.21 | $1.55 |
| GPT-6.1 | pass the tests, wrong | 7.39 | $0.530 | $0.010 | $4.88 | $0.96 |

`JUDGE_FEE` = **$5.03** a submission (the mean of the four), plus the attempt fee of $0.50 as before.

### Does every attacker earn at or below its twin? (both kinds of bad fix; 25 % find rate)

| Combination | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|
| none | no: B, S, T (up to +23,958) | no: B, S, T (up to +19,230) | no: S (up to +703) | no: B, S, T (up to +23,740) | no: B, S, T (up to +18,132) | no: S (up to +675) |
| R | no: B, S, T, Tf, RS (up to +6,681) | no: B, S, T, Tf (up to +3,056) | holds | no: B, S, T, Tf, L, RS (up to +6,679) | no: B, S, T, Tf (up to +2,732) | holds |
| P | no: B, S, T, F, SF, I (up to +26,467) | no: B, S, T, F, SF, I (up to +18,138) | no: S, F, SF, I (up to +15,022) | no: B, S, T, F, SF, I (up to +33,788) | no: B, S, T, F, SF, I (up to +20,955) | no: B, S, F, SF, I (up to +14,261) |
| F | no: B, S, T (up to +20,267) | no: B, S, T (up to +14,152) | holds | no: B, S, T (up to +18,691) | no: B, S, T (up to +11,130) | holds |
| R+P | no: S, Tf, F, SF, I (up to +14,864) | no: S, Tf, F, SF, I (up to +14,946) | no: F, SF, I (up to +15,022) | no: B, S, Tf, F, SF, I (up to +15,629) | no: S, Tf, F, SF, I (up to +13,974) | no: F, SF, I (up to +14,261) |
| R+F | no: B, S, T, Tf, RS (up to +3,045) | holds | holds | no: B, S, T, Tf, L, RS (up to +1,711) | holds | holds |
| P+F | no: B, S, T, F, SF, I (up to +22,647) | no: B, S, T, F, SF, I (up to +14,943) | no: F, SF, I (up to +15,019) | no: B, S, T, F, SF, I (up to +27,108) | no: B, S, T, F, SF, I (up to +13,971) | no: F, SF, I (up to +14,259) |
| R+P+F | no: S, Tf, F, SF, I (up to +14,861) | no: S, Tf, F, SF, I (up to +14,943) | no: F, SF, I (up to +15,019) | no: S, Tf, F, SF, I (up to +13,783) | no: S, Tf, F, SF, I (up to +13,971) | no: F, SF, I (up to +14,259) |

### Combination none: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+1,820 ± 196** | **+787 ± 144** | -374 ± 44 | **+4,332 ± 254** | **+2,176 ± 180** | -63 ± 80 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+5,025 ± 292** | **+2,648 ± 209** | -115 ± 77 | **+2,617 ± 186** | **+1,401 ± 164** | -165 ± 53 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+6,455 ± 592** | **+3,342 ± 436** | -28 ± 130 | **+13,423 ± 768** | **+7,420 ± 594** | **+675 ± 236** |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+15,663 ± 819** | **+8,861 ± 546** | **+703 ± 205** | **+8,458 ± 521** | **+4,985 ± 370** | **+246 ± 144** |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+16,040 ± 458** | **+7,117 ± 448** | -13,804 ± 490 | **+23,740 ± 556** | **+18,132 ± 474** | -7,148 ± 394 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+23,958 ± 585** | **+19,230 ± 514** | -8,143 ± 420 | **+20,391 ± 535** | **+13,046 ± 492** | -9,476 ± 398 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | -527 ± 175 | -527 ± 175 | -527 ± 175 | -474 ± 168 | -474 ± 168 | -474 ± 168 |

### Combination R: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+586 ± 127** | +5 ± 57 | -398 ± 15 | **+1,744 ± 164** | **+612 ± 84** | -229 ± 22 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+1,958 ± 146** | **+685 ± 78** | -320 ± 27 | **+1,210 ± 135** | **+367 ± 54** | -259 ± 18 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+523 ± 79** | +38 ± 56 | -472 ± 19 | **+1,742 ± 110** | **+797 ± 78** | -242 ± 28 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+1,956 ± 109** | **+899 ± 73** | -352 ± 33 | **+982 ± 70** | **+429 ± 51** | -296 ± 24 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+1,157 ± 154** | -157 ± 89 | -1,086 ± 34 | **+4,031 ± 206** | **+1,272 ± 132** | -648 ± 37 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+5,094 ± 269** | **+1,621 ± 120** | -930 ± 46 | **+3,123 ± 284** | **+747 ± 107** | -724 ± 34 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | **+871 ± 268** | -4,693 ± 348 | -16,077 ± 410 | **+6,679 ± 148** | **+2,732 ± 199** | -11,315 ± 298 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+6,681 ± 174** | **+3,056 ± 206** | -13,060 ± 334 | **+4,198 ± 179** | -451 ± 213 | -12,481 ± 313 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -2,723 ± 339 | -4,027 ± 273 | -4,867 ± 268 | **+1,636 ± 444** | -209 ± 290 | -1,296 ± 203 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -95 ± 431 | -1,986 ± 289 | -3,371 ± 222 | **+1,351 ± 452** | -406 ± 304 | -1,722 ± 230 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | +52 ± 187 | -20 ± 156 | -97 ± 141 | **+289 ± 227** | +125 ± 165 | +98 ± 158 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | **+252 ± 197** | +67 ± 155 | -129 ± 117 | **+611 ± 297** | +118 ± 237 | +17 ± 216 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | -527 ± 175 | -527 ± 175 | -527 ± 175 | -474 ± 168 | -474 ± 168 | -474 ± 168 |

### Combination P: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+3,279 ± 344** | **+1,554 ± 238** | -269 ± 73 | **+8,197 ± 478** | **+4,364 ± 328** | **+217 ± 153** |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+7,151 ± 390** | **+3,920 ± 307** | +39 ± 109 | **+5,829 ± 402** | **+3,354 ± 353** | +93 ± 124 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+6,630 ± 676** | **+3,383 ± 468** | -30 ± 139 | **+15,079 ± 910** | **+8,392 ± 648** | **+771 ± 276** |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+13,499 ± 736** | **+7,646 ± 527** | **+508 ± 182** | **+11,228 ± 726** | **+6,666 ± 584** | **+453 ± 207** |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+21,252 ± 575** | **+9,524 ± 512** | -13,856 ± 515 | **+31,863 ± 539** | **+20,866 ± 442** | -8,704 ± 409 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+26,467 ± 565** | **+18,138 ± 380** | -10,870 ± 398 | **+33,788 ± 697** | **+20,955 ± 512** | -8,865 ± 442 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | **+6,555 ± 414** | **+6,575 ± 415** | **+6,592 ± 419** | **+5,873 ± 469** | **+5,922 ± 474** | **+5,979 ± 479** |
| farmer filing its own issues, unfunded (twin: typical issues, same effort) | (good fixes) | **+5,286 ± 409** | **+5,316 ± 413** | **+5,335 ± 415** | **+4,725 ± 463** | **+4,789 ± 466** | **+4,883 ± 473** |
| inflater, +1 SD of signal at $20 a fix (twin: does not inflate) | (good fixes) | **+14,864 ± 286** | **+14,946 ± 290** | **+15,022 ± 301** | **+13,786 ± 299** | **+13,974 ± 313** | **+14,261 ± 328** |

### Combination F: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+946 ± 186** | -87 ± 134 | -1,248 ± 46 | **+3,308 ± 245** | **+1,152 ± 170** | -1,086 ± 77 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+4,151 ± 284** | **+1,776 ± 205** | -987 ± 74 | **+1,593 ± 184** | **+376 ± 166** | -1,189 ± 55 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+5,580 ± 580** | **+2,467 ± 426** | -903 ± 125 | **+12,399 ± 755** | **+6,396 ± 581** | -349 ± 227 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+14,789 ± 809** | **+7,987 ± 540** | -170 ± 200 | **+7,433 ± 516** | **+3,960 ± 366** | -779 ± 142 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+10,211 ± 433** | -158 ± 521 | -24,261 ± 669 | **+18,691 ± 489** | **+11,130 ± 406** | -19,785 ± 614 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+20,267 ± 546** | **+14,152 ± 500** | -17,706 ± 540 | **+13,947 ± 510** | **+4,764 ± 497** | -22,557 ± 576 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | -1,178 ± 168 | -1,178 ± 168 | -1,178 ± 168 | -1,237 ± 167 | -1,237 ± 167 | -1,237 ± 167 |

### Combination R+P: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | -94 ± 61 | -221 ± 18 | -390 ± 14 | +15 ± 46 | -88 ± 17 | -219 ± 20 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | -149 ± 39 | -197 ± 27 | -336 ± 18 | **+210 ± 78** | -21 ± 38 | -245 ± 17 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+1,351 ± 156** | **+488 ± 107** | -405 ± 32 | **+3,599 ± 206** | **+1,838 ± 147** | -103 ± 55 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+3,628 ± 192** | **+1,881 ± 133** | -214 ± 58 | **+2,257 ± 139** | **+1,198 ± 102** | -197 ± 44 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -1,147 ± 37 | -1,024 ± 25 | -1,083 ± 28 | -689 ± 36 | -683 ± 20 | -726 ± 22 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | -1,050 ± 42 | -1,000 ± 28 | -1,049 ± 29 | -773 ± 68 | -732 ± 28 | -730 ± 24 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | **+7,858 ± 325** | +311 ± 387 | -15,239 ± 429 | **+15,629 ± 287** | **+9,906 ± 240** | -10,199 ± 340 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+13,601 ± 300** | **+8,631 ± 259** | -12,272 ± 365 | **+13,727 ± 321** | **+7,004 ± 255** | -11,091 ± 339 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -2,215 ± 1,762 | -3,529 ± 1,729 | -4,357 ± 1,716 | -6,177 ± 2,054 | -7,099 ± 2,051 | -7,547 ± 2,099 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -4,661 ± 1,547 | -5,435 ± 1,603 | -6,241 ± 1,634 | -3,652 ± 2,263 | -5,300 ± 2,247 | -6,636 ± 2,221 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | -498 ± 1,172 | -139 ± 1,207 | -50 ± 925 | -848 ± 954 | -973 ± 882 | -1,158 ± 856 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | -70 ± 1,023 | -334 ± 985 | -279 ± 763 | -2,390 ± 1,580 | -1,439 ± 1,278 | -1,162 ± 992 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | **+6,555 ± 414** | **+6,575 ± 415** | **+6,592 ± 419** | **+5,873 ± 469** | **+5,922 ± 474** | **+5,979 ± 479** |
| farmer filing its own issues, unfunded (twin: typical issues, same effort) | (good fixes) | **+5,286 ± 409** | **+5,316 ± 413** | **+5,335 ± 415** | **+4,725 ± 463** | **+4,789 ± 466** | **+4,883 ± 473** |
| inflater, +1 SD of signal at $20 a fix (twin: does not inflate) | (good fixes) | **+14,864 ± 286** | **+14,946 ± 290** | **+15,022 ± 301** | **+13,786 ± 299** | **+13,974 ± 313** | **+14,261 ± 328** |

### Combination R+F: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | -176 ± 119 | -736 ± 49 | -1,120 ± 24 | **+849 ± 157** | -259 ± 75 | -1,089 ± 27 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+1,196 ± 141** | -61 ± 77 | -1,052 ± 33 | **+296 ± 135** | -512 ± 56 | -1,107 ± 28 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | -348 ± 71 | -833 ± 50 | -1,342 ± 30 | **+722 ± 101** | -224 ± 69 | -1,261 ± 32 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+1,086 ± 103** | +30 ± 74 | -1,222 ± 40 | -39 ± 73 | -592 ± 59 | -1,316 ± 37 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -980 ± 141 | -2,049 ± 88 | -2,934 ± 64 | **+1,628 ± 196** | -952 ± 128 | -2,823 ± 63 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+3,036 ± 255** | -279 ± 119 | -2,778 ± 70 | **+348 ± 239** | -1,599 ± 90 | -2,871 ± 68 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | -4,810 ± 327 | -11,839 ± 470 | -26,488 ± 603 | **+1,711 ± 121** | -4,118 ± 280 | -23,943 ± 555 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+3,045 ± 146** | -1,949 ± 217 | -22,559 ± 500 | -2,134 ± 211 | -8,625 ± 327 | -25,551 ± 546 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -2,707 ± 338 | -4,007 ± 272 | -4,843 ± 268 | **+1,670 ± 444** | -172 ± 289 | -1,257 ± 202 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -69 ± 430 | -1,957 ± 288 | -3,337 ± 220 | **+1,373 ± 452** | -373 ± 302 | -1,684 ± 228 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | +30 ± 182 | -36 ± 155 | -109 ± 141 | **+280 ± 227** | +118 ± 164 | +94 ± 157 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | **+242 ± 195** | +59 ± 154 | -134 ± 117 | **+568 ± 291** | +99 ± 237 | +7 ± 216 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | -1,178 ± 168 | -1,178 ± 168 | -1,178 ± 168 | -1,237 ± 167 | -1,237 ± 167 | -1,237 ± 167 |

### Combination P+F: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+2,402 ± 332** | **+676 ± 227** | -1,147 ± 69 | **+7,167 ± 468** | **+3,334 ± 316** | -814 ± 147 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+6,272 ± 382** | **+3,041 ± 303** | -840 ± 109 | **+4,800 ± 400** | **+2,325 ± 353** | -936 ± 123 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+5,751 ± 664** | **+2,505 ± 457** | -909 ± 133 | **+14,047 ± 899** | **+7,359 ± 635** | -261 ± 269 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+12,619 ± 727** | **+6,766 ± 521** | -373 ± 181 | **+10,198 ± 723** | **+5,636 ± 581** | -578 ± 205 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+15,196 ± 562** | **+2,055 ± 580** | -24,349 ± 685 | **+26,580 ± 492** | **+13,349 ± 477** | -21,361 ± 653 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+22,647 ± 530** | **+12,648 ± 385** | -20,433 ± 552 | **+27,108 ± 664** | **+12,409 ± 546** | -22,008 ± 606 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | **+5,898 ± 407** | **+5,917 ± 408** | **+5,934 ± 412** | **+5,101 ± 462** | **+5,150 ± 466** | **+5,206 ± 472** |
| farmer filing its own issues, unfunded (twin: typical issues, same effort) | (good fixes) | **+4,627 ± 403** | **+4,657 ± 407** | **+4,675 ± 409** | **+3,952 ± 457** | **+4,015 ± 460** | **+4,108 ± 467** |
| inflater, +1 SD of signal at $20 a fix (twin: does not inflate) | (good fixes) | **+14,861 ± 286** | **+14,943 ± 290** | **+15,019 ± 301** | **+13,783 ± 299** | **+13,971 ± 313** | **+14,259 ± 328** |

### Combination R+P+F: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | -859 ± 61 | -964 ± 24 | -1,115 ± 23 | -884 ± 50 | -965 ± 30 | -1,084 ± 26 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | -914 ± 50 | -947 ± 39 | -1,073 ± 27 | -707 ± 87 | -903 ± 44 | -1,097 ± 27 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+477 ± 145** | -386 ± 99 | -1,279 ± 37 | **+2,574 ± 195** | **+812 ± 136** | -1,129 ± 52 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+2,754 ± 185** | **+1,006 ± 131** | -1,089 ± 61 | **+1,233 ± 139** | **+173 ± 106** | -1,222 ± 51 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -3,304 ± 69 | -2,942 ± 52 | -2,946 ± 62 | -3,122 ± 61 | -2,920 ± 54 | -2,930 ± 56 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | -3,140 ± 63 | -2,933 ± 43 | -2,930 ± 61 | -3,575 ± 98 | -3,097 ± 60 | -2,895 ± 64 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | **+2,020 ± 354** | -6,930 ± 483 | -25,660 ± 613 | **+10,472 ± 223** | **+2,717 ± 288** | -22,854 ± 604 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+9,853 ± 261** | **+3,376 ± 249** | -21,773 ± 525 | **+7,237 ± 301** | -1,306 ± 330 | -24,182 ± 557 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -2,198 ± 1,762 | -3,508 ± 1,729 | -4,332 ± 1,716 | -6,142 ± 2,053 | -7,061 ± 2,050 | -7,507 ± 2,097 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -4,634 ± 1,547 | -5,405 ± 1,603 | -6,208 ± 1,633 | -3,629 ± 2,262 | -5,266 ± 2,246 | -6,597 ± 2,219 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | -520 ± 1,172 | -156 ± 1,207 | -62 ± 925 | -858 ± 955 | -980 ± 882 | -1,163 ± 857 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | -80 ± 1,022 | -342 ± 986 | -284 ± 762 | -2,434 ± 1,585 | -1,458 ± 1,278 | -1,173 ± 993 |
| farmer of the cheapest fifth (twin: typical issues, same effort) | (good fixes) | **+5,898 ± 407** | **+5,917 ± 408** | **+5,934 ± 412** | **+5,101 ± 462** | **+5,150 ± 466** | **+5,206 ± 472** |
| farmer filing its own issues, unfunded (twin: typical issues, same effort) | (good fixes) | **+4,627 ± 403** | **+4,657 ± 407** | **+4,675 ± 409** | **+3,952 ± 457** | **+4,015 ± 460** | **+4,108 ± 467** |
| inflater, +1 SD of signal at $20 a fix (twin: does not inflate) | (good fixes) | **+14,861 ± 286** | **+14,943 ± 290** | **+15,019 ± 301** | **+13,783 ± 299** | **+13,971 ± 313** | **+14,259 ± 328** |

### Code health (E2): correctly fixed / wrongly marked fixed / left unfixed, per 100 funded issues

| Combination | Seated | 1 solver: the tests fail them | 3 solvers: the tests fail them | 10 solvers: the tests fail them | 1 solver: pass the tests, wrong | 3 solvers: pass the tests, wrong | 10 solvers: pass the tests, wrong |
|---|---|---|---|---|---|---|---|
| none | Opus 5.5 | 58.5 / 3.3 / 38.1 | 58.5 / 1.9 / 39.6 | 58.5 / 0.2 / 41.3 (left) | 58.5 / 7.6 / 33.9 | 58.5 / 4.3 / 37.2 | 58.5 / 0.3 / 41.1 (left) |
| none | GPT-6.1 | 43.9 / 6.3 / 49.7 | 43.9 / 3.6 / 52.5 | 43.9 / 0.3 / 55.8 (left) | 43.9 / 4.1 / 51.9 | 43.9 / 2.4 / 53.7 | 43.9 / 0.2 / 55.9 (left) |
| R | Opus 5.5 | 59.6 / 3.2 / 37.2 | 59.8 / 1.8 / 38.3 | 60.0 / 0.2 / 39.8 (left) | 59.6 / 7.4 / 33.0 | 59.8 / 4.1 / 36.1 | 59.9 / 0.4 / 39.7 (left) |
| R | GPT-6.1 | 44.7 / 6.1 / 49.1 | 44.9 / 3.4 / 51.7 | 44.9 / 0.3 / 54.8 (left) | 44.6 / 4.0 / 51.4 | 44.8 / 2.2 / 52.9 | 45.0 / 0.2 / 54.8 (left) |
| P | Opus 5.5 | 54.7 / 3.2 / 42.1 | 54.5 / 1.8 / 43.7 | 54.8 / 0.2 / 45.0 (left) | 53.5 / 7.2 / 39.3 | 52.9 / 4.1 / 43.0 | 52.4 / 0.5 / 47.1 |
| P | GPT-6.1 | 39.8 / 6.0 / 54.2 | 39.4 / 3.4 / 57.3 | 38.8 / 0.4 / 60.7 | 41.0 / 4.0 / 55.1 | 40.7 / 2.3 / 57.0 | 40.5 / 0.3 / 59.2 |
| F | Opus 5.5 | 58.5 / 3.3 / 38.1 | 58.5 / 1.2 / 40.3 (left) | 58.5 / 0.2 / 41.3 (left) | 58.5 / 7.6 / 33.9 | 58.5 / 4.3 / 37.2 | 58.5 / 0.3 / 41.1 (left) |
| F | GPT-6.1 | 43.9 / 6.3 / 49.7 | 43.9 / 3.6 / 52.5 | 43.9 / 0.3 / 55.8 (left) | 43.9 / 4.1 / 51.9 | 43.9 / 2.4 / 53.7 | 43.9 / 0.2 / 55.9 (left) |
| R+P | Opus 5.5 | 56.3 / 2.0 / 41.7 (left) | 56.3 / 1.2 / 42.6 (left) | 56.2 / 0.2 / 43.6 (left) | 55.7 / 4.4 / 39.9 (left) | 55.5 / 2.4 / 42.1 (left) | 55.1 / 0.3 / 44.6 (left) |
| R+P | GPT-6.1 | 41.1 / 5.8 / 53.1 | 41.5 / 2.0 / 56.5 (left) | 41.2 / 0.3 / 58.6 (left) | 41.8 / 3.9 / 54.3 | 42.1 / 1.3 / 56.5 (left) | 42.1 / 0.2 / 57.7 (left) |
| R+F | Opus 5.5 | 59.6 / 2.1 / 38.3 (left) | 59.8 / 1.2 / 38.9 (left) | 60.0 / 0.2 / 39.8 (left) | 59.6 / 7.4 / 33.0 | 59.8 / 2.6 / 37.6 (left) | 59.9 / 0.4 / 39.7 (left) |
| R+F | GPT-6.1 | 44.7 / 6.1 / 49.1 | 44.9 / 2.2 / 52.9 (left) | 44.9 / 0.3 / 54.8 (left) | 44.6 / 4.0 / 51.4 | 44.8 / 1.4 / 53.8 (left) | 45.0 / 0.2 / 54.8 (left) |
| P+F | Opus 5.5 | 54.7 / 3.2 / 42.1 | 54.5 / 1.8 / 43.7 | 54.8 / 0.2 / 45.0 (left) | 53.5 / 7.2 / 39.3 | 52.9 / 4.1 / 43.0 | 53.8 / 0.3 / 45.9 (left) |
| P+F | GPT-6.1 | 39.8 / 6.0 / 54.2 | 39.4 / 3.4 / 57.3 | 40.2 / 0.3 / 59.5 (left) | 41.0 / 4.0 / 55.1 | 40.7 / 2.3 / 57.0 | 41.0 / 0.2 / 58.8 (left) |
| R+P+F | Opus 5.5 | 56.3 / 2.0 / 41.7 (left) | 56.3 / 1.2 / 42.6 (left) | 56.2 / 0.2 / 43.6 (left) | 55.7 / 4.4 / 39.9 (left) | 55.5 / 2.4 / 42.1 (left) | 55.1 / 0.3 / 44.6 (left) |
| R+P+F | GPT-6.1 | 41.7 / 3.6 / 54.7 (left) | 41.5 / 2.0 / 56.5 (left) | 41.2 / 0.3 / 58.6 (left) | 42.1 / 2.4 / 55.5 (left) | 42.1 / 1.3 / 56.5 (left) | 42.1 / 0.2 / 57.7 (left) |

### The judges' fee against the solver of bad fixes and the retrier (no cap, no pot)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+1,820 ± 196** → **+946 ± 186**; zero at $8.71 | **+787 ± 144** → -87 ± 134; zero at $4.69 | -374 ± 44 → -1,248 ± 46; zero at $0.18 | **+4,332 ± 254** → **+3,308 ± 245**; zero at $17.89 | **+2,176 ± 180** → **+1,152 ± 170**; zero at $9.51 | -63 ± 80 → -1,086 ± 77; zero at $0.81 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+5,025 ± 292** → **+4,151 ± 284**; zero at $21.17 | **+2,648 ± 209** → **+1,776 ± 205**; zero at $11.93 | -115 ± 77 → -987 ± 74; zero at $1.19 | **+2,617 ± 186** → **+1,593 ± 184**; zero at $11.22 | **+1,401 ± 164** → **+376 ± 166**; zero at $6.49 | -165 ± 53 → -1,189 ± 55; zero at $0.41 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+6,455 ± 592** → **+5,580 ± 580**; zero at $26.73 | **+3,342 ± 436** → **+2,467 ± 426**; zero at $14.62 | -28 ± 130 → -903 ± 125; zero at $1.52 | **+13,423 ± 768** → **+12,399 ± 755**; zero at $53.24 | **+7,420 ± 594** → **+6,396 ± 581**; zero at $29.90 | **+675 ± 236** → -349 ± 227; zero at $3.67 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+15,663 ± 819** → **+14,789 ± 809**; zero at $62.54 | **+8,861 ± 546** → **+7,987 ± 540**; zero at $36.09 | **+703 ± 205** → -170 ± 200; zero at $4.37 | **+8,458 ± 521** → **+7,433 ± 516**; zero at $33.93 | **+4,985 ± 370** → **+3,960 ± 366**; zero at $20.43 | **+246 ± 144** → -779 ± 142; zero at $2.00 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+16,040 ± 458** → **+10,211 ± 433**; zero at $9.29 | **+7,117 ± 448** → -158 ± 521; zero at $4.98 | -13,804 ± 490 → -24,261 ± 669; zero at $0.21 | **+23,740 ± 556** → **+18,691 ± 489**; zero at $18.16 | **+18,132 ± 474** → **+11,130 ± 406**; zero at $9.84 | -7,148 ± 394 → -19,785 ± 614; zero at $0.86 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+23,958 ± 585** → **+20,267 ± 546**; zero at $21.85 | **+19,230 ± 514** → **+14,152 ± 500**; zero at $12.14 | -8,143 ± 420 → -17,706 ± 540; zero at $1.19 | **+20,391 ± 535** → **+13,947 ± 510**; zero at $11.93 | **+13,046 ± 492** → **+4,764 ± 497**; zero at $6.66 | -9,476 ± 398 → -22,557 ± 576; zero at $0.45 |

### What an active honest solver earns a search of a pass, gross (it costs $0.50, assumed)

| Combination | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| none | the tests fail them | $0.18 | $0.13 | $0.06 | $0.37 | $0.28 | $0.14 |
| none | pass the tests, wrong | $0.36 | $0.27 | $0.13 | $0.31 | $0.22 | $0.11 |
| P | the tests fail them | $2.90 | $2.17 | $1.07 | $6.97 | $5.40 | $2.68 |
| P | pass the tests, wrong | $5.24 | $3.93 | $1.94 | $6.32 | $4.60 | $2.25 |

### The honest solver: its year, and what the cap costs a newcomer and an established solver

| Combination | Seated | Solvers | An honest solver's year with no cap ($) | Newcomer: cost of the cap ($ a year) | …runs in which it may claim a median bounty ($86) | …week it first may | …week it first may claim $184 (p90) | Issues it wanted, turned away | …their share of the value | Its resets a year | Established (5,000): cost of the cap ($ a year) | …its resets a year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | Opus 5.5 | 1 | 4,977 ± 290 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| none | Opus 5.5 | 3 | 4,706 ± 284 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| none | Opus 5.5 | 10 | 4,383 ± 270 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| none | GPT-6.1 | 1 | 1,105 ± 285 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| none | GPT-6.1 | 3 | 593 ± 287 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| none | GPT-6.1 | 10 | 41 ± 283 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| R | Opus 5.5 | 1 | 4,977 ± 290 | -637 ± 201 | 100 ± 0 % | 0.6 ± 0.1 | 1.3 ± 0.2 | 12.7 % | 17.3 % | 10.6 ± 1.0 | -519 ± 190 | 10.5 ± 0.9 |
| R | Opus 5.5 | 3 | 4,706 ± 284 | -658 ± 184 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 15.5 % | 21.2 % | 13.8 ± 1.2 | -587 ± 205 | 13.5 ± 1.2 |
| R | Opus 5.5 | 10 | 4,383 ± 270 | -773 ± 179 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 17.6 % | 23.6 % | 16.3 ± 1.1 | -756 ± 190 | 16.2 ± 1.2 |
| R | GPT-6.1 | 1 | 1,105 ± 285 | -269 ± 309 | 100 ± 0 % | 0.8 ± 0.2 | 1.5 ± 0.2 | 21.5 % | 28.3 % | 16.5 ± 1.1 | -233 ± 295 | 16.5 ± 1.1 |
| R | GPT-6.1 | 3 | 593 ± 287 | -229 ± 260 | 100 ± 0 % | 0.9 ± 0.2 | 1.8 ± 0.3 | 25.9 % | 33.6 % | 20.8 ± 1.2 | -235 ± 253 | 20.8 ± 1.3 |
| R | GPT-6.1 | 10 | 41 ± 283 | -178 ± 270 | 100 ± 0 % | 0.9 ± 0.2 | 1.9 ± 0.3 | 31.6 % | 40.9 % | 26.7 ± 1.4 | -158 ± 284 | 26.1 ± 1.3 |
| P | Opus 5.5 | 1 | 12,560 ± 466 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P | Opus 5.5 | 3 | 12,244 ± 450 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P | Opus 5.5 | 10 | 11,899 ± 442 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P | GPT-6.1 | 1 | 11,535 ± 573 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P | GPT-6.1 | 3 | 10,793 ± 566 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P | GPT-6.1 | 10 | 10,021 ± 501 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| F | Opus 5.5 | 1 | 4,088 ± 288 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| F | Opus 5.5 | 3 | 3,817 ± 282 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| F | Opus 5.5 | 10 | 3,494 ± 268 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| F | GPT-6.1 | 1 | 64 ± 284 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| F | GPT-6.1 | 3 | -448 ± 288 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| F | GPT-6.1 | 10 | -1,000 ± 285 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| R+P | Opus 5.5 | 1 | 12,560 ± 466 | -18,322 ± 1,201 | 100 ± 0 % | 0.6 ± 0.1 | 1.3 ± 0.2 | 12.7 % | 17.3 % | 10.6 ± 1.0 | -18,269 ± 1,217 | 10.5 ± 0.9 |
| R+P | Opus 5.5 | 3 | 12,244 ± 450 | -19,032 ± 934 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 15.5 % | 21.2 % | 13.8 ± 1.2 | -19,148 ± 1,007 | 13.5 ± 1.2 |
| R+P | Opus 5.5 | 10 | 11,899 ± 442 | -19,816 ± 803 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 17.6 % | 23.6 % | 16.3 ± 1.1 | -19,730 ± 832 | 16.2 ± 1.2 |
| R+P | GPT-6.1 | 1 | 11,535 ± 573 | -19,540 ± 690 | 100 ± 0 % | 0.8 ± 0.2 | 1.5 ± 0.2 | 21.5 % | 28.3 % | 16.5 ± 1.1 | -19,578 ± 769 | 16.5 ± 1.1 |
| R+P | GPT-6.1 | 3 | 10,793 ± 566 | -18,942 ± 655 | 100 ± 0 % | 0.9 ± 0.2 | 1.8 ± 0.3 | 25.9 % | 33.5 % | 20.8 ± 1.2 | -19,073 ± 687 | 20.8 ± 1.3 |
| R+P | GPT-6.1 | 10 | 10,021 ± 501 | -18,388 ± 623 | 100 ± 0 % | 0.9 ± 0.2 | 1.9 ± 0.3 | 31.7 % | 41.0 % | 26.8 ± 1.4 | -18,573 ± 622 | 26.1 ± 1.3 |
| R+F | Opus 5.5 | 1 | 4,088 ± 288 | -616 ± 200 | 100 ± 0 % | 0.6 ± 0.1 | 1.3 ± 0.2 | 12.7 % | 17.3 % | 10.6 ± 1.0 | -498 ± 190 | 10.5 ± 0.9 |
| R+F | Opus 5.5 | 3 | 3,817 ± 282 | -634 ± 183 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 15.5 % | 21.2 % | 13.8 ± 1.2 | -564 ± 204 | 13.5 ± 1.2 |
| R+F | Opus 5.5 | 10 | 3,494 ± 268 | -740 ± 177 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 17.6 % | 23.6 % | 16.3 ± 1.1 | -725 ± 189 | 16.2 ± 1.2 |
| R+F | GPT-6.1 | 1 | 64 ± 284 | -226 ± 310 | 100 ± 0 % | 0.8 ± 0.2 | 1.5 ± 0.2 | 21.5 % | 28.3 % | 16.5 ± 1.1 | -193 ± 295 | 16.5 ± 1.1 |
| R+F | GPT-6.1 | 3 | -448 ± 288 | -177 ± 261 | 100 ± 0 % | 0.9 ± 0.2 | 1.8 ± 0.3 | 25.9 % | 33.6 % | 20.8 ± 1.2 | -186 ± 254 | 20.8 ± 1.3 |
| R+F | GPT-6.1 | 10 | -1,000 ± 285 | -112 ± 270 | 100 ± 0 % | 0.9 ± 0.2 | 1.9 ± 0.3 | 31.6 % | 40.9 % | 26.7 ± 1.4 | -96 ± 284 | 26.1 ± 1.3 |
| P+F | Opus 5.5 | 1 | 11,667 ± 463 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P+F | Opus 5.5 | 3 | 11,350 ± 447 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P+F | Opus 5.5 | 10 | 11,004 ± 438 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P+F | GPT-6.1 | 1 | 10,487 ± 571 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P+F | GPT-6.1 | 3 | 9,745 ± 564 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| P+F | GPT-6.1 | 10 | 8,972 ± 500 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| R+P+F | Opus 5.5 | 1 | 11,667 ± 463 | -18,300 ± 1,200 | 100 ± 0 % | 0.6 ± 0.1 | 1.3 ± 0.2 | 12.7 % | 17.3 % | 10.6 ± 1.0 | -18,248 ± 1,217 | 10.5 ± 0.9 |
| R+P+F | Opus 5.5 | 3 | 11,350 ± 447 | -19,007 ± 932 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 15.5 % | 21.2 % | 13.8 ± 1.2 | -19,124 ± 1,006 | 13.5 ± 1.2 |
| R+P+F | Opus 5.5 | 10 | 11,004 ± 438 | -19,783 ± 802 | 100 ± 0 % | 0.7 ± 0.1 | 1.3 ± 0.2 | 17.6 % | 23.6 % | 16.3 ± 1.1 | -19,699 ± 830 | 16.2 ± 1.2 |
| R+P+F | GPT-6.1 | 1 | 10,487 ± 571 | -19,495 ± 691 | 100 ± 0 % | 0.8 ± 0.2 | 1.5 ± 0.2 | 21.5 % | 28.3 % | 16.5 ± 1.1 | -19,537 ± 769 | 16.5 ± 1.1 |
| R+P+F | GPT-6.1 | 3 | 9,745 ± 564 | -18,889 ± 656 | 100 ± 0 % | 0.9 ± 0.2 | 1.8 ± 0.3 | 25.9 % | 33.5 % | 20.8 ± 1.2 | -19,024 ± 687 | 20.8 ± 1.3 |
| R+P+F | GPT-6.1 | 10 | 8,972 ± 500 | -18,321 ± 622 | 100 ± 0 % | 0.9 ± 0.2 | 1.9 ± 0.3 | 31.7 % | 41.0 % | 26.8 ± 1.4 | -18,509 ± 621 | 26.1 ± 1.3 |

### The reputation rule's numbers swept (alone; Opus 5.5 or GPT-6.1; 3 solvers; the tests fail them)

| Rule | Seated | Bad fixes, one identity | Free identities | Retrier | Long con | Reputation sale | Newcomer: cost ($ a year) | …week it may claim $86 | …issues turned away | Established: cost |
|---|---|---|---|---|---|---|---|---|---|---|
| base $25, x0.5 | Opus 5.5 | -101 ± 19 | -111 ± 15 | -425 ± 42 | -2,763 ± 310 | -281 ± 211 | -1,894 ± 286 | 2.4 ± 0.3 | 40.5 % | -1,748 ± 296 |
| base $25, x0.5 | GPT-6.1 | **+109 ± 26** | **+87 ± 21** | **+264 ± 53** | -581 ± 286 | -100 ± 213 | -449 ± 269 | 3.7 ± 0.7 | 60.8 % | -440 ± 227 |
| base $25, x1 | Opus 5.5 | -90 ± 24 | -111 ± 15 | -405 ± 49 | -4,029 ± 294 | -183 ± 188 | -1,158 ± 238 | 1.6 ± 0.3 | 27.0 % | -1,191 ± 234 |
| base $25, x1 | GPT-6.1 | **+140 ± 34** | **+87 ± 21** | **+342 ± 63** | -731 ± 236 | -33 ± 196 | -383 ± 278 | 2.0 ± 0.4 | 49.5 % | -390 ± 241 |
| base $25, x2 | Opus 5.5 | -63 ± 34 | -111 ± 15 | -397 ± 68 | -4,929 ± 375 | -261 ± 174 | -892 ± 198 | 1.3 ± 0.2 | 20.2 % | -1,003 ± 189 |
| base $25, x2 | GPT-6.1 | **+190 ± 46** | **+87 ± 21** | **+516 ± 99** | -321 ± 331 | -112 ± 188 | -404 ± 261 | 1.7 ± 0.4 | 39.9 % | -364 ± 261 |
| base $50, x0.5 | Opus 5.5 | -28 ± 45 | +38 ± 56 | -172 ± 89 | -2,811 ± 259 | -50 ± 186 | -1,058 ± 219 | 1.0 ± 0.2 | 22.3 % | -1,076 ± 211 |
| base $50, x0.5 | GPT-6.1 | **+555 ± 73** | **+797 ± 78** | **+1,141 ± 111** | -171 ± 225 | +101 ± 219 | -305 ± 293 | 1.2 ± 0.2 | 36.9 % | -350 ± 271 |
| base $50, x1 | Opus 5.5 | +5 ± 57 | +38 ± 56 | -157 ± 89 | -4,027 ± 273 | -20 ± 156 | -658 ± 184 | 0.7 ± 0.1 | 15.5 % | -587 ± 205 |
| base $50, x1 | GPT-6.1 | **+612 ± 84** | **+797 ± 78** | **+1,272 ± 132** | -209 ± 290 | +125 ± 165 | -229 ± 260 | 0.9 ± 0.2 | 25.9 % | -235 ± 253 |
| base $50, x2 | Opus 5.5 | +50 ± 73 | +38 ± 56 | -83 ± 103 | -4,718 ± 313 | -5 ± 143 | -565 ± 179 | 0.5 ± 0.1 | 10.5 % | -524 ± 182 |
| base $50, x2 | GPT-6.1 | **+700 ± 99** | **+797 ± 78** | **+1,601 ± 144** | +240 ± 336 | +193 ± 204 | -95 ± 270 | 0.7 ± 0.1 | 19.1 % | -150 ± 273 |
| base $100, x0.5 | Opus 5.5 | **+216 ± 87** | **+670 ± 123** | **+413 ± 131** | -2,763 ± 310 | -57 ± 166 | -589 ± 210 | 0.2 ± 0.1 | 10.6 % | -525 ± 194 |
| base $100, x0.5 | GPT-6.1 | **+1,150 ± 116** | **+2,075 ± 169** | **+2,909 ± 174** | -99 ± 212 | +31 ± 192 | -228 ± 237 | 0.2 ± 0.1 | 17.4 % | -182 ± 229 |
| base $100, x1 | Opus 5.5 | **+234 ± 83** | **+670 ± 123** | **+512 ± 177** | -3,803 ± 304 | +59 ± 146 | -395 ± 177 | 0.2 ± 0.1 | 7.3 % | -387 ± 167 |
| base $100, x1 | GPT-6.1 | **+1,215 ± 133** | **+2,075 ± 169** | **+3,139 ± 209** | +236 ± 372 | **+201 ± 200** | -193 ± 241 | 0.2 ± 0.1 | 12.3 % | -178 ± 225 |
| base $100, x2 | Opus 5.5 | **+296 ± 94** | **+670 ± 123** | **+609 ± 187** | -4,824 ± 341 | +31 ± 152 | -319 ± 172 | 0.2 ± 0.1 | 5.4 % | -263 ± 166 |
| base $100, x2 | GPT-6.1 | **+1,231 ± 132** | **+2,075 ± 169** | **+3,602 ± 206** | **+570 ± 305** | **+226 ± 174** | -64 ± 212 | 0.2 ± 0.1 | 9.2 % | -78 ± 177 |
| base $200, x0.5 | Opus 5.5 | **+555 ± 124** | **+1,767 ± 242** | **+1,619 ± 230** | -2,963 ± 281 | +86 ± 134 | -294 ± 146 | 0.2 ± 0.1 | 3.2 % | -270 ± 128 |
| base $200, x0.5 | GPT-6.1 | **+1,808 ± 163** | **+4,286 ± 331** | **+6,155 ± 249** | +243 ± 251 | +135 ± 184 | +72 ± 191 | 0.2 ± 0.1 | 5.3 % | +77 ± 190 |
| base $200, x1 | Opus 5.5 | **+569 ± 113** | **+1,767 ± 242** | **+1,759 ± 240** | -4,084 ± 381 | +94 ± 148 | -177 ± 132 | 0.2 ± 0.1 | 2.3 % | -170 ± 126 |
| base $200, x1 | GPT-6.1 | **+1,865 ± 180** | **+4,286 ± 331** | **+6,542 ± 292** | **+807 ± 269** | +179 ± 180 | +58 ± 151 | 0.2 ± 0.1 | 3.8 % | +28 ± 151 |
| base $200, x2 | Opus 5.5 | **+596 ± 127** | **+1,767 ± 242** | **+2,020 ± 246** | -4,891 ± 339 | +131 ± 143 | -123 ± 118 | 0.2 ± 0.1 | 1.7 % | -114 ± 116 |
| base $200, x2 | GPT-6.1 | **+1,911 ± 188** | **+4,286 ± 331** | **+7,284 ± 351** | **+1,163 ± 364** | **+175 ± 169** | +79 ± 149 | 0.2 ± 0.1 | 3.0 % | +67 ± 151 |
| base $50, x1; a reversal takes 2 x its bounty off | Opus 5.5 | +10 ± 61 | +38 ± 56 | -117 ± 93 | -4,669 ± 331 | +3 ± 119 | -100 ± 141 | 0.6 ± 0.1 | 1.7 % | +0 ± 0 |
| base $50, x1; a reversal takes 2 x its bounty off | GPT-6.1 | **+630 ± 87** | **+797 ± 78** | **+1,324 ± 141** | +101 ± 379 | +82 ± 192 | +169 ± 233 | 0.9 ± 0.2 | 2.8 % | +0 ± 0 |

### The pot alone: equal units and impact weights (3 solvers; the tests fail them)

| Split | Seated | Bad fixes, one identity ($ a year) | Farmer of the cheapest fifth − its twin | Farmer filing its own issues − its twin | An honest solver's year | Issues not worth an honest fix | …their share of the funding | Fixed / wrong / unfixed per 100 (solver of bad fixes present while it profits) | A unit of weight ($) |
|---|---|---|---|---|---|---|---|---|---|
| equal units | Opus 5.5 | **+1,524 ± 217** | **+20,461 ± 360** | **+18,418 ± 338** | 12,573 ± 366 | 5.1 % | 12.6 % | 55.4 / 1.9 / 42.7 | 161.5 ± 1.4 |
| equal units | GPT-6.1 | **+4,410 ± 326** | **+19,091 ± 454** | **+17,288 ± 424** | 10,968 ± 488 | 7.7 % | 17.1 % | 40.5 / 3.4 / 56.1 | 185.4 ± 1.4 |
| impact, correlation 0.3 | Opus 5.5 | **+1,598 ± 250** | **+13,271 ± 562** | **+11,602 ± 541** | 12,932 ± 467 | 12.0 % | 17.5 % | 51.5 / 1.8 / 46.8 | 138.0 ± 1.2 |
| impact, correlation 0.3 | GPT-6.1 | **+4,547 ± 355** | **+12,128 ± 606** | **+10,642 ± 584** | 11,376 ± 586 | 15.9 % | 22.0 % | 37.0 / 3.2 / 59.8 | 158.0 ± 1.3 |
| impact, correlation 0.6 | Opus 5.5 | **+1,554 ± 238** | **+6,575 ± 415** | **+5,316 ± 413** | 12,244 ± 450 | 6.8 % | 9.4 % | 54.5 / 1.8 / 43.7 | 134.4 ± 1.0 |
| impact, correlation 0.6 | GPT-6.1 | **+4,364 ± 328** | **+5,922 ± 474** | **+4,789 ± 466** | 10,793 ± 566 | 10.4 % | 13.7 % | 39.4 / 3.4 / 57.3 | 154.2 ± 1.1 |
| impact, correlation 0.9 | Opus 5.5 | **+1,467 ± 221** | **+967 ± 294** | -63 ± 294 | 11,001 ± 401 | 0.2 % | 0.3 % | 58.4 / 1.9 / 39.7 | 129.2 ± 0.8 |
| impact, correlation 0.9 | GPT-6.1 | **+4,023 ± 303** | **+775 ± 347** | -116 ± 344 | 9,418 ± 493 | 1.1 % | 1.4 % | 43.4 / 3.6 / 53.0 | 146.2 ± 0.9 |

### The inflater against its twin, by the assumed correlation and cost

| Correlation (assumed) | Seated | Inflating costs $0 a fix | Inflating costs $5 a fix | Inflating costs $20 a fix | Inflating costs $50 a fix | Inflating costs $100 a fix |
|---|---|---|---|---|---|---|
| impact, correlation 0.3 | Opus 5.5 | **+20,456 ± 394** | **+19,161 ± 375** | **+15,275 ± 324** | **+7,502 ± 268** | -5,451 ± 362 |
| impact, correlation 0.3 | GPT-6.1 | **+19,407 ± 413** | **+18,112 ± 394** | **+14,225 ± 343** | **+6,453 ± 284** | -6,501 ± 367 |
| impact, correlation 0.6 | Opus 5.5 | **+20,127 ± 365** | **+18,832 ± 345** | **+14,946 ± 290** | **+7,174 ± 232** | -5,780 ± 343 |
| impact, correlation 0.6 | GPT-6.1 | **+19,155 ± 388** | **+17,860 ± 367** | **+13,974 ± 313** | **+6,201 ± 250** | -6,752 ± 344 |
| impact, correlation 0.9 | Opus 5.5 | **+18,769 ± 319** | **+17,474 ± 298** | **+13,587 ± 240** | **+5,815 ± 185** | -7,139 ± 332 |
| impact, correlation 0.9 | GPT-6.1 | **+18,009 ± 345** | **+16,713 ± 326** | **+12,827 ± 278** | **+5,055 ± 240** | -7,899 ± 374 |

### The find rate: 10 % and 50 % in place of 25 %

| Combination | Find rate (assumed) | Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|---|---|
| none | 10 % | solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+2,318 ± 212** | **+1,832 ± 196** | **+627 ± 138** | **+5,169 ± 260** | **+4,139 ± 259** | **+1,774 ± 193** |
| none | 10 % | solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+6,148 ± 313** | **+5,032 ± 283** | **+2,082 ± 188** | **+3,255 ± 203** | **+2,682 ± 180** | **+947 ± 108** |
| none | 10 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+7,954 ± 639** | **+6,361 ± 583** | **+2,907 ± 379** | **+15,981 ± 818** | **+12,944 ± 803** | **+6,158 ± 583** |
| none | 10 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+18,979 ± 907** | **+15,652 ± 827** | **+7,155 ± 560** | **+10,356 ± 577** | **+8,654 ± 524** | **+3,601 ± 364** |
| none | 10 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+18,551 ± 457** | **+15,408 ± 486** | **+3,821 ± 436** | **+24,597 ± 557** | **+23,439 ± 564** | **+15,392 ± 533** |
| none | 10 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+24,708 ± 608** | **+23,863 ± 587** | **+16,868 ± 499** | **+22,150 ± 549** | **+20,188 ± 511** | **+9,893 ± 508** |
| none | 50 % | solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+980 ± 158** | -147 ± 79 | -539 ± 21 | **+2,708 ± 218** | **+408 ± 102** | -385 ± 20 |
| none | 50 % | solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+3,143 ± 229** | **+349 ± 99** | -540 ± 18 | **+1,537 ± 170** | **+131 ± 70** | -388 ± 17 |
| none | 50 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+3,868 ± 423** | **+607 ± 204** | -525 ± 38 | **+8,615 ± 575** | **+2,031 ± 268** | -360 ± 43 |
| none | 50 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+10,064 ± 619** | **+2,151 ± 315** | -510 ± 43 | **+5,285 ± 462** | **+1,173 ± 199** | -377 ± 25 |
| none | 50 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | **+9,669 ± 395** | -8,489 ± 449 | -18,591 ± 424 | **+20,155 ± 492** | **+859 ± 407** | -15,384 ± 370 |
| none | 50 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+21,098 ± 573** | **+1,075 ± 514** | -18,502 ± 422 | **+15,025 ± 494** | -3,337 ± 383 | -15,461 ± 365 |
| R+F | 10 % | solver of bad fixes, one identity (twin: nothing) | the tests fail them | **+234 ± 146** | -243 ± 107 | -820 ± 49 | **+1,414 ± 178** | **+688 ± 149** | -447 ± 71 |
| R+F | 10 % | solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+1,973 ± 186** | **+1,132 ± 154** | -296 ± 75 | **+992 ± 207** | **+323 ± 150** | -738 ± 51 |
| R+F | 10 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | -122 ± 75 | -370 ± 69 | -899 ± 50 | **+1,105 ± 102** | **+631 ± 102** | -425 ± 79 |
| R+F | 10 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+1,583 ± 116** | **+1,066 ± 108** | -241 ± 78 | **+250 ± 81** | -20 ± 76 | -805 ± 56 |
| R+F | 10 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -27 ± 218 | -1,058 ± 144 | -2,258 ± 76 | **+3,033 ± 215** | **+1,293 ± 223** | -1,367 ± 93 |
| R+F | 10 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+5,175 ± 307** | **+2,730 ± 225** | -920 ± 120 | **+2,418 ± 420** | **+282 ± 225** | -2,028 ± 87 |
| R+F | 10 % | retrying solver, a new identity each try (twin: nothing) | the tests fail them | -2,701 ± 259 | -5,194 ± 305 | -14,091 ± 437 | **+2,940 ± 104** | **+1,382 ± 145** | -6,438 ± 303 |
| R+F | 10 % | retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+4,172 ± 136** | **+2,853 ± 160** | -4,015 ± 268 | -274 ± 190 | -2,337 ± 240 | -11,056 ± 396 |
| R+F | 10 % | long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -1,768 ± 353 | -2,834 ± 304 | -4,197 ± 331 | **+2,932 ± 540** | **+1,800 ± 449** | -339 ± 257 |
| R+F | 10 % | long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | **+1,746 ± 496** | +272 ± 498 | -2,244 ± 281 | **+3,086 ± 604** | **+1,583 ± 473** | -737 ± 292 |
| R+F | 10 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | +173 ± 212 | +91 ± 187 | -36 ± 164 | **+464 ± 254** | **+289 ± 243** | +60 ± 165 |
| R+F | 10 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | **+363 ± 248** | +157 ± 177 | -34 ± 156 | **+826 ± 330** | **+472 ± 321** | +46 ± 247 |
| R+F | 50 % | solver of bad fixes, one identity (twin: nothing) | the tests fail them | -659 ± 62 | -1,056 ± 29 | -1,168 ± 24 | -69 ± 94 | -925 ± 38 | -1,186 ± 27 |
| R+F | 50 % | solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+147 ± 94** | -892 ± 45 | -1,184 ± 26 | -456 ± 91 | -1,010 ± 34 | -1,166 ± 23 |
| R+F | 50 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | -749 ± 58 | -1,240 ± 39 | -1,415 ± 34 | -30 ± 81 | -1,037 ± 45 | -1,413 ± 35 |
| R+F | 50 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+221 ± 84** | -997 ± 53 | -1,410 ± 34 | -535 ± 70 | -1,177 ± 43 | -1,414 ± 33 |
| R+F | 50 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -1,890 ± 85 | -2,777 ± 71 | -3,035 ± 67 | -445 ± 136 | -2,529 ± 73 | -3,086 ± 68 |
| R+F | 50 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+221 ± 125** | -2,354 ± 88 | -3,100 ± 71 | -1,461 ± 98 | -2,684 ± 60 | -3,028 ± 71 |
| R+F | 50 % | retrying solver, a new identity each try (twin: nothing) | the tests fail them | -9,818 ± 419 | -22,915 ± 572 | -29,707 ± 604 | -2,228 ± 216 | -17,937 ± 489 | -29,673 ± 606 |
| R+F | 50 % | retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | -295 ± 181 | -16,132 ± 379 | -29,633 ± 604 | -6,918 ± 253 | -21,160 ± 457 | -29,694 ± 602 |
| R+F | 50 % | long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -3,793 ± 367 | -4,712 ± 266 | -4,912 ± 247 | +207 ± 320 | -989 ± 210 | -1,422 ± 197 |
| R+F | 50 % | long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -1,508 ± 364 | -3,140 ± 212 | -3,604 ± 215 | -216 ± 383 | -1,559 ± 276 | -1,838 ± 212 |
| R+F | 50 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | -31 ± 154 | -113 ± 140 | -135 ± 133 | +160 ± 185 | +66 ± 148 | +85 ± 158 |
| R+F | 50 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | -3 ± 156 | -84 ± 125 | -135 ± 116 | +197 ± 226 | +40 ± 218 | +6 ± 217 |
| R+P+F | 10 % | solver of bad fixes, one identity (twin: nothing) | the tests fail them | -646 ± 122 | -873 ± 47 | -975 ± 29 | -795 ± 81 | -869 ± 75 | -972 ± 28 |
| R+P+F | 10 % | solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | -806 ± 68 | -899 ± 42 | -972 ± 30 | -336 ± 173 | -770 ± 94 | -953 ± 32 |
| R+P+F | 10 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | **+886 ± 149** | **+441 ± 135** | -500 ± 87 | **+3,301 ± 201** | **+2,413 ± 199** | **+435 ± 150** |
| R+P+F | 10 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+3,586 ± 202** | **+2,734 ± 192** | **+548 ± 133** | **+1,798 ± 157** | **+1,283 ± 145** | -233 ± 101 |
| R+P+F | 10 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -3,621 ± 98 | -3,283 ± 70 | -2,943 ± 49 | -3,188 ± 87 | -3,095 ± 58 | -2,918 ± 53 |
| R+P+F | 10 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | -3,104 ± 91 | -3,110 ± 65 | -2,938 ± 47 | -4,170 ± 146 | -3,550 ± 111 | -3,012 ± 60 |
| R+P+F | 10 % | retrying solver, a new identity each try (twin: nothing) | the tests fail them | **+4,671 ± 304** | **+1,509 ± 334** | -9,865 ± 458 | **+12,084 ± 234** | **+10,032 ± 242** | -359 ± 376 |
| R+P+F | 10 % | retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+11,282 ± 266** | **+9,597 ± 269** | **+779 ± 313** | **+9,579 ± 312** | **+6,936 ± 322** | -4,656 ± 406 |
| R+P+F | 10 % | long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -877 ± 1,739 | -2,179 ± 1,742 | -3,696 ± 1,730 | -5,719 ± 2,032 | -6,388 ± 2,099 | -7,158 ± 2,030 |
| R+P+F | 10 % | long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -4,065 ± 1,621 | -4,559 ± 1,569 | -5,664 ± 1,622 | -1,773 ± 2,400 | -3,436 ± 2,409 | -5,721 ± 2,200 |
| R+P+F | 10 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | -149 ± 1,420 | -661 ± 1,312 | -169 ± 1,115 | -1,009 ± 1,082 | -1,086 ± 1,047 | -1,170 ± 857 |
| R+P+F | 10 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | -91 ± 1,140 | -121 ± 999 | -118 ± 766 | -2,025 ± 1,892 | -2,245 ± 1,636 | -1,302 ± 1,050 |
| R+P+F | 50 % | solver of bad fixes, one identity (twin: nothing) | the tests fail them | -949 ± 33 | -1,059 ± 27 | -1,167 ± 24 | -957 ± 31 | -1,029 ± 30 | -1,184 ± 27 |
| R+P+F | 50 % | solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | -927 ± 36 | -1,023 ± 27 | -1,183 ± 27 | -887 ± 57 | -1,037 ± 32 | -1,167 ± 24 |
| R+P+F | 50 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | -238 ± 114 | -1,110 ± 59 | -1,413 ± 35 | **+1,167 ± 150** | -719 ± 76 | -1,408 ± 36 |
| R+P+F | 50 % | free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+1,325 ± 143** | -709 ± 84 | -1,407 ± 35 | **+285 ± 132** | -951 ± 67 | -1,411 ± 33 |
| R+P+F | 50 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -3,062 ± 61 | -2,901 ± 63 | -3,034 ± 68 | -2,950 ± 57 | -2,903 ± 61 | -3,084 ± 69 |
| R+P+F | 50 % | retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | -2,997 ± 50 | -2,899 ± 61 | -3,094 ± 73 | -3,200 ± 60 | -2,893 ± 60 | -3,026 ± 71 |
| R+P+F | 50 % | retrying solver, a new identity each try (twin: nothing) | the tests fail them | -4,352 ± 433 | -21,150 ± 591 | -29,695 ± 603 | **+5,267 ± 295** | -15,343 ± 546 | -29,662 ± 607 |
| R+P+F | 50 % | retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+5,524 ± 241** | -14,300 ± 411 | -29,626 ± 603 | **+902 ± 303** | -18,282 ± 467 | -29,680 ± 602 |
| R+P+F | 50 % | long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -3,382 ± 1,761 | -4,142 ± 1,700 | -4,479 ± 1,708 | -6,949 ± 2,085 | -7,358 ± 2,144 | -7,592 ± 2,136 |
| R+P+F | 50 % | long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | -5,297 ± 1,638 | -5,975 ± 1,634 | -6,190 ± 1,635 | -5,080 ± 2,238 | -6,317 ± 2,242 | -6,706 ± 2,233 |
| R+P+F | 50 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | -121 ± 978 | +128 ± 900 | +161 ± 882 | -973 ± 859 | -1,114 ± 869 | -1,196 ± 868 |
| R+P+F | 50 % | reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | -226 ± 905 | -496 ± 880 | -353 ± 761 | -1,299 ± 1,176 | -1,183 ± 1,050 | -1,261 ± 1,038 |

### Post hoc: the cap with a reversal taking 2 x its bounty off, and the judges' fee

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | -97 ± 148 | -732 ± 52 | -1,120 ± 24 | **+926 ± 172** | -244 ± 77 | -1,089 ± 27 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | **+1,514 ± 212** | -57 ± 78 | -1,052 ± 33 | **+647 ± 227** | -510 ± 60 | -1,107 ± 28 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | -348 ± 71 | -833 ± 50 | -1,342 ± 30 | **+722 ± 101** | -224 ± 69 | -1,261 ± 32 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | **+1,086 ± 103** | +30 ± 74 | -1,222 ± 40 | -39 ± 73 | -592 ± 59 | -1,316 ± 37 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | -718 ± 236 | -2,064 ± 88 | -2,927 ± 65 | **+1,938 ± 220** | -916 ± 133 | -2,821 ± 64 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | **+3,870 ± 364** | -233 ± 124 | -2,781 ± 72 | **+2,444 ± 912** | -1,619 ± 93 | -2,874 ± 67 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | -4,810 ± 327 | -11,839 ± 470 | -26,488 ± 603 | **+1,711 ± 121** | -4,118 ± 280 | -23,943 ± 555 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | **+3,045 ± 146** | -1,949 ± 217 | -22,559 ± 500 | -2,134 ± 211 | -8,625 ± 327 | -25,551 ± 546 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | -3,165 ± 383 | -4,657 ± 330 | -5,532 ± 232 | **+3,383 ± 700** | +128 ± 378 | -1,386 ± 265 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | **+1,715 ± 610** | -1,624 ± 339 | -3,535 ± 219 | **+3,047 ± 635** | -25 ± 434 | -1,965 ± 249 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | +68 ± 157 | -13 ± 118 | -111 ± 122 | **+237 ± 231** | +75 ± 191 | -27 ± 170 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | **+267 ± 206** | +82 ± 159 | -93 ± 113 | **+505 ± 272** | +31 ± 217 | -24 ± 201 |

| Seated | Solvers | Newcomer: cost of the cap ($ a year) | …week it first may claim $86 | …issues it wanted, turned away | …their share of the value | Established (5,000): cost |
|---|---|---|---|---|---|---|
| Opus 5.5 | 1 | -112 ± 140 | 0.6 ± 0.1 | 1.6 % | 2.3 % | +0 ± 0 |
| Opus 5.5 | 3 | -99 ± 141 | 0.6 ± 0.1 | 1.7 % | 2.5 % | +0 ± 0 |
| Opus 5.5 | 10 | -58 ± 137 | 0.6 ± 0.1 | 1.8 % | 2.6 % | +0 ± 0 |
| GPT-6.1 | 1 | +136 ± 216 | 0.8 ± 0.2 | 2.4 % | 3.4 % | +0 ± 0 |
| GPT-6.1 | 3 | +172 ± 233 | 0.9 ± 0.2 | 2.8 % | 3.7 % | +0 ± 0 |
| GPT-6.1 | 10 | +28 ± 213 | 0.9 ± 0.2 | 3.5 % | 4.8 % | +0 ± 0 |

### Post hoc: the deposit that would close the holes of the cap and the fee, one active solver

| Attacker | Bad fixes | Seated | No deposit (grid) | Deposit 500 | Deposit 1,000 | Deposit 2,500 |
|---|---|---|---|---|---|---|
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | Opus 5.5 | -97 ± 148 | -675 ± 118 | -1,254 ± 93 | -2,988 ± 90 |
| solver of bad fixes, one identity (twin: nothing) | the tests fail them | GPT-6.1 | **+926 ± 172** | **+436 ± 167** | -55 ± 163 | -1,527 ± 158 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | Opus 5.5 | **+1,514 ± 212** | **+1,009 ± 199** | **+505 ± 187** | -1,008 ± 156 |
| solver of bad fixes, one identity (twin: nothing) | pass the tests, wrong | GPT-6.1 | **+647 ± 227** | -81 ± 198 | -808 ± 174 | -2,991 ± 167 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | Opus 5.5 | -348 ± 71 | -886 ± 71 | -1,424 ± 74 | -3,038 ± 90 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | the tests fail them | GPT-6.1 | **+722 ± 101** | **+237 ± 103** | -248 ± 106 | -1,702 ± 123 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | Opus 5.5 | **+1,086 ± 103** | **+620 ± 106** | **+153 ± 109** | -1,246 ± 127 |
| free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing) | pass the tests, wrong | GPT-6.1 | -39 ± 73 | -562 ± 80 | -1,084 ± 89 | -2,652 ± 122 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | Opus 5.5 | -718 ± 236 | -1,816 ± 225 | -3,946 ± 290 | -36,380 ± 3,570 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | the tests fail them | GPT-6.1 | **+1,938 ± 220** | **+1,306 ± 229** | **+423 ± 256** | -6,006 ± 815 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | Opus 5.5 | **+3,870 ± 364** | **+3,295 ± 364** | **+2,541 ± 368** | -2,056 ± 697 |
| retrying solver, one identity, up to 21 tries an issue (twin: nothing) | pass the tests, wrong | GPT-6.1 | **+2,444 ± 912** | **+932 ± 776** | -2,162 ± 585 | -51,586 ± 9,123 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | Opus 5.5 | -4,810 ± 327 | -7,177 ± 463 | -12,454 ± 803 | -101,909 ± 7,248 |
| retrying solver, a new identity each try (twin: nothing) | the tests fail them | GPT-6.1 | **+1,711 ± 121** | **+810 ± 145** | -562 ± 203 | -12,155 ± 1,136 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | Opus 5.5 | **+3,045 ± 146** | **+2,378 ± 155** | **+1,461 ± 185** | -4,715 ± 750 |
| retrying solver, a new identity each try (twin: nothing) | pass the tests, wrong | GPT-6.1 | -2,134 ± 211 | -3,584 ± 291 | -6,782 ± 507 | -61,209 ± 4,861 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | Opus 5.5 | -3,165 ± 383 | -5,557 ± 369 | -7,948 ± 385 | -15,124 ± 570 |
| long con: farms, then cashes in until reset (twin: farms all year) | the tests fail them | GPT-6.1 | **+3,383 ± 700** | **+2,294 ± 658** | **+1,205 ± 619** | -2,061 ± 527 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | Opus 5.5 | **+1,715 ± 610** | +301 ± 564 | -1,114 ± 526 | -5,357 ± 474 |
| long con: farms, then cashes in until reset (twin: farms all year) | pass the tests, wrong | GPT-6.1 | **+3,047 ± 635** | **+799 ± 615** | -1,450 ± 615 | -8,195 ± 722 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | Opus 5.5 | +68 ± 157 | -92 ± 135 | -251 ± 128 | -730 ± 194 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | the tests fail them | GPT-6.1 | **+237 ± 231** | +191 ± 239 | +145 ± 248 | +8 ± 280 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | Opus 5.5 | **+267 ± 206** | **+211 ± 197** | +156 ± 189 | -10 ± 173 |
| reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms) | pass the tests, wrong | GPT-6.1 | **+505 ± 272** | **+301 ± 256** | +97 ± 255 | -515 ± 331 |

