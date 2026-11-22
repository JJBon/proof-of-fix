# Token emission, v2 (proof-of-fix#58, 2026-10-29)

**Command:** `python3 -m pof.sim market tokens --seeds 40 > reports/tokens-v2.json` (8 weeks a run, about 25 minutes). Simulation only. The baseline is [`tokens-v1`](tokens-v1.md).

**What changed since v1** (the owner's decisions on v1, 2026-10-29):
1. **The founder's share is 1 %**, not 5 %, and there's **no genesis** (design D2).
2. **Inflation forfeits the reporter's share** (D3, amended). If the registered weight is above 200 % of the merge estimate, the bounty's reporters lose:
   - the finder's fee, which returns to the funders;
   - their tokens, which go to the solver;
   - reporter points.

   Their stake and registration fee come back. The tolerance is also run at 150 % and 300 %.
3. **New measurement:** who pays for a ring's gain.

## Result

| | v1 | **v2** |
|---|---|---|
| Without tokens | ✅ every criterion | ✅ the same run |
| Price 0 | ❌ award-mode variant | ❌ the same: +105 ± 40 |
| Price 0.01 | ❌ a ring of 4 gains | ✅ **every criterion passes** |
| Price 0.05 | ❌ a ring of 6 gains | ❌ the same: +577 ± 166. It costs no one (below) |
| Price 0.2 | ❌ matching adds less | ❌ the same: +0.023 ± 0.016 |

**#58's own criteria hold at every price:**
- **Conservation** holds.
- **Tokens by weight:** reporters get 14.2-14.4 % of tokens for the same share of weight. That's below 15 % now, because forfeited reporter shares go to solvers.
- **The owner's coin gain** is 0.00.
- **The owner's supply share** is 1.0 % in `market`, `market_owner` and its variant.
- **Attackers lose:** spam loses 333 to 1,323, and every checking attack except the sock loses (the sock isn't significant).

| Token price | Bounties paid | Funders' cost per fix | Solvers' earnings | Reporters' earnings (v1) | 0-coin fixed |
|---|---|---|---|---|---|
| without | 35.5 ± 0.9 | 120 ± 3 | +62.7 | +26.1 | — |
| 0 | 37.4 ± 0.8 | 117 ± 3 | +94.3 | +29.6 (+32.2) | 0 % |
| 0.01 | 39.9 ± 1.0 | 116 ± 4 | +106.7 | +35.7 (+38.0) | 6 % |
| 0.05 | 52.9 ± 1.1 | 105 ± 3 | +151.2 | +65.6 (+68.2) | 38 % |
| 0.2 | 67.5 ± 1.0 | 91 ± 2 | +471.9 | +169.0 (+168.9) | 76 % |

## 1. The founder's share at 1 %
The owner's share of the supply after 8 weeks of a thin launch: 3 solvers, the owner one of them.

| Founder option | Price 0 | 0.01 | 0.05 | 0.2 |
|---|---|---|---|---|
| None (only coding) | 5.3 % | 5.3 % | 9.5 % | 16.2 % |
| **1 % share (now the default)** | 6.3 % | 6.3 % | 10.5 % | **17.3 %** |
| 5 % share (v1) | 10.1 % | 10.0 % | 14.1 % | 20.6 % |
| Genesis (2 periods' emission) | 27.5 % | 27.0 % | 29.8 % | 34.1 % |

At 1 % the owner stays under the 20 % cap at every price, so the v1 breach is gone. The share adds about 1 point; the rest is the owner's own coding.

## 2. Inflation forfeits the reporter's share
The inflater against its honest twin. The merge check catches the inflation 90 % of the time; the tolerance changes by row.

| Tolerance | Inflaters' bounties forfeited | Honest reporters' bounties forfeited | Inflater's gain, price 0 | 0.01 | 0.05 | 0.2 |
|---|---|---|---|---|---|---|
| none (v1) | — | — | 0 | **+32 ± 13** | −100 ± 109 | −130 ± 143 |
| 150 % | 65-81 % | **18-19 %** | −26 ± 5 | −13 ± 12 | −114 ± 63 | −289 ± 170 |
| **200 % (default)** | 42-54 % | **5-6 %** | **−17 ± 3** | **0 ± 12** | −109 ± 63 | −246 ± 175 |
| 300 % | 14-17 % | **0.4-0.8 %** | −4 ± 2 | +17 ± 11 | −60 ± 59 | −141 ± 174 |

- **At 200 % the inflater's gain is gone at every price:** it loses at price 0 and gains nothing at 0.01.
- **The cost:** the two AI estimates have their own error (about 30 % each), so 5-6 % of honest reporters' paid bounties fall outside 200 % and lose the share. In the market, honest reporters earn 2.3-2.6 less a run at prices 0-0.05 (4-8 %). At 0.2 it doesn't show.
- **The trade-off:**
  - 300 % almost never hits honest reporters (under 1 %), but the inflater's gain at 0.01 comes back in part (+17 ± 11, not significant).
  - 150 % hits one honest reporter's bounty in five.
- Both numbers rest on the assumed 30 % estimate error. A more accurate weight estimate makes 200 % fairer; the real-data measurement will tell.

## 3. Who pays for a ring
Each ring is run against the same accounts racing each other. These are the changes the ring causes (40 seeds, paired):

| Price, ring size | Ring's gain | Outsiders' earnings | Funders' cost per fix | Bounties paid | Days to fix |
|---|---|---|---|---|---|
| 0.05, 6 (the failure) | **+577 ± 166** | **+69 ± 26** | +2.8 ± 3.4 | −2.6 ± 1.9 | **−1.0 ± 0.3** |
| 0.01, 4 (v1's failure) | +86 ± 68 | +2 ± 8 | −0.3 ± 4.0 | −0.5 ± 1.0 | −0.1 ± 0.2 |
| 0.2, 4 | +464 ± 510 | +20 ± 75 | +0.9 ± 3.3 | +0.9 ± 1.5 | 0.0 ± 0.5 |
| 0, 3 | −37 ± 39 | +1 ± 6 | +8.1 ± 3.7 | +0.1 ± 0.8 | +0.4 ± 0.2 |

**A ring is a team, not an attack:**
- Its members stop racing each other, so they waste less effort.
- With fewer rivals on each bounty, outsiders earn more, not less: +69 at the failing point.
- Funders pay the same, and fixes come a day sooner.
- In 16 comparisons (4 sizes × 4 prices), outsiders never lose significantly. Funders pay more once, narrowly: a ring of 3 at price 0, +8 ± 3.7, with no gain to the ring.

## The other failures (unchanged from v1)
- **Price 0, the award-mode variant (+105 ± 40):** its second account never wins a bounty. The gap looks like twin runs diverging (v1: +52 ± 21 over 100 seeds, a narrow fail). The contract replay (#56 task 2.6) reruns it on paired runs.
- **Price 0.2, matching adds less:** tokens already pay solvers what matching would add (v1).

## For the owner
1. **Rings:** the "no ring gains" criterion assumes a ring's gain comes from others, and these runs show it doesn't. My recommendation is to change it to "a ring doesn't lower outsiders' earnings or raise funders' cost". With that change, price 0.05 passes every criterion.
2. **Tolerance:** keep 200 %. It removes the inflater's gain, at the cost of about 6 % of honest reporters' bounties. Use 300 % instead if wrongly penalized honest reporters matter more than a small, unproven inflater gain at low token prices.
