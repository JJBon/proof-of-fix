# v3 on a throwaway local devnet (proof-of-fix#140, 2026-11-15)

Tasks 5.0 and 5.1 of `openspec/changes/proof-of-fix-132-open-validators`, and a first measure of the time to heal.

**Commands** (each starts its own devnet, deploys v2, deploys v3 beside it, and removes everything when it ends):
- `scripts/devnet-v3-e2e.sh`: task 5.1's run, about 5 minutes;
- `scripts/integration.sh --version 3`: the same scenarios as the integration suite's v3 run (task 5.0);
- `scripts/time-to-heal.sh`: 5.1's run plus the time to heal of a paid fix, 6 to 11 minutes;
- `scripts/integration.sh`: v2's suite, unchanged in what it checks, now reading its draws through the panel interface.

Everything ran on this machine: anvil in the pinned Foundry image (chain 7193, EIP-170 enforced), anvil's public test keys, the fake judge, no model call, no AWS, no public chain. The numbers below are from `the last `scripts/time-to-heal.sh` run (337 s of wall time, 523 h of chain time, 288 panels)`; the run's own figures are in [`devnet-v3-local.json`](devnet-v3-local.json).

## Result
| What | Result |
|---|---|
| v3 deployed beside v2 on one chain, one genesis validator at level A (`simulated`) | ✅ `scripts/devnet.sh deploy-v3`; the record is marked `testOnly` and names v2's race |
| Validators register and qualify until k = 3, then k = 5 | ✅ 3 active after 27 registration checks and 9.0 h of chain time; 5 active after 24 more |
| A k = 1 verdict held, audited twice, final after its window | ✅ with one difference from the task's wording, below |
| A bounty above k = 1's limit waits, is shadowed, is drawn when k = 3 is reached | ✅ sealed at $84.15 (limit $50), 2 candidates shadowed it, drawn with k = 3 12 s after two validators topped up |
| A challenged k = 1 verdict reversed by a fresh panel of 3 | ✅ pass → fail, the challenger's stake credited back, the registration forfeited |
| A silent judge replaced (scenario 4) | ✅ slashed $5, replaced from the same sample, 3 verdicts and 3 usage reports |
| Time to heal | ✅ measured, two cases, below |
| v2's integration suite on the panel interface, local | ✅ scenarios 1–7 and 10 pass (27 minutes) |
| v2's integration suite on AWS | ⚠️ not run: not this task's to run. `tests/integration/aws.py` is untouched |
| `scripts/check.sh` | ⚠️ 1,549 of 1,550 pass; `test_judge_gateway`'s killed-run test failed in both full runs (30 calls against 29: one in flight at the kill). It imports nothing changed here and passed 3 of 3 alone, so it looks like a timing flake under load |
| `scripts/contracts.sh test` | ✅ 547 of 547, and a fresh anvil answers (no contract source changed) |
| `scripts/node-v3-e2e.sh` (task 4.1's run) | ✅ still passes |

## What the run is
- **The contracts are the real ones.** Validators, Panels, FeesV3, PanelScores, RaceV3 and its annex check every registration, signature, draw, window and payment.
- **The validators are real `NodeV3` objects with the fake judge,** all in one process, as in task 4.1's run. Each has its own key, family, host and operator.
  - Their keys and quotes come from a stand-in for the dstack simulator.
  - The repository host is a fake holding the registrations' claims and the fixes' pull requests.
  - A fix's tests are a stand-in for the sandbox: exit 0 for the good fix, 1 for the bad one. No fix's code exists, so none is run.
- **Time is the chain's, under the real windows.** Panels' windows are constants (seal 2 h, reveal 1 h, a k = 1 window of 168 h). The run moves anvil's clock to the next deadline whenever no node has anything to do, and registers more issues when there is no deadline to wait for.
- **Every duration below is therefore chain time, and part of it is the run's own doing.** How fast validators qualify depends on how fast issues arrive, and the run feeds them as fast as the network takes them.

## The k = 1 hold: three validators, or five
The task says "held until three more validators are active". The contracts hold a k = 1 verdict until three validators **who could judge its challenge** are active, and its auditors can't (D13, and `PanelsV3B.t.sol`: "the genesis judge and both auditors sit out").

Each auditor is drawn as soon as one is eligible. So two orders are possible, and both were seen:

| Order | Validators beside the genesis one when the window started | Held for | Seen in |
|---|---|---|---|
| The window starts before any auditor is drawn (three candidates qualify close together) | 3 | 7 h | the final runs |
| Auditors are drawn first (candidates qualify apart) | 5 | 94 h | an earlier run of the same script |

- **Nothing in the contracts picks the order.** `startWindow` and `drawAudits` are both calls anyone may make, and the node's keeper makes them in the same pass.
- **A third, random audit (1 in 10) takes one more validator out.**
- **A silent auditor is replaced, and both it and its replacement sit out.**
- **The script accepts both orders and prints which one happened.**

This is the known finding "the k = 1 hold needs 6 validators", narrowed: it needs 4 to 7, depending on a race. It isn't fixed here, because the rule is the design's and choosing another is the owner's.

## Time to heal
`scripts/time-to-heal.sh` lets two wrong verdicts pass and measures the chain time from each wrong pass to its reversal.

| | A wrong k = 1 verdict | A bad fix passed by a panel of 3 |
|---|---|---|
| The wrong pass | the lone genesis judge passes a registration nobody claimed | two lying judges of three pass a fix whose tests fail; it wins and is claimed |
| Challenged by | a candidate that re-ran the check | the outvoted judge |
| Reversed by | a fresh panel of 3 | a fresh panel of 5 |
| **Wrong pass → reversal** | **367.0 h** | **483.0 h** |
| until the challenge | 1.0 h | 0.0 h |
| the challenge waits for a panel to exist | 364.0 h | 481.0 h |
| the panel's draw → its verdict | 2.0 h | 2.0 h |
| What was lost meanwhile | nothing: no bounty opened on it, and the registration ended forfeited | nothing: the award was clawed back with $0 earned, and the bounty reopened |
| What the liar lost | $0 of its bond. Its family was barred from counted panels by its score | $0 of the two bonds |

Across the runs made while writing this, the k = 1 case took 96 to 367 h and the fix 181 to 483 h. All of the spread is the wait for a panel, and **that wait is mostly the run's own schedule**: the script registers new validators at fixed points of its story (two before k = 5, then one more only when a verdict has too few left to judge its challenge), and new candidates need about 24 checks each to qualify. On a real network it is however long it takes enough independent validators to join and qualify. The 2.0 h and the validator counts below are the contracts'; the hundreds of hours are not a property of v3.

**What the numbers say.**
- **Once the challengers exist, a reversal takes 2.0 h.** That is `SEAL_WINDOW`: reveals can't start before the seal deadline, even when every judge sealed in the first minute. With today's constants no wrong verdict heals faster than that.
- **Almost all the time is the wait for a panel that is larger than the original and shares no judge with it.**
  - A k = 1 verdict needs 3 more validators beyond its auditors.
  - A k = 3 verdict needs 5 more, each bonded for the bounty: 8 in all.
  - A k = 5 verdict would need 7 more (12), and a k = 7 verdict 7 more (14).
  - A network smaller than that can't reverse its own verdicts until it grows. Meanwhile the verdict's window is frozen and nothing is paid, so the wait costs time and not money; the bounty is stuck for as long.
- **A reversal by disagreement slashes nobody.** In both cases the panel disagreed on the outcome and found no false receipt, so the lying judges kept their bonds. The only penalty was the score: the lying genesis judge's family was barred once its one failed outcome was final.
- **A reversed pass that had won a bounty pays nothing.** Instalments start at finality, and a challenge freezes the window.

**What the measure doesn't cover.**
- **Detection.** The watcher challenges at once, with the fake judge. How long a real watcher takes, and how often it's right, isn't measured.
- **The dispute backed by a failing test, the solver's deposit and the appeal** (D21–D23, task 10.4): not built. The measure uses what exists: a staked challenge and a larger fresh panel.
- **Short test windows.** There are none (below), so these are the production windows on a clock the run moves.
- **Separate machines.** The nodes share a process and a receipts folder, so every challenge judge can read the original receipts.

## Task 5.0: what's done and what isn't
- **Done:** `tests/integration/panel.py` is the panel interface. `PanelV2` reads `Verdicts.drawn`; `PanelV3` reads Panels' counted panel. Both answer who is drawn, how many decide, and whether a silent seat is replaced.
  - v2's suite reads its draws through it (scenarios 4, 7 and the books), and passes locally.
  - `scripts/integration.sh --version 3` runs `tests/integration/suite_v3.py` with `contracts/deployments/integration/devnet-v3.json`: registration and qualification, the replacement of a silent judge, the k = 1 hold and its audits, a waiting bounty, a challenge.
- **Not done:** v2's scenarios 1–3, 5, 7 and 10 aren't shared with v3. They go through pofctl, the bot and the relay, and none of them speaks v3. v3's suite calls the contracts directly.
- **Not verified:** v2's run on AWS.

So 5.0 isn't ticked.

## Findings
**Known ones, and what happened to each here.**
| Finding | Here |
|---|---|
| `Panels.drawAudits` accepts repeat calls | not fixed; the keeper's own limit (3 tries a registry state) kept it harmless |
| The on-chain `Receipt` has no validator or seat field | not fixed; no challenge here turned on it |
| The k = 1 hold needs 6 validators | not fixed; measured as a race between 4 and 7 (above) |
| A one-family network stalls under the family cap | worked around: 9 families priced at deployment, one a validator |
| The node image lacks the zkTLS checker; the prover is a stub | not touched: the `simulated` proof type only, and no node image |
| The relay doesn't speak v3 messages | worked around: the `onchain` transport, nodes in one process |
| `RaceV3` can't open ADRs or escalated fixes | not exercised |

**New ones.**
1. **Panels' windows are constants.** Task 5.2 asks for a deployment record with the seal, reveal and challenge windows in minutes. No such parameter exists, and the contracts have no setter by design. On AWS nobody can move the clock, so 5.2 needs a decision first: windows as constructor arguments for a test deployment, or a k = 1 verdict that takes a week.
2. **The node's keeper reads every submission since its start block on every pass.** A run of 100 checks makes it quadratic. The suite gives the keeper only the open submissions (`LiveChain`); a node that runs for weeks needs a cursor.
3. **`Wallet.send` waited 0.4 s between looks for a receipt,** which was most of the wall time of a local run. It's now an attribute (`poll_s`, still 0.4 s by default) that a test chain sets lower.
4. **A challenge or a draw whose sample finds too few validators waits for the registry to change,** not for time. In these runs a change always came (an activation, a top-up). On a quiet network anyone can force one with a 1 micro-coin `topUp`.
5. **A sealed vote not revealed after the majority revealed leaves its seat empty** (the owner's rule of 2026-11-13). It showed up by accident while writing the silent-judge scenario: a "silent" node that had already sealed isn't replaced.
6. **Every validator ever seated as a k = 1 verdict's auditor sits out of its challenge,** including a third, random audit and a replaced auditor. In the last run three validators had sat as the wrong verdict's auditors, so its challenge needed a seventh validator (v6) before a fresh panel of 3 existed. Not changed: it is D13's rule.
7. **A silence slash takes a floor bond under the floor, and the validator silently stops being drawn.** $5 off a $100 bond leaves $95: the validator stays `Active`, but `isDrawable` is false until it tops up, so the network shrinks by one with no event saying so. An earlier run stalled on exactly this (a challenge waiting for a validator that looked active). The script now checks it and tops the bond back up. Worth a decision: slash into a separate margin, or emit an event, or let the node top up on its own.

## Changed outside the new files
- `scripts/devnet.sh`: `deploy-v3` (local only; remote mode refuses it).
- `contracts/script/NodeV3Local.s.sol`: its record gains `version`, `testOnly`, `proofTypes` and `besideV2`. No contract under `contracts/src` changed.
- `oracle/rpc.py`: `Wallet.poll_s`. `oracle/abi.py`: `selector` is cached.
- `tests/integration/suite.py`: its draws read through the panel interface.

## Not done
- Validators as separate processes, the validator kit (task 4.2) and the node image.
- The AWS devnet (task 5.2) and v2's AWS run.
- The CI image run of task 5.3.
