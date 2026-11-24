# Design

## Context

- **Why:** see proposal.md. The behaviour is in the delta to `challenges` ("A panel reveals once every seat has committed",
  "No counted vote is public while a shadow can still commit" and "A waiting shadow cut short counts no miss"). This document covers how, the attacks, the parameters, gas and
  sizes.
- **Numbering:** the decisions are **E1–E8**, to avoid #132's D-numbers, #251's L-numbers and #310's RB-numbers.
- **Base commit:** everything marked "observed" was read at `origin/main` 072d4a3 (#310's spec merged).

### What v3 does today (observed)

| Step | Where | What happens |
|---|---|---|
| Seal | `PanelsJudge.seal`, `PanelsJudge.sol:41-54` | Refused after `sealBy` (`TooLate`, `:47`); `++p.nSealed` (`:52`) |
| Reveal window | `PanelsJudge._inRevealWindow`, `PanelsJudge.sol:388-392` | `TooEarly` until `sealBy` for every kind; a judging panel (not a shadow) also needs `seats == k && nSealed == k`; `TooLate` after `revealBy` |
| Reveal, receipt | `PanelsJudge.reveal` `:56-88`, `receipt` `:90-104` | Both call `_inRevealWindow`; the panel counts at its k-th reveal with a receipt (`_complete`, `:367-372`) |
| Timeline | `PanelsBase.resetTimeline`, `PanelsBase.sol:288-292` | `sealBy = now + SEAL_WINDOW`, `revealBy = sealBy + REVEAL_WINDOW`; reset by a refill (`PanelsJudge._refill`, `:331`) |
| Missed deadlines | `PanelsJudge.advance`, `PanelsJudge.sol:106-135` | After `sealBy` with a seat unsealed: silence, replaced. After `revealBy`: a sealed seat without reveal and receipt is slashed and replaced, or not replaced when the revealed votes already decide (owner, 2026-11-13) |
| Shadows drawn | `PanelsVerdict.draw`, `PanelsVerdict.sol:57-61` (a waiting submission, `ex = 0`, its own `sealBy`) and `:72-73` (with the counted panel: `sealBy` = the counted panel's) | `_drawShadows` (`:412-450`) sets `sealBy` and `revealBy = sealBy + REVEAL_WINDOW` (`:444-445`), and overwrites `s.shadowPid` (`:449`) |
| Shadow reveal | `_inRevealWindow` | After the shadow panel's own `sealBy`, independent of the counted panel |
| Shadow settle | `PanelsVerdict._settleShadows`, `PanelsVerdict.sol:454-505` | Once past `revealBy`: `recordShadow(key, revealed && receipted)` for every seat (`:464`), so an unsealed shadow is a miss; then scoring |
| Windows | `contracts/deployments/sepolia-v3.json` `windows` | `seal` 7,200 s, `reveal` 3,600 s |
| Node | `oracle/node_v3.py:416-438` (`_reveal`) | Waits for `now > sealBy` and, on a judging panel, a full sealed panel (`:422`) |
| Watcher | `validator-kit/sevsnp/lambda/watcher.py:214-227` (`phase`) | "reveal" due once the panel is full and `now >= sealBy - REVEAL_LEAD_SECONDS` (`:226-227`) |

So the reveal of a prompt panel starts at `sealBy`, 2 h after the draw (or the last replacement).

### Sizes, measured (`scripts/contracts.sh sizes` and `out/*.json`, pinned Foundry 1.8.5, solc 0.8.37, at 072d4a3)

| Contract | Runtime (B) | Runtime margin (B) | Initcode margin (B) |
|---|---:|---:|---:|
| Panels | 19,026 | 5,550 | 26,452 |
| PanelsJudge (linked library) | 16,515 | 8,061 | 32,605 |
| PanelsVerdict (linked library) | 23,163 | **1,413** | 25,957 |
| PanelsDraw (linked library) | 10,656 | 13,920 | 38,466 |
| PanelScores | 5,869 | 18,707 | 43,196 |

PanelsVerdict is the tight one, so the new code goes into PanelsJudge where it can (E5).

## Goals / Non-Goals

**Goals:**

- A panel whose judges (and shadows) all seal promptly is counted minutes after the last seal, not after
  `SEAL_WINDOW`.
- No vote becomes copyable: not by a judge of the panel, not by a shadow, not by a mempool watcher.
- Candidates keep every chance to qualify they have today: a shadow is never shut out by a fast counted panel.
- No new storage slot and no ABI change, so the change costs no new EIP-8037 state gas and the node's and the
  watcher's decoders don't change.

**Non-Goals:**

- Changing `SEAL_WINDOW`/`REVEAL_WINDOW` or any deadline. The issue keeps them as the limits for slow judges.
- Making a silent shadow cheaper for the counted panel: a shadow that never seals holds the counted reveal to
  `sealBy`, as today (E2).
- v2. Its relay already closes the seal window once every judge sealed (`docs/exchange.md:93-95`).

## Decisions

### E1. The reveal opens when the panel is full and sealed

`_inRevealWindow` on a judging panel (counted, audit, challenge) needs `nSealed == k` (which implies `seats == k`,
since `nSealed <= seats <= k`) and `now <= revealBy`, and no longer `now > sealBy`; a counted panel before its `sealBy`
also needs E2's shadow condition. The `now > sealBy` check stays for shadow panels.

- **Why it's safe inside the panel:** a reveal is possible only when every seat of the panel has a commitment. A seat
  that is vacated (a mismatch) and refilled brings `nSealed` below k, and the reveal closes again until the replacement
  seals, as today.
- **The deadlines:** unchanged. `sealBy` still bounds a silent seat (`advance`'s first branch), and `revealBy` still
  bounds a sealed seat's reveal. A prompt panel thus gets a longer reveal window (from its last seal to `revealBy`),
  never a shorter one.
- **Alternative rejected: also move `revealBy` to "last seal + REVEAL_WINDOW".** It would make the miss deadline
  depend on the slowest sealer and add a write to `seal`. Nothing needs it: a judge that reveals promptly is counted
  promptly whatever `revealBy` is.

### E2. The shadow guard: no counted reveal while a shadow can still seal

**Decided (owner, 2026-11-23):** E2 is accepted. An early reveal also waits until every shadow drawn with the panel
has sealed, instead of the issue's literal form (refusing shadow seals after the first counted reveal).

The issue asks that "a shadow's seal after the first counted reveal must be refused". The design makes that hold by
construction: **before its `sealBy`, a counted panel's reveal also needs every seat of its shadow panel sealed.** The
shadow panel is the submission's `shadowPid` when its `ex` is this counted panel. Its seats are always all filled
(shadows are never vacated or refilled), so the test is `q.nSealed == q.k || now > q.sealBy`.

- **Why it's a guard:** a counted reveal is accepted only when every shadow has sealed (it can't seal again,
  `AlreadySealed`) or the shadows' window is over (`TooLate`, `PanelsJudge.sol:47`). A shadow's `sealBy` is never
  later than its counted panel's (it is the counted panel's at the draw, `PanelsVerdict.sol:73`, and a refill only
  moves the counted one later), so after the counted `sealBy` the test is skipped and the rule is today's.
- **Mempool front-running is impossible**, not just refused: no counted reveal can be valid while a shadow may still
  seal, so there's no reveal transaction to copy from.
- **Alternative rejected: close the shadows' seal window at the counted panel's last seal** (the issue's wording, with
  the guard at the first reveal or at the panel filling). It shuts a shadow out whenever it is slower than the
  counted panel. At the launch every verdict is k = 1, so a shadow would have to beat the lone judge to every seal:
  the integration harness, which ticks the genesis node first, would never qualify a candidate, and on Sepolia the
  candidates on slower hosts never would either. The network could not grow. With E2 a candidate keeps its whole
  window, and the early reveal comes whenever everyone drawn is prompt.
- **The cost:** a shadow that never seals holds its counted panel's reveal to `sealBy`: today's timing, no worse.
  Shadows are candidates whose qualification needs `QUALIFY_REVEAL_BPS` of reveals, so they have every reason to be
  prompt. Audit and challenge panels have no shadows.

### E3. A waiting submission's shadows close at the counted draw

Shadows drawn while a submission waited (`ex = 0`, `PanelsVerdict.sol:60`) have their own `sealBy`, which can still be
open when the counted panel is drawn (`draw` runs again on any registry change, `PanelsVerdict.sol:40-42`). E2's test
doesn't cover them (their `ex` isn't the counted panel, and the counted draw overwrites `s.shadowPid`,
`PanelsVerdict.sol:449`). So `draw`, before it seats the counted panel, closes the seal window of the submission's
previous shadow panel: `sealBy = now − 1` when it is still open, so not even a seal in the draw's own block is
taken. Its `revealBy` doesn't move.

- **What that exposes:** a waiting shadow that sealed can then reveal before the counted judges seal. That's not new:
  today a waiting shadow's `sealBy` is always earlier than the later counted panel's, so its reveals are already open
  while the counted judges seal. Waiting shadows are scored by their own majority, never by the counted panel's.
- **Alternative rejected: re-link the waiting panel to the counted one** (set its `ex`). It would change how the
  waiting shadows are scored (D5) and add code to the tight PanelsVerdict.

### E4. A waiting shadow cut short counts no miss

A shadow panel whose seal window was closed by E3 is recognisable from its own timeline, with no new field:
`_drawShadows` always sets `revealBy = sealBy + REVEAL_WINDOW` (`PanelsVerdict.sol:444-445`), and shadow panels are
never refilled (`advance` and `refill` refuse them, `PanelsJudge.sol:108` and `:140`). So **cut ⇔ `sealBy +
REVEAL_WINDOW < revealBy`**. In `_settleShadows`, a seat of a cut panel that has no seal isn't recorded
(`recordShadow` isn't called for it): neither a draw nor a miss toward `QUALIFY_REVEAL_BPS`. A seat that sealed is
recorded as today.

- **Why:** the shadow couldn't know the counted draw would come early; counting a miss would punish it for the
  registry changing.
- **What a candidate could game:** skip a waiting draw by not sealing, hoping the counted draw comes first. It gains no
  agreement point and needs `QUALIFY_VERDICTS` scored verdicts anyway; if the draw doesn't come, its silence is a miss.

### E5. Where the code goes

| Piece | Where | Why there |
|---|---|---|
| The reveal condition and E2's shadow test | `PanelsJudge._inRevealWindow` (it gets the `Store`) | It is the only reveal and receipt gate; PanelsJudge has 8 KB of margin |
| Closing the waiting shadows (E3) | `PanelsVerdict.draw` | The draw is there; a few dozen bytes |
| No miss for a cut shadow (E4) | `PanelsVerdict._settleShadows` | Settle is there; one comparison per panel |
| Natspec | `Panels.sol` ("Seals, reveals and receipts", "Shadows") | The rules are documented there |

The size rule: each of Panels, PanelsJudge and PanelsVerdict keeps at least 512 B of runtime margin (as #310's RB10
for RaceV3). If PanelsVerdict would drop below it, E3 and E4 move behind a PanelsJudge entry.

### E6. Gas (EIP-8037)

No new storage slot is written, so **no new state gas** (97,920 per new slot under EIP-8037,
`reports/glamsterdam-runtime-v1.md`, "EIP-8037 semantics"). The deltas are execution gas only:

- `reveal` and `receipt` on a counted panel before its `sealBy`: the submission's `shadowPid` and the shadow panel's
  timeline and `ex` (2–3 cold reads, about 4–6k gas). After `sealBy`, and on audit and challenge panels: one comparison
  fewer than today.
- `draw` of a counted panel: one read of `shadowPid` and, when it's non-zero, of its panel's timeline; one write over a
  non-zero slot when that panel was still open.
- `settleShadows`: one comparison per panel, with `REVEAL_WINDOW` from the `Env` (an immutable, no SLOAD).
- Deploying PanelsJudge and PanelsVerdict: their code-size change × 1,530 gas per byte (EIP-8037's code deposit).

Task 1.5 measures `reveal`, `receipt`, `seal` and `draw` with `forge test --gas-report` before and after, and records
the deltas here and the deploy cost from the size change. A Sepolia rehearsal (as in the Glamsterdam report) is part
of the release candidate, not this change. Since no slot is new and nothing reads `gasleft()`, the report's R1–R4
caveats are unchanged.

### Measured (task 1.5, pinned Foundry 1.8.5, solc 0.8.37)

**Sizes** (`scripts/contracts.sh sizes` and `out/*.json`; before at 072d4a3):

| Contract | Runtime before (B) | Runtime after (B) | Δ | Runtime margin after (B) | Initcode margin after (B) |
|---|---:|---:|---:|---:|---:|
| Panels | 19,026 | 19,026 | 0 | 5,550 | 26,452 |
| PanelsJudge | 16,515 | 16,695 | +180 | 7,881 | 32,425 |
| PanelsVerdict | 23,163 | 23,327 | +164 | **1,249** | 25,793 |
| PanelsDraw | 10,656 | 10,656 | 0 | 13,920 | 38,466 |
| PanelScores | 5,869 | 5,869 | 0 | 18,707 | 43,196 |

Every margin stays above E5's 512 B. RaceV3 (1,964 B), RaceV3Annex (2,214 B), RaceV3Endings (2,731 B), Validators
(1,668 B) and FeesV3 (6,550 B) are unchanged. Deploying the two libraries costs 344 B more code: 526,320 more state gas
under EIP-8037 (1,530 a byte), 68,800 under the old rules (200 a byte).

**Gas** (`forge test --gas-report` over `PanelsV3Test` and `PanelsV3BTest`, the same 83 tests before and after, median
per call; and a probe of one counted reveal and receipt before `sealBy`, with and without shadows):

| Call | Before (median) | After (median) | Δ |
|---|---:|---:|---:|
| `seal` | 74,190 | 74,190 | 0 |
| `reveal` (these suites reveal after `sealBy`) | 51,769 | 51,804 | +35 |
| `receipt` (likewise) | 85,969 | 86,004 | +35 |
| `draw` | 643,392 | 646,557 | +3,165 (the previous shadow panel's timeline read) |
| `settleShadows` | 92,418 | 92,589 | +171 |
| a counted `reveal` before `sealBy`, its shadows sealed, against none drawn | | 63,915 vs 59,596 | +4,319 (the shadow panel's reads) |
| a counted `receipt` likewise | | 98,131 vs 93,813 | +4,318 |

All of it is execution gas: no call writes a new slot (the only new write, E3's, overwrites a non-zero `sealBy`), so
EIP-8037's state gas (97,920 a new slot) doesn't change for any transaction. Against the Sepolia rehearsal's
per-transaction figures (`reports/glamsterdam-runtime-v1.md`: reveal 467,519, draw 1,429,934) the deltas are under 1 %.

### E7. The node and the watcher

- **Node** (`oracle/node_v3.py` `_reveal`, `:422`): a judging seat tries its reveal once its panel is full and sealed,
  with no `sealBy` test; a shadow seat once `now > p["sealBy"]`, as before. For a counted seat before `sealBy` it also
  reads the shadow panel (`verdict(s).shadowPid`, `panel`) and waits until E2's test holds, so it sends nothing the
  chain would refuse. A running node reveals in its next pass (seconds) after the panel and its shadows fill. On a
  deployment without the early reveal (v3) the first early attempt is refused with `TooEarly` at the gas estimate (no
  transaction is sent); the node remembers that and waits for `sealBy` from then on.
- **Watcher** (`watcher.py` `phase`, `:226-227`): a sealed judging seat is "reveal" due as soon as its panel is full
  and sealed, whatever `sealBy` is; a shadow as before. It doesn't read the shadows: starting the node a little early
  only holds the instance up while it waits (the node holds it while a seat is open), and it covers a node that stopped
  or crashed after sealing: the watcher starts it within a minute of the panel filling, not at
  `sealBy - REVEAL_LEAD_SECONDS`.
- Changing `oracle/` changes the validator disk's image digest: expected for v3.1, with a new disk and release
  candidate. The change to `node_v3.py` stays inside `_reveal` and the docstring, away from #310's edits (the patch
  lookup, the case, the keeper).

### E8. Audit and challenge panels get the early reveal too

Decided: yes, E1 applies to every judging panel.

- **Audits** are one-seat panels: the auditor reveals right after its seal, and a disagreement opens its challenge
  about `SEAL_WINDOW` sooner. Two audits of one verdict can be drawn together (a k = 1 verdict's `K1_AUDITS`), and the
  first could reveal while the second still seals. Copying it gains nothing a copier hasn't already: the audited
  verdict is public, and a disagreeing audit opens a challenge by itself.
- **Challenge panels** judge a verdict whose votes are already public; inside the panel every judge has sealed before
  any reveal. There's one challenge panel at a time per submission.
- **#310's rebase checks** are ordinary counted panels (RB6), so they get E1–E4 with no extra code; #310's RB9 table
  already counts on it ("With rebase + #311").

## Risks / Trade-offs

- [A silent shadow holds its counted panel's reveal to `sealBy`] → today's timing, no regression; shadows have their
  qualification at stake. The integration scenario shows the saving with prompt shadows.
- [A replacement seals after reveals are public: a mismatch vacates a seat while others have revealed] → unchanged from
  today, where a mismatch also happens in the reveal window; it can now happen earlier, nothing more.
- [Cut detection by `sealBy + REVEAL_WINDOW < revealBy` breaks if shadow timelines are ever reset] → a Foundry test
  pins it, and the natspec of `_drawShadows` states it.
- [A counted reveal sent in the same block as the last seal] → it reverts with `TooEarly`; the node retries next pass.

## Migration Plan

- Ships in v3.1 with #310, after a new release candidate (#310 tasks 7.0–7.2). v3 on Sepolia keeps today's rule; a
  new node on v3 makes one early attempt, refused at its gas estimate (`oracle/rpc.py:271`), then waits for `sealBy`
  (E7). The watcher's earlier start on v3 only holds the instance up until `sealBy`.
- Rollback: redeploy without it (keyless upgrades by migration); the node change is harmless on v3 as above.
