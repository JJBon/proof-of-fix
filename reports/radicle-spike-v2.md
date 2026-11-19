# Radicle spike v2: who signs `main` when v3's judges change with every draw?

proof-of-fix#251, tasks 2.1–2.6 of `openspec/changes/proof-of-fix-251-testnet-launch` (design L9, L11, L12). Run on 2026-11-18, on one machine, in Docker, on an internal network with no route out. Nothing touched Radicle's public network, a public chain or AWS. No model call (the fake judge). Simulated money only. Task 2.7, the choice, is the owner's.

## The answer

**Both (a) and (b) work on a local network with the real v3 contracts; (a) costs one identity revision per seat change and needs a link between validator keys and node keys that v3 doesn't have yet; (c) can't run, there is no enclave key provider to run it on.**

1. **(a) The seated validators as delegates works, as a mechanism.** In three runs in a row, the owner's node handed the delegate set to the seats, and the delegate set then followed every seat change the chain made: a validator qualifying, one leaving, one slashed below the floor and topped up again. Each change was one identity revision, signed by the threshold of the delegates in force (1, 3, 3, 3 and 2 signatures). Every node had the new identity within 0.45 s on this network. Each seated node's gate moved the canonical `main` to `Heads.head` at the threshold and refused anything else. An outsider and one rogue delegate changed nothing, and an unseated key proposed by a delegate was refused by every honest seat.
2. **(a)'s protection is still where the keys are.** The rogue majority (control) moved `main` and added an unseated key to the delegates, as #190's scenario G did. `verify-delegates` and `verify-head` both caught it, and readers who take the code at `Heads.head` weren't affected.
3. **(b) The chain as the only truth works with nothing to do at seat changes.** It needs zero Radicle operations per seat change. A checkout of the commit `Heads.head` names, taken from any namespace on any node, passed its tests in every case, a rogue `main` included. Its cost is what Radicle's own tools show. A fresh `rad clone` gave the **genesis** commit after a judged fix had moved the head, and the **rogue** commit after the one delegate of convenience pushed one. `verify-head` flagged both.
4. **The spike's recommendation** is (a), with (b)'s checks as what validators and tools actually rely on. That is L11's recommendation, with conditions (see Recommendation). If the owner doesn't want every validator to run a Radicle node with a review loop, (b) is the fallback, with the owner's node pushing only `Heads.head` through the same gate.

## What ran

- **Entry point:** `scripts/radicle-spike.sh --v3` (spikes/radicle/v3_spike.py). It builds #190's node image, starts everything on an internal Docker network, runs every scenario, prints pass/fail, and removes its containers and network. `scripts/radicle-spike.sh clean` removes anything a stopped run left behind. Results and node logs go to `.radicle-spike/v3/` (gitignored). The three runs' measurements are in [`radicle-spike-v2.json`](radicle-spike-v2.json).
- **The three runs quoted here,** in a row from a clean state, at commit `e24160c`:
  - **run 1:** 2026-11-18T19:47:01Z, 346 s;
  - **run 2:** 2026-11-18T19:52:55Z, 315 s;
  - **run 3:** 2026-11-18T19:58:18Z, 315 s.
  - Before and after each run: 0 containers and 0 networks with the spike's prefix.
  - All 22 scenarios passed in each run.
  - Five development runs before them failed on bugs in the script, all fixed. One of those bugs taught something about Radicle, and one about v3 (Findings 1 and 5).
- **Radicle:** heartwood 1.10.3, commit `7e1cb406…`, #190's image. The release is pinned by SHA-256 and is the only download, at image build. The nodes run on Radicle's `test` network with no seeds and static peers connected by name, as in #190.
  - Seven nodes: `owner` (who runs `rad init`), the five validators' nodes (`genesis`, `v1`–`v4`), and `solver` (the outsider who opens patches).
  - A fresh `viewer-*` node is started for each fresh-clone check.
  - Two repositories with the same genesis commit: **A** for candidate (a) and **B** for candidate (b).
- **Chain:** anvil with the real v3 contracts, deployed by `contracts/script/NodeV3Local.s.sol` (Validators, Panels, PanelScores, FeesV3, PoolV3, RaceV3).
  - The validators are real v3 node objects (`oracle/node_v3.py`) with the fake judge, driven by `tests/integration/suite_v3.py`'s network: one genesis validator, then `v1`–`v3` and later `v4`. Each registered with a bond and qualified by its shadow verdicts, with no shortcut: 24 registration checks for `v1`–`v3`, 24 more for `v4`, in every run.
  - Panels were drawn for registration checks and fixes: 82, 34 and 34 panels by the end of setup in runs 1–3.
  - Panels' windows are constants in hours (task 3.4 isn't built), so the clock moves with `evm_increaseTime`.
- **Seats** are `Validators.isDrawable`, read from the chain: every key in a `Registered` event that is drawable now. That is the set L5 means.
- **L9's stand-in.** `RaceV3.claim` moves its own `Heads` before finality (task 3.5 isn't built). So:
  - RaceV3 is deployed with no repository, so its `claim` moves nothing. The run checks this: its `Heads.repos()` is empty.
  - A separate v2 `Heads` holds A's and B's heads, with its mover an account that stands in for `merge(bounty)`.
  - The stand-in moves a head only when the winning verdict is `Final` and claimed. In each run it refused at claim, when the verdict was still in its `Window`. It moved the head 86,400 s of chain time later (86,399 s once): the k = 3 level A window, 24 h. That is the wait L9 adds before the head moves.
  - The contract doesn't enforce this rule; the stand-in does.
  - **Since #251's contract batch 2 (task 3.5), A's head is the real one.** RaceV3 serves A (L1) and moves its own `Heads` only by `merge(bounty)` at finality (L9); the spike now uses it for A (`heads_for`), and keeps the stand-in for B only (B isn't the race's repository). One run of `scripts/radicle-spike.sh --v3` on 2026-11-18 passed every scenario (S, a1–a9, b1–b10, L, I; 317 s): `RaceV3.merge` refused at the claim (`NotYet`) and moved A's head at finality, 24.0 h of chain time later (k = 3, level A). The runs 1–3 figures below are from before that change.
- **Fixes are Radicle patches (L12, task 2.5).**
  - The solver seals its commitment on RaceV3, then opens a patch whose description carries the claim (bounty, submission, salt, solver: the bot's pull-request format).
  - Each validator's node lists the patches on its **own** Radicle node, refuses a revision whose base isn't `Heads.head`, and copies the commit's tree from its own node's storage.
  - The tests (`test.sh`) run inside that validator's own node container, and the fake judge labels the fix by them.
  - The node objects read those patches as their "pull requests".
  - Each run judged three fixes, each by a counted panel of 3. Each run made 10 test runs: the 9 drawn judges' and one more validator's on a shadow or audit seat. Each ran on the commit from that validator's own node, and each exited 0.
- **No network path from the driver to the chain.** The driver's JSON-RPC goes through a `docker exec -i` pipe into a relay container: the oracle node's pinned `python:3.12-alpine` image, on the internal network.
- **Pure rules** (`spikes/radicle/seats.py`, unit-tested in `tests/test_radicle_seats.py`):
  - the seat binding;
  - `verify_delegates`;
  - `review_revision`, the rule an honest seated node signs by;
  - the `rad id update` arguments;
  - the patch reader.

### How a seat maps to a delegate (something the spike had to add)

The chain knows a validator by its Ethereum key. Radicle knows a delegate by its node key (a `did:key`). Nothing in v3 links the two: `Registration` has no field for it. The spike adds a **binding**:

- **What is signed:** each validator signs, with its validator key, its node's DID for this repository on this deployment. The signed digest covers the chain id, the registry, the RID and the DID.
- **Where it lives:** the bindings sit in the identity document itself, in a payload of our own: `xyz.proofoffix.seats`, key `bindings`. Radicle accepted the custom payload.
- **`verify_delegates`** passes only when:
  - every delegate has a binding that recovers to a seated validator;
  - every seat has exactly one delegate;
  - the threshold is a majority.
- **`review_revision`**, the rule an honest seated node signs by, also requires:
  - each new delegate has published `main` at `Heads.head`;
  - nothing else in the document changes.

## Results per scenario

Every scenario passed in runs 1, 2 and 3.

### Setup and isolation

| | Scenario | What happened |
|---|---|---|
| S | Setup (2.1) | v3 deployed. The genesis validator was active from the start. `v1`–`v3` were seated after 24 registration checks: 32.0 h of chain time in run 1, 6.0 h in runs 2 and 3. A and B started at the genesis commit, both in `Heads` and as canonical `main` on all 7 nodes. RaceV3's own `Heads` held no repository. |
| L | Largest delegate set | See Measurements. |
| I | Isolation | See Isolation evidence. |

### (a) The seated validators are the delegates (repository A)

| | Scenario | What happened |
|---|---|---|
| a1 | The genesis delegate hands over | Before: `verify-delegates` failed, naming the owner's unbound node and the 4 seats with no delegate. Each seated node published `main` at `Heads.head` through its gate. The owner, still the sole delegate, signed one revision: 4 delegates (the seats, with bindings), threshold 3, and itself removed. After: `verify-delegates` passed. |
| a2 | A fix through v3, merged on Radicle (2.5) | Judged by a counted panel of 3, passed, claimed, final, then the head moved. The seated nodes' gates pushed one by one. Canonical `main` stayed at the old head after 1 and 2 pushes, and became the fix at the 3rd (the threshold) on all 7 nodes. `verify-head` exited 0, a fresh clone gave the fix, and the patch showed as merged. |
| a3 | Outsider | The solver's own `main` was moved to an unjudged commit and a patch opened with it. Canonical `main` didn't change on any node. A seated gate refused the commit (exit 3, not `Heads.head`), and `verify-delegates` still passed. |
| a4 | Seat added | `v4` qualified and was seated on-chain. Until the revision landed, `verify-delegates` failed, naming the seat with no delegate. `v4` published `main` at the head, `genesis` proposed, and `v1` and `v2` reviewed and accepted. The identity became 5 delegates, threshold 3, and `verify-delegates` passed. |
| a5 | Seat removed | `v2` called `leave` and was no longer seated. One revision followed, accepted by `genesis`, `v1` and `v3`: 4 delegates, threshold 3. `v2`'s node was no longer a delegate. |
| a6 | Below the floor (L5) | `v4`, bonded at exactly the floor, was muted. It was slashed for silence on a counted panel within 2 registration checks, to 95.00 (runs 1 and 2) or 90.00 (run 3, slashed twice). It was still `Active`, and `activeCount` still counted 4, but it wasn't drawable: finding 7, what L5 fixes. One revision removed it (3 delegates, threshold 2). It topped up to the floor, and one revision added it back (4, threshold 3). |
| a7 | Seated nodes offline | A second fix went through v3 and the head moved. Then 2 of the 4 seated nodes went offline. The 2 online gates pushed, but canonical `main` stayed at the previous head, and `verify-head` exited 1, naming both commits. `v1` came back and its gate pushed: canonical `main` = the fix on every online node, and `verify-head` exited 0. `v4`, back online, had **not** caught up after 45 s with no sync. Its gate, which fetches first, brought it up and pushed. |
| a8 | One rogue delegate | `v4` pushed an unjudged commit to its own `main`: no change on any node. `v4` proposed adding the solver's node with a forged binding. `genesis` and `v1` refused it, and Radicle then marked the revision `rejected`; `v3`'s reject was refused as a vote on a rejected revision. The identity didn't change and `verify-delegates` passed. `v4` could still propose again afterwards. |
| a9 | Rogue majority (control) | 3 of 4 delegates skipped their gates: canonical `main` became the rogue commit, and `verify-head` exited 1, naming both commits. The same 3 accepted a revision adding the solver's node, so it is now a delegate, and `verify-delegates` failed, naming it. A checkout at `Heads.head` still gave the judged commit. |

### (b) The chain is the only truth (repository B)

| | Scenario | What happened |
|---|---|---|
| b1 | Setup | B: 1 delegate (the owner's node), threshold 1, 1 identity revision. |
| b2 | A fix through v3, nobody pushes (2.5) | Judged by a counted panel of 3, passed, claimed, final, then the head moved. The checkout on the solver's node and on `v3`'s node gave `Heads.head`, from the solver's namespace, and its tests exited 0. `verify-head` exited 1, naming genesis as canonical `main` and the fix as the head. A fresh `rad clone` gave **genesis** (output below). |
| b3 | The delegate of convenience pushes the head | The owner's node pushed through the same gate. Canonical `main` = the fix on all 7 nodes, `verify-head` exited 0, and a fresh clone gave the fix. |
| b4 | Outsider | The solver's own `main` moved to an unjudged commit and a patch was opened. Canonical `main` didn't change, the gate refused the commit (exit 3), and the checkout still gave `Heads.head`. |
| b5, b6, b7 | Seat added, removed, below the floor | At each of a4, a5 and a6: B still had 1 identity revision, and the checkout on another node gave `Heads.head(B)`. |
| b8 | Seated nodes offline | With `v1`'s node down, the checkout on `v3`'s node gave `Heads.head(B)`. |
| b9 | Rogue delegate | The owner's node pushed an unjudged commit: canonical `main` = the rogue commit, from one delegate. `verify-head` exited 1. A **fresh `rad clone` gave the rogue commit** (output below). A checkout on the same fresh node still gave `Heads.head(B)`, and its tests exited 0. |
| b10 | Rogue majority | Not a separate case: with one delegate, b9 is the majority. |

### What a fresh `rad clone` shows under (b) (run 3, verbatim)

After the judged fix moved the head and nobody pushed (b2, node `viewer-b2`). `Heads.head(B)` was `1a0ce4a…`:

```
$ git rev-parse HEAD
ad2f661fe9aa42958f391a5bc0db8126e1125a68
$ git log --oneline -1
ad2f661 genesis: add() is wrong (proof-of-fix#251)
$ rad patch list --all
│ ●  568097a  fix add() on B  solver  z6Mko2v…mqieibv  -        1a0ce4a  +1  -1  8 seconds ago         │
```

After the delegate of convenience pushed an unjudged commit (b9, node `viewer-b9`). `Heads.head(B)` was still `1a0ce4a…`:

```
$ git rev-parse HEAD
5a7cf9d5a6111dea7f09fe2b3d50b846ba5cb762
$ git log --oneline -1
5a7cf9d a rogue change, never judged (proof-of-fix#251)
$ rad patch list --all
│ ●  29055cd  An unjudged change  solver  z6Mko2v…mqieibv  -        9e3a5a4  +1  -0  2 minutes ago         │
│ ✓  568097a  fix add() on B      solver  z6Mko2v…mqieibv  -        1a0ce4a  +1  -1  2 minutes ago         │
```

So under (b), `rad clone` and `git clone` give whatever the delegate of convenience last pushed. A reader who doesn't run `verify-head` or a checkout by hash can't tell.

**The web view wasn't run.** The pinned release has no `radicle-httpd`, and downloading another component is outside this spike's rules. By Radicle's rule (assumed, not observed), the explorer shows the canonical default branch, so it would show what the fresh clones showed.

## Measurements (2.2)

**Identity operations per seat change** (a). Identical in all three runs:

| Change | Delegates (threshold) before → after | Revisions | Signatures | Wall time, proposal → the deciding signature |
|---|---|---|---|---|
| Handover (a1) | 1 (1) → 4 (3) | 1 | 1 | 0.32–0.34 s |
| Seat added (a4) | 4 (3) → 5 (3) | 1 | 3 | 1.51–1.56 s |
| Seat removed (a5) | 5 (3) → 4 (3) | 1 | 3 | 1.51–1.52 s |
| Below the floor (a6) | 4 (3) → 3 (2) | 1 | 3 | 1.51–1.52 s |
| Back above the floor (a6) | 3 (2) → 4 (3) | 1 | 2 | 0.97 s |

- **Signatures needed:** one revision per change, signed by the threshold of the delegates **in force**, not the new set: the author's signature comes with the proposal, and the reviewers add theirs. Each signature is a node that has fetched the proposal, read the chain, and run `review_revision`.
- **How every v3 seat change looks:** a qualification, a `leave`, a slash below the floor, a top-up and a suspension are all seat changes. Each costs one such revision.
- **The wall times are this machine's:** nodes reviewing one after another over a local network, not a protocol constant.

**Time for every node to converge** (a). Measured from the start of the deciding command: the signature that reached the threshold, or the push that did. No sync was forced. The probe resolution is about 0.2 s.

| What | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Identity revision, all 7 nodes (a1, a4, a5, a6 ×2) | 0.37–0.43 s | 0.36–0.43 s | 0.36–0.45 s |
| Canonical `main` of A at the threshold push (a2), all 7 nodes | 0.49 s | 0.49 s | 0.50 s |
| Canonical `main` of B after its one push (b3), all 7 nodes | 0.46 s | 0.46 s | 0.48 s |
| Canonical `main` of A once `v1` was back online (a7), from its restart, 6 online nodes | 2.09 s | 2.04 s | 2.03 s |
| `v4` back online, no sync forced (a7) | not within 45 s | not within 45 s | not within 45 s |

- **Why the numbers are small:** a push through `git-remote-rad`, and a `rad sync --announce` after an identity signature, return only once peers have fetched. So "converged" is mostly the duration of the command itself.
- **A node that was offline doesn't catch up on its own.** It fetches what it missed only when something new is announced, or when it syncs. The gate syncs first, so a seated node catches up at its next gate run.

**Largest delegate set Radicle 1.10.3 accepts** (scenario L, on a private scratch repository of the owner's node, with fresh keys made in the container):

- 255 delegates, threshold 1: accepted, in 13 ms (runs 1, 2) and 16 ms (run 3).
- 256 delegates: refused with `✗ Error: invalid delegates: number of delegates cannot exceed 255`.
- With a majority threshold, 255 delegates would also need 128 of them to have published `main` before the revision is accepted. Radicle refuses a revision whose threshold the published delegates can't meet (#190).
- So 255 is the ceiling on seats under (a). L16's launch set (7 minimum, 15 the target) is far below it.

## Isolation evidence (checked by the script, scenario I, every run)

- **The network:** `docker network inspect` reports `Internal: true` for `pof251-net`.
- **No default route** in `/proc/net/route` of any container: anvil, the relay, and the 7 nodes plus the 4 viewers.
- **Radicle node logs:** 11 nodes, each log kept in `.radicle-spike/v3/<node>.log`:
  - `0 nodes added to address book` on every node: the `test` network has no bootstrap nodes;
  - every `Connecting to`, `Attempted connection to` and `Connected to` line names a spike container or an address in the network's subnet (`172.24.0.0/16`);
  - no IP address outside that subnet appears, besides `0.0.0.0` and `127.*`;
  - no public Radicle hostname appears (`radicle.xyz`, `.garden`, `.dev`, `.network`, `seed.radicle`, `iris.`, `rosa.`).
- **The driver** had no network path to the chain: no port is published, and its RPC went through a `docker exec` pipe (59,723 calls in run 1, 48,129 in run 2, 48,548 in run 3).
- **Downloads:** the only one is the pinned Radicle release, at image build (#190's Dockerfile). Every other image was already present locally, pinned by digest: the pinned Foundry image and the oracle node's pinned Python image.
- **Paid calls:** none.
- **One thing outside the spike:** Docker Desktop wasn't running when the work started. Starting it also restarted some containers of other local projects (their own restart policies). They were left as they were.

## (c) One merge key in approved enclaves: desk study (2.4)

Not run. `oracle/keys.py` has one enclave provider, `DstackKeys`, a Phala dstack TDX confidential VM. It derives a key *inside* one VM and quotes its report. No provider shares a key between enclaves, and there is no SEV-SNP provider (#253 builds the first SEV-SNP kit). Each step of (c), with what it depends on:

1. **Key generation in an enclave.** The Radicle node key (ed25519) must be created inside the enclave and never leave it.
   - Radicle's node reads its secret key from `$RAD_HOME/keys`, so the whole Radicle node, gate included, has to run inside the enclave.
   - A dstack VM could derive the key from `GetKey`, keeping it there.
   - *Depends on:* #94 (an enclave key provider for the node, with the Radicle node packaged into the measured image) and #253 (for SEV-SNP).
2. **Sharing to attested enclaves.** Every approved enclave must hold the same merge key, released only to an enclave whose attestation shows an accepted TEE type, firmware and image. Those are the lists `Validators` keeps (D10, D11).
   - Needs a key-release protocol: a releasing enclave verifies the requester's TDX quote or SEV-SNP report against the chain's lists, then wraps the key to a key the requester's report binds.
   - dstack's KMS derives one key per application identity for every VM it attests. That would give "one key, many attested enclaves" for TDX on dstack, but it trusts dstack's KMS and covers one TEE type only.
   - *Depends on:* #94 (sharing), the chain's accepted lists (built), and an attestation verifier for each TEE type (TDX: dstack's; SEV-SNP: #253; neither checks against the chain today).
3. **Rotation by ADR.** One delegate means one key. Rotating it is an identity revision signed by the old key, adding the new one and removing itself. It is triggered by an ADR that passed on-chain (D11) and executed by an enclave that reads the ADR.
   - If the old key is lost (every holder down) or compromised, nobody can sign the rotation. The repository would have to be re-created under a new RID, with a new record (D15).
   - *Depends on:* #94, and an ADR operation for "rotate the merge key" (not in `IValidators.Op` today).
4. **What a level B extraction exposes.** Level B is SEV-SNP or TDX on hardware the operator controls, so physical attacks are in scope.
   - Extracting the shared key from **one** level B enclave gives the attacker the only delegate. It can move `main` and rotate the identity to itself, locking everyone else out of Radicle's view.
   - The chain is unaffected, and `verify-head` flags the mismatch at once.
   - The blast radius is the whole repository from one machine. Under (a) the same outcome needs a majority of the seated validators' keys; under (b) it needs the one delegate of convenience's key.
   - So (c) is no stronger than (a) unless every key holder is level A. That would contradict L16, which counts level B validators toward the launch set.
   - *Depends on:* L10/L16's levels; no code.

**Verdict on (c):** it needs at least #94's sharing, a key-release protocol with an attestation verifier per TEE type, the Radicle node inside the enclave, and a new ADR operation. None of these exists. Even built, one level B extraction ends it. Not recommended for the testnet.

## Findings beyond the scenarios

1. **`rad sync --rid` doesn't exist in Radicle 1.10.3.** The RID is a positional argument (`rad sync --fetch <RID>`). The `--rid` form exits with a usage error, which every caller hides (`>/dev/null 2>&1 || true`), so those syncs were silent no-ops. It is in:
   - #190's `spikes/radicle/gate.sh` (fixed here);
   - `scripts/radicle-spike.sh`'s v1 `sync_all` (not changed: the v1 run isn't repeated here);
   - `oracle/radicle.py`'s snapshot script, which `pofctl verify-head` runs;
   - `tests/integration/radicle.py`.

   #190's and #201's results held because pushes announce on their own. But a node that missed an announcement (finding 2) stays behind until something else syncs it.

   Here, `verify-head` is run after an explicit `rad sync --fetch <RID>`. The adapter's fix belongs to task 4.1.
2. **A restarted node doesn't fetch what it missed** (a7, all runs: not within 45 s). Under (a), a delegate that was offline votes with a stale `main` until its gate runs (the gate fetches first). Under (b) it doesn't matter.
3. **The merge quorum and the seat-change quorum are one number** (#190's finding, confirmed under v3). With a majority threshold, the same majority that can move `main` can rewrite the delegates (a9).
   - **Liveness:** with more than `n − threshold` delegates offline, neither `main` nor the delegate set can change. With 2 of 4 offline, `main` waited (a7).
   - **The chain doesn't wait:** `Heads` moves regardless, and readers who follow it aren't affected.
4. **Radicle's sibling rule constrains seat-change revisions.** A delegate that accepted one pending revision can't accept another with the same parent. A development run hit it as `✗ Error: delegate already accepted a sibling revision`, when a proposal was left pending and a second seat change came.
   - With an open validator set, two seat changes close together need a policy: one pending revision at a time, and a stale one rejected before the next.
   - A rejected revision doesn't block its author: in a8, `v4` proposed again afterwards in every run.
5. **A verdict can't become final when an audit falls due and no auditor is eligible.** It happened in a development run, with exactly 3 validators eligible for a fix: the counted panel used all 3, so there was no auditor outside it. The verdict stayed in its window indefinitely, and the keeper's `drawAudits` retried after every registry change.
   - The spike now tops up a 4th validator so an auditor exists.
   - L19's `panel-liveness` covers silent counted seats, not a due audit with no eligible auditor. Its requirement "No submission is ever stuck" doesn't hold today in that case.
   - This contradicts the launch spec; see "Against the launch spec".
6. **`activeCount` vs drawable** (a6, all runs): a validator at 90–95 below the floor of 100 was still `Active` and counted, 4 active against 3 drawable. Under (a), "the seats" must be the drawable set, or a below-floor validator stays a delegate. L5's `BelowFloor` makes the two agree.

## Proven and assumed

- **Proven here** (three runs, 7 nodes, two repositories, real v3 contracts and node objects):
  - (a)'s delegate set follows the seats on-chain through every kind of v3 seat change, with one revision each and only bound, seated keys accepted by honest seats;
  - the threshold merge moves `main` to `Heads.head` only at the threshold;
  - outsiders and one rogue delegate change nothing;
  - `verify-delegates` and `verify-head` detect a rogue majority;
  - (b) needs no Radicle operation at seat changes, and its checkout by hash follows `Heads.head` whatever `main` shows;
  - a validator can take a patch's commit from its own node, refuse a wrong base, and judge it;
  - the stand-in for L9 moves the head only at finality, 24 h of chain time after claim for k = 3, level A;
  - 255 delegates is Radicle's ceiling.
- **Assumed or not tested:**
  - **Scale and real links.** 7–11 nodes on one host; no partitions, packet loss or wide-area latency. Convergence times are this machine's.
  - **The keys are on disk,** in containers, not in enclaves. As in #190, protection against a colluding majority is the detection by `verify-head` and `verify-delegates`, not prevention.
  - **The binding's transport.** The spike's driver handed each new seat's binding to the proposer. On a real network it needs a channel: a Radicle issue, or better a field in the v3 registration, which is a contract change.
  - **The review loop is driver code** calling each node's `rad`, as `oracle/radicle.py` does for v2, not a node process.
  - **L9 is a stand-in;** task 3.5 builds `merge(bounty)`.
  - **The web view wasn't run** (no `radicle-httpd` in the pinned release).
  - **`pofctl checkout` doesn't exist yet,** and `pofctl verify-head` reads `Heads` through v2's race. The spike used the same library function (`oracle.radicle.verify_head`) and a checkout by hash of its own. Both commands belong to task 4.4.
  - **The release's SSH signature wasn't verified,** as in #190 (SHA-256 only).

## Recommendation

**(a), with (b)'s checks as what anyone relies on**, as design L11 proposed, if the owner accepts these conditions:

1. **A validator's Radicle node ID on-chain.** Add it to the v3 registration, signed with the rest. Until then, keep this spike's signed bindings in the identity document. Without one of the two, nobody can check that the delegates are the seats.
2. **Seats = drawable,** with L5's `BelowFloor` built, so the chain's own count agrees.
3. **Every validator runs a Radicle node,** with the gate (push only `Heads.head`) and the review rule (sign only the revision whose delegates are the seats). This is task 4.1's adapter: a node process, not driver code. Also:
   - one pending revision at a time;
   - an explicit sync before every decision (finding 1).
4. **The owner's node hands over at the first seats** (a1), and the deployment record names it as the genesis delegate until then.
5. **Validators, `pofctl` and the docs build from `Heads.head`** by hash (`checkout`), never from `main` (`specs/canonical-head`, "Readers take the code at the head on-chain"). `verify-head` and `verify-delegates` are the alarms.

**Why not (b) outright:** it is simpler and had no failure of its own here. But plain `rad clone`, `git clone` and the explorer show whatever one key last pushed, which is the owner's for the whole testnet. (a) makes that view need a majority of bonded, seated validators, and costs one revision per seat change.

**(b) remains the fallback** if conditions 1 or 3 can't be met for the launch. In that case, the owner's node should push only `Heads.head` through the same gate (b3), and the README should say that `main` is a convenience.

**(c) is not recommended.** See its section.

## Against the launch spec

- **`specs/radicle-hosting`, "Delegates follow the seats":** it says each node signs only a revision whose delegates equal the seats, but not how a seat maps to a node key. The spike had to add a binding (condition 1). If (a) is chosen, the requirement should name the binding, or the registration field.
- **`specs/panel-liveness`, "No submission is ever stuck":** a due audit with no eligible auditor leaves a verdict in its window indefinitely (finding 5). L19 covers silent counted seats only.
- **`specs/canonical-head`, "Anyone can check a copy against the head":**
  - the tool exists, but only for v2 (`pofctl verify-head` reads `Heads` through RaceV2);
  - its Radicle snapshot's sync is a no-op on 1.10.3 (finding 1);
  - `pofctl checkout`, which design L11 and task 2.3 name, doesn't exist.

  These are tasks 4.1 and 4.4.
- **Design L11** said the spike would record "what the explorer shows". It couldn't be run within the spike's rules (no `radicle-httpd` in the pinned release).
