# v3 contracts at runtime under Glamsterdam (EIP-8037) on Sepolia, v1

proof-of-fix #251. Date: 2026-11-22. Release candidate: rc2 (8d4b217). Deployment under test: the throwaway
**Sepolia rehearsal** (`contracts/deployments/sepolia-rehearsal/chain-11155111.json`, RaceV3
`0x4dc5cFADaf7f94F3305E14275831dCF816Ee7A38`, deployed 2026-11-22 with throwaway keys; launch rules: caps off, kTop 3,
challenge size same; production windows: seal 7200 s, reveal 3600 s).

**Verdict: safe with caveats.**

<!-- VERDICT -->

No contract change is needed for the Sepolia launch, and nothing found calls for a new release candidate. The core
path ran on Sepolia from registration to `result`, with every transaction at the tools' own gas limits: register,
the k = 1 draw of the genesis validator, seal, receipt, reveal, usage report, `result`, plus the keeper's `post`,
`signal` and `drawAudits`. Every transaction succeeded, each followed the same path as under the old rules, and none
of the contracts' `gasleft()` sites misbehaved. The caveats are below in "Risks and recommended fixes":

- the relayer's gas repayment undercounts (a deploy parameter, moot at Sepolia gas prices);
- `roll` with a hand-picked gas limit can revert, and `roll` itself still waits to run live (possible from 2026-11-23 18:13 -05);
- the configured RPC's limits (operational).
<!-- /VERDICT -->

## Why this was needed

Sepolia has run Glamsterdam since 2026-10-06. EIP-8037 meters *state gas* (new storage slots, new accounts, code
deposit) separately from execution gas. rc2 was tested only on anvil with pre-8037 rules, and pinned Foundry 1.8.5's
`--hardfork amsterdam` does not model EIP-8037 (it estimated a library deploy at 2.4M where Sepolia needed 16.7M). So
Sepolia itself is the only faithful test bed. This report has three parts: a static review of every gas-sensitive
construct in `contracts/src/v3`, a live run of the core path on the rehearsal deployment, and the same transactions
replayed with pre-Glamsterdam rules (the comparison is in the transactions table and the `result` measurement).

## EIP-8037 semantics that matter here

Read from the EIP text (eips.ethereum.org/EIPS/eip-8037, Last Call; values marked "not final" there), then checked on
Sepolia itself (the probe below):

- The transaction's gas is split. `gas_left = min(TX_MAX_GAS_LIMIT − intrinsic, tx.gas − intrinsic)` with
  TX_MAX_GAS_LIMIT = 2^24 (EIP-7825). The rest is the **state-gas reservoir**: `max(0, tx.gas − 2^24)`. A transaction
  whose limit is at most 2^24 has an empty reservoir.
- **`GAS` / `gasleft()` returns `gas_left` only**, never the reservoir.
- State charges draw from the reservoir first, then from `gas_left`. If both run out, it is an ordinary out-of-gas.
- CPSB = 1530 gas per state byte. A new storage slot costs 64 × 1530 = **97,920** state gas plus EIP-8038's execution
  part (cold access 2,100 and STORAGE_WRITE 10,000). A new account costs 120 × 1530 = **183,600**. Code deposit costs
  1530 per byte.
- In a CALL, the reservoir goes to the child **whole**, and the 63/64 rule applies to `gas_left` only. When the child
  reverts or halts, the reservoir goes back to its value at the child's entry.
- **`gas_left` can increase.** Clearing a slot that was set earlier in the same transaction refills its 97,920 state
  gas. The refill goes to `gas_left` before the reservoir. So `g0 − gasleft()` can be negative: under checked
  arithmetic it reverts (the EIP's Security Considerations).
- Receipt `gasUsed` includes state gas, and `eth_estimateGas` has to cover both dimensions.

### The probe on Sepolia (real transactions)

The probe is a throwaway contract, `GAS; SSTORE(0,1); GAS; SSTORE(0,0); GAS; LOG0(g0, g1, g2)` (runtime
`0x5a60016000555a60006000555a60405260205260005260606000a000`, 28 bytes). The rehearsal deployer deployed it at
`0x784dc91c35897ad79306ae507e7289088555b32f` in tx
[0x9ce4fa1b…](https://sepolia.etherscan.io/tx/0x9ce4fa1bd5289bc60704e2434b0e4c3f9ee02a2c416e893946e1bc36821b2358)
(251,002 gas, of which 183,600 is the new account and 42,840 the code deposit), then called it with chosen gas limits.

| tx gas limit | g0 (first `GAS`) | set 0→1, as `GAS` sees it | clear 1→0, as `GAS` sees it | gasUsed | Tx |
|---:|---:|---:|---:|---:|---|
| 300,000 | 284,998 | −110,028 | **+97,812** (gasleft rose) | 22,716 | [0x63e74e12…](https://sepolia.etherscan.io/tx/0x63e74e1250bf77090d7ab9b754e5606076eaa8255105d5896f4d4892cad21c91) |
| 1,000,000 | 984,998 | −110,028 | **+97,812** | 22,716 | [0xa5ac76d9…](https://sepolia.etherscan.io/tx/0xa5ac76d9a446af8b97ac260f65707dc91eaa6ec0590d27c4be23af1620a56fd4) |
| 16,777,216 (2^24) | 16,762,214 | −110,028 | **+97,812** | 22,716 | [0x6fa88a68…](https://sepolia.etherscan.io/tx/0x6fa88a68a4ce3149a67348cf71fd4814cd58874507059e089e73652aef695863) |
| 17,000,000 | 16,762,214 (capped) | −12,108 | −108 | 22,716 | [0x2b3a8945…](https://sepolia.etherscan.io/tx/0x2b3a8945d5907b09eefed340f44a47194e3250e6075f762e61db70ee5e84bd27) |
| 20,000,000 | 16,762,214 (capped) | −12,108 | −108 | 22,716 | [0x2da1d865…](https://sepolia.etherscan.io/tx/0x2da1d865e256eed05db8e8e8d2de33ae219c6df1b4de4ebe048b4c3cc9e848a0) |

This confirms at consensus level:

1. `gasleft()` is capped at 2^24 minus the intrinsic gas (15,002 here).
2. With a limit of at most 2^24, a new slot costs 110,028 as `gasleft()` sees it (97,920 state plus 12,108 execution),
   and clearing it in the same transaction **raises** `gasleft()` by 97,812.
3. Above 2^24 the state part is invisible to `gasleft()`, because it is paid from the reservoir.
4. Sepolia accepts transactions with a limit above 2^24.

**`eth_call` is not a faithful substitute above 2^24.** The same probe run as `eth_call` with a state override gave
different answers from different backends of the same load-balanced RPC. One backend applied the split, giving the
numbers above. Another (it reports `Geth/v1.17.8-stable`) returned `g0 = 29,984,998` for a 30M call, with no split at
all, and charged the 97,920 against `gas_left`. Below 2^24 every backend agreed with the real transactions. So any
simulation (`eth_call`, `eth_estimateGas`, forge's local estimate) of a transaction above 2^24 should be treated as
approximate. Only the receipt is authoritative.

## 1. Static review: every `gasleft()`, gas-limited call and gas budget in `contracts/src/v3`

There is no `call{gas: …}`, no fixed stipend, and no ETH `transfer`/`send` anywhere in `contracts/src/v3`. The
low-level calls are these:

- RaceV3's and RaceV3Annex's delegate proxies: `delegatecall(gas(), …)`, at RaceV3.sol:515 and RaceV3Annex.sol:57.
- `_view`'s `staticcall`, at RaceV3Base.sol:359.

All of them bubble a failure up as a revert. Under 8037 a starved child therefore reverts the whole transaction, as
before. It never silently skips work.

| # | Where | What it does | How EIP-8037 changes it | Loops too little or too much, reverts, or griefable? |
|---|---|---|---|---|
| R1 | RaceV3.sol:320 `uint256 g = gasleft();` and :334 `fees.settle(…, g - gasleft())` | Measures the relayer's gas for the repayment (FeesV3.sol:990–996 `_gasCost`: `(gasUsed + gasOverhead)`, capped at `gasAllowance`, times `min(tx.gasprice, maxGasPrice)`) | (a) The window has one SSTORE, `s.paid = true` (RaceV3.sol:332). `paid` shares a slot with `outcome`/`appealed`/`done` (RaceV3Base.sol:119–122), and that slot is zero before, so this is a **new slot**. Its 97,920 state gas is counted when `tx.gas ≤ 2^24` and missed when the caller's limit is above 2^24 (reservoir). (b) `gasleft()` can rise on a refill, but nothing in the window clears a slot. The window only reads (`_sub`, `panels.judges`, `_reportsDue` RaceV3Base.sol:561 is a `view`) and sets `paid`. So the subtraction can't underflow. (c) Most of `result`'s gas comes **after** the measurement: `settle` writes `settled[id]`, coin transfers to the judges and the relayer (a new balance slot each), `fees.drawn` writes `_drawnIn`, and `_decided`. A flat `gasOverhead` covers all of it (50,000 in the deployment record) | No revert, and nobody else can grief it. The **repayment undercounts** more than before. Measured live (see "What `result` measures"): the window was 218,571 gas of the transaction's 698,932, so the repayment counts 218,571 + 50,000 = 268,571 gas, **38%** of the real cost. Under the old rules it was 129,751 of 330,689, so 179,751 or 54%. So `gasOverhead` was already low and is now far too low. With a limit above 2^24, the measure also loses the 97,920 for `paid`. Economic only. On Sepolia it is moot: at about 22 wei/gas the repayment rounds to 0 micro-coins either way |
| R2 | FeesV3.sol:81 `ROLL_PART_GAS = 1_000_000`; FeesV3.sol:343–348 `roll()`: `do { rollPart(); } while (rolled == p && gasleft() > ROLL_PART_GAS);` | Runs roll parts while more than 1M gas is left (internal calls: no 63/64) | A part's cost is now dominated by new slots. `_countPart` writes `_rc[n++]` (FeesV3.sol:705), a new slot the first time each index is used. `_step` pushes a `_hist[u]` checkpoint whenever a price moves (FeesV3.sol:675, up to 3 a family and 4 shared a period, a new slot each). `_priceNew` writes `_hist`, `_first`, `_pricedAt` and `_priced` (FeesV3.sol:829–834). A families part (ROLL_WORK 100: with 3 posters, about 25 families) can write about 75 new slots: about 8.3M gas under 8037 against about 1.7M before. So **1M of headroom no longer bounds the next part**. When `tx.gas > 2^24`, `gasleft()` doesn't see the reservoir, so the loop judges by execution gas alone | **Can revert, but isn't stuck.** With a hand-picked limit, the loop can start a part with just over 1M left and run out of gas. The whole `roll` then reverts and the caller loses that gas. eth_estimateGas-driven callers (the node: estimate × 1.25 + 10,000) get a limit that runs the roll to the close. The one exception is an estimator that settles on an early-stop limit: success isn't monotonic in the limit, and the margin can then push the loop into a part it can't finish. `rollPart()` is `public` (FeesV3.sol:361), so anyone can advance one part at a time. Not griefable by others: only the caller's own transaction fails. On the rehearsal (1 family, 1 poster) parts are tiny |
| R3 | PanelsBase.sol:317–319 `try e.fees.announce(key) {} catch {} // never blocks a draw`; called at PanelsJudge.sol:329 and PanelsVerdict.sol:51, :105, :156, :440 | Lets a draw announce an unpriced family without ever failing the draw | `FeesV3.announce` (FeesV3.sol:329–336) writes `_announced[f]` and `_pending.push(f)`: 2–3 new slots, about 200–300k gas under 8037 against about 45–65k before. The try forwards 63/64 of `gas_left` and the whole reservoir. If the child halts, the reservoir comes back intact | **Not griefable in practice; no change in kind.** To make the announce fail silently while the draw succeeds, a caller has to leave the child too little gas. The parent then keeps at most 1/64 of `gas_left` (about 5k for a 300k child) for everything after the try. Every call site writes seats or panels afterwards (each SSTORE costs at least 12k execution), so the whole draw reverts instead. With a reservoir, only the child's execution part (about 35k) can be starved, and the parent's 1/64 (about 550) covers nothing. Even if it happened, the only effect is a missed announcement: `FeesV3.announce` is permissionless, and the node or anyone re-announces |
| R4 | Count-bounded loops: `DRAW_TRIES = 8` per seat (Panels.sol:148; PanelsJudge.sol:327 `tries(c.snap) * (k - have)`), K_MAX seats and shadows, `ROLL_WORK`, `PENDING_PERIODS`, MAX_REDRAWS | Bound work by counts, not by gas | Their worst case costs 2–5x more, because each new slot now costs about 110k. Execution gas is unchanged. 8037 also **lifts** the old ceiling: osaka capped a whole transaction at 2^24, while under 8037 only execution is capped and state gas can go into the reservoir (tx.gas up to 2^32−1). The deployment itself relied on this (txs up to 46.3M gas) | No new "too big to execute" risk; only cost. No loop runs a different number of times under 8037, because none uses `gasleft()` |
| R5 | Off-chain: oracle/rpc.py:228 `gas = estimate * 1.25 + 10_000` (the node and pofctl) | Gas limit for every transaction the tools send | Sepolia's eth_estimateGas includes state gas. Estimates were 0.8–4.2% above gasUsed on all 13 transactions below | Fine. Every transaction succeeded with the tools' own limits |

## 2. Live run on Sepolia (the rehearsal deployment)

### How it was driven

- **Reporter:** the rehearsal deployer, with its genesis test coins. It ran `pofctl --v3 issue register --rad-issue
  <id>`, which pays the registration fee 2, the stake 5 and the check's deposit 7.053654 POFTEST.
- **Validator:** the genesis validator (k = 1), running `python3 -m oracle run` (v3 node, fake judge, keeper on,
  on-chain exchange) with `ORACLE_FIX_SOURCE=radicle`, `ORACLE_MERGE_VIA=forge` and `ORACLE_RADICLE_RID` = the
  deployment's RID.
- **No real Radicle node was touched.** `ORACLE_RADICLE_EXEC` put a stand-in `rad` on PATH. It serves one issue whose
  comment carries pofctl's three claim lines, signed by the reporter's key for this chain, race, registration 1, the
  RID's id and the issue id. The node found and verified the claim (`find_claim`), and the fake judge passed it.
- **Keys and attestation.** The genesis validator is registered `tee` / `amd-sev-snp`, so `ORACLE_KEYS=env` is refused
  by the node: its proof type needs an SEV-SNP quote. The run used `ORACLE_KEYS=snp`, with the SEV-SNP report replaced
  in-process by a stand-in (1184 zero bytes). On-chain the receipt carries only keccak256 of the quote, and nothing
  verifies it there.
- **eth_getLogs.** The RPC is a free tier that answers eth_getLogs over at most 10 blocks. The tools were run with an
  in-process shim that splits log queries into 10-block chunks (see "Findings beside 8037").
- **Logging.** Every transaction was logged at the tools' `Wallet.send`: function, Sepolia's eth_estimateGas, the gas
  limit sent and the receipt.

### Transactions (Sepolia vs the same transaction with pre-Glamsterdam rules)

"Old rules" means the same sender (impersonated), target, calldata and block timestamp, replayed on an anvil fork of
Sepolia at the block before. The fork used pinned Foundry 1.8.5
(`ghcr.io/foundry-rs/foundry@sha256:32c8ea9e…0e043`) with `--hardfork osaka`. Every replay took the same path: same
status and same number of logs. The one exception is the ETH transfer, which logs under Glamsterdam (EIP-7708).

<!-- TABLE -->
| # | Function (contract) | Sender | Sepolia gasUsed | Sepolia estimate | Gas limit sent | Status | Old rules (osaka fork) gasUsed | Ratio | Tx |
|---|---|---|---:|---:|---:|---|---:|---:|---|
| 1 | `ETH transfer to a new account` (genesis validator (EOA)) | deployer/reporter | 204,600 | 207,391 | 269,608 | ok | 21,000 | 9.74x | [0x8458665c…](https://sepolia.etherscan.io/tx/0x8458665ca27f98fa1b33ee7b6c556ac2e792eaa5a0b3402ef81597dcd9fefb49) |
| 2 | `approve` (TestCoin) | deployer/reporter | 128,189 | 129,281 | 171,601 | ok | 46,269 | 2.77x | [0x427816b4…](https://sepolia.etherscan.io/tx/0x427816b4ab88c3ea7707dfa2f06c494124d257895595bd8fecba3a04b491441e) |
| 3 | `register` (RaceV3) | deployer/reporter | 2,416,879 | 2,494,208 | 3,127,760 | ok | 639,079 | 3.78x | [0xd965a385…](https://sepolia.etherscan.io/tx/0xd965a38500e77c2198a1468621a0d162f6c1ba58a8bc141e086e4637fb693c28) |
| 4 | `post` (FeesV3) | genesis node | 1,590,540 | 1,604,331 | 2,015,413 | ok | 364,860 | 4.36x | [0x3df9589c…](https://sepolia.etherscan.io/tx/0x3df9589cbdde7f8201421fe19eb6e203a722bf470a2fc7b77dbed9dba1538720) |
| 5 | `draw` (Panels) | genesis node | 1,429,934 | 1,454,967 | 1,828,708 | ok | 450,914 | 3.17x | [0x07139072…](https://sepolia.etherscan.io/tx/0x07139072e671ba67b1cb793b686b7bff5773dffbb225c6d83d2e9cc4be34066b) |
| 6 | `signal` (RaceV3) | genesis node | 217,352 | 226,434 | 293,042 | ok | 126,432 | 1.72x | [0x57c29de4…](https://sepolia.etherscan.io/tx/0x57c29de4109d574cf31a0ebbd704634e8f6b87d82a2c5a6663021e6d1a957d22) |
| 7 | `seal` (Panels) | genesis node | 171,010 | 173,534 | 226,917 | ok | 74,190 | 2.31x | [0x2e5b8f67…](https://sepolia.etherscan.io/tx/0x2e5b8f675f8048647312f2e87ae5c87bbe89ca25f6e1672c0820b3cec40c25d0) |
| 8 | `post` (FeesV3) | genesis node | 159,164 | 160,378 | 210,472 | ok | 100,864 | 1.58x | [0x0139f250…](https://sepolia.etherscan.io/tx/0x0139f25034c7a616a886b5b5db0d2cae02ec62f480bb6110ea560963c03b9b2d) |
| 9 | `receipt` (Panels) | genesis node | 160,320 | 162,760 | 213,450 | ok | 70,700 | 2.27x | [0xa98f7b72…](https://sepolia.etherscan.io/tx/0xa98f7b721818fd767c2280bcc05f58262d68d73a377d31689996377fbef93e84) |
| 10 | `reveal` (Panels) | genesis node | 467,519 | 484,733 | 615,916 | ok | 185,559 | 2.52x | [0x4591ee3c…](https://sepolia.etherscan.io/tx/0x4591ee3cfdde585e7351eb5f5a26f2684ee3ec77f5c32c6881e42fa8722b0f69) |
| 11 | `report` (RaceV3) | genesis node | 498,815 | 517,023 | 656,278 | ok | 151,235 | 3.30x | [0xc020b389…](https://sepolia.etherscan.io/tx/0xc020b3894c1bc5233363481f3f4466e1c399285c746d074155493fbf5337e12d) |
| 12 | `result` (RaceV3) | genesis node | 698,932 | 705,646 | 892,057 | ok | 330,689 | 2.11x | [0x12012e39…](https://sepolia.etherscan.io/tx/0x12012e39cceccd6ad1c74ab0e58b78bc77bfb5a5ca183f5f4fed30b1aee6a8e6) |
| 13 | `drawAudits` (Panels) | genesis node | 286,993 | 293,884 | 377,355 | ok | not replayed (RPC 429) |  | [0x1e290d91…](https://sepolia.etherscan.io/tx/0x1e290d912e0ef12f03a0638c09807403a5db025e1c1f2d37185bfa5363ce254e) |
<!-- /TABLE -->

### Read paths (eth_estimateGas, block 12191910)

| Call | Sepolia | Old rules (osaka fork) |
|---|---:|---:|
| `FeesV3.maxDeposit(repo, 3)` | 78,273 | 83,383 |
| `FeesV3.currentPeriod()` | 15,507 | 21,347 |
| `Panels.judges(1)` | 22,043 | 27,877 |
| `Validators.validator(genesis)` | 41,558 | 47,186 |
| `Validators.isDrawable(genesis)` | 33,831 | 39,474 |
| `FeesV3.announce(genesis)` (family already priced: a no-op) | 26,850 | 32,107 |
| `FeesV3.roll()` | reverts `TooEarly()` | reverts `TooEarly()` |

Reads are about 5–6k *cheaper* on Sepolia. That is Glamsterdam's lower intrinsic cost; the probe's g0 shows about
15,000 intrinsic against 21,000 before. Nothing in a read path writes state.

### The deployment itself (for the record, from the rehearsal's broadcast)

13 transactions, **319.2M gas** in total. They include RaceV3 at 46.3M, RegistryMaker.make at 40.7M, RaceV3Annex at
37.0M, RaceV3Endings at 36.1M, PanelsVerdict at 36.0M, FeesV3 at 31.4M and Panels at 29.9M. Each of these is above the
old per-transaction cap of 2^24, and only the reservoir makes them possible.

<!-- PENDING -->
### What `result` measures (the relayer's gas), on Sepolia and with the old rules

`RaceV3.result` passes `g - gasleft()` to `FeesV3.settle` as `gasUsed`. To read it exactly, `result(1)` was run as
`eth_call` from the genesis validator with two state overrides:
- FeesV3's code was replaced by a stub that reverts with its calldata (`0x366000600037366000fd`), so `settle`'s
  arguments come back in the revert data.
- On Sepolia, the submission's `paid` slot was set back to its pre-result value 0. The archive call at the parent
  block hit rate limits.

The call gas limit was 892,057, the real transaction's. Results:

| | `gasUsed` passed to `settle` (window RaceV3.sol:320–334) | `result` transaction gasUsed | Repaid gas `min(window + 50,000, 1,000,000)` | Share of the real cost |
|---|---:|---:|---:|---:|
| Sepolia (Glamsterdam) | 218,571 | 698,932 | 268,571 | 38% |
| Old rules (osaka fork at block 12192482) | 129,751 | 330,689 | 179,751 | 54% |

The window's growth (+88,820) is the `paid` slot: 110,020 for a new slot against 22,100 before, plus EIP-8038's dearer
cold account access. The tail after the measurement grew from 200,938 to 480,361 gas.

### The state after the run

- **Registration 1 passed.** Its verdict is Held with pass. `result` paid the judge 0.25412 POFTEST from the deposit
  and set `paid`, and the deposit's rest (6.799534) waits for the verdict to finish.
- **The audits can't be drawn yet.** `auditsDue` is 3 and `auditWaits` is true, because the rehearsal has one validator
  and an audit needs another. The window doesn't start yet either (`startWindow` → `NotReady()`).
- **Spend.** The deployer started with 0.049374 ETH and has 0.045374, of which 0.004 went to fund the genesis
  validator. The genesis validator's thirteen transactions cost less than 10^-9 ETH (about 22 wei/gas).

### Pending, and when each becomes possible

- **`FeesV3.roll()` (R2 live)** becomes possible at **2026-11-23 18:13:12 -05** (FeesV3 `start` 1795389192 plus
  PRICE_PERIOD of 1 day). Anyone can call it. The genesis validator's node does so by itself while
  `rolled < currentPeriod` (oracle/node_v3.py:810). On the rehearsal (1 family, 1 poster) a part is small, so it
  shows the loop running to the close, not the worst case.
- **The audits, the window and `finalize`/`finish`** need a second registered validator for the audit, then the
  challenge window (days). They are not gas-sensitive beyond what the table shows (no `gasleft()`).
- **The drawAudits row lacks its old-rule number.** The osaka fork couldn't start while the RPC was rate-limiting
  (HTTP 429). `scratchpad/glam/replay.py` reruns it.

## Risks and recommended fixes

1. **Relayer repayment undercount (R1).** This is economic and needs no code change. The deployment's `gasOverhead` of
   50,000 covers only the call's tail, which is now about 480k gas per `result` with k = 1 (200k before, so it was
   already short). `gasAllowance` (1,000,000) still covers `result` at k = 1. At k = 3 (kTop) the tail grows with each
   judge paid (a new balance slot each), so 1M could bind. Both are FeesV3 constructor parameters (`caps`).
   - *Recommendation:* raise `gasOverhead` to about 500,000 and `gasAllowance` to about 2,000,000 in the deploy plan if
     the repayment should mean anything. On Sepolia at about 22 wei/gas the repayment rounds to 0 micro-coins whatever
     the values, so it can also wait.
   - *Longer term (a later RC, not now):* measure the whole call, for example `settle` paying from a gas reading taken
     after the transfers, or a per-judge overhead.
2. **`roll` with a hand-picked limit can revert (R2).** No code change is needed for launch. The node already uses
   eth_estimateGas × 1.25. A stuck roll can always be advanced by `rollPart()` one part at a time.
   - *A later RC could:* raise `ROLL_PART_GAS` to a bound on one part under 8037 (about 10M at ROLL_WORK 100), or have
     each part stop by work done rather than by `gasleft()`.
   - *Operational:* a caller should give `roll` the full estimate and not a smaller limit.
3. **Simulation above 2^24 isn't reliable.** As the probe shows, backends disagree. For any transaction above 2^24 (the
   deploy's biggest are 29–46M), use the receipt of a real transaction, as the rehearsal deploy did with
   `--skip-simulation` and Sepolia's estimate. The tools' own transactions are all far below 2^24.
4. **R3 (`try announce`) and R4 (count-bounded loops)**: no action.
<!-- /PENDING -->

## Findings beside 8037 (operational, for the launch)

1. **eth_getLogs range.** The configured Sepolia RPC (a free tier) refuses eth_getLogs over more than 10 blocks.
   `Rpc.logs` (oracle/rpc.py:197) sends one query from `from_block` to `latest`. So `pofctl --v3 status` fails with
   HTTP 400, and so would the node's seat scan (`Chain.seated`, oracle/v3.py:306). The fix is either a paid RPC tier or
   chunked, cached log queries in `Rpc.logs`.
2. **The deployment record has no `"block"`.** pofctl's `from_block()` (pofctl/v3cli.py:151) then scans from block 0.
   The fix is for scripts/deploy_sepolia.py to write the deployment block.
3. **The RPC's backends lag each other and rate-limit.** Its load-balanced backends disagree on the head, so a log query up to one backend's `latest` was refused by another ("block range extends beyond current head block"). That crashed the node once, mid-window: it was restarted, resumed its round from disk and revealed in time. Under the node's rescans and the keeper's retries the RPC answered HTTP 429. The keeper also estimates `startWindow` on every pass while it can only revert `NotReady()`: 38 estimate-reverts in about 20 minutes, with no transaction sent and no gas spent. It should back off.
4. **A `tee` genesis validator can't run with `ORACLE_KEYS=env`.** It needs `snp` on its SEV-SNP host, which is by
   design. Rehearsals need a stand-in report, as here.

## Method and reproducibility

The scripts lived in the session's scratchpad and are not committed, because they handle the throwaway keys through
the environment:

- `run_tool.py` runs pofctl or the oracle in-process, with the transaction log, the log-chunking shim, the stand-in
  SEV-SNP report and the deployer's key for pofctl.
- `replay.py` is the anvil osaka fork replay.
- `probe_tx.py` is the real-transaction probe; `probe.py` is its `eth_call` variant, which showed the backends disagreeing.
- `measure.py` reads `result`'s measured gas with the `settle`-stub override.
- `reads.py` collects the read-path estimates.

The raw numbers are in `reports/glamsterdam-runtime-v1.json`. No key, RPC URL or secret appears in this report or the
JSON.
