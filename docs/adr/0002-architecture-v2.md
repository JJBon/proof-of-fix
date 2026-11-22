# ADR 0002: The v2 architecture: keyless coin-only contracts, a drawn quorum of seats, metered check fees, and validators that run on demand

- **Status:** in effect for the private devnet (recorded at genesis by the owner, like ADR 0001; no constitution tier exists yet to pass it). Not superseded: v2 stays deployed as described here. Its successor, v3, is built beside it and not deployed (see "Successors").
- **Date:** 2026-11-02
- **Author:** the owner (proof-of-fix#114). Interest disclosed: the owner may run one validator seat, recused on any bounty they're party to; no founder's share and no token (parked).
- **Constitution articles changed:** none. This records how the DRAFT constitution's articles are built.
- **Protected paths touched:** `docs/adr/0002-architecture-v2.md`

## Problem
The design grew over many issues and PRs: #56 (the race), #58 (the token), #85 (self-healing, v2), #94 (the oracle node), #101/#105 (fees and bonds), #104 (the engineers' demo), #112 (the owner's seats), and infra#197–#200 (the devnet). There was no single record of **what the system is now:** which contracts exist, what they hold and call, where the AI checks run, who pays whom, and how a new validator joins. Newcomers, including the engineers invited to the demo, need that in one place, with an honest list of what's built and what isn't.

## Options
1. **Keep the record spread over issues, specs and reports:** nothing to write, but nobody can see the whole, and decisions get re-argued.
2. **Record the architecture as built, with its status, in one ADR, plus diagrams in the README:** a little writing, kept current by each PR that changes the architecture.

## Decision
Option 2. The architecture, and each part's status: **built** (on `main`), **#113** (pending merge), or **to build** (with its issue or task).

### 1. Contracts: keyless and coin-only (v2)
| Contract | Holds and does | Status |
|---|---|---|
| `RaceV2` (+ `RaceV2Base`) | the race: issues, bounties, pledges in the fee coin, attempts, sealed submissions, results, merges, instalments, settlement, refunds; delegates rarely used actions to its annex | built (#103, #107, #109, #111) |
| `RaceV2Annex` | appeals, `junk`, `refuseSimilar`, `withdrawIssue`, `timeOut`, `mergeExpired`, `challengeUpheld`; runs in `RaceV2`'s storage by DELEGATECALL; address fixed at deployment | built (#109) |
| `Verdicts` | the **7 seats** (operator, model family, provider), each seat's key; the **draw of 3 of 7** by the submission's seed, 2 to pass; **recusal** of a party's seat; the constitution tier (5 of 7); **joining** a vacant seat and **rotating** a key (co-signed by the seat and 5 others, after 7 days); suspension | built (#109) |
| `Fees` (the meter) | the **unit price table** (tokens per model family; sandbox vCPU- and GB-seconds; storage; ETH for gas); the **$0.05 service fee** (cap $0.25); caps per check and the repository's CI profile; the solver's **maximum deposit**; the **median** of the drawn judges' signed usage; each judge paid to its seat; the relayer's gas repaid; the rest refunded; bounded (±25 %, ≤ 2× genesis), delayed (7 days) price updates by 5 of 7 | built (#111); the price challenge waits for bonds (5.8) |
| `Heads` | each registered repository's canonical head; it moves only on a merge verdict whose base is the head | built (#107) |
| `Pool` | the sponsors' pool: funded by anyone, no owner, no withdraw | built (#103); its spending (5.11) to build |
| `QuoterV2` | the quote: price, instalments, finder's fee, attempt fee, the check deposit, the service fee | built (#103, #111) |
| v1 (`Race`, `Token`, `Quoter`, `OracleAuth`) | kept, untouched; its bounties finish in v1 | built (#56, #96) |

- **No owner, admin, upgrade or pause.** Rules change only by a new version and a migration (D15). Changing seats or prices follows the rules above.
- **Coin only:** the token (`Token`, POF) is built but **parked** (owner, 2026-10-30). v2 makes no token calls, and validators are paid in the fee coin, never in POF.
- **Sizes** (runtime, EIP-170 limit 24,576): `RaceV2` 23,628, `RaceV2Annex` 17,598, `Fees` 11,754, `Verdicts` 7,321, `QuoterV2` 3,157, `Pool` 1,398, `Heads` 1,091. `RaceV2`'s initcode is 47,886 of 49,152 (EIP-3860), so new logic goes into other contracts ([`reports/contract-v2.md`](../../reports/contract-v2.md)).
- **Built in v3, not in v2** (design D18 of #132; see "Successors"): sealed verdicts on-chain (5.5), receipts on-chain (5.6), and bonds, slashing and challenges (5.8). v2 stays without them.
- **To build (#85 tasks):** data availability (5.9), the constitution's hash and ADR challenges (5.10), the pool's spending (5.11), the deployment record's library hashes (5.12), the migration from v1 (5.13), the replay with fees (5.14).

### 2. The chain: a private devnet with mainnet rules
- **Built:** `https://devnet.example.com` (infra#199, #200), chain **7193**, Osaka, EIP-170 enforced, a block every 2 s.
  - It runs on a t4g.small in the **platform account**, isolated by its own security group (port 443 only) and a minimal IAM role, with no dedicated VPC and no separate account (owner, 2026-11-02).
  - Caddy terminates TLS (Let's Encrypt), and **each engineer has an API key** (HTTP basic auth, keys in OpenBao, only hashes on the host).
  - Daily snapshots; stopped 01:00–09:00 America/Bogota like the other hosts; about $15 a month.
- **Not decided yet:** a public testnet or mainnet (after D1, going public).

### 3. The validation infrastructure: AI checks, run on demand
- **The oracle node** (`oracle/`): fetches the fix, runs its tests in a sandbox (pinned image, no network), asks its judge, signs its usage report and its verdict, and relays them.
  - Built: v1 mode (#95, #99).
  - **#113:** v2 mode, acting only when `Verdicts.drawn` names its key; usage reports; fee withdrawal; `run --until-idle`.
- **The validator kit** (`validator-kit/`, #106): a Terraform module **each validator applies in their own AWS account.**
  - A **watcher Lambda** polls the chain every minute. A chain can't push events into AWS, so a cheap poll is the standard pattern.
  - It **starts a stopped EC2 node only when there's work for that seat;** the node checks, then **powers itself off.**
  - The signing key lives in the validator's own Secrets Manager. Model access is the validator's own (Bedrock or an API key). There's a budget alarm and a kill switch.
  - Idle cost is about $2–3 a month; a run costs about $0.005.
  - **#113** makes the watcher use the draw.
- **Judges, the target** (#85 S13/S14, #101): each seat a different model family; **counted judges call providers directly** from a TEE (Phala dstack or AWS Nitro), with **attested receipts** (IETF draft "Attested Inference Receipt", COSE_Sign1). **To build:** attestation (#94 phase 2), direct calls, receipts on-chain (5.6).

### 4. Where the code lives
- **The demo's target repositories are on GitHub** (free, easy to inspect), read through `bot/github.py`, with Forgejo or GitHub chosen per repository (#108).
- proof-of-fix itself stays private on Forgejo.
- Radicle is the long-term storage and transport for public repositories, **not for private ones** (Radicle's September 2026 flaws; #92).

### 5. Who pays whom
- **Funders** pledge to bounties in the fee coin.
- **The winner** is paid in instalments, and **the reporter** gets 15 % (the finder's fee).
- **Solvers** pay an attempt fee and a check deposit. Their checks are charged by the meter, the rest is refunded, and the winner's checks are refunded from the bounty.
- **Validators** earn, for each counted check, their **measured usage at the price table plus the $0.05 service fee**, pulled with `withdraw`.
- **The relayer's** gas is repaid. No protocol fee is taken. The owner earns as a validator and from services, not from bounties (#82).

## Evidence
- **Contracts:** 284 contract tests pass. The v1 and v2 replays match the simulation to the micro-credit on 13 seeds. An invariant checks that the credits always add up to the deposit ([`reports/contract-v2.md`](../../reports/contract-v2.md)).
- **The devnet:** with mainnet rules, it refuses a 24,577-byte contract. The 11 oracle-path scenarios pass ([`reports/devnet-v1.md`](../../reports/devnet-v1.md)).
- **Nodes:** five independent nodes, quorum 3: a forged relay refused, a bad fix failed by all, a good fix passed with its dissent logged, canaries scoring a lying node 0 % ([`reports/oracle-v2.md`](../../reports/oracle-v2.md)).
- **The demo end to end (#113):** a new engineer's key joins a vacant seat; only the 3 drawn of 7 real nodes act; fees are charged, refunded and withdrawn exactly.
- **Economics:** the $0.05 service fee, and bonds at 2× the largest bounty ([`reports/self-healing-v1.md`](../../reports/self-healing-v1.md)); running costs ([`reports/costs-v1.md`](../../reports/costs-v1.md)).

## Consequences
- **Engineers** can take part with only an API key and their own AWS account: apply the kit, join a seat, and get paid by the contract when drawn ([`docs/participate.md`](../participate.md)).
- **Nobody can change a rule unilaterally,** the owner included. A mistake means a new version and a migration, so changes are slower.
- **Until attestation and receipts are built,** a counted verdict is trusted on its seat's key alone. Several model families, canaries and the draw are the safeguards, and they're enough only for the devnet.
- **The architecture changes through ADRs:** a PR that changes it updates this ADR or supersedes it.

## Successors
This ADR describes v2, which stays deployed and unchanged (D15). Two later ADRs build on it.

- **[ADR 0003](0003-decentralization.md)** sets the target: nothing one party runs is required. It is proposed, and the devnet still runs as described here.
- **[ADR 0004](0004-open-validators.md)** fixes the parameters of **v3, open validators** (#132). v3's contracts are built and tested in `contracts/src/v3/` ([`reports/contract-v3.md`](../../reports/contract-v3.md)). They are not deployed: the node and the kit still speak v2 (#139), and the devnet run is #140.

What v3 replaces in this ADR:

| Here (v2) | In v3 | Section |
|---|---|---|
| `Verdicts`: 7 seats, joined by co-signature | `Validators`, **the open registry.** Anyone registers a key with a bond of at least $100 and an attestation, qualifies with 20 scored shadow verdicts (95 % revealed, 80 % agreement), and leaves after an unbonding delay of 504 h. Nobody approves or co-signs. At most one genesis validator, at level A or B. | 1, 3 |
| The draw of 3 of 7, 2 to pass | `Panels`, **the k table.** k is odd, from 1 to 7, the largest the eligible validators allow, and the bounty must fit that k's limit: at level A $50 at k = 1, $250 at k = 3, $625 at k = 5 and 7; level B half of that. A bounty above the limit waits. Caps per panel: 1 per operator, and from k = 3 no majority of one host or one model family. | 1 |
| The challenge window | A window per (k, level): at level A 168 h at k = 1, 24 h at k = 3, 12 h at k = 5, 6 h at k = 7; level B twice that. A challenge is judged by a fresh, larger panel (1→3, 3→5, 5→7, 7→7), and the window is frozen until it decides. | 1 |
| No counterpart: v2 never draws one judge | **The k = 1 hold.** A lone judge's verdict isn't final, and its bounty isn't paid, until 3 validators could judge its challenge. Only then does its window run. Two auditors outside the panel re-run every k = 1 verdict, and a validator has at most 10 k = 1 verdicts pending. | 1 |
| Seals and reveals through the relay; receipts and bonds to build (5.5, 5.6, 5.8) | On-chain in `Panels` and `Validators` (D18): seals, reveals, receipt hashes, bonds and slashes for provable faults only. Attestation is a recorded hash that the drawn panel checks off-chain, with a `simulated` proof type on devnet chain ids only. | 1, 3 |
| `Fees`: a price table changed by 5 of 7 seats | `FeesV3`: active validators post tables, the lower median moves each price by at most 25 % a day, and a queue signal moves the service fee between $0.01 and $0.25. No vote. | 1, 5 |
| A model family per seat, listed at deployment | No list of families (D19). `PanelScores` keeps a score per family, which ranks it: the score scales the service fee, and a family below 70 % isn't drawn until it recovers. The rank and the per-family cap are under review in #236, after the judge measurements ([`reports/judges-v2.md`](../../reports/judges-v2.md)). | 3 |
| `RaceV2`, `RaceV2Annex`, `Pool` | `RaceV3`, `RaceV3Annex`, `PoolV3`: the same race, judged by `Panels` and charged by `FeesV3`, with instalments counted from the verdict's finality. `Heads` is reused. | 1, 5 |
| The constitution tier: 5 of 7 seats | 7 drawn, 5 to pass, from at least 21 eligible validators for an ADR that adds or loosens and 14 for one that only removes. `RaceV3` doesn't open ADRs or escalated fixes yet. | 1 |

What stays the same: no owner, admin, upgrade or pause; the fee coin only; v2 and its bounties, which finish in v2. The diagrams of both versions are in the [README](../../README.md).

## Challenge window
None: this is recorded at genesis, before any constitution tier exists. From genesis on, ADRs follow Article 9.
