# On-chain groundwork: contract, fees, chain, storage, legal (proof-of-fix#44)

**Status:** desk study, written 2026-10-25 at the owner's request. **Nothing here is deployed or to be deployed.** proof-of-fix is simulation only and under wraps:
- no wallets, testnets, accounts or contact with any project;
- prototypes, if any, run on local chains in containers.

Facts about chains and services change fast. Every one below should be **verified against the primary source before any choice**. The legal section is a list of questions for counsel, not advice.

The mechanism this is for passes every acceptance criterion in simulation (checking v5, proof-of-fix#49). Going live still needs the four items on #15's checklist: model accuracy, identity, the oracle provider and the legal review.

## 1. What goes on-chain, and what stays off

The rule of thumb: **on-chain holds money and commitments; off-chain does the work and the judging**, and posts signed results that the contract verifies.

| On-chain (the contract) | Off-chain (posting signed results on-chain) |
|---|---|
| Bounty escrow (pledges in a stablecoin), its target, deadline and refunds | The issue text and its public failing test (in git), referenced on-chain by hash |
| The **hash of the hidden tests**, fixed when the bounty opens, so they can't be changed later | The hidden tests themselves, encrypted to the attested runners' enclave keys |
| Sealed bids: commit hash, reveal, the second price, the reserve | Building the fix (the solver's own machine) |
| Stakes, bonds and **check deposits**, with their release, forfeit and slash rules | **CI:** attested runners (MCP test runners in TEEs) run the tests and sign `(delivery hash, result, enclave attestation)` |
| The oracle registry: runners and evaluators, their operators, declared models, bonds and scores | **Judging:** AI evaluators' sealed verdicts (commit, reveal), each with its evidence hash |
| Verifying signatures and attestations from registered oracles, the quorum, consensus and the second jury | Evidence and logs (content-addressed storage, by hash) |
| Payouts: the price in instalments, a clawback window, the market fee split, the finder's fee | The planted-case pool, prepared by the system |
| The challenge window (optimistic): a challenge with a proof hash, then its resolution | Re-running a challenge's proof (attested runners again) |
| Published parameters, versioned, with changes behind a time lock | Reputation can be computed off-chain from on-chain events, or kept on-chain (non-transferable) |

**How the contract trusts an oracle:**
- each runner and evaluator registers a signing key and posts a bond;
- a CI result counts only with the enclave's attestation (vendor-signed: TDX, SEV or Nitro measurements);
- a verdict counts only from a drawn juror, in the commit-reveal window;
- the draw's seed is a future block hash or a randomness beacon (a verifiable random function), fixed at delivery;
- planted cases and revealed fates update scores on-chain, and slashes are executed by the contract.

**Upgrades:** the contract should be immutable, or upgradable only through a time-locked multisig. Parameter changes should be announced in advance and recorded as events (the ledger's "published parameters" rule).

## 2. How contributors know the fees before they bid

The owner's rule (#49) puts the decision with the contributor: "it's up to them to judge whether a bounty is profitable." That needs a **quote before bidding**:
- **A read-only `quote(bountyId, solver)` on the contract** (or the same computation in a CLI or MCP tool) returns:
  - the price cap and the **reserve** (the most it can be paid);
  - the **stake** this solver must post (after its trust discount);
  - the **check deposit** (one full attempt's checks at the top tier), returned unused;
  - the **expected checks:** runs, the first jury, and the second jury at the published escalation rate, at this solver's likely jurors' tiers;
  - the **market fee** and the **finder's fee** (paid from the bounty, not the solver);
  - the published rates the solver needs to price risk: the share of deliveries the checks catch, the escalation rate, and the solver's own record.
- **A bounty page** shows the same quote, plus the round's deadline, the public failing test, and the attempt history (published failed attempts, #43).
- **Everything comes from published parameters and on-chain history,** with no private pricing. A solver's net if it wins at price P: P − its build cost − its checks; the deposit's unused part and its bond come back.

## 3. Which chain

**Recommendation for a prototype (local first): an Ethereum layer-2. Base first, Arbitrum One as the alternative.** Both have Circle-issued native USDC and EVM tooling. Reported median fees in April 2026 were about $0.02 per USDC transfer on Base against $0.04 on Arbitrum ([eco.com comparison](https://eco.com/support/en/articles/14798701-base-vs-arbitrum-which-l2-should-you-build-on)); verify current numbers on L2BEAT and growthepie.

| Need | Why an EVM layer-2 fits |
|---|---|
| Stablecoin bounties (the owner: "bounty still fixed stablecoin") | Native USDC on both, with regulated on- and off-ramps |
| Cheap commit-reveal, attestations and instalments | Cents per transaction |
| Mature contract tooling and audits | Solidity, Foundry, OpenZeppelin, Safe multisig; audit firms know it |
| Attestations and optimistic disputes | The Ethereum Attestation Service and UMA-style optimistic oracles live in this ecosystem. **Check which are deployed on the chosen chain.** |
| Neutrality and exit | Both settle to Ethereum. Base is run by Coinbase (one sequencer operator); Arbitrum has a DAO. Weigh operator concentration against Base's on-ramp convenience |

**Not recommended first:**
- **A chain of our own or a Bittensor subnet:** emissions-based rewards conflict with #15 principle 1 (money from outside the group being paid).
- **Ethereum mainnet:** fees are too high for per-check transactions.
- **Non-EVM chains such as Solana:** cheap and fast, but we'd lose the attestation and dispute tooling above.

**Local prototype path:** Foundry's local chain (anvil), forking Base's state for USDC, in a container. No wallets or testnets until the go-live checklist is done.

## 4. Storage: decentralized, or GitHub?

**Recommendation: keep the work in git, and put only evidence and commitments in content-addressed storage.**
- **Code and fixes:** git, where developers already are (GitHub, Forgejo or any host).
  - A delivery is identified on-chain by its **commit hash**, which is already content-addressed and verifiable.
  - There's no need to move code to IPFS. If a host disappears, the hash still identifies the exact code, and mirrors can serve it.
- **Hidden tests:** encrypted to the runners' enclave keys and stored in content-addressed storage (IPFS, pinned; or Arweave). The hash is on-chain from the start.
- **Evidence, CI logs and jury evidence** (sealed until the bounty settles, #43): content-addressed storage, by hash.
- **Bounties posted from GitHub:** a bot reads an issue labelled `bounty` (or a `/bounty` comment, as Algora does) and opens the on-chain bounty with the issue's URL and the public test's hash. The issue is the human-readable front; the contract is the source of truth.
- **Censorship resistance,** only if needed later: mirror to Radicle, or a self-hosted forge. GitHub can remove content or accounts, but the on-chain hashes keep what was agreed verifiable.

## 5. Is it legal to post bounties on GitHub?

**Not legal advice: these are the questions for counsel, by jurisdiction.**

**GitHub itself:**
- Bounty platforms (Algora, IssueHunt, the former Bountysource) have operated on GitHub for years. Algora's flow is a `/bounty $AMOUNT` comment on an issue and `/claim` in the PR ([Algora docs](https://docs.algora.io/bounties/workflow)). Bounties as such aren't the problem.
- GitHub's Acceptable Use Policies cover spam, unsolicited bulk automation and harassment. A bot posting bounties on repositories **without their maintainers' consent** risks that, and is socially hostile: maintainers object when outsiders put bounties on their issues ([a Bountysource thread](https://github.com/bountysource/frontend/issues/930)). Projects like PX4 approve bounties through a maintainer ([PX4 forum](https://discuss.px4.io/t/px4-bounties-are-here-solve-an-issue-receive-a-reward/35604)).
- **Our rule should be:** bounties only on repositories whose maintainers opted in (installed the app), or on our own fork or distribution. That matches #15's "respect the upstream author", and **while under wraps, nothing at all on storytold or GridCraft**.
- Some projects require a CLA before a contributor can claim a reward ([CommCare](https://dimagi.atlassian.net/wiki/x/O4E0m)). The contract can require the same signed statement.

**The money**, which matters more than GitHub:
- **Custody and money transmission:** holding pledges for others can be money transmission (US federal and state licences; comparable rules elsewhere). A non-custodial contract, where funds sit in the contract and no company can move them, reduces but doesn't remove the question, especially if we run the front end and the oracles. *Counsel:* is the operator a money transmitter in our jurisdictions?
- **Paying people:**
  - tax reporting (in the US, W-9 and 1099 for residents over the threshold, W-8BEN for others);
  - sanctions screening (for example OFAC) before paying any address;
  - possibly identity checks (KYC). That also ties into #15's identity item.
- **Contractor status:** paying for work could raise employment and contractor questions in some countries.
- **Tokens:** a stablecoin bounty is a payment. A tradable token of our own would raise securities questions. #15 already says: no token unless needed.
- **Consumer and platform terms:** our own terms for funders and solvers (refunds, disputes, the AI juries' role, no person deciding), and a privacy notice for identity data.

## 6. Prototype plan (local only, once the owner says so)

1. Solidity contracts for escrow, sealed bids, deposits and payouts, and an oracle registry that verifies signatures, all on anvil, mirroring `pof/market.py` and `pof/checking.py`. The simulation's ledger events are the test oracle: the same seeds should give the same balances.
2. A mock attested runner (a container signing results with a test key), and mock juries (the simulation's evaluators posting signed verdicts).
3. The `quote()` view and a CLI/MCP tool that prints it.
4. A GitHub-issue bot only against a local Forgejo test repository of our own.

## Sources

- [Base vs Arbitrum: which L2 should you build on (eco.com)](https://eco.com/support/en/articles/14798701-base-vs-arbitrum-which-l2-should-you-build-on)
- [Base vs Arbitrum 2026 (eco.com)](https://eco.com/support/en/articles/15183718-base-vs-arbitrum-2026-which-l2-fits-your-use-case)
- [USDC on Base (eco.com)](https://eco.com/support/support/en/articles/14998918)
- [Algora bounty workflow](https://docs.algora.io/bounties/workflow)
- [PX4 bounties](https://discuss.px4.io/t/px4-bounties-are-here-solve-an-issue-receive-a-reward/35604)
- [CommCare open-source bounty program](https://dimagi.atlassian.net/wiki/x/O4E0m)
- [Bountysource: maintainers' objections](https://github.com/bountysource/frontend/issues/930)
- [Phala x DeMCP: MCP servers in TEEs](https://phala.com/posts/phala-x-demcp-leveraging-tee-for-decentralized-mcp-network)
- [Verifiable MCP proposal (zk-tokyo)](https://github.com/zk-tokyo/advanced-cryptography-2026/issues/94)
