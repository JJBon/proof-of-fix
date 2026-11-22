"""The bounty market (the default, proof-of-fix#15):
python3 -m pof.sim market run --scenario market --seed 1        one run's report (JSON)
python3 -m pof.sim market accept --seeds 20                      the market's acceptance check
python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20   the market's acceptance summary (reports/)
    (--award-mode auction reproduces the runs before #60, checking v6 and earlier)
python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20     the award modes compared (proof-of-fix#60)
python3 -m pof.sim market split --seeds 40                       the reporter's and the solver's split (proof-of-fix#56)
python3 -m pof.sim market tokens --seeds 40                      the token emission at each token price (proof-of-fix#58)
python3 -m pof.sim market validators --seeds 40                  v3's open validators under #141's round 2
    (proof-of-fix#141, task group 7): every scenario's table, each switch beside its rule, and the acceptance criteria
    under D17's round-2 criteria, met or not (markdown, not JSON; pof.sim.openval.round2; --jobs 4 runs it on four
    processes; reports/open-validators-v3.md)
python3 -m pof.sim market validators --seeds 40 --round3         round 3's addendum (task group 8,
    pof.sim.openval.round3): report v3's acceptance table re-judged under round 3's criteria, the silence-slash sweep
    and the deposit's honest cost (reports/open-validators-v3.1.md; --jobs 4 as above)
python3 -m pof.sim market validators --seeds 40 --v2r1           round 1's report (task group 6, pof.sim.openval.rerun)
    on round 1's rules, unchanged (reports/open-validators-v2.md)
python3 -m pof.sim market validators --seeds 40 --v1             #134's report (task 1.8, pof.sim.openval.full) on
    #134's rules, unchanged (reports/open-validators-v1.md)
python3 -m pof.sim market run --weeks 2 --seed 1 --export-events > contracts/test/data/race-1.json
python3 -m pof.sim market run --weeks 2 --seed 1 --export-events --tokens > contracts/test/data/tokens-1.json
    a race run in the contract's shape (CONTRACT), exported for the contract's replay (proof-of-fix#56 design D7)

The legacy pool (LEGACY: a fund per release split by lines changed, the placeholder of runs v1-v5), kept to compare
with and to reproduce those runs:
python3 -m pof.sim run --scenario honest --seed 1               one run's report (JSON)
python3 -m pof.sim accept --seeds 20                             every legacy scenario, with the acceptance check
python3 -m pof.sim summary --seeds 100 --sweep-seeds 20          the legacy acceptance summary (reports/acceptance-v5)
"""

from __future__ import annotations

import argparse
import json
import sys

from . import export as X
from . import market_sim as MS
from . import scenarios as S
from .report import acceptance, report
from .summary import summarize
from ..params import CONTRACT


def _validators_v1(a) -> int:
    """#134's report (pof.sim.openval.full) with every default #134's: POF_OPENVAL_RULES=v1, read when
    pof.sim.openval.params is first imported, so it needs a process that hasn't imported it yet (as the command is)."""
    import os
    seeds, sweep = range(1, a.seeds + 1), (range(1, a.sweep_seeds + 1) if a.sweep_seeds else None)
    if "pof.sim.openval.params" in sys.modules and sys.modules["pof.sim.openval.params"].RULES != "v1":
        print("--v1 needs a fresh process: python3 -m pof.sim market validators --v1", file=sys.stderr)
        return 2
    os.environ["POF_OPENVAL_RULES"] = "v1"
    from .openval.full import full_report
    print(full_report(seeds, sweep, quick=a.quick))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim")
    sub = ap.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="LEGACY pool (pay by lines changed): one run")
    run.add_argument("--scenario", choices=S.SCENARIOS, required=True)
    run.add_argument("--seed", type=int, default=1)
    run.add_argument("--weeks", type=int, default=S.WEEKS)
    run.add_argument("--share", type=float, help="collusion: the colluders' share of validator stake")
    run.add_argument("--self-interested", action="store_true", help="owner: the self-interested owner")
    run.add_argument("--multiplier", type=int, help="risk: the high-risk stake multiplier")
    run.add_argument("--mechanism-off", action="store_true", help="replay: the contribution stream only")
    acc = sub.add_parser("accept", help="LEGACY pool: the acceptance check")
    acc.add_argument("--seeds", type=int, default=20)
    acc.add_argument("--weeks", type=int, default=S.WEEKS)
    acc.add_argument("--summary", action="store_true", help="omit the per-run reports")
    summ = sub.add_parser("summary", help="LEGACY pool: the acceptance summary")
    summ.add_argument("--seeds", type=int, default=20)
    summ.add_argument("--sweep-seeds", type=int, help="seeds for the sweeps and ablation (default: --seeds)")
    summ.add_argument("--weeks", type=int, default=S.WEEKS)
    mk = sub.add_parser("market", help="the bounty market (the default, proof-of-fix#15)")
    mk.add_argument("action", choices=("run", "accept", "summary", "modes", "split", "tokens", "validators"))
    mk.add_argument("--scenario", choices=MS.SCENARIOS, default="market")
    mk.add_argument("--seed", type=int, default=1)
    mk.add_argument("--seeds", type=int, default=20)
    mk.add_argument("--sweep-seeds", type=int)
    mk.add_argument("--weeks", type=int, default=MS.WEEKS)
    mk.add_argument("--award-mode", choices=("race", "auction", "claim"), default="race",
                    help="how jobs are awarded (#60): the race is the default; auction reproduces runs before it")
    mk.add_argument("--contract", action="store_true",
                    help="run: the contract's shape (CONTRACT: no treasury, matching, trust discount or market fee)")
    mk.add_argument("--export-events", action="store_true",
                    help="run: the run's events for the contract's replay (#56 D7), instead of its report; implies "
                         "--contract")
    mk.add_argument("--quick", action="store_true",
                    help="validators: one row per section (the tests' reproducibility check), not a result to read")
    mk.add_argument("--v1", action="store_true",
                    help="validators: #134's report on #134's rules (reports/open-validators-v1.md), unchanged")
    mk.add_argument("--round3", action="store_true",
                    help="validators: round 3's addendum (reports/open-validators-v3.1.md): v3 re-judged, the sweeps")
    mk.add_argument("--v2r1", action="store_true",
                    help="validators: round 1's report on round 1's rules (reports/open-validators-v2.md), unchanged")
    mk.add_argument("--jobs", type=int, default=1,
                    help="validators: processes to run the sections on (the numbers don't change)")
    mk.add_argument("--tokens", action="store_true",
                    help="run --export-events: with the token emission on (pof's TOKENS on the contract's shape) and "
                         f"solvers valuing a token at {X.REPLAY_TOKEN_PRICE} (#56 task 3.4)")
    a = ap.parse_args(argv)
    if a.command == "run":
        knobs = {k: v for k, v in (("share", a.share), ("multiplier", a.multiplier)) if v is not None}
        if a.self_interested:
            knobs["self_interested"] = True
        if a.mechanism_off:
            knobs["mechanism"] = False
        world = S.run(a.scenario, a.seed, weeks=a.weeks, **knobs)
        out = report(world, a.scenario, a.seed, **knobs) if world.mechanism else {
            "scenario": a.scenario, "seed": a.seed, "contributions": len(world.stream)}
    elif a.command == "market" and a.action == "validators":  # v3's open validators (pof.sim.openval)
        seeds, sweep = range(1, a.seeds + 1), (range(1, a.sweep_seeds + 1) if a.sweep_seeds else None)
        if a.v1:
            return _validators_v1(a)
        if a.v2r1:  # round 1's report reads round 1's rules explicitly (params.V2R1), whatever the defaults
            from .openval.rerun import full_report as round1_report
            print(round1_report(seeds, sweep, quick=a.quick, jobs=max(1, a.jobs)))
            return 0
        if a.round3:  # round 3's addendum: v3's numbers re-judged, and the sweeps round 3 added
            from .openval.round3 import full_report as round3_report
            print(round3_report(seeds, quick=a.quick, jobs=max(1, a.jobs)))
            return 0
        from .openval.round2 import full_report
        print(full_report(seeds, sweep, quick=a.quick, jobs=max(1, a.jobs)))
        return 0
    elif a.command == "market":
        params = (CONTRACT if a.contract or a.export_events else MS.MARKET).with_(award_mode=a.award_mode)
        if a.action == "run" and a.export_events and a.tokens:
            out = X.export(a.seed, scenario=a.scenario, params=X.CONTRACT_TOKENS.with_(award_mode=a.award_mode),
                           weeks=a.weeks, token_price=X.REPLAY_TOKEN_PRICE)
        elif a.action == "run" and a.export_events:
            out = X.export(a.seed, scenario=a.scenario, params=params, weeks=a.weeks)
        elif a.action == "run":
            out = MS.market_report(MS.run(a.scenario, a.seed, params, weeks=a.weeks), a.scenario, a.seed)
        elif a.action == "accept":
            out = MS.acceptance(range(1, a.seeds + 1), params, weeks=a.weeks)
            out.pop("runs")
        elif a.action == "tokens":  # #58: the token emission at each swept token price
            out = MS.tokens_summary(range(1, a.seeds + 1), weeks=a.weeks)
        elif a.action == "split":  # #56 D13: the reporter's share of the payout
            out = MS.split_sweep(range(1, a.seeds + 1), weeks=a.weeks)
        elif a.action == "modes":  # #60: the award modes compared
            sweep = range(1, a.sweep_seeds + 1) if a.sweep_seeds else None
            out = MS.summarize_modes(range(1, a.seeds + 1), weeks=a.weeks, sweep_seeds=sweep)
        else:
            sweep = range(1, a.sweep_seeds + 1) if a.sweep_seeds else None
            out = MS.summarize(range(1, a.seeds + 1), params, weeks=a.weeks, sweep_seeds=sweep)
    elif a.command == "summary":
        sweep = range(1, a.sweep_seeds + 1) if a.sweep_seeds else None
        out = summarize(range(1, a.seeds + 1), weeks=a.weeks, sweep_seeds=sweep)
    else:
        out = acceptance(range(1, a.seeds + 1), weeks=a.weeks)
        if a.summary:
            out.pop("runs")
    json.dump(out, sys.stdout, indent=2, default=str)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
