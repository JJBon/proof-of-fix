# Tasks

Order (design, Migration Plan):
- groups 1–2 can start now; group 6 (#141's re-run) follows group 1, group 7 (its round 2) follows group 6, group 8 (round 3) follows group 7, and all three come before group 2's ADR;
- group 3 starts now (owner, 2026-11-13). v3 builds its own seals, reveals and receipts on-chain (in place of #85 5.5/5.6, #122) and its own bonds and provable faults (in place of #85 5.8). It takes attestation as a recorded hash that the drawn panel checks off-chain, with a simulated proof type on devnets (D18). v2 stays as deployed;
- groups 4–5 follow group 3.

The road to a test chain (owner, 2026-11-13):
1. this change's group 3: `Validators`, `FeesV3`, `Panels`, proof levels, `RaceV3`;
2. #186's contracts (`proof-of-fix-186-cycle-pools`, its group 3): cycle pools, the index pool, the merit panel, the token and the payout fee, built on `RaceV3` and `Panels`. Its D8 freezes them before #160;
3. this change's groups 4–5 with #186's group 4: node, kit and the devnets, bounties and pools end to end;
4. the paid judge check (#160) on that frozen build;
5. then a test-chain deployment.

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

## 3. Contracts: #138 (absorbing #122 and #85 5.5, 5.6 and 5.8; D18)

- [x] 3.1 `Validators`:
  - registration, signed by the new key: bond ≥ `BOND_FLOOR`, image on the allowed list, accepted attestation type, host, TEE type, family and operator;
  - bond tiers at every level's k-table limits, their counters, and the epoch counter;
  - candidate/active/leaving state, the reveal-rate floor (silence counts as a miss, and costs a counted judge `SILENCE_SLASH`), and qualification counters for scored shadow verdicts;
  - a model family fixed by the registration;
  - unbonding that waits for the delay, every verdict's finality and every challenge naming the validator;
  - the bonds in `FEE_COIN` and the provable-fault slashes with D16's amounts (in place of #85 5.8, D18): equivocation checked by the contract, a sealed vote not revealed, silence, failed availability and upheld receipt challenges, with the challenger's share and the pool's;
  - at most `GENESIS_MAX` genesis validators at deployment, at level A or B.

  No owner, admin or setter. Verify with Foundry tests for every `validator-admission` scenario, a fuzz test that the tier counters always equal a full recount, a test that no function changes a parameter, and an invariant that no slash exceeds a validator's bond and none follows a mere disagreement (#85 5.8's).
- [x] 3.2 `Panels`:
  - **the draw:** k from the counters; rejection sampling under the caps (the TEE cap from k = 3 while at least `TEE_CAP_K3_TYPES` TEE types are accepted, from k = 5 otherwise) with the fixed `DRAW_TRIES`, and the step-down; the seed from `blockhash(sealBlock + SEED_DELAY)`, re-targeting after 256 blocks; the draw as a recomputable view; a void draw when the panel's level is too weak; validators of an unpriced family (D19) skipped, as counted judges and as shadows;
  - **seals, reveals and receipts on-chain** (in place of #122 and #85 5.5/5.6, D18): each drawn judge posts its seal, then its reveal and its receipt's hash within their windows; the counted result comes from the on-chain reveals; early, mismatched and replayed reveals are refused, and a missed deadline counts as silence;
  - **judging:** replacement of silent judges; shadow draws, on drawn and on waiting submissions, scored against outcomes no lone validator set (once, by the sealed majority, on a held k = 1 verdict);
  - **audits:** at `AUDIT_RATE`, plus two of every k = 1 verdict (`K1_AUDITS`) and one of every split level C pass;
  - **finality:** the hold on k = 1 verdicts and `K1_PENDING_MAX`; challenge panels larger than the original, and the frozen window;
  - **scores:** per-family balanced scores from counted final outcomes, the `SCORE_MIN` eligibility rule, and recovery on fresh blocks of shadow verdicts;
  - **qualification counters** at finality;
  - **the constitution tier:** `K_MAX` from at least `CONSTITUTION_MIN_ELIGIBLE` eligible, or `REMOVAL_MIN_ELIGIBLE` for an ADR that only removes, with expiry and `ADR_DEPOSIT`.

  Verify with Foundry tests for every `judge-panels` scenario, a test that the view's panel matches the recorded one, a fuzz test that k is always odd, at most `K_MAX`, and never changes after the draw, tests for the early, mismatched and replayed reveal and the missed deadline, and the gas per seal, reveal and receipt in `reports/contract-v3.md`.
- [x] 3.3 `FeesV3`: v2's fee formula with D9's pricing and D14's normalised score factor on the service fee:
  - posted tables with every unit, from active validators;
  - the median, the lower one for an even count, per `PRICE_PERIOD`, with its step, minimum and 2× cap;
  - the queue-driven service fee starting at `FEE_CEILING`, counting every wait once, within its floor and ceiling;
  - prices fixed per attempt, and no setter;
  - open model families (D19): no list; a new family priced by tables from other families' validators, capped at `PRICE_CAP_X` × the most expensive priced family, and not drawn until priced.

  Verify with Foundry tests for every `check-pricing` scenario and a fuzz test that no sequence of posts moves a price by more than `PRICE_STEP_MAX` per period.
- [x] 3.4 Proof levels and removal (D10, D11):
  - the accepted proof types, notaries and minimum firmware levels on the constitution's list, each attestation scheme its own TEE type (D6);
  - each validator's level at registration, and the panel's level;
  - limits and windows per (k, level);
  - all-TEE panels for hidden tests and private repositories;
  - removal after `REMOVAL_WINDOW` against addition after the full window;
  - re-attestation after a raised minimum without re-qualifying.
  - level C off at launch: zkTLS verification in the code but not on the list until an adding ADR; receipts carrying their proof-type id, model and weights hash, image digest, seed, and prompt and answer hashes; no ADR can add verifier code (owner, 2026-11-03);
  - the `simulated` proof type (D18): a deployment record may list it only on a devnet chain id (31337, 7193), never on any other chain; there it counts as level A.

  Verify with Foundry tests for every proof-level, firmware and removal scenario, and a test that a deployment on any other chain id refuses the `simulated` type.
- [x] 3.5 `RaceV3`: the race reading k, the majority, the hold and finality from `Panels`, with instalments starting at finality; `Fees` paying each counted judge (the median of k reports; k = 1 is its own median) when the verdict is posted, and shadows from the pool, capped per draw. Verify with the v2 race tests ported to v3, plus a replay on fixed seeds matching the simulation of group 7 to the micro-credit. Keep every contract under EIP-170 and `RaceV3`'s initcode under EIP-3860, and record the sizes in `reports/contract-v3.md`.
  - `FeesV3.roll` split into bounded parts (or the posters it counts bounded) so one call fits a block on a busy chain: about 5.3M gas at 36 posters × 16 families today (#222).

## 4. Node, kit and docs: #139

- [ ] 4.1 The oracle node:
  - `register` and `leave`;
  - acting when drawn as a judge, an auditor or a shadow, on drawn and on waiting submissions;
  - posting the receipt on-chain;
  - seals, reveals and signatures through the `onchain` transport (`oracle/transport.py`, #122's), the default for v3; the hosted relay stays optional;
  - on devnets, the `simulated` proof type's quote from the dstack simulator (`ORACLE_KEYS=dstack` with `DSTACK_SIMULATOR_ENDPOINT`, D18);
  - `challenge`, which re-runs a check and files a challenge with evidence;
  - posting its table each period: its own shared-unit costs and every family's public list price;
  - for nodes without a TEE, a zkTLS prover for the model call (the implementation chosen in task 1.9).

  Verify with unit tests against a local chain, and a test that a shadow's seal is sent before the counted reveals.

  Status (#139): built and tested in `oracle/node_v3.py`, `oracle/v3.py` and the `onchain` transport, against a fake chain (`tests/test_oracle_v3.py`) and against the real contracts on anvil (`scripts/node-v3-e2e.sh`), except the last bullet. The zkTLS prover is an interface with the offline check of a proof (`oracle/zktls.py`); its driver for task 1.9's TLSNotary tools is a stub that was never run, since it needs the pinned Rust build, a notary that signs and a paid model call. Left unticked until that prover has run once. Also not done here: a challenge judge's seat on a real chain (it's tested against the fake chain only: a challenge panel needs more qualified validators than the local run grows), and the hosted exchange service doesn't take v3's messages.
- [ ] 4.2 The validator kit and `pofctl`: register instead of join, with the cloud-neutral core (#123): a cron or systemd watcher for home machines (level B or C) beside the AWS adapter. The watcher reacts to counted, shadow, audit and challenge draws. Update the runbook and `docs/participate.md` with "anyone can run a validator: bond, attest, qualify". Verify with the kit's tests, `tofu validate`, and the docs' commands run in the end-to-end test.
- [x] 4.3 Update ADR 0002's successor notes and the README's diagrams for v3: the open registry, the k table and the k = 1 hold. Verify that the Mermaid blocks render with the pinned mermaid-cli.

## 5. On the devnet: #140

- [ ] 5.0 The integration suite on a panel interface (D18): the scenarios read who is drawn and what quorum decides from one place, so v2 and v3 share them; `scripts/integration.sh --version 3` with `contracts/deployments/devnet-*-v3.json`. Scenario 6 becomes registration and qualification, scenario 4 the replacement of a silent judge, and the k = 1 hold, its audits and a waiting bounty are new scenarios. Verify that v2's run still passes locally and on AWS, unchanged.
  Status (#140, 2026-11-15), not ticked: partly done.
  - Done and run: the panel interface is `tests/integration/panel.py` (`PanelV2`, `PanelV3`: who is drawn, what decides, whether a silent seat is replaced). The v2 suite reads its draws through it, and its local run passes unchanged (`scripts/integration.sh`: scenarios 1–7 and 10). `scripts/integration.sh --version 3` deploys v3 beside v2 (`scripts/devnet.sh deploy-v3`, record `contracts/deployments/integration/devnet-v3.json`) and runs `tests/integration/suite_v3.py`: registration and qualification, the replacement of a silent judge, the k = 1 hold and its audits, a waiting bounty, and a challenge.
  - Not done: v2's scenarios 1–3, 5, 7 and 10 aren't shared with v3 (they go through pofctl, the bot and the relay, none of which speaks v3), and v3's validators run as node objects in one process, not as separate processes. v2's AWS run wasn't re-run (`tests/integration/aws.py` is untouched). See `reports/devnet-v3-local.md`.
- [x] 5.1 Deploy v3 beside v2 on a throwaway local devnet with one genesis validator at level A or B. Then register and qualify validators until k reaches 3, then 5. Show:
  - a k = 1 verdict held until three more validators are active, audited twice, then final after its window;
  - a bounty above k = 1's limit waiting, shadowed by candidates, then drawn when k = 3 is reached;
  - a challenged k = 1 verdict reversed by a fresh panel of 3.

  Verify with an end-to-end script in the style of `scripts/demo-e2e.sh`, leaving no containers behind.

  Status (#140, 2026-11-15): `scripts/devnet-v3-e2e.sh` shows all three, and `scripts/time-to-heal.sh` adds the chain time from a wrong pass to its reversal (`reports/devnet-v3-local.md`). Two things differ from the wording above:
  - the hold needs three validators **outside the verdict's auditors**. An auditor is drawn as soon as one is eligible, and sits out of the verdict's challenge (D13), so three more validators are enough only when the window starts before the audits are drawn; otherwise it takes five or more (a random or a replaced auditor sits out too). The run reports which happened, and both orders were seen;
  - the validators are real `NodeV3` objects in one process with the fake judge, not separate processes over a relay (the relay doesn't speak v3 messages).
- [ ] 5.2 v3 on the AWS devnet beside v2, with a deployment record for testing only (the seal, reveal and challenge windows in minutes, the `simulated` proof type), the seats host's six nodes registering as validators, and `scripts/integration.sh --target aws --version 3 --seats-elsewhere` passing. v2's AWS run keeps passing.
- [ ] 5.3 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`, locally and in the CI image (Amazon Linux 2023, Python 3.9, as root).

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

## 9. Confirmatory runs (docs/research/protocol.md, #229)

- [ ] 9.1 Freeze every acceptance criterion (D17, round 3's values) and pre-register a confirmatory run of group 8's scenarios on fresh seeds 41–80 (`reports/open-validators-confirm.prereg.md`, hashed before the run), with the number of criteria judged and a Holm–Bonferroni correction. Verify: the report gives each criterion's result on the new seeds, and H6 and H8 in `docs/research/hypotheses.md` move from exploratory to supported or refuted.
- [ ] 9.2 Label each simulation input as measured, assumed or chosen, and sweep each assumed one over a stated plausible range (H10). Verify: the report names any criterion whose outcome flips inside a range.
- [ ] 9.3 After #160: re-run 9.1 with the measured judge accuracy, borderline rate and family agreement in place of the assumed values (H7). Verify: a report comparing the two runs criterion by criterion.

## 10. After the judge measurement: seats, disputes, deposits and appeals (#236; D20–D23)

- [x] 10.0 The simulation on #160's verdicts: the honest network, disputes backed by a failing test, and the attackers (`pof/sim/openval/measured.py`, `contenders.py`; `reports/open-validators-measured-v1.md` and `-v2.md`, PR #237). Exploratory, seeds 1–40.
- [x] 10.1 In the simulation, on the measured verdicts and the market fee: seats by rank with `SEAT_MARGIN` and `CAP_MIN_FAMILIES` swept; the solver's deposit with `SOLVER_DEPOSIT_BPS` swept; the appeal, with its panel drawn from other families and, as the alternative, from the seated ones; a new family's start as a contender. New actors: a solver that appeals every rejection, and a disputer without evidence. Verify with a test per switch, and a report giving each rule beside its alternative on the same seeds (D17's "Each rule runs beside its alternatives").
  - Done (exploratory, seeds 1–40): `pof/sim/openval/seats.py` and `sizing.py`, `tests/test_openval_seats.py`, [`reports/open-validators-measured-v3.md`](../../../reports/open-validators-measured-v3.md). The fee is the market's; the market's entry and exit are off, except in the judged spammer's rows.
  - **The appeal panel's condition (D23) is not met:** a panel drawn from the families that didn't judge overturns four in five of the correct rejections appealed to it, and a solver of bad fixes gains by appealing (report, section 5). The question returns to the owner in 10.2.
- [ ] 10.2 The owner's decisions on D20–D28's values, recorded here and in a new parameters ADR that replaces ADR 0004 (owner, 2026-11-14), with the bonds and windows re-derived from 10.1's bad fixes per 100 paid. The direction is decided (design, "Decided 2026-11-14" and "Decided 2026-11-15"): one family may hold every seat, the deposit goes to the issue's bounty, and the seated families decide an appeal (the panel of 2026-11-14, with contenders, is dropped). Each part of D24–D28 is proposed until the owner accepts, changes or rejects it (task 11.2).
- [ ] 10.3 **Paid, last, and only with the owner's approval of a pre-registered plan:** measure the two assumed rates of D21 on labelled fixes: how often a contender's model writes a failing test for a bad fix it flagged, and how often a judge accepts a test that states the wrong requirement. Verify: a pre-registration hashed before the run, and a report that replaces the assumed range in 10.1 with the measured one.
- [ ] 10.4 Contracts: seats by rank and the conditional family cap in the draw (`Panels`, `PanelScores`); the dispute backed by a test (`Panels`; the appeal is task 11.4); the solver's deposit and its three destinations (`RaceV3`). Verify with Foundry tests for each spec scenario, the replay against the simulation, and the gas and size lines in `reports/contract-v3.md`.
- [ ] 10.5 The node: a contender's loop (shadow-judge, search the fixes its model failed, post a test with the stake), the test runner in the checker image (the appeal is task 11.5). Verify with unit tests against a local chain and one end-to-end dispute on the local devnet.
- [ ] 10.6 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`.

## 11. The appeal on evidence, sponsorship, known answers and the second draw (#236; D24–D28, revision 2026-11-15)

Every rule in this group is **proposed** except the owner's decision of 2026-11-15 (the seated families decide an appeal). No contract or node task starts before 11.2.

- [x] 11.1 In the simulation, on the measured verdicts, 40 seeds, both kinds of bad fix, each rule behind a named switch with a test: the appeal on evidence decided by the seated families, swept over the two assumed rates; a contender's sponsorship and what it does to seating; known-answer issues at several rates, with their cost; the second draw among few families; the deposit held during the appeal period. Attackers: a solver that appeals every rejection with a test it wrote, a contender that sponsors every rejection, a solver that tries an issue again while its deposit is held. Added the same day at the owner's request: rival solvers as disputers, a code-health measure across the deposit, the network with no deposit, and a shared pot split by standing fixes as a hypothesis (expected values only: `pof/sim/openval/potsplit.py`).
  - Done (exploratory, seeds 1–40): `pof/sim/openval/evidence.py`, `tests/test_openval_evidence.py`, [`reports/open-validators-measured-v4.md`](../../../reports/open-validators-measured-v4.md).
- [ ] 11.2 The owner accepts, changes or rejects each of D24–D28, part by part (design, "For the owner, after task 11.1"), and the accepted values go into the parameters ADR of task 10.2: `APPEAL_STAKE`, `SPONSOR_REWARD_BPS`, `KNOWN_RATE`, `KNOWN_MIN`, `KNOWN_WINDOW`, `SECOND_PANEL`. **The solver's deposit (D22) is on hold (owner, 2026-11-15):** whether there is one, and `SOLVER_DEPOSIT_BPS` (10.1 found 2,500 too low and 4,000 enough), wait for his ruling, with report v4's no-deposit results in hand.
- [ ] 11.3 **Paid, with task 10.3, and only with the owner's approval of a pre-registered plan:** measure the two rates D24 assumes, on labelled fixes: how often a judge that rejected a good fix passes it when shown a test that fails on the base code and passes with the fix, and how often a judge that rejected a bad fix passes it when shown such a test written by the fix's author. Verify: a pre-registration hashed before the run, and a report that replaces the swept range of 11.1.
- [ ] 11.4 Contracts, for the parts accepted in 11.2: the appeal with a test and a stake, its panel drawn from the seated families, and the second draw among few families (`Panels`); the stake's two destinations, the deposit held until the appeal period closes, and the sponsor's share of the bounty (`RaceV3`); known-answer verdicts and the score the seat rule reads (`PanelScores`). Verify with Foundry tests for each spec scenario, the replay against the simulation, and the gas and size lines in `reports/contract-v3.md`.
- [ ] 11.5 The node, for the parts accepted in 11.2: the checker image runs an appeal's test on the base code and on the fixed code, twice each, test files only; the appeal panel's prompt shows the test and its results; a solver's and a contender's appeal commands; a validator judges known-answer issues as it judges any other. Verify with unit tests against a local chain and one end-to-end appeal on the local devnet.
- [ ] 11.6 Where known answers come from, without a privileged author: a design note for #136 (keyless known-answer issues), since D26 needs it before any contract. Verify: the note names the source, who could tell a known-answer issue from a live one, and what the simulation's rate costs with it.
- [ ] 11.7 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`.

## 12. No deposit: the reputation cap, the judges' fee, the pot by impact (#236; D29, D30, PROPOSED)

The owner approved simulating three deposit-free mechanisms (2026-11-15). D29 and D30 are **proposed**; the pot by impact is not. No contract or node task starts before 12.2.

- [x] 12.1 In the simulation, on the measured verdicts, 40 seeds, both kinds of bad fix, Opus 5.5 and GPT-6.1 seated alone, 1, 3 and 10 active honest solvers, no deposit: the reputation cap, the pot by impact (in the network) and the judges' fee, each behind a named switch with a test, alone and in every combination. Attackers: the solver of bad fixes, free identities, the retrier on one and on fresh identities, the long con, the reputation sale, the farmer, the farmer filing its own issues, the inflater; and the honest newcomer's cost.
  - Done (exploratory, seeds 1–40): `pof/sim/openval/nodeposit.py`, `nodeposit_tables.py`, `tests/test_openval_nodeposit.py`, [`reports/open-validators-measured-v5.md`](../../../reports/open-validators-measured-v5.md). Post hoc rows are marked.
- [ ] 12.2 The owner accepts, changes or rejects D29 (`REP_BASE`, `REP_MULT`, `REP_ON_REVERSAL`, `REP_LOSS_X`) and D30 (`JUDGE_FEE` and how it is re-measured), and rules on D22 with report v5's one-solver gap in hand. The accepted values go into the parameters ADR of task 10.2.
- [ ] 12.3 Confirm the recommended rule on fresh seeds 41–80 with a pre-registration hashed before the run: R(minus 2×)+F, every attacker of 12.1, 1, 3 and 10 active honest solvers, find rates 10, 25 and 50 %. Verify: the report states, cell by cell, whether every attacker is at or below its twin, and the newcomer's cost.
- [ ] 12.4 Simulate what 12.1 left out before any contract: rivals' wrong tests (they now cost honest reputation), a deposit only while a repository has fewer than three active solvers, and the appeal (D24) beside D29 and D30. Verify: a report beside v5's rows on the same seeds.
- [ ] 12.5 Contracts, for the parts accepted in 12.2: identities with reputation, claims registered before judging against the cap, a reversal by test recorded against the identity (`RaceV3`); the flat judges' fee in place of per-check charges, with its period's value (`RaceV3`, `Panels`). Verify with Foundry tests for each scenario, the replay against the simulation, and the gas and size lines in `reports/contract-v3.md`.
- [ ] 12.6 The node and the kit: a solver's command shows its cap and open claims; the fee's measurement per period from the validators' posted costs. Verify with unit tests against a local chain and one end-to-end claim refused over the cap on the local devnet.
- [ ] 12.7 The pot by impact waits for #247: measure the impact signal's correlation with an outside judgment of impact and the cost of inflating it, then re-run report v5's pot section with the measured values. Verify: a report naming whether the inflater and the farmer stay at or below their twins.
- [ ] 12.8 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`.

## 13. A validator's capacity and the queue under spam (#253; D31, D32, PROPOSED)

The owner asked (#253) for a per-validator limit of checks an hour, so a validator can't be spammed. D31 and D32 are **proposed**. No contract or node task starts before 13.2.

- [x] 13.1 In the simulation, on the measured verdicts, 40 seeds, Opus 5.5 and GPT-6.1 seated alone: a validator's capacity (1, 3, 5, 10 an hour), a repository's cap, the queue's order (reputation or arrival), each behind a named switch with a test; a spammer of junk fixes from free identities at two rates, paying nothing (a testnet) or the judges' fee (D30), and one spamming from a reputable identity; 4, 7 and 15 validators. Measure honest fixes' waits and time to heal, validators' spend a day, checks spent on junk, and whether the backlog clears.
  - Done (exploratory, seeds 1–40): `pof/sim/openval/capacity.py`, `tests/test_openval_capacity.py`, [`reports/open-validators-measured-v6.md`](../../../reports/open-validators-measured-v6.md), simulation A. A capacity bounds spend; it doesn't keep honest fixes moving once spam exceeds the network's capacity; reputation first serves established solvers and starves newcomers.
- [ ] 13.2 The owner accepts, changes or rejects D31 (`MAX_CHECKS_PER_HOUR`, `REPO_CHECKS_PER_HOUR`) and D32 (`QUEUE_ORDER`), with report v6's numbers. The accepted values go into the parameters ADR of task 10.2.
- [ ] 13.3 Contracts, for the parts accepted in 13.2: per-validator check counts in a rolling hour read by the draw, k from every eligible validator, a waiting queue drawn again in its order (`Panels`). Verify with Foundry tests for each scenario, the replay against the simulation, and the gas and size lines in `reports/contract-v3.md`.
- [ ] 13.4 The node and the kit: a validator's capacity shown and its spend guard set from it (validator-kit/COSTS.md); the testnet faucet's rate beside it. Verify with unit tests against a local chain and one end-to-end spam run on the local devnet.
- [ ] 13.5 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`.
- [x] 13.6 Simulate a way through for a newcomer's first fix under spam (a reserved share of each hour for fixes without reputation, a per-identity rate behind the faucet's, or a charge in test ETH) beside report v6's rows on the same seeds, before 13.2 fixes a capacity below the spam a testnet may see.
  - Done for the lane and the rate (post hoc, seeds 1–40): `NEWCOMER_LANE`, `LANE_PER_ID_DAY` in `pof/sim/openval/capacity.py`, tests in `tests/test_openval_capacity.py`, report v6's section "Post hoc: the newcomer lane". No lane share passes; the rate refuses nothing against free identities; with identities that cost something (pools of 10), D29's cap lets newcomers through. The charge in test ETH is task 13.7.
- [ ] 13.7 Design how a testnet identity costs something (one identity per account at the faucet, or a charge in test ETH backed by the faucet's limit), estimate how many identities a day a spammer gets under it, and simulate the spammer at that rate beside report v6's pool rows (reputation first, D29's cap, a lane of 0 and 25 %), on fresh seeds (41–80) so the result is confirmatory. Verify: a report naming whether newcomers' fixes hold P.1's criterion at 7 and 15 validators with one repository.
- [ ] 13.8 Before the testnet's launch, set `REPO_CHECKS_PER_HOUR` off while there is one repository (report v6, post hoc: a cap of 7 there is a network-wide cap and fails even at 1 junk fix an hour); record the rule for turning it on in the parameters ADR of task 10.2.

## 14. Validators choose repositories (#252; D33, D34, PROPOSED)

The owner decided (#252) on enclaves only (levels A and B) and on allow and deny lists respected everywhere. The minimum and the stake cap (D34) are **proposed**. No contract or node task starts before 14.2.

- [x] 14.1 In the simulation, on the measured verdicts, 40 seeds: repositories, validators' allow and deny lists respected by every draw, a repository's minimum of eligible validators counted across TEE types, and a bounty cap scaled to the stake outside the largest TEE type, each behind a named switch with a test. Attackers: silent validators concentrated on a small repository; a broken TEE type's validators concentrated on it or spread, both kinds of bad fix; the target's honest validators 1, 3, 5, 10.
  - Done (exploratory, seeds 1–40): `pof/sim/openval/choice.py`, `tests/test_openval_choice.py`, [`reports/open-validators-measured-v6.md`](../../../reports/open-validators-measured-v6.md), simulation B. M = 5 (at most 2 of one TEE type) holds the broken TEE; no minimum stops silence, which stalls panels nothing releases.
- [ ] 14.2 The owner accepts, changes or rejects D33 and D34 (`REPO_MIN_ELIGIBLE`, `REPO_STAKE_X`), with report v6's numbers, and rules on what releases a counted panel that can never complete (report v6). The accepted values go into the parameters ADR of task 10.2.
- [ ] 14.3 Contracts, for the parts accepted in 14.2: a validator's lists in the registry, read by every draw (counted, audit, challenge, appeal) and by the hold's count; a repository's listing condition and its stake cap (`ValidatorRegistry`, `Panels`, `RaceV3`). Verify with Foundry tests for each scenario, the replay against the simulation, and the gas and size lines in `reports/contract-v3.md`.
- [ ] 14.4 The node and the kit: commands to set and show a validator's lists; a repository's eligible count and listing status shown to funders. Verify with unit tests against a local chain and one end-to-end draw on the local devnet that skips a validator that denied the repository.
- [ ] 14.5 Run the check: `scripts/check.sh` and `scripts/contracts.sh test`.
- [ ] 14.6 Simulate what 14.1 left out before any contract: D29 and D30 with M = 5 together; a rule that ends a counted panel that can't complete; silence just under the reveal-rate floor; GPT-6.1 seated; several families seated (the family half of the minimum). Verify: a report beside v6's rows on the same seeds.

Group 9's confirmatory run (9.1, 9.3) waits for 10.2 and 11.2, so that the frozen rules are these.

## Workflow follow-up
- After the owner's review of groups 1, 6, 7, 8 and 2, the parameters ADR (0004) is merged before group 3 starts. Done: ADR 0004 is accepted (merged), and group 3 started on 2026-11-13 (D18).
- After group 5: the paid judge check (#160) is the last evaluation before v3 is deployed to a test blockchain (owner, 2026-11-13).
- Archive this change once group 5 passes and v3 is the devnet's default.
