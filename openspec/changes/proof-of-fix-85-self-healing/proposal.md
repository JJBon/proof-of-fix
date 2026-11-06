# Proposal

Ticket: proof-of-fix#85. The plan before a testnet is #82; the business model is #82, comment 4391.

## Why

The owner's decision, 2026-10-30: **the primary goal is self-healing decentralized code; funding fixes is secondary.** In the owner's words: "No one controls the code, not even maintainers (AI is for that)." Constitution checks need 7 judges and issues 3, and the constitution "can only change with a solid ADR".

The race already pays a fix on merge with no admin key (#56). But two points of control remain:
- someone still holds the merge right on the git host;
- nothing stops a passing fix from wearing down the project's rules over time.

This change closes both. It defines:
- a canonical head recorded on-chain;
- two tiers of AI judges;
- a constitution that changes only through ADRs.

#84, where maintainers kept the merge, is superseded.

## What Changes

**Governance:**
- **No human merge** in a self-governed repository, the owner's and any maintainer's included. The canonical code changes only by the judges' verdicts, recorded on-chain.
- **A canonical head on-chain.** Each passing fix is recorded bound to the base commit it was checked on. A bot that anyone can run applies the head to the git mirrors, and a mirror that differs from it is simply wrong.
- **Two tiers of judges:**
  - **issue tier:** 3 judges drawn from 7 registered operators, 2 to pass;
  - **constitution tier:** all 7, 5 to pass.
  - Each judge is a different model family run by a different, independent operator. The owner runs at most one judge and recuses as a party.
- **Escalation to the constitution tier** when a fix touches a protected path, when any issue judge flags it, or when someone challenges the verdict with a stake.
- **A constitution** (`CONSTITUTION.md`) that changes only through an ADR:
  - the ADR passes 5 of 7, then a 14-day public challenge window;
  - **entrenched articles** (no human control, the judges' counts and thresholds, the amendment procedure) change only by a new version that users choose to follow (D15).
- **The first constitution and ADRs,** in this change:
  - a DRAFT `CONSTITUTION.md` for proof-of-fix itself, effective only at genesis;
  - `docs/adr/0000-template.md`;
  - `docs/adr/0001-self-healing-constitution.md`.

**Self-healing:**
- **System-registered issues:** failing tests on the head, dependency advisories and regressions. Anyone with evidence registers them, the sponsors' pool pays the registration, and the reporter's share goes to the pool.
- **The sponsors' pool:** anyone funds it, and fixed rules spend it.

**Money:**
- **No token emission at launch (BREAKING for #58's plan):**
  - the token is parked, not deleted;
  - `Token.sol` and the migration (D15, #83) stay;
  - it can be enabled only by a new version that holders choose.
- **A 0 % protocol fee,** as D9 already has on-chain.
- **Judges are paid only by check fees:**
  - the reporter's registration fee pays the registration check;
  - the solver's deposit pays its attempt's checks;
  - **the winner's checks are refunded from the bounty at merge** (**BREAKING** for "Checks paid by the contributor", #49);
  - an ADR's author pays the constitution tier, refunded from the pool if the ADR takes effect.

**The oracle network on-chain** (added 2026-11-01, after #93's devnet and #94's node; refs #92, #93, #94):
- **The verdict v2** binds the base commit it was checked on (closing #93's gap 1) and the hash of a **receipt** (the exact model, prompt and response hashes, checker image, test results, measured usage, attestation), stored content-addressed and encoded as **COSE_Sign1** after the IETF draft *Attested Inference Receipt* (-02). Allowed model versions per family are a constitution rule.
- **Attestation and infrastructure:** the constitution lists the accepted TEE types (AWS Nitro; Intel TDX through Phala dstack or self-hosted; AMD SEV-SNP) and one reproducible official checker image; each operator chooses its own infrastructure within that. **Counted judges call model providers directly from inside the TEE;** no proxy or gateway sits in the path of a counted verdict.
- **Sealed verdicts on-chain:** judges seal, then reveal; a missed reveal costs a share of the bond and hands the seat to the next in the draw.
- **Seats fixed per version** (operator, model family, provider), **at most 2 per provider.** A seat's **key** may rotate only to an attested key for an allowed checker image, co-signed by the seat's key and 5 of the other 6, after 7 days. Operators change only in a new version (D15).
- **Check fees** (the owner's decision, 2026-11-01): **the check's costs passed through at public unit prices** (tokens per family, sandbox vCPU-seconds and GB-seconds, storage), on the median of the judges' measured usage and within per-check caps from the constitution and each repository's **CI profile**, **plus one agreed `SERVICE_FEE` per check, the same for every seat.** No per-seat fees. The table and the fee change only by 5 of 7, ±25 % per update, after 7 days, citing providers' public prices and open to staked challenges; **each entry never above 2× its genesis value, `SERVICE_FEE` = $0.05 never above its $0.25 cap** (both caps in the constitution). Gas is reimbursed at cost. The solver deposits the maximum and is refunded the rest. Optionally, one attested CI run verified by the other judges. Governance of these numbers: #100.
- **Bonds, slashed only for provable faults** (conflicting signatures, a mismatched or missing reveal, failing to serve code, a bad receipt at 20 %), **at least 2 × the version's `BOUNTY_MAX`.** Seats are chosen for independence and reseated by their public record (#100). **Canaries stay off-chain** on a public scoreboard in this version.
- **Data availability (#92):** the head moves only when 5 of 7 seats sign they hold the fix's code, plus a permanent copy's receipt. Radicle carries public repositories only, until its September 2026 flaws are fixed.
- **The deployment record** lists every contract's and linked library's code hash (closing #93's gap 2).

**Outside projects:**
- **Verified fixes, offered upstream:** for projects with human maintainers, a bounty pays on the judges' verdict and the winning fix is offered as one pull request, which they merge or not. Attempts are never opened upstream.

**Openspec rules:**
- **Rule 1** holds with no exception. Everything here is specified for the local chain and the simulation. Nothing is deployed, no real operator or money is involved, and nothing is posted.
- **Rule 2:** outside projects are never forced, and fixes are offered back upstream.
- **Rule 3, the owner's benefit:**
  - at most one judge seat, paid check fees like any operator, with recusal;
  - no founder's share, since the token is parked;
  - a 0 % fee;
  - writing the genesis constitution is a disclosed, one-time act.

**Out of scope:**
- real judge operators;
- any testnet or mainnet deployment;
- real money;
- onboarding outside projects;
- the measurement and simulation work themselves (B1, B2), which are tasks here;
- the legal review (#82, D6).

**Actors, incentives and attacks affected:**
- **Maintainers** lose the merge in self-governed repositories.
- **Solvers** gain the winner's check refund.
- **Judges** gain a constitution tier.
- **New attackers to simulate:**
  - a solver who games tests;
  - a prompt injector;
  - operators colluding below and at the quorums;
  - an ADR capturer;
  - a watcher farming system issues;
  - a judge that doesn't reveal, an equivocator, a judge padding its usage, a seat withholding code, and seats colluding to raise the price table.
- **Operators** post bonds, are paid by check gas, and can be slashed for provable faults.
- **Solvers** see their check deposit's maximum before attempting.

## Capabilities

### New Capabilities
- `constitution`: the project's constitution, amendment by ADR, entrenched articles, escalation to the constitution tier, and the genesis constitution.
- `self-healing`: no human merge, the canonical head on-chain, mirrors following it, data availability before the head moves, system-registered issues, the sponsors' pool, and verified fixes offered upstream.
- `oracle-network`: the verdict v2's signed fields, sealed verdicts on-chain, seats and key rotation, the provider cap, receipts, check gas, bonds and provable faults, canaries on a scoreboard, and the deployment record.

### Modified Capabilities
- `checking`:
  - two tiers of judges;
  - one model family and one operator per judge;
  - the owner's single, recused seat;
  - the project's constitution as the reference for checks.
- `bounty-market`:
  - the winner's checks refunded at merge;
  - checks charged on measured usage at public unit prices plus one agreed service fee, within per-check caps and each repository's CI profile;
  - coin only and no protocol fee at launch.
- `contribution-lifecycle`: maintainers keep the merge only in projects that have them; a self-governed repository has none.
- `incentive-simulation`: the self-healing and oracle-network scenarios, and their acceptance criteria.

## Impact

- **Docs, in this change:** `CONSTITUTION.md` (DRAFT), and `docs/adr/0000-template.md` and `0001-self-healing-constitution.md`.
- **Later tasks:**
  - **measurement:** judges' accuracy, agreement between model families, prompt injection;
  - **costs:** per check, with 3 judges and with 7;
  - **the simulation:** new actors and criteria in `pof/`.
- **Contracts v2, local only:**
  - the head registry;
  - the tiers;
  - the constitution's hash and the ADR lifecycle;
  - the sponsors' pool;
  - no token;
  - the Race split under EIP-170, folded into v2;
  - migration from v1.
- **The bot** (`bot/`): applies the head to mirrors, and registers system issues.
