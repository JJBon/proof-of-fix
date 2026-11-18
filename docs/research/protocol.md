# The research protocol

How proof-of-fix turns a question into evidence the paper can rest on (#158, #229). Every experiment follows the same loop. A result that skipped a step is labelled **exploratory**, and only **confirmatory** results go in the paper's results section.

## The loop

1. **Hypothesis.** One falsifiable statement, entered in [`hypotheses.md`](hypotheses.md) with an ID (H1, H2, ...).
2. **Prediction.** What the data will show if the hypothesis holds, as a measure and a threshold, for example "false passes at most 10 %, the upper bound of a 95 % interval".
3. **Pre-registration,** committed and hashed **before any run**: `reports/<experiment>.prereg.md` names
   - the hypotheses it tests;
   - the data and how it's frozen (manifest and hashes);
   - the measures, the thresholds and the statistical test;
   - the sample size and why it's enough (a power estimate);
   - what counts as a failed run, and what's excluded;
   - the cost.

   A paid run starts only after the owner approves the pre-registration's hash.
4. **Run.** It's reproducible from the commit, with seeds, pinned images and stored raw outputs.
5. **Report.** `reports/<experiment>.md` gives:
   - every pre-registered measure, nulls and failures included;
   - any deviation from the pre-registration, marked;
   - a **threats to validity** section (internal, external, construct);
   - each hypothesis's new status.
6. **Decision.** A spec or design change that rests on the result cites the hypothesis's ID.
7. **Next hypothesis.** Anything learnt after looking at the data is a new, exploratory hypothesis, to be confirmed by a new pre-registered run, never by re-reading the same data.

## Rules

- **Criteria are frozen before the confirmatory run.** If a criterion changes after its results were seen (rounds 2 and 3 of #141 did this, with reasons), the run that motivated the change is exploratory. The criterion is then confirmed on fresh data: new seeds for the simulation, or a held-out set for the judges.
- **Many criteria at once:** a report that judges several criteria in one run says how many it judged and corrects for chance (Holm–Bonferroni), or reports the family-wise error.
- **Simulation inputs are labelled.** Each one is *measured* (with its source), *assumed* (with a sensitivity analysis showing which conclusions flip if it moves) or *chosen* (a design parameter).
- **Ground truth is stated.** A label says what it rests on (hidden tests, full developer tests, human review) and its known error rate. Hidden tests pass wrong patches, as Wang, Pradel and Liu (ICSE 2026) and UTBoost (ACL 2025) found, so a judge study that uses them says so.
- **Data rules:** rule 5 (aggregate only, no per-person data), licences checked, and nothing published from this repository.

## Statuses (in the register)

- **open:** stated, not yet tested;
- **pre-registered:** a hashed plan exists;
- **supported** or **refuted:** by a confirmatory run;
- **exploratory:** seen in data that wasn't pre-registered for it, so a confirmatory run is still owed;
- **retired:** no longer relevant, with the reason.
