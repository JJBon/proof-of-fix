"""proof-of-fix#40 design D1: the market's acceptance on the verdict seeds without a reserve (100 %) and at 90 %, at
each hunting elasticity, to see what the reserve itself buys. Output: JSON on stdout.

    python3 scripts/reserve_ablation.py > reports/acceptance-market-v4-reserve.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pof.params import DEFAULTS  # noqa: E402
from pof.sim import market_sim as M  # noqa: E402


def row(reserve_bps: int, elasticity: float, seeds=range(1, 101)) -> dict:
    r = M.acceptance(seeds, DEFAULTS.with_(reserve_bps=reserve_bps), hunt_elasticity=elasticity)
    c, h = r["criteria"], M._headline(r)
    return {"reserve_bps": reserve_bps, "hunt_elasticity": elasticity, "passed": r["passed"],
            "failed_criteria": h["failed_criteria"],
            "rings": {k[5:]: c[k] for k in sorted(c) if k.startswith("ring@")},
            "bluffer_gain": c.get("bluffer_gain"), "solver_net_of_effort": c.get("solver"),
            "bounties_paid": h["bounties_paid"], "bounties_unsolved": h["bounties_unsolved"],
            "bond_change": c.get("bond_change")}


if __name__ == "__main__":
    rows = [row(10_000, e) for e in (0.0, 0.5, 1.0)] + [row(9_000, 0.5)]
    json.dump({"seeds": 100, "rows": rows}, sys.stdout, indent=2, sort_keys=True)
    print()
