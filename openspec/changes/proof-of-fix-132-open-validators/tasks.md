# Tasks

Order (design, Migration Plan):
- groups 1–2 can start now; group 6 (#141's re-run) follows group 1, group 7 (its round 2) follows group 6, group 8 (round 3) follows group 7, and all three come before group 2's ADR;
- group 3 starts after #85's bonds and challenges (5.8), seals and receipts on-chain (5.5/5.6, #122) and attestation (#94);
- groups 4–5 follow group 3.

## 1. Simulation: open validators (`pof/sim/oraclenet.py`): #134; task 1.9 is #135

- [x] 1.1 Model the registry: registration with a bond, candidates, shadow judging, activation by the qualification thresholds, the reveal-rate floor, leaving with the unbonding delay, and the genesis validator. Verify with unit tests, each rule alone: a candidate qualifies at exactly `QUALIFY_VERDICTS` with the thresholds met, a leaver is still slashable during the delay, and a second genesis validator is refused.
- [x] 1.2 Model the panels:
  - k from bond-tiered eligibility, the k table's bounty limits and `K_MAX`;
  - sampling under the caps, with k stepping down by 2;
  - the seed from a later block;
  - replacement of silent judges;
  - `CHALLENGE_WINDOW[k]` and `CHALLENGE_K[k]`;
  - the constitution tier at exactly `K_MAX`.

  Verify with tests for every scenario in `specs/judge-panels`: one, two, six and forty validators; a bounty above the limit waits; a silent judge doesn't lower k; a challenge with too few validators freezes the window; an ADR on 4 validators waits.
- [x] 1.3 Model the actors: the sybil (many validators, one party), the colluding lone validator, the seed grinder, the silent judge, the fee farmer, and the constitution coalition. Verify with tests in which each acts as configured, alone, and its honest twin is the same actor behaving honestly.
- [x] 1.4 Model market pricing (design D9): validators posting cost tables, the median with `PRICE_STEP_MAX` and `MEDIAN_MIN_POSTERS`, the queue-driven service fee with `FEE_STEP`, `WAIT_HIGH`, `IDLE_HIGH`, the floor and the ceiling, and validators that join or leave by their expected net. Add the cartel faking a shortage, the spammer faking demand and validators posting inflated costs. Verify with tests for every `check-pricing` scenario, each attacker alone, and a test that the fee settles from the ceiling toward the validators' cost on a fixed seed.
- [x] 1.5 Model proof levels (design D10): validators at levels A, B and C, a panel's level as its majority's weakest, the largest bounty and window per (k, level), hidden tests only for all-TEE panels, the level C test liar and answer shopper, and the level B chip breaker. Verify with tests for every proof-level scenario in `validator-admission`, `judge-panels` and `incentive-simulation`.
- [x] 1.6 Model random audits (design D13) at `AUDIT_RATE`, with and without volunteer challengers. Verify with tests for the audit scenarios in `judge-panels` and the watcher's dilemma.
- [x] 1.7 Model per-family scores (design D14): agreement with final outcomes over `SCORE_WINDOW`, `SCORE_MIN`, the neutral start and the fee factor, plus weighted votes as an alternative, validators all moving to the top family, and herders. Verify with tests for every `judge-scores` scenario and each new actor alone.
- [x] 1.8 Add the scenarios "The k table compared", "The window's length", "Growth from one validator", "The fee finds the validators' cost", "The watcher's dilemma", "One vote, pay by score, weighted votes", "Everyone moves to the top model", "Herding", and the pricing and proof-level attacks, and the acceptance criteria for open validators, as `python3 -m pof.sim market validators --seeds 40` (or the closest existing entry point). Write `reports/open-validators-v1.md` with every table the spec asks for. Verify with a test that the command's numbers are reproducible on fixed seeds, and that the report names each criterion as met or not. Run the check.

- [x] 1.9 zkTLS spike: with one open-source zkTLS implementation and at least two independent notaries, prove one small model call each to Anthropic, OpenAI and Gemini, and record the time, the proof's size, the TLS version used and any limit on the answer's size in `reports/zktls-spike-v1.md`. It makes real, PAID model calls (a few cents) and contacts outside notaries, so it runs only with the owner's approval. Verify with the report and a test that checks one recorded proof offline.

## 2. Parameters, decided: #137

- [x] 2.1 From the reports (`reports/open-validators-v3.md` and its addendum `reports/open-validators-v3.1.md`, with v2 and v1 for the rules round 2 and #141 replaced), propose in `docs/adr/0004-open-validators.md`:
  - the k table, `BOND_FLOOR`, `CHALLENGE_WINDOW[k, level]`, `K1_PENDING_MAX`, the caps, `TEE_CAP_FROM_K` and the accepted TEE types (D6);
  - the qualification thresholds, the slashes (D16) with `SILENCE_SLASH_BPS` and `SEALED_NO_REVEAL_SLASH_BPS` from task 8.2's sweep, `AUDIT_RATE`, `K1_AUDITS`, `CONSTITUTION_MIN_ELIGIBLE`, `REMOVAL_MIN_ELIGIBLE` and `ADR_DEPOSIT`;
  - the pricing bounds and `IDLE_HIGH`;
  - the published acceptance thresholds (D17, round 3), `GAIN_TOLERANCE` among them, with the named trust points (answer shopping, the accomplice's other fixes, one TEE type's majority, a silence bribe above the slash);
  - the first zkTLS notaries;
  - for each switch of #141's three rounds, the rule or alternative the re-runs support.

  Name the evidence and any criterion that fails. The owner decides; until then the design's starting values stand. Verify with `openspec validate proof-of-fix-132-open-validators --strict` and a review of the ADR's numbers against the reports.

## 3. Contracts (after #85 5.8, 5.5/5.6 (#122) and #94): #138

- [ ] 3.1 `Validators`:
  - registration, signed by the new key: bond ≥ `BOND_FLOOR`, image on the allowed list, accepted attestation type, host, TEE type, family and operator;
  - bond tiers at every level's k-table limits, their counters, and the epoch counter;
  - candidate/active/leaving state, the reveal-rate floor (silence counts as a miss, and costs a counted judge `SILENCE_SLASH`), and qualification counters for scored shadow verdicts;
  - a model family fixed by the registration;
  - unbonding that waits for the delay, every verdict's finality and every challenge naming the validator;
  - the slashing hooks from 5.8 with D16's amounts;
  - at most `GENESIS_MAX` genesis validators at deployment, at level A or B.

  No owner, admin or setter. Verify with Foundry tests for every `validator-admission` scenario, a fuzz test that the tier counters always equal a full recount, and a test that no function changes a parameter.
- [ ] 3.2 `Panels`:
  - **the draw:** k from the counters; rejection sampling under the caps (the TEE cap from k = 3 while at least `TEE_CAP_K3_TYPES` TEE types are accepted, from k = 5 otherwise) with the fixed `DRAW_TRIES`, and the step-down; the seed from `blockhash(sealBlock + SEED_DELAY)`, re-targeting after 256 blocks; the draw as a recomputable view; a void draw when the panel's level is too weak;
  - **judging:** replacement of silent judges; shadow draws, on drawn and on waiting submissions, scored against outcomes no lone validator set (once, by the sealed majority, on a held k = 1 verdict);
  - **audits:** at `AUDIT_RATE`, plus two of every k = 1 verdict (`K1_AUDITS`) and one of every split level C pass;
  - **finality:** the hold on k = 1 verdicts and `K1_PENDING_MAX`; challenge panels larger than the original, and the frozen window;
  - **scores:** per-family balanced scores from counted final outcomes, the `SCORE_MIN` eligibility rule, and recovery on fresh blocks of shadow verdicts;
  - **qualification counters** at finality;
  - **the constitution tier:** `K_MAX` from at least `CONSTITUTION_MIN_ELIGIBLE` eligible, or `REMOVAL_MIN_ELIGIBLE` for an ADR that only removes, with expiry and `ADR_DEPOSIT`.

  Verify with Foundry tests for every `judge-panels` scenario, a test that the view's panel matches the recorded one, and a fuzz test that k is always odd, at most `K_MAX`, and never changes after the draw.
- [ ] 3.3 `FeesV3`: v2's fee formula with D9's pricing and D14's normalised score factor on the service fee:
  - posted tables with every unit, from active validators;
  - the median, the lower one for an even count, per `PRICE_PERIOD`, with its step, minimum and 2× cap;
  - the queue-driven service fee starting at `FEE_CEILING`, counting every wait once, within its floor and ceiling;
  - prices fixed per attempt, and no setter.

  Verify with Foundry tests for every `check-pricing` scenario and a fuzz test that no sequence of posts moves a price by more than `PRICE_STEP_MAX` per period.
- [ ] 3.4 Proof levels and removal (D10, D11):
  - the accepted proof types, notaries and minimum firmware levels on the constitution's list, each attestation scheme its own TEE type (D6);
  - each validator's level at registration, and the panel's level;
  - limits and windows per (k, level);
  - all-TEE panels for hidden tests and private repositories;
  - removal after `REMOVAL_WINDOW` against addition after the full window;
  - re-attestation after a raised minimum without re-qualifying.
  - level C off at launch: zkTLS verification in the code but not on the list until an adding ADR; receipts carrying their proof-type id, model and weights hash, image digest, seed, and prompt and answer hashes; no ADR can add verifier code (owner, 2026-11-03).

  Verify with Foundry tests for every proof-level, firmware and removal scenario.
- [ ] 3.5 `RaceV3`: the race reading k, the majority, the hold and finality from `Panels`, with instalments starting at finality; `Fees` paying each counted judge (the median of k reports; k = 1 is its own median) when the verdict is posted, and shadows from the pool, capped per draw. Verify with the v2 race tests ported to v3, plus a replay on fixed seeds matching the simulation of group 7 to the micro-credit. Keep every contract under EIP-170 and `RaceV3`'s initcode under EIP-3860, and record the sizes in `reports/contract-v3.md`.

## 4. Node, kit and docs: #139

- [ ] 4.1 The oracle node:
  - `register` and `leave`;
  - acting when drawn as a judge, an auditor or a shadow, on drawn and on waiting submissions;
  - posting the receipt on-chain;
  - `challenge`, which re-runs a check and files a challenge with evidence;
  - posting its table each period: its own shared-unit costs and every family's public list price;
  - for nodes without a TEE, a zkTLS prover for the model call (the implementation chosen in task 1.9).

  Verify with unit tests against a local chain, and a test that a shadow's seal is sent before the counted reveals.
- [ ] 4.2 The validator kit and `pofctl`: register instead of join, with the cloud-neutral core (#123): a cron or systemd watcher for home machines (level B or C) beside the AWS adapter. The watcher reacts to counted, shadow, audit and challenge draws. Update the runbook and `docs/participate.md` with "anyone can run a validator: bond, attest, qualify". Verify with the kit's tests, `tofu validate`, and the docs' commands run in the end-to-end test.
- [ ] 4.3 Update ADR 0002's successor notes and the README's diagrams for v3: the open registry, the k table and the k = 1 hold. Verify that the Mermaid blocks render with the pinned mermaid-cli.

## 5. On the devnet: #140

- [ ] 5.1 Deploy v3 beside v2 on a throwaway local devnet with one genesis validator at level A or B. Then register and qualify validators until k reaches 3, then 5. Show:
  - a k = 1 verdict held until three more validators are active, audited twice, then final after its window;
  - a bounty above k = 1's limit waiting, shadowed by candidates, then drawn when k = 3 is reached;
  - a challenged k = 1 verdict reversed by a fresh panel of 3.

  Verify with an end-to-end script in the style of `scripts/demo-e2e.sh`, leaving no containers behind.
- [ ] 5.2 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`, locally and in the CI image (Amazon Linux 2023, Python 3.9, as root).

## 6. Simulation re-run with #141's rules: #141

- [x] 6.1 Implement #141's rules in `pof/sim/openval/` as the new defaults of `Params`, each a named field so the ADR cites it, with #134's rules kept reachable:
  - **k = 1:** the hold (`CHALLENGE_K[1]` eligible for its challenge before its window runs); `K1_PENDING_MAX` 10; every k = 1 verdict audited; k = 1's windows 168 / 336 / 336 h;
  - **shadows:** scored only against outcomes no lone validator set, with the majority of at least 3 sealed verdicts for held, waiting and withdrawn submissions; `SHADOW_PER_WAITING` 3;
  - **challenges:** panels larger than the original, else waiting;
  - **slashes:** `FALSE_VERDICT_SLASH_BPS` 10,000; `SEALED_NO_REVEAL_SLASH` $1; no slash for silence;
  - **unbonding:** after the longest window plus 7 days, and after every open challenge;
  - **the constitution:** `CONSTITUTION_MIN_ELIGIBLE` 14, with expiry;
  - **pricing:** `FEE_START` at the ceiling; `IDLE_HIGH` 40 %; the floor-bond wait signal; every family's list price posted by every validator; `MEDIAN_LOW_EVEN`;
  - **audits and scores:** `AUDIT_RATE` 10 %; split level C passes audited; counted-only scores with recovery by shadows; the normalised factor; a family change as a new registration;
  - **levels and caps:** a level A or B genesis; `TEE_CAP_FROM_K` 5; bond tiers at every level's limits; a void draw for a panel too weak for its bounty.

  Verify with unit tests, each rule alone, for every new or changed scenario in `validator-admission`, `judge-panels`, `judge-scores` and `check-pricing`, and a test that `Params` with #134's values reproduces v1's numbers on a fixed seed.
- [x] 6.2 Add the alternatives as switches, each run beside its rule on the same seeds:
  - `K1_PENDING_MAX` 5 / 10 / 20, and `K1_BATCH_BOND`;
  - k = 1's window 7 / 14 / 30 days;
  - `SEALED_NO_REVEAL_SLASH` $0.50 / $1 / $5, and `SILENCE_SLASH`;
  - `CONSTITUTION_MIN_ELIGIBLE` 14 / 21 / 28;
  - `IDLE_HIGH` 30 / 40 / 50 %, `IDLE_WINDOW_DAYS` 7, the any-bond wait signal and `FEE_STEP_UP` 10 %;
  - `SCORE_BALANCED` and the neutral point at the median score;
  - `C_LIMIT_X` 0.5, and the borderline rate at 1 and 3 in 10;
  - five TEE types with the TEE cap from k = 3;
  - `SHADOW_PER_WAITING` 0;
  - `FALSE_VERDICT_SLASH_BPS` 2,000 as sensitivity.

  Verify with a test per switch that it changes only what it names.
- [x] 6.3 Add the scenarios of the `incentive-simulation` delta that #141 added: "An honest network grows under the hold", "The colluding genesis under the hold", "An honest validator's month", "A silent judge without a silence slash", "An early coalition", "A rule against its alternative" and "The TEE cap from k = 5". Re-run every v1 scenario under the new defaults. Verify with tests in which each new actor acts as configured, alone, beside its honest twin.
- [x] 6.4 Implement the acceptance check with D17's published thresholds (`SYBIL_SHARE` 12.5 %, `LONE_CATCH_SHARE` 90 %, `FEE_MARGIN` 25 %, `WAIT_CROWD_MAX` 15 %, growth to k ≥ 3 in every run, answer shopping counted at 1 in 10), judged as "How a criterion is judged" says. Verify with a test that each criterion's verdict follows from its numbers, and that a result that isn't significant fails.
- [x] 6.5 Run `python3 -m pof.sim market validators --seeds 40` and write `reports/open-validators-v2.md`:
  - every table v1 had, with v1's number beside each changed row;
  - the new scenarios, and each switch beside its rule;
  - the acceptance table under D17;
  - the parameters to drop or change, for the ADR (#137).

  Keep `reports/open-validators-v1.md` as it is. Verify with a test that the command's numbers are reproducible on fixed seeds and that the report names each criterion as met or not. Run the check.

## 7. Simulation re-run, round 2: #141

- [x] 7.1 Implement round 2's rules (design, "Revision 2026-11-03, round 2") in `pof/sim/openval/` as the new defaults of `Params`, each a named field so the ADR cites it, with round 1's rules kept reachable as one switch set, `V2R1` (and #134's as `V1`):
  - **the fee:** `WAIT_SIGNAL` "every": a submission counts once, in the period it starts waiting, and a stalled counted panel once;
  - **slashes:** `SEALED_NO_REVEAL_SLASH` $5 and `SILENCE_SLASH` $5, flat, for counted judges only;
  - **the constitution:** `CONSTITUTION_MIN_ELIGIBLE` 21 for ADRs that add or loosen and for escalated fixes, `REMOVAL_MIN_ELIGIBLE` 14 for ADRs that only remove or raise a firmware minimum, read from the ADR's operations, with expiry for both; `ADR_DEPOSIT` $15, forfeited to the sponsors' pool by a rejected ADR or escalated fix (never to the issue's funder or reporter) and refunded when it takes effect or expires;
  - **k = 1:** `K1_AUDITS` 2: two different auditors outside the panel, each drawn by the seed once eligible;
  - **scores:** `SCORE_BALANCED` on; recovery on fresh blocks of `SCORE_RECOVER_VERDICTS` (100) shadow verdicts at `SCORE_MIN` + `SCORE_RECOVER_MARGIN` (10 points), each block judged once;
  - **shadows:** on a k = 1 verdict held at its reveal, scored once by the sealed majority, never again at finality;
  - **the TEE cap:** `TEE_CAP_FROM_K` 3 while at least `TEE_CAP_K3_TYPES` (5) TEE types are accepted, otherwise 5.

  Verify with unit tests, each rule alone, for every new or changed scenario in `validator-admission`, `judge-panels`, `judge-scores` and `check-pricing`, and a test that `V2R1` reproduces `reports/open-validators-v2.md`'s numbers on a fixed seed.
- [x] 7.2 Replace the placeholder TEE types with D6's real ones: the launch world with Intel TDX, AMD SEV-SNP and AWS Nitro Enclaves (three types, the cap from k = 5), and a five-type world adding Intel SGX and IBM Secure Execution (the cap from k = 3). Spread newcomers over the types evenly, and skewed toward TDX and SEV-SNP, each spread a named `World` assumption. Verify with a test that the cap's start follows the number of accepted types, and moves when an ADR removes one.
- [x] 7.3 Add the switches, each run beside its round-2 rule on the same seeds:
  - `V2R1` as a whole;
  - the floor-bond and any-bond wait signals;
  - both flat slashes at $1, and silence unslashed;
  - one constitution threshold for every ADR, at 14 and at 28; `ADR_DEPOSIT` $0 and $25;
  - `K1_AUDITS` 1;
  - plain agreement for the score; round 1's sliding recovery, and a fresh block of 200 at + 5 points;
  - three and five TEE types, each spread evenly and skewed.

  Add the scenarios "A bribed silent judge and a bribed withholder", "A coalition of removals", "Recovery by chance" and "The TEE cap and the number of TEE types". Verify with a test per switch that it changes only what it names, and tests in which each new actor acts as configured, alone, beside its honest twin.
- [x] 7.4 Implement D17's round-2 criteria: "doesn't gain against its honest twin" (mean ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE`, $10) for every attacker criterion, with "loses" reported beside it; no adding ADR passed below 21 eligible and no removal below 14; `LONE_CATCH_SHARE` with two audits. Verify with a test that each verdict follows from its numbers: −$1 ± 7 passes; −$34 ± 47 and +$3 ± 2 fail.
- [x] 7.5 Run `python3 -m pof.sim market validators --seeds 40` and write `reports/open-validators-v3.md`:
  - every table v2 had, with round 1's number beside each changed row;
  - the pricing attackers (the spammer and the cartel above all) under the every-wait signal; the honest validator's month with every outage slashed $5; the silent judge and the withholder; both coalitions with the deposit, and the coalition of removals; the colluding genesis with two audits; the herders and recovery under the balanced score; the one-type majorities with the real TEE types;
  - the design's derived numbers (the coalition of 5 at about −$255 ± 152 from 21, about 96 % reversed, 0.2 to 0.3 chance recoveries a year) beside what the run measures;
  - each switch beside its rule.

  Keep `reports/open-validators-v1.md` and `reports/open-validators-v2.md` as they are. Verify with a test that the command's numbers are reproducible on fixed seeds and that the report names each criterion as met or not. Run the check.
- [x] 7.6 Acceptance check: the report's acceptance table under D17's round-2 criteria names every criterion as met or not, and for each one not met the parameter that decides it and the switch that would meet it, for the ADR (#137). The owner decides; until then the design's values stand. Verify with a test that the table's verdicts follow from the criteria's numbers.

## 8. Round 3: criteria and sweeps: #141

- [x] 8.1 Implement round 3's criteria (design, "Revision 2026-11-03, round 3") in the acceptance check, each a named field of `Params` with round 2's kept as a switch:
  - `GAIN_TEST` "not shown to gain" (mean − 2 SE ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE`) for every attacker criterion, round 2's "doesn't gain" the switch, "loses" reported beside both;
  - `LONE_CATCH_COUNT` "own": `LONE_CATCH_SHARE` on the verdicts the colluding lone validator gave itself; round 2's count ("all") reported beside, as the accomplice's trust point;
  - `WAIT_CROWD_MAX` 20 %.

  Keep round 2's acceptance table reproducible with `V2R2`. Verify with tests that each verdict follows from its numbers: +$2.7 ± 3.9, +$0.2 ± 0.7 and −$1 ± 7 pass; +$3 ± 2 and −$34 ± 47 fail; the switch restores round 2's verdicts.
- [x] 8.2 Add `SILENCE_SLASH_BPS` and `SEALED_NO_REVEAL_SLASH_BPS` (default 0): the slash is max(`SILENCE_SLASH`, x % of the bounty), and the same for a sealed vote not revealed; the flat amount for ADRs, which have no bounty. Sweep x of 0, 1, 2 and 5 % on 40 seeds: the silent judge and the withholder bribed 5 % and 10 % of the bounty beside their twins, and the honest validator's month on the market (1 outage in 200 draws, before and after the seal) with the fee and break-even. Verify with tests that the slash follows the bounty, that each switch changes only what it names, and that x = 0 gives round 2's numbers on a fixed seed.
- [x] 8.3 The deposit's honest cost: an honest author submitting good ADRs with the deposit to a grown network (at least 21 eligible), beside its twin with no deposit. Report the share rejected and the deposits forfeited per ADR, beside D7's hand estimate (2.6 %, about $0.39). Verify with a test in which the author acts as configured.
- [x] 8.4 Write `reports/open-validators-v3.1.md`, an addendum to v3:
  - the acceptance table under round 3's criteria beside v3's, re-judged from v3's numbers (the rules and seeds are round 2's, so nothing of v3 is re-run);
  - the silence-slash sweep and the deposit's honest cost;
  - what changes for the ADR (#137).

  Keep `reports/open-validators-v3.md` as it is. Verify with tests that the re-judged verdicts follow from v3's published numbers, that those numbers appear in v3's report, and that the report names each criterion as met or not. Run the check.

## Workflow follow-up
- After the owner's review of groups 1, 6, 7, 8 and 2, the parameters ADR (0004) is merged before group 3 starts.
- Archive this change once group 5 passes and v3 is the devnet's default.
