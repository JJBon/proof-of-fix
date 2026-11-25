## Why

On v3 and v3.1 only the genesis validator is active from the deployment (`Validators.GENESIS_MAX = 1`, D10, #141).
The six launch candidates (v2 to v7) each need 20 scored shadow verdicts (`QUALIFY_VERDICTS`), a 95 % reveal rate and
80 % agreement before they are active. Until enough of them are, every k = 1 verdict stays held, so no check is final
and nothing merges. That blocks #329's "first merged fixes before Show HN". v3.1 is a new deployment, so qualification
starts from zero there. On 2026-11-24 the owner decided to seed about 60 clearly labelled calibration checks right
after the v3.1 deploy, with the nodes' model caps raised for the run. The contracts don't change (D10 stays).

Ticket: #334. Refs #251, #329, #328.

## What Changes

- **A calibration set** (`calibration/`). It has 60 deliberate, small bugs, each with the buggy code, a visible test,
  a protected test under `tests/` (`tests/test_calibration.py`), an issue text and a prepared fix. 45 prepared fixes
  are good. 15 are subtly wrong: they pass the visible test and fail the protected one. Every test is gated on its
  item's `FIXED` flag, so main's suite stays green with every bug present, and a fix that sets the flag is judged by
  the protected test. The good or bad label is only in the driver's data (`scripts/calibrate_items.json`).
- **A driver** (`scripts/calibrate.py plan | run | status`). It registers each issue through pofctl, with Radicle,
  and follows its check. Once the check is final, it opens the bounty, pledges if asked, records the attempt, submits
  the prepared fix as a Radicle patch, and claims and merges up to `--merge` passing good fixes. It reads each
  candidate's qualification counters from `Validators`. It records everything in a JSONL ledger and resumes from it.
  It estimates each check's model spend from FeesV3's prices and stops before `--max-usd`. It never prints the RPC URL
  or a key. `run --target sepolia` refuses to start without `--yes-spend` and an explicit `--max-usd`.
- **The local proof** (`scripts/integration.sh --version 3 --radicle --calibration`). On the Radicle devnet with the
  fake judge, six candidates qualify on calibration checks alone. The driver then submits a good fix, which passes
  and merges, and a bad one, which fails.
- **A runbook** (`calibration/RUNBOOK.md`): raising the nodes' caps (genesis to $30 a day, v2–v7 to $10, the monthly
  and per-run caps with them), the order of operations after the v3.1 deploy, restoring the caps, and the kill
  switch.

Out of scope: running it on Sepolia (that waits for the owner's go after the v3.1 deploy), any contract change, and
the nodes' configuration files, which the runbook describes but this change doesn't edit.

## Actors, incentives and attacks

- **Validators.** Calibration checks are real checks: the candidates' shadow verdicts are scored by the contracts'
  existing rules. During qualification they judge registration checks, which ask whether an issue is a genuine bug
  report in scope, because a fix can only follow a registration check that is final. The bad prepared fixes measure
  agreement on fixes once the hold ends.
- **The owner's keys** play the reporter and the solver. Registrations pay the deployment's fees in the test coin,
  which has no value. Nothing is hidden: every issue and fix is labelled as calibration, so no one is misled about
  what was fixed.
- **Model spend** is bounded twice: by the driver's `--max-usd` and by each node's raised caps, which are restored
  afterwards.
