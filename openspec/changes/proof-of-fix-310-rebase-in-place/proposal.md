## Why

In v3 a winning fix whose base is no longer the head can never merge, and v3 has no way to rebase it:

- `Heads.move` refuses a base that isn't the head (`contracts/src/v2/Heads.sol:98`).
- `RaceV3.merge` passes the base revealed at the claim (`contracts/src/v3/RaceV3.sol:389`).
- Only `mergeExpired` frees the bounty, `mergeDays` (14 on Sepolia, `contracts/script/DeploySepolia.s.sol:400`) after the
  verdict's finality (`contracts/src/v3/RaceV3Endings.sol:178-196`).

So when two fixes are judged on the same head, the second takes 15 days or more (#306's spike, section 3.0). v2 had the
path: a new verdict on the rebased commit merged in the winner's place (`contracts/src/v2/RaceV2.sol:259-282`). The
owner approved this change on 2026-11-23, because the merge rate is make-or-break for the project.

## What Changes

- **Rebase in place.** A claimed, unmerged award whose base is no longer the head can be re-submitted rebased onto
  the current head. The award keeps its place, its epoch and its locked price. The solver may do this at once; anyone
  else may after a published grace period.
- **The re-check.** The rebased commit is judged as a new check by one fresh counted panel of the usual size. Its
  tests run with the protected paths taken from the new base, and the judges compare it with the approved fix. It has
  its own full challenge window, audits and D21 disputes. Nothing of the original approval carries over to the new
  tree.
- **Merge.** The head moves to the rebased commit once both the original verdict and the rebase's verdict are final
  passes. Instalments count from the later of the two finalities.
- **Fail fast.** A rebase by the solver that fails, on a base that is still the head, closes the award at once and
  reopens the bounty. A third party's failed rebase ends only that attempt.
- **The taxi fare.** Whoever submits the rebase pays its metered check (the same deposit as a fix) and opens a claim
  under its reputation cap. If the rebase merges, its checks are refunded from the bounty's pot, as the winner's
  checks are (S6).
- **The merge deadline** counts from the latest passing rebase's finality. A rebase in flight holds it off.
- **Tooling.** The validator node finds a rebase check's patch revision, gives the judge the range-diff, and keeps
  rebase checks moving to `merge` or to the reopening. pofctl gets `rebase`. The guide gets a section on it.
- **Shipping.** The change ships in a new keyless deployment, v3.1, after a new release candidate. The design covers
  how the Radicle repository moves from v3 to v3.1. **BREAKING** for clients of v3's ABI: `Submission` and `Award`
  gain fields, and there is a new event.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `bounty-market`: a rebase of a won fix whose base went stale: who may submit it, its deposit and claim, the fail-fast
  reopening, and the merge deadline.
- `checking`: what the rebase check runs (the new base's protected tests) and what its judges compare.
- `challenges`: a rebase check's verdict is challenged and disputed as any verdict, and the dispute reward applies.
- `contribution-lifecycle`: a conflicting fix merges about one cycle after the first. The head moves to the rebased
  commit only after both verdicts are final, and instalments count from the later finality.
- `reputation`: whose claim and reputation a rebase check uses.

## Impact

- **Contracts** (`contracts/src/v3`):
  - RaceV3: `merge`, `isParty`, and a delegated `rebase` entry;
  - RaceV3Endings: `rebase`, and `mergeExpired` extended;
  - RaceV3Annex: `settleChallenge`'s dispute reward;
  - RaceV3Base: `Submission.rebaseOf`, `Award.rebase`, `_earned`, `_settle`.

  Panels, Heads, FeesV3, Validators and SolverBook don't change. EIP-170 margins are tight: RaceV3 has 1,964 B left,
  the Annex 2,214 B and the Endings 2,731 B (measured on `origin/main` b61fa63).
- **Node and tools:**
  - `oracle/node_v3.py`: finding the patch, the judge's case for a rebase, the keeper;
  - `oracle/radicle_v3.py`: how a node behaves when a newer deployment takes over;
  - `pofctl/v3cli.py`, `bot/logic.py` (the claim lines are reused);
  - `docs/guides/submit-a-fix.md`.
- **Tests:**
  - a new Foundry suite `contracts/test/v3/RebaseV3.t.sol`, plus changes to the invariants;
  - a new integration scenario in `tests/integration/scenarios_v3.py`, and a Radicle variant.
- **Deployment:** a new release candidate (L18), then the v3.1 Sepolia deployment, each with the owner's go. Then the
  Radicle hand-over from v3 to v3.1 (design R12).
- **Related, not in scope:**
  - #311 (early reveal), its own change, ships in the same v3.1 release candidate (owner, 2026-11-23);
  - #314 (keeper backoff);
  - #306's `next` branch.
