# Design

## Context

The race (#60) checks the first submission through the constitution's gates and the AI juries. Attempts in progress are published, and the first attempt locks the rising price. Both are free today, and the duplicate check has no appeal for a submitter who isn't the failed fix's author.

## Decisions

### D1. The attempt fee
- `attempt_fee` = 0.5 credits: about 0.4 % of the race's mean price in modes v2 (115). It's paid to the infrastructure account, which runs the oracles that publish attempts, and never refunded.
- **Why small:** the fee must make fake attempts cost something without taxing honest racers. Honest solvers start about 3 attempts per bounty they win, so the fee costs them about 1.5 credits per win, against a +68 net per run. It's swept (0.1, 0.5 and 2).
- **The first paid attempt locks the rising price,** as before.

### D2. Arriving late
- A submission after the bounty is won isn't checked. It pays the evaluation fee (2 credits) for the timing and similarity check, and keeps the rest of its deposit.
- **In the simulation,** honest solvers already stop when a bounty is won. Late submissions are those whose build finished on the day another fix won.

### D3. The duplicate appeal
- `duplicate_appeal_jury` = 3: one evaluator per provider, drawn from the leaderboard as for juries (#47). It's swept to 5 with the second jury's per-family rule.
- **The submitter pays** the appeal fee (`rerun_appeal_fee`, 2) plus the jury's verdict fees from its deposit.
  - The jury votes on "independent or not". In the simulation each evaluator is right with its model's accuracy, and the majority decides.
  - If the fix is found independent, it's checked like any submission: gates, then the jury.
- **False positives:** `duplicate_false_bps` (a simulation assumption, default 500) is the chance that the similarity check flags an honest independent fix as another's failed one, when the bounty has a failed fix. Swept: 0, 500 and 2,000.
- **Honest solvers appeal a false flag** (they know their fix is their own); attackers don't.

### D4. The fake attempter
- An attacker running two sock accounts that start paid attempts on every bounty it attempts, and never submit. It inflates the published count, so others see more rivals, and the earliest attempt locks the price.
- Its honest twin: the same accounts, with the socks idle.
- **Measured:**
  - its gain against the twin (fees counted);
  - other honest solvers' earnings;
  - bounties left unsolved.

### D5. Modes v3
- The same command as v2, with the new scenario.
- **Compared with v2:**
  - honest solvers' net;
  - wasted effort;
  - funders' cost;
  - bounties paid;
  - the fake attempter's gain;
  - appeals won on false duplicates.
- Sweeps of `attempt_fee` and `duplicate_false_bps`.

## Risks

- **The fee taxes honest racers too.** The sweep shows the level at which honest earnings or bounties paid start to drop.
- **The false-positive rate is assumed,** like the gates' accuracy. The real AI similarity check needs measuring, as the models did (#47).

## D6. Fake attempts: judged "don't gain" (owner, 2026-10-25)

The first modes v3 run failed one criterion as specified: the fake attempter gained +12.9 ± 15.6 against its honest twin, not the significant loss asked for. Its fees and the rivals it scares off roughly cancel out. Probes on 30 seeds:

| Variant | Fake attempter | Honest solvers |
|---|---|---|
| Fee 0.5, every attempt counted | +3 ± 24 | +74 |
| Fee 2 | −12 ± 24 | +64 |
| Fee 0.5, only solvers with earned reputation counted (`published_attempts = "trusted"`) | −27 ± 20 | **−71**: honest solvers no longer see real rivals and crowd in |

**The owner chose:** fee 0.5, every attempt counted, and the fake attempter judged like the other award-mode attacks: it mustn't gain significantly ("rigging is paying without benefit"). `published_attempts = "trusted"` stays as a parameter for comparison, not the default.
