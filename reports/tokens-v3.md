# Token emission, v3 (proof-of-fix#58, 2026-10-29)

**Command:** `python3 -m pof.sim market tokens --seeds 40 > reports/tokens-v3.json` (8 weeks a run, about 25 minutes). Simulation only. The baseline is [`tokens-v2`](tokens-v2.md).

**What changed since v2** (the owner's decisions on v2, 2026-10-29):
1. **The inflation tolerance is 300 %.** A reporter forfeits only when the registered weight is above 3× the merge estimate (design D3). It was 200 %.
2. **A ring is judged by what it costs others.** The criterion is now that no ring of 2-6 solvers significantly lowers outsiders' earnings or raises funders' cost per paid bounty (`incentive-simulation`, MODIFIED). A ring's own gain is still reported.

## Result

| | v2 | **v3** |
|---|---|---|
| Without tokens | ✅ every criterion | ✅ every criterion, the new ring criterion included |
| Price 0 | ❌ award-mode variant | ❌ the variant (+108 ± 40), and a ring of 3 raising funders' cost (+8.3 ± 3.7; not on 100 seeds, below) |
| Price 0.01 | ✅ | ✅ **every criterion passes** |
| Price 0.05 | ❌ a ring of 6 gains | ✅ **every criterion passes** |
| Price 0.2 | ❌ matching adds less | ❌ the same: +0.023 ± 0.016 |

**#58's own criteria hold at every price:**
- **Conservation** holds.
- **Tokens by weight:** reporters get 14.9-15.0 % of tokens for the same share of weight; few forfeits now.
- **The owner:** coin gain 0.00, and supply share 1.0 % in the market scenarios.
- **The thin launch:** at price 0.2 the owner holds 17.3 % of the supply, under the 20 % cap.
- **Attackers lose:** spam loses 333 to 1,319, and every checking attack except the sock loses (the sock isn't significant).

| Token price | Bounties paid | Funders' cost per fix | Solvers' earnings | Reporters' earnings | Honest reporters' bounties forfeited | 0-coin fixed |
|---|---|---|---|---|---|---|
| without | 35.5 | 120 | +62.7 | +26.1 | — | — |
| 0 | 37.3 | 118 | +94.2 | +31.9 | 0.7 % | 0 % |
| 0.01 | 39.9 | 117 | +106.2 | +38.1 | 0.6 % | 6 % |
| 0.05 | 52.9 | 105 | +151.4 | +68.4 | 0.8 % | 38 % |
| 0.2 | 67.5 | 91 | +462.8 | +176.6 | 0.8 % | 77 % |

Reporters earn what they earned in v1, without the forfeit; at 200 % (v2) they lost 4-8 %.

## The inflater at 300 %
The merge check catches the inflation 90 % of the time; the inflater is compared against its honest twin.

| Tolerance | Inflaters' bounties forfeited | Honest forfeited | Price 0 | 0.01 | 0.05 | 0.2 |
|---|---|---|---|---|---|---|
| 200 % (v2) | 42-54 % | 5-6 % | −17 ± 3 | 0 ± 12 | −109 ± 63 | −246 ± 175 |
| **300 % (now)** | 14-17 % | **under 1 %** | **−4 ± 2** | +17 ± 11 | −60 ± 59 | −141 ± 174 |

The inflater loses at price 0 and gains nothing significant at any price. Its +17 ± 11 at 0.01 is half of v1's +32 ± 13 and isn't significant, so the criteria pass.

## Rings
What each ring changes, against the same accounts racing each other (40 seeds, paired):

| Price, ring size | Ring's gain | Outsiders' earnings | Funders' cost per fix |
|---|---|---|---|
| 0.05, 6 | +568 ± 168 | **+70 ± 26** | +3.1 ± 3.4 |
| 0.01, 4 | +90 ± 66 | +2 ± 7 | −0.3 ± 4.1 |
| 0, 3 (the failure) | −40 ± 39 | +1 ± 6 | **+8.3 ± 3.7** |

**The price-0 failure, on 100 seeds** (`_ring_effects` on seeds 1-100):

| Ring size | Ring's gain | Outsiders | Funders' cost per fix |
|---|---|---|---|
| 2 | +14 ± 18 | +2.5 ± 2.8 | −2.1 ± 1.9 |
| 3 | −4 ± 26 | +2.8 ± 3.5 | **+3.4 ± 2.3** |
| 4 | −18 ± 28 | +0.4 ± 3.6 | −3.3 ± 2.4 |
| 6 | −24 ± 38 | +6.0 ± 4.3 | +1.2 ± 2.4 |

On 100 seeds no ring costs outsiders or funders, and at price 0 no ring gains. The 40-seed failure was noise, a narrow one: its mean less 2 SE was +0.9.

## The other failures (unchanged)
- **Price 0, the award-mode variant (+108 ± 40):** its second account never wins a bounty. The contract replay (#56 task 2.6) reruns it on paired runs.
- **Price 0.2, matching adds less:** tokens already pay solvers what matching would add.

## Summary for the owner
With a 1 % founder's share, no genesis, the forfeit at 300 % and the ring criterion on others' cost:
- the token emission passes every criterion at token prices 0.01 and 0.05;
- at price 0, the only failure is the variant, for the replay to settle;
- at price 0.2, matching adds less because tokens already do its job. This is a finding about matching, not a fault.
