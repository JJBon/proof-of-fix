# Proposal

Ticket: proof-of-fix#251. Builds on #132 (open validators, v3), #190 and #201 (Radicle), #158 (the gates before going public), #215 (the Radicle-under-v3 item and the threat model), #236 and #250 (D20–D30), #248 (v3 on a local devnet) and ADR 0003. Depends on #252 (repository choice) and #253 (validator kit and capacity), both simulated on other branches.

## Why

The owner decided on 2026-11-17: *"lets go full public deployment with radicle and testnet. let focus for now on only using proof of fix"*, and, in #251's comment, *"limit contract to only work for proof of fix and deploy it on a testnet (that way i can promote the repo, don't be concerned of people using the code a way that is not intended and focus on getting feedback)"*.

So proof-of-fix publishes its own code on Radicle, under the owner's real name, and runs v3 on Sepolia with proof-of-fix as its only repository. Its own issues are funded and fixed through its own contracts: it heals itself (#85). v3 today is built and runs on a local devnet (#248), but it isn't ready for a public chain: its windows are constants, a validator below the bond floor stops being drawn without saying so, it accepts any number of repositories on any chain, its head moves before a verdict is final, the deposit-free rules decided in #250 aren't in it, and #201's Radicle adapter only works with v2's fixed seats.

## What Changes

**The deployment is bound to proof-of-fix and to Sepolia** (new: `deployment-binding`):
- The contracts take proof-of-fix's Radicle repository id, `keccak256(RID)`, as an immutable constructor argument and refuse issues and bounties for any other repository. The Radicle repository exists before the deploy, and its `main` at that moment is the genesis head.
- The constructor refuses to deploy unless `block.chainid` is Sepolia (11155111); the deploy script refuses mainnet and any chain but Sepolia. (Local test chains: design L2, a question for the owner.)
- **These checks bind this deployment, not the open code.** Anyone can fork the code and remove them; the README and the paper say so plainly.
- The waiting windows (seal, reveal, challenge per panel size and level) become constructor parameters, checked for order and recorded in the deployment record, instead of constants. Nothing can change them after deployment.
- Only TEE proof types (levels A and B) are accepted, at genesis and by any later ADR: no level C (zkTLS) in this deployment.

**Contract rules before Sepolia** (modified: `validator-admission`, `reputation`, `bounty-market`; new: `canonical-head`):
- A validator whose bond falls below the floor is visibly inactive (an event, and a state the registry reports), not counted as active, and can top up or leave. No silent stuck state.
- D27 (one seated family closes its own challenges with its own second draw), the reputation cap D29 with a reversal taking 2 × its bounty off, and the judges' fee D30, as decided in #250. D27's spec text stays in #132's `judge-panels`; D29 and D30 are specified here.
- No pledges are taken while proof-of-fix has fewer than 3 active solvers, with "active" defined on-chain (design L6).
- `Heads` and the merge wired into v3: the head moves only when the winning verdict is final, so a verdict reversed in its window never reaches the canonical head.

**Code on Radicle** (new: `radicle-hosting`):
- The public repository starts from the scrubbed snapshot, never Forgejo's history.
- Funding refers to a Radicle issue; a fix is a Radicle patch; the validator fetches the patch's commit from Radicle; issues are funded straight from `pofctl` (a bot adapter is optional).
- The seed replicates proof-of-fix only (selective seeding). Hosting is the owner's decision; no host is started without asking.
- **How the canonical `main` follows v3's changing panels is the open design problem.** A spike decides between (a) the seated validators as delegates, following the seats on-chain, with a `verify-delegates` check; (b) the chain as the only truth, readers following `Heads.head` with `pofctl verify-head`; (c) one merge key held only inside approved enclaves. Recommended: (a), with (b) as the check anyone runs. The spike decides.

**Public steps behind gates** (new: `public-release`):
- Publishing on Radicle and deploying on Sepolia each need the owner's explicit go at that moment, recorded in the tasks.
- **Proposed, awaiting the owner:** a README "intended use" section (research; a single-repository testnet; other deployments are their operators' responsibility), a wording check of the README and the paper, and a lawyer's review as a gate before publishing and before deploying.

## Capabilities

### New Capabilities
- `deployment-binding`: what binds one deployment of the contracts: the single repository, the chain, the windows and the accepted proof types, all fixed at construction.
- `canonical-head`: how a repository's head on-chain moves in v3 and how anyone checks a copy of the code against it.
- `radicle-hosting`: proof-of-fix's code on Radicle: publishing, seeding, issues and patches as the bounty's references, and who may move the canonical `main`.
- `public-release`: the gates before any public step: the scrub, the owner's go, and the proposed wording and legal checks.

### Modified Capabilities
- `validator-admission` (created by #132, not yet archived): a validator below the bond floor is visibly inactive.
- `reputation`: open claims capped by reputation, and a reversal's cost (D29).
- `bounty-market`: the judges' fee per submission (D30), and no pledges before 3 active solvers.

## Out of scope
- Any other repository: practice repositories, the friends' test on GitHub, #215's shadow forks. Repository choice by validators is #252; this deployment needs none.
- Validator capacity and the per-repository rate limit (#253): referenced as a dependency; their values come from #253's simulation.
- Level C (zkTLS), mainnet, real money, tokens (#142), the legal wrapper (#126), the pot by impact (#247).
- Hosting itself: which seed and which validator hosts run, and their budget, are the owner's decisions; this change only says what they must do.
- The anonymity plan of #215 (separate account, hidden IP, deleted founder key): replaced by publishing under the owner's name. Fixers stay anonymous by default.
- Editing `openspec/changes/proof-of-fix-132-open-validators/`: its decisions are referenced by D-number.

## Exceptions to the project rules
- **Rule 1 (everything simulated, no public posts).** Exception for this change, decided by the owner on 2026-11-15 and 2026-11-17: the code is published on Radicle, and v3 runs on Sepolia, a public test chain. Its coin is a test coin with no value: no real money, no mainnet, no tokens. Each public step needs the owner's go at that moment (`public-release`).
- **Rule 5 (no personal data in the repository).** Exception: the owner's real name as the author of the code and the paper, by their decision. Collaborators' names, the company domain, AWS ids and ERP or platform references are still removed (#158's list).
- **The PoC's upstream target** (storytold/gridcraft) isn't a repository of this deployment. Rule 2 still applies to anything taken from it; the Ridges/storytold decision is a #158 gate, recorded before publishing (task 1.1).

## Actors, incentives and attacks affected
- **Solvers:** the 3-active-solver minimum can be met by one party with three identities (design L6: a named trust point, bounded by D29's cap). The reputation cap and the judges' fee change what every attempt costs.
- **Validators:** the bond-floor state; the TEE-only rule; real model costs paid against play-money fees, so spam is real (#253's capacity is the brake).
- **Delegates or merge-key holders on Radicle:** a colluding majority (a), anyone (b), or a broken enclave (c) could move `main` away from `Heads.head`; the spike measures each, and `verify-head` detects it for anyone.
- **Funders:** play money only; the testnet tests the flow, not the economics (the paper says so).
- **The owner:** named publicly; may run one validator under the same rules (#132); no key, seat, vote or payout discretion over the contracts. Any recipient of fees they control on Sepolia is disclosed in the deployment record (rule 3).
- **Forks:** anyone may deploy the open code elsewhere without the checks. That is outside this deployment, and the intended-use section (proposed) says whose responsibility it is.

## Impact
- **Contracts:** `RaceV3`, `RaceV3Annex`, `RaceV3Base`, `Panels*`, `Validators`, `FeesV3`, `Heads` (v2's, reused or a v3 copy), a new Sepolia deploy script. v2 is untouched.
- **Node and tools:** `oracle/radicle.py` and `oracle/node_v3.py` (a v3 Radicle adapter), `pofctl` (v3 and Radicle; it speaks only v2 today), `scripts/github_snapshot.py` (a Radicle target), `scripts/radicle-spike.sh` (the v3 spike), the integration suite's `--radicle` run on v3.
- **Docs:** README (intended use, proposed), the paper, `docs/participate.md`, three onboarding guides, a deployment record under `contracts/deployments/`.
- **External, each behind the owner's go:** a Radicle repository and a seed; a Sepolia deployment from a fresh wallet funded by a faucet.
