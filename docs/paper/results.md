# Paper draft: results (sections 5 and 6 of the outline)

> **Status:** a draft of the results for the owner's review (proof-of-fix#158), following [the outline](outline.md). It
> is not the paper and must not be published from this repository. Every figure is quoted from the report named next to
> it; nothing here is recomputed. Two sources are still open pull requests: `reports/potfee-v1.md` (#183) and
> `reports/cyclepool-v1.md` (#185). Their figures change if those reports do.

**Conventions.**
- All money is simulated. Amounts are dollars at 1 credit = $1, and no simulation opens a connection.
- Unless a table says otherwise, a figure is a mean over seeds and every ± is two standard errors of that mean.
- An attacker is compared with its *honest twin*: the same actor on the same seeds, behaving honestly.
- Sections 5.1 to 5.6 are simulation. Section 6 is what ran on real systems, and it says what each run does and doesn't
  show.

**The thesis these results test:**
- **The claim:** an open market for verified fixes can heal itself. Faults are tolerated, and when one pays, the
  mechanism makes it stop paying.
- **The measures:** whether each attack pays, and where the simulations allow it, how long healing takes and what it
  costs honest participants.

## 5. Results from simulation

### 5.1 Four rounds of the open-validator design

The v3 design was simulated against every attacker in section 4, with 40 seeds a round. The spec was changed after each
round, and the round was re-run.

| Round | Criteria met | What decided it | Source |
|---|---|---|---|
| v1 | 4 of 10 | A lone validator can't be trusted, the outage slash froze the fee, and an early coalition owns the rules. | `reports/open-validators-v1.md` |
| v2 | 8 of 13 | The lone validator and the seed grinder now lose, but the fee signal collapsed the market in 33 of 40 runs. | `reports/open-validators-v2.md` |
| v3 | 9 of 13 | No attacker shown to gain. Two criteria failed only on the sign of a mean too small to measure. | `reports/open-validators-v3.md` |
| v3.1 | 13 of 13 | v3's numbers re-judged under round 3's criteria. No rule changed and no number moved. | `reports/open-validators-v3.1.md` |

**What broke, and why.** This is the main contribution: each failure, and the fix that made it stop paying.

1. **A single judge.** At k = 1, a colluding genesis validator gained **+$2,920 ± 456** a year, and in none of 40 runs
   were all its bad fixes reversed before payment (v1). Longer challenge windows shrank the gain but never made it
   lose. Holding and auditing every lone verdict (round 1) turned it into a loss of **−$221 ± 38**, with 87 % of its bad
   fixes reversed before payment (v2). In v3, **98.4 % ± 1.8** of its own lone bad verdicts were reversed (184 of 187),
   and it lost **−$247 ± 41**.
2. **The fee could not find the validators' cost.** In v1 the fee sat at its $0.25 ceiling all year in every run,
   because the outage slash made large bonds unprofitable. Round 1's floor-bond wait signal let the fee only fall, and
   **33 of 40** markets collapsed (v2). Round 2 counted every wait: no run of 40 collapsed, and over the last 13 weeks
   the fee was **1.20 ± 0.04 ×** the validators' break-even (v3).
3. **Silence was free.** A bribed silent judge gained **+$317 ± 13** and a judge that sealed then withheld **+$249 ± 12**
   (v2). With a $5 slash both lost: **−$14 ± 9** and **−$15 ± 9** (v3). A larger bribe still pays: at 10 % of the
   bounty the silent judge gains **+$311 ± 21**. No slash in proportion to the bounty fixed that without breaking the
   market: at 10 % of the bounty, 3 of 40 markets collapsed (v3.1). The flat $5 stays, and the bribe above it is a named
   trust point.
4. **Early coalitions owned the rules.** Five early validators gained **+$5,196 ± 2,178** (v1). With the constitution
   drawn from 21 eligible validators and a $15 deposit, a coalition of 5 lost **−$280 ± 147** and one of 3 lost
   **−$431 ± 145**. No adding ADR passed below 21 eligible validators, and no removal below 14, in any run (v3).
5. **Criteria that misread zero-effect attacks.** In v3, two attackers failed "doesn't gain" on means indistinguishable
   from zero: the inflaters at **+$2.7 ± 3.9** and a weak family's herders at **+$0.2 ± 0.7**. Round 3 adopted "not
   shown to gain", a test on both bounds of the interval, and the same numbers met it (v3.1).

**Growth from one validator.** A small bounty reaches k ≥ 3 by **week 6 in 40 of 40 runs**, with 51 of 54 newcomers
qualifying in 15 days (v2; v3 unchanged). In v1 it took until week 18, and only 18 of 54 qualified, in 135 days.

**What still holds, unchanged since v2:**
- the sybil at 12.5 % never holds a majority of a panel of k ≥ 3;
- every proof-level attacker loses: answer shopping at 1 in 10 loses **−$13 ± 1**, but at 3 in 10 it gains **+$174 ± 46**,
  which is reported as a trust point (v3).

### 5.2 Paying for checks

Solvers pay for their own checks by metered units (check gas) instead of flat fees. Over 100 paired seeds they pay
**$5.04 per paid fix instead of $9.21 (−45 %)**. Attempts rise **+7.1 ± 1.6**, paid bounties **+1.7 ± 0.6**, and funders'
cost per paid bounty falls **−$6.82 ± 2.83** (`reports/self-healing-v1.md`). The same report sizes the seat bond: one
equivocation sold on the largest bounty needs **$1,107** of bond to lose at 50 % detection, so the bond follows bounty
size, not fees.

### 5.3 Honest validators' month: churn, not a shortage

An honest validator nets **−$1.43 ± 0.22** a month (`reports/open-validators-v3.1.md`). Split by who stays, the loss is
an average over people who tried and left:
- **validators who stayed** net **+$1.20 ± 0.18** a month (701 of them across 40 runs);
- **those who left** lost **−$2.62 ± 0.25** (1,567 of them);
- about 40 newcomers join a year and about 40 leave, against about 18 active.

(Source: proof-of-fix#142, comment 6271.)

**A token slice for validators doesn't fix it.** The market passes the subsidy on: as tokens arrive, idle validators
push the service fee down, so checks get cheaper and validators don't get richer. Their net turns positive only once the
fee reaches its $0.01 floor, at about $200 of tokens a week (+$3.47 ± 0.22 a month; #142, comment 6271). The owner
decided (2026-11-08) to judge the criterion on validators who stay, report leavers' losses as the cost of trying, and
add no slice (#142, comment 6395).

### 5.4 Rewards beyond the bounty: tokens, and the farmer

**The farmer.** It registers a repository, files real issues, funds them from accounts it controls, fixes them
properly and mints tokens. Every judge rightly passes the fixes, and the coin goes round in a circle. Each table reports
**how much of their funding honest funders get back in tokens at the point where farming starts to pay**: the higher,
the safer.

**Per-repository tokens were dropped** (`reports/repotokens-v1.md`):
- **A fixed weekly emission per repository** pays once tokens return **2–3 %**: one trivial fix a week takes the whole
  emission.
- **Minting only up to the judged value, from coin pledged by others,** holds at **89 %** against trivial issues, but
  fails once the farmer can make bugs the judges value highly. At $200 a fix with the contract's fees, it pays at
  **2 %**, and so does the protocol's single token. The judges can't see that nobody uses the repository.
- **Burning coin per token** is the only rule that holds whatever the judges say, but at a $0.05 floor honest funders
  burn about **41 %** of what they fund.

The owner dropped per-repository tokens on 2026-11-08 (`reports/repotokens-v2.md`, "Decision").

**One shared pool a cycle, split by the judges' merit** (`reports/repotokens-v2.md`):
- **It holds against trivial farming:** **97 %**.
- **It fails against faked importance:** **6 %**. Needing more funders, renewing reputation each quarter, and releasing
  tokens on realised reach all stayed at 4–9 %. Releasing on reach also cost honest projects about 11 % of their tokens.

**The hybrid:** each fix's share is capped by the bounty coin pledged by accounts other than its solver, with a fee on
that coin (`reports/repotokens-v2.md`):

| Fee on bounty coin | 0 % of fakes caught | 50 % | 80 % | 90 % |
|---|---|---|---|---|
| 0 % | 5 % | 8 % | 14 % | 21 % |
| 10 % | 18 % | 29 % | 55 % | **83 %** |
| 20 % | 27 % | 46 % | **86 %** | **95 %** |

- **Without a fee, the cap does nothing:** the farmer's coin comes back to it as the solver.
- **The fee and the judges only work together.** A 20 % fee with judges who catch nothing holds at 27 %. Judges catching
  90 % with no fee hold at 21 %.

**Dynamic fees** (`reports/potfee-v1.md`):
- **A fee by bounty size** (5 / 10 / 20 %) is worse than a flat one: **72 %** at 90 % caught against a flat 10 % fee's
  **83 %**. Honest funders paid more (13.3 %), because the farmer moved into the cheap tier.
- **A fee indexed to the pot's value** (β times the token value a dollar earns) is about three times weaker than a flat
  fee at a similar cost. At 80 % caught, β = 0.3 holds to **33 %**, against a flat 20 % fee's **86 %**. No β makes
  farming impossible, not even β = 1. The farmer's fakes are judged at the coin behind them, while honest fixes are
  judged below their bounty, so the farmer earns about 1.3 times the rate the fee is priced on.
- **Capped, it works.** The token value a dollar earns, up to 20 % of the coin, protects like a flat 20 % fee (**86 %**
  at 80 % caught, **95 %** at 90 %). Honest funders never pay more than their tokens are worth, and nearly nothing
  while the token is worth little. The cost is a dependence on a price feed.

### 5.5 Pools per repository: is inflated merit healed?

**The design:**
- Each repository has a pool each cycle, funded by investors who hold shares in proportion to what they brought.
- At the cycle's end, judges split the pool's coin among the merged fixes by merit.
- People with a claim on the repository challenge overclaims before the split, alongside the AI checks.

**The attacker:** a project's own team files 5 correct but trivial fixes a cycle, each worth $5, and claims whatever pays
it best. Up to 8 of 15 judges collude with it. The pool is $2,000 a cycle, with about 10 honest fixes. Judges see through
an overclaim 80 % of the time (`reports/cyclepool-v1.md`, 20 seeds).

- **With no defence,** the team takes **8 %** of the pool with no colluding judges, and **20–38 %** with 3–8 of 15
  colluding.
- **A stake forfeited when the claim is over 3× the merit awarded makes overclaiming lose.** That's #58 D3's rule. With
  challenges, scores, audits and the stake, and up to 5 of 15 judges colluding, the team's best response is to claim
  within the rule, and it still loses (**$−2,124 to $−465** a year). About **1 %** of the pool is overpaid. Without the
  stake, the same defences leave the team **$6,700–8,700** a year.
- **Judges' scores alone backfire under a colluding majority.** Scored by consensus, at 8 of 15 colluding, the honest
  judges look like the outliers: colluders reach **87 %** of draws, and **46 %** of the pool is overpaid, worse than no
  defence. Challenges before the split anchor consensus to the corrected merit, so the colluders lose score instead:
  **37 %** of draws in the last quarter, against 53 % with no defence.
- **Time to heal:**
  - **Colluders a minority:** healing is immediate, because the team loses from the first quarter.
  - **Colluders a majority:** it isn't complete within the year. At 8 of 15, the team's profit falls from **$2,536** in
    the first quarter to **$1,197** in the last, but **21 %** of the pool is still overpaid.
- **What honest participants pay:**
  - honest fixers lose **$80–190** a year to mistaken challenges and forfeited stakes, under 0.2 % of the pool;
  - challengers net **$230–1,800** a year while there are overclaims to catch.

### 5.6 The open number: how often judges see through inflated merit

Every result in 5.4 and 5.5 is conditional on one assumption: the share of faked importance the judges see through.
- **At 80 %:** the defences above hold. A 20 % fee or its capped version protects to **86 %** (5.4), and a refundable
  stake under the 3× rule makes overclaiming lose (5.5).
- **At 50 %:** every defence together still leaves **22–33 %** of a pool overpaid, even with no colluding judges
  (`reports/cyclepool-v1.md`).

No measured value exists yet. The planned measurement, a paid run of seven model families on 50 labelled fix pairs from
public data, is estimated at **about $89** (`reports/judges-v1.md`; a plan, not a result). It is held until the design is
frozen (proof-of-fix#160).

## 6. Experiments with real systems

### 6.1 End to end on a private devnet

A private Ethereum devnet on AWS, a private repository on Forgejo (`pof-sandbox`), six role seats on the owner's PC and
one validator seat on AWS, started on demand. The seat on AWS calls a real model through Bedrock; the others use a free,
deterministic fake judge that follows the test result. (Proof-of-fix#150.)

- **The first bounty ran the whole loop** (2026-11-04, comment 5789): registered, funded, attempted, sealed, judged,
  merged, settled, and fees withdrawn. Two wrong fixes failed and a correct one passed, each judged in 52–97 seconds. The
  head on-chain moved to the merged commit.
  - The owner's seat's watcher started its node on the draw.
  - The node fetched the commit read-only, ran the tests in its sandbox, and called the model through Bedrock.
  - It reported the provider's token counts on-chain, signed, and relayed the result.
- **A real model judged a correct fix** (comment 5890). The owner's seat was drawn on the 6th try and answered Pass. It
  then signed and relayed the merge.
- **The local copy of the whole setup passed** (2026-11-08, comment 6335): every role withdrew its fees, and the owner's
  slow node sealed in time. No key, credential or token appeared in any command line, process, output or log.

**What these runs don't show:**
- **Judge quality:** a small, correct fix with passing tests is an easy case, and the model was told the test result.
- **That a real model can change an outcome:** the fake judges hold the majority of any draw.
- **Independence, attestation, or anything with real money.**

### 6.2 Determinism of an open model judge

From `reports/determinism-v1.md`: one open-weight model, two engines and 30 judge cases, on the owner's PC.
- **Within one setup:** vLLM's batch-invariant mode gave the same tokens on every call, **600 of 600**, at 2.5 times the
  GPU time. Its default mode is not reproducible token for token.
- **Across setups:** tokens differ and verdicts usually survive, but not always. Up to **5 of 30** verdicts differed. A
  re-run proves something only on the same engine, build, weights, quantization, flags and GPU type.
- **Answer shopping has less room than the simulation assumed.** A shopper with 5 calls gains **+3.5 points** on
  borderline fixes and **+10.7** on bad ones, against the simulation's 3-in-10 assumption of +53 points.
- **A new lever:** the check ID. Choosing among 5 IDs gains **+11.7 points** on bad fixes, so the ID must come from data
  the validator can't choose.

### 6.3 Verifiable model calls (zkTLS)

From `reports/zktls-spike-v1.md`: **13 real model calls** to three families on Bedrock were proven with TLSNotary. Each
proof took 2 to 22 seconds, is about 6 KB, and verifies offline. It isn't ready:
- **no independent notary signs proofs today;**
- **requests are capped at 4 KB** in the default mode, and a judge's prompt with a diff won't fit;
- **the software is alpha.**

Level C stays off.

## Notes for section 7 (trust points), from these results
- **The judges' detection rate of inflated merit** (5.6) belongs in the list as the first open problem: the token and
  pool results depend on it.
- **A colluding majority of judges** is healed only partly within a year, even with challenges (5.5).
- **The capped fee depends on a price feed** (5.4). The cap bounds the damage a manipulated price can do.
- **Item 6, "honest validators net about −$1.43 a month early on",** should be restated as churn (5.3): stayers +$1.20,
  leavers −$2.62, and no token slice.
