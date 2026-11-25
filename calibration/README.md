# Calibration issues

**These are calibration issues: deliberate, small bugs kept in this repository to qualify validators.** Nothing here
is a real defect of proof-of-fix. Each Radicle issue registered from this set says so in its title (`calibration
cNN: …`) and its text. The set was added for proof-of-fix#334, with the owner's decision of 2026-11-24.

## Why

On v3 and v3.1 only one validator is active from the deployment (`Validators.GENESIS_MAX = 1`, D10). Every other
validator registers as a candidate. A candidate becomes active after `QUALIFY_VERDICTS` (20) scored shadow verdicts,
with a reveal rate of at least 95 % (`QUALIFY_REVEAL_BPS`) and agreement of at least 80 % (`QUALIFY_AGREE_BPS`). Until
enough validators are active, every k = 1 verdict stays held: no check becomes final, no bounty opens and nothing
merges. A new deployment starts from zero, so the six launch candidates (v2 to v7) need about 6 × 20 = 120 scored
shadow verdicts before anything else can happen. This set provides the checks for them.

## What is in an item

Each of the 60 items `cNN` has:

| part | where | what |
|---|---|---|
| the buggy code | `calibration/cNN.py` | one small function with one bug, and `FIXED = False` |
| a visible test | `calibration/test_visible.py`, class `CNN` | the issue's own example |
| a protected test | `tests/test_calibration.py`, class `CNN` | the example and the edge cases |
| the issue text | `calibration/issues/cNN.md` | its first line is the title |
| a prepared fix | `calibration/fixes/cNN.py` | the whole module after the fix, with `FIXED = True` |

Whether a prepared fix is good or bad is recorded only in the driver's data, `scripts/calibrate_items.json`. The
judges read the issue, the fix's diff and the test results (`oracle/judge.py`, `case_for`). None of those holds the
label, and `tests/test_calibrate.py` checks that the issues and fixes don't hint at it.

- **45 prepared fixes (75 %) are good.** They pass the visible and the protected test.
- **15 (25 %) are bad.** They are subtly wrong: they pass the visible test (the issue's example) but fail the protected
  one on an edge case. For example, c04's fix counts `"Apple"`'s vowels right but not `"EIO"`'s, and c36's truncates
  text that already fits.

Every item is deterministic, uses no network and runs in microseconds: the whole set's tests take well under a second.

## How the tests stay green on main, and still judge a fix

A validator's check runs the repository's command from `.pof/check.json`, `python -m unittest discover -s tests -t
tests`. It runs on a tree where `tests/` (protected) is the base's copy, then runs the acceptance run at the root,
`python -m unittest` (`oracle/checkconfig.py`, `oracle/runtree.py`). The tests pass if every command exits 0. Nothing
runs the base on its own to see a test fail first. So a protected test that failed on main would make main red, and
every fix to proof-of-fix would fail its check with it.

So every calibration test is gated on its item's `FIXED` flag:

- **On main**, every item says `FIXED = False`. Its protected and visible tests skip (`skipTest` in `setUp`), so
  main's suite and CI (`scripts/check.sh`) stay green with all 60 bugs present.
- **A fix** sets `FIXED = True` in the module it fixes. That item's tests then run on the fix's code. The protected
  test comes from the base, since a fix can't change `tests/`. A good fix passes. A bad fix passes the visible test but
  fails the protected one, so the run exits non-zero and the check fails.
- **"Fails before the fix"** is checked by `tests/test_calibrate.py`. For every item it forces `FIXED = True` on the
  buggy module and checks that both the protected and the visible test fail. It then checks that the prepared fix
  passes the visible test, and that it passes the protected test exactly when the driver's data says it is good.
- Once a calibration fix is merged on the race's main, its module says `FIXED = True`. `tests/test_calibrate.py`
  then checks that the protected test passes on the merged code, instead of checking the bug.
- A fix that repairs the code but leaves `FIXED = False` skips its own tests. The judges then decide from the diff and
  the issue alone. The prepared fixes always set it.

The visible tests are found by the root acceptance run because `calibration/` is a package. CI's `discover -s
tests` finds the protected ones.

## How many checks an item makes, and how many shadow verdicts

Each item makes **two checks**:

1. **Its registration check.** `pofctl --v3 issue register` posts it, and its panel judges whether the Radicle issue
   is a genuine bug report in scope. It doesn't run tests.
2. **Its fix's check**, which runs the tests. It can only come after the registration check is **final**, since
   `RaceV3.openBounty` refuses (`NotYet`) before then. A k = 1 verdict is held until enough validators are active to
   judge its challenge, so no registration check becomes final while the candidates are still qualifying.

So **qualification comes from the registration checks.** The fix checks come afterwards. Their shadows count only
for candidates that are still qualifying then.

The shadow seats for each check (`Panels.sol`, `PanelsVerdict.sol`):

| check | shadows | scored against |
|---|---|---|
| drawn at k = 1 by the genesis validator (fewer than K_MAX = 7 active) | `SHADOW_PER_DRAW_SMALL` = 2 | the majority of the held verdict's vote and the two shadows' votes, once 3 are revealed |
| waiting (the genesis validator already holds `K1_PENDING_MAX` = 10 pending k = 1 verdicts, or no k fits) | `SHADOW_PER_WAITING` = 3 for each retry | the majority of the 3 shadows' votes, once 3 are revealed |
| a fix, drawn at k = kTop (3 at the launch) | 2 while fewer than 7 are active, then 1 | the final outcome |

A held k = 1 check gives 2 scored verdicts only if both shadows reveal: with one missing, only 2 votes are revealed,
so neither shadow is scored and the miss counts against the reveal rate. A waiting check is drawn again at each retry
(`RETRY_DELAY`, or a change in the registry), and each draw seats 3 more shadows. So waiting checks give more verdicts
per registration than the floor below.

**Sizing.** At the floor of 2 scored shadow verdicts per registration check, **60 registration checks give 120 scored
shadow verdicts**, which is 20 for each of the 6 candidates. That is the owner's estimate of about 60 checks in #334.
The waiting checks' redraws and the later fix checks add a margin. In the local proof
(`tests/integration/calibration_radicle.py`, run on 2026-11-24 with the devnet's short windows and the fake judge),
the six candidates qualified after **36 registration checks**, with **143 scored shadow verdicts**, all on calibration
checks. Waiting checks were drawn again each time a candidate qualified. With real models, a missed reveal costs a
check its shadow verdicts, so keep the full 60 available. The driver stops registering
once its budget is reached, and `--items` or `--no-fixes` can limit it further.

## Running it

`scripts/calibrate.py` drives the set (`plan`, `run`, `status`; see its docstring). It registers each issue on
Radicle and on-chain through pofctl, follows each registration check and records its seats and scored shadows. Once
a check is final, it opens the bounty, records the attempt, commits the prepared fix on `Heads.head` in the solver's
working copy, seals it and opens the Radicle patch. It claims and merges up to `--merge` passing good fixes. Each step
is appended to a JSONL ledger, so a run can be stopped and resumed.

```bash
scripts/calibrate.py plan                                             # the counts, offline
scripts/calibrate.py plan --target sepolia --deployment "$RECORD"     # with FeesV3's prices and the coins needed
scripts/calibrate.py status --target sepolia --deployment "$RECORD" --ledger "$LEDGER"   # each candidate's counters
```

On Sepolia, `run` refuses to start without `--yes-spend` and an explicit `--max-usd`. Follow `RUNBOOK.md`.

The local proof runs on the Radicle devnet with the fake judge, with no model, no public chain and no AWS:

```bash
POF_RADICLE_PREFIX=pofcal scripts/integration.sh --version 3 --radicle --calibration
```

The unit tests (`tests/test_calibrate.py`, run by `scripts/check.sh`) check every item and the driver's plan, ledger,
resume, budget stop and Sepolia refusal.
