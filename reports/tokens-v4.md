# Token emission, v4 (proof-of-fix#58 and #56, 2026-10-30)

**Command:** `python3 -m pof.sim market tokens --seeds 40 > reports/tokens-v4.json` (8 weeks a run, about 25 minutes). Simulation only. The baseline is [`tokens-v3`](tokens-v3.md).

**What changed since v3** (owner, 2026-10-30): **the simulation follows the contract for 0-coin bounties**, and **a ring fails only when it gains at others' cost** (see "Rings" below; #58 design, rings amended).
- A fix with no coin reward now runs its 4 instalment releases, its clawback period, before its bounty closes paid and mints tokens, as on-chain (#56 D15). Before, it closed when its fix's window ended.
- 0-coin fixes now earn their tokens about 4 weeks later.
- Runs without tokens have no 0-coin bounty and don't change: a 2-seed `market accept`, a 2-seed `market modes` and the legacy acceptance are byte-identical to main.

## Result

| | v3 | **v4** |
|---|---|---|
| Without tokens | ✅ every criterion | ✅ the same run |
| Price 0 | ❌ variant; a ring of 3 raising funders' cost | ❌ variant (+98 ± 36) and fake attempts (+118 ± 50). **On 100 seeds only the variant fails** (+54 ± 19); fake attempts pass (+48 ± 25). |
| Price 0.01 | ✅ | ✅ **every criterion passes.** A ring of 6 still raises funders' cost (+7.1 ± 3.5) but doesn't gain, so under the amended criterion it passes (below). |
| Price 0.05 | ✅ | ✅ **every criterion passes** |
| Price 0.2 | ❌ matching adds less | ❌ the same (+0.022 ± 0.018) |

**#58's own criteria hold at every price:**
- **Tokens:** conservation holds, and tokens go by weight.
- **The owner:** coin gain is 0, and supply share is 1.0 % in the market scenarios.
- **Attackers lose:** spam, flooding, and every checking attack but the sock (not significant) still lose.

## The market

| Price | Bounties paid (v3 → v4) | Funders' cost per fix | Solvers' earnings | Reporters' earnings | 0-coin fixed | Supply |
|---|---|---|---|---|---|---|
| 0 | 37.3 → 37.1 | 118 → 120 | +94.2 → +94.2 | +31.9 → +31.7 | 0 % → 0 % | 77.5k → 76.6k |
| 0.01 | 39.9 → 39.6 | 117 → 117 | +106 → +110 | +38.1 → +38.2 | 6 % → 7 % | 75.7k → 77.2k |
| 0.05 | **52.9 → 49.5** | 105 → 109 | +151 → +174 | +68.4 → +65.0 | **38 % → 32 %** | 85.6k → 80.9k |
| 0.2 | **67.5 → 63.5** | 91 → 93 | +463 → +500 | +177 → +161 | **77 % → 68 %** | 93.0k → 84.2k |

- **At 0.05 and above, fewer bounties are fixed:** about 3-4 a run, all of them 0-coin bounties. Every bounty still ends paid or unsolved within the run, so this isn't an end-of-run effect; more of them end unsolved.
- **The likely cause, not fully traced:** the first mint comes about 4 weeks later. Until a period has minted, the published token rate is the conservative pre-mint estimate (#58 D5), so for the first weeks solvers value a 0-coin bounty's tokens lower and fix fewer of them.
- **This is what the contract will do.** A launch has a slow first month for 0-coin bounties until tokens start flowing. Tokens still pay from about 0.05: 49.5 bounties paid against 35.5 without tokens.

## The thin launch at 1 %
The owner's share of the supply after 8 weeks:

| Price | v3 | v4 |
|---|---|---|
| 0 | 6.3 % | 6.6 % |
| 0.01 | 6.3 % | 7.2 % |
| 0.05 | 10.5 % | 11.5 % |
| 0.2 | 17.3 % | **19.8 %** |

This is still under the 20 % cap, but close at 0.2. With less minted to others early on, the owner's own coding is a larger share. **The owner accepted it as is (2026-10-30).**

## Failures explained

### Price 0: award-mode attacks
- **The variant** fails on 40 seeds (+98 ± 36) and on 100 (+54 ± 19), as in v1-v3. Its second account still wins nothing, so it looks like twin runs diverging, not a real gain. Settling it needs a paired-path rerun.
- **Fake attempts** cross the line on 40 seeds (+118 ± 50) but not on 100 (+48 ± 25). In v3 they were +105 ± 54, just inside. This is noise around the threshold.

### Rings: the criterion amended (owner, 2026-10-30)
A ring now fails "a ring doesn't cost outsiders or funders" only when it **both** gains significantly (mean − 2 SE > 0) **and** significantly lowers outsiders' earnings or raises funders' cost per paid bounty: an attack that pays. Its gain and both costs are still reported (`judge_ring` in `pof/sim/market_sim.py`). In this run no ring at any price does both. Runs without tokens still pass every criterion.

What triggered it, price 0.01 measured on 100 seeds against the same solvers racing each other:

| Ring size | Ring's gain | Outsiders | Funders' cost per fix |
|---|---|---|---|
| 2 | −17 ± 21 | −0.2 ± 2.5 | −1.2 ± 1.8 |
| 3 | −23 ± 30 | +9.7 ± 3.5 | +2.1 ± 2.2 |
| 4 | +29 ± 41 | +2.6 ± 5.1 | −0.6 ± 2.5 |
| 6 | +19 ± 48 | +2.9 ± 7.1 | **+5.9 ± 2.8** |

A ring of 6 makes funders pay about 5 % more per fix, while it doesn't gain itself and outsiders don't lose.
- **Likely mechanism:** six accounts that don't race each other start fewer attempts, so a bounty's price rises a little longer before its first attempt locks it.
- **The same effect in v3:** +5.2 ± 3.8, just under the line. Holding the 0-coin closes back changed little here.
- **Why it isn't an attack:** a ring has no reason to form for this, since it doesn't pay.

Under the amended criterion this passes: a group that costs funders about 5 % without gaining has no reason to form. If one ever gains as well, the criterion fails.

### Price 0.2: matching adds less
Unchanged: tokens already pay solvers what matching would add.
