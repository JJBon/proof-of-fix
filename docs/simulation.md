# The simulation's history

How the mechanism got here, and how to reproduce each earlier run: the legacy pool, the bounty market, checking by AI oracles and the token emission. For what's current, see the [README](../README.md); v3's open validators are in [`reports/open-validators-v3.1.md`](../reports/open-validators-v3.1.md) and [ADR 0004](adr/0004-open-validators.md).

proof-of-fix began as a simulation of incentive mechanisms. The original design (the legacy pool):
People who contribute stake on their pull requests. A pull request ships in a beta build with its payment held in escrow. During a challenge window, staked validators can prove a regression with objective evidence: a test that passes before the change, fails after it and bisects to it. If nobody does, the contributor is paid and the stake returned. Every release pays contributors, validators, the upstream author's escrowed share, infrastructure and the owner.

### Upstream

The PoC target is [storytold/gridcraft](https://github.com/storytold/gridcraft), an open-source spreadsheet in Rust (MIT OR Apache-2.0), starting with its formula core. This project is independent and not endorsed by its authors. Anything taken from upstream keeps its license, `NOTICE` and attribution. Fixes go back upstream. The author's share is held until a maintainer claims it themselves.

### Running the simulation

Python 3.9 or later, standard library only. From the repository root.

**The bounty market is the default** (owner's decision, 2026-10-24); see "The bounty market" below. The commands in this section run the **legacy pool** (`LEGACY` in `pof/params.py`): a fund per release split by lines changed. It was the placeholder of runs v1–v5, and it's kept to compare with and to reproduce them.

```sh
python3 -m pof.sim run --scenario spam --seed 1                 # one run's report (JSON)
python3 -m pof.sim run --scenario collusion --seed 1 --share 0.4
python3 -m pof.sim run --scenario owner --seed 1 --self-interested
python3 -m pof.sim run --scenario replay --seed 1 --mechanism-off # GridCraft's contribution stream only
python3 -m pof.sim run --scenario sponsorship --seed 1          # sponsored newcomers and a sponsorship abuser
python3 -m pof.sim accept --seeds 20 --summary                   # the acceptance check: passed + failures
python3 -m pof.sim summary --seeds 100 --sweep-seeds 20 > reports/acceptance-v5.json
bash scripts/check.sh                                            # OpenSpec validation + all tests
```

Scenarios: `honest`, `spam` (spammers, a splitter, a padder, a pledge stacker, an index gamer), `griefing`, `collusion` (`--share`), `owner` (`--self-interested`), `replay` (`--mechanism-off`), `risk` (`--multiplier`), `sponsorship`.

**Reading a report.** Amounts are credits.
- `returns`: each actor type's mean net gain, also per action and per unit staked.
- `group_returns`: a cohort's total (a collusion ring; an abuser and its sponsored fake accounts).
- `contributions` and `challenges`: outcome counts.
- `escaped_regressions`: defective contributions accepted and never clawed back.
- `releases`: each release's split.
- `author_escrow`: the upstream author's unclaimed share.
- `owner_payout`: everything the owner earned.
- `pr_returns`: what each kind of author earns per contribution, defective or sound.
- `pledges`: stakes partly backed by unpaid rewards (proof-of-fix#19), with the amounts pledged and lost.
- `turning_actors`, `contributors_pool_end`, `stake_index_end`: the stacker's and the index gamer's stakes before and after they turn; capped rewards left in the pool; the stake index (proof-of-fix#23).
- `panels`: approvals, decline limits, appeals and refused split changes.
- `conserved`: the ledger check.

`accept` lists every failed criterion with its scenario and seed. Defective work is judged with standard errors (attackers must lose money significantly; groups under 50 defective contributions are inconclusive), and splitting per accepted line. The latest run and what it means are in [`reports/acceptance-v5.md`](../reports/acceptance-v5.md) (robust verdicts on 100 seeds, funding that follows use, #27). It also corrects the earlier reports' splitting verdicts. The earlier runs are [`reports/acceptance-v4.md`](../reports/acceptance-v4.md) (the indexed stake and the reward cap, #23), [`reports/acceptance-v3.md`](../reports/acceptance-v3.md) (pledged stakes, #19), [`reports/acceptance-v2.md`](../reports/acceptance-v2.md) (the #10 rules) and [`reports/acceptance-defaults.md`](../reports/acceptance-defaults.md) (the first defaults).

### The bounty market (proof-of-fix#15)

`reward_source = "market"` (the default in `pof/params.py`) pays by bounty instead of the legacy pool:
- pledges, or a small treasury budget, fund bounties;
- **the race** (`award_mode = "race"`, the default since #60; the owner: "the first valid PR wins"):
  - anyone opens a bounty by paying an AI registration check (worthiness, acceptance criteria, an effort estimate), refunded when it's solved; the check refuses an issue similar to one whose bounty is open (#56);
  - a bounty has no target: it opens at once and anyone funds it while it's open, so the market sets its value (#56);
  - small issues are bundled;
  - the price is a share of the funds, opening at half and rising daily until the first attempt locks the share; later pledges still raise it (#56);
  - starting an attempt costs a small fee, and arriving after the bounty is won costs the evaluation fee (#64);
  - anyone submits, paying its own checks, and the first submission through the project's constitution (quality gates) and the AI juries wins;
  - a failed fix can't be resubmitted, but its author may appeal once to the second jury; a fix wrongly flagged as someone else's can be appealed to a jury of 3 providers (#64);
- payment comes on release through the same enforcement layer.

The sealed second-price auction (bid first, build after, #30–#55) stays as `award_mode = "auction"` (`--award-mode auction`), to compare with and to reproduce the runs before #60.

```sh
python3 -m pof.sim market run --scenario market_spam --seed 1    # one market run's report
python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20 > reports/acceptance-modes-v5.json   # the award modes compared
python3 -m pof.sim market split --seeds 40 > reports/split-v2.json   # the reporter's and the solver's split
python3 -m pof.sim market tokens --seeds 40 > reports/tokens-v4.json   # the token emission at each token price (#58)
python3 -m pof.costs   # running costs per check, paid fix and ADR: the tables of reports/costs-v1.md (#82 B2)
python3 -m pof.sim.oraclenet fees --seeds 100    # #85 check gas against flat fees, the table raised, the operator's break-even (reports/self-healing-v1.md)
python3 -m pof.sim.oraclenet bonds --seeds 100   # #85 seat bonds: every slashable fault against its honest twin
python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 --award-mode auction > reports/acceptance-checking-v6.json
```

**Discoverers and funders** (proof-of-fix#34):
- whoever reports an issue stakes on it, and earns 15 % of what the bounty pays out when its fix is paid; the solver gets 85 % (#56, [`reports/split-v1.md`](../reports/split-v1.md));
- half the treasury budget matches pledges quadratically;
- a bounty nobody can solve closes after 4 empty rounds and refunds by input.

**Reputation** (proof-of-fix#37): every account earns a non-transferable score per role from outcomes on the ledger. Trust from it does three things:
- weights matching;
- ranks treasury proposals;
- lowers a proven solver's bond.

Scores can be recomputed from the `reputation` events (`pof/reputation.py`).

**Against collusion and mispriced risk** (proof-of-fix#40):
- no price is above a reserve, 75 % of the bounty's price cap, so a lone bidder or a ring can't take the whole cap;
- an account earns at most 1 reputation point per role per release;
- in the simulation, solvers price risk from their own record.

**Checking by AI oracles** (proof-of-fix#43):
- **CI:** attested runners (MCP test runners in TEEs, two per delivery, from different operators and hardware vendors) run the public and hidden tests.
- **Judging:** AI consensus. Three evaluators must all accept; a split goes to a second AI jury of seven, which accepts with five. No person decides a delivery.
- **Scoring:** evaluators are scored on the truth (Brier), on planted cases and revealed fates.
- **Oracle fees, paid by the contributor** (proof-of-fix#49): every bid posts a check deposit worth one attempt's checks; the assigned solver's checks are paid from it, and the bounty pays none.
- **After a failure:** the attempt is published and a fresh round opens, capped at the failed price. A "not solved" challenge catches incomplete fixes.
- **Reputable models only** (proof-of-fix#47): each provider's top generally available model, from at least three providers, above an accuracy bar. Every verdict carries a proof of its model (TEE attestation or zkTLS). Juries are seated from the leaderboard, top to bottom, and verdict fees follow each evaluator's accuracy tier.

Scenarios: `market`, `market_bluff`, `market_noshow`, `market_spam`, `market_ring`, `market_flood`, `market_grief`, `market_owner`, `market_farm`, `market_self`, `market_rep`, and the checking attacks `check_lazy`, `check_herd`, `check_copy`, `check_craft`, `check_plant`, `check_sock`, `check_half`, `check_split` and `check_cheat`, and the award-mode attacks `mode_pad`, `mode_variant`, `mode_inflate` and `mode_fake` (#60, #64). Returns are net of each actor's effort.

The token emission (#58, simulated tokens only) is in [`reports/tokens-v4.md`](../reports/tokens-v4.md): 0-coin bounties now close after their clawback period, as on-chain, and a ring fails only when it gains at others' cost; **every criterion passes at token prices 0.01 and 0.05**. Before it, [`reports/tokens-v3.md`](../reports/tokens-v3.md): with a 1 % founder's share, a reporter's share forfeited above 3x the merge estimate, and rings judged by what they cost others, **every criterion passes at token prices 0.01 and 0.05**. Before it, [`reports/tokens-v2.md`](../reports/tokens-v2.md) (rings measured: they cost no one), and [`reports/tokens-v1.md`](../reports/tokens-v1.md): tokens are worth having from a token price of about 0.05 coin, where the market fixes 48 % more bounties at 10 % less per fix; at each swept price one earlier criterion fails, each named and explained there. Without tokens, the market is unchanged.

The latest run is [`reports/acceptance-modes-v5.md`](../reports/acceptance-modes-v5.md) (#56, the contract review: the price's share is locked, not its amount; locking on the first submission was measured and dropped). Before it, [`reports/acceptance-modes-v4.md`](../reports/acceptance-modes-v4.md) (#56: the market funds bounties with no target, and reporters get 15 %): **the race passes every criterion**, fixes 11 % more bounties, and reporters earn +27 a run instead of +1.5. Before that, [`reports/acceptance-modes-v3.md`](../reports/acceptance-modes-v3.md) (#64: nothing is free; fake attempts don't pay, and falsely flagged fixes win on appeal), and before that, [`reports/acceptance-modes-v2.md`](../reports/acceptance-modes-v2.md): **the race passes every criterion**, and compared with the auction it fixes 26 % more bounties, in 13 days instead of 21, at 97 % quality. Funders pay about twice as much per fix (116 against 60), and about half of solvers' effort is spent on attempts that weren't first. Before it, [`reports/acceptance-checking-v6.md`](../reports/acceptance-checking-v6.md) (the auction): **every criterion passes at every hunting elasticity**. With top models from the leaderboard, AI consensus wrongly rejects 11 % of good fixes (25 % in v5), and honest solvers earn +20. Results still rest on the assumed model accuracy until the real-data measurement. The earlier runs:
- [`checking v5`](../reports/acceptance-checking-v5.md) (the contributor pays its checks) and [`v4`](../reports/acceptance-checking-v4.md) (the bounty paid them);
- the market runs before it: [`market v4`](../reports/acceptance-market-v4.md) (passes at every hunting elasticity), [`v3`](../reports/acceptance-market-v3.md), [`v2`](../reports/acceptance-market-v2.md) and [`v1`](../reports/acceptance-market-v1.md).
