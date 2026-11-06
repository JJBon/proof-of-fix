# Design

## Context

- **Price:** a lone bid is paid the price cap (the bounty's funds ÷ (1 + fees)), and otherwise the second-lowest bid. A ring that keeps all but one member out raises the price to the next outsider's bid, or the cap.
- **Reputation:** +1 per accepted fix, with no limit on how fast it accrues. Trust is the floor 0.25 + 0.25 per point, so 3 points give full trust and the half bond.
- **Break-even** in the simulation uses the default rates (the solver's defect rate, the gate's catch rate, `review_detect_bps`) and its own discounted bond.

## Goals / Non-Goals

**Goals:**
- No ring of up to 6 gains.
- Bidding your cost is best at every elasticity.
- Every v3 criterion holds.

**Non-Goals:**
- A reserve set per bounty from a cost estimate (an AI pricing step, later).
- Identity checks against rings.

## Decisions

### D1. Reserve price
- **The rule:** reserve = `reserve_bps` × price cap.
  - Reveals above the reserve are void, and lose the fee.
  - Assignment pays min(the second price, the reserve), or the reserve for a lone bid.
  - A runner-up is paid the next queued price, capped at the reserve.
- **Default 7,500:** a lone bidder takes three quarters of the cap rather than all of it. Market v3's mean price was 1.69 × cost, with the cap well above most costs, so most honest bids fit.
- **Sweep:** 5,000, 7,500, 9,000 and 10,000 (10,000 = no reserve). It reports bounties paid and closed unsolved at each.
- *Alternative:* a Myerson-optimal reserve from the cost distribution. Rejected for now: it needs an estimate of the cost distribution per issue, which is an AI pricing step.

### D2. Per-release trust cap
- **The rule:** `trust_points_per_release` = 1, per account, role and release. Points beyond it are recorded as outcomes with +0. Negative points are never capped.
- **The effect:** full trust takes at least 3 releases (about 3 weeks) for anyone, however many jobs it wins. A ring's single winner no longer reaches the half bond sooner than an honest solver with a job a week.

### D3. Break-even from a solver's record (simulation)
- **Each solver keeps its outcomes:** jobs delivered, deliveries failed, contributions slashed or clawed back.
- **Its rates:** (outcomes + k × prior) ÷ (trials + k), with k = 5 pseudo-trials and the default assumption as the prior.
- **Break-even uses those rates,** with its own (discounted) bond as before.

### D4. Criteria
- **Collusion:** v3's ring comparison; fail if any ring size has m − 2 SE > 0.
- **Bluffing:** v3's comparison, run at elasticity 0, 0.5 and 1 on the verdict seeds.
- **Every earlier market criterion is kept.**

## Risks / Trade-offs

- **A reserve that's too low** leaves expensive issues unsolved, until they close and refund. The sweep shows how many, and the default may need tuning.
- **The trust cap slows honest solvers too,** and with them the bond saving. v4 measures how much of v3's saving (−4.4) remains.
- **Record-based pricing** makes new solvers price like the default, and experienced ones from their record. Unlucky early outcomes raise a solver's prices for a while.

## Results (market v4)

- **Every criterion passes on 100 seeds at elasticity 0, 0.5 and 1** with the defaults above, so no parameter or rule was changed (`reports/acceptance-market-v4.md`).
- **The reserve stays at 75 %.**
  - Without it, the trust cap and record pricing still pass every criterion, but the ring of 6 passes by a hair (+59 ± 32). With it, the ring of 6 is +19 ± 25.
  - The cost: about 13 % fewer bounties paid, and lower solver earnings (+19 against +34).
  - 90 % contains neither the ring (+46) nor, comfortably, bluffing (+29 ± 16) (`reports/acceptance-market-v4-reserve.json`).
