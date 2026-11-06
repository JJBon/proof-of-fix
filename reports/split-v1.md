# The reporter's and the solver's split, v1 (proof-of-fix#56 D13, 2026-10-26)

**Command:** `python3 -m pof.sim market split --seeds 40 > reports/split-v1.json` (about 2 minutes). Every run uses the race with no target and one open bounty per issue (D12).

**The question (owner):** both the issue's creator and its solver should benefit from the market; is 50/50 the right split? The reporter's share is the finder's fee, paid from the bounty on top of the solver's price. A share s of the payout is `finder_fee_bps = s / (1 − s)` of the price.

**Decision: 15 % to the reporter, 85 % to the solver** (`finder_fee_bps = 1765`; it was 500, 4.8 %).

## In the contract's shape (no treasury, no market fee; 40 seeds, 8 weeks)

| Reporter's share | Bounties paid | Funders' cost per fix | Solvers' net | Reporters' net | Match farm's net |
|---|---|---|---|---|---|
| 4.8 % (before) | 17.8 ± 0.7 | 116 ± 4 | +35.2 ± 4.2 | **−5.5 ± 0.3** | −203 ± 19 |
| 10 % | 16.8 ± 0.6 | 113 ± 3 | +23.6 ± 3.7 | −1.0 ± 0.5 | −179 ± 17 |
| 12.5 % | 16.3 ± 0.7 | 116 ± 4 | +24.4 ± 3.0 | +1.3 ± 0.7 | −182 ± 17 |
| **15 %** | **17.1 ± 0.6** | **118 ± 4** | **+25.6 ± 3.5** | **+4.2 ± 0.6** | −199 ± 20 |
| 20 % | 15.6 ± 0.7 | 126 ± 5 | +21.4 ± 3.2 | +8.6 ± 0.9 | −179 ± 17 |
| 25 % | 14.2 ± 0.6 | 124 ± 5 | +13.0 ± 4.4 | +10.8 ± 1.2 | −189 ± 16 |
| 33 % | 13.3 ± 0.7 | 131 ± 4 | +15.9 ± 2.7 | +18.5 ± 2.0 | −169 ± 15 |
| 50 % (50/50) | **10.6 ± 0.6** | **148 ± 6** | +6.3 ± 2.3 | +26.2 ± 2.4 | −117 ± 11 |

## In the simulation's default (treasury, matching and a 20 % market fee)

| Reporter's share | Bounties paid | Funders' cost per fix | Solvers' net | Reporters' net | Match farm's net |
|---|---|---|---|---|---|
| 4.8 % (before) | 38.9 ± 1.0 | 118 ± 4 | +72.5 ± 5.5 | +3.7 ± 0.4 | −207 ± 20 |
| **15 %** | **35.5 ± 0.9** | **120 ± 3** | **+62.7 ± 4.1** | **+26.1 ± 0.9** | −197 ± 17 |
| 33 % | 32.3 ± 0.8 | 132 ± 5 | +46.5 ± 3.8 | +67.1 ± 1.9 | −115 ± 15 |
| 50 % (50/50) | 26.9 ± 0.7 | 144 ± 5 | +22.9 ± 3.4 | +96.4 ± 3.8 | **−29 ± 15** |

The flood (junk issues) loses about 494 per run at every share. Every row is in `split-v1.json`.

## What it means
- **Below about 12.5 %, reporters lose money on-chain:** each registration costs a fee, and many issues are never funded or solved. At 15 %, reporting real issues pays.
- **Fixing is the bottleneck:** most open bounties sunset unfixed while issues keep arriving. Every point moved from solvers to reporters buys fewer fixes. At 50/50, 40 % fewer bounties are fixed on-chain, each costing funders 27 % more.
- **Junk doesn't gain from a larger share,** since a reporter is paid only when a real fix is merged and survives its challenges. But **self-dealing does:** the match farm, paid as reporter on its own issues, nearly breaks even at 50/50.
- **What the simulation can't show:** more reporting because it pays more (issue arrivals are fixed). If real data shows reporting is the bottleneck, the share is a parameter, set again at a new deployment.
