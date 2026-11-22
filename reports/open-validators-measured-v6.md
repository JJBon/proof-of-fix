# Open validators with measured judges, v6: a validator's capacity against spam, and validators choosing repositories (proof-of-fix#253, #252; 2026-11-17)

**Status: exploratory.** This report continues [`open-validators-measured-v5.md`](open-validators-measured-v5.md). It uses seeds 1–40, the seeds every earlier round used, so nothing here is confirmatory. Every ± is two standard errors of the mean over the seeds. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json` (#160).

**Commands:**
- `python3 -m pof.sim.openval.capacity --seeds 40 --jobs 15 --out DIR` runs simulation A (about 27 minutes on 15 cores); `--render DIR` prints its appendix;
- `python3 -m pof.sim.openval.choice --seeds 40 --jobs 15 --out DIR` runs simulation B (about 16 minutes); `--render DIR` prints its appendix;
- `python3 -m pof.sim.openval.capacity --only lane,rate --seeds 40 --jobs 15 --out DIR` runs the post hoc newcomer lane (last section); `--render DIR` prints its tables too.

**What was fixed when:** sections A.1 and B.1 were committed before any 40-seed run (`99e9e60`, `62d596f`). A 2-seed smoke run then showed a confound in B's twin, and two additions were committed before the 40-seed runs (`ca04116`, marked in B.1). Rows or readings added after the 40-seed results were seen are marked **post hoc**. The last section, the newcomer lane, is post hoc as a whole: proposed after A.2's results, its rules fixed before its own runs.

## In brief
**Simulation A: a validator's capacity (#253).**
- **A capacity bounds what spam costs each validator. It does not keep honest fixes moving once spam exceeds the network's capacity.** At 7 validators, a capacity of N an hour holds a validator to about 24 × N checks a day (5 an hour: 118 checks, **$2.36–14.18 a day** at $0.02–0.12 a check), against 239 checks ($4.78–28.66 a day) with no capacity under 10 junk fixes an hour. Without spam a validator runs 4 checks a day ($0.08–0.50).
- **Below the spam's demand, someone waits; the queue's order decides who:**
  - **in arrival order (FIFO), every honest fix waits behind the junk.** At 5 an hour and 10 junk fixes an hour, 100 % of honest fixes wait more than 24 hours and 90 % are withdrawn after 14 days (both seats). The backlog never clears (11,000 junk fixes queued after 13 weeks);
  - **reputation first serves established solvers at once** (median wait 0.6 hours, about 0 % over 24 hours), **and starves newcomers:** 85–87 % of their fixes are withdrawn, and a newcomer can never earn the reputation that would move it up. That is 8.7 ± 0.9 % (Opus 5.5) and 11.1 ± 0.9 % (GPT-6.1) of all honest fixes withdrawn, so the rule fixed in advance **does not hold**.
- **Against 1 junk fix an hour,** any capacity of 3 or more holds in both orders (no honest fix waits); a capacity of 1 fails in arrival order (98 % wait over 24 hours).
- **The recommended default, by the rule fixed in advance,** is the smallest capacity that holds at 7 validators against both spam rates: **10 an hour, with reputation first** (Opus 5.5: 0.2 ± 0.2 % over 24 hours; GPT-6.1: 0.6 ± 0.3 %; none withdrawn). **But at 7 validators 10 an hour is the high spam's own demand** (70 checks an hour over 7 validators), **so it caps nothing:** spend is $4.72–28.32 a day, as with no capacity. Newcomers still wait over 24 hours (6 ± 3 % and 9 ± 4 % of their fixes). No capacity that binds keeps honest time to heal acceptable under the high rate.
- **With 15 validators,** 5 an hour with reputation first holds for Opus 5.5 (2.8 ± 0.4 % over 24 hours, none withdrawn) and narrowly fails for GPT-6.1 (4.6 ± 0.6 %); newcomers wait over 24 hours (72–76 %), none withdrawn. **With 4 validators nothing holds, not even the base without spam:** k is 3, and 3.7 % of honest fixes carry bounties above k = 3's $250 limit and are never judged (a limit that predates this report). Measured against that base (post hoc), 4 validators behave like 7.
- **A repository's cap helps only against spam on one repository.** At 7 validators and 5 an hour, a cap of 7 checks an hour per repository confines 10 junk fixes an hour to their repository: with reputation first only 0.4–0.6 % of honest fixes are withdrawn (the target repository's newcomers), and **a validator's spend falls from $14.18 to $3.27 a day**. Spam spread over all ten repositories gets exactly the result of no repository cap.
- **The judges' fee ends free spam on a real-money chain:** 10 junk fixes an hour cost the spammer **$1,205 a day** at $5.03 each, and the fee pays the validators $0.71–1.62 a check, above any model's cost. It doesn't shorten the queue: the waits are the same as on the testnet.
- **A spammer with $5,000 of reputation** is served first, but D29's cap holds its open claims to $5,050, about 30 junk fixes at a time: no honest fix waits, and validators spend $2.56–4.12 a day.
- **Checks lost to spam:** 82–86 % of all checks at 1 junk fix an hour, 92–99.7 % at 10.
- **Post hoc, a newcomer lane** (a share of each validator's capacity reserved for fixes without reputation, first come first served; last section): **no share passes.** Junk from free identities fills the lane, so at 10 junk fixes an hour every lane at 7 validators withdraws more honest fixes than no lane (15–19 % against 8.7–11.1 %), all of them newcomers'. A per-identity rate does nothing against free identities. **When identities cost something, D29's cap already lets newcomers through** (a pool of 10 identities: every cell holds from a lane of 25 %). At the testnet's launch, with one repository, a repository cap of 7 is a network-wide cap and fails even at 1 junk fix an hour.

**Simulation B: validators choosing repositories (#252).** Opus 5.5 seated alone, 28 honest validators, the target repository allowed by h of them.
- **A broken TEE type concentrated by allow lists on a small repository gains,** against its twin, **+$3,732 ± 186 a year (3 attackers) and +$3,950 ± 194 (10) with one honest validator on the target, +$1,163 ± 147 and +$2,762 ± 150 with three** (fixes the tests fail), passing 54–57 bad fixes a year where its accomplice alone gets 12. Bad fixes that pass the tests: +$4,126 and +$4,269 with one, +$2,392 and +$3,498 with three.
  - **The per-TEE-type cap is what stops it from 5 honest validators on:** with h + a ≥ 8 the panel is 5 or 7, and one TEE type may hold only 2 or 3 seats. With fewer honest validators the caps step k down to 3, where (with three TEE types) one type may hold all the seats.
  - **Spread over repositories, it gains nothing** on fixes the tests fail (−$93 to −$548 against its twin at every h and minimum).
- **The minimum that keeps the broken TEE at or below its twin is 5 eligible validators, counting at most 2 of one TEE type** (M = 5): on fixes the tests fail it holds at every h tried; on fixes that pass the tests it removes the broken TEE's own part at every h (see the next point for the rest). M = 3 is not enough with three honest validators (+$1,163 and +$2,762). **It works by listing nothing on the target until about 5 honest validators across the three TEE types allow it:** in this world the h = 1 and h = 3 targets get no bounties at all at M = 5, so the 87–88 % of their good fixes healed at M = 0 become none. M = 7 unlists h = 5 as well.
- **On fixes that pass the tests, the twin test fails wherever the target is listed, and not because of the TEE:** the accomplice alone gains +$1,064 to +$1,525 (with 3 attackers' validators honest), as report v5's solver of bad fixes does without D29. The broken TEE's own part is +$950 to +$2,835 at h ≤ 3 and only +$8 to +$17 from h = 5 (an artifact: a faked vote never suffers an honest outage's $5 slash).
- **Under D29's cap with D30's fee** (16 rows added after the smoke run, M = 0), the broken TEE holds from h = 5 for both kinds of bad fix (+$17 ± 71 to +$48 ± 72, and −$830 to −$845), and still gains with h = 1 (+$1,162 to +$1,441) and mostly with h = 3 (+$532 to +$1,015; −$128 ± 78 with 3 attackers on fixes the tests fail). So M = 5 with D29 and D30 should hold in every cell; that combination was not run.
- **The stake cap (0.1 × the stake outside the largest TEE type) changes nothing:** with h = 1 the cap is $125 and most bounties are below it (+$3,422 ± 165).
- **Silence never pays and is never stopped by a minimum.** Silent validators lose $58–978 a year against their twins, but cut the target's good fixes healed from 87–91 % to **3–6 % (h = 1), 77–82 % (h = 3) and 82–86 % (h = 5)**; only with 10 honest validators is there no harm. **No minimum helps,** because the silent validators count toward it (they rotate over TEE types): a minimum high enough to unlist the target unlists it after the attackers are suspended, while their honest twins keep it listed. Silence holds only at h = 10.
- **Silence exposes a protocol gap:** a counted panel whose sample runs out of replacements never completes, and the protocol has no rule to release it. 3–28 % of the target's fixes end the year stuck that way (0–0.8 % in the twin's world): neither paid nor refunded.

## A.1 Simulation A (#253): the rules, fixed before the runs

**The owner's ask:** a validator takes at most N checks an hour, so it can't be spammed. On a testnet a submission costs only free test ETH, while every check costs its validator real model money.

**The rules simulated** (each a switch of `Params`, off by default, read only by `capacity.CapNet`):

| Switch | Rule | Values run |
|---|---|---|
| `MAX_CHECKS_PER_HOUR` (D31) | A counted draw skips a validator that has taken this many checks in the trailing hour, as it skips a non-responder, with no slash. **k is set from every eligible validator, as without the rule, and is never lowered for capacity:** with too few free validators the submission waits and is drawn again at the next hour; nothing fails. Audits, challenge and appeal panels count toward a validator's hour but are never refused for capacity, so spam can't suppress them (a validator may exceed N by those) | none, 1, 3, 5, 10 |
| `REPO_CHECKS_PER_HOUR` (D31) | A repository's counted checks drawn in the trailing hour | off, 7, 21 |
| `QUEUE_ORDER` (D32) | Waiting submissions are drawn in arrival order (`fifo`), or those whose identity held standing reputation when submitted first (`reputation`: D29's reputation, bounties paid and never reversed, above 0), arrival order within each class. A repository at its cap is skipped; when the best waiting submission can't be drawn for capacity, nothing behind it is drawn that hour | reputation, FIFO |

**Why k is never lowered:** if capacity lowered k, spam would turn every honest fix's panel of 7 into a panel of 1 or 3, which is a security loss, not a delay.

**The world (assumed or chosen):**
- Report v5's base network (`nodeposit.world`): one family registered and seated (Opus 5.5 or GPT-6.1), 3 active honest solvers searching passes, the world's contenders disputing, bad fixes the tests fail, no solver's deposit;
- **4, 7 or 15 validators in all**, every one bonded $1,250, no newcomers during the run (the devnet found that a k = 1 hold needs 4–7);
- **10 repositories**; the world's 30 honest fixes a week spread evenly over them;
- **50 honest solvers: 40 established (reputation $5,000, report v5's sold reputation) and 10 newcomers with none** (assumed);
- D29's cap (base $50, ×1, a reversal takes 2 × its bounty off), as report v5 recommends; **no judges' fee (a testnet)** except in the fee rows;
- **13 weeks** (a quarter): long enough for any backlog to show its growth; honest solvers withdraw a fix that has waited 14 days (`World.withdraw_after_days`, as before).

**The spammer:** junk fixes at S an hour (0; low: 1 an hour; high: 10 an hour), each from a fresh identity, so each claims at most $50 under D29, to a random one of the week's listed issues it may claim. It never withdraws. **Junk is rejected by every judge (assumed):** it buys checks, not payouts; report v5's free identities already cover bad fixes meant to pass. It pays nothing real on a testnet (its attempt fee and check charges are test ETH). In the fee rows it pays `JUDGE_FEE` ($5.03, report v5's measured panel cost) per fix, as on a real-money chain, and so does every honest fix. One more spammer, all its junk from **one identity holding $5,000 of reputation** (so under the reputation order it is served first, and only D29's cap bounds it).

**The rows:**
- **grid:** Opus 5.5 and GPT-6.1 × 4, 7, 15 validators × capacity none, 1, 3, 5, 10 × spam none, low, high × order reputation and FIFO (one order without spam), spam on one repository, no repository cap: 150 rows;
- **repo:** 7 validators at 5 an hour; repository cap 7 and 21, spam low and high, both orders, spam on one repository or spread over all ten; and spread spam with no repository cap: 40 rows;
- **fee:** 4, 7 and 15 validators at 5 an hour, reputation order, spam none, low, high, everyone paying the judges' fee; and the reputable spammer at 7 validators (low and high, no fee): 22 rows.

**Measured, per honest fix arriving from week 1 to 14 days before the end:** the wait from submission to the panel's draw (a fix never drawn counts its wait until it was withdrawn or the run ended, a lower bound), its median and 90th percentile; the shares waiting more than 24 hours and more than 7 days; the share withdrawn; time to heal (submission to payment) of good fixes paid, median and 90th percentile, and the share of good fixes healed; the newcomers' fixes (no reputation when submitted) apart. Per validator: checks a day (every check: counted, audit, challenge), its model spend a day at $0.02 and $0.12 a check (`validator-kit/COSTS.md`), the most checks it ran in one hour. The share of all checks spent on junk. The queue: its largest size, whether it was empty at some hour of the last week ("clears"). In the fee rows: the fee income per check, and the spammer's cost a day.

**The criterion, fixed now:** a capacity **holds** against a spam rate when **honest fixes waiting more than 24 hours are at most 5 %** (mean + 2 SE ≤ 5 %) **and none is withdrawn** (mean + 2 SE ≤ 1 %). It is judged for all honest fixes, and for the newcomers' apart. **The recommended default** is the smallest capacity that holds at 7 validators against both spam rates, under the order that holds; if none holds, the report says so. Spend a day is reported beside it, not judged.

## A.2 Simulation A: results

**Seven validators** (the middle of the devnet's 4–7), each honest fix's wait for a panel and what a validator spends. "Established" fixes are those of the 40 honest solvers holding reputation; "newcomers" are the 10 without (their fixes are in the second class under reputation first; the column is empty in arrival order, where nobody is told apart). A fix never drawn counts its wait until it was withdrawn (14 days), so waits are lower bounds. Spend is checks a day × $0.02 (the cheapest model call in `validator-kit/COSTS.md`) and × $0.12 (the dearest).

| Seat | Capacity /h | Spam /h | Order | Honest > 24 h (%) | Withdrawn (%) | Established > 24 h (%) | Newcomers > 24 h / withdrawn (%) | Wait, median (h) | Checks / validator / day | Spend $ / validator / day | Holds: all / newcomers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | none | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| Opus 5.5 | none | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| Opus 5.5 | none | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| Opus 5.5 | none | 10 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 239 | 4.78–28.66 | yes / yes |
| Opus 5.5 | none | 10 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 239 | 4.78–28.66 | yes / – |
| Opus 5.5 | 1 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| Opus 5.5 | 1 | 1 | reputation | 4.5 ± 0.5 | 0.2 ± 0.1 | 0.0 ± 0.0 | 96 ± 3 / 3 ± 2 | 0.6 ± 0.0 | 24 | 0.47–2.83 | yes / **no** |
| Opus 5.5 | 1 | 1 | fifo | 97.8 ± 1.4 | 1.2 ± 0.9 | 97.8 ± 1.4 | – | 163.3 ± 11.8 | 24 | 0.47–2.83 | **no** / – |
| Opus 5.5 | 1 | 10 | reputation | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.0 ± 0.0 | 100 ± 0 / 100 ± 0 | 0.7 ± 0.0 | 24 | 0.47–2.84 | **no** / **no** |
| Opus 5.5 | 1 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 24 | 0.47–2.84 | **no** / – |
| Opus 5.5 | 3 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| Opus 5.5 | 3 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| Opus 5.5 | 3 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| Opus 5.5 | 3 | 10 | reputation | 14.7 ± 1.1 | 14.7 ± 1.1 | 0.0 ± 0.0 | 100 ± 0 / 100 ± 0 | 0.6 ± 0.0 | 71 | 1.42–8.51 | **no** / **no** |
| Opus 5.5 | 3 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 71 | 1.42–8.51 | **no** / – |
| Opus 5.5 | 5 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| Opus 5.5 | 5 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| Opus 5.5 | 5 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| Opus 5.5 | 5 | 10 | reputation | 10.2 ± 0.9 | 8.7 ± 0.9 | 0.0 ± 0.0 | 100 ± 0 / 85 ± 3 | 0.6 ± 0.0 | 118 | 2.36–14.18 | **no** / **no** |
| Opus 5.5 | 5 | 10 | fifo | 100.0 ± 0.0 | 90.1 ± 0.6 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 118 | 2.36–14.19 | **no** / – |
| Opus 5.5 | 10 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| Opus 5.5 | 10 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| Opus 5.5 | 10 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| Opus 5.5 | 10 | 10 | reputation | 0.2 ± 0.2 | 0.0 ± 0.0 | 0.0 ± 0.0 | 6 ± 3 / 0 ± 0 | 0.5 ± 0.0 | 236 | 4.72–28.32 | yes / **no** |
| Opus 5.5 | 10 | 10 | fifo | 18.4 ± 7.2 | 0.0 ± 0.0 | 18.4 ± 7.2 | – | 14.9 ± 2.5 | 236 | 4.72–28.32 | **no** / – |
| GPT-6.1 | none | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| GPT-6.1 | none | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| GPT-6.1 | none | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| GPT-6.1 | none | 10 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 239 | 4.78–28.66 | yes / yes |
| GPT-6.1 | none | 10 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 239 | 4.78–28.66 | yes / – |
| GPT-6.1 | 1 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| GPT-6.1 | 1 | 1 | reputation | 6.7 ± 0.6 | 0.5 ± 0.3 | 0.0 ± 0.0 | 96 ± 3 / 6 ± 3 | 0.6 ± 0.0 | 24 | 0.47–2.83 | **no** / **no** |
| GPT-6.1 | 1 | 1 | fifo | 97.8 ± 1.4 | 1.2 ± 0.9 | 97.8 ± 1.4 | – | 163.3 ± 11.8 | 24 | 0.47–2.83 | **no** / – |
| GPT-6.1 | 1 | 10 | reputation | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.0 ± 0.0 | 100 ± 0 / 100 ± 0 | 0.7 ± 0.0 | 24 | 0.47–2.84 | **no** / **no** |
| GPT-6.1 | 1 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 24 | 0.47–2.84 | **no** / – |
| GPT-6.1 | 3 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| GPT-6.1 | 3 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| GPT-6.1 | 3 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| GPT-6.1 | 3 | 10 | reputation | 16.4 ± 0.9 | 16.4 ± 0.9 | 0.0 ± 0.0 | 100 ± 0 / 100 ± 0 | 0.6 ± 0.0 | 71 | 1.42–8.51 | **no** / **no** |
| GPT-6.1 | 3 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 71 | 1.42–8.51 | **no** / – |
| GPT-6.1 | 5 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| GPT-6.1 | 5 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| GPT-6.1 | 5 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| GPT-6.1 | 5 | 10 | reputation | 12.7 ± 0.9 | 11.1 ± 0.9 | 0.0 ± 0.0 | 100 ± 0 / 87 ± 2 | 0.6 ± 0.0 | 118 | 2.36–14.19 | **no** / **no** |
| GPT-6.1 | 5 | 10 | fifo | 100.0 ± 0.0 | 90.1 ± 0.6 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 118 | 2.36–14.19 | **no** / – |
| GPT-6.1 | 10 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 4 | 0.08–0.50 | yes / – |
| GPT-6.1 | 10 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / yes |
| GPT-6.1 | 10 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 28 | 0.55–3.31 | yes / – |
| GPT-6.1 | 10 | 10 | reputation | 0.6 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9 ± 4 / 0 ± 0 | 0.5 ± 0.0 | 236 | 4.72–28.32 | yes / **no** |
| GPT-6.1 | 10 | 10 | fifo | 18.4 ± 7.2 | 0.0 ± 0.0 | 18.4 ± 7.2 | – | 14.9 ± 2.5 | 236 | 4.72–28.32 | **no** / – |

**What the table shows:**
- **Without spam every capacity serves every honest fix at once** (median wait 0, 9 hours to heal at k = 7), at 4 checks a validator a day.
- **The capacity sets a validator's spend, nothing else:** about 24 × N checks a day under spam (1 an hour: 24; 3: 71; 5: 118; 10: 236), whatever the order. Audits and challenges may add a little (the most a validator ran in one hour was up to N + 2; appendix).
- **When the network's capacity (validators × N) is below the spam's demand** (about 7 checks a junk fix), the backlog grows for the whole run: with 10 junk fixes an hour and N ≤ 5 the queue never empties in any seed. Then:
  - in arrival order, **every honest fix waits behind every earlier junk fix** and is withdrawn after 14 days;
  - with reputation first, **the established solvers' fixes are drawn within the hour** (their wait over 24 hours is 0 % in every row), **and the newcomers' never are**: 85–100 % of their fixes are withdrawn, and with none paid a newcomer never gains the reputation to move up.
- **Against 1 junk fix an hour** (7 checks an hour, about what 7 validators at 1 an hour can do), a capacity of 1 is at the edge: in arrival order 98 % of honest fixes wait over 24 hours and the median wait is 163 hours; with reputation first the established are served and 96 % of newcomers' fixes wait over 24 hours. From 3 an hour nothing waits.
- **Opus 5.5 or GPT-6.1 seated** changes the waits by at most a few points (GPT-6.1's honest fixes pass less often, so fewer of its solvers hold reputation).

**Four and fifteen validators** (appendix tables "4 validators" and "15 validators"):
- **15 validators** double the network's capacity: at 5 an hour against 10 junk fixes an hour, reputation first holds for Opus 5.5 (2.8 ± 0.4 % over 24 hours, none withdrawn; newcomers 72 ± 7 % over 24 hours, none withdrawn) and narrowly fails for GPT-6.1 (4.6 ± 0.6 %). In arrival order 90.5 % wait over 24 hours (median 70 hours) but none is withdrawn: the queue holds about 1,400 junk fixes, about three days of work, all quarter. At 10 an hour everything holds.
- **4 validators:** k is 3, whose bounty limit at level A is $250, so the 3.7 ± 0.3 % of honest fixes above it are never judged and are withdrawn **in every row, spam or not, capacity or not**. The criterion fixed in advance (none withdrawn) therefore fails everywhere at 4 validators. **Post hoc, against that base:** the rows at 4 validators differ from the base exactly as those at 7 do (capacity 5, 10 junk fixes an hour, reputation first: 12.7 % over 24 hours and 10.6 % withdrawn, of which 3.7 points are the base's; arrival order: 100 % and 84.9 %).

**A repository's cap** (7 validators, 5 an hour; appendix table `repo`):

| Spam | Repository cap /h | Order | Honest > 24 h (%) | Withdrawn (%) | Newcomers withdrawn (%) | Checks / validator / day | Spend $ / day |
|---|---|---|---|---|---|---|---|
| 10 /h on one repository | none (grid) | reputation | 10.2 ± 0.9 / 12.7 ± 0.9 | 8.7 ± 0.9 / 11.1 ± 0.9 | 85 / 87 | 118 | 2.36–14.18 |
| 10 /h on one repository | 7 | reputation | 0.4 ± 0.1 / 0.6 ± 0.1 | 0.4 ± 0.1 / 0.6 ± 0.1 | 9 / 9 | 27 | 0.54–3.27 |
| 10 /h on one repository | 7 | FIFO | 10.2 ± 0.6 | 10.2 ± 0.6 | – | 27 | 0.54–3.27 |
| 10 /h on one repository | 21 | reputation | 0.4 ± 0.1 / 0.6 ± 0.1 | 0.4 ± 0.1 / 0.6 ± 0.1 | 9 / 9 | 74 | 1.48–8.91 |
| 10 /h spread over 10 | 7 or 21 or none | reputation | 10.2 ± 0.9 / 12.7 ± 0.9 | 8.7–8.8 ± 0.9 / 11.1 ± 0.9 | 85 / 87 | 118 | 2.36–14.18 |
| 10 /h spread over 10 | 7 or 21 or none | FIFO | 100 | 90.1 ± 0.6 | – | 118 | 2.36–14.18 |
| 1 /h on one repository | 7 | FIFO | 5.8 ± 1.0 | 0 | – | 27 | 0.54–3.23 |

(Two values: Opus 5.5 / GPT-6.1; one value: the same for both.) **A repository's cap confines spam aimed at one repository to it:** the other nine repositories' fixes never wait, the target repository's fixes wait in its own queue (10.2 % of all honest fixes, the target's share, in arrival order), and a validator's spend falls by three quarters. **Spam spread over every repository is untouched by it:** each repository's share of the spam fits under its cap.

**The judges' fee and the reputable spammer** (appendix table `fee`):
- **With the fee** (every fix pays $5.03, as on a real-money chain) the waits are those of the testnet rows above, because the queue doesn't look at money. What changes: **the spammer pays $120 a day at 1 junk fix an hour and $1,205 a day at 10**, and the validators are paid $0.73 a check at 7 validators ($0.71 at 15, $1.62 at 4), above any model's cost per check.
- **The reputable spammer** (one identity of $5,000, served first) is held by D29's cap to $5,050 of open claims, about 28 junk fixes at once: no honest fix waits, and a validator runs 21–34 checks a day ($2.56–4.12). A rejection costs no reputation under D29, so the identity keeps its place; only the cap on open claims bounds it.

## A.3 What simulation A recommends
- **The rule fixed in advance names 10 an hour, with reputation first.** It is the only capacity that holds at 7 validators against both spam rates. At 7 validators it binds nothing against 10 junk fixes an hour, so it doesn't limit spend there; it is a ceiling for a larger spam or a smaller network.
- **What a capacity is for, on this evidence: a spend limit, set from what a validator will pay a day.** At 5 an hour: at most about $14 a day at $0.12 a check (a quarter of that at $0.03). Report it to validators as that, not as a spam defence.
- **What keeps honest fixes moving under spam is the queue's order, and only for those with reputation.** Reputation first is better than arrival order in every spam row; it costs the newcomers, who are exactly whom a testnet is for.
- **Before adopting a capacity below the spam a testnet may see, something must let a newcomer's first fix through.** Not simulated here: a separate share of each hour for fixes without reputation, a per-identity rate (fresh identities are free, so it needs the faucet's rate limit behind it), or a small charge in test ETH. On a real-money chain the judges' fee (D30) already prices spam out.
- **A repository's cap of about one panel an hour (7 counted checks) is worth adding**: it stops spam aimed at one repository from spreading and cuts spend by three quarters there. It does nothing against spread spam.

## B.1 Simulation B (#252): the rules, fixed before the runs

**The owner's decisions (#252):** enclaves only (levels A and B, no level C: no answer shopping and no fabricated receipt unless a TEE type is broken); allow lists and deny lists, both respected everywhere (first-round panels, audits, challenges, appeals): a validator is never drawn for a repository it denied or did not allow. A repository with too few eligible validators across TEE types and families gets no bounties.

**The rules simulated** (switches of `Params`, off by default, read only by `choice.ChoiceNet`):

| Switch | Rule | Values run |
|---|---|---|
| `REPO_LISTS` (D33) | Every draw's pool keeps only the validators that allow the submission's repository (no allow list: all) and don't deny it: counted panels, shadows, audits, challenge and appeal panels, the k = 1 hold's count | on (and off, for reference) |
| `REPO_MIN_ELIGIBLE` (D34) | A repository's fix is listed (judged, its bounty offered) only while at least M validators are eligible for it, **counted with at most (M − 1) / 2 of any one TEE type** (so M = 3, 5 and 7 each need three TEE types). Otherwise it is not listed and costs nobody anything. The family part can't be tested here: one family is seated | M = 0 (none), 3, 5, 7 |
| `REPO_STAKE_X` (D34's option) | A listed bounty is capped at X × the bonded stake of the repository's eligible validators **outside the TEE type that holds the most of it** | 0; 0.1 |

**The world (assumed or chosen):** report v5's base network with **Opus 5.5 seated alone**; **28 honest validators**, every one bonded $1,250, no newcomers; 10 repositories, 30 honest fixes a week spread evenly (the target gets about 3 a week); the target is allowed by **h = 1, 3, 5 or 10 honest validators** (the genesis first, then in registry order, so their TEE types rotate over Nitro, TDX and SEV-SNP) and denied by the rest; **D30's judges' fee ($5.03), no reputation cap** (the worst case for this simulation: with D29 a fresh identity could claim at most $50); a year.

**The attackers, each against its twin on the same seeds** (the twin: the same validators, honest, and no bad fixes):
1. **Silence:** 3 or 10 validators (TEE types and hosts rotating) allow-list only the target and never answer there (counted draws, audits, challenge panels). They shadow-judge honestly, so a suspended one qualifies again. The protocol replaces each silent judge from the same sample, slashes it $5, and the reveal-rate floor suspends it. Measured: the target's good fixes healed, time to heal, fixes expired (withdrawn after waiting 14 days), fixes stuck in a panel that never completes, the attacker's money; and the target in a world where the attackers never registered ("absent").
2. **A broken TEE type:** 3 or 10 validators on TDX, whose attestation is broken (secret all year, assumed), pass their accomplice's bad fixes (5 a week, random listed bounties). **They fake the model's answer only, so a re-run proves nothing and they are never slashed for a false verdict** (faking a test result would be caught by a re-run, a dominated strategy). As auditors and challenge judges of those fixes they defend them; elsewhere they judge honestly. **Concentrated:** all allow-list the target, where the accomplice submits. **Spread:** each allow-lists one repository in turn, and the accomplice submits to those at random. **Open (reference):** no lists for anyone. Both kinds of bad fix (the tests fail them; they pass the tests and are wrong).

**The rows:** broken TEE: both kinds of bad fix × concentrated and spread × h = 1, 3, 5, 10 × 3 and 10 attackers × M = 0, 3, 5, 7 (128 rows), the open reference (4) and the stake cap at X = 0.1 with M = 0, concentrated (16); silence: h = 1, 3, 5, 10 × 3 and 10 attackers × M = 0, 3, 5, 7 (32 rows).

**Added after a 2-seed smoke run, before the 40-seed runs** (committed separately, and marked in the results): the smoke showed that on fixes that pass the tests the accomplice gains even where no list helps it (the "open" reference: +$1,864 on 2 seeds), because without D29 report v5's plain solver of bad fixes gains on such fixes. So each broken-TEE row also runs **the accomplice alone** (the same bad fixes, its validators judging honestly), and reports **the broken TEE's part: the attacker's return minus the accomplice alone's**, judged by the same test. And 16 rows run the concentrated broken TEE under **D29's cap with D30's fee** (report v5's recommended rule; the accomplice on a fresh identity each fix, the largest listed issue it may claim), M = 0. The primary twin, and every criterion below, are unchanged.

**The criteria, fixed now:**
- **an attacker is at or below its twin** when its return minus its twin's has mean − 2 SE ≤ 0 (report v5's test);
- **for silence**, which earns no money, also **the harm**: the target's share of good fixes healed with the attacker, minus its twin's, must have mean + 2 SE ≥ 0 (not shown to harm). Silence holds only if both hold. The listed share is reported beside it: a minimum that lists nothing on the target harms nobody and heals nothing;
- **the minimum that keeps each attacker at or below its twin** is the smallest M of 0, 3, 5, 7 at which it holds, per form, h, attacker count and kind of bad fix; with what it costs: the share of the target's fixes not listed in the twin's world.

## B.2 Simulation B: results

### The broken TEE type, concentrated on the target by allow lists (fixes the tests fail)
Attacker − twin, $ a year (bold: above its twin), and the accomplice's bad fixes paid on the target (its accomplice alone, validators honest: 12–13 a year in every cell):

| Target's honest validators | Attackers | M = 0 (no minimum) | M = 3 | M = 5 | M = 7 | Bad fixes paid at M = 0 |
|---|---|---|---|---|---|---|
| 1 | 3 | **+3,732 ± 186** | 0 (not listed) | 0 (not listed) | 0 (not listed) | 54.3 ± 1.8 |
| 1 | 10 | **+3,950 ± 194** | 0 (not listed) | 0 (not listed) | 0 (not listed) | 56.5 ± 1.8 |
| 3 | 3 | **+1,163 ± 147** | **+1,164 ± 147** | 0 (not listed) | 0 (not listed) | 27.6 ± 1.3 |
| 3 | 10 | **+2,762 ± 150** | **+2,763 ± 150** | 0 (not listed) | 0 (not listed) | 44.2 ± 1.5 |
| 5 | 3 | −129 ± 138 | −129 ± 138 | −129 ± 138 | 0 (not listed) | 12.8 ± 1.3 |
| 5 | 10 | −134 ± 137 | −134 ± 137 | −133 ± 137 | 0 (not listed) | 12.9 ± 1.3 |
| 10 | 3 | −93 ± 147 | −93 ± 147 | −93 ± 147 | −93 ± 147 | 13.1 ± 1.3 |
| 10 | 10 | −93 ± 146 | −93 ± 146 | −93 ± 146 | −93 ± 146 | 13.1 ± 1.3 |
| no lists (28 + attackers) | 3 / 10 | −89 ± 147 / −84 ± 147 | | | | 13.1 ± 1.3 |

- **The per-TEE-type cap (D6) decides it.** With 5 or more honest validators the target's pool is 8 or more, and the panel is 5 or 7, where one TEE type holds at most 2 or 3 seats: the broken type can't pass a fix alone, and its accomplice gets what it would get anyway. With 1 or 3, the caps can't fill a panel of 5 or 7 from so few other types, k steps down to 3, and with three TEE types accepted k = 3 has no TEE cap (D6's named trust point): the broken type takes 2 or 3 of the seats.
- **More attackers is worse with 3 honest validators** (+$2,762 against +$1,163): 10 of one type make a k = 3 panel all theirs more often.
- **The minimum, counted with at most 2 of one TEE type (M = 5), lists nothing on a target with 1 or 3 honest validators** (they span at most 4 counted: Nitro 1, TDX 2, SEV-SNP 1), and lists the target with 5. **M = 3 counts one per type, so 3 honest validators on three types pass it, and the attacker still gains.**
- **What the minimum costs:** at M = 5 the h = 1 and h = 3 targets get no bounties at all, in the twin's world too: 87–88 % of their good fixes were healed at M = 0. At M = 7 the h = 5 target is unlisted as well.
- **Spread over the repositories** (one attacker on the target), the broken TEE loses at every h and minimum (−$93 to −$548); it adds 1–4 bad fixes a year on the target and none elsewhere (where 28 honest validators sit).
- **The stake cap** (0.1 × the bonded stake outside the largest TEE type, M = 0) caps the h = 1 target's bounties at $125, under which most bounties already fall: +$3,422 ± 165 and +$3,608 ± 163 (h = 1), +$1,406 ± 157 and +$3,174 ± 185 (h = 3). It changes nothing that matters at 0.1.

### Fixes that pass the tests and are wrong
The accomplice alone, its validators honest, already gains here: **+$1,064 ± 167 to +$1,525 ± 207 a year** with 3 validators, as report v5's solver of bad fixes gains on such fixes without D29. So the twin test fails wherever the target is listed, at every h, in both forms and in the world without lists (+$1,884 ± 206). **The broken TEE's own part** (attacker − the accomplice alone):

| Target's honest validators | 3 attackers | 10 attackers |
|---|---|---|
| 1 | **+2,706 ± 168** | **+2,835 ± 178** |
| 3 | **+950 ± 100** | **+2,063 ± 154** |
| 5 | +9 ± 2 | +15 ± 7 |
| 10 | +8 ± 2 | +17 ± 3 |

From h = 5 the broken TEE adds no bad fix paid (31.6 against 31.6 a year); the +$8–17 is a modelling artifact (a faked vote is always "revealed", so it never pays an honest outage's $5 slash). At M = 5 the h = 1 and h = 3 rows are unlisted, so **M = 5 removes the broken TEE's part in every cell**; what remains is report v5's hole, which D29 addresses.

### Under D29's cap and D30's fee (added after the smoke run; M = 0; the accomplice on a fresh identity each fix)

| Target's honest validators | Tests fail them: 3 / 10 attackers | Pass the tests: 3 / 10 attackers |
|---|---|---|
| 1 | **+1,162 ± 79** / **+1,263 ± 75** | **+1,387 ± 78** / **+1,441 ± 76** |
| 3 | −128 ± 78 / **+639 ± 63** | **+532 ± 80** / **+1,015 ± 68** |
| 5 | −845 ± 61 / −841 ± 61 | +17 ± 71 / +21 ± 72 |
| 10 | −830 ± 64 / −832 ± 64 | +48 ± 72 / +47 ± 72 |

D29 cuts the gain by two thirds or more where the target is small (a fresh identity claims at most $50) but does not close it: with 1 or 3 honest validators the broken TEE still passes 28–62 bad fixes a year. From 5 it holds for both kinds. **Inference, not run:** M = 5 unlists exactly the rows that still gain, so D29 + D30 + M = 5 should hold in every cell here.

### Silence on the target (Opus 5.5, fixes the tests fail)

| Target's honest validators | Attackers | Minimum | Listed: attacker / twin (%) | Good fixes healed: attacker / twin / absent (%) | Harm (points) | Stuck (%) | Attacker − twin ($) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 0 | 100 / 100 | 3 / 87 / 0 | **84.3 ± 1.4** | 24.3 ± 1.3 | −257 ± 17 |
| 1 | 3 | 3 | 5 / 100 | 0 / 87 / 0 | **87.3 ± 1.1** | 4.4 ± 0.4 | −58 ± 5 |
| 1 | 3 | 5, 7 | 0 / 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| 1 | 10 | 0 | 100 / 100 | 6 / 91 / 0 | **84.7 ± 1.7** | 27.7 ± 1.5 | −978 ± 44 |
| 1 | 10 | 3, 5, 7 | 7–9 / 100 | 0 / 91 / 0 | **91.2 ± 0.9** | 6.6–9.0 | −225 to −262 |
| 3 | 3 | 0, 3 | 100 / 100 | 77 / 91 / 87 | **13.7–14.0** | 12.7–12.9 | −321 ± 8 |
| 3 | 3 | 5 | 4 / 100 | 0 / 91 / 0 | **91.2 ± 1.0** | 4.1 ± 0.4 | −81 ± 3 |
| 3 | 3 | 7 | 0 / 0 | 0 / 0 / 0 | 0 | 0 | 0 |
| 3 | 10 | 0, 3 | 100 / 100 | 82 / 91 / 87 | **9.6 ± 0.8** | 7.8 ± 0.5 | −358 ± 13 |
| 3 | 10 | 5, 7 | 5–6 / 100 | 0 / 91 / 0 | **91.2 ± 0.9** | 4.9–6.0 | −275 to −290 |
| 5 | 3 | 0, 3, 5 | 100 / 100 | 82 / 91 / 89 | **9.2 ± 1.0** | 10.6–10.7 | −301 ± 8 |
| 5 | 10 | 0, 3, 5 | 100 / 100 | 86 / 91 / 89 | **5.0–5.1 ± 0.6** | 5.8 ± 0.5 | −335 ± 9 |
| 5 | 3 or 10 | 7 | 3–4 / 100 | 0 / 91 / 0 | **91.2** | 3.1–4.0 | −81 to −288 |
| 10 | 3 or 10 | any | 100 / 100 | 91 / 91 / 91 | 0.0 ± 0.0 | 0 | −279 to −337 |

- **Silence always loses money** ($5 a silence; at M = 0, 50–190 silences and 8–21 suspensions a year) **and always harms a target with 5 or fewer honest validators.** The harm is worse than the attackers never registering ("absent") with 3 or 5 honest validators: 77–86 % healed against 87–89 %.
- **How it harms:** a counted panel of k is drawn; each silent judge is replaced from the same sample; when the sample has no one left the panel waits for a replacement that never comes (D2: k never shrinks), and **nothing in the protocol releases it.** The fix is neither paid nor refunded ("stuck": 3–28 % of the target's fixes at the end of the year). With 1 honest validator, fixes also expire waiting (65–72 % withdrawn).
- **No minimum helps.** The silent validators rotate over TEE types, so they count toward any minimum while active. Once suspended (the reveal-rate floor works: 8–21 suspensions a year), the count falls below M and the target is unlisted, while in the twin's world the same validators answer and keep it listed. Only targets that are unlisted in both worlds show no harm, and they heal nothing.
- **Holds:** only with 10 honest validators, at any minimum.

### The minimum that keeps each attacker at or below its twin

| Attacker | h = 1 | h = 3 | h = 5 | h = 10 | Cost of that minimum |
|---|---|---|---|---|---|
| Broken TEE, concentrated, tests fail them | M = 3 | M = 5 | M = 0 | M = 0 | h = 1 and 3 unlisted at M = 5 |
| Broken TEE, concentrated, pass the tests | none (the accomplice alone gains); its TEE part: M = 3 | none; TEE part: M = 5 | none; TEE part: +$9–15 at any listed M, the artifact (by the strict test, only M = 7, which unlists) | none; TEE part: +$8–17 at every M, the artifact | as above |
| …under D29 + D30, M = 0 only | not at M = 0 | 3 attackers, tests fail: M = 0; otherwise not at M = 0 | M = 0 | M = 0 | – |
| Broken TEE, spread, tests fail them | M = 0 | M = 0 | M = 0 | M = 0 | none |
| Silence (harm) | 3 attackers: M ≥ 5, which lists nothing; 10: none | 3 attackers: M = 7, which lists nothing; 10: none | none | M = 0 | – |
| Silence (money) | M = 0 | M = 0 | M = 0 | M = 0 | none |

("Which lists nothing": it holds only because neither world offers a bounty on the target.)

## B.3 What simulation B recommends
- **Allow and deny lists can be adopted with a minimum of 5 eligible validators per repository, at most 2 of one TEE type counted (D34), and only together with D29 and D30.** On fixes the tests fail, M = 5 alone kept a broken TEE type's validators, concentrated by allow lists, at or below their twins in every cell tried. On fixes that pass the tests it removed the broken TEE's own part, and D29 is what closes the rest (report v5's hole); D29 with M = 5 was not run together, so that it holds in every cell is an inference from the two tables above.
  - **The price:** a repository allowed by fewer than about 5 honest validators across the three TEE types gets no bounties. In a network of 28, that is any repository most validators ignore.
  - **Count per TEE type, not per head.** M = 3 counted one per type still lets the broken type win with 3 honest validators.
  - **Not the stake cap at 0.1:** it binds too rarely to matter.
- **Silence needs its own rule, which this change doesn't have:** a counted panel that can't be completed must end. Options for the owner (none simulated): after the seal and reveal windows with no replacement, redraw the panel from the currently eligible (silent judges excluded) at the same k, or release the fix unjudged with its fee back. And a silent validator should not count toward a repository's minimum after a miss.
- **The family half of the minimum ("across TEE types and families") is untested:** one family is seated here, so the family cap is off (D20). With several families seated it would count at most (M − 1) / 2 of one family the same way.

## What this does not show
- **A newcomer's way through spam.** No rule that reserves capacity for fixes without reputation was simulated; A.3 names three.
- **Spam meant to pass.** Junk is rejected by every judge here (assumed); report v5's free identities cover bad fixes meant to pass, and under D29 a fresh identity claims at most $50.
- **A spammer filing its own issues at tiny bounties** on a testnet, which D29's cap would not bound by value; the spammer here takes listed issues.
- **Capacity on a growing network,** with newcomers joining and qualifying while spam runs (no newcomers here), and the market's fee reacting to the waits (the fee's wait signal counts every wait, so it would rise; on a testnet that is test ETH).
- **Capacity under the measured judges' disputes at scale:** audits and challenge panels are never refused for capacity; at 10 junk fixes an hour they added at most 2 checks to a validator's busiest hour.
- **The family half of the repository minimum:** one family is seated in both simulations.
- **GPT-6.1 in simulation B,** and repositories allowed by validators of only one or two TEE types (the target's honest validators rotate over all three here).
- **A broken TEE found and removed** (D11's 48-hour removal): the flaw stays secret all year, the worst case.
- **A rule releasing a stalled panel,** which silence shows is missing (B.3).
- **Silence at a rate under the reveal-rate floor** (the attackers here are silent on every draw and get suspended); a silent rate just under 10 % would avoid suspension and stall fewer panels.
- **Confirmation:** seeds 1–40 only, as every earlier round; nothing here is confirmatory.

## For the owner
- **#253, a validator's capacity:** adopt it as a **spend limit** (D31), with **reputation first** (D32) and **a repository's cap of about 7 counted checks an hour**. The rule fixed in advance names **10 an hour**; 5 an hour holds a validator to about $14 a day at the dearest model, and with 15 validators it held against 10 junk fixes an hour for Opus 5.5 (narrowly not for GPT-6.1). **Decide how a newcomer's first fix gets through under spam;** without it, reputation first leaves newcomers' fixes withdrawn whenever spam exceeds the network's capacity.
- **#252, repository choice:** allow and deny lists (D33) hold against a broken TEE type only with **a minimum of 5 eligible validators per repository, at most 2 of one TEE type counted** (D34), **and D29 with D30**. Smaller repositories then get no bounties. **Decide what releases a counted panel that can never complete** (task 14.2): silence harms small repositories whatever the minimum.

## What is assumed, measured or chosen

| Input | Value | Status |
|---|---|---|
| A judge's verdict on an honest or bad fix | its family's recorded #160 verdict | **measured** |
| A junk fix's verdict | rejected by every judge | **assumed** (junk buys checks, not payouts) |
| The spam rates | 1 and 10 junk fixes an hour | chosen (about 5 and 55 times the honest rate of 30 a week) |
| The spammer | never withdraws; a fresh identity each junk fix | chosen (the worst case for the queue) |
| A model call's cost to a validator | $0.02–0.12 a check | `validator-kit/COSTS.md` (B2's estimate, not measured on a testnet) |
| The judges' fee | $5.03 a submission | **measured** in report v5's simulator |
| Honest solvers' reputation | 40 of 50 at $5,000, 10 newcomers at 0 | **assumed** |
| Repositories, and the honest fixes' spread | 10, even | chosen |
| Validators | 4, 7, 15 (A); 28 (B), all bonded $1,250, no newcomers | chosen |
| Run length | 13 weeks (A), a year (B) | chosen |
| An honest solver withdraws a fix | after waiting 14 days | as every earlier report (`World.withdraw_after_days`) |
| A broken TEE type | secret all year; its validators fake the model's answer only | **assumed** (the worst case: no removal ADR, no slash) |
| The target's honest validators' TEE types | rotating: Nitro, TDX, SEV-SNP | chosen |
| The accomplice's rate | 5 bad fixes a week | as report v5's solver of bad fixes |
| Active honest solvers searching passes, their find rate | 3, 25 % | **assumed** (report v5's base) |

## Appendix: the full output
Printed by `--render` from the 40-seed results, and (the two tables by validator count) from the same results with the established solvers' share derived per seed.

### Simulation A, by validator count

#### 4 validators

| Seat | Capacity /h | Spam /h | Order | Honest > 24 h (%) | Withdrawn (%) | Established > 24 h (%) | Newcomers > 24 h / withdrawn (%) | Wait, median (h) | Checks / validator / day | Spend $ / validator / day | Holds: all / newcomers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | none | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| Opus 5.5 | none | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 4 ± 2 / 4 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| Opus 5.5 | none | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| Opus 5.5 | none | 10 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 4 ± 2 / 4 ± 2 | 0.0 ± 0.0 | 189 | 3.77–22.64 | **no** / **no** |
| Opus 5.5 | none | 10 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 189 | 3.77–22.64 | **no** / – |
| Opus 5.5 | 1 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| Opus 5.5 | 1 | 1 | reputation | 8.2 ± 0.6 | 3.9 ± 0.4 | 3.7 ± 0.3 | 96 ± 2 / 7 ± 3 | 0.6 ± 0.0 | 19 | 0.37–2.23 | **no** / **no** |
| Opus 5.5 | 1 | 1 | fifo | 97.7 ± 1.4 | 4.9 ± 1.0 | 97.7 ± 1.4 | – | 169.0 ± 12.2 | 19 | 0.37–2.23 | **no** / – |
| Opus 5.5 | 1 | 10 | reputation | 21.5 ± 0.8 | 21.5 ± 0.8 | 3.7 ± 0.4 | 100 ± 0 / 100 ± 0 | 0.7 ± 0.0 | 19 | 0.37–2.23 | **no** / **no** |
| Opus 5.5 | 1 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 19 | 0.37–2.23 | **no** / – |
| Opus 5.5 | 3 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| Opus 5.5 | 3 | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 4 ± 2 / 4 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| Opus 5.5 | 3 | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| Opus 5.5 | 3 | 10 | reputation | 17.3 ± 1.1 | 17.2 ± 1.1 | 3.7 ± 0.3 | 100 ± 0 / 100 ± 0 | 0.6 ± 0.0 | 61 | 1.21–7.28 | **no** / **no** |
| Opus 5.5 | 3 | 10 | fifo | 100.0 ± 0.0 | 99.8 ± 0.1 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 61 | 1.21–7.28 | **no** / – |
| Opus 5.5 | 5 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| Opus 5.5 | 5 | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 4 ± 2 / 4 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| Opus 5.5 | 5 | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| Opus 5.5 | 5 | 10 | reputation | 12.7 ± 1.0 | 10.6 ± 1.0 | 3.7 ± 0.3 | 100 ± 0 / 75 ± 4 | 0.6 ± 0.0 | 105 | 2.11–12.65 | **no** / **no** |
| Opus 5.5 | 5 | 10 | fifo | 100.0 ± 0.0 | 84.9 ± 0.8 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 105 | 2.11–12.64 | **no** / – |
| Opus 5.5 | 10 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| Opus 5.5 | 10 | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 4 ± 2 / 4 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| Opus 5.5 | 10 | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| Opus 5.5 | 10 | 10 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 4 ± 2 / 4 ± 2 | 0.0 ± 0.0 | 189 | 3.77–22.65 | **no** / **no** |
| Opus 5.5 | 10 | 10 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.1 ± 0.0 | 189 | 3.77–22.65 | **no** / – |
| GPT-6.1 | none | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| GPT-6.1 | none | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.8 ± 0.3 | 3 ± 2 / 3 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| GPT-6.1 | none | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| GPT-6.1 | none | 10 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.8 ± 0.3 | 3 ± 2 / 3 ± 2 | 0.0 ± 0.0 | 189 | 3.77–22.64 | **no** / **no** |
| GPT-6.1 | none | 10 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 189 | 3.77–22.64 | **no** / – |
| GPT-6.1 | 1 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| GPT-6.1 | 1 | 1 | reputation | 10.4 ± 0.7 | 4.2 ± 0.4 | 3.7 ± 0.3 | 96 ± 2 / 9 ± 3 | 0.6 ± 0.0 | 19 | 0.37–2.23 | **no** / **no** |
| GPT-6.1 | 1 | 1 | fifo | 97.7 ± 1.4 | 4.9 ± 1.0 | 97.7 ± 1.4 | – | 169.0 ± 12.2 | 19 | 0.37–2.23 | **no** / – |
| GPT-6.1 | 1 | 10 | reputation | 22.1 ± 0.8 | 22.1 ± 0.8 | 3.7 ± 0.3 | 100 ± 0 / 100 ± 0 | 0.7 ± 0.0 | 19 | 0.37–2.23 | **no** / **no** |
| GPT-6.1 | 1 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 19 | 0.37–2.23 | **no** / – |
| GPT-6.1 | 3 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| GPT-6.1 | 3 | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.8 ± 0.3 | 3 ± 2 / 3 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| GPT-6.1 | 3 | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| GPT-6.1 | 3 | 10 | reputation | 19.0 ± 0.9 | 19.0 ± 0.9 | 3.6 ± 0.3 | 100 ± 0 / 100 ± 0 | 0.6 ± 0.0 | 61 | 1.21–7.28 | **no** / **no** |
| GPT-6.1 | 3 | 10 | fifo | 100.0 ± 0.0 | 99.8 ± 0.1 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 61 | 1.21–7.28 | **no** / – |
| GPT-6.1 | 5 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| GPT-6.1 | 5 | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.8 ± 0.3 | 3 ± 2 / 3 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| GPT-6.1 | 5 | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| GPT-6.1 | 5 | 10 | reputation | 14.9 ± 0.9 | 12.5 ± 0.9 | 3.7 ± 0.3 | 100 ± 0 / 78 ± 3 | 0.6 ± 0.0 | 105 | 2.11–12.65 | **no** / **no** |
| GPT-6.1 | 5 | 10 | fifo | 100.0 ± 0.0 | 84.9 ± 0.8 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 105 | 2.11–12.64 | **no** / – |
| GPT-6.1 | 10 | 0 | – | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 3 | 0.06–0.38 | **no** / – |
| GPT-6.1 | 10 | 1 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.8 ± 0.3 | 3 ± 2 / 3 ± 2 | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / **no** |
| GPT-6.1 | 10 | 1 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.0 ± 0.0 | 22 | 0.43–2.60 | **no** / – |
| GPT-6.1 | 10 | 10 | reputation | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.8 ± 0.3 | 3 ± 2 / 3 ± 2 | 0.0 ± 0.0 | 189 | 3.77–22.65 | **no** / **no** |
| GPT-6.1 | 10 | 10 | fifo | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | – | 0.1 ± 0.0 | 189 | 3.77–22.65 | **no** / – |

#### 15 validators

| Seat | Capacity /h | Spam /h | Order | Honest > 24 h (%) | Withdrawn (%) | Established > 24 h (%) | Newcomers > 24 h / withdrawn (%) | Wait, median (h) | Checks / validator / day | Spend $ / validator / day | Holds: all / newcomers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | none | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| Opus 5.5 | none | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| Opus 5.5 | none | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| Opus 5.5 | none | 10 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / yes |
| Opus 5.5 | none | 10 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / – |
| Opus 5.5 | 1 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| Opus 5.5 | 1 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| Opus 5.5 | 1 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.1 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| Opus 5.5 | 1 | 10 | reputation | 16.7 ± 0.9 | 16.7 ± 0.9 | 0.0 ± 0.0 | 100 ± 0 / 100 ± 0 | 0.6 ± 0.0 | 22 | 0.44–2.66 | **no** / **no** |
| Opus 5.5 | 1 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 22 | 0.44–2.66 | **no** / – |
| Opus 5.5 | 3 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| Opus 5.5 | 3 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| Opus 5.5 | 3 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| Opus 5.5 | 3 | 10 | reputation | 9.2 ± 0.9 | 7.2 ± 0.9 | 0.0 ± 0.0 | 100 ± 0 / 76 ± 4 | 0.5 ± 0.0 | 63 | 1.26–7.58 | **no** / **no** |
| Opus 5.5 | 3 | 10 | fifo | 100.0 ± 0.0 | 85.4 ± 0.8 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 63 | 1.26–7.58 | **no** / – |
| Opus 5.5 | 5 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| Opus 5.5 | 5 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| Opus 5.5 | 5 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| Opus 5.5 | 5 | 10 | reputation | 2.8 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 | 72 ± 7 / 0 ± 0 | 0.5 ± 0.0 | 108 | 2.16–12.96 | yes / **no** |
| Opus 5.5 | 5 | 10 | fifo | 90.5 ± 1.4 | 0.0 ± 0.0 | 90.5 ± 1.4 | – | 69.8 ± 3.6 | 108 | 2.16–12.96 | **no** / – |
| Opus 5.5 | 10 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| Opus 5.5 | 10 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| Opus 5.5 | 10 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| Opus 5.5 | 10 | 10 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / yes |
| Opus 5.5 | 10 | 10 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / – |
| GPT-6.1 | none | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| GPT-6.1 | none | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| GPT-6.1 | none | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| GPT-6.1 | none | 10 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / yes |
| GPT-6.1 | none | 10 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / – |
| GPT-6.1 | 1 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| GPT-6.1 | 1 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| GPT-6.1 | 1 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.1 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| GPT-6.1 | 1 | 10 | reputation | 17.9 ± 0.8 | 17.9 ± 0.8 | 0.0 ± 0.0 | 100 ± 0 / 100 ± 0 | 0.6 ± 0.0 | 22 | 0.44–2.66 | **no** / **no** |
| GPT-6.1 | 1 | 10 | fifo | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 22 | 0.44–2.66 | **no** / – |
| GPT-6.1 | 3 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| GPT-6.1 | 3 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| GPT-6.1 | 3 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| GPT-6.1 | 3 | 10 | reputation | 11.6 ± 0.8 | 9.3 ± 0.8 | 0.0 ± 0.0 | 100 ± 0 / 79 ± 3 | 0.6 ± 0.0 | 63 | 1.26–7.58 | **no** / **no** |
| GPT-6.1 | 3 | 10 | fifo | 100.0 ± 0.0 | 85.4 ± 0.8 | 100.0 ± 0.0 | – | 336.0 ± 0.0 | 63 | 1.26–7.58 | **no** / – |
| GPT-6.1 | 5 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| GPT-6.1 | 5 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| GPT-6.1 | 5 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| GPT-6.1 | 5 | 10 | reputation | 4.6 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 | 76 ± 6 / 0 ± 0 | 0.5 ± 0.0 | 108 | 2.16–12.96 | **no** / **no** |
| GPT-6.1 | 5 | 10 | fifo | 90.5 ± 1.4 | 0.0 ± 0.0 | 90.5 ± 1.4 | – | 69.8 ± 3.6 | 108 | 2.16–12.96 | **no** / – |
| GPT-6.1 | 10 | 0 | – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 2 | 0.04–0.24 | yes / – |
| GPT-6.1 | 10 | 1 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / yes |
| GPT-6.1 | 10 | 1 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 13 | 0.27–1.60 | yes / – |
| GPT-6.1 | 10 | 10 | reputation | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 / 0 ± 0 | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / yes |
| GPT-6.1 | 10 | 10 | fifo | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | – | 0.0 ± 0.0 | 115 | 2.31–13.84 | yes / – |

### Simulation A, table `grid` (mean ± 2 SE over 40 seeds)

| Seat | Validators | Capacity /h | Spam /h | Order | Repo cap /h | Spam's form | Wait median (h) | Wait p90 (h) | > 24 h (%) | > 7 d (%) | Withdrawn (%) | Heal median (h) | Heal p90 (h) | Newcomers > 7 d (%) | Checks / validator / day | Spend $/day at $0.12 | Most in an hour | Checks on junk (%) | Queue max | Queue cleared in the last week (% of seeds) | Fee in $/check |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 4 | none | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | none | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.7 ± 2.0 | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | none | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | none | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.7 ± 2.0 | 188.7 ± 0.4 | 22.64 ± 0.05 | 22.9 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | none | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 188.7 ± 0.4 | 22.64 ± 0.05 | 22.9 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 1 | 0 | fifo | off | one | 0.0 ± 0.0 | 1.2 ± 0.1 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 28.0 ± 0.1 | – | 3.2 ± 0.1 | 0.38 ± 0.01 | 2.0 ± 0.0 | 0.0 ± 0.0 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 1 | 1 | reputation | off | one | 0.6 ± 0.0 | 9.6 ± 6.6 | 8.2 ± 0.6 | 5.2 ± 0.5 | 3.9 ± 0.4 | 27.6 ± 0.0 | 28.5 ± 0.1 | 31.5 ± 7.1 | 18.6 ± 0.0 | 2.23 ± 0.00 | 1.9 ± 0.1 | 83.1 ± 0.3 | 371 ± 17 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 1 | 1 | fifo | off | one | 169.0 ± 12.2 | 287.2 ± 12.3 | 97.7 ± 1.4 | 49.0 ± 4.0 | 4.9 ± 1.0 | 186.7 ± 11.1 | 302.8 ± 12.1 | – | 18.5 ± 0.0 | 2.23 ± 0.00 | 2.0 ± 0.1 | 85.6 ± 0.2 | 371 ± 16 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 1 | 10 | reputation | off | one | 0.7 ± 0.0 | 336.0 ± 0.0 | 21.5 ± 0.8 | 21.5 ± 0.8 | 21.5 ± 0.8 | 27.6 ± 0.0 | 28.1 ± 0.0 | 100.0 ± 0.0 | 18.6 ± 0.0 | 2.23 ± 0.00 | 1.9 ± 0.1 | 86.1 ± 0.3 | 19,929 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 1 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 18.6 ± 0.0 | 2.23 ± 0.00 | 1.8 ± 0.1 | 99.7 ± 0.0 | 19,685 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 3 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 3 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.3 ± 0.1 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.2 ± 0.1 | 3.7 ± 2.0 | 21.7 ± 0.1 | 2.60 ± 0.02 | 4.1 ± 0.1 | 85.5 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 3 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.4 ± 0.1 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.3 ± 0.1 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 4.1 ± 0.1 | 85.5 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 3 | 10 | reputation | off | one | 0.6 ± 0.0 | 336.0 ± 0.0 | 17.3 ± 1.1 | 17.3 ± 1.1 | 17.2 ± 1.1 | 27.5 ± 0.0 | 27.9 ± 0.0 | 100.0 ± 0.0 | 60.7 ± 0.1 | 7.28 ± 0.01 | 4.3 ± 0.1 | 95.5 ± 0.1 | 15,007 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 3 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 99.8 ± 0.1 | 374.7 ± 3.3 | 375.0 ± 3.4 | – | 60.6 ± 0.1 | 7.28 ± 0.01 | 4.0 ± 0.0 | 99.6 ± 0.0 | 14,764 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 5 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.7 ± 2.0 | 21.7 ± 0.1 | 2.60 ± 0.02 | 5.4 ± 0.2 | 85.5 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 5 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 5.4 ± 0.2 | 85.5 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 247.9 ± 44.4 | 12.7 ± 1.0 | 12.3 ± 1.0 | 10.6 ± 1.0 | 27.5 ± 0.0 | 27.9 ± 0.0 | 95.3 ± 1.9 | 105.4 ± 0.0 | 12.65 ± 0.01 | 6.7 ± 0.2 | 97.2 ± 0.1 | 9,772 ± 45 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 5 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 97.5 ± 0.4 | 84.9 ± 0.8 | 266.6 ± 6.2 | 349.3 ± 4.2 | – | 105.4 ± 0.1 | 12.64 ± 0.01 | 6.2 ± 0.1 | 99.4 ± 0.0 | 9,564 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 10 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 10 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.7 ± 2.0 | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 10 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 10 | 10 | reputation | off | one | 0.0 ± 0.0 | 0.4 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.3 ± 0.0 | 3.7 ± 2.0 | 188.7 ± 0.4 | 22.65 ± 0.04 | 12.4 ± 0.2 | 98.3 ± 0.0 | 30 ± 2 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 4 | 10 | 10 | fifo | off | one | 0.1 ± 0.0 | 0.9 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.1 ± 0.0 | 27.8 ± 0.0 | – | 188.7 ± 0.4 | 22.65 ± 0.04 | 12.3 ± 0.2 | 98.3 ± 0.0 | 31 ± 2 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | none | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | none | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | none | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | none | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 238.8 ± 0.5 | 28.66 ± 0.06 | 25.4 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | none | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 238.8 ± 0.5 | 28.66 ± 0.06 | 25.4 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 1 | 0 | fifo | off | one | 0.0 ± 0.0 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 10.0 ± 0.1 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 1.1 ± 0.1 | 0.0 ± 0.0 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 1 | 1 | reputation | off | one | 0.6 ± 0.0 | 1.3 ± 0.1 | 4.5 ± 0.5 | 1.4 ± 0.3 | 0.2 ± 0.1 | 9.6 ± 0.0 | 10.4 ± 0.1 | 29.8 ± 6.5 | 23.6 ± 0.0 | 2.83 ± 0.00 | 1.0 ± 0.0 | 82.5 ± 0.3 | 374 ± 17 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 1 | 1 | fifo | off | one | 163.3 ± 11.8 | 277.9 ± 12.9 | 97.8 ± 1.4 | 46.8 ± 4.1 | 1.2 ± 0.9 | 168.6 ± 11.1 | 285.7 ± 12.1 | – | 23.6 ± 0.0 | 2.83 ± 0.00 | 1.0 ± 0.0 | 85.2 ± 0.3 | 371 ± 16 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 1 | 10 | reputation | off | one | 0.7 ± 0.0 | 336.0 ± 0.0 | 18.6 ± 0.8 | 18.6 ± 0.8 | 18.6 ± 0.8 | 9.6 ± 0.0 | 10.0 ± 0.0 | 100.0 ± 0.0 | 23.6 ± 0.0 | 2.84 ± 0.00 | 1.1 ± 0.1 | 85.7 ± 0.3 | 19,928 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 1 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 23.6 ± 0.0 | 2.84 ± 0.00 | 1.1 ± 0.1 | 99.7 ± 0.0 | 19,674 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 3 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 3 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.2 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.3 ± 0.1 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 3.0 ± 0.0 | 85.0 ± 0.2 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 3 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.4 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.4 ± 0.1 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 3.0 ± 0.0 | 85.0 ± 0.2 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 3 | 10 | reputation | off | one | 0.6 ± 0.0 | 319.2 ± 23.4 | 14.7 ± 1.1 | 14.7 ± 1.1 | 14.7 ± 1.1 | 9.5 ± 0.0 | 9.9 ± 0.0 | 100.0 ± 0.0 | 70.9 ± 0.0 | 8.51 ± 0.00 | 3.0 ± 0.0 | 95.0 ± 0.1 | 15,557 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 3 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 70.9 ± 0.0 | 8.51 ± 0.00 | 3.1 ± 0.1 | 99.6 ± 0.0 | 15,304 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 156.0 ± 50.8 | 10.2 ± 0.9 | 10.2 ± 0.9 | 8.7 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.1 ± 0.1 | 96.8 ± 0.1 | 11,184 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 270.8 ± 6.3 | 334.6 ± 3.7 | – | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 10 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 10 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 10 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 10 | 10 | reputation | off | one | 0.5 ± 0.0 | 0.9 ± 0.0 | 0.2 ± 0.2 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.5 ± 0.0 | 9.9 ± 0.0 | 0.0 ± 0.0 | 236.0 ± 0.2 | 28.32 ± 0.02 | 10.3 ± 0.1 | 98.3 ± 0.0 | 317 ± 36 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 10 | 10 | fifo | off | one | 14.9 ± 2.5 | 24.2 ± 3.0 | 18.4 ± 7.2 | 0.0 ± 0.0 | 0.0 ± 0.0 | 23.8 ± 2.5 | 33.3 ± 3.0 | – | 236.0 ± 0.2 | 28.32 ± 0.02 | 10.1 ± 0.1 | 98.3 ± 0.0 | 324 ± 37 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | none | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | none | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | none | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | none | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 115.4 ± 0.2 | 13.84 ± 0.03 | 17.6 ± 0.3 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | none | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 115.4 ± 0.2 | 13.84 ± 0.03 | 17.6 ± 0.3 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 1 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 2.0 ± 0.0 | 0.0 ± 0.0 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 1 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.9 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 10.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 2.3 ± 0.1 | 85.0 ± 0.2 | 9 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 1 | 1 | fifo | off | one | 0.1 ± 0.0 | 1.5 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.1 ± 0.0 | 10.7 ± 0.1 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 2.4 ± 0.2 | 85.0 ± 0.2 | 9 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 1 | 10 | reputation | off | one | 0.6 ± 0.0 | 336.0 ± 0.0 | 16.7 ± 0.9 | 16.7 ± 0.9 | 16.7 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 100.0 ± 0.0 | 22.2 ± 0.0 | 2.66 ± 0.00 | 2.1 ± 0.1 | 92.4 ± 0.2 | 17,871 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 1 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 22.2 ± 0.0 | 2.66 ± 0.00 | 2.1 ± 0.1 | 99.7 ± 0.0 | 17,616 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 3 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 3 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 4.0 ± 0.0 | 85.0 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 3 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 4.0 ± 0.0 | 85.0 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 3 | 10 | reputation | off | one | 0.5 ± 0.0 | 105.8 ± 43.3 | 9.2 ± 0.9 | 8.9 ± 0.9 | 7.2 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 95.8 ± 1.9 | 63.2 ± 0.0 | 7.58 ± 0.01 | 4.0 ± 0.1 | 97.1 ± 0.1 | 10,014 ± 45 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 3 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 97.8 ± 0.3 | 85.4 ± 0.8 | 253.7 ± 6.0 | 333.2 ± 3.7 | – | 63.2 ± 0.0 | 7.58 ± 0.00 | 4.0 ± 0.0 | 99.4 ± 0.0 | 9,787 ± 45 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 5 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 5.0 ± 0.1 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 5 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 5.0 ± 0.1 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 5 | 10 | reputation | off | one | 0.5 ± 0.0 | 0.9 ± 0.0 | 2.8 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.5 ± 0.0 | 10.0 ± 0.1 | 0.0 ± 0.0 | 108.0 ± 0.0 | 12.96 ± 0.01 | 6.1 ± 0.1 | 98.2 ± 0.0 | 1,427 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 5 | 10 | fifo | off | one | 69.8 ± 3.6 | 115.0 ± 4.0 | 90.5 ± 1.4 | 0.0 ± 0.0 | 0.0 ± 0.0 | 78.6 ± 3.5 | 124.1 ± 4.1 | – | 108.0 ± 0.0 | 12.96 ± 0.00 | 6.2 ± 0.1 | 98.3 ± 0.0 | 1,431 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 10 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 10 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 10 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 10 | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 115.4 ± 0.2 | 13.84 ± 0.03 | 11.2 ± 0.1 | 98.3 ± 0.0 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 15 | 10 | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 115.4 ± 0.2 | 13.84 ± 0.03 | 11.2 ± 0.1 | 98.3 ± 0.0 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | none | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | none | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.3 ± 1.8 | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | none | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | none | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.3 ± 1.8 | 188.7 ± 0.4 | 22.64 ± 0.05 | 22.9 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | none | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 188.7 ± 0.4 | 22.64 ± 0.05 | 22.9 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 12 ± 11 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 1 | 0 | fifo | off | one | 0.0 ± 0.0 | 1.2 ± 0.1 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 28.0 ± 0.1 | – | 3.2 ± 0.1 | 0.38 ± 0.01 | 2.0 ± 0.0 | 0.0 ± 0.0 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 1 | 1 | reputation | off | one | 0.6 ± 0.0 | 47.1 ± 14.4 | 10.4 ± 0.7 | 6.4 ± 0.6 | 4.2 ± 0.4 | 27.6 ± 0.0 | 29.9 ± 1.9 | 39.6 ± 5.6 | 18.5 ± 0.0 | 2.23 ± 0.00 | 2.0 ± 0.0 | 83.1 ± 0.3 | 371 ± 17 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 1 | 1 | fifo | off | one | 169.0 ± 12.2 | 287.2 ± 12.3 | 97.7 ± 1.4 | 49.0 ± 4.0 | 4.9 ± 1.0 | 186.2 ± 11.5 | 303.3 ± 12.4 | – | 18.5 ± 0.0 | 2.23 ± 0.00 | 2.0 ± 0.1 | 85.6 ± 0.2 | 371 ± 16 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 1 | 10 | reputation | off | one | 0.7 ± 0.0 | 336.0 ± 0.0 | 22.1 ± 0.8 | 22.1 ± 0.8 | 22.1 ± 0.8 | 27.6 ± 0.0 | 28.0 ± 0.0 | 100.0 ± 0.0 | 18.6 ± 0.0 | 2.23 ± 0.00 | 2.0 ± 0.1 | 86.2 ± 0.3 | 19,927 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 1 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 18.6 ± 0.0 | 2.23 ± 0.00 | 1.8 ± 0.1 | 99.7 ± 0.0 | 19,685 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 3 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 3 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.3 ± 0.1 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.2 ± 0.1 | 3.3 ± 1.8 | 21.7 ± 0.1 | 2.60 ± 0.02 | 4.1 ± 0.1 | 85.5 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 3 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.4 ± 0.1 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.3 ± 0.1 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 4.1 ± 0.1 | 85.5 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 3 | 10 | reputation | off | one | 0.6 ± 0.0 | 336.0 ± 0.0 | 19.0 ± 0.9 | 19.0 ± 0.9 | 19.0 ± 0.9 | 27.5 ± 0.0 | 27.9 ± 0.0 | 100.0 ± 0.0 | 60.7 ± 0.0 | 7.28 ± 0.01 | 4.3 ± 0.1 | 95.6 ± 0.1 | 15,000 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 3 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 99.8 ± 0.1 | 375.5 ± 9.0 | 375.5 ± 9.0 | – | 60.6 ± 0.1 | 7.28 ± 0.01 | 4.0 ± 0.0 | 99.6 ± 0.0 | 14,764 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 5 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.3 ± 1.8 | 21.7 ± 0.1 | 2.60 ± 0.02 | 5.4 ± 0.2 | 85.5 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 5 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 5.4 ± 0.2 | 85.5 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 298.5 ± 32.4 | 14.9 ± 0.9 | 14.5 ± 0.9 | 12.5 ± 0.9 | 27.5 ± 0.0 | 27.9 ± 0.0 | 96.3 ± 1.3 | 105.4 ± 0.1 | 12.65 ± 0.01 | 6.6 ± 0.2 | 97.3 ± 0.1 | 9,768 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 5 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 97.5 ± 0.4 | 84.9 ± 0.8 | 266.7 ± 6.9 | 347.8 ± 5.3 | – | 105.4 ± 0.1 | 12.64 ± 0.01 | 6.2 ± 0.1 | 99.4 ± 0.0 | 9,564 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 10 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 10 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.3 ± 1.8 | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 10 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | – | 21.7 ± 0.1 | 2.60 ± 0.02 | 7.2 ± 0.2 | 85.5 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 10 | 10 | reputation | off | one | 0.0 ± 0.0 | 0.4 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.4 ± 0.0 | 3.3 ± 1.8 | 188.7 ± 0.4 | 22.65 ± 0.04 | 12.4 ± 0.2 | 98.3 ± 0.0 | 30 ± 2 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 10 | 10 | fifo | off | one | 0.1 ± 0.0 | 0.9 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.1 ± 0.0 | 27.8 ± 0.0 | – | 188.7 ± 0.4 | 22.65 ± 0.04 | 12.3 ± 0.2 | 98.3 ± 0.0 | 31 ± 2 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | none | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | none | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | none | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | none | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 238.8 ± 0.5 | 28.66 ± 0.06 | 25.4 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | none | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 238.8 ± 0.5 | 28.66 ± 0.06 | 25.4 ± 0.4 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 1 | 0 | fifo | off | one | 0.0 ± 0.0 | 1.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 10.0 ± 0.1 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 1.1 ± 0.1 | 0.0 ± 0.0 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 1 | 1 | reputation | off | one | 0.6 ± 0.0 | 4.0 ± 2.9 | 6.7 ± 0.6 | 2.7 ± 0.5 | 0.5 ± 0.3 | 9.6 ± 0.0 | 10.6 ± 0.1 | 38.1 ± 5.2 | 23.6 ± 0.0 | 2.83 ± 0.00 | 1.0 ± 0.0 | 82.6 ± 0.3 | 372 ± 17 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 1 | 1 | fifo | off | one | 163.3 ± 11.8 | 277.9 ± 12.9 | 97.8 ± 1.4 | 46.8 ± 4.1 | 1.2 ± 0.9 | 168.2 ± 11.6 | 285.9 ± 12.2 | – | 23.6 ± 0.0 | 2.83 ± 0.00 | 1.0 ± 0.0 | 85.2 ± 0.3 | 371 ± 16 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 1 | 10 | reputation | off | one | 0.7 ± 0.0 | 336.0 ± 0.0 | 19.2 ± 0.8 | 19.2 ± 0.8 | 19.2 ± 0.8 | 9.5 ± 0.0 | 10.0 ± 0.0 | 100.0 ± 0.0 | 23.6 ± 0.0 | 2.84 ± 0.00 | 1.0 ± 0.0 | 85.8 ± 0.3 | 19,926 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 1 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 23.6 ± 0.0 | 2.84 ± 0.00 | 1.1 ± 0.1 | 99.7 ± 0.0 | 19,674 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 3 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 3 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.2 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.3 ± 0.1 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 3.0 ± 0.0 | 85.0 ± 0.2 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 3 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.4 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.4 ± 0.1 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 3.0 ± 0.0 | 85.0 ± 0.2 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 3 | 10 | reputation | off | one | 0.6 ± 0.0 | 336.0 ± 0.0 | 16.4 ± 0.9 | 16.4 ± 0.9 | 16.4 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 100.0 ± 0.0 | 70.9 ± 0.0 | 8.51 ± 0.00 | 3.0 ± 0.0 | 95.1 ± 0.1 | 15,552 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 3 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 70.9 ± 0.0 | 8.51 ± 0.00 | 3.1 ± 0.1 | 99.6 ± 0.0 | 15,304 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 241.0 ± 45.4 | 12.7 ± 0.9 | 12.7 ± 0.9 | 11.1 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.1 ± 0.1 | 96.9 ± 0.1 | 11,177 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 269.8 ± 7.2 | 333.7 ± 4.8 | – | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 10 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 10 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 10 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 7.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 10 | 10 | reputation | off | one | 0.5 ± 0.0 | 1.0 ± 0.1 | 0.6 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.5 ± 0.0 | 10.0 ± 0.0 | 0.0 ± 0.0 | 236.0 ± 0.2 | 28.32 ± 0.02 | 10.3 ± 0.1 | 98.3 ± 0.0 | 317 ± 36 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 10 | 10 | fifo | off | one | 14.9 ± 2.5 | 24.2 ± 3.0 | 18.4 ± 7.2 | 0.0 ± 0.0 | 0.0 ± 0.0 | 23.8 ± 2.5 | 33.3 ± 3.1 | – | 236.0 ± 0.2 | 28.32 ± 0.02 | 10.1 ± 0.1 | 98.3 ± 0.0 | 324 ± 37 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | none | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | none | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | none | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | none | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 115.4 ± 0.2 | 13.84 ± 0.03 | 17.6 ± 0.3 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | none | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 115.4 ± 0.2 | 13.84 ± 0.03 | 17.6 ± 0.3 | 98.3 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 1 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 2.0 ± 0.0 | 0.0 ± 0.0 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 1 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.9 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 10.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 2.3 ± 0.1 | 85.0 ± 0.2 | 9 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 1 | 1 | fifo | off | one | 0.1 ± 0.0 | 1.5 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.1 ± 0.0 | 10.7 ± 0.1 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 2.4 ± 0.2 | 85.0 ± 0.2 | 9 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 1 | 10 | reputation | off | one | 0.6 ± 0.0 | 336.0 ± 0.0 | 17.9 ± 0.8 | 17.9 ± 0.8 | 17.9 ± 0.8 | 9.5 ± 0.0 | 9.9 ± 0.0 | 100.0 ± 0.0 | 22.2 ± 0.0 | 2.66 ± 0.00 | 2.1 ± 0.1 | 92.5 ± 0.1 | 17,869 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 1 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | 100.0 ± 0.0 | – | – | – | 22.2 ± 0.0 | 2.66 ± 0.00 | 2.1 ± 0.1 | 99.7 ± 0.0 | 17,616 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 3 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 3 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 4.0 ± 0.0 | 85.0 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 3 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 4.0 ± 0.0 | 85.0 ± 0.2 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 3 | 10 | reputation | off | one | 0.6 ± 0.0 | 209.5 ± 44.1 | 11.6 ± 0.8 | 11.3 ± 0.8 | 9.3 ± 0.8 | 9.5 ± 0.0 | 10.0 ± 0.0 | 97.0 ± 1.1 | 63.2 ± 0.0 | 7.58 ± 0.01 | 4.0 ± 0.0 | 97.1 ± 0.1 | 10,008 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 3 | 10 | fifo | off | one | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 97.8 ± 0.3 | 85.4 ± 0.8 | 253.8 ± 6.4 | 332.1 ± 4.1 | – | 63.2 ± 0.0 | 7.58 ± 0.00 | 4.0 ± 0.0 | 99.4 ± 0.0 | 9,787 ± 45 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 5 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 5.0 ± 0.1 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 5 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 5.0 ± 0.1 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 5 | 10 | reputation | off | one | 0.5 ± 0.0 | 1.0 ± 0.0 | 4.6 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.5 ± 0.0 | 10.4 ± 0.2 | 0.0 ± 0.0 | 108.0 ± 0.0 | 12.96 ± 0.01 | 6.2 ± 0.1 | 98.2 ± 0.0 | 1,428 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 5 | 10 | fifo | off | one | 69.8 ± 3.6 | 115.0 ± 4.0 | 90.5 ± 1.4 | 0.0 ± 0.0 | 0.0 ± 0.0 | 78.5 ± 3.7 | 124.4 ± 4.2 | – | 108.0 ± 0.0 | 12.96 ± 0.00 | 6.2 ± 0.1 | 98.3 ± 0.0 | 1,431 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 10 | 0 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 10 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 10 | 1 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 13.3 ± 0.1 | 1.60 ± 0.01 | 6.3 ± 0.2 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 10 | 10 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 115.4 ± 0.2 | 13.84 ± 0.03 | 11.2 ± 0.1 | 98.3 ± 0.0 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 15 | 10 | 10 | fifo | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 115.4 ± 0.2 | 13.84 ± 0.03 | 11.2 ± 0.1 | 98.3 ± 0.0 | 6 ± 0 | 100 ± 0 | 0.00 ± 0.00 |

### Simulation A, table `repo` (mean ± 2 SE over 40 seeds)

| Seat | Validators | Capacity /h | Spam /h | Order | Repo cap /h | Spam's form | Wait median (h) | Wait p90 (h) | > 24 h (%) | > 7 d (%) | Withdrawn (%) | Heal median (h) | Heal p90 (h) | Newcomers > 7 d (%) | Checks / validator / day | Spend $/day at $0.12 | Most in an hour | Checks on junk (%) | Queue max | Queue cleared in the last week (% of seeds) | Fee in $/check |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 7 | 5 | 1 | reputation | 7 | one | 0.0 ± 0.0 | 0.2 ± 0.0 | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.2 ± 0.1 | 0.0 ± 0.0 | 26.9 ± 0.1 | 3.23 ± 0.01 | 4.1 ± 0.1 | 84.7 ± 0.2 | 77 ± 9 | 5 ± 7 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | 7 | spread | 0.0 ± 0.0 | 0.3 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.4 ± 0.1 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | fifo | 7 | one | 0.0 ± 0.0 | 7.4 ± 3.3 | 5.8 ± 1.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 17.0 ± 3.5 | – | 26.9 ± 0.1 | 3.23 ± 0.01 | 4.1 ± 0.1 | 84.7 ± 0.2 | 77 ± 9 | 5 ± 7 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | fifo | 7 | spread | 0.0 ± 0.0 | 0.4 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.4 ± 0.1 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | 7 | one | 0.0 ± 0.0 | 0.2 ± 0.0 | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.4 ± 0.1 | 9.0 ± 0.0 | 9.2 ± 0.0 | 8.6 ± 2.6 | 27.2 ± 0.1 | 3.27 ± 0.01 | 4.1 ± 0.1 | 84.9 ± 0.2 | 19,651 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | 7 | spread | 0.6 ± 0.0 | 156.1 ± 50.8 | 10.2 ± 0.9 | 10.2 ± 0.9 | 8.8 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.1 ± 0.1 | 96.8 ± 0.1 | 11,183 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | fifo | 7 | one | 0.0 ± 0.0 | 176.8 ± 53.6 | 10.2 ± 0.6 | 10.2 ± 0.6 | 10.2 ± 0.6 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.2 ± 0.1 | 3.27 ± 0.01 | 4.0 ± 0.1 | 86.3 ± 0.2 | 19,620 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | fifo | 7 | spread | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 271.0 ± 6.3 | 334.8 ± 3.7 | – | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | 21 | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | 21 | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | fifo | 21 | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | fifo | 21 | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | 21 | one | 0.0 ± 0.0 | 0.1 ± 0.0 | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.4 ± 0.1 | 9.0 ± 0.0 | 9.2 ± 0.0 | 8.7 ± 2.6 | 74.3 ± 0.1 | 8.91 ± 0.01 | 5.0 ± 0.0 | 94.5 ± 0.1 | 15,286 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | 21 | spread | 0.6 ± 0.0 | 156.0 ± 50.8 | 10.2 ± 0.9 | 10.2 ± 0.9 | 8.7 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.1 ± 0.1 | 96.8 ± 0.1 | 11,184 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | fifo | 21 | one | 0.0 ± 0.0 | 177.1 ± 53.5 | 10.2 ± 0.6 | 10.2 ± 0.6 | 10.2 ± 0.6 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 74.3 ± 0.1 | 8.91 ± 0.01 | 5.0 ± 0.0 | 95.0 ± 0.1 | 15,256 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | fifo | 21 | spread | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 270.8 ± 6.3 | 334.6 ± 3.7 | – | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | off | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | fifo | off | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | off | spread | 0.6 ± 0.0 | 156.0 ± 50.8 | 10.2 ± 0.9 | 10.2 ± 0.9 | 8.7 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.1 ± 0.1 | 96.8 ± 0.1 | 11,184 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | fifo | off | spread | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 270.8 ± 6.3 | 334.6 ± 3.7 | – | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | 7 | one | 0.0 ± 0.0 | 0.2 ± 0.0 | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.2 ± 0.1 | 0.0 ± 0.0 | 26.9 ± 0.1 | 3.23 ± 0.01 | 4.1 ± 0.1 | 84.7 ± 0.2 | 77 ± 9 | 5 ± 7 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | 7 | spread | 0.0 ± 0.0 | 0.3 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.4 ± 0.1 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | fifo | 7 | one | 0.0 ± 0.0 | 7.4 ± 3.3 | 5.8 ± 1.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 17.1 ± 3.7 | – | 26.9 ± 0.1 | 3.23 ± 0.01 | 4.1 ± 0.1 | 84.7 ± 0.2 | 77 ± 9 | 5 ± 7 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | fifo | 7 | spread | 0.0 ± 0.0 | 0.4 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.4 ± 0.1 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | 7 | one | 0.0 ± 0.0 | 0.2 ± 0.0 | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.6 ± 0.1 | 9.0 ± 0.0 | 9.2 ± 0.0 | 9.3 ± 2.0 | 27.2 ± 0.1 | 3.27 ± 0.01 | 4.1 ± 0.1 | 84.9 ± 0.2 | 19,650 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | 7 | spread | 0.6 ± 0.0 | 241.0 ± 45.4 | 12.8 ± 0.9 | 12.8 ± 0.9 | 11.1 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.1 ± 0.1 | 96.9 ± 0.1 | 11,177 ± 44 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | fifo | 7 | one | 0.0 ± 0.0 | 176.8 ± 53.6 | 10.2 ± 0.6 | 10.2 ± 0.6 | 10.2 ± 0.6 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.2 ± 0.1 | 3.27 ± 0.01 | 4.0 ± 0.1 | 86.3 ± 0.2 | 19,620 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | fifo | 7 | spread | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 270.1 ± 7.2 | 333.9 ± 4.8 | – | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | 21 | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | 21 | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | fifo | 21 | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 5 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | fifo | 21 | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | 21 | one | 0.0 ± 0.0 | 0.1 ± 0.0 | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.6 ± 0.1 | 9.0 ± 0.0 | 9.1 ± 0.0 | 9.4 ± 2.0 | 74.2 ± 0.1 | 8.91 ± 0.01 | 5.0 ± 0.0 | 94.5 ± 0.1 | 15,286 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | 21 | spread | 0.6 ± 0.0 | 241.0 ± 45.4 | 12.7 ± 0.9 | 12.7 ± 0.9 | 11.1 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.1 ± 0.1 | 96.9 ± 0.1 | 11,177 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | fifo | 21 | one | 0.0 ± 0.0 | 177.1 ± 53.5 | 10.2 ± 0.6 | 10.2 ± 0.6 | 10.2 ± 0.6 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 74.3 ± 0.1 | 8.91 ± 0.01 | 5.0 ± 0.0 | 95.0 ± 0.1 | 15,256 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | fifo | 21 | spread | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 269.8 ± 7.2 | 333.7 ± 4.8 | – | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | off | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | fifo | off | spread | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | – | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | off | spread | 0.6 ± 0.0 | 241.0 ± 45.4 | 12.7 ± 0.9 | 12.7 ± 0.9 | 11.1 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.1 ± 0.1 | 96.9 ± 0.1 | 11,177 ± 43 | 0 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | fifo | off | spread | 336.0 ± 0.0 | 336.0 ± 0.0 | 100.0 ± 0.0 | 99.9 ± 0.1 | 90.1 ± 0.6 | 269.8 ± 7.2 | 333.7 ± 4.8 | – | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.2 ± 0.1 | 99.5 ± 0.0 | 10,947 ± 42 | 0 ± 0 | 0.00 ± 0.00 |

### Simulation A, table `fee` (mean ± 2 SE over 40 seeds)

| Seat | Validators | Capacity /h | Spam /h | Order | Repo cap /h | Spam's form | Wait median (h) | Wait p90 (h) | > 24 h (%) | > 7 d (%) | Withdrawn (%) | Heal median (h) | Heal p90 (h) | Newcomers > 7 d (%) | Checks / validator / day | Spend $/day at $0.12 | Most in an hour | Checks on junk (%) | Queue max | Queue cleared in the last week (% of seeds) | Fee in $/check |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 4 | 5 | 0 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.7 ± 2.0 | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 1.62 ± 0.00 |
| Opus 5.5 | 4 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.7 ± 2.0 | 21.7 ± 0.1 | 2.60 ± 0.02 | 5.4 ± 0.2 | 85.5 ± 0.2 | 2 ± 0 | 100 ± 0 | 1.62 ± 0.00 |
| Opus 5.5 | 4 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 247.9 ± 44.4 | 12.7 ± 1.0 | 12.3 ± 1.0 | 10.6 ± 1.0 | 27.5 ± 0.0 | 27.9 ± 0.0 | 95.3 ± 1.9 | 105.4 ± 0.0 | 12.65 ± 0.01 | 6.7 ± 0.2 | 97.2 ± 0.1 | 9,772 ± 45 | 0 ± 0 | 1.62 ± 0.00 |
| Opus 5.5 | 7 | 5 | 0 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.73 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.73 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 156.0 ± 50.8 | 10.2 ± 0.9 | 10.2 ± 0.9 | 8.7 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.18 ± 0.00 | 5.1 ± 0.1 | 96.8 ± 0.1 | 11,184 ± 44 | 0 ± 0 | 0.73 ± 0.00 |
| Opus 5.5 | 15 | 5 | 0 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.71 ± 0.00 |
| Opus 5.5 | 15 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 5.0 ± 0.1 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.71 ± 0.00 |
| Opus 5.5 | 15 | 5 | 10 | reputation | off | one | 0.5 ± 0.0 | 0.9 ± 0.0 | 2.8 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.5 ± 0.0 | 10.0 ± 0.1 | 0.0 ± 0.0 | 108.0 ± 0.0 | 12.96 ± 0.01 | 6.1 ± 0.1 | 98.2 ± 0.0 | 1,427 ± 42 | 0 ± 0 | 0.71 ± 0.00 |
| Opus 5.5 | 7 | 5 | 1 | reputation | off | reputable | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 21.4 ± 0.7 | 2.56 ± 0.09 | 5.0 ± 0.0 | 80.5 ± 0.8 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| Opus 5.5 | 7 | 5 | 10 | reputation | off | reputable | 0.0 ± 0.0 | 0.1 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.1 ± 0.1 | 0.0 ± 0.0 | 34.0 ± 1.1 | 4.08 ± 0.14 | 5.0 ± 0.0 | 87.7 ± 0.5 | 28 ± 1 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 4 | 5 | 0 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.3 ± 1.8 | 3.1 ± 0.1 | 0.38 ± 0.01 | 3.2 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 1.62 ± 0.00 |
| GPT-6.1 | 4 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 3.7 ± 0.3 | 3.7 ± 0.3 | 3.7 ± 0.3 | 27.0 ± 0.0 | 27.0 ± 0.0 | 3.3 ± 1.8 | 21.7 ± 0.1 | 2.60 ± 0.02 | 5.4 ± 0.2 | 85.5 ± 0.2 | 2 ± 0 | 100 ± 0 | 1.62 ± 0.00 |
| GPT-6.1 | 4 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 298.5 ± 32.4 | 14.9 ± 0.9 | 14.5 ± 0.9 | 12.5 ± 0.9 | 27.5 ± 0.0 | 27.9 ± 0.0 | 96.3 ± 1.3 | 105.4 ± 0.1 | 12.65 ± 0.01 | 6.6 ± 0.2 | 97.3 ± 0.1 | 9,768 ± 43 | 0 ± 0 | 1.62 ± 0.00 |
| GPT-6.1 | 7 | 5 | 0 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 4.1 ± 0.1 | 0.50 ± 0.01 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.73 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 27.6 ± 0.2 | 3.31 ± 0.02 | 5.0 ± 0.0 | 85.0 ± 0.2 | 3 ± 0 | 100 ± 0 | 0.73 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | off | one | 0.6 ± 0.0 | 241.0 ± 45.4 | 12.7 ± 0.9 | 12.7 ± 0.9 | 11.1 ± 0.9 | 9.5 ± 0.0 | 9.9 ± 0.0 | 99.9 ± 0.2 | 118.2 ± 0.0 | 14.19 ± 0.00 | 5.1 ± 0.1 | 96.9 ± 0.1 | 11,177 ± 43 | 0 ± 0 | 0.73 ± 0.00 |
| GPT-6.1 | 15 | 5 | 0 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 2.0 ± 0.0 | 0.24 ± 0.00 | 3.3 ± 0.2 | 0.0 ± 0.0 | 0 ± 0 | 100 ± 0 | 0.71 ± 0.00 |
| GPT-6.1 | 15 | 5 | 1 | reputation | off | one | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 13.3 ± 0.1 | 1.60 ± 0.01 | 5.0 ± 0.1 | 85.0 ± 0.2 | 0 ± 0 | 100 ± 0 | 0.71 ± 0.00 |
| GPT-6.1 | 15 | 5 | 10 | reputation | off | one | 0.5 ± 0.0 | 1.0 ± 0.0 | 4.6 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.5 ± 0.0 | 10.4 ± 0.2 | 0.0 ± 0.0 | 108.0 ± 0.0 | 12.96 ± 0.01 | 6.2 ± 0.1 | 98.2 ± 0.0 | 1,428 ± 42 | 0 ± 0 | 0.71 ± 0.00 |
| GPT-6.1 | 7 | 5 | 1 | reputation | off | reputable | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.0 ± 0.0 | 0.0 ± 0.0 | 21.4 ± 0.7 | 2.56 ± 0.09 | 5.0 ± 0.0 | 80.5 ± 0.8 | 2 ± 0 | 100 ± 0 | 0.00 ± 0.00 |
| GPT-6.1 | 7 | 5 | 10 | reputation | off | reputable | 0.0 ± 0.0 | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 9.0 ± 0.0 | 9.2 ± 0.1 | 0.0 ± 0.0 | 34.3 ± 1.1 | 4.12 ± 0.14 | 5.0 ± 0.1 | 87.8 ± 0.4 | 28 ± 1 | 100 ± 0 | 0.00 ± 0.00 |

### Simulation B, table `tee` (mean ± 2 SE; bold: the attacker above its twin)

| Bad fixes | Form | Target's honest validators | Attackers | Minimum | Stake cap × | Listed (%) | Bad fixes paid: target / elsewhere | …with its validators honest | Of submitted | Healed: attacker / twin (%) | Attacker − twin ($ a year) | Attacker − the accomplice alone (the broken TEE's part, $) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| the tests fail them | one | 1 | 3 | 0 | 0 | 100 ± 0 | 54.3 ± 1.8 / 0.0 ± 0.0 | 12.4 ± 1.3 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **3,732 ± 186** | **4,008 ± 192** |
| the tests fail them | one | 1 | 3 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 1 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 1 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 1 | 10 | 0 | 0 | 100 ± 0 | 56.5 ± 1.8 / 0.0 ± 0.0 | 12.5 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **3,950 ± 194** | **4,228 ± 199** |
| the tests fail them | one | 1 | 10 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 1 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 1 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 3 | 3 | 0 | 0 | 100 ± 0 | 27.6 ± 1.3 / 0.0 ± 0.0 | 12.5 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **1,163 ± 147** | **1,434 ± 119** |
| the tests fail them | one | 3 | 3 | 3 | 0 | 100 ± 0 | 27.6 ± 1.3 / 0.0 ± 0.0 | 12.5 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **1,164 ± 147** | **1,434 ± 119** |
| the tests fail them | one | 3 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 3 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 3 | 10 | 0 | 0 | 100 ± 0 | 44.2 ± 1.5 / 0.0 ± 0.0 | 12.5 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **2,762 ± 150** | **3,041 ± 157** |
| the tests fail them | one | 3 | 10 | 3 | 0 | 100 ± 0 | 44.2 ± 1.5 / 0.0 ± 0.0 | 12.5 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **2,763 ± 150** | **3,041 ± 157** |
| the tests fail them | one | 3 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 3 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 5 | 3 | 0 | 0 | 100 ± 0 | 12.8 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -129 ± 138 | **9 ± 2** |
| the tests fail them | one | 5 | 3 | 3 | 0 | 100 ± 0 | 12.8 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -129 ± 138 | **9 ± 2** |
| the tests fail them | one | 5 | 3 | 5 | 0 | 100 ± 0 | 12.8 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -129 ± 138 | **9 ± 2** |
| the tests fail them | one | 5 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 5 | 10 | 0 | 0 | 100 ± 0 | 12.9 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -134 ± 137 | **18 ± 10** |
| the tests fail them | one | 5 | 10 | 3 | 0 | 100 ± 0 | 12.9 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -134 ± 137 | **18 ± 10** |
| the tests fail them | one | 5 | 10 | 5 | 0 | 100 ± 0 | 12.9 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -133 ± 137 | **18 ± 10** |
| the tests fail them | one | 5 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| the tests fail them | one | 10 | 3 | 0 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 147 | **8 ± 2** |
| the tests fail them | one | 10 | 3 | 3 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 147 | **8 ± 2** |
| the tests fail them | one | 10 | 3 | 5 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 147 | **8 ± 2** |
| the tests fail them | one | 10 | 3 | 7 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 147 | **8 ± 2** |
| the tests fail them | one | 10 | 10 | 0 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 146 | **17 ± 3** |
| the tests fail them | one | 10 | 10 | 3 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 146 | **17 ± 3** |
| the tests fail them | one | 10 | 10 | 5 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 146 | **17 ± 3** |
| the tests fail them | one | 10 | 10 | 7 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 146 | **17 ± 3** |
| the tests fail them | spread | 1 | 3 | 0 | 0 | 100 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -548 ± 122 | **1 ± 1** |
| the tests fail them | spread | 1 | 3 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -93 ± 119 | **1 ± 1** |
| the tests fail them | spread | 1 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -93 ± 119 | **1 ± 1** |
| the tests fail them | spread | 1 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -93 ± 119 | **1 ± 1** |
| the tests fail them | spread | 1 | 10 | 0 | 0 | 100 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -255 ± 126 | **1 ± 1** |
| the tests fail them | spread | 1 | 10 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -132 ± 123 | **1 ± 1** |
| the tests fail them | spread | 1 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -132 ± 123 | **1 ± 1** |
| the tests fail them | spread | 1 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -132 ± 123 | **1 ± 1** |
| the tests fail them | spread | 3 | 3 | 0 | 0 | 100 ± 0 | 3.9 ± 0.7 / 9.0 ± 1.1 | 12.9 ± 1.3 | 262 ± 5 | 87 ± 1 / 87 ± 1 | -207 ± 132 | **3 ± 1** |
| the tests fail them | spread | 3 | 3 | 3 | 0 | 100 ± 0 | 3.9 ± 0.7 / 9.0 ± 1.1 | 12.9 ± 1.3 | 262 ± 5 | 87 ± 1 / 87 ± 1 | -207 ± 132 | **3 ± 1** |
| the tests fail them | spread | 3 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -93 ± 119 | **1 ± 1** |
| the tests fail them | spread | 3 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -93 ± 119 | **1 ± 1** |
| the tests fail them | spread | 3 | 10 | 0 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 87 ± 1 / 87 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 3 | 10 | 3 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 87 ± 1 / 87 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 3 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -132 ± 123 | **1 ± 1** |
| the tests fail them | spread | 3 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -132 ± 123 | **1 ± 1** |
| the tests fail them | spread | 5 | 3 | 0 | 0 | 100 ± 0 | 4.0 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.4 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -155 ± 138 | **3 ± 1** |
| the tests fail them | spread | 5 | 3 | 3 | 0 | 100 ± 0 | 4.0 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.4 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -155 ± 138 | **3 ± 1** |
| the tests fail them | spread | 5 | 3 | 5 | 0 | 100 ± 0 | 4.0 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.4 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -155 ± 138 | **3 ± 1** |
| the tests fail them | spread | 5 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 9.0 ± 1.1 | 9.0 ± 1.1 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -93 ± 119 | **1 ± 1** |
| the tests fail them | spread | 5 | 10 | 0 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 5 | 10 | 3 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 5 | 10 | 5 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 5 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 11.8 ± 1.3 | 11.8 ± 1.3 | 262 ± 5 | 0 ± 0 / 0 ± 0 | -132 ± 123 | **1 ± 1** |
| the tests fail them | spread | 10 | 3 | 0 | 0 | 100 ± 0 | 4.1 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -152 ± 137 | **2 ± 1** |
| the tests fail them | spread | 10 | 3 | 3 | 0 | 100 ± 0 | 4.1 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -152 ± 137 | **2 ± 1** |
| the tests fail them | spread | 10 | 3 | 5 | 0 | 100 ± 0 | 4.1 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -152 ± 137 | **2 ± 1** |
| the tests fail them | spread | 10 | 3 | 7 | 0 | 100 ± 0 | 4.1 ± 0.7 / 9.0 ± 1.1 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -152 ± 137 | **2 ± 1** |
| the tests fail them | spread | 10 | 10 | 0 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 10 | 10 | 3 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 10 | 10 | 5 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | spread | 10 | 10 | 7 | 0 | 100 ± 0 | 1.2 ± 0.4 / 11.8 ± 1.3 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -159 ± 128 | **1 ± 1** |
| the tests fail them | open | 28 | 3 | 0 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -89 ± 147 | **3 ± 1** |
| the tests fail them | open | 28 | 10 | 0 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -84 ± 147 | **9 ± 2** |
| the tests fail them | one | 1 | 3 | 0 | 0.1 | 100 ± 0 | 56.3 ± 1.9 / 0.0 ± 0.0 | 12.9 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **3,422 ± 165** | **3,761 ± 158** |
| the tests fail them | one | 1 | 10 | 0 | 0.1 | 100 ± 0 | 58.5 ± 1.9 / 0.0 ± 0.0 | 13.0 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **3,608 ± 163** | **3,947 ± 153** |
| the tests fail them | one | 3 | 3 | 0 | 0.1 | 100 ± 0 | 28.5 ± 1.2 / 0.0 ± 0.0 | 13.0 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,406 ± 157** | **1,547 ± 120** |
| the tests fail them | one | 3 | 10 | 0 | 0.1 | 100 ± 0 | 45.9 ± 1.6 / 0.0 ± 0.0 | 13.0 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **3,174 ± 185** | **3,322 ± 154** |
| the tests fail them | one | 5 | 3 | 0 | 0.1 | 100 ± 0 | 12.8 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -130 ± 138 | **9 ± 2** |
| the tests fail them | one | 5 | 10 | 0 | 0.1 | 100 ± 0 | 12.9 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -125 ± 141 | **18 ± 10** |
| the tests fail them | one | 10 | 3 | 0 | 0.1 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 147 | **8 ± 2** |
| the tests fail them | one | 10 | 10 | 0 | 0.1 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -93 ± 146 | **17 ± 3** |
| pass the tests, wrong | one | 1 | 3 | 0 | 0 | 100 ± 0 | 58.6 ± 1.8 / 0.0 ± 0.0 | 30.5 ± 1.7 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **4,126 ± 196** | **2,706 ± 168** |
| pass the tests, wrong | one | 1 | 3 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 1 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 1 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 1 | 10 | 0 | 0 | 100 ± 0 | 60.1 ± 1.9 / 0.0 ± 0.0 | 30.8 ± 1.6 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **4,269 ± 204** | **2,835 ± 178** |
| pass the tests, wrong | one | 1 | 10 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 1 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 1 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 3 | 3 | 0 | 0 | 100 ± 0 | 40.7 ± 1.7 / 0.0 ± 0.0 | 30.8 ± 1.6 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **2,392 ± 176** | **950 ± 100** |
| pass the tests, wrong | one | 3 | 3 | 3 | 0 | 100 ± 0 | 40.7 ± 1.7 / 0.0 ± 0.0 | 30.8 ± 1.6 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **2,392 ± 176** | **950 ± 100** |
| pass the tests, wrong | one | 3 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 3 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 3 | 10 | 0 | 0 | 100 ± 0 | 51.9 ± 1.7 / 0.0 ± 0.0 | 30.8 ± 1.6 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **3,498 ± 196** | **2,063 ± 154** |
| pass the tests, wrong | one | 3 | 10 | 3 | 0 | 100 ± 0 | 51.9 ± 1.7 / 0.0 ± 0.0 | 30.8 ± 1.6 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **3,498 ± 196** | **2,063 ± 154** |
| pass the tests, wrong | one | 3 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 3 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 5 | 3 | 0 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,823 ± 203** | **9 ± 2** |
| pass the tests, wrong | one | 5 | 3 | 3 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,823 ± 203** | **9 ± 2** |
| pass the tests, wrong | one | 5 | 3 | 5 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,824 ± 203** | **9 ± 2** |
| pass the tests, wrong | one | 5 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 5 | 10 | 0 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,825 ± 202** | **15 ± 7** |
| pass the tests, wrong | one | 5 | 10 | 3 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,825 ± 202** | **15 ± 7** |
| pass the tests, wrong | one | 5 | 10 | 5 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,825 ± 202** | **15 ± 7** |
| pass the tests, wrong | one | 5 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 | 262 ± 5 | 0 ± 0 / 0 ± 0 | 0 ± 0 | 0 ± 0 |
| pass the tests, wrong | one | 10 | 3 | 0 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,880 ± 206** | **8 ± 2** |
| pass the tests, wrong | one | 10 | 3 | 3 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,880 ± 206** | **8 ± 2** |
| pass the tests, wrong | one | 10 | 3 | 5 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,880 ± 206** | **8 ± 2** |
| pass the tests, wrong | one | 10 | 3 | 7 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,880 ± 206** | **8 ± 2** |
| pass the tests, wrong | one | 10 | 10 | 0 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,879 ± 206** | **17 ± 3** |
| pass the tests, wrong | one | 10 | 10 | 3 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,879 ± 206** | **17 ± 3** |
| pass the tests, wrong | one | 10 | 10 | 5 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,879 ± 206** | **17 ± 3** |
| pass the tests, wrong | one | 10 | 10 | 7 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,879 ± 206** | **17 ± 3** |
| pass the tests, wrong | spread | 1 | 3 | 0 | 0 | 100 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **717 ± 164** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 3 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,171 ± 162** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,171 ± 162** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,171 ± 162** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 10 | 0 | 0 | 100 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,520 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 10 | 3 | 0 | 0 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,643 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,643 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 1 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,643 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 3 | 3 | 0 | 0 | 100 ± 0 | 10.1 ± 0.9 / 21.6 ± 1.4 | 31.6 ± 1.7 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **1,650 ± 190** | **3 ± 1** |
| pass the tests, wrong | spread | 3 | 3 | 3 | 0 | 100 ± 0 | 10.1 ± 0.9 / 21.6 ± 1.4 | 31.6 ± 1.7 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **1,650 ± 190** | **3 ± 1** |
| pass the tests, wrong | spread | 3 | 3 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,171 ± 162** | **1 ± 1** |
| pass the tests, wrong | spread | 3 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,171 ± 162** | **1 ± 1** |
| pass the tests, wrong | spread | 3 | 10 | 0 | 0 | 100 ± 0 | 2.9 ± 0.6 / 29.1 ± 1.5 | 32.0 ± 1.7 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **1,778 ± 200** | **1 ± 1** |
| pass the tests, wrong | spread | 3 | 10 | 3 | 0 | 100 ± 0 | 2.9 ± 0.6 / 29.1 ± 1.5 | 32.0 ± 1.7 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **1,778 ± 200** | **1 ± 1** |
| pass the tests, wrong | spread | 3 | 10 | 5 | 0 | 0 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,643 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 3 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,643 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 5 | 3 | 0 | 0 | 100 ± 0 | 10.5 ± 0.8 / 21.6 ± 1.4 | 32.0 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,812 ± 202** | **3 ± 1** |
| pass the tests, wrong | spread | 5 | 3 | 3 | 0 | 100 ± 0 | 10.5 ± 0.8 / 21.6 ± 1.4 | 32.0 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,812 ± 202** | **3 ± 1** |
| pass the tests, wrong | spread | 5 | 3 | 5 | 0 | 100 ± 0 | 10.5 ± 0.8 / 21.6 ± 1.4 | 32.0 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,812 ± 202** | **3 ± 1** |
| pass the tests, wrong | spread | 5 | 3 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 21.6 ± 1.4 | 21.6 ± 1.4 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,171 ± 162** | **1 ± 1** |
| pass the tests, wrong | spread | 5 | 10 | 0 | 0 | 100 ± 0 | 3.0 ± 0.6 / 29.1 ± 1.5 | 32.1 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,834 ± 204** | **1 ± 1** |
| pass the tests, wrong | spread | 5 | 10 | 3 | 0 | 100 ± 0 | 3.0 ± 0.6 / 29.1 ± 1.5 | 32.1 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,834 ± 204** | **1 ± 1** |
| pass the tests, wrong | spread | 5 | 10 | 5 | 0 | 100 ± 0 | 3.0 ± 0.6 / 29.1 ± 1.5 | 32.1 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,834 ± 204** | **1 ± 1** |
| pass the tests, wrong | spread | 5 | 10 | 7 | 0 | 0 ± 0 | 0.0 ± 0.0 / 29.1 ± 1.5 | 29.1 ± 1.5 | 262 ± 5 | 0 ± 0 / 0 ± 0 | **1,643 ± 191** | **1 ± 1** |
| pass the tests, wrong | spread | 10 | 3 | 0 | 0 | 100 ± 0 | 10.7 ± 0.8 / 21.6 ± 1.4 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,826 ± 202** | **2 ± 1** |
| pass the tests, wrong | spread | 10 | 3 | 3 | 0 | 100 ± 0 | 10.7 ± 0.8 / 21.6 ± 1.4 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,826 ± 202** | **2 ± 1** |
| pass the tests, wrong | spread | 10 | 3 | 5 | 0 | 100 ± 0 | 10.7 ± 0.8 / 21.6 ± 1.4 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,826 ± 202** | **2 ± 1** |
| pass the tests, wrong | spread | 10 | 3 | 7 | 0 | 100 ± 0 | 10.7 ± 0.8 / 21.6 ± 1.4 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,826 ± 202** | **2 ± 1** |
| pass the tests, wrong | spread | 10 | 10 | 0 | 0 | 100 ± 0 | 3.1 ± 0.6 / 29.1 ± 1.5 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,835 ± 204** | **1 ± 1** |
| pass the tests, wrong | spread | 10 | 10 | 3 | 0 | 100 ± 0 | 3.1 ± 0.6 / 29.1 ± 1.5 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,835 ± 204** | **1 ± 1** |
| pass the tests, wrong | spread | 10 | 10 | 5 | 0 | 100 ± 0 | 3.1 ± 0.6 / 29.1 ± 1.5 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,835 ± 204** | **1 ± 1** |
| pass the tests, wrong | spread | 10 | 10 | 7 | 0 | 100 ± 0 | 3.1 ± 0.6 / 29.1 ± 1.5 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,835 ± 204** | **1 ± 1** |
| pass the tests, wrong | open | 28 | 3 | 0 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,884 ± 206** | **3 ± 1** |
| pass the tests, wrong | open | 28 | 10 | 0 | 0 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,888 ± 206** | **9 ± 2** |
| pass the tests, wrong | one | 1 | 3 | 0 | 0.1 | 100 ± 0 | 60.9 ± 1.9 / 0.0 ± 0.0 | 31.8 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **3,802 ± 162** | **2,524 ± 145** |
| pass the tests, wrong | one | 1 | 10 | 0 | 0.1 | 100 ± 0 | 62.4 ± 1.9 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **3,932 ± 162** | **2,640 ± 147** |
| pass the tests, wrong | one | 3 | 3 | 0 | 0.1 | 100 ± 0 | 42.5 ± 1.7 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **2,821 ± 186** | **1,050 ± 89** |
| pass the tests, wrong | one | 3 | 10 | 0 | 0.1 | 100 ± 0 | 54.0 ± 1.7 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **4,022 ± 210** | **2,257 ± 164** |
| pass the tests, wrong | one | 5 | 3 | 0 | 0.1 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,805 ± 199** | **9 ± 2** |
| pass the tests, wrong | one | 5 | 10 | 0 | 0.1 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | **1,806 ± 198** | **15 ± 7** |
| pass the tests, wrong | one | 10 | 3 | 0 | 0.1 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,880 ± 206** | **8 ± 2** |
| pass the tests, wrong | one | 10 | 10 | 0 | 0.1 | 100 ± 0 | 32.2 ± 1.7 / 0.0 ± 0.0 | 32.2 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | **1,879 ± 206** | **17 ± 3** |

### Simulation B, table `rep` (mean ± 2 SE; bold: the attacker above its twin)

| Bad fixes | Form | Target's honest validators | Attackers | Minimum | Stake cap × | Listed (%) | Bad fixes paid: target / elsewhere | …with its validators honest | Of submitted | Healed: attacker / twin (%) | Attacker − twin ($ a year) | Attacker − the accomplice alone (the broken TEE's part, $) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| the tests fail them | one | 1 | 3 | 0 | 0 | 100 ± 0 | 56.1 ± 2.0 / 0.0 ± 0.0 | 12.9 ± 1.3 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **1,162 ± 79** | **2,008 ± 78** |
| the tests fail them | one | 1 | 10 | 0 | 0 | 100 ± 0 | 58.5 ± 1.9 / 0.0 ± 0.0 | 13.0 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **1,263 ± 75** | **2,117 ± 77** |
| the tests fail them | one | 3 | 3 | 0 | 0 | 100 ± 0 | 28.4 ± 1.8 / 0.0 ± 0.0 | 13.0 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | -128 ± 78 | **717 ± 63** |
| the tests fail them | one | 3 | 10 | 0 | 0 | 100 ± 0 | 45.0 ± 1.6 / 0.0 ± 0.0 | 13.0 ± 1.3 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **639 ± 63** | **1,487 ± 58** |
| the tests fail them | one | 5 | 3 | 0 | 0 | 100 ± 0 | 12.8 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -845 ± 61 | **8 ± 2** |
| the tests fail them | one | 5 | 10 | 0 | 0 | 100 ± 0 | 12.9 ± 1.3 / 0.0 ± 0.0 | 12.8 ± 1.3 | 262 ± 5 | 90 ± 1 / 90 ± 1 | -841 ± 61 | **19 ± 5** |
| the tests fail them | one | 10 | 3 | 0 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -830 ± 64 | **10 ± 2** |
| the tests fail them | one | 10 | 10 | 0 | 0 | 100 ± 0 | 13.1 ± 1.3 / 0.0 ± 0.0 | 13.1 ± 1.3 | 262 ± 5 | 91 ± 1 / 91 ± 1 | -832 ± 64 | **15 ± 3** |
| pass the tests, wrong | one | 1 | 3 | 0 | 0 | 100 ± 0 | 61.0 ± 2.0 / 0.0 ± 0.0 | 31.8 ± 1.7 | 262 ± 5 | 87 ± 1 / 87 ± 1 | **1,387 ± 78** | **1,365 ± 71** |
| pass the tests, wrong | one | 1 | 10 | 0 | 0 | 100 ± 0 | 62.4 ± 1.9 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **1,441 ± 76** | **1,417 ± 71** |
| pass the tests, wrong | one | 3 | 3 | 0 | 0 | 100 ± 0 | 42.8 ± 1.9 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **532 ± 80** | **500 ± 57** |
| pass the tests, wrong | one | 3 | 10 | 0 | 0 | 100 ± 0 | 53.2 ± 1.8 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 88 ± 1 / 88 ± 1 | **1,015 ± 68** | **986 ± 52** |
| pass the tests, wrong | one | 5 | 3 | 0 | 0 | 100 ± 0 | 31.6 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | 17 ± 71 | **8 ± 2** |
| pass the tests, wrong | one | 5 | 10 | 0 | 0 | 100 ± 0 | 31.7 ± 1.7 / 0.0 ± 0.0 | 31.6 ± 1.7 | 262 ± 5 | 90 ± 1 / 90 ± 1 | 21 ± 72 | **18 ± 6** |
| pass the tests, wrong | one | 10 | 3 | 0 | 0 | 100 ± 0 | 32.1 ± 1.7 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | 48 ± 72 | **10 ± 2** |
| pass the tests, wrong | one | 10 | 10 | 0 | 0 | 100 ± 0 | 32.1 ± 1.7 / 0.0 ± 0.0 | 32.1 ± 1.7 | 262 ± 5 | 91 ± 1 / 91 ± 1 | 47 ± 72 | **15 ± 3** |

### Simulation B, table `silence` (mean ± 2 SE; bold: the attacker above its twin)

| Target's honest validators | Attackers | Minimum | Listed (%) | Healed: attacker / twin / absent (%) | Heal median (h): attacker / twin | Expired (%) | Stuck (%) | Harm, healed twin − attacker (points) | Silences | Suspensions | Attacker − twin ($) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 0 | 100 ± 0 | 3 ± 1 / 87 ± 1 / 0 ± 0 | 2,556 ± 512 / 27 ± 0 | 71.6 ± 1.5 | 24.3 ± 1.3 | 84.3 ± 1.4 | 50 ± 3 | 7.8 ± 0.6 | -257 ± 17 |
| 1 | 3 | 3 | 5 ± 0 | 0 ± 0 / 87 ± 1 / 0 ± 0 | – / 27 ± 0 | 0.2 ± 0.1 | 4.4 ± 0.4 | 87.3 ± 1.1 | 11 ± 1 | 1.0 ± 0.0 | -58 ± 5 |
| 1 | 3 | 5 | 0 ± 0 | 0 ± 0 / 0 ± 0 / 0 ± 0 | – / – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 0.0 ± 0.0 | 0 ± 0 |
| 1 | 3 | 7 | 0 ± 0 | 0 ± 0 / 0 ± 0 / 0 ± 0 | – / – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 0.0 ± 0.0 | 0 ± 0 |
| 1 | 10 | 0 | 100 ± 0 | 6 ± 1 / 91 ± 1 / 0 ± 0 | 2,341 ± 370 / 9 ± 0 | 64.8 ± 0.8 | 27.7 ± 1.5 | 84.7 ± 1.7 | 188 ± 9 | 20.5 ± 0.6 | -978 ± 44 |
| 1 | 10 | 3 | 9 ± 1 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 9.0 ± 0.7 | 91.2 ± 0.9 | 52 ± 2 | 6.2 ± 0.5 | -262 ± 9 |
| 1 | 10 | 5 | 8 ± 1 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 8.2 ± 0.6 | 91.2 ± 0.9 | 49 ± 1 | 5.2 ± 0.4 | -248 ± 8 |
| 1 | 10 | 7 | 7 ± 1 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 6.6 ± 0.5 | 91.2 ± 0.9 | 45 ± 1 | 3.8 ± 0.3 | -225 ± 9 |
| 3 | 3 | 0 | 100 ± 0 | 77 ± 2 / 91 ± 1 / 87 ± 1 | 27 ± 0 / 15 ± 0 | 2.6 ± 0.4 | 12.7 ± 1.0 | 13.7 ± 1.2 | 61 ± 2 | 8.4 ± 0.2 | -321 ± 8 |
| 3 | 3 | 3 | 100 ± 0 | 77 ± 2 / 91 ± 1 / 87 ± 1 | 27 ± 0 / 15 ± 0 | 2.5 ± 0.4 | 12.9 ± 1.1 | 14.0 ± 1.3 | 61 ± 2 | 8.4 ± 0.2 | -321 ± 9 |
| 3 | 3 | 5 | 4 ± 0 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 15 ± 0 | 0.0 ± 0.0 | 4.1 ± 0.4 | 91.2 ± 1.0 | 16 ± 0 | 2.0 ± 0.0 | -81 ± 3 |
| 3 | 3 | 7 | 0 ± 0 | 0 ± 0 / 0 ± 0 / 0 ± 0 | – / – | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0 ± 0 | 0.0 ± 0.0 | 0 ± 0 |
| 3 | 10 | 0 | 100 ± 0 | 82 ± 1 / 91 ± 1 / 87 ± 1 | 27 ± 0 / 9 ± 0 | 3.2 ± 0.5 | 7.8 ± 0.5 | 9.6 ± 0.8 | 70 ± 3 | 10.9 ± 0.2 | -358 ± 13 |
| 3 | 10 | 3 | 100 ± 0 | 82 ± 1 / 91 ± 1 / 87 ± 1 | 27 ± 0 / 9 ± 0 | 3.1 ± 0.5 | 7.8 ± 0.5 | 9.6 ± 0.8 | 70 ± 2 | 10.9 ± 0.2 | -357 ± 13 |
| 3 | 10 | 5 | 6 ± 0 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 6.0 ± 0.5 | 91.2 ± 0.9 | 57 ± 1 | 8.2 ± 0.3 | -290 ± 4 |
| 3 | 10 | 7 | 5 ± 0 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 4.9 ± 0.5 | 91.2 ± 0.9 | 54 ± 1 | 6.6 ± 0.2 | -275 ± 5 |
| 5 | 3 | 0 | 100 ± 0 | 82 ± 1 / 91 ± 1 / 89 ± 1 | 15 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 10.7 ± 1.0 | 9.2 ± 1.0 | 57 ± 1 | 8.3 ± 0.2 | -301 ± 8 |
| 5 | 3 | 3 | 100 ± 0 | 82 ± 1 / 91 ± 1 / 89 ± 1 | 15 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 10.6 ± 1.0 | 9.2 ± 1.0 | 57 ± 2 | 8.3 ± 0.2 | -301 ± 8 |
| 5 | 3 | 5 | 100 ± 0 | 82 ± 1 / 91 ± 1 / 89 ± 1 | 15 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 10.7 ± 1.0 | 9.2 ± 1.0 | 57 ± 2 | 8.3 ± 0.2 | -301 ± 8 |
| 5 | 3 | 7 | 4 ± 0 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 4.0 ± 0.4 | 91.2 ± 1.0 | 16 ± 0 | 2.0 ± 0.0 | -81 ± 2 |
| 5 | 10 | 0 | 100 ± 0 | 86 ± 1 / 91 ± 1 / 89 ± 1 | 15 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 5.8 ± 0.5 | 5.0 ± 0.6 | 65 ± 2 | 10.7 ± 0.2 | -336 ± 9 |
| 5 | 10 | 3 | 100 ± 0 | 86 ± 1 / 91 ± 1 / 89 ± 1 | 15 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 5.8 ± 0.5 | 5.1 ± 0.6 | 65 ± 2 | 10.7 ± 0.2 | -335 ± 9 |
| 5 | 10 | 5 | 100 ± 0 | 86 ± 1 / 91 ± 1 / 89 ± 1 | 15 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 5.8 ± 0.5 | 5.1 ± 0.5 | 65 ± 2 | 10.7 ± 0.2 | -335 ± 9 |
| 5 | 10 | 7 | 3 ± 0 | 0 ± 0 / 91 ± 1 / 0 ± 0 | – / 9 ± 0 | 0.0 ± 0.0 | 3.1 ± 0.4 | 91.2 ± 0.9 | 57 ± 1 | 7.7 ± 0.4 | -288 ± 5 |
| 10 | 3 | 0 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 53 ± 1 | 8.6 ± 0.2 | -279 ± 5 |
| 10 | 3 | 3 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 53 ± 1 | 8.6 ± 0.2 | -279 ± 5 |
| 10 | 3 | 5 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 53 ± 1 | 8.6 ± 0.2 | -279 ± 5 |
| 10 | 3 | 7 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 53 ± 1 | 8.6 ± 0.2 | -279 ± 5 |
| 10 | 10 | 0 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 65 ± 1 | 10.6 ± 0.2 | -337 ± 7 |
| 10 | 10 | 3 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 65 ± 1 | 10.6 ± 0.2 | -337 ± 7 |
| 10 | 10 | 5 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 65 ± 1 | 10.6 ± 0.2 | -337 ± 7 |
| 10 | 10 | 7 | 100 ± 0 | 91 ± 1 / 91 ± 1 / 91 ± 1 | 9 ± 0 / 9 ± 0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 | 65 ± 1 | 10.6 ± 0.2 | -337 ± 7 |

## Post hoc: the newcomer lane (#253, after A.2)

**Everything in this section is post hoc.** The lane was proposed (owner, 2026-11-17) after A.2's 40-seed results showed reputation first starving newcomers. Its rule, rows and criterion (P.1) were committed before its own 40-seed runs; P.2 (results) was written after them. Seeds 1–40 as above, so nothing here is confirmatory either.

### P.1 The rule, the rows and the criterion, fixed before the 40-seed runs

**The lane** (`NEWCOMER_LANE`, a switch of `Params`, off by default, read only by `capacity.CapNet`; it needs `MAX_CHECKS_PER_HOUR` and `QUEUE_ORDER` "reputation"):
- **A share of each validator's capacity is the only capacity the second class may be drawn on.** The second class is D32's: submissions whose identity held no standing reputation when submitted, so newcomers' fixes **and junk from fresh identities**. Within the lane they are drawn first come first served. The rest of the capacity is the first class's (established solvers).
- **Kept per validator, as a credit:** each validator earns share × N lane checks an hour (N = `MAX_CHECKS_PER_HOUR`) and banks at most max(1, share × N); a second-class counted draw skips a validator with less than 1 credit, or at its capacity N, and takes 1 credit from each judge drawn. Every check still counts toward N (D31). k is never lowered, as in A.1.
- **The lane draws as soon as its credit allows** (anyone may call the draw), not only at the hour. A smoke run of 20 rows at seed 1 (7 validators, 5 an hour, both tables) was looked at before this section was fixed; it showed a lane drained only hourly losing part of its rate, and this rule was added for that reason.
- **Per validator, not per repository, because** D31's capacity is a validator's: the lane is a slice of the same counter, checked in the same draw. It works the same with one repository or ten and with or without a repository cap. A lane per repository would need the repository cap as its base (a share of what, without it?), and at the testnet's launch, with one repository (proof-of-fix), it is a network-wide lane anyway.
- **The other reading, not simulated:** if the second class could also use the rest of the capacity once the first class has none waiting ("the rest is reputation first" taken as A.1's order), the lane changes nothing here. A.1's reputation order already gives the second class every check the first leaves, and established solvers' fixes use under one check per validator an hour; the rows would be A.2's.

**The per-identity rate** (`LANE_PER_ID_DAY`, off by default): a second-class identity may submit at most this many fixes in any trailing 24 hours; beyond it the submission is refused before anything is checked (no fee, no claim, it doesn't count toward the rate). **Fresh identities are free on a testnet, so the rate binds only an identity that costs something.** The rows test both: junk from a fresh identity each fix, and from a pool of 10 or 50 identities (identities that cost something: a faucet's limit, or a charge; assumed, not designed). The rate is **2 a day**; an honest solver here submits about 0.1 a day.

**The rows** (all reputation first, junk on one repository, as A.2's grid; the world of A.1):
- **`lane`:** share none (A.2's reputation first, as reference), 10 %, 25 %, 50 % × capacity 5 and 10 an hour × spam 1 and 10 an hour (fresh identities) × 7 and 15 validators × Opus 5.5 and GPT-6.1 seated × ten repositories or **one (the testnet's launch)**, each with no repository cap or a cap of 7 counted checks an hour. With one repository a cap of 7 is a network-wide cap of one panel an hour. 256 rows.
- **`rate`:** the testnet's launch (one repository, no cap or 7), capacity 5, 10 junk fixes an hour attempted, shares 10 %, 25 %, 50 %, 7 and 15 validators, both seats; the spammer's identities: fresh with the rate (2 a day), a pool of 10 without the rate (D29's cap alone), a pool of 10 with it, a pool of 50 with it. 96 rows.

**Measured,** as A.1, plus: established solvers' and newcomers' median and 90th-percentile wait and their shares over 24 hours and withdrawn; submissions refused by the rate.

**The criterion, the same as A.1's:** a setting **holds** in a cell when honest fixes waiting more than 24 hours are at most 5 % (mean + 2 SE) and those withdrawn at most 1 % (mean + 2 SE), judged for all honest fixes; the newcomers' fixes apart are reported against the same thresholds. **A lane share passes** when it holds for all honest fixes in every cell of the `lane` table at one capacity: both seats, 7 and 15 validators, both spam rates, all four repository settings. **The recommendation** is the smallest share, then the smallest capacity, that passes, with whether it also holds for newcomers; if none passes, the report says so, and says which cells fail. The `rate` rows are reported beside it and don't enter the recommendation: on a testnet identities are free.

**What the arithmetic expects, written before the runs:** the lane draws at most validators × share × N / 7 panels an hour (k = 7 at 7 and 15 validators): 0.5, 1.25 and 2.5 at 7 validators and N = 5 (1, 2.5, 5 at N = 10), 15/7 of that at 15 validators. Every lane but one (15 validators, N = 10, 50 %: 10.7 an hour) is below 10 junk fixes an hour, so there the second class's backlog should grow for the whole run and the newcomers' fixes (about a fifth of all honest fixes) be withdrawn: the lane shares the junk's load, so it can't save them. With one repository and a cap of 7, the network judges one panel an hour, below 1 junk fix an hour plus the honest fixes, so no lane should hold there at either rate.

### P.2 Results (40 seeds; written after the runs)

**Headline: no lane share passes the rule fixed in P.1, at either capacity.** Junk from free identities lands in the lane, and first come first served within it means a newcomer's fix waits behind every earlier junk fix, so the lane holds only where its capacity exceeds the spam. Then it limits nothing.

- **10 junk fixes an hour: no lane holds at 7 validators,** at any share, capacity or repository setting, the single repository included. **The lane is worse than no lane:** with reputation first and no lane, newcomers' fixes had every check the established left; with the lane they have only the lane. At 7 validators, N = 5, ten repositories or one, no repository cap, all honest fixes withdrawn: **no lane 8.7 ± 0.9 % (Opus 5.5) / 11.1 ± 0.9 % (GPT-6.1); lane 10 %: 19.1 ± 0.8 / 19.4 ± 0.8; 25 %: 17.8 ± 0.9 / 18.7 ± 0.8; 50 %: 15.4 ± 1.0 / 17.0 ± 0.9.** In every lane row there, 100 % of newcomers' fixes are withdrawn and the backlog never clears.
- **At 15 validators only 50 % of N = 10 holds against 10 an hour** (lane 10.7 panels an hour, just above the spam), with ten repositories or one and no repository cap. It serves all the junk, so a validator runs 115 checks a day, the same as with no lane. Every other share fails at 15 validators (7.4–19.1 % withdrawn).
- **1 junk fix an hour: 25 % and 50 % hold** for all honest fixes and for newcomers at 7 and 15 validators, ten repositories or one, with no repository cap (newcomers' median wait 0.0–1.0 hours, p90 at most 4.4 hours). **So does no lane at all** (A.2), so the lane adds nothing there. **10 % fails at 7 validators and N = 5** (lane 0.5 panels an hour, below the spam: 8.3 ± 0.9 % / 10.7 ± 1.0 % withdrawn).
- **The testnet's launch with a repository cap of 7 fails at both rates,** with or without a lane. One repository and a cap of 7 judge one panel an hour in all. At 1 junk fix an hour, 7 validators, N = 5, newcomers' fixes wait over 24 hours 96.7 ± 2.4 % (Opus 5.5) and 96.9 ± 2.5 % (GPT-6.1), median 126 and 146 hours. All honest fixes over 24 hours: 4.6 ± 0.5 % and 6.9 ± 0.6 %, so the rule fails. At 15 validators it holds for Opus 5.5's honest fixes (4.4 ± 0.5 %) but not GPT-6.1's (6.6 ± 0.6 %), and never for newcomers. The lane changes nothing there, because the repository cap binds first. **At one repository the repository cap is a network-wide cap, and 7 is below even 1 junk fix an hour.**
- **With ten repositories and the cap of 7,** spam on one repository stays confined, and lanes of 25–50 % give exactly A.2's repository rows: 0.4 ± 0.1 % and 0.6 ± 0.1 % withdrawn, all of them the target repository's newcomers (8–9 % of their fixes). That holds for all honest fixes and fails for newcomers. 10 % is worse in three of the four capacity and validator cells (1.4–3.9 % withdrawn).
- **Established solvers never wait in any lane row:** median 0.0–0.6 hours, p90 at most 1.2 hours, 0 % over 24 hours, none withdrawn. The lane can't take their capacity, as intended.
- **What the lane does do is cap spend.** At 7 validators, N = 5, 10 junk fixes an hour, a validator runs 15, 33 or 62 checks a day at 10 %, 25 % or 50 % (**$0.30–1.81, $0.66–3.93, $1.25–7.48 a day**), against 118 ($2.36–14.18) with no lane. It does this by leaving the junk, and the newcomers with it, unjudged.

**The per-identity rate (2 a day; table `rate`, the testnet's launch, N = 5, 10 junk fixes an hour attempted):**
- **Fresh identities defeat it completely:** nothing is refused (each identity submits once), and every row equals its lane row (all shares fail; 100 % of newcomers' fixes withdrawn).
- **When identities cost something, D29's cap does most of the work, not the rate.** Under D29 a reputationless identity has $50 of room, so it holds about one junk fix in flight until that fix is rejected. **A pool of 10 identities with no rate holds for all honest fixes at every share, at 7 and 15 validators, with or without the cap of 7.** It holds for newcomers too from 25 % (7 validators; median wait 0–2 hours) and from 10 % (15 validators; 8–12 hours). The spammer gets about 540 junk fixes a quarter through at 7 validators, not 22,000.
- **The rate adds little on top:** with a pool of 10 it refuses 5–12 junk fixes a day at 7 validators (45–72 at 15), and shortens the newcomers' waits at 10 % (median 14 → 10 hours at 7 validators, 8 → 1 at 15). Pass or fail is the same.
- **A pool of 50 with the rate** holds for newcomers only with no repository cap and a large lane: 50 % at 7 validators (median 0–1 hours), 25 % and 50 % at 15 (median 0–14 hours). With the cap of 7 it fails for newcomers at every share (median 68–171 hours).
- **Its cost:** the rate refused an honest fix in some seeds (0.05–0.30 a run on average, at most 2 in one run of 13 weeks), when a reputationless solver submitted a third fix within 24 hours.

**What P.2 recommends:**
- **No lane share or capacity is recommended:** none passes. Against junk from free identities, no split of capacity saves newcomers whose fixes queue with the junk. The lane gives a lower spend (a smaller D31 capacity does that too), at the newcomers' cost.
- **A newcomer's first fix gets through under spam only if identities cost something.** Then D29's cap on open claims, already proposed, bounds the junk in flight per identity. With 10 such identities against 7 validators at 5 an hour, reputation first and a lane of 25 % held in every cell run. The per-identity rate is not needed for that. How a testnet identity is made to cost something (one per account at the faucet, a charge in test ETH backed by the faucet's limit) is not designed or simulated here.
- **At the testnet's launch, with one repository, set no repository cap** (or one at or above the network's capacity): a cap of 7 there fails even at 1 junk fix an hour. The cap of 7 stays useful once there are several repositories (A.2).
- **Spam at 1 an hour needs nothing new:** reputation first with no lane holds at 7 and 15 validators, ten repositories or one, without the repository cap.

**Assumptions (in addition to A.1's):**
- The lane's credit (share × N an hour, banked to max(1, share × N)) and its draw as soon as credit allows: **chosen**.
- The spammer's pools of 10 and 50 identities, each without reputation, cycled in turn: **assumed** stand-ins for "identities that cost something". The pool's size is the unknown that matters, and it depends on a faucet or charge rule that doesn't exist yet.
- The rate of 2 a day: **chosen** (about 20 times an honest solver's rate here). Honest solvers' identities are drawn at random from 50, so a burst of three in a day is rare but happens.
- Junk is rejected by every judge and claims at most $50 under D29: as A.1.

**What is not done:**
- **The other reading of the lane** (second class may also use the rest after the first): argued equal to A.2's rows (P.1), not run.
- **A lane per repository, and spam spread over every repository** with the lane: not run. Spread spam fills every repository's share alike (A.2), so it should behave like the ten-repository rows without a cap.
- **A charge in test ETH, or the faucet's actual limit,** as the cost of an identity: only fixed pools stand in for them.
- **Fair queuing within the lane** (round robin by identity) was not tried. With fresh identities it equals first come first served, since every junk fix is its own identity.
- **The rate rows with ten repositories, at N = 10 or at 1 junk fix an hour:** not run.
- **Confirmation:** seeds 1–40 again, and the rule was proposed after seeing A.2; nothing here is confirmatory.

### P.3 Appendix: the lane and rate tables (mean ± 2 SE over 40 seeds)
Printed by `--render` from the 40-seed results. "Spend" is checks a day × $0.02 and × $0.12. "Holds" applies P.1's criterion (mean + 2 SE) to all honest fixes and to newcomers' apart. A newcomer's wait is a lower bound when the fix was withdrawn (336 hours = 14 days).

#### Table `lane` (mean ± 2 SE over 40 seeds)

| Seat | Validators | Repos | Repo cap /h | Capacity /h | Spam /h | Spammer's identities | Rate /id /day | Lane | All > 24 h (%) | All withdrawn (%) | Established wait median / p90 (h) | Established > 24 h / withdrawn (%) | Newcomers wait median / p90 (h) | Newcomers > 24 h / withdrawn (%) | Checks / validator / day | Spend $/day | Cleared (% of seeds) | Junk refused / day | Holds: all / newcomers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 7 | 10 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | off | 5 | 1 | fresh | – | 10 % | 9.9 ± 0.9 | 8.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.2 ± 0.4 | 100.0 ± 0.0 / 83.1 ± 3.0 | 15 ± 0 | 0.31–1.85 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.0 ± 0.3 / 4.4 ± 0.7 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.1 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | off | 5 | 10 | fresh | – | none | 10.2 ± 0.9 | 8.7 ± 0.9 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 84.9 ± 2.7 | 118 ± 0 | 2.36–14.18 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 5 | 10 | fresh | – | 10 % | 19.1 ± 0.8 | 19.1 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 15 ± 0 | 0.30–1.81 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 5 | 10 | fresh | – | 25 % | 17.8 ± 0.9 | 17.8 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 33 ± 0 | 0.66–3.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 5 | 10 | fresh | – | 50 % | 15.4 ± 1.0 | 15.4 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.25–7.48 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | off | 10 | 1 | fresh | – | 10 % | 1.3 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 18.6 ± 3.7 / 38.4 ± 6.1 | 34.9 ± 8.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.25 | 12 ± 11 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.1 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | off | 10 | 10 | fresh | – | none | 0.2 ± 0.2 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 8.7 ± 1.4 / 17.5 ± 2.6 | 5.6 ± 3.2 / 0.0 ± 0.0 | 236 ± 0 | 4.72–28.32 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | off | 10 | 10 | fresh | – | 10 % | 18.3 ± 0.8 | 18.3 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 10 | 10 | fresh | – | 25 % | 15.4 ± 1.0 | 15.4 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.25–7.48 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | off | 10 | 10 | fresh | – | 50 % | 9.9 ± 0.9 | 8.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.3 ± 0.6 | 100.0 ± 0.0 / 82.6 ± 3.2 | 121 ± 0 | 2.43–14.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | 7 | 5 | 1 | fresh | – | none | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 10.2 ± 6.1 | 3.1 ± 1.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | 7 | 5 | 1 | fresh | – | 10 % | 6.1 ± 0.7 | 2.0 ± 0.6 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 242.5 ± 25.6 / 320.2 ± 12.1 | 96.5 ± 1.9 / 26.8 ± 5.9 | 16 ± 0 | 0.31–1.87 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | 7 | 5 | 1 | fresh | – | 25 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.2 ± 0.0 / 13.3 ± 6.9 | 4.5 ± 2.1 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.22 | 2 ± 5 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 5 | 1 | fresh | – | 50 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 10.2 ± 6.1 | 3.1 ± 1.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | 7 | 5 | 10 | fresh | – | none | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 151.2 ± 53.5 | 8.6 ± 2.6 / 8.6 ± 2.6 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 5 | 10 | fresh | – | 10 % | 7.2 ± 0.9 | 2.5 ± 0.7 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 262.4 ± 23.2 / 329.0 ± 10.1 | 95.1 ± 2.2 / 29.9 ± 5.3 | 16 ± 0 | 0.31–1.87 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | 7 | 5 | 10 | fresh | – | 25 % | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.2 ± 0.0 / 151.5 ± 53.4 | 8.6 ± 2.6 / 8.6 ± 2.6 | 27 ± 0 | 0.54–3.25 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 5 | 10 | fresh | – | 50 % | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 151.2 ± 53.5 | 8.6 ± 2.6 / 8.6 ± 2.6 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 10 | 1 | fresh | – | none | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 10.2 ± 6.1 | 3.1 ± 1.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | 7 | 10 | 1 | fresh | – | 10 % | 1.3 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 17.4 ± 3.3 / 37.2 ± 5.7 | 32.6 ± 7.7 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.22 | 2 ± 5 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 10 | 1 | fresh | – | 25 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 10.2 ± 6.1 | 3.1 ± 1.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | 7 | 10 | 1 | fresh | – | 50 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 10.2 ± 6.1 | 3.1 ± 1.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 10 | 7 | 10 | 10 | fresh | – | none | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 151.2 ± 53.5 | 8.6 ± 2.6 / 8.6 ± 2.6 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 10 | 10 | fresh | – | 10 % | 6.5 ± 0.8 | 1.9 ± 0.6 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 238.9 ± 25.5 / 326.4 ± 12.8 | 93.5 ± 3.3 / 24.1 ± 4.7 | 27 ± 0 | 0.54–3.26 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 10 | 7 | 10 | 10 | fresh | – | 25 % | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 151.2 ± 53.5 | 8.6 ± 2.6 / 8.6 ± 2.6 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 10 | 7 | 10 | 10 | fresh | – | 50 % | 0.4 ± 0.1 | 0.4 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 151.2 ± 53.5 | 8.6 ± 2.6 / 8.6 ± 2.6 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 1 | fresh | – | 10 % | 9.9 ± 0.9 | 8.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.2 ± 0.4 | 100.0 ± 0.0 / 83.1 ± 3.0 | 15 ± 0 | 0.31–1.85 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.0 ± 0.3 / 4.4 ± 0.7 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.1 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | – | none | 10.2 ± 0.9 | 8.7 ± 0.9 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 84.9 ± 2.7 | 118 ± 0 | 2.36–14.18 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | – | 10 % | 19.1 ± 0.8 | 19.1 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 15 ± 0 | 0.30–1.81 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | – | 25 % | 17.8 ± 0.9 | 17.8 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 33 ± 0 | 0.66–3.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | – | 50 % | 15.4 ± 1.0 | 15.4 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.25–7.48 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 10 | 1 | fresh | – | 10 % | 1.3 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 18.6 ± 3.7 / 38.4 ± 6.1 | 34.9 ± 8.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.25 | 12 ± 11 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.1 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 10 | 10 | fresh | – | none | 0.3 ± 0.2 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 8.7 ± 1.4 / 28.9 ± 14.3 | 6.2 ± 3.2 / 0.0 ± 0.0 | 236 ± 0 | 4.72–28.32 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | off | 10 | 10 | fresh | – | 10 % | 18.3 ± 0.8 | 18.3 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 10 | 10 | fresh | – | 25 % | 15.4 ± 1.0 | 15.4 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.25–7.48 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 10 | 10 | fresh | – | 50 % | 10.0 ± 0.9 | 8.4 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.3 ± 0.6 | 100.0 ± 0.0 / 82.8 ± 3.1 | 121 ± 0 | 2.43–14.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 1 | fresh | – | none | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 1 | fresh | – | 10 % | 10.7 ± 0.9 | 9.4 ± 0.9 | 0.3 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 87.3 ± 2.6 | 14 ± 0 | 0.29–1.73 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 1 | fresh | – | 25 % | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 1 | fresh | – | 50 % | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | – | none | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | – | 10 % | 19.1 ± 0.8 | 19.1 ± 0.8 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 14 ± 0 | 0.29–1.72 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | – | 25 % | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | – | 50 % | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 1 | fresh | – | none | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 1 | fresh | – | 10 % | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 1 | fresh | – | 25 % | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 1 | fresh | – | 50 % | 4.6 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 125.7 ± 20.2 / 259.5 ± 24.1 | 96.7 ± 2.4 / 5.3 ± 2.8 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 10 | fresh | – | none | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 10 | fresh | – | 10 % | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 10 | fresh | – | 25 % | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 10 | 10 | fresh | – | 50 % | 18.6 ± 0.8 | 18.6 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 5 | 1 | fresh | – | 10 % | 1.3 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 17.9 ± 3.7 / 37.8 ± 6.3 | 33.8 ± 8.8 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.57 | 12 ± 11 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 5 | 10 | fresh | – | none | 2.8 ± 0.4 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 37.9 ± 4.4 / 82.2 ± 8.3 | 72.3 ± 6.5 / 0.0 ± 0.0 | 108 ± 0 | 2.16–12.96 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | off | 5 | 10 | fresh | – | 10 % | 18.3 ± 0.9 | 18.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | off | 5 | 10 | fresh | – | 25 % | 15.4 ± 1.0 | 15.4 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 30 ± 0 | 0.61–3.65 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | off | 5 | 10 | fresh | – | 50 % | 9.3 ± 0.9 | 7.4 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 335.3 ± 1.4 / 336.0 ± 0.0 | 100.0 ± 0.0 / 77.4 ± 4.0 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 10 | 1 | fresh | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.8 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 10 | 10 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | off | 10 | 10 | fresh | – | 10 % | 16.3 ± 0.9 | 16.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.49–2.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | off | 10 | 10 | fresh | – | 25 % | 9.3 ± 0.9 | 7.4 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 335.3 ± 1.4 / 336.0 ± 0.0 | 100.0 ± 0.0 / 77.3 ± 3.9 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | off | 10 | 10 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.9 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 5 | 1 | fresh | – | none | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.0 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 5 | 1 | fresh | – | 10 % | 1.2 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 16.5 ± 3.0 / 36.9 ± 5.5 | 30.9 ± 7.6 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 2 ± 5 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 5 | 1 | fresh | – | 25 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.0 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 5 | 1 | fresh | – | 50 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.0 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 5 | 10 | fresh | – | none | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 5 | 10 | fresh | – | 10 % | 5.6 ± 0.8 | 1.4 ± 0.5 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 204.9 ± 30.2 / 304.9 ± 21.7 | 89.2 ± 4.1 / 19.6 ± 4.7 | 13 ± 0 | 0.26–1.57 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 10 | 7 | 5 | 10 | fresh | – | 25 % | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 5 | 10 | fresh | – | 50 % | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 10 | 1 | fresh | – | none | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.0 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 10 | 1 | fresh | – | 10 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.1 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 10 | 1 | fresh | – | 25 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.0 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 10 | 1 | fresh | – | 50 % | 0.1 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 7.0 ± 3.9 | 2.1 ± 1.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 10 | 7 | 10 | 10 | fresh | – | none | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 10 | 10 | fresh | – | 10 % | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 10 | 10 | fresh | – | 25 % | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 10 | 7 | 10 | 10 | fresh | – | 50 % | 0.3 ± 0.1 | 0.3 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 134.4 ± 52.7 | 8.0 ± 2.5 / 8.0 ± 2.5 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 1 | fresh | – | 10 % | 1.3 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 17.9 ± 3.7 / 37.8 ± 6.3 | 33.8 ± 8.8 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.57 | 12 ± 11 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | – | none | 2.8 ± 0.4 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 37.9 ± 4.4 / 82.2 ± 8.3 | 72.3 ± 6.5 / 0.0 ± 0.0 | 108 ± 0 | 2.16–12.96 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | – | 10 % | 18.3 ± 0.9 | 18.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | – | 25 % | 15.4 ± 1.0 | 15.4 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 30 ± 0 | 0.61–3.65 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | – | 50 % | 9.3 ± 0.9 | 7.4 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 335.3 ± 1.4 / 336.0 ± 0.0 | 100.0 ± 0.0 / 77.4 ± 4.0 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 10 | 1 | fresh | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.8 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 10 | 10 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 10 | 10 | fresh | – | 10 % | 16.3 ± 0.9 | 16.3 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.49–2.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 10 | 10 | fresh | – | 25 % | 9.3 ± 0.9 | 7.4 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 335.3 ± 1.4 / 336.0 ± 0.0 | 100.0 ± 0.0 / 77.3 ± 3.9 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 10 | 10 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.9 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 1 | fresh | – | none | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 1 | fresh | – | 10 % | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.0 ± 18.3 / 252.9 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 1 | fresh | – | 25 % | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 1 | fresh | – | 50 % | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | – | none | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | – | 10 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | – | 25 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | – | 50 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 1 | fresh | – | none | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 1 | fresh | – | 10 % | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 1 | fresh | – | 25 % | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 1 | fresh | – | 50 % | 4.4 ± 0.5 | 0.3 ± 0.2 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 121.5 ± 18.7 / 252.4 ± 24.3 | 96.8 ± 2.3 / 4.8 ± 2.8 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 10 | fresh | – | none | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 10 | fresh | – | 10 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 10 | fresh | – | 25 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 10 | 10 | fresh | – | 50 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 10 | off | 5 | 1 | fresh | – | 10 % | 12.5 ± 0.9 | 10.7 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 85.0 ± 2.8 | 15 ± 0 | 0.31–1.84 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.9 ± 0.2 / 4.1 ± 0.5 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 10 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 10 | off | 5 | 10 | fresh | – | none | 12.7 ± 0.9 | 11.1 ± 0.9 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 86.5 ± 2.3 | 118 ± 0 | 2.36–14.19 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 5 | 10 | fresh | – | 10 % | 19.4 ± 0.8 | 19.4 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 15 ± 0 | 0.30–1.81 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 5 | 10 | fresh | – | 25 % | 18.7 ± 0.8 | 18.7 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 33 ± 0 | 0.66–3.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 5 | 10 | fresh | – | 50 % | 17.0 ± 0.9 | 17.0 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.24–7.47 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 10 | off | 10 | 1 | fresh | – | 10 % | 2.6 ± 0.7 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 22.7 ± 4.7 / 44.6 ± 7.9 | 42.1 ± 9.6 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.25 | 12 ± 11 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 10 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 10 | off | 10 | 10 | fresh | – | none | 0.6 ± 0.3 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 9.9 ± 1.6 / 20.4 ± 3.0 | 8.9 ± 4.4 / 0.0 ± 0.0 | 236 ± 0 | 4.72–28.32 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | off | 10 | 10 | fresh | – | 10 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 27 ± 0 | 0.54–3.22 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 10 | 10 | fresh | – | 25 % | 17.0 ± 0.9 | 17.0 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.24–7.47 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | off | 10 | 10 | fresh | – | 50 % | 12.6 ± 0.9 | 10.8 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 84.8 ± 2.7 | 121 ± 0 | 2.42–14.55 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 1 | fresh | – | none | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 9.4 ± 4.6 | 3.8 ± 1.5 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 1 | fresh | – | 10 % | 9.1 ± 1.0 | 3.7 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 280.2 ± 21.2 / 329.4 ± 8.2 | 97.9 ± 1.5 / 35.5 ± 5.9 | 15 ± 0 | 0.31–1.86 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 1 | fresh | – | 25 % | 0.3 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.2 ± 0.0 / 12.4 ± 5.4 | 5.0 ± 1.7 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.21 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 1 | fresh | – | 50 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 9.4 ± 4.6 | 3.8 ± 1.5 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 10 | fresh | – | none | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 168.0 ± 53.8 | 9.3 ± 2.0 / 9.3 ± 2.0 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 10 | fresh | – | 10 % | 10.1 ± 0.9 | 3.9 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 286.6 ± 18.7 / 332.6 ± 7.1 | 97.5 ± 1.1 / 34.8 ± 5.4 | 15 ± 0 | 0.31–1.86 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 10 | fresh | – | 25 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.2 ± 0.0 / 168.4 ± 53.7 | 9.3 ± 2.0 / 9.3 ± 2.0 | 27 ± 0 | 0.54–3.24 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 5 | 10 | fresh | – | 50 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 168.0 ± 53.8 | 9.3 ± 2.0 / 9.3 ± 2.0 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 1 | fresh | – | none | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 9.4 ± 4.6 | 3.8 ± 1.5 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 1 | fresh | – | 10 % | 2.4 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 19.4 ± 3.6 / 46.4 ± 7.1 | 38.3 ± 7.8 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.22 | 2 ± 5 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 1 | fresh | – | 25 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 9.4 ± 4.6 | 3.8 ± 1.5 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 1 | fresh | – | 50 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 9.4 ± 4.6 | 3.8 ± 1.5 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.23 | 5 ± 7 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 10 | fresh | – | none | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 168.0 ± 53.8 | 9.3 ± 2.0 / 9.3 ± 2.0 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 10 | fresh | – | 10 % | 9.3 ± 0.9 | 3.1 ± 0.7 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 266.0 ± 23.3 / 330.8 ± 10.8 | 96.4 ± 2.3 / 29.5 ± 4.7 | 27 ± 0 | 0.54–3.26 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 10 | fresh | – | 25 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 168.0 ± 53.8 | 9.3 ± 2.0 / 9.3 ± 2.0 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 10 | 7 | 10 | 10 | fresh | – | 50 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 168.0 ± 53.8 | 9.3 ± 2.0 / 9.3 ± 2.0 | 27 ± 0 | 0.54–3.27 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 1 | fresh | – | 10 % | 12.5 ± 0.9 | 10.7 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 85.0 ± 2.8 | 15 ± 0 | 0.31–1.84 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.9 ± 0.2 / 4.1 ± 0.5 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | – | none | 12.7 ± 0.9 | 11.1 ± 0.9 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 86.5 ± 2.3 | 118 ± 0 | 2.36–14.19 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | – | 10 % | 19.4 ± 0.8 | 19.4 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 15 ± 0 | 0.30–1.81 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | – | 25 % | 18.7 ± 0.8 | 18.7 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 33 ± 0 | 0.66–3.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | – | 50 % | 17.0 ± 0.9 | 17.0 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.24–7.47 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 10 | 1 | fresh | – | 10 % | 2.6 ± 0.7 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 22.7 ± 4.7 / 44.6 ± 7.9 | 42.1 ± 9.6 / 0.0 ± 0.0 | 27 ± 0 | 0.54–3.25 | 12 ± 11 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 28 ± 0 | 0.55–3.31 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 10 | 10 | fresh | – | none | 0.6 ± 0.3 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 9.9 ± 1.6 / 24.4 ± 8.3 | 9.4 ± 4.4 / 0.0 ± 0.0 | 236 ± 0 | 4.72–28.32 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 10 | 10 | fresh | – | 10 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 27 ± 0 | 0.54–3.22 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 10 | 10 | fresh | – | 25 % | 17.0 ± 0.9 | 17.0 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 62 ± 0 | 1.24–7.47 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 10 | 10 | fresh | – | 50 % | 12.6 ± 0.9 | 10.8 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 85.0 ± 2.5 | 121 ± 0 | 2.42–14.55 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 1 | fresh | – | none | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 1 | fresh | – | 10 % | 13.3 ± 1.0 | 11.9 ± 1.0 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 88.8 ± 2.5 | 14 ± 0 | 0.29–1.72 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 1 | fresh | – | 25 % | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 1 | fresh | – | 50 % | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | – | none | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | – | 10 % | 19.3 ± 0.8 | 19.3 ± 0.8 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 14 ± 0 | 0.29–1.72 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | – | 25 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | – | 50 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 1 | fresh | – | none | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 1 | fresh | – | 10 % | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 1 | fresh | – | 25 % | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 1 | fresh | – | 50 % | 6.9 ± 0.6 | 0.6 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 145.7 ± 18.7 / 285.8 ± 17.7 | 96.9 ± 2.5 / 7.5 ± 3.5 | 23 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 10 | fresh | – | none | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 10 | fresh | – | 10 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 10 | fresh | – | 25 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 10 | 10 | fresh | – | 50 % | 19.2 ± 0.8 | 19.2 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 5 | 1 | fresh | – | 10 % | 2.4 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 21.5 ± 4.4 / 43.3 ± 7.6 | 40.7 ± 9.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.57 | 12 ± 11 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 5 | 10 | fresh | – | none | 4.6 ± 0.6 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 42.6 ± 4.8 / 92.9 ± 7.3 | 76.2 ± 5.5 / 0.0 ± 0.0 | 108 ± 0 | 2.16–12.96 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 5 | 10 | fresh | – | 10 % | 19.1 ± 0.8 | 19.1 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 5 | 10 | fresh | – | 25 % | 16.9 ± 0.9 | 16.9 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 30 ± 0 | 0.61–3.65 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 5 | 10 | fresh | – | 50 % | 11.7 ± 0.8 | 9.5 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 79.9 ± 3.0 | 63 ± 0 | 1.25–7.50 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 10 | 1 | fresh | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.7 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 10 | 10 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | off | 10 | 10 | fresh | – | 10 % | 17.7 ± 0.8 | 17.7 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.49–2.92 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 10 | 10 | fresh | – | 25 % | 11.7 ± 0.8 | 9.5 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 79.9 ± 3.0 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | off | 10 | 10 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.9 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 5 | 1 | fresh | – | none | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 5 | 1 | fresh | – | 10 % | 2.1 ± 0.5 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 19.2 ± 3.5 / 43.2 ± 5.6 | 36.4 ± 7.8 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 2 ± 5 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 5 | 1 | fresh | – | 25 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 5 | 1 | fresh | – | 50 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 5 | 10 | fresh | – | none | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 5 | 10 | fresh | – | 10 % | 8.2 ± 0.9 | 2.4 ± 0.7 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 223.6 ± 30.2 / 318.6 ± 18.8 | 91.3 ± 4.0 / 24.2 ± 4.8 | 13 ± 0 | 0.26–1.57 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 10 | 7 | 5 | 10 | fresh | – | 25 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 5 | 10 | fresh | – | 50 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 10 | 1 | fresh | – | none | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 10 | 1 | fresh | – | 10 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 10 | 1 | fresh | – | 25 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 10 | 1 | fresh | – | 50 % | 0.2 ± 0.1 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 8.5 ± 4.2 | 3.4 ± 1.4 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 5 ± 7 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 10 | 7 | 10 | 10 | fresh | – | none | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 10 | 10 | fresh | – | 10 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 10 | 10 | fresh | – | 25 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 10 | 7 | 10 | 10 | fresh | – | 50 % | 0.6 ± 0.1 | 0.6 ± 0.1 | 0.0 ± 0.0 / 0.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 159.6 ± 53.7 | 9.1 ± 2.0 / 9.1 ± 2.0 | 13 ± 0 | 0.26–1.58 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 1 | fresh | – | 10 % | 2.4 ± 0.6 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 21.5 ± 4.4 / 43.3 ± 7.6 | 40.7 ± 9.5 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.57 | 12 ± 11 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.2 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | – | none | 4.6 ± 0.6 | 0.0 ± 0.0 | 0.5 ± 0.0 / 0.9 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 42.6 ± 4.8 / 92.9 ± 7.3 | 76.2 ± 5.5 / 0.0 ± 0.0 | 108 ± 0 | 2.16–12.96 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | – | 10 % | 19.1 ± 0.8 | 19.1 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 13 ± 0 | 0.26–1.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | – | 25 % | 16.9 ± 0.9 | 16.9 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 30 ± 0 | 0.61–3.65 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | – | 50 % | 11.7 ± 0.8 | 9.5 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 79.9 ± 3.0 | 63 ± 0 | 1.25–7.50 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 10 | 1 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 10 | 1 | fresh | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.7 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 10 | 1 | fresh | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 10 | 1 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.60 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 10 | 10 | fresh | – | none | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 10 | 10 | fresh | – | 10 % | 17.7 ± 0.8 | 17.7 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 24 ± 0 | 0.49–2.92 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 10 | 10 | fresh | – | 25 % | 11.7 ± 0.8 | 9.5 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 79.9 ± 3.0 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 10 | 10 | fresh | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.9 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 115 ± 0 | 2.31–13.84 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 1 | fresh | – | none | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 1 | fresh | – | 10 % | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 141.5 ± 18.1 / 281.8 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 1 | fresh | – | 25 % | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 1 | fresh | – | 50 % | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | – | none | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | – | 10 % | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | – | 25 % | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | – | 50 % | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 1 | fresh | – | none | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 1 | fresh | – | 10 % | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 1 | fresh | – | 25 % | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 1 | fresh | – | 50 % | 6.6 ± 0.6 | 0.5 ± 0.3 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 140.7 ± 18.0 / 281.3 ± 17.5 | 96.9 ± 2.5 / 6.2 ± 3.1 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 10 | fresh | – | none | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 10 | fresh | – | 10 % | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 10 | fresh | – | 25 % | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 10 | 10 | fresh | – | 50 % | 19.1 ± 0.7 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 100.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |

#### Table `rate` (mean ± 2 SE over 40 seeds)

| Seat | Validators | Repos | Repo cap /h | Capacity /h | Spam /h | Spammer's identities | Rate /id /day | Lane | All > 24 h (%) | All withdrawn (%) | Established wait median / p90 (h) | Established > 24 h / withdrawn (%) | Newcomers wait median / p90 (h) | Newcomers > 24 h / withdrawn (%) | Checks / validator / day | Spend $/day | Cleared (% of seeds) | Junk refused / day | Holds: all / newcomers |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | 2 | 10 % | 19.1 ± 0.8 | 19.0 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 15 ± 0 | 0.30–1.81 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 10 | – | 10 % | 0.8 ± 0.2 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13.8 ± 2.5 / 25.6 ± 1.7 | 21.2 ± 6.8 / 0.0 ± 0.0 | 10 ± 0 | 0.21–1.24 | 100 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 10 | 2 | 10 % | 0.5 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10.1 ± 2.8 / 23.2 ± 1.9 | 14.6 ± 7.1 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.17 | 100 ± 0 | 5 ± 1 | yes / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 50 | 2 | 10 % | 5.1 ± 0.5 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 150.8 ± 2.1 / 162.3 ± 2.2 | 100.0 ± 0.0 / 0.0 ± 0.0 | 16 ± 0 | 0.31–1.88 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | 2 | 25 % | 17.8 ± 0.9 | 17.8 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 33 ± 0 | 0.66–3.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.7 ± 0.2 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.19 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.7 ± 0.2 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.17–1.04 | 100 ± 0 | 11 ± 1 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 50 | 2 | 25 % | 2.8 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 33.5 ± 2.5 / 44.1 ± 1.2 | 73.6 ± 5.0 / 0.0 ± 0.0 | 28 ± 1 | 0.56–3.36 | 100 ± 0 | 2 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | fresh | 2 | 50 % | 15.4 ± 1.0 | 15.3 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.3 | 62 ± 0 | 1.25–7.48 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.19 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.1 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.17–1.05 | 100 ± 0 | 12 ± 1 | yes / yes |
| Opus 5.5 | 7 | 1 | off | 5 | 10 | pool of 50 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.6 ± 0.4 / 4.8 ± 0.7 | 0.1 ± 0.2 / 0.0 ± 0.0 | 26 ± 1 | 0.52–3.11 | 100 ± 0 | 7 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | 2 | 10 % | 19.1 ± 0.8 | 19.0 ± 0.8 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 14 ± 0 | 0.29–1.72 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 10 | – | 10 % | 1.2 ± 0.3 | 0.0 ± 0.0 | 0.1 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 17.3 ± 2.6 / 28.8 ± 1.7 | 32.7 ± 7.7 / 0.0 ± 0.0 | 10 ± 0 | 0.21–1.25 | 100 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 10 % | 1.2 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 16.2 ± 3.0 / 29.8 ± 1.9 | 32.6 ± 7.6 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.20 | 100 ± 0 | 5 ± 1 | yes / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 10 % | 5.3 ± 0.5 | 0.0 ± 0.0 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 171.1 ± 3.0 / 183.2 ± 3.7 | 100.0 ± 0.0 / 0.0 ± 0.0 | 15 ± 0 | 0.29–1.74 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | 2 | 25 % | 18.6 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.6 ± 0.4 / 6.0 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.23 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.4 ± 0.1 / 2.2 ± 0.3 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.18–1.07 | 100 ± 0 | 11 ± 1 | yes / yes |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 25 % | 4.2 ± 0.4 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 70.3 ± 2.4 / 82.3 ± 1.8 | 99.0 ± 1.0 / 0.0 ± 0.0 | 23 ± 0 | 0.47–2.81 | 15 ± 11 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | fresh | 2 | 50 % | 18.6 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.6 ± 0.4 / 6.0 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.23 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.4 ± 0.1 / 2.2 ± 0.3 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.18–1.07 | 100 ± 0 | 11 ± 1 | yes / yes |
| Opus 5.5 | 7 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 50 % | 4.2 ± 0.4 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 70.3 ± 2.4 / 82.3 ± 1.8 | 99.0 ± 1.0 / 0.0 ± 0.0 | 23 ± 0 | 0.47–2.81 | 15 ± 11 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | 2 | 10 % | 18.3 ± 0.9 | 18.2 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.3 | 13 ± 0 | 0.26–1.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 10 | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 7.8 ± 0.2 / 10.2 ± 0.3 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.59 | 5 ± 7 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 10 | 2 | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.9 ± 0.2 / 2.6 ± 0.3 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.35 | 100 ± 0 | 59 ± 1 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 50 | 2 | 10 % | 4.1 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 72.0 ± 0.8 / 76.4 ± 0.8 | 100.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.27–1.59 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | 2 | 25 % | 15.4 ± 1.0 | 15.3 ± 1.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.3 | 30 ± 0 | 0.61–3.65 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.5 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 19 ± 0 | 0.39–2.33 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.5 ± 0.2 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.35 | 100 ± 0 | 70 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 50 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 14.5 ± 0.3 / 16.8 ± 0.4 | 0.1 ± 0.3 / 0.0 ± 0.0 | 31 ± 0 | 0.61–3.66 | 0 ± 0 | 3 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | fresh | 2 | 50 % | 9.3 ± 0.9 | 7.4 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 335.3 ± 1.4 / 336.0 ± 0.0 | 100.0 ± 0.0 / 77.0 ± 3.9 | 63 ± 0 | 1.25–7.51 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 20 ± 0 | 0.39–2.36 | 100 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.1 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.35 | 100 ± 0 | 72 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | off | 5 | 10 | pool of 50 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.1 ± 0.1 / 1.3 ± 0.3 | 0.1 ± 0.3 / 0.0 ± 0.0 | 44 ± 0 | 0.88–5.31 | 100 ± 0 | 47 ± 1 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | 2 | 10 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 10 | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.1 ± 0.4 / 16.6 ± 0.7 | 0.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 3.0 ± 0.2 / 6.3 ± 0.7 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.31 | 100 ± 0 | 45 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 10 % | 4.4 ± 0.4 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 90.7 ± 1.3 / 99.4 ± 1.5 | 100.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | 2 | 25 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.0 ± 0.4 / 16.3 ± 0.6 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 3.1 ± 0.2 / 6.1 ± 0.7 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.31 | 100 ± 0 | 45 ± 1 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 25 % | 4.4 ± 0.4 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 90.4 ± 1.3 / 99.3 ± 1.5 | 100.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | fresh | 2 | 50 % | 18.5 ± 0.8 | 18.5 ± 0.8 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.0 ± 0.4 / 16.3 ± 0.6 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 3.1 ± 0.2 / 6.1 ± 0.7 | 0.1 ± 0.3 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.31 | 100 ± 0 | 45 ± 1 | yes / yes |
| Opus 5.5 | 15 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 50 % | 4.4 ± 0.4 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 90.4 ± 1.3 / 99.3 ± 1.5 | 100.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | 2 | 10 % | 19.4 ± 0.8 | 19.3 ± 0.7 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 15 ± 0 | 0.30–1.81 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 10 | – | 10 % | 1.0 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.0 ± 2.6 / 24.4 ± 1.7 | 18.5 ± 6.4 / 0.0 ± 0.0 | 11 ± 0 | 0.21–1.27 | 100 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 10 | 2 | 10 % | 0.7 ± 0.3 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 8.6 ± 2.8 / 21.9 ± 2.2 | 12.4 ± 5.8 / 0.0 ± 0.0 | 10 ± 0 | 0.19–1.15 | 100 ± 0 | 5 ± 1 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 50 | 2 | 10 % | 7.2 ± 0.5 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 150.2 ± 2.0 / 162.9 ± 1.9 | 100.0 ± 0.0 / 0.0 ± 0.0 | 16 ± 0 | 0.31–1.87 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | 2 | 25 % | 18.7 ± 0.8 | 18.6 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 33 ± 0 | 0.66–3.93 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.6 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.19 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.5 ± 0.1 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.17–1.03 | 100 ± 0 | 10 ± 1 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 50 | 2 | 25 % | 3.7 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 30.4 ± 2.2 / 43.1 ± 1.3 | 63.4 ± 4.8 / 0.0 ± 0.0 | 28 ± 1 | 0.57–3.40 | 100 ± 0 | 2 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | fresh | 2 | 50 % | 17.0 ± 0.9 | 16.9 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 62 ± 0 | 1.24–7.47 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.19 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.17–1.05 | 100 ± 0 | 12 ± 1 | yes / yes |
| GPT-6.1 | 7 | 1 | off | 5 | 10 | pool of 50 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.3 ± 0.2 / 4.1 ± 0.8 | 0.1 ± 0.2 / 0.0 ± 0.0 | 26 ± 1 | 0.52–3.14 | 100 ± 0 | 7 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | 2 | 10 % | 19.3 ± 0.8 | 19.3 ± 0.7 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 14 ± 0 | 0.29–1.72 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 10 | – | 10 % | 1.6 ± 0.4 | 0.0 ± 0.0 | 0.1 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 14.2 ± 2.5 / 28.2 ± 1.9 | 26.6 ± 6.6 / 0.0 ± 0.0 | 11 ± 0 | 0.21–1.26 | 100 ± 0 | 0 ± 0 | yes / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 10 % | 1.6 ± 0.4 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13.9 ± 3.1 / 28.4 ± 2.4 | 27.8 ± 6.9 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.21 | 100 ± 0 | 5 ± 1 | yes / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 10 % | 7.4 ± 0.5 | 0.0 ± 0.0 | 0.3 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 169.8 ± 3.1 / 184.1 ± 3.7 | 100.0 ± 0.0 / 0.0 ± 0.0 | 14 ± 0 | 0.29–1.74 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | 2 | 25 % | 19.2 ± 0.8 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.2 ± 0.4 / 5.4 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.22 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.3 ± 0.1 / 2.2 ± 0.3 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.18–1.07 | 100 ± 0 | 10 ± 1 | yes / yes |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 25 % | 6.2 ± 0.5 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 67.6 ± 2.3 / 81.4 ± 1.6 | 98.2 ± 1.4 / 0.0 ± 0.0 | 23 ± 0 | 0.47–2.82 | 20 ± 13 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | fresh | 2 | 50 % | 19.2 ± 0.8 | 19.1 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 24 ± 0 | 0.47–2.82 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 1.2 ± 0.4 / 5.4 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 10 ± 0 | 0.20–1.22 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 1.2 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.3 ± 0.1 / 2.2 ± 0.3 | 0.1 ± 0.2 / 0.0 ± 0.0 | 9 ± 0 | 0.18–1.07 | 100 ± 0 | 10 ± 1 | yes / yes |
| GPT-6.1 | 7 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 50 % | 6.2 ± 0.5 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 67.6 ± 2.3 / 81.4 ± 1.6 | 98.2 ± 1.4 / 0.0 ± 0.0 | 23 ± 0 | 0.47–2.82 | 20 ± 13 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | 2 | 10 % | 19.1 ± 0.8 | 19.0 ± 0.7 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 13 ± 0 | 0.26–1.56 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 10 | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 7.6 ± 0.2 / 10.2 ± 0.3 | 0.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.59 | 2 ± 5 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 10 | 2 | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.9 ± 0.1 / 2.4 ± 0.2 | 0.1 ± 0.2 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.35 | 100 ± 0 | 60 ± 1 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 50 | 2 | 10 % | 6.1 ± 0.5 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 72.2 ± 0.6 / 77.4 ± 0.7 | 100.0 ± 0.0 / 0.0 ± 0.0 | 13 ± 0 | 0.26–1.59 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | 2 | 25 % | 16.9 ± 0.9 | 16.8 ± 0.9 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 30 ± 0 | 0.61–3.65 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.4 ± 0.1 | 0.0 ± 0.0 / 0.0 ± 0.0 | 19 ± 0 | 0.39–2.33 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.5 ± 0.1 | 0.1 ± 0.2 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.35 | 100 ± 0 | 70 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 50 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 14.4 ± 0.2 / 16.7 ± 0.3 | 0.2 ± 0.3 / 0.0 ± 0.0 | 30 ± 0 | 0.61–3.66 | 0 ± 0 | 3 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | fresh | 2 | 50 % | 11.7 ± 0.8 | 9.4 ± 0.8 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 79.5 ± 3.0 | 63 ± 0 | 1.25–7.50 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 20 ± 0 | 0.39–2.36 | 100 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.1 ± 0.2 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.35 | 100 ± 0 | 72 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | off | 5 | 10 | pool of 50 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 0.0 ± 0.0 / 1.3 ± 0.2 | 0.1 ± 0.2 / 0.0 ± 0.0 | 44 ± 0 | 0.88–5.31 | 100 ± 0 | 46 ± 1 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | 2 | 10 % | 19.1 ± 0.7 | 19.0 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 10 | – | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.0 ± 0.3 / 16.0 ± 0.4 | 0.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 10 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 3.1 ± 0.2 / 5.6 ± 0.4 | 0.1 ± 0.2 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.31 | 100 ± 0 | 45 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 10 % | 6.3 ± 0.5 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 91.1 ± 1.0 / 100.6 ± 1.7 | 100.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | 2 | 25 % | 19.1 ± 0.7 | 19.0 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 10 | – | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.1 ± 0.3 / 16.0 ± 0.5 | 0.2 ± 0.4 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 25 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 3.0 ± 0.2 / 5.6 ± 0.3 | 0.1 ± 0.2 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.31 | 100 ± 0 | 45 ± 1 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 25 % | 6.3 ± 0.5 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 90.8 ± 1.1 / 101.1 ± 1.4 | 100.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | fresh | 2 | 50 % | 19.1 ± 0.7 | 19.0 ± 0.7 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 336.0 ± 0.0 / 336.0 ± 0.0 | 100.0 ± 0.0 / 99.6 ± 0.2 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 10 | – | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 12.1 ± 0.3 / 16.0 ± 0.5 | 0.2 ± 0.4 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 10 | 2 | 50 % | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.1 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 3.0 ± 0.2 / 5.6 ± 0.3 | 0.1 ± 0.2 / 0.0 ± 0.0 | 11 ± 0 | 0.22–1.31 | 100 ± 0 | 45 ± 1 | yes / yes |
| GPT-6.1 | 15 | 1 | 7 | 5 | 10 | pool of 50 | 2 | 50 % | 6.3 ± 0.5 | 0.0 ± 0.0 | 0.6 ± 0.0 / 1.0 ± 0.0 | 0.0 ± 0.0 / 0.0 ± 0.0 | 90.8 ± 1.1 / 101.1 ± 1.4 | 100.0 ± 0.0 / 0.0 ± 0.0 | 11 ± 0 | 0.23–1.36 | 0 ± 0 | 0 ± 0 | **no** / **no** |

