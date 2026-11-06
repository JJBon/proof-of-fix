# Proposal

## Why

Popular, fast-growing open-source apps run out of review, not code. In the GridCraft sample (it-ops#14, comment 3323):
- 4 maintainers merged all 40 recent PRs;
- only about a quarter had a human review;
- 526 PRs are open against 136 merged a week;
- the oldest open PRs (median 1,098 lines) sit unreviewed for days.

AI makes PRs cheap to produce, so paying per PR would attract spam. We need a mechanism that pays for changes that **hold up**, makes checking them worth someone's time, and refunds the upstream author and the infrastructure from every release. The mechanism must be specified and tested in simulation before anything real exists (ticket: it-ops#14).

## What Changes

- **Contribution lifecycle:** a contributor stakes on a PR, which is merged optimistically into a beta build with its payment held in escrow. A challenge window follows, and the PR then settles: paid and refunded, or slashed.
- **Challenges:**
  - a staked challenger proves a regression with objective evidence: a test that passes before the PR, fails after it, and bisects to it; for GridCraft, a formula result checked against a reference implementation;
  - judgement in layers: deterministic checks, then AI review (a first pass, never final on a slash), then human jurors on appeal;
  - slashing scaled and capped; challengers stake too.
- **Validator selection:** validators are drawn at random, weighted by stake; verdicts use commit-reveal voting.
- **Release payouts:** each release's funds are split by fixed, published shares among contributors, validators and reviewers, the upstream author's escrow, infrastructure, an insurance pool, and the owner.
  - The author's escrow is claimable only with a verifiable proof.
  - The owner's share is capped, vested and carries no discretion.
- **Stakes scale with PR size and risk:** small PRs are cheap; very large ones need a bigger stake and more validators.
- **Simulated ledger:** an append-only, value-conserving ledger in simulated credits. No real chain, tokens, wallets or money.
- **Incentive simulation:** an agent-based simulation with these actors:
  - honest contributors;
  - PR spammers;
  - griefing challengers;
  - colluding validators;
  - a self-interested owner;
  - a replay of real, aggregated GridCraft PR history.

  It reports whether honesty pays and attacks don't, under named parameters.

Out of scope:
- a real chain, tokens, wallets or money;
- hosting on Radicle or IPFS;
- pull requests to the upstream project, and contacting its maintainers about this project (bug reports follow rule 1 in `openspec/config.yaml`);
- building and running GridCraft's own code (a later change, in containers);
- choosing a chain or a legal entity.

## Capabilities

### New Capabilities
- `contribution-lifecycle`: a PR from stake to settlement: entry stake, beta build, escrow, challenge window, settlement outcomes.
- `challenges`: what counts as proof, who may challenge, validator selection, commit-reveal verdicts, judgement layers and appeals, and slashing rules.
- `release-payouts`: how each release's funds are split, and how the author's escrow, the owner's share and the insurance pool behave.
- `ledger`: the simulated ledger. Accounts, append-only entries, conservation of value, and audit of every settlement.
- `incentive-simulation`: actors, scenarios, the replay of real history, metrics, and the acceptance criteria the mechanism must meet.

### Modified Capabilities
- None (first change in this repository).

**Actors and attacks affected:**
- Actors: contributors, challengers and validators, maintainers, the upstream author, the owner, the treasury.
- Attacks covered: PR spam, griefing challenges, validator collusion, sybil identities, prompt injection against the AI review, and owner self-dealing.

## Impact

- **New code in this repository:** a mechanism library and its simulation in Python (standard library only, so the `pof / check` CI runs it without installs). Tests run in `scripts/check.sh`.
- **Data:** aggregated statistics of GridCraft's public PR history (sizes, review counts, merge times), with no per-person data.
- **No change to any other repository or system.** Nothing is deployed.
