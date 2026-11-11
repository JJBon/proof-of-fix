# Per-repository tokens and the self-farmer, v1 (proof-of-fix#177; 2026-11-07)

**Command:** `python3 -m pof.sim.repotokens --seeds 40 [--contract] [--weight W]` (a few seconds each). Simulation only (rule 1). The model is in `pof/sim/repotokens.py`; its docstring lists every assumption.

**The question (owner, 2026-11-07):** can each repository have its own token, minted by #58's rule scoped to it? The risk: a farmer registers a repository, files real issues, funds them from sock accounts, fixes them properly and mints its own token. Every judge rightly passes the fixes, and the coin only goes round in a circle.

**How to read it.** Prices are an input, not a prediction, so the useful number is relative. **"Farming pays once honest funders get back X in tokens"** is the farmer's break-even token price times the tokens honest projects mint per dollar they fund. Below X, farming loses money. Above it, farming pays. A high X is safe: a token would have to be paying honest funders back most of what they fund before farming paid. A low X means farming pays almost as soon as the token is worth anything.

The farmer picks its cheapest strategy per rule: fixes a week, coin per bounty, sock accounts, and whether to buy their reputation by funding other projects ($500 each). Its costs are the race's fees (the $2 AI registration check, the $0.50 attempt fee, three checks at the market's $0.21 plus $0.13 usage) and the market fee (20 % of the winner's price; 0 in the contract). Its development cost is taken as zero. The judges' value estimate (#58 D3: the smaller of two noisy estimates) is centred on `--weight`: $5 for a trivial issue, more for a manufactured bug that looks serious.

## Summary
1. **A fixed weekly emission per repository is broken.** It pays once tokens return 2-3 %. One trivial fix a week takes the whole emission. Capping it (R5) changes the scale, not the ratio.
2. **The judges' value estimate is the main defence**, which answers the owner's question about validators. Minting only up to the judged value, from coin pledged by others (R1), holds at 89 % against trivial issues (66 % with the contract's fees).
3. **It fails if a farmer can make bugs the judges value highly.** At $200 a fix with the contract's fees, R1, R2, R4 and **#58's single protocol token** all pay at 2 %. The judges can't see that nobody uses the repository. `token_self` in `reports/tokens-v3` didn't test this attacker.
4. **Reputation adds little** (R2, R4). The fees dominate the farmer's costs, and buying reputation ($500 a sock, spent on real fixes elsewhere) is small against a year of minting. The model is also generous to reputation: socks funding the farmer's own repository would earn reputation for free, and the protocol can't tell they're socks.
5. **Burning coin per token (R3) is the only rule that holds whatever the judges say,** because every token costs its floor. But it does so by making tokens something honest funders buy: at a $0.05 floor they burn about 41 % of what they fund. That makes a repository token a bought funding certificate, not a reward.
6. **All rules together hold at 56-63 % in every case,** but honest projects mint about a tenth as many tokens (0.42 per dollar against 8.30).

## Recommendation (for the owner)
- **Don't give repositories their own emission.** Every emission rule tested is either broken (R0, R5) or as safe as the judges' value estimate (R1, R2, R4), which a manufactured bug defeats.
- **If projects want their own token, make it bought, not mined:** minted only against coin burned or locked at a price (R3, with no free emission). It's then a funding certificate that tracks the project, with no farming subsidy to take.
- **Test the judges' value estimate before trusting it anywhere, #58's token included.** A local evaluation: seeded, serious-looking bugs in a repository nobody uses, against the same fix in a real, used project. If judges value them alike, the weight needs a usage signal (outside funders with reputation, dependents), and #58's `token_self` needs a manufactured-bug variant.

## Results (40 seeds, a year)

### Trivial issues (judged at about $5), the market's fees
| Rule | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Farmer's tokens a year | Its cost a year ($) | Its best strategy | Honest repos with the token on | Weeks to turn on | Honest funding burned |
|---|---|---|---|---|---|---|---|---|---|
| R0: a fixed 1,000 tokens a week per repository | **3%** | 0.0058 ± 0.0000 | 4.54 | 40,703 | 235 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R1: 10 tokens per counted dollar (outside coin, up to the AI weight) | **89%** | 0.1074 ± 0.0005 | 8.29 | 36,014 | 3,913 | 1 fixes a week, $5 each, 3 socks | 100% | 0.0 | 0.0% |
| R2: R1, outside coin weighted by reputation | **93%** | 0.1227 ± 0.0001 | 7.56 | 107,974 | 13,252 | 50 fixes a week, $5 each, 3 socks with bought reputation | 100% | 0.0 | 0.0% |
| R3: R1, burning $0.05 per token | **131%** | 0.1574 ± 0.0005 | 8.29 | 36,014 | 5,714 | 1 fixes a week, $5 each, 3 socks | 100% | 0.0 | 41.5% |
| R4: R2, on after 5 reputable funders | **113%** | 0.1552 ± 0.0002 | 7.28 | 107,974 | 16,752 | 50 fixes a week, $5 each, 10 socks with bought reputation | 100% | 4.0 | 0.0% |
| R5: R0, capped at 100 tokens a week | **3%** | 0.0577 ± 0.0000 | 0.45 | 4,070 | 235 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R2 + R3 + R4 + R5 | **62%** | 1.4753 ± 0.0056 | 0.42 | 3,838 | 5,662 | 2 fixes a week, $5 each, 10 socks with bought reputation | 100% | 4.0 | 2.1% |
| For comparison: #58's one protocol token (a shared pool) | **102%** | 0.2329 ± 0.0090 | 4.43 | 1,972 | – | its fixes in the shared pool | – | – | – |

### Serious-looking issues judged at $50, the market's fees
| Rule | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Farmer's tokens a year | Its cost a year ($) | Its best strategy | Honest repos with the token on | Weeks to turn on | Honest funding burned |
|---|---|---|---|---|---|---|---|---|---|
| R0: a fixed 1,000 tokens a week per repository | **3%** | 0.0058 ± 0.0000 | 4.54 | 40,703 | 235 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R1: 10 tokens per counted dollar (outside coin, up to the AI weight) | **27%** | 0.0321 ± 0.0001 | 8.29 | 360,136 | 11,706 | 1 fixes a week, $50 each, 3 socks | 100% | 0.0 | 0.0% |
| R2: R1, outside coin weighted by reputation | **26%** | 0.0339 ± 0.0000 | 7.56 | 1,079,739 | 36,652 | 50 fixes a week, $50 each, 3 socks with bought reputation | 100% | 0.0 | 0.0% |
| R3: R1, burning $0.05 per token | **68%** | 0.0821 ± 0.0001 | 8.29 | 360,136 | 29,712 | 1 fixes a week, $50 each, 3 socks | 100% | 0.0 | 41.5% |
| R4: R2, on after 5 reputable funders | **27%** | 0.0372 ± 0.0000 | 7.28 | 1,079,739 | 40,152 | 50 fixes a week, $50 each, 10 socks with bought reputation | 100% | 4.0 | 0.0% |
| R5: R0, capped at 100 tokens a week | **3%** | 0.0577 ± 0.0000 | 0.45 | 4,070 | 235 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R2 + R3 + R4 + R5 | **59%** | 1.3939 ± 0.0000 | 0.42 | 4,070 | 5,674 | 2 fixes a week, $5 each, 10 socks with bought reputation | 100% | 4.0 | 2.1% |
| For comparison: #58's one protocol token (a shared pool) | **32%** | 0.0720 ± 0.0027 | 4.43 | 12,087 | – | its fixes in the shared pool | – | – | – |

### Serious-looking issues judged at $200, the market's fees
| Rule | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Farmer's tokens a year | Its cost a year ($) | Its best strategy | Honest repos with the token on | Weeks to turn on | Honest funding burned |
|---|---|---|---|---|---|---|---|---|---|
| R0: a fixed 1,000 tokens a week per repository | **3%** | 0.0058 ± 0.0000 | 4.54 | 40,703 | 235 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R1: 10 tokens per counted dollar (outside coin, up to the AI weight) | **22%** | 0.0270 ± 0.0000 | 8.29 | 130,000 | 3,515 | 5 fixes a week, $50 each, 3 socks | 100% | 0.0 | 0.0% |
| R2: R1, outside coin weighted by reputation | **21%** | 0.0282 ± 0.0000 | 7.56 | 1,300,000 | 36,652 | 50 fixes a week, $50 each, 3 socks with bought reputation | 100% | 0.0 | 0.0% |
| R3: R1, burning $0.05 per token | **64%** | 0.0770 ± 0.0000 | 8.29 | 520,000 | 40,061 | 20 fixes a week, $50 each, 3 socks | 100% | 0.0 | 41.5% |
| R4: R2, on after 5 reputable funders | **22%** | 0.0309 ± 0.0000 | 7.28 | 1,300,000 | 40,152 | 50 fixes a week, $50 each, 10 socks with bought reputation | 100% | 4.0 | 0.0% |
| R5: R0, capped at 100 tokens a week | **3%** | 0.0577 ± 0.0000 | 0.45 | 4,070 | 235 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R2 + R3 + R4 + R5 | **59%** | 1.3939 ± 0.0000 | 0.42 | 4,070 | 5,674 | 2 fixes a week, $5 each, 10 socks with bought reputation | 100% | 4.0 | 2.1% |
| For comparison: #58's one protocol token (a shared pool) | **27%** | 0.0625 ± 0.0022 | 4.43 | 36,585 | – | its fixes in the shared pool | – | – | – |

### Trivial issues, the contract's fees (no market fee)
| Rule | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Farmer's tokens a year | Its cost a year ($) | Its best strategy | Honest repos with the token on | Weeks to turn on | Honest funding burned |
|---|---|---|---|---|---|---|---|---|---|
| R0: a fixed 1,000 tokens a week per repository | **2%** | 0.0045 ± 0.0000 | 4.54 | 40,703 | 183 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R1: 10 tokens per counted dollar (outside coin, up to the AI weight) | **66%** | 0.0794 ± 0.0005 | 8.29 | 31,399 | 2,535 | 1 fixes a week, $50 each, 3 socks | 100% | 0.0 | 0.0% |
| R2: R1, outside coin weighted by reputation | **71%** | 0.0941 ± 0.0001 | 7.56 | 113,141 | 10,652 | 50 fixes a week, $50 each, 3 socks with bought reputation | 100% | 0.0 | 0.0% |
| R3: R1, burning $0.05 per token | **107%** | 0.1294 ± 0.0005 | 8.29 | 31,399 | 4,105 | 1 fixes a week, $50 each, 3 socks | 100% | 0.0 | 41.5% |
| R4: R2, on after 5 reputable funders | **91%** | 0.1251 ± 0.0002 | 7.28 | 113,141 | 14,152 | 50 fixes a week, $50 each, 10 socks with bought reputation | 100% | 4.0 | 0.0% |
| R5: R0, capped at 100 tokens a week | **2%** | 0.0450 ± 0.0000 | 0.45 | 4,070 | 183 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R2 + R3 + R4 + R5 | **61%** | 1.4394 ± 0.0058 | 0.42 | 3,863 | 5,559 | 2 fixes a week, $50 each, 10 socks with bought reputation | 100% | 4.0 | 2.1% |
| For comparison: #58's one protocol token (a shared pool) | **79%** | 0.1814 ± 0.0070 | 4.43 | 1,972 | – | its fixes in the shared pool | – | – | – |

### Serious-looking issues judged at $200, the contract's fees
| Rule | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Farmer's tokens a year | Its cost a year ($) | Its best strategy | Honest repos with the token on | Weeks to turn on | Honest funding burned |
|---|---|---|---|---|---|---|---|---|---|
| R0: a fixed 1,000 tokens a week per repository | **2%** | 0.0045 ± 0.0000 | 4.54 | 40,703 | 183 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R1: 10 tokens per counted dollar (outside coin, up to the AI weight) | **2%** | 0.0020 ± 0.0000 | 8.29 | 1,255,953 | 2,535 | 1 fixes a week, $500 each, 3 socks | 100% | 0.0 | 0.0% |
| R2: R1, outside coin weighted by reputation | **2%** | 0.0024 ± 0.0000 | 7.56 | 4,525,619 | 10,652 | 50 fixes a week, $500 each, 3 socks with bought reputation | 100% | 0.0 | 0.0% |
| R3: R1, burning $0.05 per token | **43%** | 0.0520 ± 0.0000 | 8.29 | 1,255,953 | 65,333 | 1 fixes a week, $500 each, 3 socks | 100% | 0.0 | 41.5% |
| R4: R2, on after 5 reputable funders | **2%** | 0.0031 ± 0.0000 | 7.28 | 4,525,619 | 14,152 | 50 fixes a week, $500 each, 10 socks with bought reputation | 100% | 4.0 | 0.0% |
| R5: R0, capped at 100 tokens a week | **2%** | 0.0450 ± 0.0000 | 0.45 | 4,070 | 183 | 1 fixes a week, $5 each, funding itself | 100% | 0.0 | 0.0% |
| R2 + R3 + R4 + R5 | **56%** | 1.3234 ± 0.0000 | 0.42 | 4,070 | 5,387 | 1 fixes a week, $50 each, 10 socks with bought reputation | 100% | 4.0 | 2.1% |
| For comparison: #58's one protocol token (a shared pool) | **2%** | 0.0051 ± 0.0002 | 4.43 | 36,585 | – | its fixes in the shared pool | – | – | – |

## Limits
- **One farmer, best response, a year:** the break-even is the attack's best case. Honest projects' rates and funders are stylised (20 repositories, about a paid bounty a week each, 300 funders).
- **No prices are predicted.** Whether anyone would buy a farmed token is outside the model.
- **Reputation is modelled generously** (finding 4).
- **The next step, if a design is kept:** the full market simulation with repositories (#58's scenarios), and each attacker against its honest twin.
