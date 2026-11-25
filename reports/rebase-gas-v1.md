# Rebase in place: sizes and gas, v1

proof-of-fix #310 (task 1.6 and 1.7 of `openspec/changes/proof-of-fix-310-rebase-in-place`). Date: 2026-11-23. Branch
`proof-of-fix-310-rebase`, on `origin/main` 072d4a3. Pinned Foundry 1.8.5, solc 0.8.37, `via_ir`, 200 optimizer runs.

**Not measured on Sepolia.** The task asks for the new transactions on a throwaway Sepolia deployment of the branch, as
`reports/glamsterdam-runtime-v1.md` did. That needs the owner's go and a Sepolia key, which this change's
implementation doesn't have, so it waits for the release candidate (task 7.2). What's here is the closest local
tooling allows: each transaction's gas under the old rules, and the storage slots it creates, with the EIP-8037
estimate that follows from the report's own measurement, calibrated against `register`, which the report measured.

## Sizes (task 1.6)

`scripts/contracts.sh sizes`. EIP-170's limit is 24,576 B; the rule is at least 512 B of runtime margin each.

| Contract | Runtime before (B) | Runtime after (B) | Margin after (B) | Initcode margin after (B) |
|---|---:|---:|---:|---:|
| RaceV3 | 22,612 | 22,982 | **1,594** | 16,347 |
| RaceV3Annex | 22,362 | 23,406 | **1,170** | 22,567 |
| RaceV3Endings | 21,845 | 23,381 | **1,195** | 22,784 |
| Panels | 19,026 | 19,026 | 5,550 | 26,452 |
| Validators | 22,908 | 22,908 | 1,668 | 17,992 |
| FeesV3 | 18,026 | 18,026 | 6,550 | 28,889 |
| SolverBook | 3,707 | 3,707 | 20,869 | 45,188 |
| Heads (v2) | 1,091 | 1,091 | 23,485 | 47,246 |

Panels, Validators, FeesV3, SolverBook and Heads are unchanged (their sources are untouched). The 10 % share stays.

**How it fits (RB10).** With `rebase` and the extended `mergeExpired` both in the Endings, as RB10's table placed them,
the Endings came to 24,450 B: 126 B of margin. RB10's first fallback, dropping the share, would have saved a few dozen
bytes in each companion (it sits in `_settle`), not enough; the second is a third companion. Before either, two
changes that move no behaviour:

- `mergeExpired` moved to the annex (it reaches `_reopen` and `_decide`, which the annex already holds for `_sync`), so
  the Endings keep only `rebase`;
- the head is read from `Heads.head`'s record by word (`_headRecord`, `_w`), not decoded into a struct.

That gives the margins above, every one over 1,100 B, with no third companion and no change to the deploy scripts.

## Gas (task 1.7)

From `test_gasUnderEip8037` in `contracts/test/v3/RebaseV3.t.sol` (run it with `scripts/contracts.sh test
--match-test test_gasUnderEip8037 -vv`): each transaction is called once, with the state diff recorded. "Old rules" is
its execution gas measured in the test plus the intrinsic 21,000 and its calldata (4 a zero byte, 16 otherwise), what a
receipt's `gasUsed` would be before Glamsterdam. "Slots created" are the storage slots zero at its start and nonzero at
its end (state gas under EIP-8037). The report measured a new slot at 110,028 gas as `gasleft()` sees it (97,920 state
+ 12,108 execution) against 22,100 before, so each one adds **87,928**.

| Transaction | Old rules (gas) | Slots created | EIP-8037 estimate (gas) | Design's estimate (RB11) |
|---|---:|---:|---:|---:|
| `register` (calibration) | 791,948 | 20 | 2,550,508 | report: 639,079 old, **2,416,879** on Sepolia |
| `rebase` | 842,652 | 18 | **2,425,356** | 2.2–2.6M |
| `merge` through a rebase | 359,275 | 6 | **886,843** | today's `merge` + 2–3 cold reads and an overwrite |
| `mergeExpired`'s reopening | 196,573 | 1 | **284,501** | today's |

**The calibration.** On Sepolia `register` grew by 1,777,800 gas (2,416,879 − 639,079), which is 20.2 slots at 87,928;
here it creates 20 slots and the estimate adds 1,758,560 (1.1 % less). Its old-rules gas differs from the report's
because the suite's deployment differs (#132's strict rules, `kTop` 7, so a larger deposit to quote, and other
validators), not the method.

**`rebase`.** 18 new slots: the submission's record (its bounty, day, solver, commitment, deposit, judged, pledges,
fix, base, `rebaseOf`), FeesV3's prices for the check, Panels' new submission, the SolverBook claim and `Award.rebase`.
At about 2.4M it sits inside RB11's estimate and far below 2^24, so the reservoir caveats (the report's R1, R2) don't
apply. None of the new code reads `gasleft()`.

**`merge` through a rebase.** 6 new slots: `paidFix` for both commits, and the SolverBook's records of the winner
(its reputation, its fix, its time and place in the activity list: its first merged fix in this run). Heads' record is
overwritten, not created, after the first merge; the claims' closing clears slots.

**The re-check panel.** Its chain gas is any check's (the report's table: draw 1.43M, seal 171k, receipt 160k, reveal
468k, report 499k, result 699k on Sepolia); nothing about a rebase changes it.

`forge test --gas-report --match-contract RebaseV3Test` (old rules, execution only, through RaceV3; min / avg / median /
max over the suite's calls): `rebase` 33,972 / 581,427 / 817,290 / 828,593 (the low ones are refusals); `merge`
26,435 / 280,307 / 312,961 / 348,233; `mergeExpired` 107,427 / 163,480 / 169,300 / 229,666.

## What's left for Sepolia

Task 7.2's release candidate runs on a throwaway Sepolia deployment anyway: `rebase`, `merge` through a rebase and the
reopening should be sent there once, with the tools' own gas limits, and their `gasUsed` recorded against this table.
