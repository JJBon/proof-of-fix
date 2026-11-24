## Why

A read-only audit of the v3 contracts and keeper (2026-11-23, `~/dev/pof-research/v31-polish-audit.md`, findings F1–F13,
read at `main` bafac40 with the open branches of #323 and #324) found one critical bug and several medium ones in what
is live on Sepolia v3 (RaceV3 `0xD622…9829`, rc3 at 8946b9c):

- **F1 (critical, dormant on live v3):** a draw can seat a validator whose model family was first priced *after* the
  check opened. `PanelsDraw.fill` compares `pricedFrom(family)` with the snapshot's `rolled`
  (`contracts/src/v3/PanelsDraw.sol:261`), but FeesV3 prices a check at the epoch it opened (`_epochOf[id]`,
  `contracts/src/v3/FeesV3.sol:225-229`). Then `result`, `payPanel` and `settleChallenge` revert `Unpriced` forever:
  the deposit, the bounty's queue, the pot, the challenger's stake all lock. Reproduced: 12 of 12 re-targeted counted
  panels seated the fresh family and every `result` reverted. It fires once any second family gets its first price.
- **F2:** `roll()` runs parts while `ROLL_PART_GAS` (1M) is left (`FeesV3.sol:80-81`, `:343-348`), but one part
  measured 3.1M and 4.0M gas at 3 posters even before EIP-8037; success isn't monotonic in the gas limit (the #325
  shape), and the worst part is above 2^24 under 8037 (risk R2 of `reports/glamsterdam-runtime-v1.md`).
- **F3–F5 (the keeper):** once-only calls give up after 50 refusals of any kind, `NotYet` included, so a panel with one
  late report is never paid by any keeper (F4); `startWindow`, `finish`, `release`, `result` and `refill` are retried
  every pass with no backoff (#314), and on Sepolia Infura answers with HTTP 429 storms that abort whole passes (F5);
  `payShadow` can still be closed unpaid on live v3 by short gas (#325, F3).
- **F8:** any `topUp` of one micro-coin bumps the registry's `epoch` (`contracts/src/v3/Validators.sol:383-392`), which
  re-arms every waiting draw, audit and challenge and every keeper's retry budget.
- **F10:** the node posts prices under `anthropic/claude` (`oracle/node_v3.py:65-67`) while the deployment seats
  `anthropic.claude` (`contracts/deployments/sepolia-v3.plan.json:24`, `docs/guides/run-a-validator.md:17`), so the
  priced family's price never moves and a new family named in the dotted style is never priced.
- **Who draws:** with only on-demand validators (the SEV-SNP kit's hosts sleep until the watcher sees one of *their*
  seats), nobody calls `Panels.draw` and `RaceV3.signal` for a new check: the watcher wakes a host for seats, and a check
  that isn't drawn has no seats yet. A standalone keeper on the seed host is being deployed as the operational fix
  (`~/dev/pof-research/keeper-runbook.md`); the product needs its own answer.

The owner approved this scope on 2026-11-23 as the third part of v3.1, after #310 (rebase in place) and #311 (early
reveal). Ticket: #251. Refs #314, #325, #310, #311, #318.

## What Changes

**Contracts (`contracts/src/v3`; v3.1 is a new keyless deployment, so they change freely):**

- **F1:** FeesV3 gains `drawEpoch(id)` (the check's epoch once open, else `rolled`). A counted, refill, audit or
  challenge seat goes only to a family priced at or before `min(drawEpoch(id), snapshot's rolled)`. The k = 1 hold
  counts a challenger only under the same rule. Shadows keep today's rule (a later-priced family's shadow is paid
  nothing, by design).
- **F2:** `ROLL_WORK` 100 → 40, and `roll()` runs exactly one part (no gas-dependent loop). `ROLL_PART_GAS` goes.
- **F8:** `topUp` bumps `epoch` only when the key's bucket or state changed, as `recheck` already does.
- **F9:** no change (decided: the swallowed `announce` can only skip an announcement that the next draw repeats); a
  test pins that.

**Keeper (`oracle/node_v3.py`, `oracle/rpc.py`; ships first, since it also protects live v3):**

- once-only calls aren't given up on time- or state-gated refusals (`NotYet` and the like), and their give-up is a
  wall-clock budget (F4);
- `startWindow`, `finish`, `release`, `result` and `refill` are sent only when readable state says they're due, and
  anything else refused is retried with exponential backoff per call and state (F5, #314);
- gentler polling on a public chain, a per-pass budget for the keeper's reads, a scan that skips finished checks, and
  HTTP 429 handled by pausing the keeper section without delaying a seal or reveal (F5);
- `payShadow` sent with a gas floor (F3);
- `rollPart()` in a loop instead of `roll()` (F2);
- on a deployment without F1's fix (live v3), the node's price table prices only families already priced, so no new
  family can arm F1.

**Who draws:**

- the SEV-SNP watcher gains a **draw duty**: it starts the stopped host when a check of the deployment is undrawn past
  its seed block (or a waiting one past its retry time) for a grace period, staggered per validator, so an idle network
  still draws;
- a **keeper-only node mode** (`oracle keep`): no registration, no judge, no Radicle seat; a plain gas key on any chain;
  documented with the runbook;
- **`pofctl --v3 draw <id>`**: a reporter or solver draws its own check, and `issue register` and `submit` print the
  hint.

**pofctl (#327's v3.1 list):** `status` without the keystore's password (the address from `pofctl.json` or the
keystore), the ETH balance in `status`, and `issue register` printing the Radicle issue's whole id robustly (and able to
open the issue itself).

**Deploy plan (v3.1):** `gasOverhead` 500,000 (F11; `gasAllowance` 1,000,000 and `maxGasPrice` 1 gwei unchanged), and
one family naming convention, **`provider/line`** (`anthropic/claude`), in the node, the plan, the deploy script's check,
the docs and the guides (F10).

**From the live smoke test (2026-11-23; registration 1 judged a Pass at k = 1 on Sepolia v3, now Held):**

- pofctl waits for its own approval to be visible before the next send (`issue register` failed with
  `ERC20InsufficientAllowance` right after approving), prints every transaction's hash and block (`tx`, `block` in
  `--json`), and gains `pofctl --v3 issue show --issue N` (the check's status, k, panel, deadlines, result, `finalAt`
  and the deposit's refund); `status` lists the address's registrations;
- the node posts a short verdict receipt on the Radicle issue after counting (the reason only where no sealed evidence
  is revealed);
- `oracle.rpc.Rpc` retries a 429 by default (3, Retry-After honoured) instead of failing at once;
- **no RPC key in any log line**: Infura's key sits in the URL's path, which `Rpc` doesn't strip, and the live
  validator's console shows it today; redacted at the source and at every log sink, and the printed key rotated;
- the guides' timing: about 2–3 h to a verdict on v3, then held until 6–7 validators; minutes with #311;
- the keeper-only entry point is the seed host's `oracle/keeper.py` as built (secret RPC URL, redaction, transaction
  log, address check, hourly cap), plus a configurable `Wallet.poll_s` and a cursor over finished submissions;
- the seed's Terraform gains its `keeper_secret_arns` variable and policy, and the seed's and the SEV-SNP kit's docs pin
  `create_instance = true` (a plain plan without it destroys the running host).

**The owner's decisions (2026-11-23):** the seed host's keeper is launch infrastructure with its cost line (about $0
plus small Sepolia gas); the price test in `challengersReady` and the draw duty on by default are confirmed; the genesis
node keeps its own keeper on; the snapshot's exemption code goes when v3 sunsets.

**Docs:** the k = 1 hold's real threshold (F7: 6–7 validators with room, not 3), and the newcomer's claim ceiling with
the "attempt first" advice (F6, docs only).

**The checker image's files:** the private terms #318 left in the image's inputs are removed, so the snapshot's verbatim
exemption shrinks to v3's old refs (the #318 follow-up; the image changes in v3.1 anyway).

**Not BREAKING for clients** beyond #310's ABI change: FeesV3 gains a view and loses the `ROLL_PART_GAS` constant
(only `test_rollPartsAreBounded` reads it, `contracts/test/v3/FeesV3.t.sol:1081`, and it is rewritten). It ships in v3.1's one release candidate (rc4) with #310 and #311.

**Out of scope:**

- F6's design change (D29, the newcomer cap: options (a) and (b) of the audit) awaits a separate owner decision. Only
  the docs change here.
- F7's design question (whether the hold should count only HOLD_K at launch scale): the owner's, later.
- F2's fuller fix (counting new slots as work), F11's per-judge overhead constant, F12 (binding read-back) and F13
  (faucet): info findings, not needed for v3.1.
- Applying the seed's Terraform and installing its keeper service (operations, `~/dev/pof-research/keeper-runbook.md`):
  this change commits the code and the Terraform variable they use, and applies nothing.
- v2 and its watcher.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `checking`: a seated judge's family is always payable at its check's prices; a pricing period closes in bounded
  steps; one name per model family; every check is drawn without a dedicated operator; the calls anyone may make are
  retried by state and never given up on a payment that is only late; a counted verdict is posted on its issue; no RPC
  key in a log; short rate limits retried; the guides state how long a verdict takes.
- `challenges`: only a change in who can be drawn re-opens waiting draws; the k = 1 hold counts only challengers that
  could be seated, and its published threshold is the real one.
- `bounty-market`: the result's caller is repaid about its gas; a participant's tool shows its standing without the key
  and can draw its own check; it waits for its own approval, reports every transaction, and shows a registration's
  progress; the newcomer's ceiling is published.

## Impact

- **Actors and incentives:**
  - Solvers and reporters: no check can be stuck by a newly priced family (F1); they can draw their own check
    (`pofctl draw`), paying only gas.
  - Validators: a later-priced family isn't seated on older checks' paid seats (it still shadows, unpaid as today); a
    validator's top-up no longer re-opens everyone's waits (F8); on-demand hosts wake for undrawn checks (a few minutes
    of compute each, staggered).
  - Keepers (any account): fewer RPC calls, no wasted reverting transactions, no lost payments; a keeper-only node
    needs no bond.
  - Relayers of `result`: repaid about 103 % of the measured k = 1 gas (F11).
- **Attacks considered:** pricing a new family to lock in-flight checks (F1: closed by the rule; on live v3 by the node's
  table); a one-micro-coin `topUp` to spam re-draws (F8); a short-gas `payShadow` (F3, #325); `roll()` griefed into its
  revert band (F2); RPC exhaustion through spam making honest nodes miss deadlines (F5, F13).
- **Contracts:** FeesV3 (`drawEpoch`, roll constants), `IPanels.sol` (`IPanelsFees.drawEpoch`), the PanelsDraw library
  (`fill`, `challengersReady`), Validators (`topUp`). RaceV3, its Annex and Endings, Panels, PanelsJudge,
  PanelsVerdict, Heads and SolverBook don't change, so #323's and #324's margins (RaceV3Endings 983 B, PanelsVerdict
  1,249 B) are untouched.
- **Node and tools:** `oracle/node_v3.py`, `oracle/rpc.py`, `oracle/__main__.py`, `oracle/radicle_v3.py` (the verdict
  comment), a new `oracle/keeper.py`, `seed/terraform/` and `seed/README.md`,
  `validator-kit/sevsnp/lambda/watcher.py` and its Terraform variables, `pofctl/v3cli.py` and `pofctl/cli.py`,
  `scripts/deploy_sepolia.py`, `contracts/script/DeploySepolia.s.sol`, `scripts/github_snapshot.py` and the image's
  input files. Changing `oracle/` changes the checker image's digest: expected for v3.1 (a new disk).
- **Docs:** `README.md`, `docs/take-part.md`, `docs/guides/*.md`, `validator-kit/runbook.md`,
  `validator-kit/SEVSNP-PLAN.md`.
- **Tests:** Foundry (`contracts/test/v3/`: a new `PolishV31.t.sol`, `FeesV3.t.sol`, the invariants), Python
  (`tests/test_oracle_v3.py`, `tests/test_sevsnp_watcher.py`, pofctl's and the snapshot's tests, a new keeper test),
  and the integration sets.
- **Deployment:** the v3.1 release candidate (rc4) and deployment with #310 and #311, each step on the owner's go.
