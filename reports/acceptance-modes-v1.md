# Award modes compared, v1: proof-of-fix#60 (2026-10-25)

**Command:** `python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20 > reports/acceptance-modes-v1.json` (every mode's verdicts on 100 seeds, with the award-mode attacks; sweeps on 20; about 20 minutes).

**The modes:**
- **auction:** today's sealed second-price rounds (checking v6).
- **race:** the owner's choice, "the first valid PR wins":
  - the poster pays an AI registration check;
  - funders set the price;
  - anyone submits, paying its own checks;
  - the first submission through the constitution's gates wins.
- **claim:** the race with an exclusive claim, as a comparison.

## What each mode costs and buys (100 seeds, means ± standard errors)

| | auction | **race** | claim |
|---|---|---|---|
| Honest solvers' net per run | +17 ± 3 | **+154 ± 4** | +191 ± 8 |
| **Wasted effort** (honest solvers' unpaid work) | 29 % | **53 %** | 39 % |
| **Funders' cost per paid bounty** | 60 ± 2 | **177 ± 5** | 172 ± 7 |
| Mean price | 70 | 173 | 203 |
| Bounties paid / unsolved per run | 25.5 / 62.7 | **33.5 / 47.7** | 29.7 / 50.6 |
| Days to fix | 20.6 | **11.4** | 13.9 |
| Accepted fixes at the quality bar | 89 % | **97 %** | 97 % |
| Good fixes wrongly rejected | 11.3 % | 10.3 % | 11.2 % |
| Validators' net per run | +12 | +37 | +39 |

**The race delivers what the owner wanted:**
- **31 % more bounties fixed** (33.5 against 25.5 per run), in **about half the time** (11 days against 21);
- **higher quality** (97 % of accepted fixes at the bar, against 89 %);
- **no rings:** with no price to bend, no ring gains (the ring of 6 loses 173).

**What it costs:**
- **Funders pay about three times as much per fix** (177 against 60): with no bids, a fix costs whatever was pledged, and nothing is refunded. That's also why honest solvers earn about nine times more.
- **About half of solvers' effort is wasted** on attempts that weren't first. They still earn well, because prices are full pledges.

## Verdicts

| Mode | Passed | Failed criteria |
|---|---|---|
| auction | ✅ every criterion (identical to checking v6) | none |
| **race** | ❌ 4 | no-shows lose (+0.00); discoverers earn (−0.91 ± 0.20); reputation farming loses (+67 ± 15); award-mode attacks don't gain (the variant racer, +103 ± 26) |
| claim | ❌ 2 | discoverers earn (−0.58 ± 0.24); proven solvers lock less (+0.20 ± 1.03) |

**What the race's four failures mean:**
1. **No-shows** (+0.00): the attack can't happen. A no-show wins a job and never delivers, but the race assigns no jobs, so it never acts. The criterion expects a loss; there's nothing to lose. Not a weakness.
2. **Reputation farming** (+67): the attack can't happen either. The farmer builds trust on small jobs, then "wins jobs low and walks away", but in the race there's nothing to win low or walk away from. Its +67 is honest work from its first three weeks. That's below an honest solver's +154, so it doesn't gain.
3. **Discoverers lose** (−0.91 per run): reporters now pay the 2-credit registration check on every issue. That includes issues that get bundled (no finder's fee) or never funded. At a 0.50 registration fee the criterion passes (sweep).
4. **The variant racer gains +103 ± 26: a real weakness.** When its fix fails, its second account resubmits the same fix the same day. That re-rolls the gates and the juries for the price of the checks alone, since the race has no bond to lose.

## Sweeps (race and claim, 20 seeds)

| Sweep | Race |
|---|---|
| **Attempt cost** (cost per line 0.1 / 0.5 / 1 / 2) | Honest solvers +465 / +235 / +135 / +98: they still earn at double the cost. Waste stays at 51–57 % |
| Gate accuracy (0.02 / 0.05 / 0.10) | Little change: honest solvers +146 / +135 / +140 |
| Gate bar (0.6 / 0.7 / 0.8) | At 0.8: waste 65 %, honest solvers +87, 29 bounties paid. The claim fails at 0.8 (honest solvers −131) |
| **Registration fee** (0.5 / 2 / 5) | At 0.5 every criterion passes; at 2 or 5 discoverers lose |
| Top-ups (0 / 10 % a week) | No effect: bounties are rarely idle for a week |

## Decisions for the owner before the race becomes the default

1. **Resubmitting a failed fix (the variant racer).** Proposed: a submission substantially the same as a failed attempt on that bounty (an AI similarity check) is rejected without checks, from any account. Its author may appeal once, to the second jury, at its own cost. That keeps a fair second chance for a wrongly rejected fix, without the free re-roll.
2. **Discoverers.** Proposed: the poster's registration fee is **refunded with the finder's fee when the bounty is paid**. Posters pay only for issues that go nowhere, and the finder's fee of a bundle is split among the reporters of its parts. The alternative is a lower fee (0.50).
3. **What funders pay** (about 3× the auction). Options:
   - **accept it:** funders pay what they pledged, and that's their choice;
   - **a rising price:** a bounty opens at a share of its funds (for example 50 %), and the price rises daily until the first attempt starts. The price at that point is what the winner is paid, and the rest is refunded. That's still the market's price, with no bids and nothing for a ring to bend.
4. **The no-show and reputation-farming criteria** in the race: judged as "can't gain more than an honest solver", since their attacks need an assignment that the race doesn't have.

Then modes v2 re-runs, and the race becomes the default if it passes.
