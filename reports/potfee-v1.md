# A payout fee indexed to the token pot, v1 (proof-of-fix#182; 2026-11-08)

**Command:** `python3 -m pof.sim.repotokens --pot --seeds 20` (about two minutes). Simulation only (rule 1). It extends [repotokens v2](repotokens-v2.md)'s hybrid: the per-cycle merit split, each fix's share capped by outside bounty coin, against a farmer faking $200 bugs that the judges see through with probability "caught". Each cell is the share of their funding honest funders get back in tokens at the point where farming starts to pay; higher is safer.

**The owner's question (2026-11-08):** can the fee be dynamic, so that the greater the pot, the greater the penalty?

## Summary
1. **A fee by bounty size is worse than a flat fee.** Tested before this report (5 % under $50, 10 % to $150, 20 % above): 56 % at 80 % caught and 72 % at 90 %, against a flat 10 % fee's 83 % at 90 %. Honest funders paid more (13.3 % of their coin), because the farmer moved its faked importance into the cheap tier.
2. **Rising with PR volume runs the wrong way.** With a fixed emission, more volume means fewer tokens per dollar, so less reason to farm.
3. **A fee indexed to the pot's value, alone, protects far less than a flat fee.** The fee is β times the token value a dollar of bounty coin earns in the cycle, so it shrinks with the token's price, exactly where the farmer's break-even lies. At 80 % caught, β = 0.2 holds to 24 % and β = 0.3 to 33 %, against a flat 20 % fee's 86 %. At that break-even, a flat 20 % fee costs honest funders about 23 % of their token value, so at a similar cost the pot fee protects about three times less.
4. **No β makes farming impossible, not even β = 1.** The farmer's fakes are judged at the coin behind them, while honest fixes are judged below their bounty: the judges' estimates err low and usage evidence is partial. So the farmer earns about 1.3 times the token rate the fee is priced on, and it moves to trivial $5 bounties, where a caught fix is still worth its coin. (#182's expectation that faking loses once β exceeds the share missed was wrong for this reason.)
5. **Capped, it works: the token value a dollar earns, up to 20 % of the coin (β = 1, cap 20 %).** The protection is a flat 20 % fee's (86 % at 80 % caught, 95 % at 90 %), but honest funders never pay more than their tokens are worth. While tokens are worth little the fee is close to zero, and it reaches 20 % only once a dollar of bounty earns 20 cents in tokens. A flat fee charges 20 % even when the tokens are worthless, which is when a new project most needs funders.
6. **Half the token value (β = 0.5, cap 20 %) is too weak at 80 % caught** (73 %). Capped at 10 % instead, either β matches a flat 10 % fee.

## Recommendation (for the owner)
- **For the contract spec:** a payout fee of **the token value the bounty's coin earned, up to 20 % of the coin**, burned or returned to the pool and paid to no one. It follows your "bigger pot, bigger penalty" rule up to a ceiling.
- **It needs the token's price on-chain:** a time-averaged price from an exchange where the token trades. That's an outside dependency, and a farmer could try to push the price down during a cycle to lower its fee. The cap limits the damage: the fee can never exceed a flat 20 %. Before the token has a market, the fee is 0.
- **If a price feed isn't acceptable, a flat 20 %** gives the same protection, with the early cost to honest funders.
- **Either way the judges must catch about 80 % of faked importance,** which is #160's paid test, on the frozen build.

## Results (20 seeds, a year)
| Fee | 0% caught | 50% caught | 80% caught | 90% caught | Trivial fixes only | Honest funders pay, as a share of their token value |
|---|---|---|---|---|---|---|
| flat 10% | 18% | 29% | 55% | 83% | 87% | 10% of the coin |
| flat 20% | 27% | 46% | 86% | 95% | 97% | 20% of the coin |
| pot-indexed, β = 0.1 | 6% | 9% | 18% | 29% | 86% | 10% |
| pot-indexed, β = 0.2 | 7% | 11% | 24% | 41% | 95% | 20% |
| pot-indexed, β = 0.3 | 8% | 14% | 33% | 60% | 107% | 30% |
| pot-indexed, β = 0.5 | 10% | 24% | 73% | 139% | 144% | 50% |
| pot-indexed, β = 1 | 42% | 452% | 651% | 761% | 947% | 100% |
| pot-indexed, β = 1, capped at 20% of the coin | 26% | 46% | 86% | 95% | 97% | 100% of their token value, up to 20% of the coin |
| pot-indexed, β = 0.5, capped at 20% of the coin | 10% | 24% | 73% | 95% | 97% | 50% of their token value, up to 20% of the coin |
| pot-indexed, β = 1, capped at 10% of the coin | 17% | 29% | 55% | 83% | 87% | 100% of their token value, up to 10% of the coin |
| pot-indexed, β = 0.5, capped at 10% of the coin | 10% | 24% | 55% | 83% | 87% | 50% of their token value, up to 10% of the coin |

The last column for the pot-indexed rows is the fee as a share of the token value honest funders receive. For the capped rows it's that share until the cap of the coin binds.

## Limits
- **The token's price is an input,** as in v1 and v2: the break-even is the price at which farming starts to pay. Manipulating the price feed isn't modelled.
- **The fee's base is the cycle's average:** emission over all bounty coin paid out in the cycle. A contract can compute it from its own events.
- **The share caught is assumed,** as in v2: #160 measures it.
- **One farmer,** as in v1 and v2.
