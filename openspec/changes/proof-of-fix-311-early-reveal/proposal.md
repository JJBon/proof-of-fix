## Why

In v3 every verdict waits out the whole seal window, even when every judge sealed within minutes:

- `PanelsJudge._inRevealWindow` (`contracts/src/v3/PanelsJudge.sol:388-392`) refuses a reveal or a receipt with
  `TooEarly` until `sealBy`, and on a judging panel also until every seat has sealed.
- `SEAL_WINDOW` is 2 h on Sepolia (`contracts/deployments/sepolia-v3.json`, `windows.seal` 7,200 s), so a verdict is
  counted 2 h or more after its draw, and its challenge window starts no earlier.

Once every counted seat has sealed, every vote is locked in a commitment, so waiting longer protects nothing inside the
panel. The one party that can still seal is a shadow (`PanelsVerdict.sol:73`: shadows seal by the counted panel's
`sealBy`), and an early reveal would let a shadow copy the counted votes. #306's fast-merge spike found both the saving
(about 1.5–2 h per verdict) and the shadow problem. The owner approved the change on 2026-11-23 for v3.1, together with
#310 (rebase in place); #310's tasks (task 7.0) merge this change first, as its own change.

Ticket: #311. Refs #306, #310, #251.

## What Changes

- **Early reveal.** A counted, audit or challenge panel's reveal opens as soon as all of its k seats are filled and
  sealed, instead of after `sealBy`. The deadlines don't move: `sealBy` is still the limit for a silent seat and
  `revealBy` (`sealBy` + `REVEAL_WINDOW`) for a missing reveal, and replacement and the "already decided" rule work as
  today.
- **The shadow guard.** Before its `sealBy`, a counted panel's reveal also waits until every shadow drawn with it has
  sealed. So no counted vote is ever public while a shadow can still seal: a late shadow seal is refused (`TooLate`
  once its window is over, `AlreadySealed` otherwise), and there is no counted reveal in the mempool to front-run. A
  silent shadow holds the reveal to `sealBy`, today's timing. This meets the issue's guard ("a shadow's seal after the
  first counted reveal must be refused") without shutting a shadow out when it is slower than the counted judges,
  which at the launch (every verdict k = 1) would stop candidates from qualifying (design E2).
- **Waiting shadows.** A waiting submission's shadows (drawn before any counted panel) have their seal window closed
  when the counted panel is drawn, and those that hadn't sealed count no miss.
- **The node** (`oracle/node_v3.py`) reveals a judging seat as soon as the reveal is open (the panel full and sealed,
  and for a counted panel its shadows sealed), without waiting for `sealBy`. Shadows keep their rule.
- **The v3 watcher** (`validator-kit/sevsnp/lambda/watcher.py`) treats a sealed judging seat as "reveal due" as soon
  as its panel is full, so a stopped on-demand host is started to reveal promptly, not at `sealBy`.
- **Docs:** Panels' natspec, the node's and the watcher's docstrings, and `validator-kit/SEVSNP-PLAN.md`'s deadline
  table say when the reveal opens.
- **Not BREAKING for the ABI:** no struct, event or function signature changes. It changes behaviour, so it ships in
  the v3.1 deployment (a new keyless deployment, with #310), after a new release candidate.

Out of scope:

- v2 (`RaceV2`/`Verdicts`) and v2's watcher (`validator-kit/lambda/watcher.py`): v2's relay already closes its seal
  window once every judge sealed (`docs/exchange.md:93-95`), and v2's contracts don't change.
- Shorter `SEAL_WINDOW` or `REVEAL_WINDOW` values (the limits for slow judges stay as deployed).
- #310's rebase checks themselves: they are ordinary counted panels, so they get the early reveal and the shadow guard
  with no extra code.
- The deployment of v3.1, and its release candidate (#310's tasks 7–8 carry both changes).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `challenges`: three added requirements beside "Commit-reveal verdicts": "A panel reveals once every seat has
  committed", "No counted vote is public while a shadow can still commit" and "A waiting shadow cut short counts no
  miss".

## Impact

- **Actors and incentives:**
  - Counted judges, auditors and challenge judges: the same commitments and deadlines; they can reveal earlier. A
    judge can't see another's vote before sealing, as today: the reveal opens only once every seat has sealed.
  - Shadows (candidates and barred families): the same window as today; they can't copy (they never could), and a
    silent shadow now visibly costs the verdict time (up to `sealBy`), as it already costs its own qualification.
    A waiting submission's shadows can have their window cut by the counted draw, with no miss (design E3, E4).
  - Solvers and funders: a verdict is counted, and its challenge window starts, up to `SEAL_WINDOW` (2 h) earlier.
- **Attacks considered (design E2, E3, E8):** copying by a shadow (no counted reveal while a shadow can seal),
  mempool front-running of a counted reveal (no such reveal exists in time), copying between concurrent audits (they
  check a verdict that is already public), a replacement sealing after reveals are public (unchanged: only after a
  mismatch, as today).
- **Contracts:** `contracts/src/v3/PanelsJudge.sol` (`_inRevealWindow`), `PanelsVerdict.sol` (`draw`,
  `_settleShadows`), `Panels.sol` (natspec only). RaceV3, its Annex and
  Endings, Validators, FeesV3, Heads and SolverBook don't change (#310 edits those).
- **Node and kit:** `oracle/node_v3.py` (`_reveal`'s condition and the docstring), `validator-kit/sevsnp/lambda/
  watcher.py` (`phase`). Changing `oracle/` changes the validator disk's image digest: expected for v3.1 (a new disk
  and release candidate).
- **Tests:** Foundry (`contracts/test/v3/EarlyRevealV3.t.sol`, and the existing suites' helpers and the early-reveal
  tests they had), Python (`tests/test_oracle_v3.py` or `tests/test_node_v3*.py`, `tests/test_sevsnp_watcher.py`), and
  an integration scenario in `tests/integration/scenarios_v3.py` (letter `e`, launch set).
- **Gas and sizes:** measured in task 1.5; no new storage slot, so no new EIP-8037 state gas (design E6).
