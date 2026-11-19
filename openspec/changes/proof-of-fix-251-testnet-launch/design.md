# Design

## Context
- **Why:** see proposal.md. The behaviour is in `specs/deployment-binding`, `specs/canonical-head`, `specs/radicle-hosting`, `specs/public-release` and the deltas to `validator-admission`, `reputation` and `bounty-market`. This document covers how, the parameters, the Radicle spike and the order of work. Decisions here are numbered **L1–L17** so they don't collide with #132's D-numbers, which are referenced as they are.
- **v3 today** (`contracts/src/v3`, [`reports/devnet-v3-local.md`](../../../reports/devnet-v3-local.md)): Validators, Panels, PanelScores, FeesV3, PoolV3 and RaceV3 run beside v2 on a local devnet, with the `simulated` proof type and the fake judge. #132's rules decided after the judge measurement (D20 seats by rank, D21 the test dispute, D24–D30) are in its specs and the simulation, not in the contracts (`docs/paper/open-problems.md` 7.5).
- **Radicle today:** #190's spike ([`reports/radicle-spike-v1.md`](../../../reports/radicle-spike-v1.md)) showed a threshold merge gated by `Heads.head`, with three fixed judges as delegates. #201's adapter (`oracle/radicle.py`) and `pofctl verify-head` work for v2's fixed seats. The spike's limit: **v3's per-draw judges can't be Radicle delegates**, because the delegate set changes only by a threshold of the current delegates, and a new delegate must have published `main` first.

**What the code does today that contradicts the owner's decisions** (each is a task below):

| Decision | The code today | Where |
|---|---|---|
| One repository, immutable | `RaceV3`'s constructor takes arrays `repos_`, `heads_`; `register` accepts any registered repository and also `repo == 0`, in which case `claim` never moves a head | `RaceV3.sol` constructor, `RaceV3Annex.register`, `RaceV3.claim` |
| Sepolia only | No chain check at construction; only the `simulated` proof type is tied to chain ids 31337 and 7193 | `Validators.sol` |
| Windows configurable | `SEAL_WINDOW`, `REVEAL_WINDOW`, `CHALLENGE_WINDOW[k, level]`, `ADR_WINDOW`, `REMOVAL_WINDOW` and `UNBONDING_DELAY` are constants | `PanelsBase.sol`, `Panels.sol`, `Validators.sol` |
| No silent stuck state below the floor | A $5 slash on a $100 bond leaves the validator `Active` and counted in `activeCount`, but `isDrawable` false, with no event | `Validators._rebucket`, finding 7 of the devnet report |
| Heads and the merge in v3 | `Heads` is wired, but `claim` moves the head **before** the verdict is final; a reversal in the window reopens the bounty and leaves the reversed fix as the head, with no way back | `RaceV3.claim`, `RaceV3Annex._sync`, `Heads.move` |
| D29, D30, 3 active solvers | Per-check deposits and charges; no identity reputation, no claim cap, no flat fee, no solver count | `RaceV3`, `FeesV3` |
| R+F's protection | Report v5's result rests on active honest solvers finding failing tests, i.e. D21's dispute, which isn't in the contracts (#132 task 10.4) | — |
| Enclave validators with a model | The v3 node refuses registration checks with a model judge, and stays silent on them (paying the silence slash); it finds fixes only through a forge's pull requests | `oracle/node_v3.py` `_registration`, `_find_pull` |
| Funding from pofctl | `pofctl` speaks v2 only, and its keys are devnet keys it refuses to use on a public chain | `pofctl/` |
| Open code | (fixed 2026-11-18) Was: no licence file and `UNLICENSED` headers. Now "MIT OR Apache-2.0" with `LICENSE-MIT` and `LICENSE-APACHE` | #158's licence gate |
| Publishing from the snapshot | `scripts/github_snapshot.py` targets GitHub only and refuses any target that isn't private | its `PRESETS` and target check |

## Goals / Non-Goals
**Goals:**
- A v3 deployment that can only serve proof-of-fix and can only be constructed on Sepolia, with its windows chosen per deployment.
- A head on-chain that never names a fix whose verdict was reversed.
- A Radicle merge model for changing panels, chosen by a spike, with a check anyone can run.
- Every public step behind the owner's go, recorded.

**Non-goals:**
- Preventing forks from deploying the code without these checks. It can't be done in open code, and the specs say so.
- Changing any #132 decision. D27, D29 and D30 are built as #132 records them; values not yet decided there stay its owner's decisions (#132 tasks 10.2, 11.2, 12.2).
- Validator capacity and per-repository rate limits (#253) and validators' repository choice (#252).

## Decisions

### L1. One repository, an immutable constructor argument
- **The rule:** `RaceV3`'s constructor takes `repo` (`keccak256(RID)`) and `genesisHead` instead of arrays. `Heads` is created with that one entry. `register` refuses any other id and zero (`deployment-binding`).
- **Why both refusals:** a zero repository would let a bounty be won without the head moving, which is a way around the merge rule.
- **`FeesV3`'s per-repository profiles:** one profile, for this repository; the default profile is unused.
- **Alternative rejected:** a list fixed at deployment with one entry. It keeps the code path for many repositories in the deployed bytecode and invites a second entry in a later deployment record.
- **The limit, stated:** this binds the deployment. A fork removes it with a one-line change; the README and the paper say so.

### L2. Sepolia only, at construction and in the deploy script
- **The rule:** each v3 contract's constructor reverts unless `block.chainid == 11155111`. The deploy script reads `eth_chainId` before signing anything and stops unless it is 11155111.
- **The conflict with local testing (decided by the owner on 2026-11-18: option 1):** the devnet (7193), anvil (31337) and Foundry tests need to construct the same contracts, and the `simulated` proof type is accepted only on 31337 and 7193. Three ways:
  1. **(recommended)** the constructor accepts 11155111 and the two local test ids already named in `Validators.sol`. On any other chain, mainnet included, it reverts. On Sepolia the `simulated` type is refused, as today.
  2. Exactly 11155111: local runs use `anvil --chain-id 11155111` and `vm.chainId`, and the simulated attestation needs another switch, which then exists in the Sepolia bytecode.
  3. A build profile with a different constant per chain: two bytecodes, so the audited one isn't the tested one.

  **Decided: option 1.** It matches the owner's intent (no deployment on a chain with value) and keeps one bytecode. Its risk: a public chain that reuses 31337 or 7193 could host a deployment, with the `simulated` type accepted. The deploy script refuses both ids for anything but a local endpoint.
- **Why also the script:** the constructor check costs a deployment's gas to discover; the script stops before signing.

### L3. A keyless deploy from a fresh wallet
- A new externally owned account, funded from a Sepolia faucet, deploys and has no role afterwards: no owner, admin, upgrade or pause (ADR 0002, D15). The deployment record names it.
- **The deploy script** (`contracts/script/DeploySepolia.s.sol` and a shell wrapper) is a dry run by default, and broadcasts only with an explicit flag naming the step (`public-release`). Before anything, it checks:
  - the chain id (L2);
  - that the Radicle repository exists and its canonical `main` is the genesis head given (`pofctl verify-head --rid … --commit …`);
  - that the windows pass the constructor's order check, by simulating the deployment locally first.
- **Order:** the Radicle repository first (task group 6), then the deploy (group 7). The genesis head is the Radicle repository's root commit, or its `main` at the moment of deploying.

### L4. Windows as constructor parameters
- **The rule:** a `Windows` struct passed to `Panels` (and the derived unbonding delay to `Validators`), stored as immutables, readable, and listed in the deployment record. The constructor checks order (`deployment-binding`).
- **Contents:** `SEAL_WINDOW`, `REVEAL_WINDOW`, `CHALLENGE_WINDOW[k, level]` for k ∈ {1, 3, 5, 7} and levels A and B (level C's entries are kept in the struct but unused on a TEE-only deployment), `ADR_WINDOW`, `REMOVAL_WINDOW`, `K1_WINDOW_MIN`.
- **Derived:** `UNBONDING_DELAY` = the longest challenge window + `UNBONDING_MARGIN` (7 days), as #132 already defines it (504 h with today's values).
- **Why constructor parameters and not a setter:** a setter is a key (D15). Different deployments (devnet in minutes, Sepolia, a fork) need different values; one deployment never changes.
- **Values for Sepolia (decided by the owner on 2026-11-18: the production values):**

  | Name | Production values (ADR 0004, until #132 task 10.2 replaces them) | Shortened alternative | Why |
  |---|---|---|---|
  | `SEAL_WINDOW`, `REVEAL_WINDOW` | 2 h, 1 h | 2 h, 1 h | judges on real hosts need the time either way |
  | `CHALLENGE_WINDOW[1, A]` | 168 h (level B: 336 h) | 24 h (B: 48 h) | a lone verdict needs time for anyone to re-run it |
  | `CHALLENGE_WINDOW[3, A]` | 24 h (B: 48 h) | 6 h (B: 12 h) | |
  | `CHALLENGE_WINDOW[5, A]`, `[7, A]` | 12 h, 6 h (B: twice) | 3 h, 2 h | |
  | `ADR_WINDOW`, `REMOVAL_WINDOW` | 14 days, 48 h | 14 days, 48 h | an ADR's notice isn't a speed question |

  **Decided: the production values.** The owner's thesis is to measure the time to heal (#248); a testnet with shortened windows measures a different system. The shortened column stays documented as the alternative, not used on Sepolia.
- **How it's tested:** the Foundry suite runs with production values and with minutes; the devnet run (#248's `scripts/time-to-heal.sh`) runs with minutes, so a reversal is measured in wall-clock time on a real clock, which task 5.2 of #132 needed.

### L5. A bond below the floor is a visible state
- **The rule:** the registry treats "active with a bond below `BOND_FLOOR`" as its own state, `BelowFloor`, entered and left inside `_rebucket` (or wherever the bond changes), with an event each way; `activeCount` excludes it (`validator-admission` delta).
- **`topUp`** to the floor returns it to `Active` without qualifying again: it was qualified, and only its bond changed. **`leave`** works from `BelowFloor` with the same unbonding conditions.
- **What counts it:** everything that reads `activeCount` (the shadow rate while fewer than `K_MAX` are active, the k = 1 hold, FeesV3's idle signal) no longer counts a validator that can't be drawn. That is the bug in finding 7: a challenge waited for a validator that looked active.
- **Alternatives rejected:**
  - **Slash into a separate margin above the floor:** the floor then moves up by the margin; a second slash brings back the same state.
  - **The node tops up on its own by default:** it spends the operator's coin without asking. It stays an option the operator configures.
- **How it's tested:** a Foundry test per scenario of the delta, an invariant (`activeCount` equals the count of `Active` validators with bond ≥ floor), and the devnet run without the script's manual top-up.

### L6. "Active solver" and the minimum of three
- **The rule** (`bounty-market` delta): an identity is active while, within `ACTIVE_WINDOW`, it has a final passing fix or an upheld failing-test dispute in the repository. Pledges are refused while fewer than `ACTIVE_SOLVERS_MIN` are active. Issues can still be registered and fixed with no funds.
- **Why three:** report v5 (section 2 and the post hoc rows): R+F holds, every attacker at or below its twin, with 3 and 10 active honest solvers finding a failing test 1 time in 4 (assumed); with 1 it leaves gains of $237–3,870 a year per attacker. The owner chose the minimum instead of a deposit (2026-11-17, #251; no deposit, #250).
- **Why these two events:** they are what the chain can see. The simulation's "active honest solver" is one that searches every pass; the chain can't see a search, only its results: a fix that stood, or a test that reversed one.
- **Why unfunded fixes count:** otherwise no repository could ever reach three, since nothing can be pledged before.
- **`ACTIVE_WINDOW`: 13 weeks, proposed.** Long enough that a solver working a few issues a quarter stays counted; short enough that a repository whose solvers left stops taking new money within a quarter. Report v5's not-simulated conditional deposit used "the last window" in the same sense.
- **The named trust point:** one party can make three identities active with three good fixes (three judges' fees and three fixes' work). Then the minimum is met by one solver, which is report v5's failing case. What bounds it: D29's cap (each new identity starts at $50 of open claims), and every bad fix still faces the panel and disputes. Measured by task 3.2's simulation, not assumed.
- **Funded bounties continue when the count falls:** refusing them would strand funders' coin; the count only gates new money.
- **How the simulation tests it** (task 3.2): `pof/sim/openval/nodeposit.py` gains the pledge gate and the on-chain definition of active, with report v5's attackers plus a **sybil of three** (one party's three identities unlocking pledges, then submitting bad fixes), on 1, 3 and 10 honest solvers; rows by `ACTIVE_WINDOW` (6, 13, 26 weeks).

### L7. D29 and D30 in the contracts
- **As #132 records them** (`reputation` and `bounty-market` deltas): `REP_BASE` $50, `REP_MULT` 1, `REP_LOSS_X` 2 ("minus", not a reset); `JUDGE_FEE` re-measured each period (report v5: $5.03 on its base network). On Sepolia the amounts are in the test coin.
- **The identity is the solver's address.** Report v5's free-identities attacker (S) already plays one address per fix; the cap held from 3 solvers.
- **Where they are built:** #132 task 12.5 (contracts) and 12.6 (node, pofctl). This change doesn't duplicate them: its task 3.6 checks they are in the deployed set and adds the launch's tests. If #132's tasks haven't run when the launch needs them, they are done there, under #132's ticket.
- **D21 and D20 are needed too.** R+F's result rests on rivals' failing-test disputes (D21), and a network whose validators run one family stalls under the family cap without D20 (open problems 7.5). Both are #132 task 10.4, a dependency of the deploy.

### L8. D27 is in the launch set
- **Decided for the launch (owner, 2026-11-17, #251):** while fewer than `CAP_MIN_FAMILIES` families can judge, a challenge that can't draw D4's larger fresh panel is judged by a second draw of the original size from those families. Its spec text is #132's `judge-panels` requirement "A challenge among few families gets a second draw"; its `(proposed)` mark goes when #132's task 11.2 records the decision.
- **`SECOND_PANEL` ("few families" or "always")** stays #132's open question; the launch takes whatever 11.2 records. Without D27, report v4 found 23 % of verdicts never final under one family, which on a testnet of a few validators is most of them.
- **Built by** #132 task 11.4's Panels part.

### L9. The head moves at finality
- **The rule** (`canonical-head`): `claim` no longer calls `Heads.move`. A new call, `merge(bounty)`, which anyone may make, moves the head once the winning verdict is final; until then the bounty is `Won`/claimed but not merged. Instalments still start at finality, as today.
- **Why:** today a fix reversed inside its window stays as the head, and the next fixes are based on it. Radicle's `main` (any of the candidates in L11) would then carry a reversed fix, and the only way out is a new fix that reverts it, judged and paid.
- **The cost:** the next fix to the same code waits for the previous one's finality: 24 h for a level A panel of 3 with production windows, 168 h plus any hold for k = 1. Fixes to different files still rebase cleanly. `scripts/time-to-heal.sh` measures it.
- **Alternatives rejected:**
  - **Move at claim and add `Heads.revert`:** the head can go back to the base only if nothing moved since; otherwise the chain can't compute the reverting commit. A frozen head then blocks every bounty.
  - **Keep it as it is:** a reversed fix in `main` with no automatic way out.
- **The stale-base rule** stays v2's (S1): at `merge`, the base must be the head, or the call reverts and the winner keeps its place until the merge deadline.

### L10. TEE only
- A constructor flag, `teeOnly`, true for Sepolia: `Validators` refuses the zkTLS proof type at genesis and in `applyAdr`. The `simulated` type is already refused off local chains (D18).
- **Why a flag and not leaving zkTLS off the genesis list:** an ADR could add it later (D11). The owner's decision is for this deployment, so the deployment can't change it.
- **Validators' hardware:** level A (a cloud's confidential VM with its attestation) and level B (SEV-SNP or TDX elsewhere). #253 builds the first kit (AWS SEV-SNP).

### L11. Radicle under v3: a spike between three models
The question: who signs Radicle's canonical `main` when the judges change with each draw. Each candidate keeps `Heads.head` as the truth (L9) and differs in what Radicle's own `main` means.

| | (a) Delegates are the seated validators | (b) The chain is the only truth | (c) One merge key in approved enclaves |
|---|---|---|---|
| Identity document | delegates = the validators seated on-chain; threshold = a majority of them | one or a few delegates of convenience; their `main` isn't authoritative | one delegate: a key generated inside an enclave and shared only with attested enclaves (#94) |
| Who moves `main` | every seated node pushes `Heads.head` when it moves (#190's gate: refuse anything else) | anyone may push anything; readers ignore `main` and fetch the commit `Heads.head` names | the enclave pushes only `Heads.head` |
| When seats change | each seated node signs the identity revision whose delegates equal the seats, and refuses others; a new seat first publishes `main` at the head | nothing to do | nothing; a key rotation needs an ADR and a revision signed by the old key |
| Check anyone runs | `verify-delegates` (identity vs seats) and `verify-head` | `verify-head` (the only check) | `verify-head`; the enclave's attestation |
| Fails how | a majority of seated validators colluding moves `main` or the delegates; slow or stuck when many nodes are offline | plain `rad clone`, `git clone` and the explorer show a `main` that may be wrong | a broken enclave (level B physical attack) leaks the key; complex key sharing |

- **Recommended: (a), with (b)'s check as the one anyone runs.** (a) keeps Radicle's own tools showing the judged code, its failure needs a colluding majority of bonded validators, and `verify-head` catches it anyway. (c) depends on #94's key sharing, which isn't built.
- **The genesis delegate:** the owner's node creates the repository (`rad init`), so it is the only delegate until validators are seated. Under (a), its first identity revision hands the delegate set to the seats on-chain and removes itself; until then it is a central point, named in the deployment record.
- **What the spike measures** (task group 2), all on an internal network as #190 (Radicle's `test` network, no route out, anvil, the real v3 contracts with short windows):
  1. (a): identity revisions per seat change, the time for all nodes to converge, what happens when a seated node is offline or below the floor (L5), the largest delegate set Radicle 1.10.x accepts, and #190's negative scenarios (outsider, lone delegate, two rogue delegates) under changing seats;
  2. (b): `pofctl checkout` and `verify-head` fetching the head's commit from any namespace, and what the explorer and a fresh `rad clone` show;
  3. (c): a desk study only, unless #94's enclave key provider exists by then;
  4. for each, a validator fetching a patch's commit and judging it (L12).
- **The spike decides.** Its report names the choice and the reasons; the owner accepts it; then the adapter (task 4.1) is built for that choice.
- **Decided (owner, 2026-11-18): (a), with (b)'s checks** as what tools rely on (`reports/radicle-spike-v2.md`, #261: 22 scenarios, 3 runs in a row). Conditions from the spike:
  1. **Each validator's Radicle node ID goes on-chain at registration**, so a seat maps to exactly one node key, and `verify-delegates` reads it from the chain. Today v3 has no such link; the spike carried signed bindings in the identity document instead.
  2. **`BelowFloor` (L5) is built**, so seats are the drawable validators.
  3. **The gate and the revision review run in the node's adapter (task 4.1)**, with **one pending identity revision at a time**: Radicle 1.10.3 blocks a delegate's second proposal while an earlier one is pending.
  4. **`rad sync` takes the RID as a positional argument** in Radicle 1.10.3. The `--rid` form fails, and every caller hid the error. It is fixed in #190's `gate.sh` and still to fix in `oracle/radicle.py`, the v1 spike script and `tests/integration/radicle.py` (task 4.1).
- **Measured:** each seat change is one identity revision; every node converges in 0.36–0.50 s; Radicle accepts up to 255 delegates; with 2 of 4 delegates offline, `main` lags and `verify-head` flags it until one returns. A rogue majority can move `main` and the delegates, and the checks catch it.

### L12. Bounties on Radicle
- **The issue:** an on-chain issue carries a Radicle issue id (the issue's collaborative-object id, 20 bytes) in its registration. The registration check reads the Radicle issue the way v2's bot reads a labelled forge issue: its text claims the registration (`bot/logic`'s claim format).
- **The fix:** a Radicle patch on proof-of-fix. The solver's commitment opens to the patch revision's head commit, its base and its salt; the claim (submission id, salt) is in the patch description, as it is in a pull request body today. The node replaces `_find_pull` with a Radicle source that lists patches on its own node.
- **Funding:** `pofctl` gains v3 and Radicle commands (`issue register --rad-issue …`, `pledge`, `submit --patch …`) and a public-chain key path (a keystore file, never printed). A bot adapter (#210) is optional.
- **The model judge's registration check:** the v3 node refuses it with a model judge today and stays silent, paying the silence slash. The launch needs it (task 4.3), since every Sepolia validator has a model.

### L13. The scrub and the fresh history
- `scripts/github_snapshot.py` gains a `radicle` target: it builds the snapshot tree (as today: tracked files of one ref, terms replaced, the scan), commits it as **one root commit** in a new git repository, and, only with the publish flag, runs `rad init` on the given node. Its private-target check stays for GitHub.
- **The terms for the public snapshot:** the owner's name stays (rule 5 exception); #158's removal list goes (company domain, AWS ids, collaborators' names, ERP and platform references). The terms file stays on the owner's machine.
- **Licence:** #158's gate (MIT or Apache-2.0). Every `UNLICENSED` header and a `LICENSE` file change before the snapshot.

### L14. The seed
- One seed node with a selective policy: block by default, seed proof-of-fix's RID only (`radicle-hosting`). Its configuration lives in the repository; which host runs it, and its cost, are the owner's decision. Public seeds that agree to replicate may be added; none is required (ADR 0003, principle 1).
- **Radicle's September flaws:** #190 found 1.10.3 without the fix #92 waits for; public repositories were judged unaffected. The release in use is checked again at publication time.

### L15. The deployment record goes in through the repository's own process
- After the deploy, the canonical `main` moves only through `Heads` (L9, L11). So the deployment record (addresses, constructor arguments, deploying address, chain id, RID) is first posted as a Radicle issue, and then enters the repository as the **first unfunded issue and fix** through the race. That is also the first end-to-end run on Sepolia.

### L16. Launch validators
- **At least 7 validators, 15 as the target** (owner, 2026-11-18, from report v6). With 4, a panel is at most 3, whose $250 limit leaves larger bounties never judged, even without spam. With 7 the k = 1 hold ends (devnet report). With 15, capacity plus reputation-first ordering holds against heavy spam for Opus and narrowly fails for GPT. Who runs them at first and their model budget are the owner's decisions (#251 step 8).
- **Capacity, and no repository cap at launch** (owner's go 2026-11-18, corrected by report v6's post hoc newcomer-lane run):
  - each validator takes at most `MAX_CHECKS_PER_HOUR` = 5 checks an hour. That bounds each validator's model spend under spam (118 checks a day at most, $2.36–14.18, against up to $28.66 with no capacity), with the node's own budget stop beside it;
  - **the repository cap is off while proof-of-fix is the only repository** (D31, task 13.8 of #132). With one repository it is a network-wide cap: at 7 checks an hour it means about one panel an hour for everyone, and honest fixes failed the rule at both spam rates.
- **Spam on the testnet is not solved, and the launch says so.** Junk from free identities floods honest fixes once it exceeds the network's capacity (about 10 junk fixes an hour against 7 validators). Neither reputation-first ordering nor a newcomer lane fixes it for newcomers: the lane fails at every share tested. What would fix it is an identity that costs something (D32, #132 task 13.7). That is in tension with L17's freely mintable test coin, which makes identities and bonds free. Until 13.7 is decided, the launch relies on capacity for validators' wallets, D29's claim cap, and watching the queue; heavy spam is a known risk in the README and the paper.

### L17. The fee coin on Sepolia (decided by the owner on 2026-11-18: option 2, Circle's Sepolia USDC; changed from option 1 the same day)
- **Amounts on Sepolia (owner, 2026-11-18, from `reports/faucet-spam-v1.md`, #260):**
  - **Judges' fee: $40 in test USDC per submission** (two faucet requests), the top of the report's $20–40 range, because the owner's model budget for the launch validators is $30–50 a month. An honest newcomer's first fix costs two faucet requests.
  - **Validator bond: $250**, set at deploy, so a single judge's bounty limit is $125. $1,250 bonds aren't fundable from the faucet: 7 need about 438 requests and 15 about 938. The owner asks Circle on its Discord for more test USDC; a later deployment can raise the bond.
- **Decided: Circle's Sepolia USDC.** Bonds, pledges and the judges' fee (D30) are paid in it, so every submission costs USDC that only a rate-limited faucet hands out. This is the identity cost report v6's post hoc run found necessary against spam (D32): a mintable coin made identities and junk free.
- **Why not option 1 any more:** a keyless coin anyone can mint makes bonds and fees free, so spam from fresh identities is unbounded (report v6, "Post hoc: the newcomer lane").
- **The faucet's limits must be checked before relying on them** (task 3.15). Sources disagree: a secondary guide (Oct 2026) says Circle's public faucet gives 20 USDC every 2 hours per address and per chain, with no account; Circle's Developer Console faucet, a separate tool behind a developer account, lists 10–20 USDC a day. **A limit per address is weak:** addresses are free, so it costs a spammer only the faucet's own anti-abuse checks and time. An account-gated faucet costs more per identity. Task 3.15 measures which.
- **Trade-offs:**
  - a third party's contract and faucet: Circle can change the faucet, and USDC has an issuer blacklist. On a testnet that's acceptable; the paper names it, and a real-money deployment's coin choice is separate (#215's list of coins that can't be frozen);
  - the contracts take the coin's address as a constructor argument, as before: no code depends on USDC;
  - honest newcomers also need the faucet, so the guides (5.7) start with it.
- **Either way,** test coins deter nothing that costs real money, which the paper says (open problems 7.6). The `infrastructure` recipient goes to the sponsors' pool, not to any address of the owner (rule 3).

### L18. A release candidate: what goes on Sepolia is exactly what passed the devnet (owner, 2026-11-18)
- **The problem:** everything deployed on Sepolia is new code (the contract changes, the Radicle adapter, `pofctl` v3, the enclave keys, the test coin). The devnet differs from Sepolia in four ways: simulated attestations, windows in minutes, a fake judge and a private Radicle network. Without a rule, a last-minute change could ship untested.
- **The rule:** one tagged commit, the release candidate. Before the owner is asked for the Sepolia go (task 7.3):
  1. the v3 integration suite (#256) passes on that exact commit, `scripts/integration.sh --release-candidate <commit>`, 3 runs in a row from a clean state, including the Radicle scenarios, `pofctl` v3, the guides' commands (5.7) and `scripts/time-to-heal.sh`;
  2. one full bounty with the **production windows** (L4) passes on a local chain whose clock is moved forward (`evm_increaseTime`), not with minutes;
  3. **one real SEV-SNP validator** (#253) registers with a real attestation and judges a fix on the devnet;
  4. **one small real-model run** on the devnet: the model judges' prompts, costs and answer formats against the node, after a dry run with the fake judge, and with the owner's approval and a cost estimate before any paid call;
  5. the record of the run names the commit and the **bytecode hash** of every contract.
- **Enforced by the deploy script:** it compiles the commit, compares each contract's bytecode hash with the passing record, and refuses on any mismatch or a missing record. A change after the record means a new release candidate and a new run.
- **What it doesn't cover:** the public Radicle network and the owner's seed (checked by the deploy's dry run against the published repository, task 7.1), and Sepolia's own RPC and gas (checked by the dry run against a Sepolia endpoint, with nothing sent).

### L19. A panel that can't complete is released, never stuck (owner, 2026-11-18, from report v6)
- **The gap:** when a counted panel's judge stays silent and no eligible validator is left to replace it, the round never completes, and nothing releases it. In report v6's silence runs, 3–28% of a small target's fixes ended the year stuck, neither paid nor refunded. A launch network of 7–15 validators can reach this without any attacker, from ordinary outages.
- **The rule:**
  1. **Time-out:** a round whose replacements are exhausted ends at its reveal deadline plus `STUCK_GRACE`. The silent seats are slashed as today.
  2. **Back to waiting:** the submission returns to the waiting state, keeping its place, and is drawn again with a fresh seed when the eligible set grows or after `RETRY_DELAY`, whichever comes first.
  3. **Then refund:** after `MAX_REDRAWS` failed rounds, or at the bounty's deadline, the bounty is refunded to its funders. The solver's claim is released with no reputation loss and no slash, because the solver did nothing wrong.
- **Audits too (found by the Radicle spike, #261):** when an audit falls due and no eligible validator outside the panel is left, the verdict never becomes final, and the keeper's `drawAudits` keeps retrying. The same rule applies: after `STUCK_GRACE` the audit is released, the verdict waits for an audit to be drawable, and the bounty is refunded after `MAX_REDRAWS` or at its deadline.
- **Invariant:** every submission is, at every moment, in exactly one of these states: drawn with a live deadline, waiting with a scheduled redraw, final (paid or rejected), or refunded. No other state is reachable.
- **Values** (proposed, to confirm by #256's scenario d and the simulation): `STUCK_GRACE` 24 h, `RETRY_DELAY` 24 h, `MAX_REDRAWS` 3.

### Parameters
| Name | Value | Why | How it's tested |
|---|---|---|---|
| `REPO_ID` | `keccak256(RID)` of proof-of-fix on Radicle | #190's convention, used by `oracle/radicle.py` and `verify-head` | Foundry: other ids and zero refused |
| `LAUNCH_CHAIN_ID` | 11155111, plus 31337 and 7193 for local runs (L2 option 1) | the owner's decision, 2026-11-18 | Foundry `vm.chainId`: mainnet and others revert |
| Windows | L4's table, production values (decided) | L4 | Foundry with both columns; the devnet in minutes |
| `UNBONDING_MARGIN` | 7 days | #132's rule | derived-value test |
| `BOND_FLOOR` | $100, unchanged | #132 | L5's tests |
| `ACTIVE_SOLVERS_MIN` | 3 | report v5 | task 3.2's simulation |
| `ACTIVE_WINDOW` | 13 weeks, proposed | L6 | task 3.2: 6, 13, 26 weeks |
| `REP_BASE`, `REP_MULT`, `REP_LOSS_X` | $50, 1, 2 | #132 D29, report v5 | #132 tasks 12.3 and 12.5 |
| `JUDGE_FEE` | measured each period ($5.03 on report v5's base) | #132 D30 | #132 tasks 12.5 and 12.6 |
| `SECOND_PANEL` | as #132 task 11.2 records | D27 | #132 task 11.4 |
| `MAX_CHECKS_PER_HOUR`, `REPO_CHECKS_PER_HOUR` | 5; the repository cap off while there is one repository | L16, report v6 (post hoc lane run) | #256 scenario o |
| `STUCK_GRACE`, `RETRY_DELAY`, `MAX_REDRAWS` | 24 h, 24 h, 3 (proposed) | L19 | #256 scenario d; Foundry invariant |

## Risks / Trade-offs
- **[The checks bind only this deployment]** → stated in the record, the README and the paper. Nothing else is possible with open code.
- **[One party fakes three active solvers]** → bounded by D29's cap per identity and by disputes; measured by task 3.2. If the sybil of three gains, the owner chooses between a higher minimum, a longer window or a deposit while the repository is small (report v5's untested conditional deposit).
- **[The head waits for finality, so fixes queue]** → measured by `scripts/time-to-heal.sh`; fixes to different code don't conflict.
- **[Under (a), many offline validators stop `main`]** → readers follow `Heads.head` regardless (`verify-head`); the chain doesn't wait for Radicle.
- **[The owner's node is the genesis delegate]** → named in the record; under (a) it hands over at the first seats; under (b) it doesn't matter.
- **[Validators pay real model costs on play-money fees]** → #253's capacity and budget stop; the owner sets a monthly cap for their own validators.
- **[Test coins make the economics untestable]** → the testnet tests the flow, not the incentives; the paper says so (7.6).
- **[Local chain ids accepted by the constructor (L2 option 1)]** → the deploy script refuses them for any non-local endpoint.
- **[The contracts aren't audited]** (open problems 7.5) → known findings (`drawAudits` repeat calls, the receipt without a seat) are fixed before the deploy (task 3.10); an audit is not in scope, and the README says so.
- **[No lawyer's review]** → the owner decided against one on 2026-11-18 ("no legal check"); the intended-use section and the wording check remain.

## Migration Plan
1. Gates and decisions (group 1), in parallel with the Radicle spike (group 2) and the simulation of the minimum (task 3.2).
2. Contracts (group 3), then node, pofctl and Radicle bounties (group 4), all on the local devnet first: `scripts/integration.sh --version 3 --radicle`.
3. Scrub and publication prep (group 5).
4. **Owner's go:** publish on Radicle (group 6).
5. **Owner's go:** deploy on Sepolia (group 7), the record entering through the first fix (L15).
6. Launch validators and onboarding (group 8), the paper (group 9).

**Rollback:** keyless, so there is none on-chain. A broken deployment is abandoned and a new one deployed with a new record (D15); the Radicle repository keeps its history, and its README names the deployment in force.

## Open Questions
Decided by the owner on 2026-11-18 ("proceed with recommendations"): L2 option 1, L4 production values, and the three safety items in `public-release`. L17: option 1 at first, then option 2 (Circle's Sepolia USDC) the same day, after report v6's post hoc run.

These don't change the approach; each waits for the owner or for a measurement.
- L6: `ACTIVE_WINDOW`'s value, after task 3.2.
- L14: who hosts the seed, and whether to ask public seeds to replicate.
- L16: who runs the launch validators and their model budget.
- #158's gates: closed on 2026-11-18 (publish without contact; "MIT OR Apache-2.0"; no company behind the code, so no IP note).
