# Design

## Context

See proposal.md for why. What exists today:
- **The race on-chain** (#56: `Race.sol`, `Baskets.sol`), paid on a merge signed by a fixed oracle quorum. The quorum is EIP-712 digests, used once, with more than half the keys (D3).
- **Keyless upgrades by migration** (D15).
- **The token** (`Token.sol`, #58) and its migration (#83).
- **A local bounty loop** (`bot/`, local Forgejo): the bot merges a fix once the oracles sign it.

The main specs already describe the AI jury:
- one seat per provider and per operator;
- drawn with a seed;
- bonded;
- scored on the truth.

They also describe the project's constitution as versioned quality gates.

What's missing:
- the git host's admin can still change the code;
- nothing protects the rules themselves from a stream of passing fixes;
- the owner wants no maintainer in the loop.

## Goals / Non-Goals

**Goals:**
- Every change to a self-governed repository's code goes through the judges' verdicts, recorded on-chain.
- The rules are stable: they change only through an ADR the larger tier accepts, and the core rules never change inside a version.
- The system finds and pays for its own repairs: system issues and the sponsors' pool.
- Every parameter named here is measured (B1, B2) or simulated before any contract v2 is written.

**Non-Goals:**
- Choosing the 7 model families or operators; B1 measures the candidates.
- Real deployment, real operators or real money (rule 1).
- Governing projects that keep human maintainers. They get verified-fix pull requests and nothing more.
- Reputation and treasury matching on-chain (D9 stands).

## Decisions

### S1. The canonical head is on-chain, bound to the base commit
- The contract keeps `head[repo]`: the commit of the last fix the judges passed, plus the constitution's hash.
- **A verdict signs `(repo, base, fix commit, bounty, submission)`.** It moves the head only if `base == head[repo]`.
- **If the head moved first, the verdict is stale:**
  - the winner keeps its first place and its locked share;
  - it rebases, and the issue tier checks the rebased fix again;
  - the solver pays for that check, refunded at merge like the others (S6).
- **Why bind to the base:** a fix judged on old code can be wrong on new code. The alternative, letting the bot merge whatever it can, would put unjudged code at the head.
- **Mirrors:** the bot fast-forwards each mirror to the recorded head. A mirror ahead of or different from it is reported with both commits and, where the bot has write access, restored. Anyone can run a bot; bots don't coordinate, because they all read the same chain.

### S2. Two tiers drawn from one set of 7
| Parameter | Value | Why |
|---|---|---|
| `JUDGES` | 7 | the owner's number for the constitution; enough families to stay diverse |
| `ISSUE_JUDGES` | 3 | the owner's number; 3 calls a fix keeps checks cheap |
| `ISSUE_QUORUM` | 2 | a majority of 3 |
| `CONSTITUTION_QUORUM` | 5 | a supermajority of 7: two colluding or mistaken families can't pass an ADR |

- **The issue tier draws 3 of the 7** with the verdict's seed (the jury draw in the checking spec), so the work and the fees spread across all 7 operators. That's also why a separate cap on any operator's share of verdicts isn't needed.
- **On-chain, D3 extended:**
  - the 7 keys are fixed for the version;
  - an issue verdict needs 2 signatures from the 3 the seed selects;
  - a constitution verdict needs 5 of the 7.
- **The alternative,** a separate set of 3 operators for issues, would leave 4 of the 7 idle and unpaid most of the time, and would make the issue tier a small, fixed group.
- **As built (task 5.3, `reports/contract-v2.md`):**
  - `Verdicts` holds the counts as constants (`ISSUE_JUDGES` 3, `ISSUE_QUORUM` 2) and the version's quorum as an immutable (5 with 7 keys): the constitution tier's threshold, and every other signed action's. No function changes them.
  - **The draw** is a Fisher-Yates shuffle of the keys driven by the seed (`drawn`, a view), walked in order; a key whose operator is a party is recused (`KeyRecused`) and the next in the shuffle sits. Results and merges take only signatures from the drawn keys (`authorizeDrawn`); the constitution tier takes the quorum from the keys that sit (`authorizeAll`, used from 5.10).
  - **The seed** is fixed at the commit, not chosen by the judges or the relayer: `keccak256(block.prevrandao, commitment, id)`, stored on the submission and checked against the signed verdict. The solver doesn't know the block's RANDAO value when it signs its commitment, so it can't grind its salt for friendly judges. **Limits:** a proposer can bias RANDAO by one bit, and on a layer-2 whose RANDAO the sequencer sets, the seed is only as good as the sequencer; before a public chain, a randomness beacon or the sealed verdicts' commit-reveal (S12) should feed it.
  - **Recusal** (S9, S13): the operators' disclosed accounts are fixed with the keys in `Verdicts`' constructor. The race answers `isParty` for a bounty and a submission: the issue's reporter, the submission's solver, or a funder in any fee coin.
  - **The EIP-170 split, continued:** to make room, `RaceV2`'s rarely called actions (the appeals, `withdrawIssue`, `junk`, `refuseSimilar`, `timeOut`, `mergeExpired`, `challengeUpheld`) moved unchanged into `RaceV2Annex`, which `RaceV2` deploys and delegates to (its address an immutable, no key). Both inherit `RaceV2Base`, one storage layout. `RaceV2` is 22,242 bytes (2,334 free); its initcode, 45,322 bytes, is now the tighter limit (EIP-3860).

### S3. One model family per judge, one operator per judge
- **The families are fixed at deployment.** Example: Anthropic, OpenAI, Google, plus open-weight Llama, Qwen, Mistral and DeepSeek; B1 picks the actual set. Each family has one operator; a different family is a new version.
- **Why families:** models trained on similar data share blind spots, so 7 copies of one family are one judge, not 7. B1 measures how often the families agree, and on what.
- **Each verdict names its model and version,** in the public log. An operator who quietly runs a cheaper model is the "cheat" in the model-quality spec, caught the same way: planted cases and scoring on the truth.

### S4. Escalation, challenges and reverts
- **Triggers:**
  - a protected path in the diff, which the runners check mechanically;
  - any issue judge's `constitutional` flag;
  - a staked challenge within the clawback period.
- **Merge first, challenge after:** a fix that passes the issue tier moves the head at once. The clawback period (the existing instalments) is the challenge window, so self-healing isn't delayed.
- **An upheld challenge** (5 of 7) moves the head to a revert commit, built by the bot from the recorded fix. The unpaid instalments are clawed back and the bounty reopens (D9). The challenger stake and slashing follow the challenges spec.
- **A failed challenge** pays the challenger's stake to the solver.
- **The alternative,** holding the merge until the window closes, would make every repair wait days. The risk of merging first (a bad fix at the head for a while) is measured in the simulation: the share of bad fixes merged, and the days until reverted.

### S5. The constitution and ADRs
| Parameter | Value | Why |
|---|---|---|
| `ADR_WINDOW_DAYS` | 14 | two weekly releases (`releaseEveryDays` 7) for anyone to read and challenge |
| `ADR_FEE` | 7 × the verdict fee | the constitution tier's cost; the author pays it |

- **An ADR is a pull request** that adds `docs/adr/NNNN-*.md` and changes the protected files it names. The judges check that the ADR covers exactly the protected paths it changes.
- **When it passes,** the head and the constitution's hash move after the window, unless a challenge is upheld.
- **Entrenched articles** (Articles 2, 3 and 9 of the draft): an ADR touching them is refused before judging, mechanically, by a list of entrenched article markers in `CONSTITUTION.md`. They change only by a new version (D15): a new deployment with a new constitution, which users choose to follow.
- **Bounties keep the version they were registered under,** as the checking spec already says.

### S6. Money: coin only, check fees, and the pool
- **No token emission:** v2 has no token and no `Token` calls.
  - `Token.sol`, its tests and the migration (#83) stay in the repository as the parked option.
  - A future version can include them; holders choose by migrating (D15).
  - The founder's share goes with the token.
- **`market_fee_bps = 0`,** as D9 already has on-chain.
- **Check fees:**
  - the registration fee pays the registration check;
  - the solver's check deposit pays its attempt's checks;
  - **at merge, the bounty refunds the winner's checks for that fix** (`WINNER_CHECK_REFUND`, on).
  - **Why the refund:** an honest winner shouldn't lose money on a fix that was good. Failed attempts still pay for their own checks, so spam stays expensive.
  - **The risk:** it moves cost from solvers to funders. The simulation compares the two on the same seeds before v2.
- **The sponsors' pool** is an on-chain pot, funded by anyone and spent only by fixed rules:
  - system issues' registration fees;
  - `SYSTEM_BOUNTY_START`, the starting amount of each system issue's bounty while the pool holds it, set from B2's costs;
  - refunds of accepted ADRs' fees.
  - Nothing else; there's no withdraw function.

### S7. System issues
- **Kinds:**
  - tests failing on the recorded head;
  - a security advisory for a pinned dependency;
  - a regression, meaning a test that passed at an earlier head and fails now.
- **Registration:** anyone registers with evidence and pays the registration fee. If the registration check accepts it, the pool pays the fee and the watcher is refunded; there is no reporter share, which goes to the pool.
- **Why no reward for watchers beyond the refund:** a reward would pay people to break the head or fake regressions, which the issue farmer in the simulation would exploit. The refund makes watching free; the healthy code is the watcher's interest.
- **Security advisories:** a public race would publish the exploit (D15: "security bugs go through a private reporting channel"). The private path for undisclosed vulnerabilities stays as in D15. Only public advisories become system issues.

### S8. Outside projects
- **A bounty on a project with human maintainers pays on the judges' verdict** (mode `verified`). Attempts run in the protocol's sandbox and never appear upstream.
- **The bot offers the winner's fix as one pull request,** with the verdict linked. Merging is the maintainers' choice.
- Rule 2 holds: licences and attribution are kept, and fixes are offered back upstream.

### S9. The genesis constitution
- **The owner writes `CONSTITUTION.md` v1.** It's committed here as a DRAFT and takes effect only when a v2 is deployed, with its hash recorded at genesis.
- **ADR 0001 records the decision, and discloses the owner's one-time act and benefits:**
  - one judge seat at most, with recusal;
  - solving like anyone;
  - no founder's share;
  - a 0 % fee.

### S10. Contracts v2, and the EIP-170 split
- **v1 already fits:** #93 brought Race to 23,065 bytes (the IR pipeline plus the `OracleAuth` library), with no ABI change. v2 adds much more (no token calls; the head registry, the tiers, the pool, ADRs, and S11–S18), so the split is still designed in.
- **The split is designed into v2 instead of patching v1:** `Race` (bounties and the race), `Heads` (the head registry, ADRs, the constitution's hash), `Pool` (the sponsors' pool) and `Verdicts` (the D3 quorum and the tiers, as a library or a contract).
- **Every contract must be under 24,576 bytes** (`forge build --sizes`).
- **v1 to v2 is a migration (D15):**
  - v1's bounties finish in v1, and its refund paths stay;
  - new bounties open in v2;
  - v1 had no head registry, so v2's genesis head is the commit at deployment.
- **As built (task 5.1, `reports/contract-v2.md`):**
  - the contracts are `RaceV2` (22,525 bytes), `Verdicts` (a contract, so one key set serves every v2 contract; used digests are kept per caller), `Heads` (genesis only) and `Pool` (funding only, no withdraw), beside v1;
  - the inflation rule stays on the coin (the finder's fee), and the EIP-712 domain is version `"2"`;
  - v1's suites run on v2, and the replay's 13 seeds match to the micro-credit.

### S11. The verdict v2 binds the base commit and the receipt
v1's signed `result` doesn't name the base commit it was checked on (`reports/devnet-v1.md`, gap 1). v2's EIP-712 struct does, and binds the receipt (S14):

```
Verdict(bytes32 repo, bytes20 base, bytes20 fix, uint256 bounty, uint256 submission,
        uint8 tier, uint8 outcome, bytes32 receiptHash, bytes32 seed, uint256 nonce)
```
- The domain stays as in D3 (name, version, chain ID, verifying contract), so a verdict can't be replayed on another chain, contract or version.
- S1's rule applies: a verdict moves the head only if `base == head[repo]`.
- **Why one struct for both tiers:** the tier is a field, so a 2-of-3 issue verdict can never count toward a 5-of-7 constitution verdict.
- **As built (task 5.2, `reports/contract-v2.md`):**
  - `Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)`. Two departures from the sketch above: commits are `bytes32`, like `Heads` and the submissions' `fix` (a SHA-1 left-aligned, or a SHA-256 id), and the nonce is `bytes32`, like every other signed action.
  - `result` signs `Result(Verdict verdict,Fee[] fees)` and records the base and the receipt's hash on the submission; `merged` signs `Merged(Verdict verdict,uint256 weight)` and moves the head. Both take the issue tier only (`WrongTier` otherwise), the bounty's own repository, and the quorum's signatures.
  - An issue registers in a repository of the registry, or outside it with repo 0 (S8): a merge there moves no head.
  - `Heads` is deployed by `RaceV2`'s constructor, so its only mover is fixed at creation with no key: `move` checks `base == head` (`StaleVerdict` otherwise) and records the bounty, the submission and the verdict's struct hash. A stale merge reverts whole: the winner keeps its place, its locked share and its deadline; the judges check the rebased fix on the new head and sign a new merge, whose `fix` is the rebased commit (both commits count as paid, D10).
  - A pass checked on an older base still wins its place in the queue; only the head's move needs the current base.
  - The seed is signed and recorded but nothing draws yet (5.3). The rebased fix's check fee is 5.7's.

### S12. Sealed verdicts on-chain, then revealed
The main specs already require sealed verdicts ("Jury verdicts", "Commit-reveal verdicts"). #94 does it inside the node; v2 enforces it on-chain.

| Parameter | Value | Why |
|---|---|---|
| `SEAL_WINDOW` | 2 hours from the attempt's `checksReady` event | tests plus one model call take minutes; 2 hours absorbs retries and outages without stalling the race |
| `REVEAL_WINDOW` | 1 hour after the seal window closes, or after every drawn judge has sealed | short, because revealing is just publishing what's already decided |
| `NO_REVEAL_SLASH_BPS` | 500 (5 % of the seat's bond) | the "published share" of the challenges spec: enough to make not revealing cost more than a check fee, small enough that an outage isn't ruinous |

- **Seal:** each drawn judge signs `seal = keccak256(verdictStructHash, salt)` with its seat key. Anyone (a relayer) submits the signed seals, one transaction for a batch.
- **Reveal:** after the seal window, the judge's signed reveal (`outcome`, `receiptHash`, `salt`) is checked against its seal. A mismatch is equivocation (S16).
- **A judge that doesn't reveal** loses `NO_REVEAL_SLASH_BPS` of its bond, its verdict is discarded, and the next seat in the draw replaces it, with a fresh seal window for that seat only.
- **Why on-chain and not only in the node:** a node's own rule can be switched off by its operator. On-chain, a late judge can't see the others' verdicts before sealing, whoever runs it.
- **Cost:** two signature checks per judge instead of one. At about 4,760 gas per signature (#93), that's under 15k gas per issue verdict.

### S13. Seats fixed per version; keys rotate only under an entrenched rule
D15 and Article 3 fix the judges for a version. v2 keeps that, with one precise exception:

- **Fixed per version:** the 7 seats, each seat's operator, its model family, and its inference or TEE provider. Adding, removing or replacing an operator is a new version (D15), which users choose to follow.
- **A seat's key may rotate** (an enclave redeployed, a checker image upgraded by ADR), but only if:
  1. the new key comes with an **attestation of an accepted type** (S14: AWS Nitro, Intel TDX through Phala dstack or self-hosted, or AMD SEV-SNP; or a provider-signed attestation for a provider seat) showing **the official checker image digest** on the constitution's allowed list (a protected path, so changing the list is an ADR);
  2. the rotation is **co-signed by the seat's current key and by the constitution tier** (5 of the other 6), each of whom checked the attestation off-chain with the open-source verifier;
  3. it takes effect after `KEY_ROTATION_DELAY_DAYS` = 7, published on-chain with the attestation's hash, so anyone can check it and challenge.
- **A lost key:** the seat can't rotate (it can't co-sign), so it's **suspended.** The issue tier draws from the remaining seats; the constitution tier needs 5 of those still seated, and if fewer than 6 remain, ADRs wait for a new version.
- **Automatic suspension, no vote:** a seat whose bond falls below `SEAT_BOND_MIN` (S16) is suspended until topped up.
- **Recusal** stays as in the checking delta: a seat never judges where its operator is a party.
- **Why not let the quorum add operators:** that's a standing power over who judges, which Article 2 excludes. Rotation only lets a known operator replace its own key, under an attested image.
- **Why the attestation is checked off-chain:** verifying a TDX or Nitro quote on-chain costs millions of gas. The quorum checks it once, signs, and publishes the quote's hash, which any challenger can check.

**Provider cap:** at most `PROVIDER_SEAT_CAP` = 2 seats per inference or TEE provider (for example Phala, NEAR AI, io.net, AWS Nitro). Each seat records its provider at genesis. **Why 2:** with 7 seats and 5 needed for the constitution tier, no single provider failing or colluding can block or pass an ADR; 3 per provider would let one provider plus two others reach the 5.

- **As built (task 5.4, `reports/contract-v2.md`):** the seats live in `Verdicts`, not `RaceV2` (whose size is unchanged).
  - **Genesis** (`Verdicts.Genesis`): each seat's key (0 for a vacant seat), its family (distinct per seat, Article 3), its provider (at most `PROVIDER_SEAT_CAP` per provider), the quorum, the operators' disclosed accounts by seat, the allowed checker images and the accepted attestation types (Article 7, fixed for the version until ADRs reach the chain, 5.10). At least the quorum of seats must be filled, so the version can act and fill its vacancies.
  - **Rotation** (`rotate`, then `activate` by anyone after `KEY_ROTATION_DELAY` = 7 days): signed under the `Verdicts` EIP-712 domain (`Rotate(uint256 seat,address key,bytes32 image,bytes32 attestationType,bytes32 attestation,bytes32 nonce)`) by **the new key itself** (so nobody registers a key they don't hold), the seat's current key, and the quorum of the other seats' active keys. The image must be allowed and the type accepted, with an attestation hash unless the type is `none`, which only a devnet version lists (rule 1). A key serves one seat, once; one pending key per seat. `KeyPublished` records the attestation's hash.
  - **The join flow (#104):** a seat deployed vacant (its operator, family and provider fixed at genesis) takes its first key by the same `rotate`, with no current key to co-sign. A filled seat only rotates, so a vacancy is filled once. `scripts/devnet.sh digest-v2` prints the digest an engineer signs with their own key; `join-v2 --key --sig` publishes it with the co-signers; `activate-v2` after the delay.
  - **Suspension:** the spec doesn't say who suspends a seat that can't sign. As built: the quorum of the other seats publishes it (`suspend`), it takes effect after the same delay, and **the seat's own key lifts it at any time** (`resume`), so the others can't keep out a seat that can still sign. A suspended or vacant seat is neither drawn nor counted; the draw shuffles the active keys in seat order. The bond-based suspension is a hook for 5.8 (`_bonded`).
  - Each check of a key reads its seat (filled, not suspended): `accept`, `result` and `merged` cost about 13k more gas.

### S14. Receipts, content-addressed and bound on-chain
- **Each verdict carries a receipt,** shaped after the IETF draft "Attested Inference Receipt" (COSE_Sign1): the model ID and version, the provider, the SHA-256 of the prompt and of the response, the checker image digest, the test results' hash, `base` and `fix`, a timestamp, the attestation evidence's hash, and the signing key.
- **The receipt is stored content-addressed** (by its SHA-256; IPFS or Arweave, or the operators' own stores), and **only its hash goes on-chain,** inside the sealed verdict (S11).
- **A receipt that doesn't match its hash, or whose attestation doesn't verify,** is a provable fault for a challenge (S16).
- **Why only the hash on-chain:** receipts run to kilobytes; the hash binds them for a few hundred gas.
- **Encoding:** a receipt is a **COSE_Sign1** structure following the IETF individual draft *Attested Inference Receipt*, pinned to `draft-tsyrulnikov-rats-attested-inference-receipt-02`. It's a draft, not a standard: a later version is adopted only by ADR. The node's v1 JSON receipt (#95, #99) carries the same fields and is replaced by the COSE form in task 6.3.
- **The exact model:** the receipt names the exact model ID and version. **The allowed versions for each family are listed in the constitution** (a protected path, changed by ADR). A verdict whose receipt names a model outside the list is a bad receipt (S16).
- **Usage is measured inside the attested node and recorded in the receipt:** the provider's own token counts (input, output, cached) and the sandbox's CPU-seconds and GB-seconds. Check fees are charged on these (S15).
- **Counted judges call model providers directly from inside the TEE:** the TLS session to the provider terminates inside the enclave, so the receipt proves what the provider returned. **No proxy or gateway sits in the path of a counted verdict.** The AgentCore model gateway stays for development and the B1 measurements only, where its budgets and logs help and no proof is needed.
- **Accepted attestation types, one checker:** the constitution lists the accepted TEE types (AWS Nitro; Intel TDX, through Phala dstack or self-hosted; AMD SEV-SNP) and **one official checker image, built reproducibly,** so every operator's attestation shows the same digest. Within that, each operator chooses its own infrastructure; the provider cap (S13) keeps it diverse.

### S15. Check fees: costs passed through per unit, plus one agreed service fee
The owner's decision (2026-11-01): a check is paid like a taxi fare with tolls. **The costs of that check are passed through at public unit prices, with no profit in them, plus one service fee per check that is the same for every seat.** There are no per-seat fees: seats are drawn at random, so a seat's own price could never win it work, and per-seat fees would need solvers charged an average and a balancing pool to stay fair (the owner judged that more trouble than it solves).

| Parameter | Value | Why |
|---|---|---|
| `FEE_COIN` | one stablecoin, fixed per version | the price table needs one unit; multi-coin bounties (#59) come later |
| `SERVICE_FEE` | **$0.05** per counted check, in `FEE_COIN`, the same for every seat (owner, 2026-11-01, from #102) | covers a typical operator's on-demand enclave (about $0.012 a check on top of the passed-through usage), idle time, failed runs and margin. Replaces v2's earlier 20 % margin (`CHECK_MARGIN_BPS`, removed). An operator breaks even at about 55 checked submissions a week on the network (`reports/self-healing-v1.md`) |
| `SERVICE_FEE_CAP` | **$0.25**, in the constitution, changed only by an ADR | a hard ceiling no quorum can pass |
| `PRICE_CAP_MULTIPLE` | **2×** each entry's genesis value (its price at deployment), in the constitution, changed only by an ADR | without it, 5 colluding seats could raise the table about 100,000× in a year within ±25 % per update (#102); at ×10 attempts drop about a fifth, at ×100 nothing gets paid |
| `PRICE_STEP_MAX_BPS` | 2,500 (±25 % per update) | applies to every table entry and to `SERVICE_FEE`: providers' prices move, but no single update can jump fees |
| `PRICE_DELAY_DAYS` | 7 | solvers and funders see a new price or fee a week before it applies |
| `RELAYER_GAS_OVERHEAD` | measured on the devnet | the gas the contract can't measure itself (calldata, the transaction's base cost) |

- **The price table holds unit prices, not prices per check:**
  - per model family: input, output and cached tokens, per million;
  - the sandbox: per vCPU-second and per GB-second;
  - storage of receipts and logs: per MB.

  **Gas has no table entry:** it is reimbursed at cost (below).
- **What a check costs** is the usage it measured (S14: the provider's token counts and the sandbox's seconds, inside the attested node, recorded in the receipt) × the unit prices, **plus `SERVICE_FEE`.** A long prompt or a heavy test suite costs more at the same prices.
- **The median rule:** for parts every drawn judge performs (its own AI review; its own test run when there is no single attested run), each counted judge is paid **the median of the counted judges' usage** at **its own family's** token prices. One judge padding its usage changes nothing.
- **Per-check caps:** the maximum tokens per verdict come from the constitution; the maximum CPU, memory and minutes from **the repository's CI profile** (below). A run that hits a cap stops there and is charged up to the cap.
- **CI profiles:** each repository declares in its config the test image digest, the CPU, the memory and the timeout of its checks. **Quotes show the maximum check cost** from that profile and the table in force.
- **The solver's deposit is a maximum:** the drawn judges' worst case under the caps, plus `SERVICE_FEE` for each counted judge, plus the relayer's gas allowance. The solver knows the ceiling before attempting; **whatever the checks don't use is refunded.**
- **The relayer's gas is reimbursed at cost:** the gas measured inside the call plus `RELAYER_GAS_OVERHEAD`, at the transaction's own gas price (`tx.gasprice`), within the deposit's gas allowance.
- **Who changes the numbers, and how** (owner, 2026-11-01, #100):
  1. **A proposal:** a new table or `SERVICE_FEE`, signed by **5 of 7 seats,** citing **the providers' public price lists** it follows (the evidence's hash on-chain, its content in the public log). Token prices are **indexed** to those lists: the quorum reports costs rather than chooses them.
  2. **The contract checks the bounds** and refuses anything outside them: each value within `PRICE_STEP_MAX_BPS` of its current one, **no entry above `PRICE_CAP_MULTIPLE` × its genesis value,** `SERVICE_FEE` never above `SERVICE_FEE_CAP`, one pending update at a time.
  3. **`PRICE_DELAY_DAYS` of public notice.**
  4. **Anyone can challenge with a stake** during the notice, showing that an entry doesn't match the cited public prices. The claim is a comparison with a public price list, so any honest seat can check it; it is decided by **the seats that didn't sign the update** (who decides when all 7 signed is open in #100). **An upheld challenge cancels the update and pays the challenger from the proposers' bonds** (`PRICE_CHALLENGE_SLASH_BPS`, S16); a rejected one forfeits the stake to the pool.
  5. **Otherwise it takes effect.** Changing a cap needs an ADR (5 of 7 plus 14 days, Article 9).

  What remains open in #100 is a voice for funders and solvers beyond challenges, and the validator strategy (gaining support, choosing seats).
- **Payments:** fees and gas repayments are **credits, pulled** by operators and relayers (Article 5.3). **The winner's checks are refunded from the bounty** at merge (S6), in `FEE_COIN`; a bounty must hold `FEE_COIN` for this.
- **Optional: one attested CI run** (`CI_SINGLE_RUN`, a per-version setting, off until the simulation and the devnet support it). The tests run **once,** in an attested node; the other drawn judges **verify that run's attestation and result hash** and still do their own AI review. The run's usage is charged once, at its own measurement. Anyone can **challenge by re-running** the tests in the same CI profile; a mismatch is a bad receipt (S16). It cuts the CI cost about 3× for the issue tier.
- **A node design note, not a protocol rule:** an operator may keep its fixed cost low by **starting its enclave on demand,** with a small always-on watcher that starts the enclave when its seat is drawn and stops it afterwards. The seal window (S12) leaves time to start.

- **As built (task 5.7, `reports/contract-v2.md`):** the meter is its own contract, `Fees`, deployed before `RaceV2` and passed to its constructor, which binds it (`bind`, once: from then on only that race settles with it). A version deployed without one (the zero address) keeps v1's flat check deposit and the judges' signed fee list, so the replay's 13 seeds still run unmetered (the fee replay is 5.14).
  - **The table** (`Fees.prices`): every entry in micro-coins per million units: per family input, cached and output tokens; the sandbox's vCPU-seconds and GB-seconds; storage MB; **then the ETH price** (micro-coins per ETH) and `SERVICE_FEE`. Genesis kept (`genesis`) for the 2× cap.
  - **Gas needs an ETH price entry** (a departure from "gas has no table entry"): the relayer pays gas in ETH and is repaid in `FEE_COIN`, so the conversion is an entry, bounded like the others. Repaid gas = (gas measured in `result` up to the settle + `RELAYER_GAS_OVERHEAD`) × `min(tx.gasprice, MAX_GAS_PRICE)` × the ETH price, at most the deposit's allowance. On the devnet the overhead measured 536,636 gas with 3 reports (the transaction's base and calldata, the settle and the credits after it); the deploy script sets 540,000, and the repayment came within 0.5 % of the transaction's real cost.
  - **Usage is reported per judge, before the result** (`Fees.report`, relayed by anyone): each drawn judge signs `Usage(uint256 submission,bytes32 receipt,uint64 input,uint64 cached,uint64 output,uint64 vcpuSeconds,uint64 gbSeconds,uint64 storageMb)` under the `Fees` EIP-712 domain with its seat's key; only keys `Verdicts` draws for the submission, once each, while it waits for its result. **The counted judges are the drawn judges that reported:** a judge that doesn't report isn't paid; one that dissented but reported is (it did the check). Until receipts reach the chain (5.6), the usage is taken as signed.
  - **The charge** (`Fees.settle`, called by `result`): every report capped (the constitution's tokens and storage, the CI profile's vCPU- and GB-seconds; cached never above input), then each field's median (the middle of three; the mean of two, rounded down, as `pof.checkgas`); each counted judge paid the median at its own family's token prices, the median sandbox and storage, plus `SERVICE_FEE`, credited to **its seat's first disclosed operator account** (the key itself if none); with `CI_SINGLE_RUN`, the run charged once, at its own capped usage, to the first reporter that ran it. `RaceV2` releases the credits from the deposit (never more than it), returns the rest, and keeps what was charged in the submission's `deposit` field.
  - **The deposit** (`maxDepositFor`, also the quote's `checkDeposit`): `ISSUE_JUDGES` judges at the caps at the dearest family, each with its storage and `SERVICE_FEE`; the CI runs at the profile's limits (one with `CI_SINGLE_RUN`); the gas allowance at `MAX_GAS_PRICE`; every price the dearer of the one in force and the pending one, so an update published after the commit can't push a charge over its deposit. A metered version takes check deposits in `FEE_COIN` only.
  - **The winner's refund is paid at settlement, not at the merge:** when a bounty closes paid, `_settle` refunds the winner's charged checks from what the `FEE_COIN` pot still holds after the price, the finder's fee and the registration refund. Paying at the merge would take from the pot the instalments are paid from; at settlement it can't. A pot left short pays a partial refund.
  - **CI profiles and caps are fixed at deployment** (per repository, and a default for the rest), like the other constitution values until ADRs reach the chain (5.10).
  - **Price updates:** `propose` (5 of 7 through `Verdicts.authorizeAll`; `Fees` answers no one is a party), `applyUpdate` by anyone after the notice; charges use a pending table from its effective time whether or not it was applied. **Not built: the procedure's step 4, the staked challenge** decided by the seats that didn't sign and paid from the proposers' bonds: it needs the bonds (5.8, hook `TODO(5.8)` in `Fees`).

### S16. Bonds, provable faults and canaries
| Parameter | Value | Why |
|---|---|---|
| `BOUNTY_MAX` | per version, in `FEE_COIN` (for example $625) | the largest bounty a version accepts; bonds follow it |
| `SEAT_BOND_MIN` | **2 × `BOUNTY_MAX`** (about $1,250 for $625 bounties; owner, 2026-11-01, from #102) | the binding case is one fault sold on the largest bounty: an equivocation proven half the time only loses money if the bond exceeds about 2× that bounty. The earlier starting point (50 × a seat's weekly fees, about $54) was far too low |
| `EQUIVOCATION_SLASH_BPS` | 10,000 (the whole bond) | two conflicting signatures are proof of bad faith, with no honest explanation |
| `DA_FAIL_SLASH_BPS` | 2,000 | a seat that signed "I hold it" and can't serve it (S17) |
| `BAD_RECEIPT_SLASH_BPS` | **2,000** (owner, 2026-11-01) | a receipt whose content doesn't match its hash, whose attestation doesn't verify, or that names a model version not allowed |
| `PRICE_CHALLENGE_SLASH_BPS` | 2,000, from each proposer, paid to the challenger | a price update shown not to match the public prices it cited (S15) |
| `CHALLENGE_REWARD_BPS` | 5,000 of the slash | pays whoever proves the fault; the rest goes to the sponsors' pool |

- **Each seat posts a bond** in `FEE_COIN` at genesis. Slashing is **only for provable faults, checked by the contract or by a challenge:**
  1. **Equivocation:** two signatures by one seat for conflicting outcomes on the same verdict, or a reveal that doesn't match its seal. Anyone submits both; the contract checks them itself.
  2. **No reveal** (S12).
  3. **A failed availability challenge** (S17).
  4. **A bad receipt:** its content doesn't match the hash, or its attestation doesn't verify. A challenge decided by the constitution tier, without the challenged seat.
- **Canaries stay off-chain in v2.** Planting cases that judges can't tell from real ones needs someone to make them, which would be a trusted curator. So in v2 the operators and anyone else run canaries against the public verdicts, and the results go on the **public scoreboard** (accuracy, reveal rate, canary score). **A wrong answer is not slashed on-chain in v2,** only provable faults are. This narrows the main specs' "Planted cases" (which slash on wrong answers) to the off-chain scoreboard until a curator-free design exists.
- **Why slash only provable faults:** an AI verdict can be wrong in good faith; slashing on disagreement would punish honest judges and reward copying the majority, which the main specs already forbid ("Agreement with other evaluators SHALL never count").

### S17. A head counts only when its code is available
| Parameter | Value | Why |
|---|---|---|
| `DA_SEATS` | 5 of 7 | the same supermajority as the constitution tier: no 3 seats together can make code vanish |
| `DA_HOLD_DAYS` | 365 | a year of guaranteed copies; the permanent copy covers after that |
| `DA_RESPONSE_HOURS` | 24 | time to serve a challenged object |

- **The head moves only when:**
  1. the issue tier's verdict passes (2 of 3); and
  2. at least `DA_SEATS` seats (drawn or not) have signed an availability statement: "I hold the git bundle with SHA-256 `H` for commit `fix`, and will serve it for `DA_HOLD_DAYS`"; and
  3. a **permanent copy's receipt** is recorded with the head: an Arweave transaction ID (or an equivalent content-addressed, paid-once store) for the same bundle.
- **An availability challenge:** anyone names a recorded head and a seat; the seat must post the requested object with a proof against `H` within `DA_RESPONSE_HOURS`, or lose `DA_FAIL_SLASH_BPS`.
- **Transport:** Radicle for **public** repositories only. Its September 2026 flaws (unencrypted node traffic, spoofable node IDs) mean no private repository goes over its network until a fixed release is checked (#92).
- **Why every seat, not just the drawn 3:** availability needs copies spread across operators; the 4 undrawn seats only fetch and store, which costs little.

### S18. The deployment record names every code hash
- The deployment record (as in #93's `contracts/deployments/*.json`) lists each contract's address and code hash, **and each linked library's address and code hash** (`OracleAuth` in v1, the verdict library in v2), plus the compiler version and settings.
- **Why:** anyone checking a deployment must be able to check the library code the contract delegates its signature checks to (#93, gap 2).

### S19. Choosing seats, reseating, and draws (owner, 2026-11-01, #100)
- **Independence is the main defence against collusion:** if 5 of 7 seats collude they control prices within the caps and pass non-entrenched changes. So seats are chosen for independence: **different organisations, jurisdictions and providers** (at most `PROVIDER_SEAT_CAP` per provider), each seat's operator, family, provider and country **disclosed** in the deployment record and the constitution's annex.
- **Reseating by record:** each new version chooses its seats; operators with good public records (accuracy, reveal rate, canary score, uptime) are reseated, poor ones dropped. This is the competition in a fixed-fee design: on quality and reliability, not price.
- **Draws stay uniform in v2.** A later version may weight draws **by quality**, **never by price** (weighting by price would start a race to the bottom).
- **The honest limit:** 5 colluding seats remain the trust point; the design makes it expensive (bonds), detectable (receipts, canaries, the scoreboard), bounded (caps, entrenched articles) and escapable (forks).

### How the simulation tests it
- **Judges:**
  - pof's checking layer already has evaluators with correlated errors within a family;
  - the tiers are added, so a verdict is 2 of 3 drawn, or 5 of 7;
  - escalation by path, by flag and by challenge.
- **The head and system issues:** a repository state with a head, where a bad merged fix can raise regressions that watchers register.
- **New actors:**
  - a test-gaming solver (weakens or special-cases tests);
  - a prompt injector (a fix whose text sways judges, with a published success rate per family from B1);
  - colluding operators (2 to 5 of 7);
  - an ADR capturer;
  - an issue farmer.
- **The oracle network (S12–S17):**
  - check fees (unit costs passed through plus the agreed `SERVICE_FEE`) compared with flat fees on the same seeds: solvers' and funders' costs, and operators' net per check, including the `SERVICE_FEE` that covers a typical operator's on-demand enclave;
  - bonds: the smallest `SEAT_BOND_MIN` at which every slashable fault loses money;
  - new attackers: a judge that doesn't reveal, an equivocator, a judge padding its usage, an operator withholding data, and colluders pushing the price table or `SERVICE_FEE` (at most +25 % a week, `SERVICE_FEE` never above its cap).
- **A stale input to fix (task 4.1 follow-up):** the market simulation still charges evaluators $0.30 per verdict and $0.20 per test run, figures from before B2 measured about $0.13 and a few cents (`reports/costs-v1.md`). With them, evaluators look like they lose about $0.08 per verdict under check gas; a real operator's margin is `SERVICE_FEE` less its enclave overhead (#102).
- **Criteria:** the incentive-simulation delta, reported as `reports/self-healing-v1.md`.

## Risks / Trade-offs

- **Correlated AI errors** → different families (S3), 5 of 7 for the constitution, challenges, and B1's agreement matrix before choosing the families.
- **Prompt injection** in the code under review → inputs are stripped and quoted, and judges see diffs, test results and structured fields (D3's defenses), plus the challenge window. B1 measures the success rate for each family.
- **Five operators colluding** can pass anything on the constitution tier → a public log of every verdict, challenges, independent organisations and countries, and migration as the last remedy (users follow an honest version). This is the remaining trust point, reported, not hidden.
- **Ossification** → ADRs are expensive but possible. Only the three entrenched articles need a new version.
- **Cost:** 7 judges are expensive → used only for ADRs, escalations and challenges. B2 prices it.
- **Merging before the challenge window** → a bad fix can sit at the head for days. The simulation measures how many, and for how long. Holding the merge is the fallback if the numbers are bad.
- **The pool runs dry** → system issues open at 0 coin and wait for funders. Self-healing slows; nothing breaks.
- **Legal:** code nobody controls, and AI deciding payouts → the legal review (#82, D6) before any deployment.
- **Key rotation is a power over who signs** → limited to a seat's own operator, an attested image on the allowed list, the seat's own key plus 5 of 6, and a 7-day public delay (S13). A lost key suspends the seat rather than handing it to anyone.
- **The price table or `SERVICE_FEE` can be pushed up by colluding seats** → 5 of 7 to change them, at most ±25 % per update, 7 days' notice, **each entry capped at 2× its genesis value** and `SERVICE_FEE` at `SERVICE_FEE_CAP` (both in the constitution), proposals indexed to public price lists and open to staked challenges, and the median charge (S15). #102 measured the uncapped worst case (about 100,000× in a year); the caps bound it. **The cost of the cap:** if a provider genuinely more than doubles its price, an ADR must raise the cap.
- **Counted verdicts can't go through a proxy** → an operator loses a gateway's budgets and logs for its counted calls (S14). Provider-side quotas, the node's own spending cap and the receipts replace them.
- **Canaries off-chain** → wrong-but-honest answers aren't slashed in v2; lazy or bad judges show on the scoreboard and lose reputation, not bond (S16).
- **Attestation trusts hardware vendors** (Intel, AMD, NVIDIA, AWS) and inference providers → the provider cap (S13) and mixed vendors; zkTLS and deterministic open models later (#85, comment 4614).

## Migration Plan

1. **This change:** the spec, the DRAFT constitution, the ADR template and ADR 0001. No code.
2. **B1 and B2:** reports on judge accuracy, agreement and injection, and on costs.
3. **The simulation:** v1 of the self-healing report, for the owner's decision on S4 (merge first) and S6 (winner refund).
4. **Contracts v2, local only,** with the split. Then the migration test from v1 side by side, and the bot against a local Forgejo.
5. **No deployment,** under rule 1. A testnet waits for #82's decisions.

## Open Questions

These are filled in by the tasks' measurements; none of them changes the specs:
- **Which 7 model families,** chosen by B1's accuracy and agreement.
- **The size of `SYSTEM_BOUNTY_START` and the verdict fee,** set from B2.
- **The rest of fee governance:** the update procedure, the caps and indexing are decided (S15, owner 2026-11-01); a voice for funders and solvers beyond staked challenges, and the validator strategy (gaining support, choosing independent seats, S19), stay open in **#100.** The demo with outside engineers is **#104.**
- **Whether a revert commit needs its own check** before it moves the head. It undoes a judged fix exactly, so the current answer is no; the simulation checks for cases where it conflicts with later fixes.
