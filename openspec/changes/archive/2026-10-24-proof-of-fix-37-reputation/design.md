# Design

## Context

The market (`pof/market.py`) records its outcomes as ledger events or entries:
- `delivered`, `delivery_failed`, slashes, clawbacks and a bounty being paid;
- issue stakes `rewarded` or `forfeited`;
- pledges with their pledgers.

Matching weighs every pledger equally. The AI treasury in the simulation ranks candidates by value. Bonds are 40 % of the cap for everyone.

Market v2's narrow spots:
- farming −27 ± 13;
- crowd-out failing at 50 % detection (64 %);
- full bonds for proven solvers.

## Goals / Non-Goals

**Goals:**
- Trust that's earned only by outcomes, can't be bought or moved, and is recomputable.
- Used where equal weighting is exploitable: matching and the treasury. Used where proven honesty can save capital: bonds.

**Non-Goals:**
- Tokens.
- Decay over time.
- Identity or proof of personhood.
- A reserve price.
- The AI jury.

## Decisions

### D1. Scores and points (`pof/reputation.py`)
`Reputation` keeps a score per (account, role) and records every change as a ledger event, `reputation`, with the account, role, points and the outcome's reference. The market calls it at each outcome:

| Role | Outcome | Points |
|---|---|---|
| solver | its contribution fully paid (bounty paid) | +1 |
| solver | delivery failed (gate or late) | −2 |
| solver | contribution slashed or clawed back | −3 |
| reporter | issue rewarded | +1 |
| reporter | issue forfeited as junk | −3 |
| funder | pledged at least `reputation_min_pledge` (10 credits) to a bounty that's paid | +1 |

Failures cost more than successes earn, so trust is slow to build and quick to lose.

**Recomputing:** summing the `reputation` events gives the scores. A test does exactly that.

### D2. Trust
trust(score) = min(1, `trust_floor` + max(0, score) × `trust_step`).
- **Defaults:** floor 0.25 and step 0.25, so 3 good outcomes reach full trust.
- **Rationale:** a newcomer isn't excluded, but its weight in matching is 1/16 of a proven funder's (the floor squared). Proof comes fast enough for an honest participant to matter within a few weeks.

### D3. Uses
- **Matching:** weight = (Σ t_j √p_j)² − Σ t_j² p_j, which is standard quadratic funding when every t = 1.
- **Treasury:** candidates are ranked by value × trust(reporter). It's a mechanism rule, published so anyone can check the treasury's order.
- **Bond:** stake = base stake × (1 − `bond_discount_bps` × (trust − floor) ÷ (1 − floor)). The default discount is 5,000: full trust halves the bond, and a newcomer pays the full bond. A failure costs 2–3 points, so a proven solver that fails drops toward the full bond.

### D4. Parameters (defaults)
| Parameter | Default |
|---|---|
| `points_paid` / `points_failed` / `points_slashed` | +1 / −2 / −3 |
| `points_rewarded` / `points_forfeited` | +1 / −3 |
| `reputation_min_pledge` | 10 credits |
| `trust_floor` / `trust_step` | 0.25 / 0.25 (as basis points: 2,500 / 2,500) |
| `bond_discount_bps` | 5,000 |

**Sweeps:** the trust floor (0.1, 0.25, 0.5) and the bond discount (0, 50 %, 75 %).

### D5. Simulation
- **Reputation farmer:** for 3 weeks it bids on small jobs at its break-even price and delivers honestly, which builds solver trust and a smaller bond. From then on it bids 0.5 × cost on the largest open jobs and never delivers. The test is whether its earned discount makes no-showing pay.
- **Criteria:** spec "Acceptance criteria for reputation". The crowd-out pair runs at 50 % detection. The bond comparison sets `bond_discount_bps` = 0 on the same seeds.

### D6. What the simulation changed (task 4.2)
- **Points at acceptance, not full payment.** A fix earns its solver's, reporter's and funders' points when it's accepted, at the end of its window. Full payment came about 5 weeks after delivery, so within 8 weeks almost no one reached trust, and bonds fell by 0.04 credits. A later clawback still costs the solver its −3.
- **Trust falls below the floor for negative scores,** down to nothing. A flooder whose junk was forfeited kept a newcomer's trust and still ranked junk like a new reporter's, and crowd-out at 50 % detection stayed at 65 %.
- **Match farming is measured as the farmer's net cost per own issue fixed,** split against one account. With trust-weighted matching, the fake accounts' bounties often aren't funded at all, and comparing totals counted that unspent money as a "gain".
- The spec delta is amended accordingly: "An accepted job", "A proven offender", and the farming criterion.

### D7. Market acceptance run v3 (task 4.2)
- **Every criterion passes at hunting elasticity 0 and 0.5** (100 seeds):
  - crowd-out at 50 % detection is 91 % (v2: 64 %);
  - match farming is shut down (no farm bounty funded in any seed);
  - the reputation farmer loses −232 ± 11;
  - proven solvers' bond falls −4.4 ± 0.6 per job;
  - every v2 criterion holds.
- **At elasticity 1, a 1.5× bluffer gains.** Honest break-even prices assume the discounted bond's smaller penalties, while vigorous hunting makes real penalties larger. Next step: break-even from a solver's own record.
- **Collusion:** a ring of 6 gains significantly (+72 ± 32); rings of 2–4 don't at 100 seeds. At 20 seeds a ring of 2 is flagged in most sweep rows, possibly reputation rewarding concentration (one member earns trust faster). Not conclusive. Next step: a reserve price, and possibly a per-release cap on trust earned.
- No parameter was tuned.

## Risks / Trade-offs

- **Reputation farming.** Building trust costs real work, but the discount then lowers the cost of a betrayal. The farmer measures whether that pays. If it does, the discount must be smaller, or the points for failing larger.
- **Funder trust is farmable with real money:** 10 credits on many bounties. That money really funds work, so the cost is real.
- **The floor keeps newcomers in, but their matching weight is small,** which is the point, and also a cost to honest newcomers. The sweep shows how small.
- **No decay:** old trust never expires. That's a later parameter.
