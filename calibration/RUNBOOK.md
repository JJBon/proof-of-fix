# Calibration runbook (v3.1 on Sepolia)

This runbook qualifies the launch candidates on v3.1 with the calibration set (`README.md`). The owner decided it on
2026-11-24 (proof-of-fix#334). The plan is to raise the nodes' model caps for a day or two, run the set, then restore
the caps. The estimate is $30–55 of model spend and about $4 of AWS.

This file holds no account-specific values: no instance ids, endpoints, addresses, ARNs or keys. They live in the
operator's own files, named below.

## 0. Before you start

- **v3.1 is deployed, and its `Heads.head` contains `calibration/`.** The bugs must be in the commit that the
  deployment's head names, since every fix is based on it. So deploy after this set is merged, with the deployment's
  genesis commit at or after that merge. Check it with `pofctl --v3 checkout`, and `ls calibration/c01.py` in that
  tree.
- **The candidates are registered on v3.1.** v2–v7 are registered and in standing (attested, image listed, bonded),
  and `scripts/calibrate.py status` lists each of them as `Candidate` with `scored 0/20`.
- **The roles have pofctl configs.** The reporter, the solver and, if you pledge, the funder each have a pofctl
  config: a keystore, the record, the RPC in the config's `rpc` or in `POFCTL_RPC`. Also set
  `POFCTL_KEYSTORE_PASSWORD_FILE`, naming a file only you can read. The reporter and the solver need gas, and test
  coins (`pofctl faucet`, or the owner's genesis mint): `calibrate.py plan` prints the coins that one registration
  and one fix post.
- **A Radicle working copy of the repository** (`rad clone`), on the same machine, with a `rad` node running, for the
  solver's commits and patches (`--repo`).
- **The estimate:**

  ```bash
  scripts/calibrate.py plan --target sepolia --deployment "$RECORD"                     # FeesV3's caps: worst case
  scripts/calibrate.py plan --target sepolia --deployment "$RECORD" --tokens 6000:800   # a typical call
  ```

## 1. Raise the caps

Each node caps its own model spend (`oracle/spend.py`), on both a daily and a monthly cap. Raise both, or the
monthly cap stops the node long before the daily one does. Raise the per-run call cap too.

| node | setting | normal | for the calibration |
|---|---|---|---|
| genesis | `ORACLE_SPEND_DAILY_USD` | 0.50 | **30** |
| genesis | `ORACLE_SPEND_MONTHLY_USD` | 5 | at least 60 (two days at 30) |
| genesis | `ORACLE_MAX_CALLS` | 60 | e.g. 400 (each call is counted, retries included) |
| v2–v7 | `ORACLE_SPEND_DAILY_USD` | 0.50 | **10** |
| v2–v7 | `ORACLE_SPEND_MONTHLY_USD` | 5 | at least 20 |
| v2–v7 | `ORACLE_MAX_CALLS` | 60 | e.g. 200 |

**Genesis (the genesis kit).** The settings are in the kit's tfvars file
(`validator-kit/sevsnp/terraform/<your tfvars>`), in its `node_config` map. Save a copy of the file first. Then
change the three values, `tofu plan -var-file=<your tfvars>`, and check that the plan only updates the instance's
user data in place: nothing is replaced or destroyed. Apply it. The node reads `node_config` from the user data at
its next boot.

**v2–v7 (the temporary validators' directory, `~/dev/pof-validators`).** The settings are in `validators.json`,
`common.node_config`, which every validator shares. Save a copy (`validators.json.bak-<date>`), change the three
values, then for each N in 2..7:

```bash
scripts/pofv.py plan  N run        # writes vN/vN.tfvars.json from validators.json; refuses a delete or a replacement
scripts/pofv.py apply N run        # applies that saved plan only
```

**The AWS budget stop.** Each kit's budget (`budget_limit_usd`, $15) counts the whole account (the scope warning in
`~/dev/pof-validators/runbook.md`). A day of calibration can push the account toward it. When it fires, the instances
are stopped and the watchers hold their starts. Check the month's spend before you start. If the stop would fire
during the run, raise the limit for the run and restore it with the caps.

Check that every node runs with the new caps: the boot console's configuration lines, or the node's spend ledger at
its next run.

## 2. Run the calibration

The order of operations after the v3.1 deploy:

1. The deployment is final and its record is saved. `pofctl --v3 verify-head` passes, and the genesis validator is
   active.
2. v2–v7 are registered as candidates (`calibrate.py status`).
3. The caps are raised (step 1), and the nodes are running or their watchers are on.
4. Start with one item to see the whole path once:

   ```bash
   L=~/.proof-of-fix/calibration-v31.jsonl
   scripts/calibrate.py run --target sepolia --deployment "$RECORD" --ledger "$L" --items c01 --once \
     --config-reporter reporter.json --config-solver solver.json --repo ~/proof-of-fix --max-usd 2 --yes-spend
   scripts/calibrate.py status --target sepolia --deployment "$RECORD" --ledger "$L"
   ```

   The issue is on Radicle, the registration is on-chain, and the genesis validator draws its check (k = 1) with 2
   shadows.
5. Then register the rest, paced so that the nodes' keepers draw each check:

   ```bash
   scripts/calibrate.py run --target sepolia --deployment "$RECORD" --ledger "$L" --pace-seconds 120 --batch 10 \
     --config-reporter reporter.json --config-solver solver.json --repo ~/proof-of-fix --max-usd 55 --yes-spend
   ```

   The run can be stopped (Ctrl-C) and started again with the same command. It goes on from the ledger. It stops by
   itself before the estimated spend would pass `--max-usd`. Use `--no-fixes` to register only.
6. Follow `calibrate.py status`. Each candidate's `scored` should rise towards 20, with `revealed` near 100 % and
   `agreed` at 80 % or more. A candidate that fails its attempt cools off for 7 days (`QUALIFY_COOLDOWN`). Stop and
   look at it before registering more.
7. Once 6 candidates are active, the held verdicts' windows start and the registration checks become final. The same
   `run` command then opens the bounties, records the attempts, submits the prepared fixes as Radicle patches, and
   claims and merges the first passing good fix (`--merge 1`). Each item's ledger entry records whether its verdict
   matched the prepared fix's label (`asPrepared`).
8. Record the results for #329: the agreement and reveal rates, the cost (the nodes' spend ledgers and the model
   key's usage), and the time from the first registration to six active validators.

## 3. Restore the caps

Do this as soon as six candidates are active and the first calibration fix is merged, or at the end of the second
day, whichever comes first.

- **Genesis:** restore the saved tfvars (daily 0.50, monthly 5, calls 60), then plan and apply as in step 1.
- **v2–v7:** restore `validators.json` from the copy, then `scripts/pofv.py plan N run` and `apply N run` for each.
- Restore the AWS budget limit if you raised it.
- Check the nodes' next boots show the normal caps.

## The kill switch

If spend runs away, or a node misbehaves:

```bash
~/dev/pof-validators/scripts/kill-switch.sh            # all of v2..v7
~/dev/pof-validators/scripts/kill-switch.sh v3 v5      # only these
```

For each node, this disables the watcher's rule, throttles its Lambda to 0, stops the instance and marks it `killed`
in `validators.json`, so a later run-phase apply keeps the watcher off. It never touches the genesis validator, the
seed or the keeper. To stop the genesis validator, stop its instance and disable its watcher from the genesis kit.
To stop the calibration itself, stop `calibrate.py` (Ctrl-C): nothing new is registered or submitted, and the ledger
keeps its place. To undo the kill switch, run `kill-switch.sh --undo vN`, then `pofv.py plan N run` and
`apply N run`.
