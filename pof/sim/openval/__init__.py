"""v3's open validators, simulated (proof-of-fix#134, the simulation of #132's specs: tasks 1.1-1.8).

- `params`: `Params`, every design parameter phase 1 reads, with the design's starting values (the ADR, #137, cites
  them), and `World`, the simulation's assumptions;
- `registry`: registration, candidates, qualification by shadow judging, the reveal-rate floor, unbonding, the
  genesis validator (task 1.1);
- `panels`: k, the seed, sampling under the caps, replacement, challenge panels, the constitution tier, the audit
  draw, as pure functions of a seed and a registry snapshot (task 1.2, D13);
- `net`: the network over time, with phase 2's hooks (the fee, the panel's proof level, the families' eligibility
  and outcome record);
- `actors`: the sybil, the colluding lone validator, the seed grinder, the silent judge, the fee farmer, the
  constitution coalition and D13's cheater, each against its honest twin (task 1.3, 1.6);
- `report`: the phase-1 tables of reports/open-validators-v1.md (`python3 -m pof.sim.openval`);
- `levels`, `pricing`, `scores`: proof levels (task 1.5), market pricing (1.4) and model scores (1.7);
- `full`: task 1.8, the k table compared, the window's length, scores on the market fee, the acceptance criteria and
  the whole v1 report (`python3 -m pof.sim market validators --v1`);
- `rerun`: #141's re-run (task group 6): #141's rules are the defaults (`params.V2`; #134's are `params.V1`), each
  alternative a switch run beside its rule, the new scenarios, the acceptance check under D17, and the v2 report
  (`python3 -m pof.sim market validators --v2r1`, reports/open-validators-v2.md);
- `round2`: round 2's re-run (task group 7): the v3 report (`python3 -m pof.sim market validators`,
  reports/open-validators-v3.md), and the acceptance check under D17's round-2 or round-3 criteria;
- `round3`: round 3 (task group 8): report v3 re-judged under round 3's criteria, the silence-slash sweep and the
  deposit's honest cost (`python3 -m pof.sim market validators --round3`, reports/open-validators-v3.1.md).

Simulated only (rule 1): nothing here opens a connection, holds a key or moves money.
"""
