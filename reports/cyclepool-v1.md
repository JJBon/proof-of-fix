# Cycle pools per repository, and inflated merit healed, v1 (proof-of-fix#184; 2026-11-08)

**Command:** `python3 -m pof.sim.cyclepool --seeds 20 [--detect 0.5]` (a few seconds). Simulation only (rule 1), for the paper. The model is `pof/sim/cyclepool.py`; its docstring lists every assumption.

**The owner's design (2026-11-08):**
- **The pool:** each repository has a pool each cycle, funded by investors who hold shares in proportion to what they brought.
- **The split:** at the cycle's end, judges split the pool's coin among the merged fixes by merit.
- **Opening issues:** an issue costs an AI check and gas, and issues can be filed at any time.
- **Defending it:** an investor who sees an overclaimed PR files an issue against its merit before the cycle closes, so people with a claim on the repository defend it alongside the AI checks.
- **Self-healing:** inflated merit should heal through the judges' scores.

**The attack:** a project's own team files 5 correct but trivial fixes each cycle (worth $5 each) and claims they're important. It picks the claim that pays it best under each defence: $15 (within #58's 3× rule), $50 or $200. Some judges may collude with it, always accepting its claims and judging everything else honestly. The pool is $2,000 a cycle, with about 10 honest fixes (median $86).

**The defences:**
- **Challenges before the split:** half of the overclaims that pass the panel are challenged, at $3 each, and the AI check upholds 90 % of real ones. An upheld challenge corrects the merit before the split, and the challenger gets 10 % of the overpayment it stopped. Honest fixes are also challenged by mistake, at a tenth of that rate.
- **Judges' scores by consensus with the final merit:** the merit as corrected by any challenge. A score more than 3× off, either way, halves a judge's score, and agreeing regains a little. Draws follow score. A judge below the floor is replaced by a newcomer of the same kind, and a colluder comes back under a new identity for a new $250 bond.
- **After the split:** audits of 10 % of paid fixes, and later reports on 10 %. The coin is already paid, so they heal the future, not the cycle.
- **A refundable $50 stake to open an issue:** forfeited when the claim is over 3× the merit awarded (#58 D3's rule).

## Summary
1. **With judges catching 80 % of overclaims and no defence,** the team takes 8 % of the pool with no colluding judges, and 20–38 % with 3–8 of 15 colluding.
2. **The stake is what makes overclaiming lose.** With all defences and up to 5 of 15 judges colluding, the team's best response is to claim within the rule ($15 for a $5 fix), and it still loses money ($−2,124 to $−465 a year). About 1 % of the pool is overpaid. Without the stake, the same defences leave the team at $6,700–8,700 a year.
3. **Challenges before the split are your defence, and they anchor the scores.** Consensus scoring alone backfires when colluders are a majority (8 of 15): the honest judges look like the outliers, colluders reach 87 % of draws, and 46 % of the pool goes to the team, worse than no defence. With challenges, consensus is measured against the corrected merit, so the colluders lose score instead (37 % of draws in the last quarter, against 53 % with no defence).
4. **Healing takes a year and isn't complete with a colluding majority.** At 8 of 15 with every defence, the team's profit falls from $2,536 in the first quarter to $1,197 in the last, but 21 % of the pool is still overpaid. Colluders come back under new identities, so the $250 bond is what limits how fast they return.
5. **Everything rests on the judges' detection rate.** At 50 %, every defence together still leaves 22–33 % of the pool overpaid, even with no colluders. #160's paid test measures this rate.
6. **What honest participants pay:** honest fixers lose $80–190 a year to mistaken challenges and forfeited stakes, under 0.2 % of the pool. Challengers come out ahead whenever there are overclaims to catch ($230–1,800 a year net), and lose about $100 a year when the team retreats to claims within the rule, because then only their mistaken challenges remain.
7. **Honest judges' scores settle near 0.4,** because each overclaim they miss is a disagreement. Score is relative, so this costs them nothing against each other, but it slows how fast colluders are told apart.

## For the paper
- **The claim that holds:** with judges who catch about 80 % of overclaims and colluders a minority, people with a claim on the repository (challenges before the split) plus a stake forfeited by a 3× rule make overclaiming lose money from the first quarter. The judges' scores remove colluders once challenges anchor them to the truth.
- **What doesn't hold:** scores alone (they backfire under a colluding majority), and any defence at 50 % detection.
- **The open number** is the judges' detection rate, which only the paid test with real data can measure.

## Results (20 seeds, a year; judges see through an overclaim 80 % of the time)

#### 0 of 15 judges colluding with the team (honest judges see through an overclaim 80% of the time)

| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 2,638 → 2,603 | 10,549 | 8.2% | 0% | 0 | 0 | 1.00 |
| judges' scores (consensus) and audits of 10 % of paid fixes | $200 | 2,787 → 2,889 | 10,739 | 8.4% | 0% | 0 | 0 | 0.47 |
| judges' scores, from audits and later reports (10 % each) | $200 | 2,722 → 2,723 | 10,639 | 8.3% | 0% | 0 | 0 | 0.43 |
| challenges before the split (half of overclaims) | $200 | 1,880 → 1,654 | 6,995 | 5.1% | 0% | 143 | 270 | 1.00 |
| challenges + scores + audits | $200 | 1,893 → 1,537 | 6,743 | 4.9% | 0% | 83 | 233 | 0.40 |
| challenges + scores + audits + a $50 refundable stake | $15 | -511 → -546 | -2,124 | 0.5% | 0% | 139 | -101 | 0.74 |

#### 3 of 15 judges colluding with the team (honest judges see through an overclaim 80% of the time)

| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 5,353 → 6,015 | 22,500 | 19.7% | 21% | 0 | 0 | 1.00 |
| judges' scores (consensus) and audits of 10 % of paid fixes | $200 | 4,062 → 3,585 | 14,802 | 13.5% | 10% | 0 | 0 | 0.44 |
| judges' scores, from audits and later reports (10 % each) | $200 | 4,164 → 3,472 | 14,535 | 13.2% | 9% | 0 | 0 | 0.42 |
| challenges before the split (half of overclaims) | $200 | 3,707 → 3,812 | 14,352 | 12.7% | 21% | 144 | 737 | 1.00 |
| challenges + scores + audits | $200 | 2,464 → 1,867 | 7,543 | 8.0% | 8% | 111 | 459 | 0.41 |
| challenges + scores + audits + a $50 refundable stake | $15 | -194 → -191 | -890 | 0.8% | 9% | 184 | -107 | 0.71 |

#### 5 of 15 judges colluding with the team (honest judges see through an overclaim 80% of the time)

| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 7,442 → 7,817 | 29,716 | 26.7% | 34% | 0 | 0 | 1.00 |
| judges' scores (consensus) and audits of 10 % of paid fixes | $200 | 6,362 → 5,392 | 23,222 | 21.4% | 20% | 0 | 0 | 0.38 |
| judges' scores, from audits and later reports (10 % each) | $200 | 5,798 → 5,701 | 20,925 | 19.9% | 21% | 0 | 0 | 0.34 |
| challenges before the split (half of overclaims) | $200 | 4,655 → 4,900 | 19,413 | 18.1% | 34% | 64 | 1,097 | 1.00 |
| challenges + scores + audits | $200 | 2,538 → 2,109 | 8,731 | 10.9% | 17% | 126 | 698 | 0.39 |
| challenges + scores + audits + a $50 refundable stake | $15 | 44 → -101 | -465 | 1.0% | 16% | 186 | -114 | 0.74 |

#### 8 of 15 judges colluding with the team (honest judges see through an overclaim 80% of the time)

| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 10,094 → 10,669 | 41,622 | 38.1% | 53% | 0 | 0 | 1.00 |
| judges' scores (consensus) and audits of 10 % of paid fixes | $200 | 11,880 → 12,595 | 49,739 | 46.0% | 87% | 0 | 0 | 0.15 |
| judges' scores, from audits and later reports (10 % each) | $200 | 11,326 → 12,370 | 48,079 | 44.3% | 76% | 0 | 0 | 0.15 |
| challenges before the split (half of overclaims) | $200 | 6,696 → 7,411 | 28,070 | 26.8% | 53% | 87 | 1,530 | 1.00 |
| challenges + scores + audits | $200 | 4,613 → 3,305 | 14,837 | 19.5% | 37% | 92 | 1,180 | 0.36 |
| challenges + scores + audits + a $50 refundable stake | $200 | 2,536 → 1,197 | 6,497 | 21.3% | 37% | 105 | 1,325 | 0.36 |

## The same, with judges seeing through an overclaim 50 % of the time (no defence, and every defence)
#### 0 of 15 judges colluding with the team (honest judges see through an overclaim 50% of the time)
| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 8,591 → 8,661 | 33,933 | 30.6% | 0% | 0 | 0 | 1.00 |
| challenges + scores + audits + a $50 refundable stake | $200 | 3,485 → 3,776 | 13,654 | 22.3% | 0% | 110 | 1,328 | 0.20 |
#### 3 of 15 judges colluding with the team (honest judges see through an overclaim 50% of the time)
| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 10,350 → 10,018 | 40,472 | 36.9% | 20% | 0 | 0 | 1.00 |
| challenges + scores + audits + a $50 refundable stake | $200 | 4,469 → 3,892 | 16,330 | 26.2% | 16% | 170 | 1,571 | 0.20 |
#### 5 of 15 judges colluding with the team (honest judges see through an overclaim 50% of the time)
| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 10,955 → 11,086 | 44,561 | 40.8% | 34% | 0 | 0 | 1.00 |
| challenges + scores + audits + a $50 refundable stake | $200 | 5,456 → 4,671 | 18,771 | 29.4% | 30% | 139 | 1,703 | 0.17 |
#### 8 of 15 judges colluding with the team (honest judges see through an overclaim 50% of the time)
| Defence | The team's best claim | Its profit, first quarter → last | Team's profit a year | Overpaid to the team (of the pool) | Colluders' share of draws, last quarter | Honest fixers' loss | Challengers' net | Honest judges' score |
|---|---|---|---|---|---|---|---|---|
| no defence | $200 | 11,736 → 12,066 | 47,327 | 43.6% | 53% | 0 | 0 | 1.00 |
| challenges + scores + audits + a $50 refundable stake | $200 | 6,088 → 5,653 | 22,172 | 33.3% | 50% | 91 | 1,817 | 0.19 |

## Limits
- **One team, five overclaims a cycle,** at a fixed claim per defence. It doesn't adapt during the year.
- **Investors challenge half of the overclaims that pass,** a fixed rate. In practice it depends on how many investors watch, and on the reward.
- **The challenge check (90 %) is an assumption,** like the judges' detection rate. A challenge is one focused question, so it is assumed to be more accurate than a panel judging a whole cycle.
- **Colluders always accept the team's claims and judge everything else honestly.** A smarter colluder that sometimes refuses would keep its score longer.
- **Prices and the shares' value aren't modelled.** Investors appear only as who pays the pool.
