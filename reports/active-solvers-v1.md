# The minimum of active solvers before pledges, v1: the gate, report v5's attackers and the sybil of three (proof-of-fix#251 task 3.2, launch design L6; 2026-11-18)

**Status: confirmatory on its own rule.** The rule, the rows and the criterion (section 1) were committed before the 40-seed runs, which use **fresh seeds 41–80**; every table is run on them, including report v5's R(minus)+F rows with no gate (the reference), so nothing here needs v5's seeds 1–40 for comparison. Every ± is two standard errors of the mean over the seeds. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json` (#160).

**Commands:** `python3 -m pof.sim.openval.activesolvers --seed0 41 --seeds 40 --jobs 15 --out DIR` runs every table; `--render DIR` prints the appendix.

## In brief
- **The gate does what it is for when the count is honest.** With the repository's own solvers counted, report v5's six attackers stay at or below their twins with 1, 3 and 10 honest solvers at every window, **except one cell**: the long con under GPT-6.1 with 3 solvers (the tests fail its bad fixes), **+451 ± 336** a year at every window. That cell is at even without the gate too (+177 ± 382 here, +128 ± 378 in v5), and the gate's own effect on it is not significant (+274 ± 337, paired). With 1 honest solver the gate never opens, so nobody can pledge and nobody can attack.
- **The sybil of three gains.** One party keeps three identities active with trivial fixes to issues it files itself. That costs it **19 fixes and $106 a year** at 13 weeks (38 faucet requests on Sepolia at a $40 fee). It then gets back **almost all of v5's one-solver gain:** up to **+$3,680 ± 384** a year (the retrier, Opus 5.5, fixes that pass the tests) and **+$3,386 ± 718** (the long con, GPT-6.1). That is against v5's +$3,594 with no gate on the same seeds. With 3 and 10 honest solvers it gains nothing, at every window.
- **What closes it, among the design's options:**
  - **A higher minimum doesn't:** at 5 and 10 the sybil keeps 5 or 10 identities for $177 or $356 a year and still gains up to +$3,391 and +$3,244.
  - **A longer window doesn't:** it makes the sybil cheaper ($64 a year at 26 weeks; $278 at 6 weeks, still not enough).
  - **Dearer fixes ($43 each to write) don't:** up to +$3,367.
  - **Only a deposit does: 2,500 (25 % of the bounty) closes every sybil row; 1,000 leaves four open** (up to +$2,373), as v5 found for one solver with no gate. **The deposit must not be switched off by the same count:** "a deposit while fewer than three are active" is switched off by the same three identities.
- **Two side findings for the contracts:**
  - **If anyone's upheld test counts,** as L6 is written, the world's contenders (v5's model-run disputers) open a one-solver repository within about 2 weeks, and the gate protects nothing: every v5 attacker gains again (up to +$3,399).
  - **A lone honest solver gains $3,200–11,400 a year by faking two identities** to open its own shut repository: the minimum pays honest people to cheat it.
- **A fresh repository with honest solvers only** first takes a pledge after 0.2–0.4 weeks at v5's 30 issues a week, 1.1–1.9 weeks at 5 a week and 5–11 weeks at 1 a week; with 1 honest solver, never. At 13 weeks and 3 solvers it leaves 5–8 good fixes a year unpaid ($480–850). At 1 issue a week it shuts again 1.1–1.5 times a year (at 6 weeks, 4–5 times; at 26 weeks, never).
- **Recommendation:**
  - **`ACTIVE_WINDOW` = 26 weeks** (the pre-registered rule: 13 leaves 2.4–3.4 more good fixes a year unpaid in a repository of 1 issue a week with 3 solvers; 6 leaves 14–16 more).
  - **`ACTIVE_SOLVERS_MIN`: keep 3**, though the pre-registered rule does not confirm it (the one cell above). Raising it doesn't address that cell, and no minimum stops the sybil.
  - **The gate is a guard against accident (a repository with one solver), not against a determined party.** If the owner wants the sybil closed, it takes a deposit of about 25 % on claims, applied by something other than the count. **The owner records the window (task 3.2's last step).**

## 1. The rule, the rows and the criterion, fixed before the 40-seed runs

### 1.1 What was added to the model
**The switch** (`Params.ACTIVE_GATE`, off by default, read only by `nodeposit.NDNet`; a plain `Net` refuses it), with launch design L6's rule:
- **Active:** an identity is active while, within `ACTIVE_WINDOW_WEEKS` (6, 13 or 26), it has **a fix whose passing verdict became final** (funded or not) **or a failing-test dispute that was upheld** (a test that reversed a pass).
- **The gate:** while fewer than `ACTIVE_SOLVERS_MIN` (3) identities are active, **pledges are refused**: an issue listed then stays unfunded for good (the funder doesn't come back), its fix is still judged, unpaid, and still makes its solver active. Actors start no new claim while the gate is shut. **Claims made before go on** (the retrier's retries, a fix already in judgement): the count gates only new money.
- **Whose tests count** (`ACTIVE_COUNTS`): **"repository"** (the primary rows): the repository's honest solvers' and the actors' identities. **"anyone"**: the world's contenders' upheld tests too, one identity per contender seat (the rule as L6 writes it, which can't tell a solver from anyone else who posts a test).
- **Who the repository's honest solvers are:** v5's `n` active honest solvers (1, 3 or 10), each searching every pass and finding a failing test for a bad one 1 time in 4 (assumed, as v5). **The world's fixes are attributed to them** (each fix to one of the `n`, by a draw bound to the fix), so the chain's count can see them; the world's flow of fixes is v5's (30 a week) and doesn't change with `n`. An upheld test by the honest solvers is credited to the first whose draw found it.
- **With the switch off, nothing moves:** a test checks that changing the gate's values with the switch off leaves v5's rows identical, and the existing test that `NDNet` with every switch off is v4's network is unchanged.

**The base** is report v5's recommendation, **R(minus)+F**: the reputation cap (base $50, ×1, a reversal takes 2 × its bounty off) and the judges' fee ($5.03 a submission), no deposit, v5's world (one family seated: Opus 5.5 or GPT-6.1, 28 validators; both kinds of bad fix: "the tests fail them" and "pass the tests, wrong").

**The sybil of three** (`activesolvers.Sybil`): one party keeps **3 identities** active with **good fixes to issues it files itself**: unfunded, so they carry no bounty and earn **no reputation**; each pays the attempt fee ($0.50) and the judges' fee ($5.03), and costs **$0 to write** (a trivial fix: the worst case for the defence). It renews an identity's pass when its last one is within 2 weeks of leaving the window, or the day after a rejection. Meanwhile **one of v5's six attackers** (B, S, T, Tf, L, RS) of the same party works the issues the open gate lets in, on its own identities (the cap applies to each as in v5).

### 1.2 The rows (seeds 41–80)
| Table | What | Rows |
|---|---|---|
| `ref` | v5's R(minus)+F, **no gate**: the six attackers × 2 pools × 2 seats × 1, 3, 10 honest solvers | 72 |
| `gate` | the same with **the gate on** ("repository"), at **6, 13 and 26 weeks** | 216 |
| `anyone` | the gate on with **contenders' tests counted**, 13 weeks | 72 |
| `sybil` | **the sybil of three** with each attacker × 2 pools × 2 seats × 1, 3, 10 × 6, 13, 26 weeks; plus L and RS against a twin that keeps the same identities ("Y2") | 288 |
| `options` | the design's options against the sybil, 1 honest solver, 13 weeks: **its fixes cost $43 to write** (half the median bounty); **a higher minimum, 5 and 10** (it keeps 5 or 10); **a deposit, 1,000 and 2,500** (`SOLVER_DEPOSIT_BPS`, all year: a "small" read from the same count would be met by the sybil too) | 120 |
| `unlock` | **honest solvers only:** 1, 3, 10 solvers × 2 seats × 6, 13, 26 weeks × **30, 5 and 1 issues a week** (v5's world, and two small repositories) × "repository" and "anyone" | 108 |

**Each attacker against its twin on the same seeds** (v5's twins): B, S, T and Tf's twin submits nothing; L's farms all year; RS's seller keeps the identity and farms. Under the gate, twins are gated as attackers are. **The sybil's twins**, fixed here:
- **B, S, T, Tf with the sybil ("YB", "YS", "YT", "YTf")**: the twin submits nothing and keeps no identity. The sybil pays for its identities; with 1 honest solver the twin's repository stays shut.
- **L and RS with the sybil, against a twin that keeps the same three identities and farms ("Y2L", "Y2RS")**: both open the repository, so the difference is the cheating alone.
- **L and RS against a twin that keeps nothing ("YL", "YRS")** are reported apart, not in the criterion: their gain is mostly honest farming income that only an open repository pays. It answers a different question: what opening a shut repository with fake identities is worth, cheating or not.

**Measured beside the returns:** when pledges are first taken (week), the share of the year they are, how often the gate shuts again, the pledges refused and their share of the funding, **the honest good fixes left unpaid** (and their bounties), and for the sybil: its fixes a year, how many passed, their fees at the judges' fee and, on Sepolia at a judges' fee of $40 in test USDC, in faucet requests (20 USDC each, one every 2 hours per address; report faucet-spam-v1).

### 1.3 The criterion and the decisions it drives
- **At or below its twin** (v5's): the difference's mean minus two standard errors is not above zero.
- **The gate holds** at a window when every `gate` row (6 attackers × 2 pools × 2 seats) is at or below its twin with 1, 3 and 10 honest solvers.
- **The sybil of three gains** if any of its pre-registered rows ("YB", "YS", "YT", "YTf", "Y2L", "Y2RS") is above its twin at any window and number of honest solvers.
- **An option closes the sybil** when every one of its pre-registered rows in `options` is at or below its twin (both pools, both seats).
- **`ACTIVE_SOLVERS_MIN`:** keep 3 if the gate holds at 3 and 10 honest solvers at every window; otherwise the smallest value the rows support. Whether the minimum stops the sybil is reported separately, with the option that closes it.
- **`ACTIVE_WINDOW`:** the shortest of 6, 13 and 26 weeks whose honest good fixes left unpaid in the `unlock` rows with 3 and 10 honest solvers at 1 and 5 issues a week (both seats, "repository") are not significantly more than at 26 weeks (difference within 2 SE of the two means' errors combined); a longer one if a `gate` row needs it to hold. Among windows that tie, the shorter is preferred: a repository whose solvers left stops taking money sooner, and the sybil renews more often.

**Disclosed:** a 2-seed smoke test on seeds 41–42 checked the implementation before this was written. It showed that the sybil's gain with L and RS against a twin that keeps nothing came from farming, which is why the "Y2" twins were added and the "YL"/"YRS" rows set apart; and that contenders' tests open a repository with one honest solver within weeks, which the `anyone` table measures. Seeds 41–42 are part of the 40.

## 2. Results (40 seeds, 41–80; written after the runs)
Every table ran in about 50 minutes on 15 cores. Every ± is two standard errors over the 40 seeds; "above" means its mean minus 2 SE is above zero.

### 2.1 The reference: v5's R(minus)+F with no gate, on fresh seeds
It **replicates v5:** every attacker at or below its twin with 3 and 10 honest solvers. With 1, five attackers are above in each seat: the retrier **+3,594 ± 334** (Opus 5.5, fixes that pass the tests; v5: +3,870 ± 364), the long con **+3,402 ± 664** (GPT-6.1; v5 +3,047 ± 635), the free identities, the solver of bad fixes and Tf. One difference: the reputation sale is not above its twin here (at most +97 ± 290; v5 +237 to +505).

### 2.2 The gate on, the repository's solvers counted
| Window | Opus 5.5: 1 / 3 / 10 solvers | GPT-6.1: 1 / 3 / 10 solvers |
|---|---|---|
| 6, 13 and 26 weeks (identical) | holds / holds / holds | holds / **no: L +451 ± 336** / holds |

- **With 1 honest solver nothing is ever funded,** so every attacker and its twin earn exactly 0. The repository loses all its pay instead: $81,000–108,000 of good fixes a year at v5's 30 issues a week (section 2.5).
- **With 3 and 10 the gate opens within half a week,** before the attackers do much, and every row is within a few dollars to $200 of the reference. The windows give identical rows: at 30 issues a week no honest solver ever goes 6 weeks without a final pass.
- **The one cell above its twin,** the long con under GPT-6.1 with 3 solvers and bad fixes the tests fail (+451 ± 336), **fails the pre-registered criterion.** It is the margin of R(minus)+F itself, not of the gate. The reference is +177 ± 382 on the same seeds, v5 had +128 ± 378 on seeds 1–40, and gate minus reference, seed by seed, is +274 ± 337 (post hoc, not significant). Under GPT-6.1, which rejects 30 % of good fixes, the long con's honest phase barely pays, so cashing in is close to even.
- **Small shifts the gate itself makes** (gate minus reference, seed by seed, post hoc): the retrier with new identities (Tf) does $30–200 better in 6 cells, and the solver of bad fixes and free identities $4–7 better in 3, all still far below their twins. Not starting in the gate's first days spares them a few of their worst tries.

### 2.3 The gate on, contenders' tests counted (L6 as written)
**It protects nothing with 1 honest solver:** the world's contenders (v5's disputers running the other models) post upheld tests against bad passes, each seat is an identity, and three of them plus the honest solver open the gate in **1.6–2.2 weeks**. The six attackers gain about as in the reference: up to **+3,399 ± 319** (Opus 5.5) and **+2,950 ± 492** (GPT-6.1); the reputation sale is above its twin here too (+155, +430). With 3 and 10 solvers it is the "repository" table again (the long con +364 ± 343, GPT-6.1, 3 solvers).

**What this means for the contracts:** the count works only if the identities it counts are the repository's searchers. A test can come from anyone, including disputers who don't work the repository. Counting upheld disputes only for identities that also have a final fix in the repository would close this case. **That variant was not simulated.**

### 2.4 The sybil of three
**Pre-registered rows** (YB, YS, YT, YTf against a twin that keeps nothing; Y2L, Y2RS against a twin that keeps the same identities):

| Window | Opus 5.5, 1 solver | GPT-6.1, 1 solver | 3 and 10 solvers |
|---|---|---|---|
| 6 weeks | **no**: YT, YTf, Y2L, YB, YS, Y2RS (up to +3,389) | **no**: YT, Y2L, YTf, YB, Y2RS, YS (up to +3,001) | holds |
| 13 weeks | **no**: YT, YTf, Y2L, YB, YS, Y2RS (up to +3,680) | **no**: Y2L, YT, YTf, YB, YS (up to +3,386) | holds |
| 26 weeks | **no**: YT, YTf, Y2L, YB, YS, Y2RS (up to +3,643) | **no**: Y2L, YT, YTf, YB, YS, Y2RS (up to +3,465) | holds |

- **The sybil of three gains, by the pre-registered criterion,** in every window, with 1 honest solver. With 13 weeks: the retrier **+3,680 ± 384** and **+3,013 ± 1,054**, Tf **+2,973 ± 142** and **+1,447 ± 123**, the long con against a twin that keeps too **+2,257 ± 598** and **+3,386 ± 718**, the solver of bad fixes **+1,326 ± 208** and **+708 ± 144**, free identities **+1,024 ± 90** and **+503 ± 71** (Opus 5.5 and GPT-6.1). The reputation sale is close to even (+275 ± 204 at most).
- **The gains are v5's one-solver gains less the identities' cost:** the gate opens in 0.2 weeks and stays open 99.6 % of the year.
- **What the identities cost it** (all rows with 1 honest solver):

  | Window | Its fixes a year (passed) | Judges' fee + attempt fee ($5.53 a fix) | Sepolia, judges' fee $40 in test USDC | A year per identity |
  |---|---|---|---|---|
  | 6 weeks | 50 (39) | $278 | 101 faucet requests | 17 fixes, $93 |
  | 13 weeks | 19 (15) | $106 | 38 requests | 6.4 fixes, $35 |
  | 26 weeks | 12 (9) | $64 | 23 requests | 3.8 fixes, $21 |

  On Sepolia, a year's identities at 13 weeks take about three days of one address's faucet limit (12 requests a day). A fix costs nothing to write in these rows (a trivial fix to an issue it filed). At $43 a fix the 13-week year adds about $830.
- **With 1 honest solver, two identities would do** (1 + 2 = 3), at two thirds of the cost; the rows keep three, as the design names it.
- **What opening a shut repository is worth to a lone honest solver** (YL and YRS against a twin that keeps nothing, not in the criterion): **+5,865 ± 375 to +11,390 ± 650** a year with Opus 5.5 and +3,222 to +6,420 with GPT-6.1. This is mostly honest farming that only an open repository pays. **The minimum gives a lone honest solver a reason to fake two identities.**

### 2.5 The design's options against the sybil (1 honest solver, 13 weeks; pre-registered rows)
| Option | Opus 5.5 | GPT-6.1 | Its identities a year | Closes it? |
|---|---|---|---|---|
| none (13 weeks, section 2.4) | **no**: up to +3,680 | **no**: up to +3,386 | $106 | no |
| its fixes cost $43 to write | **no**: YT +2,966 ± 384, Y2L, YTf, YB, YS, Y2RS | **no**: Y2L +3,367 ± 721, YT, YTf | $106 + $826 of work | no |
| minimum 5 (it keeps 5) | **no**: YT +3,391 ± 325, YTf, Y2L, YB, YS | **no**: YT +2,997, Y2L, YTf, YB, YS, Y2RS | $177 | no |
| minimum 10 (it keeps 10) | **no**: YT +3,244 ± 340, YTf, Y2L, YB, YS | **no**: Y2L +3,017, YT, YTf, Y2RS, YB, YS | $356 | no |
| a longer window (26 weeks, section 2.4) | **no**: up to +3,643 | **no**: up to +3,465 | $64 | no |
| deposit 1,000, all year | **no**: YT +2,373 ± 383, YTf +1,369 ± 198, YB +332 ± 184 | **no**: Y2L +617 ± 475 | $106 | no |
| **deposit 2,500, all year** | holds (at most −189) | holds (at most −241) | $106 | **yes** |

- **A higher minimum and a longer window don't close it,** and can't. Each identity costs the sybil about $35 a year at 13 weeks, against gains of about $3,000. A minimum of N costs it about $35 × N, so N would have to be on the order of 100 (extrapolated, not run). A longer window only makes the identities cheaper.
- **Only the deposit of 2,500 closes every row,** as v5's post hoc deposit rows found for one solver with no gate. **The deposit has to apply to the sybil's claims.** One that applies "while the repository is small", with small read from the active count, is switched off by the same identities. The simulation names no measure of "small" that a sybil can't fake: unfunded fixes earn no reputation, but a party can fund its own issues and be paid its own pledges.

### 2.6 A fresh repository with honest solvers only
"Repository" count; mean ± 2 SE; both seats (Opus 5.5 / GPT-6.1). Full table in the appendix.

| Issues a week | Honest solvers | First pledge (week) | Pledges taken, % of the year (6 / 13 / 26 weeks) | Shut again a year (6 / 13 / 26) | Good fixes unpaid a year (6 / 13 / 26) |
|---|---|---|---|---|---|
| 30 (v5) | 1 | never | 0 | – | 793–1,057 ($81,000–108,000) |
| 30 | 3 | 0.3–0.4 | 99.3–99.4 at every window | 0 | 5.7–6.7 ($560–670) at every window |
| 30 | 10 | 0.2–0.3 | 99.5–99.6 | 0 | 4.0–4.5 ($390–440) |
| 5 | 3 | 1.7–1.9 | 95.5–96.7 / 96.4–96.8 / 96.4–96.8 | 0.1–0.5 / 0 / 0 | 5.9–6.2 / 5.0–5.7 / 5.0–5.7 |
| 5 | 10 | 1.1–1.3 | 97.6–97.9 at every window | 0 | 3.4–3.5 |
| 1 | 3 | 8.1–10.6 | 32–42 / 71–79 / 82–84 | 4.3–5.0 / 1.1–1.5 / 0 | 19–22 / 8.0–8.4 / 5.0–5.6 |
| 1 | 10 | 5.1–6.3 | 59–71 / 87–90 / 88–90 | 4.5–4.7 / 0.1–0.4 / 0 | 10–12 / 3.6–3.8 / 3.4–3.5 |

- **One honest solver never opens the gate,** at any flow. All its work is unpaid: $2,900–3,800 a year at 1 issue a week.
- **The window matters only for small repositories.** At 1 issue a week with 3 solvers, 6 weeks shuts the gate 4–5 times a year and refuses 58–69 % of the funding. 13 weeks shuts it 1.1–1.5 times (22–30 % refused); 26 weeks never shuts it again (15–16 % refused, all before the first pledge).
- **Applying the pre-registered rule for `ACTIVE_WINDOW`** (unpaid good fixes, 3 and 10 solvers, 1 and 5 issues a week, against 26 weeks): 13 weeks leaves **+2.4 ± 0.8 and +3.4 ± 0.9** more a year with 3 solvers at 1 issue a week (significant; 10 solvers and 5 a week: no difference). 6 weeks leaves +7.0 to +16.1 more. **So the rule picks 26 weeks.**

## 3. What this recommends
| Value | Recommendation | Why |
|---|---|---|
| `ACTIVE_WINDOW` | **26 weeks** | The pre-registered rule: 13 weeks costs a repository of 1 issue a week with 3 solvers 2.4–3.4 more unpaid good fixes a year and 1–1.5 shut-agains; no attacker row differs between windows; the sybil gains at every window. The cost: a repository whose solvers all left keeps taking pledges for up to half a year (funded bounties then wait for solvers who aren't there). If the owner weighs that more, 13 weeks is the alternative, at the measured cost above. |
| `ACTIVE_SOLVERS_MIN` | **keep 3** (departing from the pre-registered rule, which doesn't confirm it) | The rule asked every gate row to hold at 3 and 10 solvers; one cell (the long con, GPT-6.1, 3 solvers) is +451 ± 336. That cell is at even without the gate too, so a higher minimum doesn't fix it; the remedy is v5's (a better find rate, a higher judge accuracy than GPT-6.1's alone). The rows don't test 4–9, and 10 would keep small repositories shut most of the year. |
| The sybil of three | **It gains**, with 1 honest solver: up to about $3,700 a year for about $106 | Of the design's options, **only a deposit of about 25 % closes it**, and only if applied by a rule the sybil can't meet with the same identities. A higher minimum and a longer window don't. If the owner keeps no deposit (#250), the README and the paper name it as a trust point, as L6 already does, now with its size. |
| Whose tests count | **Only identities that work the repository** (for example, an upheld dispute counts only for an identity with a final fix in the repository within the window); **not simulated** | If anyone's upheld test counts (L6 as written), contenders open a one-solver repository within 2 weeks. |

**Plainly:** the minimum of three stops money from reaching a repository that has one honest solver by accident. It doesn't stop one party that wants it open: three identities cost about $35 each a year, and on Sepolia a few faucet requests. Closing that needs a deposit of about a quarter of the bounty, which the owner ruled out (#250). The owner chooses between accepting the trust point (named, now measured) and a deposit applied to every claim in a repository below some size the sybil can't fake.

## 4. Assumptions
- **The repository's honest solvers write all its fixes** (v5's world of 30 a week, assigned among the `n` by a draw) **and keep fixing while the gate is shut,** unpaid, at the same rate. If they stopped working unfunded issues, no repository would ever open.
- **A pledge refused is lost:** the issue stays unfunded even after the gate opens, and its funder doesn't come back. A fix is submitted when its issue is listed.
- **Actors start nothing while the gate is shut** (no bounty to take). Claims made before go on.
- **The sybil's fixes cost $0 to write** (trivial fixes to issues it files itself), with $43 in the option rows. It renews each identity 2 weeks before its pass leaves the window. Its identities are separate from the ones its attacker uses.
- **Contenders' upheld tests** are credited to one of the seats that failed the case, by a draw ("anyone"). The honest solvers' to the first whose search found the test.
- **A fix with no funding** is judged like any other: the same panel size (k = 7 at 28 validators), the same judges' fee.
- **Sepolia:** a judges' fee of $40 in test USDC (faucet-spam-v1's upper value) = 2 faucet requests a fix; one address gets 12 requests a day.
- v5's assumptions stand: find rate 25 %, contenders 1 in 2, honest fix effort half the bounty, one family seated, 28 validators.

## 5. What is not done
- **Counting disputes only for identities with a fix in the repository** (the fix of section 2.3) is not simulated.
- **A deposit while small** is simulated only as a deposit all year; no sybil-proof measure of "small" was found or tested.
- **2 honest solvers** (where the sybil needs one identity) and **minimums of 4–9** are not run.
- **The world's flow per honest solver** is v5's in the attacker rows; the small repositories (5 and 1 a week) are in the unlock rows only, with no attacker.
- **No contract test:** task 3.3 builds the count and the gate; its replay against these rows is 3.3's.
- **The find rate is assumed** (25 %), as in v5. At 10 %, v5 found R+F fails with 3 solvers too, and the gate would let money into those repositories.
- One family seated, 28 validators, one benchmark, 40 seeds.

## Appendix: the full output
Seeds 41–80; `python3 -m pof.sim.openval.activesolvers --render DIR`.

### Does every attacker stay at or below its twin? (both kinds of bad fix)

| Table: rows | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|
| ref: gate off | no: T, Tf, L, B, S (up to +3,594) | holds | holds | no: L, T, Tf, B, S (up to +3,402) | holds | holds |
| gate: window 6 weeks | holds | holds | holds | holds | no: L (up to +451) | holds |
| gate: window 13 weeks | holds | holds | holds | holds | no: L (up to +451) | holds |
| gate: window 26 weeks | holds | holds | holds | holds | no: L (up to +451) | holds |
| anyone: window 13 weeks | no: T, Tf, L, B, S, RS (up to +3,399) | holds | holds | no: L, T, Tf, B, S, RS (up to +2,950) | no: L (up to +364) | holds |
| sybil: window 6 weeks | no: YT, YTf, Y2L, YB, YS, Y2RS (up to +3,389) | holds | holds | no: YT, Y2L, YTf, YB, Y2RS, YS (up to +3,001) | holds | holds |
| sybil: window 13 weeks | no: YT, YTf, Y2L, YB, YS, Y2RS (up to +3,680) | holds | holds | no: Y2L, YT, YTf, YB, YS (up to +3,386) | holds | holds |
| sybil: window 26 weeks | no: YT, YTf, Y2L, YB, YS, Y2RS (up to +3,643) | holds | holds | no: Y2L, YT, YTf, YB, YS, Y2RS (up to +3,465) | holds | holds |
| sybil: window 6 weeks (L, RS: twin keeps nothing) | no: YL, YRS (up to +10,742) | holds | holds | no: YL, YRS (up to +5,827) | holds | holds |
| sybil: window 13 weeks (L, RS: twin keeps nothing) | no: YL, YRS (up to +11,390) | holds | holds | no: YL, YRS (up to +6,420) | holds | holds |
| sybil: window 26 weeks (L, RS: twin keeps nothing) | no: YL, YRS (up to +10,959) | holds | holds | no: YL, YRS (up to +6,495) | holds | holds |
| options: its fixes cost $43 to write | no: YT, Y2L, YTf, YB, YS, Y2RS (up to +2,966) | – | – | no: Y2L, YT, YTf (up to +3,367) | – | – |
| options: minimum 5 (it keeps 5) | no: YT, YTf, Y2L, YB, YS (up to +3,391) | – | – | no: Y2L, YT, YTf, YB, YS, Y2RS (up to +3,203) | – | – |
| options: minimum 10 (it keeps 10) | no: YT, YTf, Y2L, YB, YS (up to +3,244) | – | – | no: Y2L, YT, YTf, Y2RS, YB, YS (up to +3,017) | – | – |
| options: deposit 1,000 all year | no: YT, YTf, YB (up to +2,373) | – | – | no: Y2L (up to +617) | – | – |
| options: deposit 2,500 all year | holds | – | – | holds | – | – |

### No gate (report v5's R(minus)+F, fresh seeds): gate off ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity | the tests fail them | -159 ± 141 | -742 ± 57 | -1,129 ± 21 | **+836 ± 137** | -248 ± 71 | -1,076 ± 28 |
| B, one identity | pass the tests, wrong | **+1,504 ± 192** | -80 ± 96 | -1,063 ± 27 | **+688 ± 281** | -600 ± 62 | -1,108 ± 27 |
| S, free identities | the tests fail them | -366 ± 61 | -849 ± 48 | -1,359 ± 30 | **+665 ± 65** | -244 ± 68 | -1,264 ± 33 |
| S, free identities | pass the tests, wrong | **+1,155 ± 91** | +5 ± 79 | -1,237 ± 36 | -23 ± 88 | -673 ± 66 | -1,326 ± 36 |
| T, retrier | the tests fail them | -822 ± 209 | -2,164 ± 55 | -2,927 ± 57 | **+1,639 ± 222** | -959 ± 116 | -2,843 ± 61 |
| T, retrier | pass the tests, wrong | **+3,594 ± 334** | -398 ± 116 | -2,789 ± 55 | **+3,402 ± 999** | -1,758 ± 102 | -2,876 ± 63 |
| Tf, retrier, new identities | the tests fail them | -4,852 ± 236 | -11,915 ± 416 | -26,552 ± 704 | **+1,589 ± 121** | -4,238 ± 257 | -23,708 ± 659 |
| Tf, retrier, new identities | pass the tests, wrong | **+3,088 ± 146** | -1,926 ± 206 | -22,386 ± 604 | -2,016 ± 224 | -8,991 ± 340 | -25,448 ± 664 |
| L, long con | the tests fail them | -3,308 ± 340 | -4,604 ± 332 | -5,470 ± 318 | **+3,104 ± 610** | +177 ± 382 | -1,402 ± 232 |
| L, long con | pass the tests, wrong | **+2,286 ± 611** | -1,714 ± 335 | -3,667 ± 205 | **+3,402 ± 664** | -208 ± 393 | -1,923 ± 288 |
| RS, reputation sale | the tests fail them | +24 ± 171 | -85 ± 150 | -201 ± 127 | +86 ± 235 | -121 ± 202 | -193 ± 202 |
| RS, reputation sale | pass the tests, wrong | +89 ± 147 | -32 ± 126 | -93 ± 129 | +97 ± 290 | -144 ± 235 | -279 ± 205 |

### The gate on: window 6 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity | the tests fail them | +0 ± 0 | -747 ± 57 | -1,125 ± 20 | +0 ± 0 | -246 ± 75 | -1,074 ± 26 |
| B, one identity | pass the tests, wrong | +0 ± 0 | -88 ± 95 | -1,061 ± 27 | +0 ± 0 | -602 ± 67 | -1,103 ± 27 |
| S, free identities | the tests fail them | +0 ± 0 | -844 ± 48 | -1,353 ± 31 | +0 ± 0 | -241 ± 68 | -1,260 ± 34 |
| S, free identities | pass the tests, wrong | +0 ± 0 | +7 ± 79 | -1,231 ± 37 | +0 ± 0 | -669 ± 65 | -1,320 ± 36 |
| T, retrier | the tests fail them | +0 ± 0 | -2,142 ± 76 | -2,906 ± 51 | +0 ± 0 | -943 ± 113 | -2,808 ± 54 |
| T, retrier | pass the tests, wrong | +0 ± 0 | -368 ± 128 | -2,769 ± 56 | +0 ± 0 | -1,793 ± 92 | -2,874 ± 59 |
| Tf, retrier, new identities | the tests fail them | +0 ± 0 | -11,815 ± 411 | -26,348 ± 706 | +0 ± 0 | -4,214 ± 252 | -23,596 ± 664 |
| Tf, retrier, new identities | pass the tests, wrong | +0 ± 0 | -1,895 ± 209 | -22,280 ± 614 | +0 ± 0 | -8,872 ± 329 | -25,325 ± 669 |
| L, long con | the tests fail them | +0 ± 0 | -4,632 ± 305 | -5,425 ± 298 | +0 ± 0 | **+451 ± 336** | -1,540 ± 219 |
| L, long con | pass the tests, wrong | +0 ± 0 | -1,673 ± 325 | -3,707 ± 208 | +0 ± 0 | -279 ± 394 | -1,837 ± 244 |
| RS, reputation sale | the tests fail them | +0 ± 0 | -54 ± 156 | -259 ± 124 | +0 ± 0 | +109 ± 276 | -113 ± 217 |
| RS, reputation sale | pass the tests, wrong | +0 ± 0 | -86 ± 148 | -92 ± 136 | +0 ± 0 | +101 ± 269 | -198 ± 224 |

### The gate on: window 13 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity | the tests fail them | +0 ± 0 | -747 ± 57 | -1,125 ± 20 | +0 ± 0 | -246 ± 75 | -1,074 ± 26 |
| B, one identity | pass the tests, wrong | +0 ± 0 | -88 ± 95 | -1,061 ± 27 | +0 ± 0 | -602 ± 67 | -1,103 ± 27 |
| S, free identities | the tests fail them | +0 ± 0 | -844 ± 48 | -1,353 ± 31 | +0 ± 0 | -241 ± 68 | -1,260 ± 34 |
| S, free identities | pass the tests, wrong | +0 ± 0 | +7 ± 79 | -1,231 ± 37 | +0 ± 0 | -669 ± 65 | -1,320 ± 36 |
| T, retrier | the tests fail them | +0 ± 0 | -2,142 ± 76 | -2,906 ± 51 | +0 ± 0 | -943 ± 113 | -2,808 ± 54 |
| T, retrier | pass the tests, wrong | +0 ± 0 | -368 ± 128 | -2,769 ± 56 | +0 ± 0 | -1,793 ± 92 | -2,874 ± 59 |
| Tf, retrier, new identities | the tests fail them | +0 ± 0 | -11,815 ± 411 | -26,348 ± 706 | +0 ± 0 | -4,214 ± 252 | -23,596 ± 664 |
| Tf, retrier, new identities | pass the tests, wrong | +0 ± 0 | -1,895 ± 209 | -22,280 ± 614 | +0 ± 0 | -8,872 ± 329 | -25,325 ± 669 |
| L, long con | the tests fail them | +0 ± 0 | -4,632 ± 305 | -5,425 ± 298 | +0 ± 0 | **+451 ± 336** | -1,540 ± 219 |
| L, long con | pass the tests, wrong | +0 ± 0 | -1,673 ± 325 | -3,707 ± 208 | +0 ± 0 | -279 ± 394 | -1,837 ± 244 |
| RS, reputation sale | the tests fail them | +0 ± 0 | -54 ± 156 | -259 ± 124 | +0 ± 0 | +109 ± 276 | -113 ± 217 |
| RS, reputation sale | pass the tests, wrong | +0 ± 0 | -86 ± 148 | -92 ± 136 | +0 ± 0 | +101 ± 269 | -198 ± 224 |

### The gate on: window 26 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity | the tests fail them | +0 ± 0 | -747 ± 57 | -1,125 ± 20 | +0 ± 0 | -246 ± 75 | -1,074 ± 26 |
| B, one identity | pass the tests, wrong | +0 ± 0 | -88 ± 95 | -1,061 ± 27 | +0 ± 0 | -602 ± 67 | -1,103 ± 27 |
| S, free identities | the tests fail them | +0 ± 0 | -844 ± 48 | -1,353 ± 31 | +0 ± 0 | -241 ± 68 | -1,260 ± 34 |
| S, free identities | pass the tests, wrong | +0 ± 0 | +7 ± 79 | -1,231 ± 37 | +0 ± 0 | -669 ± 65 | -1,320 ± 36 |
| T, retrier | the tests fail them | +0 ± 0 | -2,142 ± 76 | -2,906 ± 51 | +0 ± 0 | -943 ± 113 | -2,808 ± 54 |
| T, retrier | pass the tests, wrong | +0 ± 0 | -368 ± 128 | -2,769 ± 56 | +0 ± 0 | -1,793 ± 92 | -2,874 ± 59 |
| Tf, retrier, new identities | the tests fail them | +0 ± 0 | -11,815 ± 411 | -26,348 ± 706 | +0 ± 0 | -4,214 ± 252 | -23,596 ± 664 |
| Tf, retrier, new identities | pass the tests, wrong | +0 ± 0 | -1,895 ± 209 | -22,280 ± 614 | +0 ± 0 | -8,872 ± 329 | -25,325 ± 669 |
| L, long con | the tests fail them | +0 ± 0 | -4,632 ± 305 | -5,425 ± 298 | +0 ± 0 | **+451 ± 336** | -1,540 ± 219 |
| L, long con | pass the tests, wrong | +0 ± 0 | -1,673 ± 325 | -3,707 ± 208 | +0 ± 0 | -279 ± 394 | -1,837 ± 244 |
| RS, reputation sale | the tests fail them | +0 ± 0 | -54 ± 156 | -259 ± 124 | +0 ± 0 | +109 ± 276 | -113 ± 217 |
| RS, reputation sale | pass the tests, wrong | +0 ± 0 | -86 ± 148 | -92 ± 136 | +0 ± 0 | +101 ± 269 | -198 ± 224 |

### The gate on, contenders' tests counted: window 13 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity | the tests fail them | -169 ± 113 | -748 ± 57 | -1,125 ± 20 | **+803 ± 157** | -244 ± 77 | -1,075 ± 26 |
| B, one identity | pass the tests, wrong | **+1,472 ± 194** | -88 ± 95 | -1,062 ± 27 | **+668 ± 285** | -602 ± 67 | -1,103 ± 27 |
| S, free identities | the tests fail them | -348 ± 62 | -844 ± 48 | -1,353 ± 31 | **+640 ± 68** | -239 ± 68 | -1,259 ± 33 |
| S, free identities | pass the tests, wrong | **+1,126 ± 93** | +7 ± 80 | -1,231 ± 37 | -16 ± 85 | -670 ± 66 | -1,320 ± 36 |
| T, retrier | the tests fail them | -822 ± 180 | -2,152 ± 80 | -2,910 ± 52 | **+1,522 ± 201** | -948 ± 113 | -2,808 ± 54 |
| T, retrier | pass the tests, wrong | **+3,399 ± 319** | -380 ± 124 | -2,769 ± 56 | **+2,837 ± 953** | -1,793 ± 92 | -2,874 ± 59 |
| Tf, retrier, new identities | the tests fail them | -4,662 ± 237 | -11,822 ± 412 | -26,357 ± 710 | **+1,556 ± 112** | -4,211 ± 253 | -23,596 ± 664 |
| Tf, retrier, new identities | pass the tests, wrong | **+3,026 ± 140** | -1,898 ± 208 | -22,280 ± 614 | -1,903 ± 213 | -8,872 ± 329 | -25,325 ± 669 |
| L, long con | the tests fail them | -2,941 ± 380 | -4,636 ± 306 | -5,406 ± 290 | **+2,950 ± 492** | **+364 ± 343** | -1,499 ± 211 |
| L, long con | pass the tests, wrong | **+2,376 ± 684** | -1,697 ± 320 | -3,711 ± 208 | **+2,876 ± 656** | -312 ± 386 | -1,824 ± 248 |
| RS, reputation sale | the tests fail them | +61 ± 168 | -51 ± 151 | -234 ± 117 | +264 ± 269 | +57 ± 259 | -146 ± 196 |
| RS, reputation sale | pass the tests, wrong | **+155 ± 154** | -81 ± 151 | -98 ± 136 | **+430 ± 355** | +65 ± 260 | -198 ± 224 |

### The sybil of three: window 6 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -401 ± 136 | -990 ± 59 | -1,360 ± 21 | **+570 ± 168** | -583 ± 77 | -1,398 ± 28 |
| B, one identity with the sybil | pass the tests, wrong | **+1,202 ± 207** | -310 ± 96 | -1,295 ± 27 | **+255 ± 199** | -912 ± 69 | -1,431 ± 31 |
| S, free identities with the sybil | the tests fail them | -634 ± 55 | -1,105 ± 47 | -1,605 ± 31 | **+323 ± 67** | -577 ± 71 | -1,591 ± 36 |
| S, free identities with the sybil | pass the tests, wrong | **+866 ± 94** | -266 ± 79 | -1,472 ± 38 | -348 ± 87 | -999 ± 65 | -1,650 ± 38 |
| T, retrier with the sybil | the tests fail them | -1,086 ± 167 | -2,363 ± 71 | -3,167 ± 61 | **+1,361 ± 217** | -1,282 ± 130 | -3,142 ± 60 |
| T, retrier with the sybil | pass the tests, wrong | **+3,389 ± 335** | -647 ± 113 | -3,031 ± 63 | **+3,001 ± 991** | -2,070 ± 90 | -3,214 ± 52 |
| Tf, retrier, new identities with the sybil | the tests fail them | -5,136 ± 240 | -12,052 ± 404 | -26,683 ± 707 | **+1,256 ± 125** | -4,513 ± 257 | -23,927 ± 645 |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+2,850 ± 141** | -2,149 ± 210 | -22,615 ± 623 | -2,346 ± 220 | -9,294 ± 325 | -25,646 ± 673 |
| L, long con with the sybil | the tests fail them | **+5,874 ± 339** | -4,690 ± 298 | -5,602 ± 263 | **+5,827 ± 514** | -43 ± 362 | -1,574 ± 260 |
| L, long con with the sybil | pass the tests, wrong | **+10,742 ± 658** | -2,056 ± 358 | -4,022 ± 234 | **+5,743 ± 650** | -520 ± 410 | -2,117 ± 329 |
| RS, reputation sale with the sybil | the tests fail them | **+8,915 ± 302** | -420 ± 161 | -486 ± 142 | **+3,165 ± 297** | -289 ± 274 | -522 ± 228 |
| RS, reputation sale with the sybil | pass the tests, wrong | **+9,101 ± 301** | -253 ± 138 | -332 ± 131 | **+3,254 ± 297** | -168 ± 246 | -491 ± 234 |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -3,068 ± 356 | -4,399 ± 302 | -5,339 ± 290 | **+3,001 ± 522** | +194 ± 387 | -1,288 ± 268 |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+1,801 ± 602** | -1,760 ± 337 | -3,750 ± 242 | **+2,916 ± 633** | -262 ± 440 | -1,892 ± 282 |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | +15 ± 206 | -185 ± 178 | -181 ± 188 | +259 ± 281 | -89 ± 213 | -174 ± 195 |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+201 ± 189** | +36 ± 172 | -14 ± 140 | **+348 ± 288** | +15 ± 258 | -109 ± 227 |

### The sybil of three: window 13 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -221 ± 147 | -842 ± 53 | -1,211 ± 24 | **+708 ± 144** | -401 ± 60 | -1,199 ± 25 |
| B, one identity with the sybil | pass the tests, wrong | **+1,326 ± 208** | -179 ± 86 | -1,154 ± 27 | **+541 ± 215** | -677 ± 75 | -1,224 ± 24 |
| S, free identities with the sybil | the tests fail them | -451 ± 56 | -932 ± 47 | -1,447 ± 32 | **+503 ± 71** | -375 ± 67 | -1,384 ± 36 |
| S, free identities with the sybil | pass the tests, wrong | **+1,024 ± 90** | -106 ± 79 | -1,325 ± 34 | -141 ± 84 | -787 ± 66 | -1,433 ± 37 |
| T, retrier with the sybil | the tests fail them | -954 ± 176 | -2,226 ± 59 | -2,991 ± 61 | **+1,460 ± 203** | -1,128 ± 112 | -2,962 ± 62 |
| T, retrier with the sybil | pass the tests, wrong | **+3,680 ± 384** | -472 ± 119 | -2,880 ± 58 | **+3,013 ± 1,054** | -1,855 ± 101 | -3,021 ± 58 |
| Tf, retrier, new identities with the sybil | the tests fail them | -4,946 ± 246 | -11,932 ± 402 | -26,506 ± 714 | **+1,447 ± 123** | -4,320 ± 259 | -23,739 ± 662 |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+2,973 ± 142** | -2,001 ± 210 | -22,448 ± 604 | -2,126 ± 224 | -8,970 ± 332 | -25,494 ± 658 |
| L, long con with the sybil | the tests fail them | **+5,865 ± 375** | -4,660 ± 272 | -5,556 ± 270 | **+5,770 ± 519** | +283 ± 348 | -1,474 ± 270 |
| L, long con with the sybil | pass the tests, wrong | **+11,390 ± 650** | -1,558 ± 329 | -3,840 ± 190 | **+6,420 ± 619** | -341 ± 352 | -1,935 ± 332 |
| RS, reputation sale with the sybil | the tests fail them | **+9,302 ± 267** | -51 ± 128 | -158 ± 115 | **+3,254 ± 285** | -38 ± 216 | -230 ± 219 |
| RS, reputation sale with the sybil | pass the tests, wrong | **+9,117 ± 311** | -213 ± 141 | -372 ± 159 | **+3,222 ± 281** | -136 ± 227 | -477 ± 177 |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -3,267 ± 381 | -4,554 ± 286 | -5,469 ± 298 | **+2,736 ± 530** | +317 ± 424 | -1,423 ± 285 |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+2,257 ± 598** | -1,455 ± 325 | -3,757 ± 208 | **+3,386 ± 718** | -255 ± 432 | -1,912 ± 318 |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | **+275 ± 204** | +108 ± 177 | +38 ± 153 | +89 ± 247 | -81 ± 229 | -127 ± 211 |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | +91 ± 202 | -15 ± 175 | -146 ± 133 | +57 ± 302 | -195 ± 255 | -340 ± 232 |

### The sybil of three: window 26 weeks ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -172 ± 152 | -815 ± 55 | -1,176 ± 22 | **+676 ± 140** | -340 ± 71 | -1,144 ± 28 |
| B, one identity with the sybil | pass the tests, wrong | **+1,395 ± 194** | -152 ± 88 | -1,104 ± 29 | **+581 ± 251** | -615 ± 87 | -1,173 ± 25 |
| S, free identities with the sybil | the tests fail them | -428 ± 59 | -902 ± 44 | -1,409 ± 30 | **+564 ± 64** | -316 ± 63 | -1,339 ± 37 |
| S, free identities with the sybil | pass the tests, wrong | **+1,062 ± 90** | -65 ± 77 | -1,281 ± 38 | -95 ± 88 | -737 ± 66 | -1,390 ± 38 |
| T, retrier with the sybil | the tests fail them | -916 ± 167 | -2,170 ± 66 | -2,968 ± 62 | **+1,596 ± 200** | -1,067 ± 107 | -2,897 ± 57 |
| T, retrier with the sybil | pass the tests, wrong | **+3,643 ± 348** | -440 ± 119 | -2,829 ± 54 | **+3,109 ± 1,015** | -1,818 ± 99 | -2,974 ± 49 |
| Tf, retrier, new identities with the sybil | the tests fail them | -4,866 ± 236 | -11,863 ± 423 | -26,502 ± 723 | **+1,519 ± 120** | -4,309 ± 259 | -23,765 ± 636 |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+3,000 ± 143** | -1,975 ± 205 | -22,355 ± 608 | -2,092 ± 217 | -8,944 ± 324 | -25,441 ± 649 |
| L, long con with the sybil | the tests fail them | **+6,026 ± 277** | -4,704 ± 296 | -5,487 ± 244 | **+6,002 ± 585** | +320 ± 425 | -1,221 ± 230 |
| L, long con with the sybil | pass the tests, wrong | **+10,959 ± 640** | -1,585 ± 337 | -3,772 ± 221 | **+6,495 ± 683** | -180 ± 412 | -1,914 ± 281 |
| RS, reputation sale with the sybil | the tests fail them | **+9,202 ± 252** | -153 ± 137 | -213 ± 139 | **+3,375 ± 322** | -96 ± 207 | -358 ± 224 |
| RS, reputation sale with the sybil | pass the tests, wrong | **+9,154 ± 294** | -186 ± 151 | -341 ± 151 | **+3,282 ± 275** | -42 ± 226 | -452 ± 209 |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -3,167 ± 332 | -4,667 ± 282 | -5,494 ± 223 | **+2,972 ± 512** | +304 ± 398 | -1,205 ± 222 |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+1,766 ± 568** | -1,546 ± 354 | -3,772 ± 229 | **+3,465 ± 735** | -119 ± 466 | -1,903 ± 251 |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | **+187 ± 163** | +27 ± 161 | +8 ± 167 | **+434 ± 283** | +73 ± 265 | -47 ± 246 |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | +140 ± 160 | +30 ± 137 | -103 ± 105 | **+341 ± 277** | +110 ± 243 | -134 ± 210 |

### The design's options against the sybil (1 honest solver, 13 weeks): its fixes cost $43 to write ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -934 ± 152 | – | – | -207 ± 145 | – | – |
| B, one identity with the sybil | pass the tests, wrong | **+621 ± 207** | – | – | -404 ± 210 | – | – |
| S, free identities with the sybil | the tests fail them | -1,162 ± 61 | – | – | -393 ± 89 | – | – |
| S, free identities with the sybil | pass the tests, wrong | **+312 ± 89** | – | – | -1,038 ± 95 | – | – |
| T, retrier with the sybil | the tests fail them | -1,665 ± 178 | – | – | **+505 ± 208** | – | – |
| T, retrier with the sybil | pass the tests, wrong | **+2,966 ± 384** | – | – | **+2,048 ± 1,054** | – | – |
| Tf, retrier, new identities with the sybil | the tests fail them | -5,668 ± 254 | – | – | **+510 ± 135** | – | – |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+2,271 ± 143** | – | – | -3,090 ± 230 | – | – |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -3,248 ± 379 | – | – | **+2,709 ± 530** | – | – |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+2,274 ± 595** | – | – | **+3,367 ± 721** | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | **+262 ± 197** | – | – | +76 ± 230 | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | +91 ± 198 | – | – | +74 ± 291 | – | – |

### The design's options against the sybil (1 honest solver, 13 weeks): minimum 5 (it keeps 5) ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -230 ± 151 | – | – | **+566 ± 129** | – | – |
| B, one identity with the sybil | pass the tests, wrong | **+1,457 ± 218** | – | – | **+479 ± 267** | – | – |
| S, free identities with the sybil | the tests fail them | -529 ± 55 | – | – | **+435 ± 68** | – | – |
| S, free identities with the sybil | pass the tests, wrong | **+955 ± 88** | – | – | -253 ± 80 | – | – |
| T, retrier with the sybil | the tests fail them | -1,037 ± 163 | – | – | **+1,508 ± 215** | – | – |
| T, retrier with the sybil | pass the tests, wrong | **+3,391 ± 325** | – | – | **+2,997 ± 1,068** | – | – |
| Tf, retrier, new identities with the sybil | the tests fail them | -4,981 ± 236 | – | – | **+1,334 ± 112** | – | – |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+2,910 ± 137** | – | – | -2,240 ± 211 | – | – |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -3,198 ± 418 | – | – | **+2,996 ± 517** | – | – |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+1,878 ± 603** | – | – | **+3,203 ± 616** | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | +186 ± 207 | – | – | -39 ± 233 | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | +39 ± 212 | – | – | **+411 ± 317** | – | – |

### The design's options against the sybil (1 honest solver, 13 weeks): minimum 10 (it keeps 10) ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -466 ± 114 | – | – | **+308 ± 118** | – | – |
| B, one identity with the sybil | pass the tests, wrong | **+1,152 ± 208** | – | – | +259 ± 260 | – | – |
| S, free identities with the sybil | the tests fail them | -672 ± 54 | – | – | **+205 ± 69** | – | – |
| S, free identities with the sybil | pass the tests, wrong | **+801 ± 94** | – | – | -443 ± 88 | – | – |
| T, retrier with the sybil | the tests fail them | -1,055 ± 206 | – | – | **+1,302 ± 230** | – | – |
| T, retrier with the sybil | pass the tests, wrong | **+3,244 ± 340** | – | – | **+2,894 ± 1,035** | – | – |
| Tf, retrier, new identities with the sybil | the tests fail them | -5,162 ± 241 | – | – | **+1,152 ± 109** | – | – |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+2,754 ± 146** | – | – | -2,436 ± 221 | – | – |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -3,050 ± 362 | – | – | **+2,658 ± 607** | – | – |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | **+1,615 ± 554** | – | – | **+3,017 ± 664** | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | +67 ± 180 | – | – | **+381 ± 274** | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | +183 ± 212 | – | – | **+590 ± 387** | – | – |

### The design's options against the sybil (1 honest solver, 13 weeks): deposit 1,000 all year ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -1,373 ± 101 | – | – | -266 ± 125 | – | – |
| B, one identity with the sybil | pass the tests, wrong | **+332 ± 184** | – | – | -940 ± 143 | – | – |
| S, free identities with the sybil | the tests fail them | -1,540 ± 67 | – | – | -487 ± 75 | – | – |
| S, free identities with the sybil | pass the tests, wrong | +82 ± 95 | – | – | -1,197 ± 91 | – | – |
| T, retrier with the sybil | the tests fail them | -4,162 ± 249 | – | – | -59 ± 208 | – | – |
| T, retrier with the sybil | pass the tests, wrong | **+2,373 ± 383** | – | – | -1,480 ± 779 | – | – |
| Tf, retrier, new identities with the sybil | the tests fail them | -12,908 ± 562 | – | – | -868 ± 198 | – | – |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | **+1,369 ± 198** | – | – | -6,638 ± 502 | – | – |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -7,975 ± 410 | – | – | **+617 ± 475** | – | – |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | -613 ± 518 | – | – | -1,109 ± 667 | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | -32 ± 198 | – | – | -43 ± 254 | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | -21 ± 211 | – | – | -292 ± 316 | – | – |

### The design's options against the sybil (1 honest solver, 13 weeks): deposit 2,500 all year ($ a year against the twin, ± 2 SE; bold: above its twin)

| Attacker | Bad fixes | Opus 5.5, 1 solver | Opus 5.5, 3 solvers | Opus 5.5, 10 solvers | GPT-6.1, 1 solver | GPT-6.1, 3 solvers | GPT-6.1, 10 solvers |
|---|---|---|---|---|---|---|---|
| B, one identity with the sybil | the tests fail them | -3,102 ± 114 | – | – | -1,727 ± 107 | – | – |
| B, one identity with the sybil | pass the tests, wrong | -1,159 ± 155 | – | – | -3,161 ± 176 | – | – |
| S, free identities with the sybil | the tests fail them | -3,174 ± 91 | – | – | -1,974 ± 91 | – | – |
| S, free identities with the sybil | pass the tests, wrong | -1,331 ± 108 | – | – | -2,780 ± 109 | – | – |
| T, retrier with the sybil | the tests fail them | -35,772 ± 3,058 | – | – | -6,653 ± 785 | – | – |
| T, retrier with the sybil | pass the tests, wrong | -1,993 ± 714 | – | – | -48,623 ± 5,326 | – | – |
| Tf, retrier, new identities with the sybil | the tests fail them | -106,545 ± 4,807 | – | – | -12,845 ± 1,189 | – | – |
| Tf, retrier, new identities with the sybil | pass the tests, wrong | -4,661 ± 829 | – | – | -59,009 ± 4,544 | – | – |
| L, long con with the sybil (its twin keeps the identities too) | the tests fail them | -15,037 ± 628 | – | – | -2,561 ± 461 | – | – |
| L, long con with the sybil (its twin keeps the identities too) | pass the tests, wrong | -4,918 ± 467 | – | – | -7,852 ± 736 | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | the tests fail them | -493 ± 287 | – | – | -241 ± 273 | – | – |
| RS, reputation sale with the sybil (its twin keeps the identities too) | pass the tests, wrong | -189 ± 231 | – | – | -814 ± 371 | – | – |

### What the sybil's identities cost it (1 honest solver)

| Rows | Its fixes a year | Of them passed | Mainnet-like fees ($ a year: judges' fee $5.03 + $0.50) | Sepolia at $40 a fix: faucet requests a year | First pledge (week) | Pledges taken (% of the year) |
|---|---|---|---|---|---|---|
| sybil: window 6 weeks | 50.3 | 39.0 | 278 | 101 | 0.2 | 99.6 |
| sybil: window 13 weeks | 19.2 | 15.0 | 106 | 38 | 0.2 | 99.6 |
| sybil: window 26 weeks | 11.5 | 9.0 | 64 | 23 | 0.2 | 99.6 |
| options: its fixes cost $43 to write | 19.2 | 15.0 | 106 | 38 | 0.2 | 99.6 |
| options: minimum 5 (it keeps 5) | 32.0 | 25.0 | 177 | 64 | 0.2 | 99.5 |
| options: minimum 10 (it keeps 10) | 64.3 | 50.0 | 356 | 129 | 0.3 | 99.4 |
| options: deposit 1,000 all year | 19.2 | 15.0 | 106 | 38 | 0.2 | 99.6 |
| options: deposit 2,500 all year | 19.2 | 15.0 | 106 | 38 | 0.2 | 99.6 |

### A fresh repository with honest solvers only

| Counted | Issues a week | Window | Seated | Honest solvers | First pledge (week) | Never in the year | Pledges taken (% of the year) | Shut again (a year) | Funding refused (%) | Honest good fixes unpaid | …their bounties ($) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| repository | 30 | 6 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 1,056.5 ± 10.0 | 108,174 ± 1,379 |
| repository | 30 | 6 | Opus 5.5 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 6.7 ± 0.7 | 668 ± 90 |
| repository | 30 | 6 | Opus 5.5 | 10 | 0.2 ± 0.0 | 0 % | 99.6 ± 0.0 | 0.0 ± 0.0 | 0.4 ± 0.0 | 4.5 ± 0.4 | 441 ± 57 |
| repository | 30 | 6 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 793.0 ± 8.1 | 81,267 ± 1,081 |
| repository | 30 | 6 | GPT-6.1 | 3 | 0.4 ± 0.0 | 0 % | 99.3 ± 0.1 | 0.0 ± 0.0 | 0.7 ± 0.1 | 5.7 ± 0.7 | 564 ± 79 |
| repository | 30 | 6 | GPT-6.1 | 10 | 0.3 ± 0.0 | 0 % | 99.5 ± 0.1 | 0.0 ± 0.0 | 0.4 ± 0.1 | 4.0 ± 0.4 | 385 ± 50 |
| repository | 30 | 13 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 1,056.5 ± 10.0 | 108,174 ± 1,379 |
| repository | 30 | 13 | Opus 5.5 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 6.7 ± 0.7 | 668 ± 90 |
| repository | 30 | 13 | Opus 5.5 | 10 | 0.2 ± 0.0 | 0 % | 99.6 ± 0.0 | 0.0 ± 0.0 | 0.4 ± 0.0 | 4.5 ± 0.4 | 441 ± 57 |
| repository | 30 | 13 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 793.0 ± 8.1 | 81,267 ± 1,081 |
| repository | 30 | 13 | GPT-6.1 | 3 | 0.4 ± 0.0 | 0 % | 99.3 ± 0.1 | 0.0 ± 0.0 | 0.7 ± 0.1 | 5.7 ± 0.7 | 564 ± 79 |
| repository | 30 | 13 | GPT-6.1 | 10 | 0.3 ± 0.0 | 0 % | 99.5 ± 0.1 | 0.0 ± 0.0 | 0.4 ± 0.1 | 4.0 ± 0.4 | 385 ± 50 |
| repository | 30 | 26 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 1,056.5 ± 10.0 | 108,174 ± 1,379 |
| repository | 30 | 26 | Opus 5.5 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 6.7 ± 0.7 | 668 ± 90 |
| repository | 30 | 26 | Opus 5.5 | 10 | 0.2 ± 0.0 | 0 % | 99.6 ± 0.0 | 0.0 ± 0.0 | 0.4 ± 0.0 | 4.5 ± 0.4 | 441 ± 57 |
| repository | 30 | 26 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 793.0 ± 8.1 | 81,267 ± 1,081 |
| repository | 30 | 26 | GPT-6.1 | 3 | 0.4 ± 0.0 | 0 % | 99.3 ± 0.1 | 0.0 ± 0.0 | 0.7 ± 0.1 | 5.7 ± 0.7 | 564 ± 79 |
| repository | 30 | 26 | GPT-6.1 | 10 | 0.3 ± 0.0 | 0 % | 99.5 ± 0.1 | 0.0 ± 0.0 | 0.4 ± 0.1 | 4.0 ± 0.4 | 385 ± 50 |
| repository | 5 | 6 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 177.1 ± 3.8 | 18,280 ± 471 |
| repository | 5 | 6 | Opus 5.5 | 3 | 1.7 ± 0.2 | 0 % | 96.7 ± 0.5 | 0.1 ± 0.1 | 3.3 ± 0.5 | 5.9 ± 0.7 | 568 ± 80 |
| repository | 5 | 6 | Opus 5.5 | 10 | 1.1 ± 0.1 | 0 % | 97.9 ± 0.3 | 0.0 ± 0.0 | 1.8 ± 0.2 | 3.5 ± 0.2 | 334 ± 37 |
| repository | 5 | 6 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 134.4 ± 3.1 | 13,961 ± 423 |
| repository | 5 | 6 | GPT-6.1 | 3 | 1.9 ± 0.3 | 0 % | 95.5 ± 0.8 | 0.5 ± 0.2 | 4.2 ± 0.8 | 6.2 ± 1.1 | 616 ± 127 |
| repository | 5 | 6 | GPT-6.1 | 10 | 1.3 ± 0.2 | 0 % | 97.6 ± 0.4 | 0.0 ± 0.0 | 2.2 ± 0.3 | 3.4 ± 0.3 | 322 ± 39 |
| repository | 5 | 13 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 177.1 ± 3.8 | 18,280 ± 471 |
| repository | 5 | 13 | Opus 5.5 | 3 | 1.7 ± 0.2 | 0 % | 96.8 ± 0.5 | 0.0 ± 0.0 | 3.1 ± 0.4 | 5.7 ± 0.7 | 546 ± 77 |
| repository | 5 | 13 | Opus 5.5 | 10 | 1.1 ± 0.1 | 0 % | 97.9 ± 0.3 | 0.0 ± 0.0 | 1.8 ± 0.2 | 3.5 ± 0.2 | 334 ± 37 |
| repository | 5 | 13 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 134.4 ± 3.1 | 13,961 ± 423 |
| repository | 5 | 13 | GPT-6.1 | 3 | 1.9 ± 0.3 | 0 % | 96.4 ± 0.5 | 0.0 ± 0.0 | 3.3 ± 0.4 | 5.0 ± 0.6 | 483 ± 65 |
| repository | 5 | 13 | GPT-6.1 | 10 | 1.3 ± 0.2 | 0 % | 97.6 ± 0.4 | 0.0 ± 0.0 | 2.2 ± 0.3 | 3.4 ± 0.3 | 322 ± 39 |
| repository | 5 | 26 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 177.1 ± 3.8 | 18,280 ± 471 |
| repository | 5 | 26 | Opus 5.5 | 3 | 1.7 ± 0.2 | 0 % | 96.8 ± 0.5 | 0.0 ± 0.0 | 3.1 ± 0.4 | 5.7 ± 0.7 | 546 ± 77 |
| repository | 5 | 26 | Opus 5.5 | 10 | 1.1 ± 0.1 | 0 % | 97.9 ± 0.3 | 0.0 ± 0.0 | 1.8 ± 0.2 | 3.5 ± 0.2 | 334 ± 37 |
| repository | 5 | 26 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 134.4 ± 3.1 | 13,961 ± 423 |
| repository | 5 | 26 | GPT-6.1 | 3 | 1.9 ± 0.3 | 0 % | 96.4 ± 0.5 | 0.0 ± 0.0 | 3.3 ± 0.4 | 5.0 ± 0.6 | 483 ± 65 |
| repository | 5 | 26 | GPT-6.1 | 10 | 1.3 ± 0.2 | 0 % | 97.6 ± 0.4 | 0.0 ± 0.0 | 2.2 ± 0.3 | 3.4 ± 0.3 | 322 ± 39 |
| repository | 1 | 6 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 37.0 ± 1.9 | 3,762 ± 234 |
| repository | 1 | 6 | Opus 5.5 | 3 | 8.5 ± 1.4 | 0 % | 42.0 ± 3.9 | 5.0 ± 0.4 | 58.5 ± 4.2 | 21.7 ± 1.3 | 2,173 ± 153 |
| repository | 1 | 6 | Opus 5.5 | 10 | 5.6 ± 1.1 | 0 % | 71.1 ± 3.5 | 4.5 ± 0.7 | 28.3 ± 3.7 | 10.4 ± 0.9 | 1,018 ± 88 |
| repository | 1 | 6 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 28.5 ± 1.7 | 2,926 ± 217 |
| repository | 1 | 6 | GPT-6.1 | 3 | 10.6 ± 2.4 | 0 % | 32.4 ± 4.4 | 4.3 ± 0.5 | 68.5 ± 5.3 | 19.4 ± 1.0 | 1,959 ± 134 |
| repository | 1 | 6 | GPT-6.1 | 10 | 6.3 ± 1.1 | 0 % | 58.6 ± 4.1 | 4.7 ± 0.6 | 43.2 ± 5.3 | 11.9 ± 1.1 | 1,205 ± 140 |
| repository | 1 | 13 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 37.0 ± 1.9 | 3,762 ± 234 |
| repository | 1 | 13 | Opus 5.5 | 3 | 8.1 ± 1.2 | 0 % | 78.6 ± 3.3 | 1.1 ± 0.2 | 21.8 ± 3.9 | 8.0 ± 1.2 | 778 ± 125 |
| repository | 1 | 13 | Opus 5.5 | 10 | 5.1 ± 0.7 | 0 % | 89.6 ± 1.5 | 0.1 ± 0.1 | 9.0 ± 1.5 | 3.6 ± 0.3 | 339 ± 42 |
| repository | 1 | 13 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 28.5 ± 1.7 | 2,926 ± 217 |
| repository | 1 | 13 | GPT-6.1 | 3 | 9.1 ± 1.4 | 0 % | 70.6 ± 5.0 | 1.5 ± 0.3 | 29.9 ± 5.1 | 8.4 ± 1.0 | 846 ± 110 |
| repository | 1 | 13 | GPT-6.1 | 10 | 6.1 ± 1.0 | 0 % | 86.6 ± 2.4 | 0.4 ± 0.2 | 13.3 ± 2.6 | 3.8 ± 0.4 | 392 ± 63 |
| repository | 1 | 26 | Opus 5.5 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 37.0 ± 1.9 | 3,762 ± 234 |
| repository | 1 | 26 | Opus 5.5 | 3 | 8.1 ± 1.2 | 0 % | 84.4 ± 2.3 | 0.0 ± 0.0 | 14.8 ± 2.3 | 5.6 ± 0.7 | 536 ± 78 |
| repository | 1 | 26 | Opus 5.5 | 10 | 5.1 ± 0.7 | 0 % | 90.1 ± 1.4 | 0.0 ± 0.0 | 8.4 ± 1.3 | 3.5 ± 0.2 | 324 ± 38 |
| repository | 1 | 26 | GPT-6.1 | 1 | never | 100 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 100.0 ± 0.0 | 28.5 ± 1.7 | 2,926 ± 217 |
| repository | 1 | 26 | GPT-6.1 | 3 | 9.1 ± 1.4 | 0 % | 82.4 ± 2.7 | 0.0 ± 0.0 | 16.3 ± 2.3 | 5.0 ± 0.6 | 482 ± 64 |
| repository | 1 | 26 | GPT-6.1 | 10 | 6.1 ± 1.0 | 0 % | 88.4 ± 1.9 | 0.0 ± 0.0 | 10.5 ± 1.5 | 3.4 ± 0.3 | 319 ± 39 |
| anyone | 30 | 6 | Opus 5.5 | 1 | 2.2 ± 0.4 | 0 % | 93.7 ± 1.7 | 0.8 ± 0.3 | 6.4 ± 1.6 | 67.9 ± 17.2 | 6,929 ± 1,759 |
| anyone | 30 | 6 | Opus 5.5 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 6.3 ± 0.8 | 621 ± 92 |
| anyone | 30 | 6 | Opus 5.5 | 10 | 0.2 ± 0.0 | 0 % | 99.6 ± 0.0 | 0.0 ± 0.0 | 0.4 ± 0.0 | 4.4 ± 0.4 | 423 ± 59 |
| anyone | 30 | 6 | GPT-6.1 | 1 | 1.6 ± 0.3 | 0 % | 96.0 ± 1.1 | 0.2 ± 0.1 | 4.1 ± 1.1 | 32.7 ± 9.2 | 3,375 ± 962 |
| anyone | 30 | 6 | GPT-6.1 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 5.1 ± 0.7 | 501 ± 81 |
| anyone | 30 | 6 | GPT-6.1 | 10 | 0.2 ± 0.0 | 0 % | 99.5 ± 0.1 | 0.0 ± 0.0 | 0.4 ± 0.1 | 3.8 ± 0.4 | 363 ± 50 |
| anyone | 30 | 13 | Opus 5.5 | 1 | 2.2 ± 0.4 | 0 % | 95.8 ± 0.8 | 0.0 ± 0.0 | 4.3 ± 0.8 | 46.2 ± 9.0 | 4,703 ± 950 |
| anyone | 30 | 13 | Opus 5.5 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 6.3 ± 0.8 | 621 ± 92 |
| anyone | 30 | 13 | Opus 5.5 | 10 | 0.2 ± 0.0 | 0 % | 99.6 ± 0.0 | 0.0 ± 0.0 | 0.4 ± 0.0 | 4.4 ± 0.4 | 423 ± 59 |
| anyone | 30 | 13 | GPT-6.1 | 1 | 1.6 ± 0.3 | 0 % | 97.0 ± 0.6 | 0.0 ± 0.0 | 3.2 ± 0.7 | 25.4 ± 5.1 | 2,625 ± 540 |
| anyone | 30 | 13 | GPT-6.1 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 5.1 ± 0.7 | 501 ± 81 |
| anyone | 30 | 13 | GPT-6.1 | 10 | 0.2 ± 0.0 | 0 % | 99.5 ± 0.1 | 0.0 ± 0.0 | 0.4 ± 0.1 | 3.8 ± 0.4 | 363 ± 50 |
| anyone | 30 | 26 | Opus 5.5 | 1 | 2.2 ± 0.4 | 0 % | 95.8 ± 0.8 | 0.0 ± 0.0 | 4.3 ± 0.8 | 46.2 ± 9.0 | 4,703 ± 950 |
| anyone | 30 | 26 | Opus 5.5 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 6.3 ± 0.8 | 621 ± 92 |
| anyone | 30 | 26 | Opus 5.5 | 10 | 0.2 ± 0.0 | 0 % | 99.6 ± 0.0 | 0.0 ± 0.0 | 0.4 ± 0.0 | 4.4 ± 0.4 | 423 ± 59 |
| anyone | 30 | 26 | GPT-6.1 | 1 | 1.6 ± 0.3 | 0 % | 97.0 ± 0.6 | 0.0 ± 0.0 | 3.2 ± 0.7 | 25.2 ± 5.0 | 2,604 ± 532 |
| anyone | 30 | 26 | GPT-6.1 | 3 | 0.3 ± 0.0 | 0 % | 99.4 ± 0.1 | 0.0 ± 0.0 | 0.6 ± 0.1 | 5.1 ± 0.7 | 501 ± 81 |
| anyone | 30 | 26 | GPT-6.1 | 10 | 0.2 ± 0.0 | 0 % | 99.5 ± 0.1 | 0.0 ± 0.0 | 0.4 ± 0.1 | 3.8 ± 0.4 | 363 ± 50 |
| anyone | 5 | 6 | Opus 5.5 | 1 | 15.5 ± 3.7 | 5 % | 18.9 ± 3.2 | 2.3 ± 0.4 | 81.0 ± 3.2 | 143.5 ± 6.4 | 14,769 ± 703 |
| anyone | 5 | 6 | Opus 5.5 | 3 | 1.6 ± 0.3 | 0 % | 96.9 ± 0.5 | 0.0 ± 0.0 | 2.9 ± 0.4 | 5.3 ± 0.8 | 507 ± 80 |
| anyone | 5 | 6 | Opus 5.5 | 10 | 1.0 ± 0.1 | 0 % | 98.0 ± 0.3 | 0.0 ± 0.0 | 1.7 ± 0.2 | 3.3 ± 0.3 | 310 ± 36 |
| anyone | 5 | 6 | GPT-6.1 | 1 | 10.2 ± 2.3 | 0 % | 33.2 ± 3.7 | 3.6 ± 0.5 | 67.1 ± 3.7 | 89.8 ± 5.6 | 9,334 ± 652 |
| anyone | 5 | 6 | GPT-6.1 | 3 | 1.7 ± 0.3 | 0 % | 96.7 ± 0.5 | 0.1 ± 0.1 | 3.1 ± 0.4 | 4.5 ± 0.7 | 422 ± 70 |
| anyone | 5 | 6 | GPT-6.1 | 10 | 1.2 ± 0.2 | 0 % | 97.8 ± 0.4 | 0.0 ± 0.0 | 2.0 ± 0.3 | 3.2 ± 0.3 | 300 ± 42 |
| anyone | 5 | 13 | Opus 5.5 | 1 | 13.1 ± 2.6 | 0 % | 48.0 ± 5.1 | 1.8 ± 0.3 | 52.0 ± 5.0 | 91.5 ± 9.6 | 9,288 ± 991 |
| anyone | 5 | 13 | Opus 5.5 | 3 | 1.6 ± 0.3 | 0 % | 96.9 ± 0.5 | 0.0 ± 0.0 | 2.8 ± 0.4 | 5.3 ± 0.8 | 498 ± 76 |
| anyone | 5 | 13 | Opus 5.5 | 10 | 1.0 ± 0.1 | 0 % | 98.0 ± 0.3 | 0.0 ± 0.0 | 1.7 ± 0.2 | 3.3 ± 0.3 | 310 ± 36 |
| anyone | 5 | 13 | GPT-6.1 | 1 | 9.2 ± 2.0 | 0 % | 67.5 ± 5.0 | 1.5 ± 0.3 | 33.4 ± 5.1 | 44.2 ± 6.5 | 4,584 ± 706 |
| anyone | 5 | 13 | GPT-6.1 | 3 | 1.7 ± 0.3 | 0 % | 96.7 ± 0.5 | 0.0 ± 0.0 | 3.0 ± 0.4 | 4.4 ± 0.7 | 418 ± 70 |
| anyone | 5 | 13 | GPT-6.1 | 10 | 1.2 ± 0.2 | 0 % | 97.8 ± 0.4 | 0.0 ± 0.0 | 2.0 ± 0.3 | 3.2 ± 0.3 | 300 ± 42 |
| anyone | 5 | 26 | Opus 5.5 | 1 | 12.8 ± 2.5 | 0 % | 71.2 ± 5.1 | 0.3 ± 0.2 | 29.5 ± 5.3 | 52.6 ± 9.5 | 5,364 ± 999 |
| anyone | 5 | 26 | Opus 5.5 | 3 | 1.6 ± 0.3 | 0 % | 96.9 ± 0.5 | 0.0 ± 0.0 | 2.8 ± 0.4 | 5.3 ± 0.8 | 498 ± 76 |
| anyone | 5 | 26 | Opus 5.5 | 10 | 1.0 ± 0.1 | 0 % | 98.0 ± 0.3 | 0.0 ± 0.0 | 1.7 ± 0.2 | 3.3 ± 0.3 | 310 ± 36 |
| anyone | 5 | 26 | GPT-6.1 | 1 | 9.2 ± 2.0 | 0 % | 81.0 ± 4.1 | 0.1 ± 0.1 | 20.1 ± 4.3 | 26.8 ± 5.6 | 2,778 ± 601 |
| anyone | 5 | 26 | GPT-6.1 | 3 | 1.7 ± 0.3 | 0 % | 96.7 ± 0.5 | 0.0 ± 0.0 | 3.0 ± 0.4 | 4.4 ± 0.7 | 418 ± 70 |
| anyone | 5 | 26 | GPT-6.1 | 10 | 1.2 ± 0.2 | 0 % | 97.8 ± 0.4 | 0.0 ± 0.0 | 2.0 ± 0.3 | 3.2 ± 0.3 | 300 ± 42 |
| anyone | 1 | 6 | Opus 5.5 | 1 | 28.9 ± 15.0 | 88 % | 0.9 ± 0.8 | 0.1 ± 0.1 | 98.3 ± 1.8 | 36.5 ± 2.1 | 3,709 ± 251 |
| anyone | 1 | 6 | Opus 5.5 | 3 | 7.9 ± 1.3 | 0 % | 49.5 ± 4.1 | 4.8 ± 0.4 | 50.2 ± 4.1 | 18.4 ± 1.3 | 1,831 ± 145 |
| anyone | 1 | 6 | Opus 5.5 | 10 | 5.2 ± 0.9 | 0 % | 73.2 ± 3.4 | 4.0 ± 0.6 | 25.4 ± 3.5 | 9.3 ± 0.9 | 902 ± 85 |
| anyone | 1 | 6 | GPT-6.1 | 1 | 22.4 ± 7.7 | 78 % | 1.9 ± 1.2 | 0.2 ± 0.1 | 98.2 ± 1.2 | 27.9 ± 1.8 | 2,870 ± 225 |
| anyone | 1 | 6 | GPT-6.1 | 3 | 9.0 ± 1.5 | 0 % | 43.5 ± 4.5 | 4.7 ± 0.5 | 57.6 ± 5.6 | 16.2 ± 1.3 | 1,630 ± 153 |
| anyone | 1 | 6 | GPT-6.1 | 10 | 5.9 ± 1.1 | 0 % | 64.6 ± 3.6 | 4.7 ± 0.6 | 37.7 ± 5.0 | 10.3 ± 0.9 | 1,021 ± 120 |
| anyone | 1 | 13 | Opus 5.5 | 1 | 30.6 ± 7.1 | 68 % | 3.7 ± 2.4 | 0.4 ± 0.2 | 96.3 ± 2.6 | 35.5 ± 2.2 | 3,609 ± 259 |
| anyone | 1 | 13 | Opus 5.5 | 3 | 7.7 ± 1.3 | 0 % | 81.5 ± 3.4 | 0.7 ± 0.2 | 17.7 ± 3.2 | 6.5 ± 1.1 | 623 ± 107 |
| anyone | 1 | 13 | Opus 5.5 | 10 | 4.9 ± 0.7 | 0 % | 90.0 ± 1.5 | 0.1 ± 0.1 | 8.3 ± 1.3 | 3.4 ± 0.3 | 315 ± 41 |
| anyone | 1 | 13 | GPT-6.1 | 1 | 24.1 ± 4.7 | 55 % | 6.8 ± 3.1 | 0.5 ± 0.2 | 93.3 ± 3.6 | 26.4 ± 1.8 | 2,703 ± 234 |
| anyone | 1 | 13 | GPT-6.1 | 3 | 8.3 ± 1.3 | 0 % | 78.9 ± 3.5 | 0.9 ± 0.3 | 20.4 ± 3.5 | 5.9 ± 0.9 | 580 ± 98 |
| anyone | 1 | 13 | GPT-6.1 | 10 | 5.6 ± 0.9 | 0 % | 88.2 ± 1.9 | 0.2 ± 0.2 | 10.8 ± 1.7 | 3.3 ± 0.4 | 318 ± 47 |
| anyone | 1 | 26 | Opus 5.5 | 1 | 32.8 ± 6.2 | 58 % | 11.2 ± 5.4 | 0.3 ± 0.2 | 88.7 ± 5.2 | 32.9 ± 2.7 | 3,340 ± 305 |
| anyone | 1 | 26 | Opus 5.5 | 3 | 7.7 ± 1.3 | 0 % | 85.1 ± 2.4 | 0.0 ± 0.0 | 13.4 ± 1.9 | 5.2 ± 0.8 | 490 ± 77 |
| anyone | 1 | 26 | Opus 5.5 | 10 | 4.9 ± 0.7 | 0 % | 90.6 ± 1.4 | 0.0 ± 0.0 | 7.9 ± 1.1 | 3.2 ± 0.2 | 304 ± 35 |
| anyone | 1 | 26 | GPT-6.1 | 1 | 26.7 ± 4.2 | 40 % | 20.5 ± 6.6 | 0.5 ± 0.2 | 80.6 ± 7.2 | 22.6 ± 2.6 | 2,308 ± 292 |
| anyone | 1 | 26 | GPT-6.1 | 3 | 8.3 ± 1.3 | 0 % | 84.1 ± 2.5 | 0.0 ± 0.0 | 14.4 ± 2.0 | 4.4 ± 0.7 | 415 ± 71 |
| anyone | 1 | 26 | GPT-6.1 | 10 | 5.6 ± 0.9 | 0 % | 89.1 ± 1.8 | 0.0 ± 0.0 | 9.8 ± 1.4 | 3.1 ± 0.3 | 296 ± 43 |

