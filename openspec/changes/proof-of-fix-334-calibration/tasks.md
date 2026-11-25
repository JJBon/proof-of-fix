## 1. The calibration set

- [x] 1.1 `calibration/`: 60 items (buggy module with `FIXED = False`, visible test, issue text, prepared fix), 45
  good and 15 bad, and the README that labels them as calibration issues
- [x] 1.2 `tests/test_calibration.py`: the protected tests, each skipped until its item's fix sets `FIXED`
- [x] 1.3 `scripts/calibrate_items.json`: the good or bad label, kept out of what the judges read
- [x] 1.4 Test: each protected test fails on its bug (FIXED forced), the prepared fix passes the visible test and
  passes the protected one exactly when it is good, and main's suite stays green (`tests/test_calibrate.py`)

## 2. The driver

- [x] 2.1 `scripts/calibrate.py plan | run | status`, with `--target`, `--deployment`, `--max-usd`, `--pace-seconds`
  and `--ledger`: register, open, pledge, attempt, submit as a Radicle patch, claim and merge, through pofctl
- [x] 2.2 The ledger (JSONL) and resuming from it; the budget from FeesV3's prices; redaction with oracle/redact.py;
  `--yes-spend` and an explicit `--max-usd` on Sepolia
- [x] 2.3 Test: plan, resume, ledger, budget stop, refusal without `--yes-spend`, no RPC URL printed
  (`tests/test_calibrate.py`)

## 3. The local proof and the runbook

- [x] 3.1 `tests/integration/calibration_radicle.py` (`scripts/integration.sh --version 3 --radicle --calibration`):
  candidates go from Candidate to Active on calibration checks; a good fix passes and merges; a bad one fails
- [x] 3.2 `calibration/RUNBOOK.md`: the caps raised and restored, the order of operations after the v3.1 deploy, the
  kill switch
- [x] 3.3 Run the check (`bash scripts/check.sh`)

## 4. On Sepolia (after the v3.1 deploy, with the owner's go)

- [ ] 4.1 Raise the caps, run the set, six candidates active, the hold ends, a calibration fix final and merged
- [ ] 4.2 Restore the caps; record agreement, reveal rates, cost and time for #329
