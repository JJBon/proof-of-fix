# Design

## Context
- The market simulation (`pof/market.py`, `pof/sim/market_world.py`) runs the race with no target, one open bounty per issue, a 15/85 reporter/solver coin split and a locked share (#56 design D12-D14, on branch `proof-of-fix-56`). This change builds on it.
- A bounty closes paid in `Market._finish`, after its last instalment and window.
- An issue's true value to users is `Issue.value`. The registration check already estimates effort (`Issue.estimate`, lognormal error `estimate_error`, doubled by an inflater).
- Releases fall every 7 days, and a period here is one release.
- Coin moves on the ledger (`pof/ledger.py`), which must stay conserved.

## Goals / Non-Goals

**Goals:**
- Measure what a token on top of coin does to the race: fixes, prices, funders' cost, earnings, 0-coin bounties.
- Measure the owner's alignment and concentration with the founder's share (rule 3).
- Measure what an AI weight error is worth.

**Non-Goals:**
- A token price model: the price is an assumption, swept.
- Any on-chain token.
- A holders' vote.
- Per-account minting caps.

## Decisions

### D1. Tokens are kept apart from the coin ledger
- **Decision:** a `TokenBook` (`pof/tokens.py`) holds token balances and a mint log, outside the coin ledger.
- **Why:** coin conservation stays as it is. Tokens have their own invariant: total minted equals the sum of what each period minted, never above its emission.
- **Alternative:** a second currency in `Ledger`. Rejected: it would touch every conservation check for no gain.

### D2. The emission
Named values, the emission off by default:

| Parameter | Value | Rationale |
|---|---|---|
| `token_emission_per_period` | 0 (off); 10,000 when on | The unit is arbitrary: the swept price sets its worth (D5). |
| `token_emission_decay_bps` | 100 a period | It halves in about 69 weeks (1.3 years). It barely moves an 8-week run, but it's published and tested. |
| `token_reporter_bps` | 1,500 | The reporter's coin share (#56 D13): one split for both. |
| `founder_share_bps` | **0** | **No founder's share: a fair launch (owner, 2026-11-03).** The owner earns only by work (solving, reporting, validating) and by holding what they earn, like anyone. Earlier: 1 % (2026-10-29). Swept 0 / 100 in `reports/tokens-v1`, and the market held at both. |
| `founder_periods` | 208 | Unused while `founder_share_bps` is 0. Kept so the mechanism and its cap stay tested. |
| `founder_genesis` | 0 | No genesis (owner, 2026-10-29, after `reports/tokens-v1`). Compared at 2 periods' emission as a figure. |

- **Minting:** each period, every bounty that closed paid in it is recorded with its weight. At the next release, the period's emission, less the founder's share, is minted to them by weight. The founder's share is minted to the owner only if something closed.
- **Rounding:** each mint rounds down, and the period's remainder goes to the largest weight, so the period mints exactly its emission.

### D3. The AI weight
- **At registration:** the check estimates importance as `value × exp(N(0, weight_error))`, with `weight_error = estimate_error` (0.3, the effort estimate's measured spread, #60).
- **At merge:** an independent estimate of the same form; the smaller one counts.
- **The importance inflater:** its registrations are biased ×2. The merge estimate is independent and unbiased with probability `weight_check_catch_bps` (9,000: the jury models' measured accuracy, #47), and otherwise repeats the bias.
- **Why the minimum:** a single overestimate can't raise the weight.
- **Alternative:** the mean of the two. Rejected: half of any bias would survive it.
- **Amended (owner, 2026-10-29, after `reports/tokens-v1`): inflation forfeits the reporter's share.** The minimum corrects the tokens minted, but not the attraction: solvers choose bounties by the registered weight, before any merge estimate exists, so an inflated issue was fixed sooner and its reporter's coin share paid more often (+32 ± 13 at price 0.01, the same at every catch rate). Now, if the registered weight is above `weight_inflation_pct` (300 %) of the merge estimate, the bounty's reporters forfeit their share: the finder's fee returns to the funders with the leftover, their tokens go to the solver, and they lose reporter points (as for junk). Their stake and registration fee still return: the issue was real. The owner chose 300 % (2026-10-29, after `reports/tokens-v2`): under 1 % of honest reporters' bounties forfeit by the two estimates' own error (each about 30 %), against 5-6 % at 200 %, which removed the inflater's gain at every price but cost honest reporters 4-8 % of their income. 150 % and 200 % stay swept.
- **Rings (owner, 2026-10-29, after `reports/tokens-v2`):** a ring's gain came from the effort its members stopped wasting on each other, not from others: outsiders earned more and funders paid the same. The ring criterion is now that a ring doesn't lower outsiders' earnings or raise funders' cost per fix; its gain is still reported.
- **Rings, amended (owner, 2026-10-30, after `reports/tokens-v4`):** a ring fails only when it both gains significantly and significantly costs outsiders or funders: an attack that pays. A ring of 6 at price 0.01 raised funders' cost by +5.9 ± 2.8 per fix on 100 seeds while gaining nothing itself (+19 ± 48), so it has no reason to form; it now passes, and its gain and both costs stay in the report (`judge_ring`).
- **The owner's supply share in a thin launch (owner, 2026-10-30):** 19.8 % at price 0.2 in `reports/tokens-v4`, under the 20 % cap; accepted as is.

### D4. Bounties of 0 coin, and the treasury
- **When the emission is on:**
  - an issue nobody pledges for opens at once as a bounty of 0 coin (anyone can register it, #56 D12);
  - the treasury funds open bounties by topping them up, instead of opening bounties of its own, so there's still one open bounty per issue.
- **When the emission is off:** nothing changes (modes v5 reproduces).
- **The stake on a 0-coin bounty (found in implementation):** it's 0, as in the contract's race (#56 D9): there's no coin for it to back. With the default stake of 40 % of the price cap, a 0-coin bounty could never take a submission, so every attempt on one was wasted. A fix that's slashed or clawed back mints nothing, so the AI checks stay the gatekeeper.
- **Junk:** the treasury still spots junk at its measured rate before topping a bounty up; a confirmed flag refunds the bounty and forfeits the stake, as before.
- **When a 0-coin bounty closes paid (owner, 2026-10-30, after #56's contract):** after its 4 instalment releases, its clawback period, as on-chain, not when its fix's window ends. Its tokens are minted then, about 4 weeks later than in `reports/tokens-v1` to `v3`; `reports/tokens-v4` measures the change.

### D5. Solvers price tokens
- **The decision:** a solver adds a bounty's expected tokens, valued at the run's token price `token_price` (credits per token), to its share of the coin price.
- **Expected tokens:** `rate × weight × (1 − reporter share)`, the weight being the registration's estimate.
- **The published rate (amended in implementation):** the tokens minted to bounties per unit of their weight, pooled over the last 4 minting periods. Before the first mint, it's the emission divided by a period's worth of the weight registered so far.
  - **Why not the last period's rate:** one seed's first minting period had a single close, so its rate was 115 tokens per credit of weight, against 5 to 12 in the periods after. Solvers then expected 17,647 tokens from a bounty that minted 1,917, and they rushed it.
  - **Why not the open bounties' weight before the first mint:** few bounties are open at launch, so it overpromised too. Honest solvers lost 135 credits each at a token price of 0.2.
- **Earnings:** a kind's earnings are its net of effort, plus its tokens at `token_price`.
- **The price sweep:** `token_price` is swept so that a week's emission is worth 0, 0.2×, 1× and 4× the coin paid to solvers in a week of the run without tokens. That's 0, 0.01, 0.05 and 0.2 credits a token at 10,000 tokens a week (about 500 credits of coin a week).

### D6. Scenarios
- **`token_market`:** `market` with the emission on, at each swept price.
- **`token_self`:** a coder that registers its own issues (honest weights), doesn't fund them, and races for them. Its twin is the same accounts solving others' bounties.
- **`token_inflate`:** the importance inflater (D3), against its honest twin.
- **`token_launch`:** 3 solvers, one of them the owner as a self-funding coder. Run with the founder's share, the genesis, and both.
- **`token_owner`:** `market_owner` with the founder's share, honest and self-interested.

### D7. Criteria
- **Every earlier market criterion** must hold with the emission on, at each swept price, or be named in the report.
- **Rule 3:** the owner's coin and tokens together, at each price, aren't significantly higher when it defects.
- **Concentration:** the owner's share of the supply, founder's share plus its own mints, stays below `owner_supply_cap_bps` (2,000) in `token_market` and `token_owner`. `token_launch` reports it over the periods.
- **Figures, not criteria:** tokens against weight per kind, the inflater's extra tokens per unit of true weight, the 0-coin bounties fixed, and the self-funding coder's earnings per unit of work.
- **Not a criterion:** "token farming loses money" (owner, comment 4189).

### D8. The command and the report
- **Command:** `python3 -m pof.sim market tokens --seeds 40` runs D6 at the D5 prices and the D2 founder options.
- **Report:** `reports/tokens-v1.md` and its JSON.

## Risks / Trade-offs
- **[The token price is assumed]:** every finding is given per price, and the report states which ones hold at every price.
- **[Weights depend on the AI's accuracy]:** the inflater measures what an error is worth. The merge check is the only defence; its catch rate is an assumption, swept 7,000 / 9,000 / 9,900.
- **[Emission and fixes may not keep pace]:** with few closes in a period, each gets a large share. The launch scenario shows how concentrated that gets.
- **[It depends on #56 reaching `main`]:** the implementation waits for #56's simulation changes. Only the spec goes in now.

## Migration Plan
None: the emission is off by default, and earlier runs reproduce.

## Revision 2026-11-03: no founder's share (owner)
- **Decision:** `founder_share_bps` = 0 and `founder_genesis` = 0. There is no founder's allocation, no pre-mine and no private sale. The owner's earnings come from work (solving, reporting, validating, and paid grants for specific work) and from holding the tokens they earn, under the same rules as anyone (rule 3 is satisfied at zero).
- **Why:**
  - **Credible neutrality** for collaborators and validators.
  - **Nothing for a fork to undercut:** "the same without the founder's cut" isn't a pitch.
  - **A cleaner token story:** tokens are minted only for verified work.
  - **No large founder wallet** to trace back to a pseudonymous founder (#126).
- **Evidence:** `reports/tokens-v1` swept the founder's share at 0 and 1 %, and the token market held at both.
- **Funding instead:**
  - The DAO gathers funding for issues: its treasury tops up bounties (D4), and sponsors fund issues directly.
  - It may pay **published, capped grants for specific work**, voted and visible to all, the owner's included. A grant to the owner counts toward the owner's cap (rule 3).
  - The DAO funds only; it never controls the contracts (ADR 0003).
- **Kept:** the founder's-share mechanism and its cap stay in the code and tests at 0. A non-zero share would need a new decision, and a migration once on-chain (D15).
