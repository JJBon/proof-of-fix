# Proposal

Ticket: proof-of-fix#186 (the owner's decisions of 2026-11-08, in the ticket and in #177, #182 and #184; and of 2026-11-10/11, after #193's simulation, PR #194).

## Why

Five simulations chose how fixes should be paid, how funders are rewarded and how inflated importance is contained: #177 (`reports/repotokens-v2.md`), #182 (`reports/potfee-v1.md`), #184 (`reports/cyclepool-v1.md`) and #193/#195 (`reports/fundertoken-v1.md` and `-v2.md`, PR #194). None of it is in the contract yet:
- The contract charges no fee.
- The token's weights are set per bounty (#58 D3), and the token goes to solvers.
- Nothing lets the people funding a repository defend it against an overclaimed fix.
- #193 found a flaw in this change as first written: the pool was paid out in full whenever any fix merged, so one typo in a quiet cycle took all of it.

The design must be fixed before the paid judge test (#160), because scoring merit in dollars changes what judges produce. The contract code will be built from this spec next, on the devnet with test values, before #160 measures the real ones.

## What Changes

- **One general protocol token, earned by funders by merit** (replacing #58's token for solvers):
  - each cycle the network mints E = min(rate × total calibrated merit, cap), with no cap that follows burns;
  - each merged fix gets E × its merit share, capped at `TOKENS_PER_COIN` × its outside coin; what the caps cut goes to the uncapped fixes;
  - a fix's tokens go to its funders, bounty pledgers and pool shareholders, by coin. **Solvers are paid coin only.** Self-funded coin earns nothing on the funder's own fix. No owner's, founder's or validators' share (Article 11.3).
- **Allowed USD stablecoins:** bounties, pools and check fees take stablecoins from an allow-list, starting with one, changed only by ADR, never by a key. If an allowed coin is blocked or can't pay a passed fix, the tokens its funders would have earned go to the fixers by merit, with no extra emission. A freeze of the contract's own address means nothing in that coin can move, and the spec says so.
- **Three ways to fund work:**
  - per-issue bounties stay, optional, for buyers who need a specific fix;
  - each repository has a **cycle pool**, with each address's share recorded per cycle;
  - a **network index pool** spreads its coin over the repositories by merit, for non-technical investors.
  - Every funder of a pool gets the same tokens per coin, with no picking, and each pool's historical tokens per coin is published.
- **Merit in dollars at the cycle's end.** A panel of judges, drawn after the cycle closes, scores the fixes merged in it in dollars of value, calibrated by reference fixes with recorded merits: sealed then revealed scores, with the median per fix. This replaces #58 D3's per-bounty estimates as the token's weights.
- **Pay up to merit (the thin-cycle fix).** Each fix is paid min(its merit value, its pro-rata share) from its pool, after its bounty. The leftover stays with each funder by share; each funder alone rolls it over, withdraws it or moves it. Withdrawn coin earns nothing.
- **Adaptations:** (b) pay per merit dollar = clamp(pool ÷ merit, 1, 1.5) when money waits; (c) a shortfall is the first claim on the next cycle. (a), a cap that follows burns, is rejected (#194).
- **Challenges before the split.** Anyone with a claim on the repository (a pool or index share, or a bounty pledge) may file an issue against a fix's merit until the split. It's AI-checked like any issue. If it's upheld, the merit is corrected before the split, and the challenger is paid a published share of the overpayment it stopped.
- **A stake on claimed importance.** Opening an issue states its claimed importance in dollars and posts a refundable stake, forfeited to the repository's next pool when the claim is over `MERIT_TOLERANCE` (3×) of the merit awarded.
- **The payout fee, capped and indexed to the token** (**BREAKING** for the bounty-market spec's fee):
  - The fee on coin paid to a fix is the token value that coin earned, up to `FEE_CAP_BPS` (20 %) of the coin, out of the solver's pay. It's burned or returned to the pool, never paid to anyone.
  - The token's price comes from a fixed price feed, or an exchange's time-averaged price until one exists; with no market, the fee is 0.
- **Pay for compute.** Whoever causes a check pays its real cost in stablecoins (the price table plus the service fee, Article 5.11), plus a protocol margin in the token that is burned, never paid to validators. Reading public chain data isn't charged.
- **Judges' merit record.** A judge whose merit is more than `MERIT_TOLERANCE` off the final merit, as corrected by any challenge, loses standing; agreeing restores it. A validator below the floor isn't drawn, and coming back needs a new bond (#132). Scores never weight a vote.
- **Deployment parameters.** The numbers that depend on the judges' accuracy (`FEE_CAP_BPS`, `MERIT_TOLERANCE`, `TOKENS_PER_COIN`, the emission rate and cap, the clamp bounds, and the detection rate the safety argument assumes) are fixed per deployment, immutable and with no setter. The devnet uses test values; real values come from #160's measurement before any real deployment. A change is a new deployment by migration (ADR 0003).
- **The simulation's criteria** for these rules, taken from the reports. Every attack is judged against its **honest twin**, the same actor putting the same coin to honest use in the same run, not against a twin that does nothing: once funding pays a return, any funding beats doing nothing (`reports/fundertoken-v2.md`, #194; #195).

**Out of scope:**
- **Contract and node code:** the tasks after this spec, as small steps each with its integration scenario.
- **The owner's open choices** (design Open Questions): an early-risk multiplier for funders; whether a capped fix's cut is redistributed (the spec follows #194: redistribute) or not minted; what a pool share gives beyond tokens; the index pool's weighting window.
- **Per-repository tokens:** rejected (owner, 2026-11-08, #177). There is one protocol token.
- **Curated pools** with a performance fee (#193's lowest priority).
- **Anything real:** a chain, a token, a price feed or money (rule 1). The owner intends a paper, not a deployment.
- **The paid judge test (#160):** it runs on the frozen build that includes this change.

**Actors, incentives and attacks affected:**
- **Funders:** buyers fund bounties; investors fund one repository's pool or the index, earn tokens by merit, choose what happens to their leftover, and challenge overclaims because it's their coin.
- **Solvers:** paid in stablecoins only, up to merit from pools, and by bounties; they pay the payout fee. They earn tokens only by funding, or when a coin can't pay them.
- **Reporters:** state importance in dollars and stake on it.
- **Judges:** a new cycle-end panel scoring in dollars, a merit record, and checks paid by whoever causes them.
- **Attacks contained,** each measured against the honest use of the attacker's coin:
  - a project's own team overclaiming its fixes;
  - colluding judges, as a minority and as a majority;
  - a farmer circling its own coin through sock funders;
  - 1-cent pledges on valuable unfunded fixes (the per-fix cap, and the cut redistributed);
  - a farmer moving to the cheapest fee tier, which no longer exists because the fee doesn't depend on bounty size.

## Capabilities

### New Capabilities
- `merit-cycles`: each repository's cycle pool and the index pool, their shares and each funder's leftover choice; the cycle-end merit panel in dollars, calibrated by reference fixes; pay up to merit with (b) and (c); the network emission and the token earned by funders, with the outside-coin cap; a coin that can't pay; challenges before the split; judges' merit records; the token price the fee reads; and the parameters fixed per deployment.

### Modified Capabilities
- `bounty-market`: the market fee becomes the capped, token-indexed payout fee, paid to no one. The issue stake gains a claimed importance and the tolerance's forfeiture. Funding takes allowed stablecoins only, and whoever causes a check pays for it, with a burned margin.
- `incentive-simulation`: scenarios and acceptance criteria for cycle pools, funder tokens, the index pool, the adaptations, a blocked coin, the capped fee and challenges, with attacks judged against an honest twin with the same coin.

## Impact

- **Contracts (the next change, tasks group 3):**
  - deployment parameters, immutable, with devnet test values;
  - the allow-list of stablecoins and the probe for a coin that can't pay;
  - a cycle-pool contract keyed by repository, and the index pool;
  - the merit verdict in dollars, the pay rule, (b) and (c);
  - the network emission and the token's split to funders, replacing #58's per-bounty weights;
  - the fee reading a price feed fixed at deployment and changed only by migration (ADR 0003);
  - stakes with claimed importance; check fees with a burned margin.
- **Node:**
  - a merit-panel draw at the cycle's end;
  - a merit prompt that compares fixes in dollars, with reference fixes and batches;
  - sealed and revealed merit scores;
  - a fake merit panel for the integration suite.
- **Integration suite (`tests/integration/`):** a scenario per contract task, on the local devnet with the fake judge and the fake merit panel.
- **Simulation:** `pof/sim/cyclepool.py`, `pof/sim/repotokens.py` and `pof/sim/fundertoken.py` already model most rules, so the criteria cite them. The honest-twin measure is `invested_gain` in `pof/sim/fundertoken.py` (#194). The index by merit and the blocked coin are new.
- **#160:** its plan has to measure merit in dollars (the error against the reference fixes) and how often inflated importance is caught, alongside pass/fail accuracy. Its results become the real deployment parameters.
- **Constitution, by later ADRs:** the allow-list's record and its protected path (Article 7), and the burned margin on bounty-market checks in the version with the token (Articles 5.11 and 5.12).
