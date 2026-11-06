# Token emission, v1 (proof-of-fix#58, 2026-10-29)

**Command:** `python3 -m pof.sim market tokens --seeds 40 > reports/tokens-v1.json` (8 weeks a run, about 18 minutes). Simulation only: the tokens are numbers in `pof/tokens.py`, kept apart from the coin ledger (rule 1).

**What's on** (design D1-D8 of `proof-of-fix-58-token-emission`):
- a fixed emission each period (one release), 10,000 tokens, less 1 % a period; it's minted at the next release only to the bounties that closed paid in the period, by their AI weight (the smaller of the registration and merge estimates); with no close, nothing is minted;
- 15 % of a bounty's tokens to its reporters, as with the coin;
- the founder's share: 5 % of each period's emission for 208 periods, only in periods that mint;
- an issue nobody pledged to opens a **0-coin bounty**, which pays tokens only; the treasury can top it up;
- solvers value tokens at a fixed **token price** (coin per token) and race when coin plus tokens at that price beats their effort. The sweep is 0, 0.01, 0.05 and 0.2.

## Result

| | Every earlier criterion | Failures |
|---|---|---|
| Without tokens | ✅ | — |
| Price 0 | ❌ 1 | award-mode attacks don't gain (the variant, see below) |
| Price 0.01 | ❌ 1 | no ring gains (a ring of 4) |
| Price 0.05 | ❌ 1 | no ring gains (a ring of 6) |
| Price 0.2 | ❌ 1 | matching gets more pledged issues fixed |

**#58's own criteria hold at every price, in every run:**
- **Conservation:** every token came from a mint, and each period minted its emission or nothing.
- **By weight:** reporters got 15.0 % of the tokens for 15.0 % of the weight, and solvers 85.0 % for 85.0 %.
- **The owner's coin gain** is 0.00 ± 0.00.
- **The owner's supply share** is 5.0 % (at most 5.0 %) in `market`, `market_owner` and its variant: below the 20 % cap.
- **Attackers still lose:** spam solvers lose 333 at price 0 and 1,299 at 0.2. Every checking attack except the sock loses, and the sock isn't significant at any price.

## The market at each price

| Token price | Bounties paid | Funders' cost per fix | Solvers' earnings | Reporters' earnings | Days to fix | 0-coin opened | 0-coin fixed | Supply |
|---|---|---|---|---|---|---|---|---|
| without | 35.5 ± 0.9 | 120 ± 3 | +62.7 ± 4.1 | +26.1 ± 0.9 | 12.8 ± 0.3 | — | — | — |
| 0 | 37.3 ± 0.8 | 118 ± 3 | +94.2 ± 5.2 | +32.2 ± 0.9 | 12.4 ± 0.2 | 12.3 | 0.0 (0 %) | 77,473 |
| 0.01 | 39.6 ± 1.0 | 117 ± 4 | +103.1 ± 8.8 | +38.0 ± 1.0 | 12.4 ± 0.2 | 11.0 | 0.7 (6.5 %) | 76,369 |
| 0.05 | **52.6 ± 1.1** | **108 ± 3** | +158.1 ± 18.9 | +68.2 ± 1.2 | 12.3 ± 0.3 | 12.5 | 4.3 (39 %) | 87,131 |
| 0.2 | **67.0 ± 0.9** | **90 ± 2** | +412.2 ± 46.4 | +168.9 ± 2.9 | 12.6 ± 0.3 | 10.3 | 7.0 (73 %) | 91,485 |

Earnings are coin plus tokens at the price. The treasury spends about 8,700 a run at every price.

- **Tokens start to matter at about 0.05.** From there, solvers fix 0-coin bounties for the tokens alone, and funded bounties get fixed more often. At 0.2 the market pays 89 % more bounties than without tokens (67 against 35.5), and funders pay 25 % less per fix.
- **Coin changes even at price 0**, where tokens are worth nothing: a 0-coin bounty opens when the issue is registered, and its rising price runs while it waits for the treasury. That moves 1.8 more bounties a run to paid, and +31 to solvers.

## Failures explained

### Price 0: award-mode attacks don't gain (`mode_variant`, +108 ± 40)
The variant attacker splits its work between two accounts. Its second account won no bounty in any run, so the attack did nothing an honest solver doesn't. The gap is path divergence: the twin worlds part as soon as one bounty goes differently, and with 0-coin bounties more bounties go differently. More seeds shrink it, but not quite to zero:

| Seeds | Variant's gain against honest |
|---|---|
| 1-40 (this run) | +108 ± 40 |
| 41-100 | +14 ± 20 |
| 1-100 | +52 ± 21 (mean − 2 SE = +10: still fails, narrowly) |

The same attack is −1 ± 19 without tokens, +38 ± 37 at 0.01, +39 ± 44 at 0.05 and −5 ± 196 at 0.2. I read it as noise, not a gain, but it isn't proven. The contract's replay (#56 task 2.6) should rerun it with paired paths.

### Prices 0.01 and 0.05: no ring gains
| Ring size | without | 0 | 0.01 | 0.05 | 0.2 |
|---|---|---|---|---|---|
| 2 | −12 ± 26 | +8 ± 22 | +27 ± 24 | +7 ± 63 | +391 ± 267 |
| 3 | +6 ± 27 | −40 ± 39 | −38 ± 46 | +118 ± 98 | +137 ± 347 |
| 4 | +53 ± 40 | −16 ± 45 | **+127 ± 63** | +87 ± 118 | +141 ± 449 |
| 6 | +5 ± 40 | +38 ± 57 | +43 ± 67 | **+490 ± 175** | +909 ± 505 |

A ring's members don't race each other, so they don't spend effort on attempts that lose to a ring partner. Tokens raise what each bounty is worth, so the effort the ring saves is worth more. At 0.2 the means are larger still but too noisy to pass or fail. **Open item:** whether the ring's gain comes out of outsiders' and funders' pockets (an attack) or only from the effort it saves (coordination, as a firm of solvers would). This run doesn't measure it. Next: compare outsiders' earnings and funders' cost per fix with and without the ring, at 0.05.

### Price 0.2: matching gets more pledged issues fixed (+0.024 ± 0.017)
Matching adds to pledged bounties to get more of them fixed. At 0.2, tokens already pay solvers enough to fix most pledged issues, so matching adds less: +2.4 points, against +5.1 without tokens and +6.6 to +8.0 at lower prices. Tokens substitute for matching; the matching budget could move to 0-coin bounties.

## Self-coding (`token_self`)
A solver that registers its own issues and fixes them, against a twin that races everyone's:

| Price | Tokens per effort (self / twin) | Gain against the twin |
|---|---|---|
| 0 | 37.4 / 24.9 | +28 ± 33 |
| 0.01 | 42.3 / 25.6 | −16 ± 39 |
| 0.05 | 24.1 / 11.6 | +25 ± 39 |
| 0.2 | 15.2 / 6.3 | +20 ± 180 |

It mints more tokens per unit of effort (it doesn't lose races), but the gain isn't significant at any price: it gives up the funded bounties the twin wins.

## Importance inflation (`token_inflate`)
A reporter that registers its issues at twice their importance. The merge check catches the inflation with the probability shown, otherwise the inflated weight stands:

| Catch rate | Extra tokens per unit of true weight, price 0 | 0.01 | 0.05 | 0.2 |
|---|---|---|---|---|
| 70 % | +1.58 ± 0.24 | +1.61 ± 0.51 | +1.52 ± 0.74 | +1.72 ± 3.38 |
| 90 % (default) | +0.92 ± 0.17 | +1.17 ± 0.49 | +1.04 ± 0.72 | +0.60 ± 3.28 |
| 99 % | +0.67 ± 0.13 | +0.76 ± 0.44 | +0.76 ± 0.72 | −0.10 ± 3.30 |

The twin earns 7.6-10.5 tokens per unit of true weight, so the inflater gets 9-15 % more tokens per unit of true weight at the default catch rate. Even at 99 % some extra stays (+0.67 at price 0), more than the 1 % of inflation that slips through explains; it isn't traced yet. **Its gain against the twin** is +32 ± 13 at 0.01 at *every* catch rate, so it doesn't come from the minted tokens: solvers price the bounty on the inflated registration weight and race it sooner. At 0.05 and 0.2 the gain isn't significant (−100 ± 109, −130 ± 143), and at price 0 it's zero.

## The founder's share in a thin launch (`token_launch`)
Three solvers, the owner one of them, fixing everything in the first weeks. The owner's share of the supply at the end of the run:

| Founder option | Price 0 | 0.01 | 0.05 | 0.2 |
|---|---|---|---|---|
| None (the owner only codes) | 5.4 % | 5.3 % | 9.6 % | 16.3 % |
| **5 % share (the default)** | 10.1 % | 10.1 % | 14.2 % | **20.6 %** |
| 10 % share (above rule 3's cap) | 14.8 % | 14.8 % | 18.7 % | 25.0 % |
| Genesis (2 periods' emission) | 27.5 % | 27.0 % | 29.8 % | 34.1 % |
| Genesis and 5 % share | 31.2 % | 30.6 % | 33.3 % | 37.4 % |

- The **5 % share adds about 5 points** at every price; the rest is the owner's coding, which is earned like anyone's.
- A **genesis** starts the owner at 100 % of the supply and takes all 8 weeks to fall below 30 %. It's not needed: the share already pays the owner in every period that mints.
- At 0.2 the owner who codes in a thin launch passes the 20 % cap (20.6 ± 1.1 %), even with the default share. Without the share, coding alone reaches 16 %.

## Recommendations
1. **Price:** tokens are worth it only if the market values them at about 0.05 coin or more; below that they change little.
2. **Founder:** keep the 5 % share; no genesis.
3. **Owner decision:** if the owner codes in a thin launch and tokens trade high, the owner's supply share can pass the 20 % cap. Choices: a lower cap on the owner's coding tokens, the share paused while the owner's supply is above the cap, or accept it as earned.
4. **Open:** measure whether rings take from outsiders and funders (above). The award-mode variant is rerun with paired paths in the replay (#56 task 2.6).
5. **Inflation:** keep the merge check, and publish the expected tokens on the *smaller* of the two estimates once the merge estimate exists. Pricing on the registration weight is the part an inflater exploits.
