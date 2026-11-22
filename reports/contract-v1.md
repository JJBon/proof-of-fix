# The local contract, v1 (proof-of-fix#56 task 4.1, 2026-10-30)

**Command:** `scripts/contracts.sh test --gas-report` (Foundry v1.8.5 and solc 0.8.37 in the pinned image, no network but localhost). Main at `f68fcc5`: **135 tests pass in 13 suites, 0 fail.** Sizes from `forge build --sizes` in the same image.

**Nothing here is deployed** beyond a throwaway anvil (rule 1). The prototype has no audit and holds no real funds.

## What works
| Part | Design | PR | Tests |
|---|---|---|---|
| **Baskets:** per-coin escrow, received-amount checks, pull payouts, withdraw-only mode for each coin, caps | D5, D6 | #69 | `Baskets.t.sol` 22, plus 2 invariant suites |
| **The race:** registration, the rising price with its share locked by the first attempt, attempts, commitments, results, late fees, appeals, the paid-fix registry, merge, instalments with clawback, the issue stake and finder's fee, no target, 15/85, `timeOut` | D4, D9–D14 | #69 | `Race.t.sol` 58 (the signed quorum's tests included), plus 2 invariant suites |
| **The idle sunset** counted from opening, reopening or the last checked submission; attempts don't keep a bounty alive | D11 | #74 | in `Race.t.sol` |
| **Signed results:** EIP-712 digests binding the chain, contract, action, every argument and a nonce, each used once, from a quorum of more than half of keys fixed at deployment | D3 | #75 | in `Race.t.sol`: too few signatures, a duplicate signer, a replayed signature, cross-action and cross-contract replay, a malleable signature, the oracle set |
| **`quote()`:** a separate lens with no state, and its CLI (`scripts/contracts.sh quote`) | D8 | #76 | `Quoter.t.sol` 4, plus every replayed event's quote (below) |
| **The token:** fixed emission with 1 % decay per period, a 1 % founder's share for 208 periods, no genesis, weights from the signed results, the reporter's forfeit above 300 %, pull claims, a fixed close period with a grace week | D15 | #77, #79 | `Token.t.sol` 19, plus an invariant suite |
| **The local bounty loop:** a throwaway Forgejo and anvil, the bot, one issue from a failing fix to a merged and paid one | D8 phase 4 | #78 | `scripts/bounty-loop.sh` (end to end; see below) |
| **Keyless migration:** a new version swaps 1:1 with burn, keeps one emission schedule and doesn't double the founder's share | D15 | #83 | `Migration.t.sol` 11 |
| **The replay:** simulated runs replay to identical balances | D7 | #72, #77 | `Replay.t.sol` 13 |

**Fuzzing:** 256 runs per fuzz test; the invariant suites use 64 runs of depth 64 (`contracts/foundry.toml`). The suites run deeper with `FOUNDRY_INVARIANT_RUNS`.

**The token is parked** (owner, 2026-10-30, #82): the launch is coin-only, with no token emission, and the token can be switched on only by a later version through the migration. It stays built and tested.

## Gas per step
Median gas per call on `Race.t.sol` (from [`costs-v1`](costs-v1.md), main `5da2c56`; the Race is unchanged since). The dollar column uses the same prices as costs-v1: 0.05 gwei execution on a layer-2 chain, ETH at about $2,700, and a $0.01 data fee per transaction. Those prices are assumptions dated there.

| Call | Gas | Per transaction | Per paid fix |
|---|---|---|---|
| `register` | 273,289 | $0.047 | 3.30 |
| `accept` | 149,126 | $0.030 | 3.30 |
| `pledge` | 159,408 | $0.032 | 1 |
| `attempt` | 125,053 | $0.027 | 2.25 |
| `commit` | 295,087 | $0.050 | 1.54 |
| `result` (signed by the quorum) | 205,594 | $0.038 | 1.54 |
| `merged` | 202,838 | $0.037 | 1 |
| `settle` | 391,429 | $0.063 | 1 |
| `claimInstalments` | 104,995 | $0.024 | 1 |
| `withdraw` | 53,800 | $0.017 | 2 |
| `sunset` | 90,577 | $0.022 | 0.5 |
| `claimRefund` | 169,941 | $0.033 | 0.5 |
| **One paid fix** | **3.5 million in 19 transactions** | **$0.67** | |

- **Registering is the largest item:** 39 % of the gas. 3.3 issues are registered for every one paid. Costs-v1 proposes keeping unfunded issues off-chain until someone pledges.
- **With #85's on-chain head** (60,000 gas, not built; an assumption), costs-v1 gets 3.6 million gas in 20 transactions, or $0.69 per paid fix. That's 35 % of a paid fix's whole cost with judge-grade models ($1.96), and 84 % with cheap ones ($0.81).

**The full suite's medians** for the same calls differ: for example `register` 204,889 and `result` 226,202, because the replay and invariant suites call them with other arguments. The table keeps `Race.t.sol`'s, which is what costs-v1 prices.

**The token's calls,** if it's switched on: `record` 138,052 ($0.029), `claim` 103,652 ($0.024), and the migration's `swap` 112,871 ($0.025). `quote()` is a view, at 99,772 gas when called from a transaction.

## The replay (D7)
Each file is `python3 -m pof.sim market run --contract --export-events`: a 2-week run in the contract-shaped configuration (`pof.params.CONTRACT`). After every event, the test checks every touched account's net and every bounty's pot for **exact equality** with pof's ledger, to the micro-credit (1e-6), and that the bounty's quote equals pof's `Market.quote`.

| Run | Seeds | Events | Result |
|---|---|---|---|
| The race (coin) | 1, 2, 3, 4, 8, 9, 10, 15, 60 | 1,331 | identical on every event |
| With the token on (#58's emission) | 1, 5, 7, 15 | 733 | identical, token balances included; seed 15 has a registration inflated beyond the tolerance, and every token run has 0-coin bounties that closed paid |
| **Total** | 13 runs | **2,064 events, 1,344 quotes** | **13 of 13 pass** |

## The migration (D15)
- **No keys:** anyone can deploy a new Token and Race. The new Token names the version it continues, and must keep its schedule and its founder.
- **`swap()`** burns old tokens 1:1 and mints new ones, with no deadline.
- **One schedule across versions:** the new version mints each period's emission less what the old one *committed* in that period. The committed amount is final; the running `minted(p)` isn't, because old claims can still arrive.
- **The oldest version with a weighted close in a period takes that period's emission.** The old contract can't be changed. The side effect, recorded in the design as a risk: closes on v1 can delay v2's emission, but can't add to the supply.
- **The founder's share** is paid exactly once per period across versions.
- **Verified** by `Migration.t.sol` (11 tests): the swap through a chain of versions, a swap years later, closes in the same and different periods claimed in either order, a fuzzed six-period run, and two real Races sharing days and periods.

## The bounty loop
`scripts/bounty-loop.sh` on main `f68fcc5` **passed end to end** (rerun for this report). The run:
1. One issue was registered and pledged.
2. Solver A's fix failed its tests, and the quorum's signed result was relayed.
3. Solver B read the quote (a price of 58.31 at a locked 70 % share of the cap), and its fix passed and was merged.
4. The bot settled the bounty on day 35, the day its last instalment was released.
5. The close's tokens were claimed in period 5.

Final balances, in micro-mUSD (wallet plus credit):

| Account | Balance |
|---|---|
| reporter | 1,010,291,457 |
| funder | 929,400,002 |
| winner | 1,057,208,541 |
| failed solver | 998,900,000 |
| infrastructure | 3,000,000 |
| oracle | 600,000 |

The loop runs anvil without EIP-170's size limit, because Race is too large (below).

## Sizes
| Contract | Runtime size (bytes) | Margin under EIP-170 (24,576) |
|---|---|---|
| Race | **27,079** | **−2,503 (over)** |
| Token | 7,022 | 17,554 |
| Quoter | 2,733 | 21,843 |

**Race can't be deployed on any public chain as it is.** The split is folded into #85's contracts v2 (task 5.1: `Race`, `Heads`, `Pool` and the verdicts' quorum, with no token calls). v2 changes Race anyway, and the token's calls leave with the coin-only launch.

## What's left before any audit
Aligned with #82 (testnet readiness) and #85 (self-healing code):
1. **The judges are measured (#85 B1):** accuracy on real fixes, how often the model families agree, prompt injection. Every result here still rests on the assumed accuracy.
2. **The simulation of #85** (tasks 4.1–4.4): the tiers, escalation, the head and system issues, the winner's check refund, coin only, and the attackers.
3. **Contracts v2 (#85 tasks 5.1–5.7):**
   - the size split under EIP-170;
   - the head registry;
   - the tiers on-chain;
   - the constitution's hash, ADRs and challenges;
   - the pool;
   - the migration from v1;
   - the replay on v2's shape.
4. **The bot v2 (#85 tasks 6.1–6.2):** heads applied to mirrors, and the watchers' system issues.
5. **Security before a testnet (#82 C):**
   - an internal review and threat model;
   - Slither, with its findings triaged;
   - longer fuzzing and invariant runs;
   - a private channel for reporting vulnerabilities.
6. **Before mainnet:** an external audit and the go-live checklist (#15). No real funds until then.
