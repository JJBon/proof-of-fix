#!/usr/bin/env bash
# Time to heal on the local devnet (proof-of-fix#140; the thesis of reports/self-healing-v1.md): how long a wrong
# verdict stands before the network reverses it, in chain time, with the mechanisms the v3 contracts have today
# (a staked challenge judged by a fresh, larger panel). It is scripts/devnet-v3-e2e.sh --heal, which measures two:
#   - a wrong k = 1 verdict of the lone genesis validator (a registration nobody claimed, passed anyway), challenged
#     at once, reversed by a fresh panel of 3 once six validators exist;
#   - a bad fix passed 2 to 1 by a panel of 3 with two lying judges, won and claimed, challenged at once, reversed by a
#     fresh panel of 5 once five more validators are bonded for its bounty; the award is clawed back with nothing earned.
# Each prints the time from the wrong pass to its reversal, split into: until the challenge, the challenge's wait for
# a panel to exist, and the panel's own seal and reveal windows.
#
# What it doesn't measure: detection (the watcher here challenges at once; its judge is the fake one), the
# test-backed dispute, the solver's deposit and the appeal of D21-D23 (task 10.4: not built), and short test windows
# (Panels' windows are constants, so these are the real windows' times on a clock the run moves).
#
#   scripts/time-to-heal.sh [--report <file>] [--verbose]      about 7 minutes; needs Docker
set -euo pipefail
cd "$(dirname "$0")/.."
export POF_V3_E2E_NAME=${POF_HEAL_NAME:-pof-devnet-heal} POF_V3_E2E_PORT=${POF_HEAL_PORT:-8559} \
  POF_V3_E2E_STATE=.devnet-heal POF_V3_E2E_RECORDS=heal POF_V3_E2E_WORK=.heal
exec scripts/devnet-v3-e2e.sh --heal "$@"
