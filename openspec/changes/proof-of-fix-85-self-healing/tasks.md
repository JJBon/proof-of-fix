# Tasks

## 1. The constitution and ADRs (this change)

- [x] 1.1 A DRAFT `CONSTITUTION.md` for proof-of-fix, matching the built rules (D3, D5, D6, D9–D15) with Articles 2, 3 and 9 entrenched; `docs/adr/0000-template.md`; and `docs/adr/0001-self-healing-constitution.md`. Verify with `openspec validate proof-of-fix-85-self-healing --strict` and `scripts/check_openspec.py`.
- [x] 1.2 The oracle network's additions (design S11–S18, the `oracle-network` delta, data availability in `self-healing`, check gas in `bounty-market`, the new simulation actors) and the DRAFT constitution's matching articles (Article 3: key rotation, provider cap, seals, provable faults; Article 5: check gas; Article 7: allowed checker images; Article 8: availability). Verify with `openspec validate proof-of-fix-85-self-healing --strict` and `scripts/check_openspec.py`.

## 2. B1: measuring the judges (#82)

- [x] 2.1 A labelled set of real fixes: merged and rejected pull requests with their tests, taken from public repositories in a container (rule 4). Data about people is aggregated only (rule 5). Verify with a script that rebuilds the set from its manifest and checks the labels' counts. Done: `data/judges/manifest.json` (50 pairs), `scripts/judge-set.sh build`, `reports/judges-v1.md`.
- [ ] 2.2 Each candidate model family judges the set as an issue judge. Report accuracy, false passes and false fails, and the **agreement matrix between families** (on what they fail together). Verify with the report `reports/judges-v1.md` and a test that recomputes its numbers from the stored verdicts.
- [ ] 2.3 Prompt injection: the same fixes with injected text in code, comments and commit messages. Report the success rate for each family and for 2-of-3 and 5-of-7 panels. Verify in `reports/judges-v1.md` with the same recomputing test.

## 3. B2: costs (#82)

- [x] 3.1 The cost of a check for each family (tokens per verdict times price), sandbox compute, and gas from the local contracts' gas report. Give the cost per attempt, per paid fix (using the simulation's attempts per fix), per ADR (7 judges), with 3 judges and with 7. Verify with `reports/costs-v1.md` and a test that recomputes its table from its inputs. Done in #87.

## 4. The simulation

- [ ] 4.1 Tiers and escalation in `pof/`: 3 judges drawn from 7 with 2 to pass, 5 of 7 for the constitution tier, families with correlated errors, escalation by path, by flag and by challenge. Verify with unit tests for each scenario in the checking and constitution deltas; default runs unchanged (byte-identical to main on 2 seeds). Also replace the market simulation's stale evaluator costs ($0.30 per verdict, $0.20 per test run) with B2's measurements (design, "How the simulation tests it"; #102).
- [ ] 4.2 The head, system issues and the sponsors' pool: bad merged fixes raise regressions that watchers register, and the pool pays the registration and `SYSTEM_BOUNTY_START`. Merge first, revert on an upheld challenge. Verify with unit tests for the self-healing delta's scenarios.
- [ ] 4.3 The winner's check refund and coin only (no token, `market_fee_bps = 0`). Verify with unit tests for the bounty-market delta's scenarios, and the comparison with and without the refund on the same seeds.
- [ ] 4.4 The attackers: a test-gamer, a prompt injector (with B1's rates), colluders from 2 to 5 of 7, an ADR capturer and an issue farmer, each with an honest twin. Verify with a unit test for each, and the acceptance run `reports/self-healing-v1.md` (100 seeds) against the incentive-simulation delta's criteria.
- [x] 4.5 Check fees (S15): unit prices per family and for the sandbox and storage; the median-usage charge plus one agreed `SERVICE_FEE`; per-check caps and CI profiles; the maximum deposit; gas at cost; refunds; bounded updates of the table and the fee, the fee under `SERVICE_FEE_CAP`. Size the first `SERVICE_FEE` from B2 and the devnet so a typical operator's on-demand enclave is covered. Optionally `CI_SINGLE_RUN`. Compare with flat fees on the same seeds. Verify with unit tests for the oracle-network and bounty-market deltas' fee scenarios, and the comparison in `reports/self-healing-v1.md`. Done: `pof/checkgas.py`, the opt-in `check_gas` in the market, `pof/sim/oraclenet.py fees`, `tests/test_checkgas.py`; `CI_SINGLE_RUN` in the fee model only; the winner's refund stays with 4.3.
- [x] 4.6 Bonds and faults (S12, S16, S17): seat bonds, the non-revealer, the equivocator, the usage padder, the data withholder and price-table colluders, each with an honest twin; find the smallest `SEAT_BOND_MIN` at which every slashable fault loses money. Verify with a unit test for each actor, and the bond sweep in `reports/self-healing-v1.md`. Done: `pof/sim/oraclenet.py bonds`, `tests/test_oraclenet.py`; the seat-level model with each fault against its honest twin (100 seeds).

## 5. Contracts v2 (local only, one PR per task, each on the devnet from #93)

- [x] 5.1 Split under EIP-170 (design S10): `Race`, `Heads`, `Pool` and the verdicts' quorum, with no token calls. Verify that `forge build --sizes` shows every contract under 24,576 bytes, that the v1 test suites ported to v2 pass, and that the devnet (#93) accepts the deployment.
- [x] 5.2 The verdict v2 and the head registry (S1, S11): the EIP-712 struct with base, tier and receipt hash; stale verdicts refused; the winner keeping its place. Verify with unit tests for the oracle-network delta's verdict scenarios and the self-healing delta's head scenarios, and an invariant test that the head only moves by a quorum verdict.
- [x] 5.3 The tiers on-chain (S2): 3 drawn from 7 by seed, 2 to pass; 5 of 7; the owner's key recusing as a party; no function changing the counts. Verify with unit tests (too few signatures, a judge not drawn, a recused key) and the test listing every external function.
- [x] 5.4 Seats, keys and the provider cap (S13): the 7 seats fixed at deployment with operator, family and provider; key rotation only for an allowed image, co-signed by the seat's key and 5 of the other 6, after `KEY_ROTATION_DELAY_DAYS`; suspension of a seat that can't sign or whose bond is too low; at most `PROVIDER_SEAT_CAP` seats per provider. Verify with unit tests for each scenario in the oracle-network delta's seat requirements, and the external-function listing test (no function adds or replaces an operator).
- [ ] 5.5 Sealed verdicts on-chain (S12): batch seals within `SEAL_WINDOW`, reveals within `REVEAL_WINDOW`, discard and slash for no reveal, the next seat in the draw replacing a silent one. Verify with unit tests for the sealing scenarios and a gas report per verdict.
- [ ] 5.6 Receipts (S14): the receipt hash inside the sealed verdict, and receipt challenges decided by the constitution tier without the challenged seat. Verify with unit tests, and an end-to-end devnet test with #94's node producing real receipts.
- [x] 5.7 Check fees (S15): the unit price table and `SERVICE_FEE` with bounded, delayed updates and the fee's cap; per-check caps and the repository's CI profile in the quote; the maximum deposit; the median-usage charge plus the service fee; gas reimbursed at cost; `CI_SINGLE_RUN` behind its setting; pull credits for operators and relayers; the winner's refund at merge. Verify with unit tests for the fee scenarios, and the invariant suite extended so deposits always equal charges, repayments and refunds.
- [ ] 5.8 Bonds and provable faults (S16): seat bonds in `FEE_COIN`; equivocation checked by the contract; no-reveal, availability and receipt slashes; the challenger's share and the pool's. Verify with unit tests for each fault, and an invariant that no slash exceeds a seat's bond and none follows a mere disagreement.
- [ ] 5.9 Availability before the head moves (S17): 5 of 7 availability statements and the permanent copy's receipt required; availability challenges with `DA_RESPONSE_HOURS`. Verify with unit tests for the self-healing delta's availability scenarios.
- [ ] 5.10 The constitution's hash, ADRs and challenges (S4, S5): the 14-day window, entrenched articles refused, the revert head on an upheld challenge, the ADR fee and its refund from the pool. Verify with unit tests for each scenario in the constitution delta.
- [ ] 5.11 The pool and system issues (S6, S7). Verify with unit tests, and the invariant suite extended to the pool (the pot never pays outside its rules).
- [ ] 5.12 The deployment record (S18): every contract's and linked library's address and code hash, with the compiler's settings; also back-filled for v1's `OracleAuth`. Verify with a test that rebuilds the record's hashes from the chain.
- [ ] 5.13 Migration from v1 to v2 (D15): v1's bounties finish in v1, and new ones open in v2. Verify with a test that runs both versions side by side.
- [ ] 5.14 The replay against the simulation (D7) on v2's shape, fees and bonds included. Verify that the replay seeds match to the micro-credit.

## 6. The bot

- [ ] 6.1 The bot applies recorded heads to mirrors, reports and restores a rewritten mirror, and offers verified fixes upstream as one pull request. Verify against the local Forgejo: two bots converge on the same commit, and a rewritten mirror is restored.
- [ ] 6.2 Watchers register system issues: failing tests on the head and regressions. Verify end to end on the local loop: a failing test at the head becomes an issue, a fix passes the judges, the head moves, and the mirrors follow.
- [ ] 6.3 The oracle node v2 (#94's follow-ups): seals and reveals on-chain, receipts as COSE_Sign1 after the IETF draft (-02) with the exact model ID and measured usage, model calls direct to the provider from inside the TEE (no gateway), the accepted attestation types and the reproducible checker image, signed usage for check fees, an optional on-demand enclave start, availability statements and serving challenged objects, seeding public repositories over Radicle. Verify end to end on the devnet with 7 nodes and fake judges, against every oracle-network scenario.
- [x] 6.4 (done in #99) The node's cryptography on reviewed, pinned libraries (replacing #94's hand-written keccak, secp256k1 and EIP-712 code) before any key other than a devnet key is used. Verify that the node's signatures and digests match the contract's on fixed test vectors.

## 7. Report

- [ ] 7.1 A report with what works, the judges' measurements, the costs, the simulation and gas per step, posted on #85 and #82; update `README.md`. Then run the check: `scripts/check.sh` (Python tests) and `scripts/contracts.sh test`.
