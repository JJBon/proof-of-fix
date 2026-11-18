# Design

## Context

- **#58 (`openspec/changes/proof-of-fix-58-token-emission`):** a fixed emission per period, split by each bounty's AI weight, the smaller of a registration estimate and a merge estimate (D3). The v1 contracts carry it: `Race.sol` records weights, and `Token.sol` splits each period's pool by weight. The v2 node signs a fixed `merge_weight` from its configuration, so no model estimates merit today.
- **The bounty-market spec's market fee:** 20 % of the winning price, split among validators, the author's escrow, infrastructure, insurance and the owner. The contract charges none (`pof.params` CONTRACT). Since #157 the owner takes no founder's share.
- **#132 (`openspec/changes/proof-of-fix-132-open-validators`):** gives panels (odd k, a seed fixed after the event, silent judges replaced), sealed then revealed verdicts, challenges by a larger fresh panel, random audits, family scores that never weight a vote, bonds and the silence slash.
- **#56 (`openspec/changes/proof-of-fix-56-local-contract`):** fee coins are a short list fixed at deployment, credits are pulled to any address their owner names, and a coin whose solvency fails goes withdraw-only for good, alone (Article 5.2). It also decided that no contract rule judges that a coin "can't pay"; D12 adds one, narrowly.
- **The constitution:** no key changes a rule (Article 2); the owner earns tokens only as an ordinary funder (Article 11.3, ADR 0005, merged); every margin is burned in one token and paid to no one (Article 12.2). This version mints no token (Article 5.12): everything here is for the version that carries the token, reached by migration.
- **The simulations behind each decision:**
  - `reports/repotokens-v2.md` (#177): the per-cycle split and the outside-coin cap;
  - `reports/potfee-v1.md` (#182): the capped token-indexed fee;
  - `reports/cyclepool-v1.md` (#184): pools, challenges, merit records and the stake;
  - `reports/fundertoken-v1.md` (#193, PR #194): one general token earned by funders, investor pools, the thin-cycle fix and the adaptations (a), (b) and (c);
  - `reports/fundertoken-v2.md` (#194, with #195's check domains): outside revenue, and the baseline every attack is judged against, D9.
- **The owner's decisions of 2026-11-10/11,** after #194, are folded in here: one general token earned by funders (D3), allowed stablecoins (D12), pools for non-technical investors (D13), the thin-cycle fix (D10), adaptations (b) and (c) and not (a) (D11), pay for compute (D14) and deployment parameters (D15).

## Goals / Non-Goals

**Goals:**
- Fix the rules so that contract and node work can start, and so #160 tests the judges on the job they will do: pass/fail plus merit in dollars.
- Every parameter named, with its value from the simulation or marked open.
- Build the architecture before the AI is measured: every number that depends on the judges' accuracy is a deployment parameter (D15), so the devnet runs the whole design on test values while #160 measures the real ones.

**Non-Goals:**
- Contract or node code: the tasks after this spec.
- The owner's open choices (Open Questions): an early-risk multiplier, what a pool share gives beyond tokens, the index pool's window, and whether a capped fix's cut is redistributed.
- Weighting votes by score (#132 keeps one judge, one vote).

## Decisions

### D1. Three ways to fund work: bounties, a repository's pool and the index pool
- **The rule:**
  - **bounties** stay optional, and their coin goes to the fix their funders chose: for buyers who need a specific fix;
  - **a repository's cycle pool** is funded by anyone, with shares recorded per cycle;
  - **the network index pool** spreads its coin over the repositories by merit (D13).
  - Pool coin pays fixes by merit (D10). Every product pays in allowed stablecoins (D12) and earns its funders the one token (D3).
- **Why all three:** the pools are simpler for non-technical funders and let minor fixes be paid on merit. Bounties keep a funder's say over what gets fixed, which is the demand signal the self-healing thesis relies on. In #194, single-repository pools, the index pool and bounty pickers all got 22–23 cents back per dollar at p\*, so no product is a trap.
- **Alternatives:**
  - pool only: the owner's first sketch; it loses the funder's say and the targeted demand signal;
  - bounties only: as today; minor work goes unpaid unless someone posts a bounty for it.

### D2. Merit is set at the cycle's end, in dollars, by one panel comparing the cycle's fixes
- **The rule:** the panel follows #132's draw. Each judge seals, then reveals, a merit in dollars of value for every fix, and a fix's merit is the median, unweighted.
- **Calibrated in dollars by reference fixes:** every panel also scores `MERIT_REFS` published reference fixes, each with a recorded dollar merit. Each judge's scores are scaled so the median of its reference scores matches the recorded merits, so merit is on one network-wide dollar scale. The reference set and its merits are part of the frozen merit prompt (D8), a protected path (Article 7), changed only by ADR.
- **Why dollars:** the pay rule (D10) pays at most a fix's merit value, and the emission (D3) is per network merit dollar. Both need merit on one scale across repositories, not shares within one cycle.
- **Why compare:** comparing is easier than pricing one fix alone. The simulation used a 15 % comparison error, against 30 % for #58's single estimates, and an overclaimed trivial fix stands out next to real ones.
- **Large cycles:** judges score at most `MERIT_BATCH` fixes per batch, each batch including the same reference fixes, which also scale the batches to one another.
- **What it replaces:** #58 D3's two per-bounty estimates as the token's weights. Those estimates stay useful as the claimed importance a reporter states, see D5.
- **Alternative:** keep D3's per-fix estimates. Each fix judged alone is easier to inflate, and its error is twice as large.

### D3. One general token, earned by funders by merit
- **The rule:**
  - **Emission:** each cycle the network mints E = min(`EMISSION_RATE` × the network's total calibrated merit, `EMISSION_CAP`).
  - **Per fix:** each merged fix gets E × its share of that merit, capped at `TOKENS_PER_COIN` × its outside coin: the coin from bounties and pools that paid it, less what its solver's accounts contributed. What the caps cut goes to the uncapped fixes in proportion to their merits. Only when every fix is capped is the rest not minted.
  - **To its funders:** a fix's tokens go to the funders whose outside coin paid it, bounty pledgers and pool shareholders alike, in proportion to that coin.
  - **Solvers are paid coin only,** in allowed stablecoins. A solver may also fund, and earns tokens on others' fixes like anyone; its own coin earns nothing on its own fix.
  - **Nobody else is minted tokens:** no owner's, founder's or validators' share (Article 11.3). The one exception is D12's blocked coin.
- **Why one token** (owner, #177 and 2026-11-10): per-repository tokens were rejected. One token lets every burn, including outside check domains' margins (Article 12), reach every funder.
- **Why the cap** (#177; #194 summary 5): without it, faked importance mints tokens for free, and 1-cent pledges on valuable unfunded fixes gained $3,700–74,000 a year in #194. With it, every claimed dollar of importance needs real coin behind it, which the fee then taxes (D4).
- **Why redistribute the cut** (#194 summary 6): #193's "the cut isn't minted" lets 1-cent pledges put their fixes' merit into the network total while their tokens are cut, so for $31 a year honest investors' tokens per coin fell 16 %. Redistributing the cut changes them by +0.2 %. The owner's confirmation of this rule is still listed in Open Questions.
- **`TOKENS_PER_COIN`, `EMISSION_RATE` and `EMISSION_CAP`:** deployment parameters (D15). #194 used 1 token per coin, 1 token per merit dollar and 8,000 a cycle.
- **What it replaces:** #58's fixed emission per period. The emission now follows merit, up to the cap.
- **Alternatives:** tokens to solvers (#58), which pays the people the fee is meant to tax; per-repository tokens (#177, rejected).

### D4. The market fee: the token value the coin earned, capped at `FEE_CAP_BPS`
- **The rule:** the fee comes out of the coin paid to a fix, so solvers pay it, and it's paid to nobody; burned, or added to the repository's next pool (`FEE_SINK`, see Open Questions). The price comes from a feed fixed at deployment, or an exchange's time average over `TWAP_WINDOW` until a feed exists; with no market, the fee is 0. `FEE_CAP_BPS` is a deployment parameter (D15); #182 chose 2,000.
- **Why** (#182):
  - **A flat 20 % fee** protects to 86 % at 80 % caught, but charges honest funders 20 % even while tokens are worthless.
  - **The uncapped indexed fee** is about three times weaker, and no setting stops farming.
  - **A fee by bounty size** is weaker than a flat 10 % fee and costs honest funders more.
  - **The capped indexed fee** protects like the flat fee, and never charges more than the tokens are worth.
- **Who pays, honestly** (#194 summary 2): the fee is almost all of what funders get back from the protocol's own activity. At p\* it takes about 19 % of solvers' pay. If it went to the next pool instead of a burn, investors would get back 3 cents per dollar instead of 23.
- **Why paid to nobody:** a fee paid to validators or the owner would give them a reason to inflate it. The owner takes no share (#157, Article 11.3).
- **Keyless:** the feed can't be switched by an account (ADR 0003 principle 5). A manipulated price can only move the fee within 0–`FEE_CAP_BPS` of the coin.

### D5. Claimed importance and the issue stake, forfeited above `MERIT_TOLERANCE`
- **The rule:** an issue states its claimed importance, in dollars, and posts `ISSUE_STAKE` (50 coin in the simulation). It's forfeited to the next pool when the claim is over `MERIT_TOLERANCE` (3× in the simulation, a deployment parameter, D15) times the merit awarded. The finder's fee is paid only on the outside coin, so funding your own issue earns no finder's fee, whatever the market fee is.
- **Why** (#184; #194 summary 5): the stake is what makes overclaiming lose. With challenges, records and audits but no stake, the team still made 6,700–8,700 a year. With the stake, its best response is to claim within the rule, and it loses money with up to 5 of 15 judges colluding. Without the stake, it gained $1,400–2,500 a year in coin alone once funders earn tokens.
- **Why 3×:** #58's tolerance, chosen for under 1 % false forfeits at the estimates' 30 % error. In #184, honest fixers lost under 0.2 % of the pool. Its real value depends on the judges' measured error (#160), so it's a deployment parameter.

### D6. Merit challenges until the split, by anyone with a claim on the repository
- **Who:** a share in the repository's pool or the index pool, or a pledge in the repository. They pay the challenge's check (D14), and get an AI check.
- **Upheld:** the merit is corrected before the split, and the challenger is paid `CHALLENGE_REWARD_BPS` (1,000 in the simulation) of the coin moved.
- **Why anyone with a claim:** investors have the motive, since it's their coin. In #184 the challenges anchored the judges' records to the truth. Without them, merit records backfired under a colluding majority: colluders reached 87 % of draws and 46 % of the pool was overpaid.
- **Window:** `CHALLENGE_WINDOW` after the panel reveals, before the split.
- **Alternative:** #132's challenge by a larger fresh panel. It's still available, but a merit challenge is one focused question, so an AI check suffices (the simulation assumed 90 % accuracy).

### D7. Judges' merit records against the corrected merit
- **The rule:** a merit more than `MERIT_TOLERANCE` off the final merit, either way, is a disagreement. It counts against the validator's own record (`RECORD_PENALTY` 0.5, `RECORD_RECOVERY` 0.02 per agreement, `RECORD_FLOOR` 0.05) and its family's score (#132).
- **Below the floor:** a validator isn't drawn for counted panels until it re-registers with a new bond, and starts again at `RECORD_NEWCOMER` 0.2.
- **Why per validator:** collusion is by validators, not by model families. A family score would dilute one colluder among its family's honest validators. Votes stay unweighted.
- **Alternative:** family scores only, as in #132. That leaves a colluding validator drawn as often as its family's honest ones.

### D8. Frozen before #160
The merit prompt (comparing a cycle's fixes in dollars, the batches and the reference fixes with their recorded merits) and its output format are part of the build #160 tests. #160's plan measures pass/fail accuracy, the share of inflated importance caught and the dollar error against the references, on mixed cycles of honest and attacker-inflated fixes. The 80 % pass mark is from #184's criterion. #160's measured values become the real deployment parameters (D15).

### D9. Every attack is judged against the honest use of the attacker's coin
- **The rule:** an attack's gain is its profit less its honest twin's, in the same run and on the same seed. The twin does the honest version of the play (fixes claimed at their worth) and puts the attack's coin to honest use, funding the pools at the tokens and returns honest funders get, or keeps it when that pays back less than the coin.
- **Why** (`reports/fundertoken-v2.md`, #194, summary 3 and table 7): funders now earn tokens (D3), so once the token has a price any play that funds beats a twin that does nothing, and plain investing would look like an attack. Against the honest twin:
  - overclaimed merit, funded from a second wallet, loses $2,900–4,700 a year at every price up to $100 a token, with 0, 3 or 5 of 15 judges colluding;
  - self-dealing (a fix claimed at its worth and funded from a second wallet) gains only the edge any bounty has, from $1.16–1.54 a token and by $11–43 a year: its own coin is paid in full when a pool is short;
  - 1-cent pledges, with the per-fix cap, gain only from about $16 a token, by $4–18 a year.
- **What it changes:**
  - v1's attack prices ($1.12 for self-dealing, $2.84 for overclaiming with self-funding) were measured against a twin that funds nothing, so they are no longer the test. What stops overclaiming is the issue stake (D5) and the challenges (D6), not a low token price.
  - While the token has no price, funding pays nothing back, the honest twin is the same as doing nothing, and #177's, #182's and #184's figures stand.
- **Where it's computed:** `invested_gain` and `pays_over_investing` in `pof/sim/fundertoken.py` (#194). The incentive-simulation criterion uses the same measure (task 1.5).
- **Alternative:** keep the twin that funds nothing. It flags honest investing as an attack as soon as funding pays, and would push for a low token price (the rebate ceiling #194 proposed) instead of the stake and challenges that actually stop overclaiming. ADR 0005 §7 set the rebate ceiling aside for the same reason.

### D10. Pay: each fix gets the lesser of its merit value and its pro-rata share (the thin-cycle fix)
- **The rule:**
  - **A fix's claim on its pool** is its merit in dollars times the pay per merit dollar (1, or D11's (b)), less the bounty coin it was already paid.
  - **The pool pays** each claim in full when it covers them all, and pro rata to the claims when it's short. So each fix is paid min(its claim, its pro-rata share).
  - **The leftover stays with each funder by share.** Each funder chooses, alone, to roll it over to the next cycle (the default), withdraw it, or move it to another repository's pool or the index pool. Withdrawn coin earns nothing. No majority decides for a funder.
- **Why:** the earlier rule paid the whole pool by merit whenever any fix merged, so one typo in a quiet cycle took all of it (the flaw #193 found in merit-cycles). Paying at most the merit value turns a pool into a budget that waits for work.
- **What it costs** (#194 summary 1 and 4): without (b), about 15 % of pool coin waits at the year's end, and investors leave stalled repositories within about 5 cycles. Waiting coin costs them idle money, not token yield.
- **Alternative:** split the whole pool by merit (the rule this replaces); or a majority of shareholders decides what happens to the leftover (rejected by the owner: each funder decides alone).

### D11. Adaptations: (b) and (c) adopted, (a) rejected
- **(b) The price of work rises when money waits:** the pay per merit dollar is clamp(pool ÷ the cycle's unpaid merit, `PAY_MIN`, `PAY_MAX`), with 1 and 1.5 in #194, both deployment parameters (D15). It spends idle coin (0.3 % waits at the year's end, against 14.7 %) and draws solvers in (11.4 fixes a cycle in a healthy repository, against 10.6).
- **(c) A shortfall carries over:** what a short pool leaves unpaid, at 1× merit, is the first claim on the repository's next cycle. Its tokens are minted when it's paid, as merit equal to the coin that paid it. It leaves no merit unpaid, and slows the exit from a stalled repository by 2–3 cycles while its backlog is paid.
- **Together:** (b) alone leaves 11 % of merit unpaid, because it drains pools at 1.5× and they're short later; (b) + (c) pays solvers $1.06 per merit dollar, leaves 0.5 % unpaid and 0.1 % of coin idle (#194 table 3). Funders' tokens per coin fall from 0.85 to 0.77, because each coin buys less merit; the value back per coin at p\* stays 23 %.
- **(a) The cap follows burns: rejected.** cap = base + last cycle's burns doesn't settle supply: once the cap binds, minting replaces every burned token and adds the base, so supply grows by about the base every cycle whatever the use. With a base equal to the cap it inflated more than a fixed cap (mint ÷ burn 4.0 against 3.5 at $1, #194 summary 7). A small base (a quarter of the cap) bounds inflation at the base, and with outside burns stops being a risk (v2 summary 7), but it adds a moving part for no gain in what funders get back, which only burns set. The cap is fixed per deployment (D15). If (a) is ever reconsidered, it's only with a small base, by a new deployment.

### D12. Allowed USD stablecoins, and a coin that can't pay
- **The allow-list:** bounties, pools and check fees take USD stablecoins from an allow-list, starting with one. It's fixed at deployment and changed only by an accepted ADR (the constitution tier), never by a key (Article 2). Until ADRs reach the chain (#85 task 5.10), applying such an ADR is a new deployment by migration, as #56 decided for fee coins; after that, a constitution-tier verdict (5 of 7, Article 5.5) applies it.
- **A coin that can't pay** is one whose transfer out of the contract fails for everyone, or whose solvency fails:
  - **evidence on-chain only:** anyone may call a probe that transfers one smallest unit of the coin from the contract to itself. If it reverts (the coin is paused, or the contract's own address is frozen), the coin is blocked from that block; a later probe that succeeds lifts it. A solvency failure (Article 5.2) blocks it for good.
  - **a recipient frozen by an issuer isn't a blocked coin:** the credit is pulled to another address (#56).
  - **while blocked,** the coin takes no new funding, and its credits stay owed, pulled when transfers work again (Article 5.3). #56's `offerSwap` still lets anyone offer a credit's owner another coin.
- **Its tokens go to the fixers:** for the fixes a blocked coin was due to pay, the tokens that coin's funders would have earned go to those fixes' solvers, in proportion to merit, out of the same emission. No extra tokens are minted. This is the only case in which solving earns tokens.
- **Said plainly:** a freeze of the contract's own address means nothing in that coin can move: no payout, refund or withdrawal, for anyone, until the issuer lifts it. The contract can't route around it. The token and the other allowed coins carry on.
- **Why:** the allow-list keeps out coins whose issuer could break the books, and starting with one keeps every price in one unit. Giving the funders' tokens to the fixers when coin can't reach them pays the people who did the work in the one asset the protocol controls, without minting more.
- **Note on #56:** #56 decided that no contract rule judges that a coin "can't pay". This adds one, narrowly: a failed self-transfer or a solvency failure, both on-chain facts.

### D13. Pools for non-technical investors
- **The rule:**
  - **A repository's cycle pool** (D1) and **the network index pool**, which at each cycle's start spreads its coin over the registered repositories in proportion to their calibrated merit over the last `INDEX_WINDOW` cycles. Coin it places is pool coin like any other; what a cycle leaves unspent returns to the index.
  - **No picking inside a pool:** every funder of a pool earns the same tokens per coin spent in a cycle: the pool's tokens split by the coin each funder's share spent.
  - **Published history:** each pool's tokens per coin spent, cycle by cycle, is computable from the contract's events alone and published with the leaderboard (#151).
- **Why:** an investor who can't judge code still gets the network's average. In #194 the index (by need) got 0.86 tokens per coin and single-repository pools 0.85, and at p\* both got back 23 cents per dollar. The published history is what a non-technical funder chooses on.
- **By merit, not need:** #194's index spread by need (recent merit less bounty coin and coin already waiting). The owner chose merit; the window is open (Open Questions), and task 1.7 re-runs #194's figures with it.
- **Bounties remain** for buyers who need a specific fix.
- **Not modelled yet:** curated pools with a performance fee (#193's lowest priority).

### D14. Whoever causes compute pays for it
- **The rule:** every check is paid by whoever causes it: the reporter's registration, the solver's attempts, a challenger's merit challenge, an outside requester's question (Article 12), and the cycle's pool for its merit panel, before the split. It pays:
  - the judges' real cost in an allowed stablecoin, at the price table's unit prices plus the one service fee per counted check (Article 5.11);
  - in a version with the token, a protocol margin of `CHECK_MARGIN` dollars a check, paid in the token at D4's price and burned, never paid to validators or anyone. With no token price, the margin is 0.
- **Reads can't be charged:** anyone can read public chain data without the contract, so no rule charges for reading verdicts, pools or the published history.
- **The owner** earns tokens only as an ordinary funder (Article 11.3, merged in ADR 0005).
- **Why:** #194 found margins add under half a point of what funders get back from the bounty market alone, but every burn counts once outside use grows (v2: break even at about $6,900 of margin a week). Charging the cause keeps any one actor from spending others' coin on checks.
- **The service fee isn't the margin:** #193's note said validators are paid at cost; Article 5.11 also pays them one service fee per counted check, which stays. The margin is separate, and burned.

### D15. Deployment parameters: the architecture before the AI is measured
- **The rule:** every number that depends on the judges' measured accuracy is fixed per deployment: set in the constructor, immutable and readable on-chain, with no setter:
  - `FEE_CAP_BPS` (D4);
  - `MERIT_TOLERANCE`, the 3× of the stake and the records (D5, D7);
  - `TOKENS_PER_COIN`, `EMISSION_RATE` and `EMISSION_CAP` (D3);
  - `PAY_MIN` and `PAY_MAX`, the clamp bounds (D11);
  - `ASSUMED_DETECTION_BPS`, the detection rate the safety argument assumes (80 % in #184 and #194). The contract doesn't use it; it records what the deployment's safety rests on.
- **The devnet** deploys with test values (#194's: 2,000 bps, 3×, 1 token per coin, 1 token per merit dollar, 8,000 a cycle, 1 and 1.5, 8,000 bps). **Real values** come from #160's measurement, and a deployment to anything but a devnet records the hash of #160's report; the deploy script refuses without it. Nothing real is deployed (rule 1).
- **Keyless:** a change is a new deployment by migration (ADR 0003), never a setter.
- **Why:** the contracts and the integration suite can be built and tested end to end now, on the fake judge and a fake merit panel, while #160 measures what the real values should be.

## Risks / Trade-offs

- **[Risk] A colluding majority isn't fully healed:** 21 % of the pool overpaid at 8 of 15 colluding, in #184. → Bonds per re-entry, #132's caps per operator, and challenges. The report names the limit; the paper states it.
- **[Risk] Everything rests on the detection rate:** at 50 %, 22–33 % of the pool is overpaid in #184. → #160 measures it before any real deployment, and its measured values become the deployment parameters (D15).
- **[Risk] Funders don't get their money back from the protocol's own activity:** about 23 cents per dollar at p\* (#194). → Outside check domains' burns (Article 12, ADR 0005). The paper doesn't present pools as investments with a return.
- **[Risk] Price feed manipulation.** → The cap bounds the fee to 0–`FEE_CAP_BPS` of the coin, and the time-averaging window spreads a push.
- **[Risk] Calibration drifts:** judges may score the reference fixes differently over time. → Scores are scaled to the references each cycle, and #160 measures the residual error.
- **[Risk] An issuer freezes the contract.** → Nothing in that coin moves (D12); the allow-list starts with one coin, and the other coins and the token carry on.
- **[Risk] A large cycle may not fit one prompt.** → Batches with reference fixes. The scaling error is a parameter to measure in #160.
- **[Risk] Outside use pushes the token's price above v1's attack prices** (p\* of about $3-4 at #196's upper end, `reports/fundertoken-v2.md`). → Attacks are judged against the honest twin (D9), and overclaiming still loses at every price up to $100 a token. Self-dealing's and 1-cent pledges' small gains stay figures in the report.
- **[Trade-off] Pay arrives at the cycle's end,** not at merge. → Bounties still pay at merge, as today; only pool coin and tokens wait.
- **[Trade-off] Coin waits in pools** under the thin-cycle fix. → (b) spends it and (c) pays the shortfall later; each funder may withdraw or move it.

## Migration Plan

- **Simulation and specs first.** Contracts follow in a later change: a new contract version deployed beside the old (keyless migration, ADR 0003), the first one with a token (Article 5.12). The old Race keeps its per-bounty weights until its last period closes.
- **Devnet first, on test values** (D15); real values only after #160.
- **Rollback:** don't migrate. Nothing real is deployed (rule 1).

## Open Questions

**The owner's to decide:**
- **An early-risk multiplier for funders:** whether funding a repository or the network early earns more tokens per coin than later funding, and how it would decay. Not simulated; it would change D3's split to funders, not the per-fix cap.
- **Whether a capped fix's cut goes to the uncapped fixes or isn't minted.** The spec follows #194's recommendation and D3: redistribute, which removes the 16 % dilution 1-cent pledges cause. An equivalent rule counts each fix's merit in the network total only up to its coin.
- **What a pool share gives beyond tokens:** a vote on priorities, a claim on the fee sink, or nothing. It changes the pool's attractiveness, not these rules.
- **The index pool's weighting window (`INDEX_WINDOW`):** decided by the owner, 2026-11-13: **4 cycles** (28 days), as #194 simulated. One cycle of merit is noisy, so one big fix would swing where the whole index goes; repositories are still paid every cycle.

**Parameters and follow-ups** that don't change the requirements' structure:
- **Cycle length (`CYCLE_DAYS`):** decided by the owner, 2026-11-13: **7 days**, as the simulations used.
- **The merit panel's size:** #132's k rule, or a larger fixed k for cycle-end panels, which judge more coin at once.
- **`MERIT_BATCH`, `MERIT_REFS` and the reference set:** set by #160's measured scaling error.
- **`ISSUE_STAKE`, `CHALLENGE_REWARD_BPS` and `CHALLENGE_WINDOW`.** The simulation used 50 coin, 10 % and before the split.
- **The bond per validator and per re-entry:** ADR 0004's bond, or a larger one. #184 used 250.
- **`FEE_SINK`:** burn, or the next pool. #194 recommends the burn: it's 20 of the 23 cents investors get back.
- **`CHECK_MARGIN`:** #194 suggests $0.05–0.10 a check; and whether a payer may pay it in coin that the contract swaps to the token.
- **`TWAP_WINDOW`, and which feed:** Chainlink, or another oracle.
- **The first allowed stablecoin,** named by its ADR.
