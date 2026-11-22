# Contracts v2: started (proof-of-fix#85, tasks 5.1–5.2)

Task 5.1 splits v2 under EIP-170 (design S10) into `RaceV2`, `Heads`, `Pool` and the verdicts' quorum (`Verdicts`), coin only. **v1 stays as it is:** deployed on the devnet and untouched. v2 sits beside it, and the move from one to the other is task 5.13.

## Sizes (`scripts/contracts.sh sizes`)
After task 5.2 (task 5.1's in brackets):

| Contract | Runtime (bytes) | Margin under 24,576 |
|---|---|---|
| `RaceV2` | **24,457** (22,525) | **119** (2,051) |
| `Verdicts` | 1,410 | 23,166 |
| `Heads` | 1,091 (582) | 23,485 |
| `Pool` | 1,398 | 23,178 |
| `QuoterV2` | 2,430 | 22,146 |
| *v1 `Race`, for comparison* | *23,065* | *1,511* |

`RaceV2` is 540 bytes smaller than v1's Race: the token calls are gone, and the quorum check is a call to `Verdicts`. It also has none of the views that only pass through to `Verdicts` (the keys, the quorum, the used digests); those are read on `verdicts()` directly, to keep room for tasks 5.2–5.8.

## What changed from v1
- **Coin only (S6):** no `Token`, no `token()`, and no token record when a bounty closes paid.
  - **The inflation rule stays, on the coin:** a registered weight above `inflationPct` (300 %) of the merge estimate still forfeits the reporter's finder's fee, which stays in the pot and is refunded by input. That's v1's rule minus the token's half.
- **The quorum is a contract, `Verdicts`:**
  - the same rules and errors as v1's `OracleAuth` library: at least the quorum of distinct keys, signers in strictly increasing order, each digest once, high-s signatures refused;
  - one key set shared by every v2 contract;
  - anyone may call `authorize`, but used digests are kept **per caller**, so nobody can spend another contract's digests. Each consumer also signs over its own EIP-712 domain.
- **The EIP-712 domain is version `"2"`:** a v1 signature can't be used on v2.
- **The day count starts at a fixed time:** by default the deployment. A later version may pass an earlier start to keep its days (D15).
- **`Heads`:** the head registry's **genesis only**. Each repository's head and the constitution's hash are fixed at deployment; nothing moves a head yet (5.2, 5.9, 5.10).
- **`Pool`:** the sponsors' pot. Anyone funds it, in the fee coins, credited by what actually arrived. It has **no withdraw function and no owner**; its spending rules come with 5.10 and 5.11.
- **Keyless throughout:** no owner, admin, proxy, upgrade or pause.
- Each later task has a TODO hook in the code, named by its task number.

## Gas against v1 (the replay's 13 seeds, mean)
| Call | v1 `Race` | v2 `RaceV2` | Change |
|---|---|---|---|
| `accept` (signed) | 196,724 | 198,422 | +1,698 (a call to `Verdicts` instead of a library) |
| `result` (signed) | 304,629 | 306,304 | +1,675 |
| `merged` (signed) | 216,674 | 218,326 | +1,652 |
| `settle` | 279,715 | **156,576** | **−123,139** (no token record) |
| `register`, `attempt`, `commit`, `pledge`, `claimInstalments`, `sunset` | — | — | unchanged (±22) |

So a paid fix costs less on v2 than on v1: the three signed calls add about 5,000 gas, and settling saves about 123,000.

## Tests
- **v1's suites ported to v2, all passing:**
  - Race: 57 tests. The 8 token tests became their coin-only counterparts (the inflation rule's finder's fee, a 0-coin close paying nothing), and there are new tests for v2's parameters, a shared `Verdicts`, and a stranger who can't spend a Race's digest.
  - The invariants (2 suites).
  - The quoter.
  - **The replay: all 13 seeds match the simulation to the micro-credit,** including the 4 token seeds' coin side (seed 15 has an inflated registration, which forfeits its finder's fee on v2 too).
- **New tests for the split** (`SplitV2.t.sol`, 8 tests):
  - `Verdicts`' rules, and that it has no privileged call;
  - `Heads`' genesis and its checks, with no write function;
  - `Pool`: funding, a coin that charges on transfer, and no way out.
- **v1's suites are unchanged:** 135/135.
- In all, 219 contract tests pass.

## Devnet
`scripts/devnet.sh deploy-v2` deploys v2 beside v1 on the devnet (chain 7193, Osaka, EIP-170 enforced).
- It uses the same keys and quorum as v1: from OpenBao, or `DEVNET_KEYS=insecure-local` for tests.
- The genesis head is the commit deployed, and the constitution's hash is `CONSTITUTION.md`'s sha256 at that commit.
- The record goes to `contracts/deployments/devnet-v2.json`.
- **Tested** on a throwaway devnet (port 8548) with public test keys:
  - every contract deployed;
  - `Verdicts.quorum()` reads 3;
  - `RaceV2.verdicts()` is that `Verdicts`;
  - `Heads.head(repo)` returns the deployed commit and the constitution's hash.

  That record isn't committed. The owner's run makes the real one.

## Task 5.2: the verdict v2 and the head registry (design S1, S11)
- **The verdict v2,** one EIP-712 struct for the result and the merge:
  `Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)`.
  - `result(Verdict, Fee[], sigs)` signs `Result(Verdict verdict,Fee[] fees)`, and records the base and the receipt's hash on the submission.
  - `merged(Verdict, weight, sigs)` signs `Merged(Verdict verdict,uint256 weight)`, and moves the head.
  - Both take only the issue tier (`WrongTier`), the bounty's own repository, and the quorum.
- **Issues name their repository** at registration: one in the registry, or 0 outside it (S8, a project with human maintainers, where a merge moves no head). An unknown repository is refused.
- **`Heads` moves a head** only when its mover calls, and only if the verdict's base is the head (`StaleVerdict` otherwise). Each head records its bounty, submission and verdict hash. **`RaceV2` deploys `Heads` in its constructor,** so the mover is fixed at creation with no key and no address prediction.
- **A stale merge reverts whole:** the winner keeps its place, its locked share and its deadline, and nothing is spent. The judges check the rebased fix on the new head and sign a new merge naming the rebased commit; the checked commit and the rebased one both count as paid (D10).
- **A pass checked on an older base still wins its place in the queue;** only the head's move needs the current base.

### Gas (the replay's 13 seeds, mean; every replayed bounty is outside the registry)
| Call | 5.1 | 5.2 | Change |
|---|---|---|---|
| `result` (signed) | 306,304 | 359,978 | +53,674: the base and the receipt's hash stored on the submission (two new slots), and the 10-field struct in calldata |
| `merged` (signed) | 218,326 | 226,627 | +8,301 |
| `commit` | 258,890 | 263,177 | +4,287 (the submission's two new fields) |
| `register` | 205,753 | 207,873 | +2,120 (the repository) |
| `accept`, `settle` | — | — | +46, +48 |

**A merge that moves a head** costs 297,026 at 2 of 3, against 216,858 outside the registry (+80,168: the head's new bounty, submission and verdict slots, and the call to `Heads`).

### Tests
- `VerdictV2.t.sol`, 13 tests:
  - the head moves and records its verdict;
  - the result records its base and receipt;
  - the receipt, base and seed are signed;
  - **a stale verdict is refused and the winner keeps its place,** then the rebased fix merges;
  - a pass on an old base still wins;
  - **the tier is signed and checked** (a constitution verdict refused, a relabelled one fails its signatures);
  - the repository must be the bounty's; unknown repositories are refused at registration;
  - no head moves outside the registry;
  - a merge must pass and name the winner;
  - only the race moves a head; a merge needs the quorum;
  - gas.
- `HeadsInvariant.t.sol`: random wins, merges (on the head, stale, under-signed), expiries and strangers calling `Heads.move`, with reverts treated as failures. **The head is always the last commit the quorum merged on the head:** 64 runs, 4,096 calls.
- The ported suites (Race, invariants, quoter, split) now use verdicts v2. **The replay still matches all 13 seeds to the micro-credit.**
- In all, 233 contract tests pass, v1's 135 unchanged.

### Devnet
`scripts/devnet.sh deploy-v2` now takes `Heads` from `RaceV2`. Tested on a throwaway devnet (port 8549, public test keys): `race.heads()` is the registry, `heads.mover()` is the race, and the genesis head is the deployed commit. That record isn't committed.

### Left for later
- **`RaceV2` is 119 bytes under the limit.** 5.7 (check fees) has to move code out of it first, for example the appeals or the fee payouts into their own contract or library.
- **#94's oracle node still signs v1's `Result`:** it moves to the verdict v2 in node task 6.3, as does the bot.
- 5.3 draws by the signed seed; 5.6 challenges receipts; 5.7 pays the rebased fix's check.
- **Possible saving:** the base and receipt on the submission (about 44k gas a result) could become event fields. A receipt challenge (5.6) can prove a counted verdict from `Verdicts.used`, with no storage. Left to 5.6.

## Task 5.3: the tiers on-chain (design S2)
**What's built** (`Verdicts`, `RaceV2`):
- **The issue tier:** a result or a merge counts only with **2 signatures from the 3 judges drawn** with the submission's seed (`ISSUE_JUDGES` = 3, `ISSUE_QUORUM` = 2, constants). A key that wasn't drawn is refused (`NotDrawn`), even beside a drawn one, and the whole set's quorum doesn't stand in for the draw.
- **The draw** is a Fisher-Yates shuffle of the keys driven by the seed, walked in order: `Verdicts.drawn(seed, bounty, submission, consumer)` is a view, so anyone recomputes it.
- **The seed is fixed at the commit, not chosen by the judges or the relayer:** `keccak256(block.prevrandao, commitment, id)`, stored on the submission. The verdict signs it (5.2) and the race refuses any other (`Refused`).
- **Recusal:** the operators' disclosed accounts are fixed with the keys (`Verdicts`' constructor, pairwise with their seats). A key whose operator is a party to the bounty (`RaceV2.isParty`: the issue's reporter, the submission's solver, or anyone who pledged in a fee coin) is recused, the next key in the shuffle sits, and `KeyRecused` records it.
- **The constitution tier** (`authorizeAll`): the version's quorum from the keys that sit. A recused key's signature is refused (`Recused`), and the threshold stays 5 (5 of the 6 who sit). Nothing in `RaceV2` uses it yet; ADRs and challenges come in 5.10.
- **No function changes the counts, the keys or the operators:** the ABI listing test covers every external function of `Verdicts`.
- **Every other signed action** (accept, junk, refuseSimilar, appealResult, challengeUpheld) keeps the version's whole-set quorum, as before.

**The EIP-170 split, continued.** The draw's check needed room `RaceV2` didn't have (119 bytes), so `RaceV2` is now three contracts with one storage layout:
- `RaceV2Base` (abstract): the types, the state, the views the internals use, and the internals;
- `RaceV2`: the race's actions, its struct views and `isParty`;
- `RaceV2Annex`: its rarely called actions, moved unchanged (the appeals, `withdrawIssue`, `junk`, `refuseSimilar`, `timeOut`, `mergeExpired`, `challengeUpheld`).
  - `RaceV2` deploys it in its constructor with its own parameters and delegates those calls to it (DELEGATECALL), so they run in `RaceV2`'s storage with its balances and its caller.
  - Its address is an immutable on `RaceV2` (`annex()`): no key, no upgrade. Called directly, its functions refuse.
- **`RaceV2`'s external ABI is unchanged** except `isParty` and `annex`. The types and errors now live on `RaceV2Base` (Solidity doesn't resolve an inherited type through the derived contract's name), so the tests, `QuoterV2` and `DeployV2` name them there.

### Sizes
| Contract | Runtime (5.2) | Runtime (5.3) | Initcode (5.3) |
|---|---|---|---|
| `RaceV2` | 24,457 | **22,242** (2,334 free) | **45,322** (3,830 under EIP-3860's 49,152) |
| `RaceV2Annex` | — | 16,777 | 18,594 |
| `Verdicts` | 1,410 | 3,572 | 4,493 |

**Initcode is now the tighter limit:** `RaceV2`'s includes the creation code of `Heads` and `RaceV2Annex`. If 5.4 or 5.7 needs more, `RaceV2Annex` (or `Heads`) can be deployed separately at a precomputed address and checked by code hash, instead of inside the constructor.

### Gas (the replay's 13 seeds, mean)
| Call | 5.2 | 5.3 | Change | Why |
|---|---|---|---|---|
| `commit` | 263,177 | 284,435 | +21,258 | the seed stored on the submission |
| `result` | 359,978 | 383,716 | +23,738 | the draw (a shuffle of 3 to 7 steps) and the drawn-only check |
| `merged` | 226,627 | 252,448 | +25,821 | the same |
| `appeal` | 319,622 | 345,883 | +26,261 | the delegation, and the new submission's seed |
| `accept` | 198,468 | 198,842 | +374 | the call through Verdicts' shared check |
| others | | | under ±30 | |

A recused key adds one `isParty` call (a few SLOADs, plus one per fee coin) for each of its operator accounts, only when the draw reaches it.

### Tests
- `TiersV2.t.sol` (13 tests): the counts; the operators' checks; **"Two of three"**; too few signatures; **a judge not drawn**; **"The draw is reproducible"** (and the seed is the commit's); the draw spreading over the 7 seats (700 draws, each seat 240-360 times); **"The owner solves a bounty"** (the owner's seat recused, the next sits, `KeyRecused` emitted, the owner's key refused); the owner as funder or reporter; the owner's seat judging otherwise; the annex running only through the race; **"Four of seven"**; **"The owner writes an ADR"** (5 of the 6 who sit).
- The ported suites now sign with the drawn judges. **The replay still matches all 13 seeds to the micro-credit** (v1's replay too).
- In all, 246 contract tests pass, v1's 135 unchanged.

### Devnet
`scripts/devnet.sh deploy-v2` deploys `RaceV2Annex` with the race (`ANNEX=`, `annex` and `annexCodehash` in the record) and passes operators from `DEVNET_OPERATORS`/`DEVNET_OPERATOR_KEYS` when set. Tested on a throwaway devnet (port 8550, public test keys, 5 oracles, quorum 3): `RaceV2` 22,242 bytes and `RaceV2Annex` 16,777 bytes on-chain, `ISSUE_JUDGES` 3 and `ISSUE_QUORUM` 2, and `drawn` returns 3 judges. That record isn't committed.

### Left for later
- **The seed's limits:** the block's proposer can bias RANDAO by one bit (propose or skip), and a solver who is also the proposer could grind it. On a layer-2 whose RANDAO the sequencer sets (or holds constant), the seed is only as good as the sequencer. Before a public chain, take the seed from a randomness beacon or the sealed verdicts' own commit-reveal (5.5).
- **#94's oracle node and the bot** sign with the version's key set; they must sign only when drawn (node task 6.3).
- **Initcode** (above): 3,830 bytes left.

## Task 5.4: seats, keys and the provider cap (design S13)
**What's built** (`Verdicts` only; `RaceV2` is unchanged):
- **Seats fixed at genesis** (`Verdicts.Genesis`): each seat's key (0 for a vacant seat), a **distinct model family**, a provider with **at most 2 seats per provider** (`PROVIDER_SEAT_CAP`), the operators' disclosed accounts by seat, the quorum, the **allowed checker images** and the **accepted attestation types**. At least the quorum of seats must be filled at genesis.
- **Key rotation** (`rotate`, then `activate` by anyone after `KEY_ROTATION_DELAY` = 7 days): signed by the **new key itself**, the seat's **current key**, and **the quorum of the other seats' active keys**, under `Verdicts`' own EIP-712 domain (`rotateDigest` prints the digest). The image must be on the allowed list, and the attestation of an accepted type with its hash (except the devnet-only type `none`). A key serves one seat, once; one pending key per seat.
- **The join flow (#104):** a vacant seat (operator, family and provider fixed) takes its first key by the same `rotate`, with no current key to co-sign. Once filled, it only rotates.
- **Suspension:** the quorum of the other seats publishes it (`suspend`); it takes effect after 7 days; **the seat's own key lifts it at any time** (`resume`). A vacant or suspended seat is neither drawn nor counted. The bond-based suspension is 5.8's hook.
- **No function adds, removes or replaces a seat, an operator, a family, a provider, the counts or the lists:** the ABI listing test (`SplitV2Test.test_verdictsHaveNoPrivilegedCall`) names all 30 external functions.

### Sizes
| Contract | Runtime | Initcode |
|---|---|---|
| `Verdicts` | 3,572 → **7,321** | 4,493 → **9,428** |
| `RaceV2` | 22,242 (unchanged, 2,334 free) | 45,322 (unchanged, 3,830 under EIP-3860) |
| `RaceV2Annex` | 16,777 (unchanged) | 18,594 |

`Verdicts` is deployed on its own and passed to `RaceV2`, so its growth costs `RaceV2`'s initcode nothing.

### Gas
| Call | 5.3 | 5.4 | Change | Why |
|---|---|---|---|---|
| `accept` | 198,842 | 211,564 | +12,722 | each signer's seat read (filled, not suspended) |
| `result` | 383,716 | 397,213 | +13,497 | the same, and the active keys built for the draw |
| `merged` | 252,448 | 265,945 | +13,497 | the same |
| `commit`, `appeal` | | | 0 | |

The replay's 13 seeds, mean. The seat calls (`SeatsV2.t.sol`): `rotate` about 270k with 6 signatures (126k median, refusals included), `activate` 118k for a first key, `suspend` 140k, `resume` 63k.

### Tests
- `SeatsV2.t.sol` (14 tests), a version of 7 seats with 6 filled and 1 vacant, quorum 5: the genesis seats; **"A third seat on one provider"** (refused; two are fine); distinct named families; the quorum filled at genesis and the lists set; **the join flow** (published, too early, activated, drawn, its operator's account mapped); a join needs the new key and 5 others, and refuses outsiders; `none` only where accepted, and a TEE type needs its hash; **"An enclave redeployed"**; a rotation needs the current key; **"A key from an unlisted image"** and **"An attestation of an unlisted type"**; a key serves one seat and one pending at a time; **"A lost key"** (suspended after the delay, not drawn, not counted, can't rotate); a seat that can sign lifts its suspension; a suspension needs 5 others, not the seat itself, and can't be replayed.
- The ported suites build their `Verdicts` through `helpers/GenesisV2.sol` (each seat its own family and provider).
- **In all, 260 contract tests pass, v1's 135 unchanged, and both replays match all 13 seeds to the micro-credit.**

### Devnet
`scripts/devnet.sh deploy-v2` with `DEVNET_V2_VACANT=2` deploys 7 seats (the 5 oracle roles filled, 2 vacant), quorum 5. Tested on a throwaway devnet (port 8551, public test keys, never the owner's):
1. `join-v2 5 joiner-0`: seat 5's key published; `activate-v2 5` refused (`TooEarly`); `warp 7`; activated.
2. **The engineer's way:** `digest-v2 6 <address>` printed the digest; the joiner-1 key signed it on its own (`cast wallet sign --no-hash`); `join-v2 6 --key <address> --sig <signature> --nonce <nonce>` published it with the co-signers; `warp 7`; `activate-v2 6`.
3. `seats-v2`: all 7 seats active, 7 keys drawn from.

That record isn't committed. `devnet-keys.sh` gains the roles `joiner-0` and `joiner-1` (appended, so the other roles keep their indices; `init` creates them in OpenBao).

### Left for later
- **A staked challenge during a rotation's delay** (5.10), and changing the allowed images and attestation types by ADR (5.10).
- **The bond-based suspension** (5.8, `_bonded`).
- **#94's oracle node and the bot** read `keys()` (the active keys); an engineer's node signs with the joined key (node task 6.3).
- **Checking the attestation itself** stays off-chain, by the co-signers (S13); the devnet versions accept `none`.

## Task 5.7: check fees (design S15)
**What's built:** a new contract, `Fees` (the meter), deployed before `RaceV2` and bound by it. Without a meter (the zero address) a version keeps v1's flat check deposit and the judges' signed fee list; the replay runs that way.
- **A unit price table** in micro-coins per million units: per model family input, cached and output tokens; the sandbox's vCPU- and GB-seconds; storage MB; the ETH price (to repay gas in the fee coin); and `SERVICE_FEE` ($0.05, cap $0.25). Every entry keeps its genesis value.
- **Bounded, delayed updates:** `propose`, signed by 5 of 7 seats (`Verdicts.authorizeAll`) with the public price lists' hash as evidence; every entry within ±25 % of its current value and **at most 2× its genesis value**; `SERVICE_FEE` at most the cap; one pending at a time; in force 7 days later (`applyUpdate` by anyone, or automatically for charges). **Not built:** the staked challenge during the notice (needs 5.8's bonds).
- **Per-check caps and CI profiles:** 140,000 input and 16,000 output tokens and 20 MB per verdict; each repository's profile (test image, CPU, memory, timeout), a default for the rest; all fixed at deployment.
- **The deposit:** the worst case at the caps (3 judges at the dearest family, each with storage and the service fee; 3 CI runs at the profile's limits, or 1 with `CI_SINGLE_RUN`; the gas allowance at `MAX_GAS_PRICE`), at the dearer of the prices in force and pending. The quote shows it (`QuoterV2`: `checkDeposit`, `metered`, `serviceFee`, `judges`). Fee coin only.
- **Usage:** each drawn judge signs its measured usage with its seat's key; anyone relays it (`Fees.report`) before the result. The result settles: reports capped, each field's median, each reporting judge paid the median at its own family's prices plus the service fee, **to its seat's operator account**; the relayer its gas; **the rest refunded** to the solver; all as credits, pulled (`withdraw`).
- **The winner's refund at settlement:** once the bounty is paid, the winner's charged checks come back from what the fee-coin pot still holds after the price and the reporter's dues.

### Worked example (devnet, 2026-11-02, port 8552, public test keys, `scripts/devnet.sh fees-v2`)
The devnet's 5 oracle roles, quorum 3, every family priced at the dearest list price (Claude Opus 5.5: $4 input, $0.20 cached, $20 output per million tokens), `MAX_GAS_PRICE` 0.05 gwei.
| Step | Amount (coin) |
|---|---|
| The quote, and the deposit taken at the commit | **3.039915** |
| Judges' usage: 28,500 / 285,000 (padded) / 28,000 input tokens, 7,000 cached, about 4,000 output, 300 vCPU-s, 600 GB-s, 2 MB | median: 28,500 / 7,000 / 4,000, 300, 600, 2 |
| Each judge: tokens 0.167400 + sandbox 0.004114 + storage 0.000539 + service fee 0.050000 | **0.222053** × 3 = 0.666159 |
| The relayer's gas: 646,487 gas at 0.0076 gwei, $2,700 per ETH | **0.013322** |
| Refunded to the solver | **2.360434** |
| Kept as the checks' charge (the winner's refund at settlement) | 0.666159 |
| One judge pulled its fee (`withdraw`) | 0.222053 |

The padder changed nothing. The deposit covered the charge about 4.5 times. The relayer's repayment came within 0.5 % of the transaction's real cost (`RELAYER_GAS_OVERHEAD` 540,000, measured 536,636). That record isn't committed.

### Sizes
| Contract | Runtime | Initcode |
|---|---|---|
| `Fees` (new) | 11,754 | 14,484 |
| `RaceV2` | 22,242 → **23,628** (948 free) | 45,322 → **47,886** (1,266 under EIP-3860) |
| `RaceV2Annex` | 16,777 → 17,598 | 18,594 → 19,462 |
| `QuoterV2` | 2,430 → 3,157 | |
| `Verdicts` | 7,321 (unchanged) | 9,428 |

`RaceV2`'s initcode includes the annex it deploys; it now has 1,266 bytes left, so 5.8's bonds must live outside `RaceV2` (in `Verdicts` or their own contract), or the annex moves to its own deployment checked by code hash.

### Gas (unmetered: the replay's mean after 5.4; metered: `FeesV2.t.sol`'s medians, so the two runs differ in their bounties)
| Call | Unmetered (5.4, replay mean) | Metered | Why |
|---|---|---|---|
| `commit` | 284,435 | 445,230 | the deposit computed by the meter (`maxDepositFor` about 122k, its reads of the race) |
| `result` | 397,213 | 530,934 | the meter's settle: the medians, the payees and the credits |
| `Fees.report` (each judge) | | 389,495 | the draw recomputed (with `isParty` asked of the race) and the seat looked up |
| `Fees.propose` | | 940,171 | 5 signatures, the bounds on 26 entries, the table stored |

### Tests
- `FeesV2.t.sol` (23 tests): **"The deposit's ceiling"**, the quote, the fee coin only, the meter bound once and only to a fee coin; **"One judge pads its usage"** and **"The solver pays its checks"** (each judge's pay recomputed from the prices); **"A heavier check costs more at the same prices"**; reports capped; two reports and a silent judge; `CI_SINGLE_RUN`; a signed fee list refused with a meter; reports by keys not drawn, twice, after the result, or moved to another submission, refused; the relayer's gas bounded; **"The winner is refunded"**; **"A price jump"**, **"A service fee above the cap"**, the 2× genesis cap, 5 of 7 and one at a time, **"A price update's notice"**; an operator withdrawing; a fuzz test that the credits always add up to the deposit; the ABI listing of `Fees`.
- **The invariant suite extended:** `RaceV2MeteredInvariantTest` runs the same random races with a meter (random reports, random gas prices) and checks after every result that **the judges', the relayer's, the infrastructure's and the solver's credits add up to the deposit**, besides the books, the pots and the payouts.
- **In all, 284 contract tests pass; v1's suites and both replays (13 seeds each, to the micro-credit) are unchanged.**

### Left for later
- **5.8:** the price challenge (step 4 of the procedure) and the seats' bonds.
- **5.5/5.6:** usage inside the sealed verdict and the receipt, instead of a separate signed report.
- **5.14:** the replay with the fee model (`pof.checkgas`).
- **Gas:** a key-to-seat view in `Verdicts` and a batch `report` would cut most of a report's cost; passing the repository to `maxDepositFor` would cut the commit's.
- **Appeals** still pay their jurors from a signed list.
- **Clients:** `pofctl` (#108) shows the quote's metered fields and a `validator fees` view; #94's node signs its usage and relays it; the validator kit's watcher relays reports.

## Next
- 5.5, sealed verdicts on-chain (5.7, check fees, is done: #104's fees paid to each validator);
- and on through 5.14, one PR each.
