# Design

## Context

- **Delivery today** (`Market.deliver`): the simulation draws whether the gate catches a defect (`checks_catch_bps`, a property of the test suite), and the contribution then goes to beta. After that:
  - one reviewer finds a defect with `review_detect_bps`;
  - hunters find one at a rate that grows with pay;
  - panels vote with `vote_error_bps`.
- **AI review** (`challenges.ai_review`): two independent draws at `ai_review_accuracy_bps`, used only inside challenges.
- **Validators** have stakes (`ValidatorSet`), are drawn by stake with a seed, and are paid from the validators' share by units of work.

What's missing: who runs the checks, an AI judgement at delivery, and anyone scoring the AI.

## Goals / Non-Goals

**Goals:**
- Model checking with actors who can cheat, and price their cheating.
- Keep every market v4 criterion.
- Define what an oracle has to report (for #44).

**Non-Goals:**
- Real model calls, which need a budget.
- TEEs, zkTLS and chains (#44).
- Changing the legacy pool's gate.

## Decisions

### D1. Re-runs
- **Who runs them:** `rerun_validators` = 3, drawn like reviewers (stake-weighted, seeded, excluding the parties), with quorum `rerun_quorum` = 2. Each posts the review bond.
- **What they run:** the checks from one reproducible build. An honest validator's result is the truth, except on a flaky test (`replay_inconclusive_bps`, 5 %), where it is a coin toss.
- **Dissent:** a dissenting or unrevealed result loses `rerun_dissent_penalty_bps` = 2,000 of the bond. That's small, because honest validators sometimes hit flaky tests.
- **No quorum:** fresh validators re-run once; a second failure to reach a quorum counts as a failed check.
- **Run cost:** `rerun_cost` = 0.2 credits of effort per re-run. It isn't a ledger flow; it's what a lazy validator saves.
- *Alternative:* a single attested runner (a TEE). Kept for #44; it replaces k with 1 but means trusting the hardware maker.

### D2. Planted cases
- **How many:** `planted_share_bps` = 1,000, so 10 % of check and jury jobs are planted.
- **What they are:** made from a pool built from past deliveries, half with a known defect that the hidden tests catch, half known-good. They're indistinguishable from real deliveries.
- **A wrong answer** costs `planted_penalty_bps` = 5,000 of the bond and is scored. The case is revealed on the ledger once settled.
- **Who pays:** planted cases move no bounty money. Their work units are paid from the validators' share like any other.

### D3. The jury
- **Who sits:** `jury_size` = 3, drawn with a seed from the top `jury_pool` = 10 by score, at most one per operator and per declared family.
- **Bonds and thresholds:** `evaluator_bond` = 10 credits; accept with `jury_accept` = 2; fail only if unanimous. Otherwise the decision escalates to a validator panel of the tier's size (`validators_for`), with today's panel rules.
- **Evidence:** a verdict without evidence is discarded. In the simulation, a herding evaluator that cites none is discarded `herd_no_evidence_bps` of the time.
- **Cost:** `evaluator_cost` = 0.3 credits of effort per verdict, standing for the model call.

### D4. Scoring
- **The rule:** Brier, (p − y)², over an evaluator's last `score_window` = 50 scored verdicts. Lower is better, and the published top ranks by it.
- **The truth:**
  - a planted case's answer, at once;
  - a real delivery's fate once its contribution is accepted (y = good) or slashed or clawed back (y = bad);
  - appeal results.
- **Qualifying:** shadow mode lasts until `shadow_verdicts` = 20 scored verdicts with Brier ≤ `qualify_brier` = 0.15. In shadow, an evaluator judges as a 4th seat that never counts.
- **Penalties:** a bond loss applies only to wrong planted answers given with p ≥ 0.8 (confidently wrong). On real deliveries, bad scores cost seats (and pay), not bond.

### D5. The error model (simulation)
- **The shape:** a Gaussian copula. For each case, evaluator e of family f errs if Φ(z) < 1 − a_f, where z = √ρx·g_case + √(ρw − ρx)·g_f + √(1 − ρw)·g_e.
- **Defaults:**
  - 4 families, with accuracies 0.85, 0.85, 0.80 and 0.75;
  - correlation within a family ρw = 0.5, across families ρx = 0.2;
  - 2 evaluators per family and operator, 12 evaluators in all.
- **Reported probability:** an honest evaluator reports its family's accuracy as p, on the side it chose.
- **What the jury judges:** whether a delivery that passed the re-runs is defective. Defects the tests catch never reach it; the jury is a new layer before beta, so detection can only grow when it works.

### D6. Attackers
- **Lazy validator:** reports "pass" without running, which saves `rerun_cost`. Most real deliveries pass, so only planted defects catch it.
- **Herding evaluator:** always accepts with p = 0.9 and saves the model call. Under agreement scoring it would earn; under Brier it loses on planted defects and slashed fixes. The report runs both rules on the same seeds.
- **Copy operator:**
  - registers 4 evaluators of one model under 4 operator names, all declaring different families;
  - their errors are perfectly correlated;
  - it partners with a solver that delivers defective fixes, and accepts them whenever it holds 2 seats.

  The cohort's return is compared with the same accounts behaving honestly.
- **Crafting solver:** its defective fixes fool family A with probability 0.9 and the others with 0.3. It's measured against the same solver delivering honestly.
- **Bug planter:** a solver plants a defect in an accepted fix, and a partner challenges it. The cohort's return is compared with no planting.

### D7. Criteria and the run
- **Seeds:** verdicts on 100 seeds, sweeps on 20.
- **Detection floor:** the share of defective deliveries caught before beta, against fixed odds (the gate alone) on the same seeds.
- **Sweeps:**
  - ρw: 0, 0.5, 0.8;
  - planted share: 0, 5 %, 10 %, 20 %;
  - jury size: 1, 3, 5;
  - accept threshold: majority, unanimous.

## Risks / Trade-offs

- **Honest fixes rejected unanimously:** the chance is (1 − a)³ before correlation, more with it. It costs honest solvers their bond. With correlation 0.5 it may matter: the market v4 criterion "honest solvers earn" will show it, and the escalation rule (anything but unanimity goes to people) limits it.
- **Undeclared copies:** if the copy operator still gains, the next lever is detecting abnormal agreement on planted cases (a statistical test), or identity checks.
- **Cost:** planted cases cost validators' time and the validators' share. The planted-share sweep shows what each share buys.
- **The model is the assumption:** real accuracies and correlations come only from the real-data measurement (#15, needs a budget). Until then the sweeps bound the conclusions.

## Changes made while building it (task 4.2)

Each was found by the 20- and 40-seed probes, and each is in the defaults the acceptance run uses.

1. **Planted re-runs mostly fail, and a wrong planted answer forfeits the whole bond.** `planted_fail_bps` = 8,000 and `planted_penalty_bps` = 10,000, against D2's half and half and 50 %.
   - A lazy "pass" is right on a passing planted case, so only failing ones catch it. At a 5 % encounter rate and a 2.5-credit loss, laziness still paid (+1.8 ± 1.4).
   - Neither costs an honest validator anything: its planted answers are always right.
2. **Confidence and qualifying thresholds fit calibrated evaluators.** `confident_bps` = 9,000, not 0.8; `qualify_brier_bps` = 2,000, not 0.15.
   - A calibrated evaluator with accuracy a reports p = a, so it's never confidently wrong at 0.9.
   - Its expected Brier score is a(1 − a): 0.13 at 0.85 and 0.19 at 0.75. A 0.15 bar would shut out every family below 0.83.
3. **Five families and five operators,** each operator running three families (15 evaluators), so a jury of 5 (the size sweep) can be seated.
4. **The founding evaluators' exam is paid by the system.** It's the historical set of the real-data measurement; evaluators who join later qualify in shadow seats at their own cost. Charging 20 exam verdicts to each founding evaluator (6 credits) against about 12 paid verdicts in 8 weeks made honest evaluators lose.
5. **A rejection at delivery is a fate.** A delivery rejected by the jury or the panel is resolved as bad at once, and its verdicts are scored and paid.
   - Before, only accepted deliveries were ever scored, so a correct rejection earned nothing: a bias toward accepting.
   - **The cost:** for a unanimous rejection, the "truth" is the decision itself. An appeal of jury rejections is the follow-up that would make it true truth.
6. **Validators get 50 % of the market fee and infrastructure 10 %** (from 40 % and 20 %): validators now run the checks on their own machines. With the old split, honest evaluators broke even (−0.15 ± 0.14).
7. **Variant runs are kept apart from the base runs** in the summary. Before, the matching-off, discount-off and weak-detection variants were averaged into the market's reported means.
8. **The agreement-scoring comparison has no ground truth at all:** no planted cases, an exam at the real base rate (90 % good), and no truth-based penalties. That's what an agreement-only system looks like, and it's where herding pays.
9. **Attackers who deliver junk bid as honest solvers do,** to win jobs. Pricing from their own 100 % defect rate, they never won any.

## Second round of changes (owner's questions, 2026-10-24)

Each came from a question the owner asked, and each was measured on 100 seeds unless noted.

10. **Validators re-run only the public checks.** A re-runner necessarily sees what it runs, so **the hidden tests run on the system's own runner** and are retired after any failed attempt. Blind re-runs in an enclave are an option for #44.
11. **No bidder checks its own bounty:** every bidder on a bounty, and linked accounts, are excluded from its re-runs and juries.
12. **A solver can appeal failed re-runs** for a fee. Fresh validators re-run them; if they pass, the first re-runners who reported a failure lose the dissent share from their stakes. This answers two colluding re-runners.
13. **Jury evidence stays sealed until the bounty settles,** so the next solver doesn't learn how to fool the judges.
14. **Failed attempts are published, and a fresh round opens** instead of the queue (the owner's proposal).
    - It ends the advantage of seeing an attempt, and stale runner-up prices.
    - Against the queue rule, funders pay about 7.5 less per paid bounty and mean prices are about 5 lower.
    - Alone, it brought the ring of 4 back (+53 ± 21). **A reopened round's reserve is capped at the failed attempt's price,** which closed it (−1 ± 25).
15. **A "not solved" challenge:** a case of the reported issue that still fails with a bounty's fix. Before it, an incomplete fix that broke nothing couldn't be challenged at all.
    - An upheld challenge slashes the fix as a wrong result, adds its case to the bounty's public definition, and reopens the bounty.
    - Broader amendments to tests or scope between rounds are proof-of-fix#46.
16. **The simulation's partial fixes:** an honest solver's fix solves only the public case 5 % of the time. The hidden tests catch it 60 % of the time, then the jury.
    - Solvers price at the checking layer's published detection rate (0.9).
    - With partial fixes, a ring of 4 gains again (about +60). Without them it's −44 ± 23. Rings sit on the edge of the criterion under modelling choices unrelated to them, so the lever is ring detection and identity, not price (to be ticketed).
17. **AI consensus decides deliveries, with no person** (the owner's decision):
    - all three jurors to accept;
    - a split goes to a second AI jury of 7 (one per operator, at most 2 per family), which accepts with 5;
    - 5 of 7 was measured against 6 of 7: good fixes wrongly failed 20 % against 28 %.

    The cost depends on model accuracy (10 seeds):

    | | Bad fixes caught | Good fixes failed | Honest solvers |
    |---|---|---|---|
    | Consensus at 0.75–0.85 accuracy | 100 % | 20 % | about break-even |
    | Consensus at about 0.9 | 100 % | 11 % | +21 |
    | Majority (2 of 3), for comparison | 91 % | 5 % | +30 |

    **Condition for going live:** the real-data measurement shows each model at 0.9 accuracy or better on our kind of PRs.
18. **A split rejection keeps the bond** (the owner: "the value lost is time or tokens"). Only clear failures forfeit it: no delivery, failing tests, or a unanimous first jury. A split rejected by the second jury returns the bond and keeps the fee. Under consensus this moved honest solvers from −67 to about −10 (10 seeds).
19. **Rejected deliveries aren't scored.** Scoring them against the rejection (change 5) was agreement scoring in disguise: under consensus it spiralled, and evaluators who were right about good fixes were scored as wrong until none qualified. Their verdicts count as work; truth scoring comes from planted cases (half good, half bad) and accepted fixes' fates.
20. **Confidently wrong means p ≥ 0.99** (from 0.9). A calibrated evaluator of 0.95 accuracy reporting 0.95 was losing its bond on its honest mistakes, so better models fared worse. Brier scoring already punishes overconfidence.
21. **Oracle fees, paid by the bounty** (the owner, 2026-10-25: "these are AI oracles"; "oracle/MCP fees need to be covered by the bounty"):
    - **What's paid:** every check run on a delivery, from its bounty, whatever the outcome:
      - `run_fee` (0.3) to each re-run that matches the quorum, and to the system's runner for the hidden tests;
      - `verdict_fee` (0.5) to each counted verdict on either jury.

      Correctness is enforced by seats (Brier ranking), bonds (planted cases) and the quorum, not by withholding pay.
    - **The oracle reserve:** a bounty's target must exceed one full attempt's checks: (3 re-runs + the hidden runner) × 0.3 + (3 + 7) × 0.5 = 6.2. Its price cap is computed on what it holds less the reserve. Later attempts are paid from what's left, which includes forfeited bonds.
    - **Planted cases:** paid the same fees from insurance.
    - **The validators' share:** pays reviews and challenge verdicts only again. Change 6's split (validators 50 %, infrastructure 10 %) is reverted to 40 % and 20 %: its reason, validators running the checks unpaid, is gone.
    - **Pledges** may now pay oracle fees for checks on their bounty's deliveries, as well as the price, the market fee and refunds. The market criterion "pledges pay only for released fixes" is amended to allow it.
    - **Why it changes the model:** checking becomes a per-bounty cost the funders see in the price, not a share of the fee on successful fixes. Junk attempts now cost the bounty fees as well as delaying it; their forfeited bonds cover that.
22. **CI is an oracle too: attested runners** (the owner, 2026-10-25: "judge and CI are all AI/MCP oracles").
    - **Who runs the checks:** a delivery's public and hidden tests run on `ci_runners` = 2 attested runners, MCP test-runner services in TEEs. Each is registered by an operator with a bond (`runner_bond` = 20), and the two are drawn from different operators and hardware vendors.
    - **Agreement:** results must agree. A split is run again by fresh runners, and whoever disagreed with their result loses the dissent share of the small review bond, since it's often a flaky test.
    - **Lying:** a wrong answer on a planted case is a definite lie and costs a share of the runner's own bond.
    - **Hidden tests** run inside the enclaves, so the system's own runner and its fee go away. The oracle reserve becomes 2 runs + 10 verdicts = 5.6.
    - **Validators** leave the delivery path (they keep reviews and challenges). Re-runs by validators stay as the simulation's comparison (`ci_mode = "validators"`).
    - **Precedents** (#44): DeMCP (MCP servers in TEEs on Phala) and a draft "verifiable MCP" extension whose tool results carry an attestation. **The new trust assumption is the hardware vendors:** two different vendors per delivery, plus planted cases, bound it. The simulation draws a 0.5 % chance per run of a compromised or faulty enclave (swept 0 / 0.5 / 5 %).
    - **First probe (10 seeds):**
      - a forging runner loses −7.6, and a runner bidding through a second identity loses −23;
      - honest runners broke even only once a dissent cost the small bond, not a share of their own. Before that, flaky tests made them lose −2.
23. **CI inconclusive keeps the bond.** If even fresh runners can't agree, the delivery isn't accepted but the bond returns, as for a split jury rejection: flaky tests are the project's problem, not the solver's. A CI failure forfeits the bond only when the runners agree the tests fail.
24. **CI runs draw from their own random stream** in the simulation. Before, attested CI (2 runs) and validator CI (3) shifted every later jury's random errors, and that made attested CI look 9–12 worse for honest solvers. With separate streams the difference is −2.3 ± 5.2 (60 seeds), not significant.
25. **The hidden bidder (sock) is judged like bluffing and rings: it mustn't gain significantly.** It holds no edge over its honest twin, since it can't learn anything the other bidders can't, and the quorum and appeals catch its lies. So "doesn't gain" is the right test, not "loses".
26. **The owner's direction on quality** (2026-10-25):
    - **The accuracy penalty must come down over time, by paying for quality.** AI oracles must point to reputable models, and better models should earn more.
    - **Honest solvers with good architecture and coding skills should win the job.** The market already favours low cost and a clean record (pricing from the record, trust, bond discounts). What decides whether skill wins is the false-rejection rate, so the two directions are one goal.
    - **Proposed follow-up (to ticket):**
      - a published list of reputable models that evaluators must declare from, kept by measured accuracy;
      - verdict fees tiered by an evaluator's measured accuracy (its Brier score), so running a better model pays;
      - the real-data measurement sets both.

      At about 0.9 accuracy per model (the go-live condition) the simulation gives honest solvers +22 and 5 % of good fixes rejected.
