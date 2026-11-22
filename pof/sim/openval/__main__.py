"""python3 -m pof.sim.openval {growth,attackers,sybil,audits,levels,pricing,scores,all,params} --seeds N (see pof.sim.openval.report)."""

import sys

from .report import main

if __name__ == "__main__":
    sys.exit(main())
