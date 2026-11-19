# Paper draft: open problems (section 7 of the outline)

Status on 2026-11-15. Each problem says what is known, with the report it comes from, why it matters, and what would
settle it. They are written as work someone else can pick up: this section is the invitation to collaborate.

## 7.1 The judges are the weakest part

**Known** ([`reports/judges-v2.md`](../../reports/judges-v2.md), 228 labelled fixes, no test run shown to the judge):

| Judge | Bad fixes that fail the hidden tests, passed | Bad fixes that pass the tests but are wrong, passed | Good fixes rejected |
|---|---|---|---|
| Claude Opus 5.5 | 19 % | 46 % | 2 % |
| GPT-6.1 Sol | 40 % | 19 % | 30 % |
| Gemini 3.1 Pro (low reasoning effort) | 78 % | 51 % | 2 % |
| Six open-weight models | 71–96 % | 68–94 % | 2–17 % |

- Most models approve almost everything. One is strict and rejects a third of the good fixes. Only one is usable on
  both sides, and it still passes nearly half of the fixes that pass the tests and are wrong.
- The mistakes are shared: of the 18 bad fixes the best judge passed in one pool, at least one of the other eight
  judges rejected 11, and all nine passed the other 7. A larger panel of today's models does not vote the error away.
- The judges were not compared on equal terms: reasoning settings and prices differ per provider.

**Why it matters:** every payment rests on a verdict. The mechanism survives this through deposits, audits and
disputes (7.2), not through good judging.

**What would settle it:** a judge, a prompt, a tool or a panel rule that lowers the 46 % without raising the 2 %, shown
on the same cases under the same pre-registered rule. Two things tried and reported here did not do it:
- A code graph of the repository, as features with no model: no better than chance
  ([`reports/graph-test-v1.md`](../../reports/graph-test-v1.md)).
- Notes on earlier rejected fixes, given to the judge: a pilot on the best judge cut its wrong approvals from 25 to
  16–18 of 28 with good fixes unchanged, but it was exploratory and run outside the judge's normal path
  ([`reports/memory-pilot-v1.md`](../../reports/memory-pilot-v1.md)); the pre-registered run on GPT moved 21 to 17 of
  101 and missed its threshold, p = 0.0625 ([`reports/judges-memory-v1.md`](../../reports/judges-memory-v1.md)).
  It did no harm and is not confirmed.

## 7.2 Disputes carry the design, and their key rate is assumed

**Known** ([`reports/open-validators-measured-v2.md`](../../reports/open-validators-measured-v2.md)): with the best
family alone on the panel, 6.0 bad fixes are paid per 100. If a contender finds a failing test for a quarter, a half
or three quarters of the bad fixes its model rejected, that falls to 5.2, 4.4 or 3.5.

**Not known:** how often a model that rejects a fix can also write a test that fails on it and that a panel accepts
as stating the issue's requirement, and how often a wrong test is accepted. Both are inputs today, not measurements.

**What would settle it:** the measurement in task 10.3 of the open-validators change: on labelled fixes, ask the
contender's model for a failing test, run it, and have a panel rule on it.

## 7.3 One family holds the seats

Seats go to the families that score within a margin of the best. On today's numbers that is one family. The family
cap, the design's defence against one provider's shared blind spot, then has nothing to cap. The simulation says the
alternative (seating weaker families for diversity) pays more bad fixes. This is a measured trade-off, not a solved
problem, and it moves each time a provider ships a model.

## 7.4 Everything was measured on one benchmark

- The cases are SWE-bench Verified issues from eleven Python projects.
- The good fixes are the projects' own and the bad ones were written by models, so a feature can separate the author
  and not the quality (the graph test found exactly this for "touches tests").
- The judges saw no test run, the hardest setting. A live check runs the tests first.

**What would settle it:** the same measurement on other languages, on bad fixes written by people, and with the test
run shown.

## 7.5 The reference implementation is a prototype

- No audit. The contracts pass their unit, invariant and replay tests; that is all.
- Two known findings are fixed for the testnet launch (#251, task 3.10). `Panels.drawAudits` accepted repeat calls,
  which let a caller re-target the audit draw; now a draw that finds no auditor waits for the registry to change, and
  every call until then is refused. The on-chain receipt didn't name the validator's seat; now it names the Panels,
  the panel, the slot and the validator's key, so one seat's receipt can't be posted for another.
- The zkTLS prover is a stub; the `simulated` proof type stands in for it.
- The relay does not speak the v3 messages. `RaceV3` cannot open constitution changes or escalated fixes.
- The rules decided after the judge measurement (seats by rank, the test-backed dispute, the solver's deposit, the
  appeal) are in the specification and the simulation, not yet in the contracts. Until they are, a network whose
  validators all run one family stalls under the family cap.

## 7.6 Self-healing is argued, not yet timed

The claim of the work is that a wrong payment is found and reversed quickly by people paid to look. The simulation
counts how many are reversed. Nothing yet measures how long it takes on a running chain, from the wrong verdict to the
reversal. A testnet shows the machinery; its tokens are worth nothing, so it does not show the incentive.

## 7.7 The simulation's inputs

Several inputs are assumed (task group 9): the confirmatory run on fresh seeds, the label of each input as measured,
assumed or chosen, and the sweep of each assumed one are not done. A criterion that flips inside a plausible range is
a result the paper must report.

## 7.8 It is not new to pay on an AI verdict

Others pay bounties on model verdicts already ([`related-work.md`](related-work.md)). What this work adds is the
adversarial design, the record of what broke in simulation, and the accuracy measurement above. Recheck before
submission.
