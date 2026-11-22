# Open validators with measured judges, v4: the appeal on evidence, rival solvers, no deposit (proof-of-fix#236, task 11.1; 2026-11-15)

**Status: exploratory.** This report continues [`open-validators-measured-v3.md`](open-validators-measured-v3.md) (task 10.1). It uses seeds 1–40, the seeds every earlier round used, so nothing here is confirmatory. Every ± is two standard errors of the mean. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json` (#160), on issue-tier fixes only.

**Commands:**
- `python3 -m pof.sim.openval.evidence --seeds 40 --jobs 15` prints every simulated table in the appendix, in about 25 minutes.
- `python3 -m pof.sim.openval.potsplit` prints section 10's model, which uses expected values and runs no simulation.

**Two kinds of bad fix,** as before, each run on its own: the 100 fixes the hidden tests fail ("the tests fail them"), and the 78 that pass the tests and are wrong ("pass the tests, wrong").

**What the owner decided on 2026-11-15, and what he did not:**
- **Decided:**
  - D23's appeal panel, drawn from the families that did not judge the fix, is dropped. The seated judges decide an appeal.
  - The solver's deposit (D22) is **on hold**. The owner is against it and wants the market's own incentives to stop bad fixes.

  For that reason **no deposit is the primary case here**, and deposits of 2,500 and 4,000 appear only as comparison rows. 10.1's figure of 4,000 is recorded as a finding, not as a recommendation.
- **Not decided:** every rule below. Each is **proposed**, for the owner to accept, change or reject (design D24–D28).

## In brief
- **The appeal on evidence (D24) works only if the seated panel rarely passes a bad fix because its author attached a passing test.** #160 cannot say how often that happens.
  - With no deposit, a solver of bad fixes that appeals every rejection loses $1,766 ± 114 and $1,375 ± 89 a year when the panel passes 1 such test in 20.
  - It breaks even near 1 in 5 (+$153 ± 194 and +$85 ± 178), and gains $3,835 ± 302 and $2,927 ± 284 at 1 in 2.
  - Ten rival solvers, each finding a failing test 1 time in 4, make the appeal lose at every rate tried.
- **What the appeal is for:** it restores about half of the good fixes wrongly rejected, if the panel accepts half of the true tests (assumed). Good fixes wrongly unpaid fall from 8.9 % to 6.1 % and from 9.0 % to 6.2 %.
- **A better newcomer is seated by known-answer issues (D26), not by sponsorship (D25).** The newcomer is Opus 5.5 joining a network that GPT-6.1 seats.
  - Known-answer issues at 5 % seat it in 95 % ± 7 and 68 % ± 15 of runs. At 10 % they seat it in 100 % and 92 % ± 8 of runs, from about week 25. The checks cost $163 a year at 10 %.
  - Sponsorship alone seats it in 2 % ± 5 and 0 % of runs, and in 50 % ± 16 and 8 % ± 8 with six contender shadows a draw.
  - D26 needs a source of known answers that has no privileged author (#136). That source does not exist yet.
- **Verdicts never final: 0.0 %** with the second draw among few families (D27). Without it, 2.7 % ± 0.2 under seats by rank and 23.6 % ± 2.5 under v3's seats.
- **With no deposit, rival solvers decide whether a bad-fix solver profits** (D21 says anyone may dispute; only contenders disputed before).
  - With contenders only, it gains $2,741 ± 204 and $6,126 ± 370 a year.
  - It stops gaining at about **10 rival solvers each finding a test 1 time in 4** (−$265 ± 43 and −$77 ± 68), or 3 rivals finding one 1 time in 2 on fixes the tests fail (−$27 ± 83; still +$418 ± 102 on fixes that pass them). This holds for GPT-6.1 seated alone too (−$62 ± 79 and −$195 ± 53).
  - The rivals' find rate is assumed.
- **With per-issue bounties and no deposit, nothing pays the rivals to look.** At a reward of 1,000 of the bounty, a search loses $0.10 to $0.35 (expected values).
- **The shared pot (the owner's funding idea) does pay rivals to look:** +$1.44 to +$5.35 a search. But it does not lower the attacker's gain by itself. Where every fix earns an equal unit, it also pays a farmer of trivial fixes $22,000–28,000 a year more than bounties do, and leaves 11–18 % of the funding on issues not worth an honest fix.
  - **The owner's hypothesis is half supported.** The attacker's gain does fall to near zero, but only with enough rivals, and it falls just as far under per-issue bounties.
  - "Without hurting code quality" is refuted for equal units.
- **What only a deposit stops, in this simulation:**
  - **A solver that tries the same issue again and again.** With no deposit and no rival solvers it gains $19,833 ± 700 and $24,082 ± 685 a year. Ten rivals at 1 in 4 bring that to −$4,352 ± 333 and −$764 ± 309.
  - **No non-money limit was simulated.** A fee that covers the judges' cost is already in every row ($1.64 a fix) and does not stop it.

## 1. What was added to the model
Each rule is a named field of `Params` or `World`, off by default, so reports measured-v1 to -v3 reproduce. A test checks that every switch is off by default.

| Switch | Rule | Default | The proposal |
|---|---|---|---|
| `APPEAL` "evidence", `APPEAL_STAKE`, `APPEAL_STAKE_BPS`, `APPEAL_STAKE_TO` | D24: an appeal with a test and a stake, decided by a fresh draw of the seated families | "off" | stake the larger of $5 and 10 % of the bounty; a lost stake goes to the sponsors' pool |
| `World.appeal_accept_good`, `appeal_accept_bad` | D24's two **assumed** rates: the panel passes a wrongly rejected good fix, or a correctly rejected bad fix, when shown its test | 0.5, 0.05 | swept 0.25–1.0 and 0–0.5 |
| `SPONSOR`, `SPONSOR_REWARD_BPS`, `World.sponsor_by` | D25: a contender appeals in the solver's place for a fix its model passed | off | 1,000 |
| `KNOWN_RATE`, `KNOWN_WINDOW`, `KNOWN_MIN` | D26: known-answer issues judged by one validator of every family; the seat rule reads them once a family has `KNOWN_MIN` | 0 | 5 % (10 % recommended), 200, 50 |
| `SECOND_PANEL` | D27: "larger" (D4: wait), "few" (a second draw while fewer than 3 families can judge), "always" | "larger" | "few" |
| `World.rival_solvers`, `rival_find` | D21's "anyone": honest solvers of the repository dispute others' passes, each on its own draw | 0 | swept 1, 3, 10 and 10–50 % |

**How the rules are implemented, and readings chosen before the 40-seed runs:**
- **The panel's answer on an evidence appeal is one draw per fix at the assumed rate.** The panel is drawn and paid as any panel is. Its recorded #160 votes are not read, because they would only repeat the first verdict.
- **The appeal panel:**
  - It is a fresh draw from the seated families, of D4's size where that can be drawn outside the first panel.
  - Otherwise it is a fresh draw of the first panel's size, in which the first judges may sit again. This reading was added after 1-seed trial runs showed that 380 of 383 appeals found no panel.
  - An appeal whose panel stalls on a silent judge lapses after one appeal period, and its stake comes back. This was also added after trial runs.
- **An honest solver appeals:**
  - its wrongly rejected good fixes (`appeal_good` 1);
  - in "every rejection appealed" rows, every rejection too. That is the worst case: a solver of bad fixes that believes them good.
- **A sponsor's money is followed only for an actor.** The world's contenders sponsor for free.
- **Known-answer issues:**
  - Their answers are correct, and a judge cannot tell them from live submissions (assumed).
  - They are judged beside a live submission, with chance `KNOWN_RATE` per submission.
  - Their checks are paid from the fees, like an audit's.
- **A rival solver's test** is accepted when found, as a contender's is (task 10.1's machinery), and finds only bad fixes. Wrong tests from rivals are not modelled.
- **The disputer's reward with no deposit** is `EVIDENCE_REWARD_BPS` (1,000) of the reversed fix's bounty, which is then not paid to its solver. In section 10's pot it is the reversed fix's unit.
- **The deposit around an appeal (D28):** a rejected fix's deposit is held until its appeal period closes. It then goes to the issue's bounty, or back to the solver if the appeal passed. A failed appeal's stake goes to the sponsors' pool. The stake is separate from the deposit.

**Rows marked "post hoc"** were added after a run's results were seen:
- the 15 % rows of the appeal attack;
- the honest Opus 5.5 sponsor rows;
- the rival-solver rows in the code-health table.

No acceptance threshold was moved, and no row was dropped. Every earlier test still passes.

**What is assumed, measured or chosen:**

| Input | Value | Status |
|---|---|---|
| A judge's verdict on a fix | its family's recorded #160 verdict | **measured** |
| The panel passes a wrongly rejected good fix shown its test (`appeal_accept_good`) | 0.5; swept 0.25–1.0 | **assumed**: #160 has no verdict given with a test in view |
| The panel passes a correctly rejected bad fix shown a test that passes with it (`appeal_accept_bad`) | 0.05; swept 0–0.5 | **assumed**, and decisive for D24 |
| A contender finds a failing test for a bad fix | 1 in 2 | assumed (10.1) |
| A rival solver finds one | 10, 25, 50 % each | **assumed**, swept |
| Known-answer issues exist, are labelled right and can't be told apart | yes | **assumed**; no design exists (#136) |
| What a test or a sponsorship search costs | $0.50 | assumed |
| An honest fix's cost to write (section 10) | half its bounty | assumed |
| Honest solvers who stay away as the deposit rises (section 9) | 0, 25, 50 or 100 % of the deposit's share | **assumed**, swept |
| `APPEAL_WINDOW`, the stake's floor | 72 h, $5 | chosen |

## 2. The appeal on evidence (D24)
The base is 10.1's network on known seats: Opus 5.5 seated alone on fixes the tests fail, and Opus, GPT-6.1 and Gemini 3.1 Pro on fixes that pass them. The 2,500 deposit is the base's.

| Rates (assumed): good / bad evidence accepted | Bad fixes merged per 100 paid: the tests fail them | pass the tests, wrong | Good fixes wrongly unpaid | Wrongly rejected good fixes paid in the end |
|---|---|---|---|---|
| no appeal (10.1) | 4.5 ± 0.2 | 8.5 ± 0.2 | 8.9 % ± 0.2 / 9.0 % ± 0.3 | 0 % |
| D23's alternative: the seated families with no evidence (10.1) | 4.5 ± 0.2 | 8.5 ± 0.2 | 8.9 % ± 0.2 / 9.0 % ± 0.3 | 0 % (380 ± 7 of 383 appeals found no panel) |
| 25 % / 5 % | 5.1 ± 0.2 | 8.9 ± 0.2 | 7.5 % ± 0.2 / 7.5 % ± 0.3 | 24 % ± 2 / 25 % ± 1 |
| **50 % / 5 %** | 5.0 ± 0.2 | 8.7 ± 0.2 | 6.1 % ± 0.2 / 6.2 % ± 0.2 | 46 % ± 2 / 47 % ± 2 |
| 50 % / 20 % | 6.8 ± 0.3 | 10.1 ± 0.2 | 6.1 % / 6.2 % | 46 % / 47 % |
| 50 % / 50 % | 10.5 ± 0.3 | 12.7 ± 0.3 | 6.1 % / 6.2 % | 46 % / 47 % |
| 100 % / 5 % | 4.9 ± 0.2 | 8.5 ± 0.2 | 3.4 % ± 0.2 / 3.5 % ± 0.2 | 93 % ± 1 / 93 % ± 1 |

These rows assume that every rejected fix is appealed. With only good fixes appealed, bad fixes merged stay at 4.4 and 8.3.

**What an honest solver pays:**
- with no deposit, $2.00 ± 0.04 and $2.06 ± 0.06 a good fix with D24, against $1.64 and $1.57 without an appeal (whole network on live scores, appendix);
- with a deposit of 2,500, $3.55 and $3.57 against $3.93 and $3.95, because restored good fixes no longer lose their deposit.

The lost appeal stakes cost an honest solver $0.29–0.45 a good fix.

**The solver of bad fixes that appeals every rejection,** against the same solver that never appeals. The stake is the larger of $5 and 10 % of the bounty.

| Bad evidence accepted (assumed) | No deposit: the tests fail them | pass the tests, wrong | No deposit, 10 rival solvers at 25 %: the tests fail them | pass the tests, wrong | Deposit 2,500 (comparison): the tests fail them | pass the tests, wrong |
|---|---|---|---|---|---|---|
| 5 % | −1,766 ± 114 | −1,375 ± 89 | −2,231 ± 68 | −1,730 ± 51 | −1,636 ± 133 | −1,279 ± 105 |
| 10 % | −1,108 ± 156 | −861 ± 131 | −2,095 ± 66 | −1,621 ± 52 | −838 ± 190 | −657 ± 161 |
| 15 % (post hoc) | −457 ± 160 | −368 ± 150 | −1,951 ± 61 | −1,506 ± 53 | −53 ± 196 | −63 ± 186 |
| 20 % | +153 ± 194 | +85 ± 178 | −1,798 ± 65 | −1,392 ± 61 | +682 ± 238 | +485 ± 220 |
| 50 % | +3,835 ± 302 | +2,927 ± 284 | −1,025 ± 62 | −784 ± 65 | +5,121 ± 378 | +3,906 ± 354 |

- **The machine's check stops nothing by itself.** The author of a bad fix can always write a test that fails before its fix and passes after it. The panel's judgment is the whole filter.
- **A deposit makes appealing more attractive, not less.** An upheld appeal returns the deposit too, so the prize is larger. The break-even acceptance rate is stake / (stake + what the appeal wins): 16.7 % with no deposit and half the passes reversed by tests (the same formula), and 13.8 % at 2,500 (appendix, exact table).
- **The stake:**
  - $5 flat lets the solver break even at 10 % (+$158 ± 187 with 2,500).
  - 25 % of the bounty holds to about 1 in 4.
  - 10 % is the proposal: it costs an honest solver $0.29 a good fix.

**Recommendation for D24:** adopt the appeal on evidence, with a stake of the larger of $5 and 10 % of the bounty, **on the condition that task 11.3 measures `appeal_accept_bad` below about 15 %**.
- If it is higher, the appeal pays a solver of bad fixes unless rival solvers dispute.
- The number that decides it: **the break-even near 1 bad-fix test in 5 accepted** with no deposit.

## 3. The deposit held during the appeal period (D28)
A solver tries each issue up to 21 times, and is the only solver of its issues. Its twin submits nothing.

| Rule | The tests fail them | Pass the tests, wrong |
|---|---|---|
| Deposit 2,500, moved at once (10.1) | −98,721 ± 11,985 | +12,152 ± 2,283 |
| Deposit 2,500, **held** for the appeal period | −90,175 ± 12,224 | +13,019 ± 1,825 |
| …it submits again while the deposit is held | −18,568 ± 2,048 | +4,734 ± 780 |
| …it appeals every rejection, then tries again | −65,334 ± 8,615 | +8,565 ± 1,395 |
| Deposit 4,000, held | −918,858 ± 122,331 | −21,237 ± 14,259 |
| **No deposit**, no rival solvers | +19,833 ± 700 | +24,082 ± 685 |
| No deposit, 10 rival solvers at 25 % | −4,352 ± 333 | −764 ± 309 |
| No deposit, 10 rival solvers at 50 % | −8,032 ± 364 | −7,978 ± 182 |

- **Holding the deposit opens no new gain.** Held and moved at once differ by less than their errors.
- **Submitting again while a deposit is held earns less, not more.** The next fix stakes a share of the bare bounty, but the same issue's bounty pays only once.
- **The retrying solver is the deposit's real job,** and the hole that no deposit leaves open: +$19,833 and +$24,082 a year with only contenders disputing. Ten rivals at 1 in 4 close it on fixes the tests fail, and only just on fixes that pass them.

## 4. Sponsorship and seating (D25)
Live scores. The newcomer, Opus 5.5, joins in week 8 a network that GPT-6.1 seats, starting as a contender. "Six shadows" means six contender shadows drawn with each panel.

| Network | The tests fail them: runs in which Opus is ever seated | week | pass the tests, wrong: runs | week |
|---|---|---|---|---|
| no appeal (10.1) | 0 % | n/a | 0 % | n/a |
| appeal on evidence, solvers appeal their own good fixes | 5 % ± 7 | 40 | 0 % | n/a |
| …six shadows | 62 % ± 16 | 33 | 12 % ± 11 | 32 |
| solvers never appeal; **the newcomer sponsors the fixes its model passed** | 2 % ± 5 | 39 | 0 % | n/a |
| …six shadows | 50 % ± 16 | 33 | 8 % ± 8 | 30 |
| …six shadows, good evidence accepted 100 % | 98 % ± 5 | 28 | 75 % ± 14 | 28 |
| known-answer issues at 5 %, no appeal | 95 % ± 7 | 41 | 68 % ± 15 | 44 |
| known-answer issues at 10 % | 100 % | 25 | 92 % ± 8 | 28 |
| known-answer issues at 5 %, the newcomer sponsors, six shadows | 100 % | 35 | 82 % ± 12 | 39 |

- **Sponsorship moves the score the same way a solver's own appeal does,** and no faster. A sponsored appeal adds no rank of its own, and a contender's score is still a shadow block judged against outcomes that mostly come from the incumbent.
- **It does not pay at 1,000.** An honest contender running Opus 5.5 against a GPT-6.1 panel nets:
  - −$671 ± 80 and −$1,601 ± 70 a year at 1,000 (good evidence accepted 50 %);
  - +$1,257 ± 130 and +$531 ± 116 at 2,500 (post hoc rows).
  
  A contender no better than the seated panel loses at both (GPT-6.1 or DeepSeek V3.2 against Opus: −$726 to −$2,850). On fixes that pass the tests GPT-6.1 is itself seated, so it cannot sponsor ($0 in both rows).
- **A weak newcomer** (Mistral Large 3, sponsoring every fix it passed) is never seated. While it loses money it still gets 2–26 bad fixes a year paid, depending on the assumed bad-evidence rate.

**The contender that sponsors every rejection,** against a twin that sponsors nothing:
- it loses in every row: −$3,487 ± 84 at 5 % bad evidence accepted, and −$1,329 ± 72 at 50 %;
- at a reward of 2,500 and 50 %, it nears even: −$141 ± 120 and −$101 ± 88;
- it has the network pay for 8–78 more bad fixes a year than its twin's network does;
- it never seated a weak family more than 1 % of the year.

**Recommendation for D25:** allow sponsorship as a permission. Do not rely on it to seat a better family. If it is kept, `SPONSOR_REWARD_BPS` 1,000 does not pay an honest sponsor; 2,500 does when its model is clearly better.
- The number that decides it: **2 % ± 5 of runs seated** by sponsorship alone.

## 5. Known-answer issues (D26)
Live scores, no appeal. In the GPT-6.1 rows, GPT-6.1 is the genesis family.

| Rate | The tests fail them: Opus seated, share of the year | bad per 100 paid | good unpaid | Pass the tests, wrong: Opus seated | Checks a year | …a submission |
|---|---|---|---|---|---|---|
| none (live score alone) | 0 % | 10.5 ± 0.3 | 31.6 % ± 0.4 | 0 % | $0 | $0 |
| 2 % | 0 % | 10.5 | 31.6 % | 0 % | $33 ± 2 | $0.021 |
| 5 % | 34 % ± 3 (first seated week 34 ± 2) | 8.2 ± 0.4 | 24.2 % ± 0.7 | 20 % ± 5 | $81 ± 3 | $0.052 |
| **10 %** | 66 % ± 2 (week 18 ± 1) | 6.3 ± 0.3 | 16.8 % ± 0.5 | 46 % ± 7 | $163 ± 5 | $0.105 |
| 20 % | 83 % ± 1 (week 9) | 5.4 ± 0.3 | 12.8 % ± 0.3 | 62 % ± 8 | $327 ± 7 | $0.211 |
| upper bound: scores on every known answer | 100 % | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % | n/a | n/a |

- **It is the only rule that reliably unseats a strict incumbent.** At 2 %, 31 known-answer issues a year are under `KNOWN_MIN` (50), so nothing changes within the year.
- **It is cheap:** the costs are counted at the floor fee ($0.01), and are about 2.6 times as much at the fee D9 sets when only seated validators count as idle.
- **Where three families are level, a window of 200 is too noisy to seat all three at once.** At 10 % they hold the seats 80 %, 44 % and 39 % of the year.
- **It is D13's audit machinery** (a draw by the seed, paid from the fees) with what an audit lacks: a known answer, and every family.
- **The difficulty is not in this simulation.** Someone must write the known-answer issues, and judges must not be able to tell them from live ones. That is a privileged role, which D14 declined, and #136's keyless version has no design.

**Recommendation for D26:** adopt at 10 % (`KNOWN_MIN` 50, `KNOWN_WINDOW` 200) **once task 11.6 names a source of known answers**. Until then it cannot be built.
- The number that decides it: **a better newcomer is seated in 100 % and 92 % of runs at 10 %, for $163 of checks a year.**

## 6. The second draw among few families (D27)
Volunteers' second-opinion challenges are on, as in reports measured-v1 and -v2, so that challenges exist to be stuck.

| Network | Verdicts never final: the tests fail them | pass the tests, wrong |
|---|---|---|
| v3's seats, D4 (the challenge waits for a larger panel) | 23.6 % ± 2.5 | 23.0 % ± 2.4 |
| v3's seats, **a second draw while fewer than 3 families can judge** | 0.1 % ± 0.2 | 0.0 % ± 0.0 |
| seats by rank, D4 | 2.7 % ± 0.2 | 0.3 % ± 0.1 |
| seats by rank, **a second draw among few families** | 0.0 % ± 0.0 | 0.3 % ± 0.1 (3 families seated: the rule doesn't apply) |
| seats by rank, a second draw whenever the larger panel can't be drawn | 0.0 % ± 0.0 | 0.0 % ± 0.0 |

- **It ends the wait and corrects nothing.** The same family repeats its verdict.
- **Under v3's seats it lets more bad fixes through** (8.8 → 10.2 and 9.7 → 11.3 per 100 paid), because verdicts that used to wait for good now pass. A stuck verdict had been counted as unpaid.

**Recommendation for D27:** adopt, and consider "always" in place of "few".
- The number that decides it: **verdicts never final 0.0 %.**

## 7. Rival solvers as disputers (D21: anyone may dispute)
No deposit. A rival's upheld test pays it `EVIDENCE_REWARD_BPS` (1,000) of the bounty and reopens the issue. The table shows bad fixes merged per 100 paid.

| Each rival finds a test (assumed) | Rivals | The tests fail them | Pass the tests, wrong |
|---|---|---|---|
| (no test disputes at all) | 0 | 6.0 ± 0.2 | 11.7 ± 0.3 |
| (contenders only) | 0 | 4.5 ± 0.2 | 8.5 ± 0.2 |
| 10 % | 1 / 3 / 10 | 4.0 / 3.3 / 1.7 | 7.7 / 6.2 / 3.1 |
| 25 % | 1 / 3 / 10 | 3.4 / 2.0 / **0.3** | 6.4 / 3.6 / **0.5** |
| 50 % | 1 / 3 / 10 | 2.3 / 0.6 / 0.0 | 4.3 / 1.1 / 0.0 |
| 25 %, no contenders | 1 / 3 / 10 | 4.6 / 2.7 / 0.4 | 8.9 / 5.1 / 0.8 |

- **Good fixes wrongly unpaid don't change** (8.9 % and 9.0 %). Rivals' wrong tests are not modelled, and are the cost this table leaves out.

**The solver of bad fixes, no deposit,** against a twin that submits nothing ($ a year):

| Seated | Rivals | The tests fail them | Pass the tests, wrong |
|---|---|---|---|
| 10.1's seats | 0 | +2,741 ± 204 | +6,126 ± 370 |
| | 1 at 25 % | +1,902 ± 179 | +4,466 ± 336 |
| | 3 at 25 % | +891 ± 159 | +2,433 ± 251 |
| | 3 at 50 % | −27 ± 83 | +418 ± 102 |
| | 10 at 10 % | +707 ± 122 | +1,896 ± 213 |
| | **10 at 25 %** | **−265 ± 43** | **−77 ± 68** |
| GPT-6.1 alone | 0 | +5,768 ± 278 | +3,779 ± 270 |
| | 3 at 25 % | +2,237 ± 180 | +1,451 ± 172 |
| | 10 at 25 % | −62 ± 79 | −195 ± 53 |
| comparison: deposit 2,500, no rivals | | −2,976 ± 262 | +1,191 ± 369 |
| comparison: deposit 4,000, no rivals | | −6,407 ± 337 | −1,769 ± 394 |

**When it starts to hold.** The bad-fix solver earns nothing at about **10 rival solvers each finding a test 1 time in 4**, or 3 to 5 rivals at 1 in 2, for Opus 5.5 and GPT-6.1 alike. Section 10's expected values give the same counts for both seats: 4–5 rivals at 50 %, 9–12 at 25 % and 24–33 at 10 %.

**But nothing pays them to look.** With per-issue bounties and no deposit, a rival's search of a passed fix earns:
- 1,000 of the bounty with probability (share of passes that are bad) × (find rate);
- that is −$0.10 to −$0.35 a search at $0.50 a search (section 10).

Rivals who search anyway search for nothing. In the simulation they do so for free, so this table is an upper bound on what rivals do.

## 8. What only a deposit stops
- **Repeated attempts on the same issue** (section 3): +$19,833 and +$24,082 a year with no deposit and no rivals.
- **One bad fix after another from free identities** is the same attack spread across names. Only the attempt's cost limits it, and every name it adds is free.
- **The non-money limits:**
  - **a fee that covers the judges' cost:** it is already in every row (the attempt fee and seven checks, about $1.64 a fix). It does not stop either attacker. To stop the bad-fix solver it would have to reach about the deposit's size, at which point it is a deposit that honest solvers lose too;
  - **a per-identity rate limit:** useless against free identities. Not simulated;
  - **reputation earned before a large claim** (only identities with standing fixes may claim bounties above a cap): the plausible stand-in. It makes a new identity's attempts small and slow, which is what a deposit does. **Not simulated.** Its weak point is the farmer of section 10, who earns reputation cheaply;
  - **enough rival solvers:** the only non-money remedy the simulation supports (sections 3 and 7), conditional on the assumed find rate and on something paying them to search.
- **Plainly:** in this simulation, with per-issue bounties, nothing but a deposit closes the bad-fix solver's gain unless about ten rival solvers search for free. The pot of section 10 is the one change tried that pays them to search.

## 9. Code health across the deposit (per 100 funded issues)
The bad-fix solver (5 a week) stays while it profits. When it leaves, its issues count as funded and unfixed. Honest solvers stay away in proportion to the deposit's share, a rate that is **assumed** and swept. The appeal is off; the rows with the appeal on are in the appendix and differ by under 2 points.

| Deposit | The tests fail them: the solver's return | stays? | honest away | fixed / wrong / unfixed | Pass the tests, wrong: return | stays? | fixed / wrong / unfixed |
|---|---|---|---|---|---|---|---|
| 0 | +2,741 ± 204 | yes | 0 % | 57.8 / 4.5 / 37.8 | +6,126 ± 370 | yes | 58.3 / 9.0 / 32.7 |
| 1,000 | +454 ± 213 | yes | 0–10 % | 57.8–52.0 / 4.5–4.2 / 37.8–43.8 | +4,152 ± 363 | yes | 58.3–52.5 / 9.0–8.4 / 32.7–39.1 |
| 2,500 | −2,976 ± 262 | no | 0–25 % | 57.8–43.3 / 2.7–2.0 / 39.5–54.6 | +1,191 ± 369 | yes | 58.3–43.7 / 9.0–7.6 / 32.7–48.6 |
| 4,000 | −6,407 ± 337 | no | 0–40 % | 57.8–34.7 / 2.7–1.6 / 39.5–63.7 | −1,769 ± 394 | no | 58.3–35.0 / 5.4–3.3 / 36.3–61.8 |
| 0, 3 rivals at 25 % (post hoc) | +891 ± 159 | yes | 0 % | 57.8 / 1.9 / 40.3 | +2,433 ± 251 | yes | 58.3 / 3.7 / 38.0 |
| 0, 10 rivals at 25 % (post hoc) | −265 ± 43 | no | 0 % | 57.8 / 0.2 / 42.0 | −77 ± 68 | no | 58.3 / 0.3 / 41.4 |

"Wrong" means a bad fix paid and never reversed. In every row, a wrong fix that is reversed stood 0.1–0.2 days: a test reverses a pass inside its window, before payment.

**The best deposit for code health such that the bad-fix solver does not profit:**
- It is the smallest deposit that stops the solver: 2,500 on fixes the tests fail, and 4,000 on fixes that pass them.
- More than that only costs honest solvers who stay away.
- **This is the same answer as profit alone gives,** as long as no honest solver stays away.
- **It differs once they do.** At the assumed rate of 25 % of the deposit's share (10 % of honest solvers away at 4,000), 4,000 costs about 6 issues fixed in every 100 (57.8 → 52.0 and 58.3 → 52.5). It saves 2.1 wrong fixes (4.5 → 2.4) on the first kind and 4.1 (9.0 → 4.9) on the second.
- Ten rival solvers at 25 % with no deposit beat every deposit on wrong fixes (0.2 and 0.3) at no cost in fixes, if they exist and search.

**What the measure leaves out:** issues with no solver at all. Every issue in the model gets one submission. The "unfixed" counts are rejected good fixes, the issues of a bad-fix solver that left, and the issues of honest solvers who stayed away.

## 10. A shared pot split by standing fixes (the owner's hypothesis)
**The idea:**
- There are no per-issue bounties. Funders pay into the repository's pot per window.
- Each accepted fix earns its solver one unit of reputation, and at the window's end the pot is split in proportion to the units that still stand. A reversed fix earns nothing; its unit goes to whoever reversed it.
- No deposit.

**How it differs from #186's merit pool** (docs/paper/results.md 5.5; `pof/sim/cyclepool.py`): there, judges split each cycle's pool by each fix's merit, and overclaims are challenged before the split. Here nobody scores merit: every accepted fix is one unit. That removes 5.6's open number (how often judges see through inflated merit), and creates the two problems below. I read 5.4–5.6 for the definitions, but this model reuses none of `cyclepool.py`'s code.

**This model uses expected values, not the network** (`pof/sim/openval/potsplit.py`):
- Pass rates are #160's.
- Bad fixes stand when no contender (1 in 2) and no rival (each at its rate) finds a test.
- Total funding is the same as the bounties': report v3's 1,560 issues a year, median bounty $86.
- An honest fix costs half its bounty to write, and the bounty stands for the issue's difficulty (assumed).
- A bad fix costs nothing to write. There is no deposit.

| Seated | Rivals at 25 % | Bad-fix solver: bounties | the pot | Honest solver: bounties | the pot | Farmer of the cheapest fifth: pot − bounties | Issues not worth an honest fix (pot) | …their share of funding | A rival's search: bounties | the pot | Fixed / wrong / unfixed per 100: bounties | the pot | Income spread (CV per 13 weeks): bounties | the pot |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 (tests fail them) | 1 | +2,364 | +3,115 | +5,756 | +11,169 | +27,074 | 3 % | 11 % | −$0.35 | +$1.44 | 70 / 2.5 / 27 | 68 / 2.4 / 29 | 0.05 | 0.03 |
| | 3 | +1,200 | +1,622 | +5,465 | +10,796 | +27,074 | 3 % | 11 % | −$0.35 | +$1.44 | 70 / 1.4 / 28 | 68 / 1.4 / 30 | 0.11 | 0.08 |
| | 10 | −97 | −40 | +5,141 | +10,380 | +27,074 | 3 % | 11 % | −$0.35 | +$1.44 | 70 / 0.2 / 29 | 68 / 0.2 / 32 | 0.23 | 0.18 |
| GPT-6.1 (tests fail them) | 1 | +4,532 | +6,685 | +1,568 | +8,256 | +23,776 | 7 % | 18 % | −$0.10 | +$5.35 | 52 / 4.6 / 43 | 49 / 4.3 / 47 | 0.06 | 0.03 |
| | 3 | +2,420 | +3,631 | +1,040 | +7,493 | +23,776 | 7 % | 18 % | −$0.10 | +$5.35 | 52 / 2.6 / 45 | 49 / 2.4 / 49 | 0.13 | 0.09 |
| | 10 | +66 | +228 | +451 | +6,642 | +23,776 | 7 % | 18 % | −$0.10 | +$5.35 | 52 / 0.3 / 47 | 49 / 0.3 / 51 | 0.26 | 0.21 |
| Opus 5.5 (pass the tests, wrong) | 3 | +2,902 | +3,289 | +5,890 | +8,231 | +22,303 | 6 % | 16 % | −$0.15 | +$3.39 | 70 / 3.0 / 26 | 66 / 2.9 / 31 | 0.11 | 0.08 |
| GPT-6.1 (pass the tests, wrong) | 3 | +1,480 | +2,640 | +805 | +10,098 | +28,340 | 4 % | 13 % | −$0.29 | +$3.00 | 52 / 1.7 / 46 | 50 / 1.6 / 48 | 0.13 | 0.09 |

The appendix has every row, the specialist's (the tests-pass-but-wrong pool), and the rival counts each threshold needs.

**What each attacker earns:**
- **The bad-fix solver:** slightly more in the pot than with bounties (+$3,115 against +$2,364, Opus 5.5, one rival). A unit is worth the whole fund divided by the units that stand, which is more than a mean bounty. It falls to near zero at the same rival counts as with bounties:
  - 10–12 rivals at 25 % to earn nothing (9–12 with bounties);
  - 5–8 rivals to earn under a tenth of an honest solver's income.
- **The tests-pass-but-wrong specialist:** the same pattern, at the same counts (the "pass the tests, wrong" rows).
- **The farmer of trivial fixes:** with equal units, good fixes to the cheapest fifth of listed issues earn $22,000–28,000 a year more than with bounties. If anyone may file issues, a farmer filing its own trivial ones earns $24,000–27,000 a year.
- **The Sybil solver:** it gains nothing by splitting into names, because the split is linear in units. That is true by construction, and says nothing about free identities making more attempts (section 8).

**What it does to code health and to solvers:**
- **Hard issues are neglected with equal units.** 3–7 % of issues (11–18 % of the funding) are worth more effort than a unit pays. Fixed per 100 issues falls by 1–4 points. Weighting each unit by the funder's figure for the issue removes this, but that is per-issue pricing again.
- **Income is steadier:** the coefficient of variation of an honest solver's 13-week income is 0.03–0.21, against 0.04–0.26 with bounties.
- **What the pot does change:** a rival's search pays (+$1.44 to +$5.35) where it does not with bounties. The freed unit goes to whoever reversed the fix, and every solver's share grows when a bad fix's unit is removed.
- **One caveat on fairness:** the pot pays out all of each window's funding. Bounties leave the money of unfixed issues unpaid within the year. That, not skill, is part of why the honest solver earns more in the pot.

**The owner's hypothesis,** "with a healthy number of solvers and strong judges, the attacker's gain is near zero or well below an honest solver's, without hurting code quality":
- **Supported in part:**
  - with about 10 rivals at 1 in 4, or 4–5 at 1 in 2, the bad-fix solver's gain is near zero for Opus 5.5 and for GPT-6.1;
  - with 5–8 rivals it is under a tenth of an honest solver's;
  - "strong judges" matters less than the number of rivals: GPT-6.1 needs one or two more.
- **Not because of the pot.** Per-issue bounties reach zero at the same counts. The pot's real contribution is paying the rivals to look, which bounties with no deposit do not do.
- **Refuted on code quality with equal units:** the farmer and the neglected hard issues.
- **Untested:**
  - whether the rivals the pot pays actually turn up. Their number is an input here, not a result;
  - a network simulation of the pot. This section is expected values only.

## 11. What this does not show
- **D24's safety rests on a rate nobody has measured:** how often a seated judge passes a correctly rejected bad fix once its author shows a test that passes. Measuring it needs model calls with tests in the prompt, on #160's bad fixes, and tests written by the fixes' authors to beat the judge (task 11.3).
- **The rival solvers' find rate, and whether they exist,** are assumed. Measuring them needs real repositories with several solvers, or model calls that write tests for others' fixes.
- **Rival solvers' and sponsors' wrong tests are not modelled.** With more disputers, more wrong tests are filed, and 10.1 found them the larger part of an honest solver's cost when accepted 1 time in 5.
- **Known-answer issues assume a source that does not exist** (#136).
- **The pot is not simulated in the network;** section 10 is expected values with stated assumptions.
- **Validators neither enter nor leave;** the fee sits at its floor under seats by rank (10.1, section 8).
- **Seeds 1–40, 228 cases, one benchmark;** each kind of bad fix is run on its own.

## 12. For the owner
| Rule | Recommendation | The number that decides it |
|---|---|---|
| D24, the appeal on evidence decided by the seated families | **adopt, with a stake of the larger of $5 and 10 %, on the condition that task 11.3 measures the bad-evidence rate under about 15 %** | the appealing solver of bad fixes breaks even near 1 test in 5 accepted (no deposit: +$153 ± 194 at 20 %, −$457 ± 160 at 15 %) |
| D25, sponsorship | **allow; don't rely on it** (2,500 if it should pay) | a better newcomer seated in 2 % ± 5 of runs by sponsorship alone |
| D26, known-answer issues | **adopt at 10 %, once a source exists (task 11.6)** | a better newcomer seated in 100 % and 92 % of runs, for $163 a year |
| D27, the second draw among few families | **adopt** ("always" also closes the 0.3 %) | verdicts never final: 0.0 % (from 2.7 % and 23.6 %) |
| D28, the deposit held during the appeal period | **adopt if there is a deposit**; on hold with D22 | the retrying solver: +$13,019 held against +$12,152 moved at once, no new gain |
| D22, the deposit itself | **on hold (owner).** Without it, about 10 rival solvers at 1 in 4 are needed, and only the pot pays them | the bad-fix solver: +$2,741 and +$6,126 a year with no deposit and no rivals; −$265 and −$77 with 10 rivals at 25 % |
| The shared pot | **not yet:** test it in the network with weighted units before the owner rules | farmer +$22,000–28,000 a year with equal units; a rival's search +$1.44 to +$5.35 (against −$0.10 to −$0.35 with bounties) |

## Appendix: the full output

Seeds 1-40; every ± is two standard errors of the mean. The tables come from four runs of the same code (`--only` subsets), joined here in the module's order; the pot's tables are `potsplit`'s output.

### The acceptance rate above which an appeal pays (exact, no simulation)

| Stake, share of the bounty | Deposit 2,500: an appeal pays above | …if half the bad fixes it wins are then reversed by a test | Deposit 4,000: an appeal pays above | …if half are then reversed | A sponsor paid 1,000 of the bounty gains above | A sponsor paid 2,500 gains above |
|---|---|---|---|---|---|---|
| 5 % | 3.8 % | 7.4 % | 3.4 % | 6.7 % | 33 % | 17 % |
| 10 % | 7.4 % | 13.8 % | 6.7 % | 12.5 % | 50 % | 29 % |
| 25 % | 16.7 % | 28.6 % | 15.2 % | 26.3 % | 71 % | 50 % |
| 50 % | 28.6 % | 44.4 % | 26.3 % | 41.7 % | 83 % | 67 % |

### The appeal on evidence, decided by the seated families (D24): the two assumed rates

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | …of which appeal stakes lost | Appeals a year | Correct rejections overturned, of those appealed | Bad fixes paid after an appeal, a year | Wrongly rejected good fixes paid in the end | Appeals with no panel | Verdicts never final |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: no appeal (task 10.1's base) | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | $0.00 ± 0.00 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 | 0.0 % ± 0.0 |
| bad = the tests fail them: D23's appeal, the seated families' next draw, no evidence (10.1) | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | $0.00 ± 0.00 | 383 ± 7 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 380 ± 7 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 25 %, bad-fix evidence accepted 5 %; every rejection appealed | 5.1 ± 0.2 | 7.5 % ± 0.2 | $4.06 ± 0.10 | $1.91 ± 0.07 | $0.45 ± 0.03 | 383 ± 7 | 5 % ± 0 | 7.5 ± 1.0 | 24 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 0 %; every rejection appealed | 4.4 ± 0.2 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 383 ± 7 | 0 % ± 0 | 0.0 ± 0.0 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: **appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %**; every rejection appealed | 5.0 ± 0.2 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 383 ± 7 | 5 % ± 0 | 7.5 ± 1.0 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 10 %; every rejection appealed | 5.6 ± 0.3 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 383 ± 7 | 10 % ± 1 | 15.2 ± 1.4 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 20 %; every rejection appealed | 6.8 ± 0.3 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 382 ± 7 | 19 % ± 1 | 29.6 ± 2.2 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 50 %; every rejection appealed | 10.5 ± 0.3 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 383 ± 7 | 50 % ± 1 | 77.7 ± 3.3 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 75 %, bad-fix evidence accepted 5 %; every rejection appealed | 4.9 ± 0.2 | 4.7 % ± 0.2 | $3.06 ± 0.07 | $1.21 ± 0.06 | $0.14 ± 0.01 | 383 ± 7 | 5 % ± 0 | 7.5 ± 1.0 | 70 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 75 %, bad-fix evidence accepted 20 %; every rejection appealed | 6.7 ± 0.3 | 4.7 % ± 0.2 | $3.06 ± 0.07 | $1.21 ± 0.06 | $0.14 ± 0.01 | 383 ± 7 | 19 % ± 1 | 29.6 ± 2.2 | 70 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 100 %, bad-fix evidence accepted 5 %; every rejection appealed | 4.9 ± 0.2 | 3.4 % ± 0.2 | $2.59 ± 0.05 | $0.88 ± 0.05 | $0.00 ± 0.00 | 383 ± 7 | 5 % ± 0 | 7.5 ± 1.0 | 93 % ± 1 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 100 %, bad-fix evidence accepted 20 %; every rejection appealed | 6.6 ± 0.3 | 3.4 % ± 0.2 | $2.58 ± 0.05 | $0.88 ± 0.05 | $0.00 ± 0.00 | 383 ± 7 | 19 % ± 1 | 29.6 ± 2.2 | 93 % ± 1 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; good fixes only appealed | 4.4 ± 0.2 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 68 ± 2 | n/a | 0.0 ± 0.0 | 46 % ± 2 | 1 ± 0 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; every rejection appealed; deposit 4,000 | 5.0 ± 0.2 | 6.1 % ± 0.2 | $4.48 ± 0.11 | $2.49 ± 0.09 | $0.29 ± 0.02 | 383 ± 7 | 5 % ± 0 | 7.5 ± 1.0 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; every rejection appealed; lost stakes to the issue's bounty | 5.0 ± 0.2 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 383 ± 7 | 5 % ± 0 | 7.5 ± 1.0 | 46 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = the tests fail them: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 20 %; every rejection appealed; no test disputes | 10.4 ± 0.3 | 3.0 % ± 0.2 | $2.75 ± 0.08 | $0.75 ± 0.05 | $0.29 ± 0.02 | 383 ± 7 | 19 % ± 1 | 59.7 ± 2.6 | 49 % ± 2 | 7 ± 1 | 0.0 % ± 0.0 |
| bad = pass the tests, wrong: no appeal (task 10.1's base) | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | $0.00 ± 0.00 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: D23's appeal, the seated families' next draw, no evidence (10.1) | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.98 ± 0.08 | $2.34 ± 0.08 | $0.00 ± 0.00 | 310 ± 7 | 0 % ± 0 | 0.0 ± 0.0 | 0 % ± 0 | 104 ± 15 | 0.3 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 25 %, bad-fix evidence accepted 5 %; every rejection appealed | 8.9 ± 0.2 | 7.5 % ± 0.3 | $4.07 ± 0.10 | $1.96 ± 0.08 | $0.45 ± 0.03 | 310 ± 7 | 5 % ± 0 | 6.1 ± 0.9 | 25 % ± 1 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 0 %; every rejection appealed | 8.3 ± 0.2 | 6.2 % ± 0.2 | $3.57 ± 0.08 | $1.61 ± 0.07 | $0.30 ± 0.02 | 310 ± 7 | 0 % ± 0 | 0.0 ± 0.0 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: **appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %**; every rejection appealed | 8.7 ± 0.2 | 6.2 % ± 0.2 | $3.57 ± 0.08 | $1.62 ± 0.07 | $0.30 ± 0.02 | 310 ± 7 | 5 % ± 0 | 6.0 ± 0.8 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 10 %; every rejection appealed | 9.2 ± 0.2 | 6.2 % ± 0.2 | $3.57 ± 0.08 | $1.62 ± 0.07 | $0.30 ± 0.02 | 310 ± 7 | 10 % ± 0 | 11.9 ± 1.1 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 20 %; every rejection appealed | 10.1 ± 0.2 | 6.2 % ± 0.2 | $3.57 ± 0.09 | $1.61 ± 0.07 | $0.30 ± 0.03 | 310 ± 7 | 20 % ± 1 | 24.2 ± 1.5 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 50 %; every rejection appealed | 12.7 ± 0.3 | 6.2 % ± 0.2 | $3.57 ± 0.08 | $1.61 ± 0.07 | $0.29 ± 0.02 | 310 ± 7 | 50 % ± 1 | 60.8 ± 2.8 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 75 %, bad-fix evidence accepted 5 %; every rejection appealed | 8.6 ± 0.2 | 4.9 % ± 0.2 | $3.10 ± 0.07 | $1.29 ± 0.06 | $0.15 ± 0.02 | 310 ± 7 | 5 % ± 0 | 6.0 ± 0.8 | 70 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 75 %, bad-fix evidence accepted 20 %; every rejection appealed | 10.0 ± 0.2 | 4.9 % ± 0.2 | $3.10 ± 0.07 | $1.28 ± 0.06 | $0.15 ± 0.02 | 310 ± 7 | 20 % ± 1 | 24.2 ± 1.5 | 70 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 100 %, bad-fix evidence accepted 5 %; every rejection appealed | 8.5 ± 0.2 | 3.5 % ± 0.2 | $2.61 ± 0.06 | $0.95 ± 0.06 | $0.00 ± 0.00 | 310 ± 7 | 5 % ± 0 | 6.1 ± 0.8 | 93 % ± 1 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 100 %, bad-fix evidence accepted 20 %; every rejection appealed | 9.9 ± 0.2 | 3.5 % ± 0.2 | $2.60 ± 0.06 | $0.94 ± 0.06 | $0.00 ± 0.00 | 310 ± 7 | 20 % ± 1 | 24.2 ± 1.5 | 93 % ± 1 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; good fixes only appealed | 8.3 ± 0.2 | 6.2 % ± 0.2 | $3.57 ± 0.08 | $1.61 ± 0.06 | $0.30 ± 0.02 | 68 ± 2 | n/a | 0.0 ± 0.0 | 47 % ± 2 | 0 ± 0 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; every rejection appealed; deposit 4,000 | 8.7 ± 0.2 | 6.2 % ± 0.2 | $4.54 ± 0.12 | $2.59 ± 0.11 | $0.30 ± 0.02 | 310 ± 7 | 5 % ± 0 | 6.0 ± 0.8 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; every rejection appealed; lost stakes to the issue's bounty | 8.7 ± 0.2 | 6.2 % ± 0.2 | $3.57 ± 0.08 | $1.62 ± 0.07 | $0.30 ± 0.02 | 310 ± 7 | 5 % ± 0 | 6.0 ± 0.8 | 47 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |
| bad = pass the tests, wrong: appeal on evidence; good-fix evidence accepted 50 %, bad-fix evidence accepted 20 %; every rejection appealed; no test disputes | 14.6 ± 0.3 | 3.2 % ± 0.2 | $2.78 ± 0.09 | $0.82 ± 0.06 | $0.29 ± 0.02 | 310 ± 7 | 20 % ± 1 | 48.2 ± 2.0 | 50 % ± 2 | 2 ± 1 | 0.2 % ± 0.1 |

### The solver that appeals every rejection with a test it wrote, against the same solver that never appeals

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: bad-fix evidence accepted 5 %; stake $5 flat; deposit 2,500 | -583 ± 121 | loses | -3,522 | -2,939 | 211 appeals, 10 upheld, 5 of them paid; 37 bad fixes paid of 261 (twin: 32); $-2.76 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 5 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | -1,636 ± 133 | loses | -4,575 | -2,939 | 211 appeals, 10 upheld, 5 of them paid; 37 bad fixes paid of 261 (twin: 32); $-7.74 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 5 %; stake the larger of $5 and 25 %; deposit 2,500 | -4,576 ± 198 | loses | -7,516 | -2,939 | 211 appeals, 10 upheld, 5 of them paid; 37 bad fixes paid of 261 (twin: 32); $-21.64 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 10 %; stake $5 flat; deposit 2,500 | +158 ± 187 | not significant | -2,781 | -2,939 | 211 appeals, 20 upheld, 10 of them paid; 42 bad fixes paid of 261 (twin: 32); $+0.75 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 10 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | -838 ± 190 | loses | -3,777 | -2,939 | 211 appeals, 20 upheld, 10 of them paid; 42 bad fixes paid of 261 (twin: 32); $-3.96 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 10 %; stake the larger of $5 and 25 %; deposit 2,500 | -3,625 ± 232 | loses | -6,564 | -2,939 | 211 appeals, 20 upheld, 10 of them paid; 42 bad fixes paid of 261 (twin: 32); $-17.14 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 15 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | -53 ± 196 | not significant | -2,992 | -2,939 | 211 appeals, 31 upheld, 15 of them paid; 47 bad fixes paid of 261 (twin: 32); $-0.25 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 20 %; stake $5 flat; deposit 2,500 | +1,565 ± 234 | **wins** | -1,374 | -2,939 | 211 appeals, 42 upheld, 21 of them paid; 52 bad fixes paid of 261 (twin: 32); $+7.40 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 20 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | +682 ± 238 | **wins** | -2,258 | -2,939 | 211 appeals, 42 upheld, 21 of them paid; 52 bad fixes paid of 261 (twin: 32); $+3.22 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 20 %; stake the larger of $5 and 25 %; deposit 2,500 | -1,788 ± 274 | loses | -4,728 | -2,939 | 211 appeals, 42 upheld, 21 of them paid; 52 bad fixes paid of 261 (twin: 32); $-8.46 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 50 %; stake $5 flat; deposit 2,500 | +5,680 ± 380 | **wins** | 2,741 | -2,939 | 211 appeals, 103 upheld, 51 of them paid; 83 bad fixes paid of 261 (twin: 32); $+26.86 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 50 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | +5,121 ± 378 | **wins** | 2,182 | -2,939 | 211 appeals, 103 upheld, 51 of them paid; 83 bad fixes paid of 261 (twin: 32); $+24.22 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 50 %; stake the larger of $5 and 25 %; deposit 2,500 | +3,560 ± 382 | **wins** | 621 | -2,939 | 211 appeals, 103 upheld, 51 of them paid; 83 bad fixes paid of 261 (twin: 32); $+16.84 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 5 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | -1,558 ± 145 | loses | -7,906 | -6,348 | 211 appeals, 10 upheld, 5 of them paid; 37 bad fixes paid of 261 (twin: 32); $-7.37 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 10 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | -676 ± 210 | loses | -7,024 | -6,348 | 211 appeals, 20 upheld, 10 of them paid; 42 bad fixes paid of 261 (twin: 32); $-3.20 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 15 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | +190 ± 218 | not significant | -6,158 | -6,348 | 211 appeals, 31 upheld, 15 of them paid; 47 bad fixes paid of 261 (twin: 32); $+0.90 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 20 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | +999 ± 265 | **wins** | -5,349 | -6,348 | 211 appeals, 42 upheld, 21 of them paid; 52 bad fixes paid of 261 (twin: 32); $+4.72 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 50 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | +5,893 ± 424 | **wins** | -455 | -6,348 | 211 appeals, 103 upheld, 51 of them paid; 83 bad fixes paid of 261 (twin: 32); $+27.87 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 10 %; stake the larger of $5 and 10 %; deposit 2,500; no test disputes | +435 ± 241 | **wins** | -645 | -1,080 | 211 appeals, 20 upheld, 20 of them paid; 66 bad fixes paid of 261 (twin: 46); $+2.06 an appeal |
| bad = the tests fail them: bad-fix evidence accepted 20 %; stake the larger of $5 and 10 %; deposit 2,500; no test disputes | +3,345 ± 303 | **wins** | 2,265 | -1,080 | 212 appeals, 42 upheld, 42 of them paid; 88 bad fixes paid of 261 (twin: 46); $+15.81 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 5 %; stake $5 flat; deposit 2,500 | -458 ± 94 | loses | 764 | 1,222 | 163 appeals, 8 upheld, 4 of them paid; 69 bad fixes paid of 261 (twin: 65); $-2.81 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 5 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | -1,279 ± 105 | loses | -57 | 1,222 | 163 appeals, 8 upheld, 4 of them paid; 69 bad fixes paid of 261 (twin: 65); $-7.85 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 5 %; stake the larger of $5 and 25 %; deposit 2,500 | -3,570 ± 153 | loses | -2,348 | 1,222 | 163 appeals, 8 upheld, 4 of them paid; 69 bad fixes paid of 261 (twin: 65); $-21.91 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 10 %; stake $5 flat; deposit 2,500 | +121 ± 158 | not significant | 1,343 | 1,222 | 163 appeals, 16 upheld, 8 of them paid; 72 bad fixes paid of 261 (twin: 65); $+0.74 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 10 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | -657 ± 161 | loses | 565 | 1,222 | 163 appeals, 16 upheld, 8 of them paid; 72 bad fixes paid of 261 (twin: 65); $-4.03 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 10 %; stake the larger of $5 and 25 %; deposit 2,500 | -2,830 ± 190 | loses | -1,608 | 1,222 | 163 appeals, 16 upheld, 8 of them paid; 72 bad fixes paid of 261 (twin: 65); $-17.37 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 15 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | -63 ± 186 | not significant | 1,159 | 1,222 | 163 appeals, 24 upheld, 12 of them paid; 77 bad fixes paid of 261 (twin: 65); $-0.39 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 20 %; stake $5 flat; deposit 2,500 | +1,174 ± 219 | **wins** | 2,396 | 1,222 | 163 appeals, 32 upheld, 16 of them paid; 81 bad fixes paid of 261 (twin: 65); $+7.21 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 20 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | +485 ± 220 | **wins** | 1,707 | 1,222 | 163 appeals, 32 upheld, 16 of them paid; 81 bad fixes paid of 261 (twin: 65); $+2.97 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 20 %; stake the larger of $5 and 25 %; deposit 2,500 | -1,440 ± 238 | loses | -218 | 1,222 | 163 appeals, 32 upheld, 16 of them paid; 81 bad fixes paid of 261 (twin: 65); $-8.84 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 50 %; stake $5 flat; deposit 2,500 | +4,342 ± 355 | **wins** | 5,564 | 1,222 | 163 appeals, 80 upheld, 40 of them paid; 104 bad fixes paid of 261 (twin: 65); $+26.64 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 50 %; stake the larger of $5 and 10 % of the bounty; deposit 2,500 | +3,906 ± 354 | **wins** | 5,128 | 1,222 | 163 appeals, 80 upheld, 40 of them paid; 104 bad fixes paid of 261 (twin: 65); $+23.96 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 50 %; stake the larger of $5 and 25 %; deposit 2,500 | +2,689 ± 360 | **wins** | 3,911 | 1,222 | 163 appeals, 80 upheld, 40 of them paid; 104 bad fixes paid of 261 (twin: 65); $+16.50 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 5 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | -1,220 ± 115 | loses | -2,941 | -1,720 | 163 appeals, 8 upheld, 4 of them paid; 69 bad fixes paid of 261 (twin: 65); $-7.49 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 10 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | -534 ± 179 | loses | -2,254 | -1,720 | 163 appeals, 16 upheld, 8 of them paid; 72 bad fixes paid of 261 (twin: 65); $-3.28 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 15 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | +120 ± 207 | not significant | -1,600 | -1,720 | 163 appeals, 24 upheld, 12 of them paid; 77 bad fixes paid of 261 (twin: 65); $+0.74 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 20 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | +724 ± 246 | **wins** | -996 | -1,720 | 163 appeals, 32 upheld, 16 of them paid; 81 bad fixes paid of 261 (twin: 65); $+4.45 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 50 %; stake the larger of $5 and 10 % of the bounty; deposit 4,000 | +4,493 ± 396 | **wins** | 2,773 | -1,720 | 163 appeals, 80 upheld, 40 of them paid; 104 bad fixes paid of 261 (twin: 65); $+27.57 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 10 %; stake the larger of $5 and 10 %; deposit 2,500; no test disputes | +310 ± 246 | **wins** | 5,533 | 5,223 | 163 appeals, 16 upheld, 16 of them paid; 112 bad fixes paid of 261 (twin: 96); $+1.90 an appeal |
| bad = pass the tests, wrong: bad-fix evidence accepted 20 %; stake the larger of $5 and 10 %; deposit 2,500; no test disputes | +2,572 ± 301 | **wins** | 7,795 | 5,223 | 163 appeals, 32 upheld, 32 of them paid; 129 bad fixes paid of 261 (twin: 96); $+15.79 an appeal |

### The solver that appeals every rejection, with no deposit

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: no deposit; bad-fix evidence accepted 5 %; stake the larger of $5 and 10 %; 0 rival solvers | -1,766 ± 114 | loses | 975 | 2,742 | 211 appeals, 10 upheld, 5 of them paid; 37 bad fixes paid of 261 (twin: 32); $-8.35 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 5 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -2,231 ± 68 | loses | -2,497 | -266 | 211 appeals, 10 upheld, 0 of them paid; 2 bad fixes paid of 261 (twin: 2); $-10.56 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 10 %; stake the larger of $5 and 10 %; 0 rival solvers | -1,108 ± 156 | loses | 1,634 | 2,742 | 211 appeals, 20 upheld, 10 of them paid; 42 bad fixes paid of 261 (twin: 32); $-5.24 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 10 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -2,095 ± 66 | loses | -2,361 | -266 | 211 appeals, 20 upheld, 1 of them paid; 2 bad fixes paid of 261 (twin: 2); $-9.91 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 15 %; stake the larger of $5 and 10 %; 0 rival solvers | -457 ± 160 | loses | 2,285 | 2,742 | 211 appeals, 31 upheld, 15 of them paid; 47 bad fixes paid of 261 (twin: 32); $-2.16 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 15 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,951 ± 61 | loses | -2,217 | -266 | 211 appeals, 31 upheld, 1 of them paid; 3 bad fixes paid of 261 (twin: 2); $-9.23 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 20 %; stake the larger of $5 and 10 %; 0 rival solvers | +153 ± 194 | not significant | 2,894 | 2,742 | 211 appeals, 42 upheld, 21 of them paid; 52 bad fixes paid of 261 (twin: 32); $+0.72 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 20 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,798 ± 65 | loses | -2,064 | -266 | 211 appeals, 42 upheld, 2 of them paid; 3 bad fixes paid of 261 (twin: 2); $-8.51 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 50 %; stake the larger of $5 and 10 %; 0 rival solvers | +3,835 ± 302 | **wins** | 6,576 | 2,742 | 211 appeals, 103 upheld, 51 of them paid; 83 bad fixes paid of 261 (twin: 32); $+18.14 an appeal |
| bad = the tests fail them: no deposit; bad-fix evidence accepted 50 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,025 ± 62 | loses | -1,291 | -266 | 212 appeals, 103 upheld, 3 of them paid; 5 bad fixes paid of 261 (twin: 2); $-4.85 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 5 %; stake the larger of $5 and 10 %; 0 rival solvers | -1,375 ± 89 | loses | 4,751 | 6,126 | 163 appeals, 8 upheld, 4 of them paid; 69 bad fixes paid of 261 (twin: 65); $-8.44 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 5 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,730 ± 51 | loses | -1,807 | -77 | 163 appeals, 8 upheld, 0 of them paid; 4 bad fixes paid of 261 (twin: 4); $-10.62 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 10 %; stake the larger of $5 and 10 %; 0 rival solvers | -861 ± 131 | loses | 5,264 | 6,126 | 163 appeals, 16 upheld, 8 of them paid; 72 bad fixes paid of 261 (twin: 65); $-5.29 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 10 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,621 ± 52 | loses | -1,698 | -77 | 163 appeals, 16 upheld, 1 of them paid; 4 bad fixes paid of 261 (twin: 4); $-9.95 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 15 %; stake the larger of $5 and 10 %; 0 rival solvers | -368 ± 150 | loses | 5,758 | 6,126 | 163 appeals, 24 upheld, 12 of them paid; 77 bad fixes paid of 261 (twin: 65); $-2.26 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 15 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,506 ± 53 | loses | -1,583 | -77 | 163 appeals, 24 upheld, 1 of them paid; 5 bad fixes paid of 261 (twin: 4); $-9.25 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 20 %; stake the larger of $5 and 10 %; 0 rival solvers | +85 ± 178 | not significant | 6,211 | 6,126 | 163 appeals, 32 upheld, 16 of them paid; 81 bad fixes paid of 261 (twin: 65); $+0.52 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 20 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -1,392 ± 61 | loses | -1,470 | -77 | 163 appeals, 32 upheld, 1 of them paid; 5 bad fixes paid of 261 (twin: 4); $-8.55 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 50 %; stake the larger of $5 and 10 %; 0 rival solvers | +2,927 ± 284 | **wins** | 9,053 | 6,126 | 163 appeals, 80 upheld, 40 of them paid; 104 bad fixes paid of 261 (twin: 65); $+17.96 an appeal |
| bad = pass the tests, wrong: no deposit; bad-fix evidence accepted 50 %; stake the larger of $5 and 10 %; 10 rival solvers at 25 % | -784 ± 65 | loses | -861 | -77 | 163 appeals, 80 upheld, 2 of them paid; 6 bad fixes paid of 261 (twin: 4); $-4.81 an appeal |

### The deposit held during the appeal period (D28): a solver that tries the same issue again

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: tries each issue up to 21 times; deposit 2,500; no appeal: the deposit moves at once (10.1) | -98,721 ± 11,985 | loses | -98,721 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $-54.41 a fix submitted; $232,275 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 2,500; **the deposit held for the appeal period**; it waits, and does not appeal | -90,175 ± 12,224 | loses | -90,175 | 0 | 216 bad fixes paid of 1730 submitted (12 %); $-52.11 a fix submitted; $205,439 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 2,500; the deposit held; it submits again while it is held | -18,568 ± 2,048 | loses | -18,568 | 0 | 168 bad fixes paid of 1347 submitted (13 %); $-13.79 a fix submitted; $48,423 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 2,500; the deposit held; it appeals every rejection, then tries again | -65,334 ± 8,615 | loses | -65,334 | 0 | 224 bad fixes paid of 1550 submitted (14 %); $-42.15 a fix submitted; $150,461 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 4,000; no appeal: the deposit moves at once (10.1) | -1,038,175 ± 118,779 | loses | -1,038,175 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $-572.21 a fix submitted; $1,633,868 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 4,000; **the deposit held for the appeal period**; it waits, and does not appeal | -918,858 ± 122,331 | loses | -918,858 | 0 | 216 bad fixes paid of 1730 submitted (12 %); $-531.02 a fix submitted; $1,408,684 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 4,000; the deposit held; it submits again while it is held | -62,823 ± 6,346 | loses | -62,823 | 0 | 168 bad fixes paid of 1347 submitted (13 %); $-46.65 a fix submitted; $107,812 of deposits lost |
| bad = the tests fail them: tries each issue up to 21 times; deposit 4,000; the deposit held; it appeals every rejection, then tries again | -553,248 ± 77,019 | loses | -553,248 | 0 | 224 bad fixes paid of 1550 submitted (14 %); $-356.92 a fix submitted; $921,978 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 2,500; no appeal: the deposit moves at once (10.1) | +12,152 ± 2,283 | **wins** | 12,152 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $+11.77 a fix submitted; $46,010 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 2,500; **the deposit held for the appeal period**; it waits, and does not appeal | +13,019 ± 1,825 | **wins** | 13,019 | 0 | 251 bad fixes paid of 1011 submitted (25 %); $+12.87 a fix submitted; $43,441 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 2,500; the deposit held; it submits again while it is held | +4,734 ± 780 | **wins** | 4,734 | 0 | 174 bad fixes paid of 703 submitted (25 %); $+6.73 a fix submitted; $14,769 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 2,500; the deposit held; it appeals every rejection, then tries again | +8,565 ± 1,395 | **wins** | 8,565 | 0 | 251 bad fixes paid of 955 submitted (26 %); $+8.96 a fix submitted; $34,577 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 4,000; no appeal: the deposit moves at once (10.1) | -35,882 ± 19,157 | loses | -35,882 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $-34.75 a fix submitted; $170,668 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 4,000; **the deposit held for the appeal period**; it waits, and does not appeal | -21,237 ± 14,259 | loses | -21,237 | 0 | 251 bad fixes paid of 1011 submitted (25 %); $-21.00 a fix submitted; $148,004 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 4,000; the deposit held; it submits again while it is held | -3,842 ± 1,236 | loses | -3,842 | 0 | 174 bad fixes paid of 703 submitted (25 %); $-5.46 a fix submitted; $25,508 of deposits lost |
| bad = pass the tests, wrong: tries each issue up to 21 times; deposit 4,000; the deposit held; it appeals every rejection, then tries again | -13,158 ± 8,149 | loses | -13,158 | 0 | 251 bad fixes paid of 955 submitted (26 %); $-13.77 a fix submitted; $102,770 of deposits lost |

### Sponsorship and seating (D25, D26), on live scores

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | Runs in which the new family was ever seated | Week it was first seated | Seated, share of its weeks | GPT-6.1 seated, share of the year | Opus 5.5 seated, share of the year | Appeals a year | …sponsored | Bad fixes paid after an appeal, a year | No family met the rule, share of the year |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: no appeal (10.1) | 10.7 ± 0.6 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: no appeal, six contender shadows a draw (10.1) | 10.7 ± 0.6 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: appeal on evidence, solvers appeal their good fixes, no sponsor | 9.1 ± 0.5 | 17.0 % ± 0.6 | 5 % ± 7 | 40 ± 15 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 130 ± 23 | 0 ± 0 | 0.0 ± 0.0 | 1 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: appeal on evidence, solvers appeal their good fixes, no sponsor; six shadows | 7.9 ± 0.6 | 14.4 % ± 1.2 | 62 % ± 16 | 33 ± 4 | 18 % ± 8 | 85 % ± 7 | 15 % ± 7 | 102 ± 15 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: solvers never appeal; **the newcomer sponsors the fixes its model passed** | 9.4 ± 0.5 | 20.0 % ± 0.6 | 2 % ± 5 | 39 ± 0 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 114 ± 21 | 114 ± 21 | 0.2 ± 0.1 | 0 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: solvers never appeal; **the newcomer sponsors; six shadows** | 8.4 ± 0.7 | 18.2 % ± 1.2 | 50 % ± 16 | 33 ± 4 | 14 % ± 7 | 89 % ± 6 | 12 % ± 6 | 87 ± 17 | 87 ± 17 | 0.2 ± 0.1 | 1 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: the newcomer sponsors; six shadows; good-fix evidence accepted 25 % | 10.0 ± 0.5 | 25.3 % ± 0.7 | 18 % ± 12 | 39 ± 8 | 0 % ± 1 | 100 % ± 0 | 0 % ± 0 | 114 ± 20 | 114 ± 20 | 0.2 ± 0.1 | 0 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: the newcomer sponsors; six shadows; good-fix evidence accepted 100 % | 5.5 ± 0.4 | 9.7 % ± 0.4 | 98 % ± 5 | 28 ± 2 | 54 % ± 5 | 55 % ± 4 | 45 % ± 4 | 29 ± 2 | 29 ± 2 | 0.1 ± 0.1 | 0 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: every contender sponsors the fixes its model passed; six shadows | 8.8 ± 0.6 | 15.4 % ± 1.1 | 55 % ± 16 | 32 ± 4 | 11 % ± 7 | 90 % ± 6 | 9 % ± 6 | 207 ± 32 | 207 ± 32 | 2.4 ± 0.7 | 1 % ± 0 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: every contender sponsors; six shadows; bad-fix evidence accepted 20 % | 9.9 ± 0.6 | 15.1 % ± 1.2 | 45 % ± 16 | 29 ± 5 | 14 % ± 8 | 88 % ± 7 | 12 % ± 7 | 209 ± 31 | 209 ± 31 | 10.2 ± 2.7 | 1 % ± 1 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: known-answer issues at 5 %, no appeal | 7.6 ± 0.4 | 21.2 % ± 1.4 | 95 % ± 7 | 41 ± 1 | 24 % ± 3 | 79 % ± 3 | 20 % ± 3 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 10 % ± 3 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: known-answer issues at 10 %, no appeal | 5.6 ± 0.3 | 13.0 % ± 0.6 | 100 % ± 0 | 25 ± 1 | 61 % ± 2 | 47 % ± 2 | 52 % ± 1 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 10 % ± 2 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: known-answer issues at 20 %, no appeal | 5.0 ± 0.3 | 10.9 % ± 0.4 | 100 % ± 0 | 17 ± 0 | 81 % ± 1 | 32 % ± 1 | 68 % ± 1 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 11 % ± 2 |
| bad = the tests fail them: Opus 5.5 joins GPT-6.1's network: **known-answer issues at 5 %, the newcomer sponsors, six shadows** | 6.5 ± 0.4 | 14.3 % ± 0.8 | 100 % ± 0 | 35 ± 2 | 34 % ± 6 | 72 % ± 5 | 29 % ± 5 | 59 ± 11 | 59 ± 11 | 0.1 ± 0.1 | 6 % ± 2 |
| bad = the tests fail them: Mistral Large 3 joins Opus 5.5's network: it sponsors every fix its model passed; six shadows; bad-fix evidence accepted 5 % | 5.0 ± 0.4 | 5.9 % ± 0.4 | 0 % ± 0 | n/a | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 128 ± 24 | 128 ± 24 | 2.8 ± 0.7 | 0 % ± 0 |
| bad = the tests fail them: Mistral Large 3 joins Opus 5.5's network: it sponsors every fix its model passed; six shadows; bad-fix evidence accepted 20 % | 6.5 ± 0.4 | 5.9 % ± 0.4 | 0 % ± 0 | n/a | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 128 ± 23 | 128 ± 23 | 10.3 ± 2.2 | 0 % ± 0 |
| bad = the tests fail them: Mistral Large 3 joins Opus 5.5's network: it sponsors every fix its model passed; six shadows; bad-fix evidence accepted 50 % | 9.5 ± 0.6 | 6.0 % ± 0.4 | 0 % ± 0 | n/a | 0 % ± 0 | 0 % ± 1 | 100 % ± 1 | 129 ± 23 | 129 ± 23 | 25.8 ± 5.1 | 0 % ± 0 |
| bad = the tests fail them: Mistral Large 3 joins Opus 5.5's network: known-answer issues at 5 %; it sponsors; six shadows; bad-fix evidence accepted 50 % | 9.5 ± 0.6 | 5.9 % ± 0.4 | 0 % ± 0 | n/a | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 128 ± 23 | 128 ± 23 | 25.8 ± 5.0 | 0 % ± 1 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: no appeal (10.1) | 7.4 ± 0.4 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: no appeal, six contender shadows a draw (10.1) | 7.4 ± 0.4 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: appeal on evidence, solvers appeal their good fixes, no sponsor | 6.2 ± 0.3 | 17.1 % ± 0.6 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 131 ± 23 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: appeal on evidence, solvers appeal their good fixes, no sponsor; six shadows | 6.3 ± 0.4 | 17.0 % ± 0.6 | 12 % ± 11 | 32 ± 14 | 0 % ± 0 | 99 % ± 3 | 0 % ± 0 | 127 ± 22 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: solvers never appeal; **the newcomer sponsors the fixes its model passed** | 6.7 ± 0.3 | 20.1 % ± 0.6 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 142 ± 27 | 142 ± 27 | 0.8 ± 0.3 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: solvers never appeal; **the newcomer sponsors; six shadows** | 6.7 ± 0.3 | 20.1 % ± 0.6 | 8 % ± 8 | 30 ± 20 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 142 ± 27 | 142 ± 27 | 0.8 ± 0.3 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: the newcomer sponsors; six shadows; good-fix evidence accepted 25 % | 7.1 ± 0.4 | 25.4 % ± 0.6 | 0 % ± 0 | n/a | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 141 ± 27 | 141 ± 27 | 0.8 ± 0.3 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: the newcomer sponsors; six shadows; good-fix evidence accepted 100 % | 7.0 ± 0.4 | 9.4 % ± 0.5 | 75 % ± 14 | 28 ± 3 | 11 % ± 5 | 85 % ± 6 | 9 % ± 4 | 96 ± 16 | 96 ± 16 | 0.6 ± 0.2 | 2 % ± 1 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: every contender sponsors the fixes its model passed; six shadows | 7.0 ± 0.3 | 17.1 % ± 0.6 | 2 % ± 5 | 25 ± 0 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 244 ± 43 | 244 ± 43 | 3.0 ± 0.8 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: every contender sponsors; six shadows; bad-fix evidence accepted 20 % | 8.9 ± 0.4 | 17.1 % ± 0.6 | 8 % ± 8 | 38 ± 14 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 243 ± 43 | 243 ± 43 | 11.4 ± 2.4 | 0 % ± 0 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: known-answer issues at 5 %, no appeal | 8.2 ± 0.4 | 23.0 % ± 2.1 | 68 % ± 15 | 44 ± 2 | 11 % ± 4 | 89 % ± 5 | 10 % ± 3 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 2 % ± 2 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: known-answer issues at 10 %, no appeal | 9.0 ± 0.4 | 16.5 % ± 1.9 | 92 % ± 8 | 28 ± 2 | 43 % ± 7 | 79 % ± 7 | 36 % ± 6 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 3 % ± 2 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: known-answer issues at 20 %, no appeal | 8.8 ± 0.3 | 15.3 % ± 1.9 | 98 % ± 5 | 20 ± 3 | 60 % ± 8 | 80 % ± 6 | 50 % ± 7 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 3 % ± 3 |
| bad = pass the tests, wrong: Opus 5.5 joins GPT-6.1's network: **known-answer issues at 5 %, the newcomer sponsors, six shadows** | 7.9 ± 0.4 | 15.8 % ± 1.2 | 82 % ± 12 | 39 ± 3 | 14 % ± 4 | 88 % ± 5 | 12 % ± 4 | 107 ± 21 | 107 ± 21 | 0.6 ± 0.2 | 2 % ± 2 |
| bad = pass the tests, wrong: Mistral Large 3 joins Opus 5.5's network: it sponsors every fix its model passed; six shadows; bad-fix evidence accepted 5 % | 9.1 ± 0.5 | 10.1 % ± 1.3 | 0 % ± 0 | n/a | 0 % ± 0 | 30 % ± 8 | 68 % ± 8 | 135 ± 29 | 135 ± 29 | 2.2 ± 0.7 | 2 % ± 1 |
| bad = pass the tests, wrong: Mistral Large 3 joins Opus 5.5's network: it sponsors every fix its model passed; six shadows; bad-fix evidence accepted 20 % | 10.3 ± 0.5 | 10.3 % ± 1.3 | 0 % ± 0 | n/a | 0 % ± 0 | 33 % ± 8 | 65 % ± 8 | 135 ± 30 | 135 ± 30 | 8.1 ± 1.8 | 2 % ± 1 |
| bad = pass the tests, wrong: Mistral Large 3 joins Opus 5.5's network: it sponsors every fix its model passed; six shadows; bad-fix evidence accepted 50 % | 12.7 ± 0.7 | 10.4 % ± 1.4 | 0 % ± 0 | n/a | 0 % ± 0 | 33 % ± 9 | 66 % ± 8 | 132 ± 30 | 132 ± 30 | 18.4 ± 3.7 | 3 % ± 2 |
| bad = pass the tests, wrong: Mistral Large 3 joins Opus 5.5's network: known-answer issues at 5 %; it sponsors; six shadows; bad-fix evidence accepted 50 % | 12.5 ± 0.5 | 8.7 % ± 1.0 | 0 % ± 0 | n/a | 0 % ± 0 | 31 % ± 7 | 75 % ± 7 | 143 ± 23 | 143 ± 23 | 23.0 ± 3.6 | 3 % ± 3 |

### A contender that sponsors (its twin sponsors nothing)

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 5 %; reward 1,000 | -3,487 ± 84 | loses | -3,487 | 0 | 315 appeals sponsored, 15 upheld, 7 paid, 7 of them bad fixes; bad fixes paid in the network 57 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 20 %; reward 1,000 | -2,804 ± 72 | loses | -2,804 | 0 | 315 appeals sponsored, 60 upheld, 30 paid, 30 of them bad fixes; bad fixes paid in the network 79 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 50 %; reward 1,000 | -1,329 ± 72 | loses | -1,329 | 0 | 315 appeals sponsored, 154 upheld, 78 paid, 78 of them bad fixes; bad fixes paid in the network 127 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection, and solvers never appeal; reward 1,000 | -3,599 ± 90 | loses | -3,599 | 0 | 384 appeals sponsored, 48 upheld, 39 paid, 7 of them bad fixes; bad fixes paid in the network 57 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 1,000 | -1,247 ± 62 | loses | -1,247 | 0 | 132 appeals sponsored, 16 upheld, 13 paid, 3 of them bad fixes; bad fixes paid in the network 52 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 1,000 | -1,128 ± 55 | loses | -1,128 | 0 | 132 appeals sponsored, 22 upheld, 19 paid, 3 of them bad fixes; bad fixes paid in the network 52 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 1,000 | -2,850 ± 82 | loses | -2,850 | 0 | 315 appeals sponsored, 45 upheld, 37 paid, 6 of them bad fixes; bad fixes paid in the network 55 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 1,000 | -2,521 ± 85 | loses | -2,521 | 0 | 315 appeals sponsored, 62 upheld, 54 paid, 6 of them bad fixes; bad fixes paid in the network 55 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 5 %; reward 2,500 | -3,375 ± 88 | loses | -3,375 | 0 | 315 appeals sponsored, 15 upheld, 7 paid, 7 of them bad fixes; bad fixes paid in the network 57 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 20 %; reward 2,500 | -2,358 ± 86 | loses | -2,358 | 0 | 315 appeals sponsored, 60 upheld, 30 paid, 30 of them bad fixes; bad fixes paid in the network 79 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 50 %; reward 2,500 | -141 ± 120 | loses | -141 | 0 | 315 appeals sponsored, 154 upheld, 78 paid, 78 of them bad fixes; bad fixes paid in the network 127 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection, and solvers never appeal; reward 2,500 | -2,986 ± 108 | loses | -2,986 | 0 | 384 appeals sponsored, 48 upheld, 39 paid, 7 of them bad fixes; bad fixes paid in the network 57 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 2,500 | -1,036 ± 71 | loses | -1,036 | 0 | 132 appeals sponsored, 16 upheld, 13 paid, 3 of them bad fixes; bad fixes paid in the network 52 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 2,500 | -830 ± 62 | loses | -830 | 0 | 132 appeals sponsored, 22 upheld, 19 paid, 3 of them bad fixes; bad fixes paid in the network 52 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 2,500 | -2,263 ± 97 | loses | -2,263 | 0 | 315 appeals sponsored, 45 upheld, 37 paid, 6 of them bad fixes; bad fixes paid in the network 55 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 2,500 | -1,698 ± 111 | loses | -1,698 | 0 | 315 appeals sponsored, 62 upheld, 54 paid, 6 of them bad fixes; bad fixes paid in the network 55 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 1,000 | -671 ± 80 | loses | -671 | 0 | 293 appeals sponsored, 132 upheld, 126 paid, 0 of them bad fixes; bad fixes paid in the network 88 (twin's run: 92); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 1,000 | +423 ± 67 | **wins** | 423 | 0 | 195 appeals sponsored, 131 upheld, 125 paid, 0 of them bad fixes; bad fixes paid in the network 76 (twin's run: 92); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 2,500 | +1,257 ± 130 | **wins** | 1,257 | 0 | 293 appeals sponsored, 132 upheld, 126 paid, 0 of them bad fixes; bad fixes paid in the network 88 (twin's run: 92); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 2,500 | +2,340 ± 308 | **wins** | 2,340 | 0 | 195 appeals sponsored, 131 upheld, 125 paid, 0 of them bad fixes; bad fixes paid in the network 76 (twin's run: 92); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection; live scores, six shadows; bad-fix evidence accepted 20 %; reward 1,000 | -2,795 ± 74 | loses | -2,795 | 0 | 314 appeals sponsored, 60 upheld, 30 paid, 30 of them bad fixes; bad fixes paid in the network 79 (twin's run: 50); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection; live scores, six shadows, known-answer issues at 5 %; bad-fix evidence accepted 20 %; reward 1,000 | -2,804 ± 71 | loses | -2,804 | 0 | 315 appeals sponsored, 60 upheld, 30 paid, 30 of them bad fixes; bad fixes paid in the network 79 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection; live scores, six shadows; bad-fix evidence accepted 50 %; reward 1,000 | -1,306 ± 77 | loses | -1,306 | 0 | 312 appeals sponsored, 153 upheld, 77 paid, 77 of them bad fixes; bad fixes paid in the network 128 (twin's run: 50); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = the tests fail them: sponsors every rejection; live scores, six shadows, known-answer issues at 5 %; bad-fix evidence accepted 50 %; reward 1,000 | -1,318 ± 74 | loses | -1,318 | 0 | 313 appeals sponsored, 153 upheld, 77 paid, 77 of them bad fixes; bad fixes paid in the network 128 (twin's run: 49); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 5 %; reward 1,000 | -2,693 ± 74 | loses | -2,693 | 0 | 244 appeals sponsored, 12 upheld, 6 paid, 6 of them bad fixes; bad fixes paid in the network 104 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 20 %; reward 1,000 | -2,135 ± 60 | loses | -2,135 | 0 | 244 appeals sponsored, 48 upheld, 24 paid, 24 of them bad fixes; bad fixes paid in the network 123 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 50 %; reward 1,000 | -1,024 ± 59 | loses | -1,024 | 0 | 244 appeals sponsored, 120 upheld, 61 paid, 61 of them bad fixes; bad fixes paid in the network 159 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection, and solvers never appeal; reward 1,000 | -2,808 ± 78 | loses | -2,808 | 0 | 313 appeals sponsored, 45 upheld, 38 paid, 6 of them bad fixes; bad fixes paid in the network 104 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 1,000 | +0 ± 0 | not significant | 0 | 0 | 0 appeals sponsored, 0 upheld, 0 paid, 0 of them bad fixes; bad fixes paid in the network 98 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 1,000 | +0 ± 0 | not significant | 0 | 0 | 0 appeals sponsored, 0 upheld, 0 paid, 0 of them bad fixes; bad fixes paid in the network 98 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 1,000 | -1,845 ± 58 | loses | -1,845 | 0 | 227 appeals sponsored, 42 upheld, 36 paid, 4 of them bad fixes; bad fixes paid in the network 103 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 1,000 | -1,525 ± 59 | loses | -1,525 | 0 | 227 appeals sponsored, 58 upheld, 52 paid, 4 of them bad fixes; bad fixes paid in the network 103 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 5 %; reward 2,500 | -2,602 ± 75 | loses | -2,602 | 0 | 244 appeals sponsored, 12 upheld, 6 paid, 6 of them bad fixes; bad fixes paid in the network 104 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 20 %; reward 2,500 | -1,769 ± 64 | loses | -1,769 | 0 | 244 appeals sponsored, 48 upheld, 24 paid, 24 of them bad fixes; bad fixes paid in the network 123 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection the solver did not appeal; bad-fix evidence accepted 50 %; reward 2,500 | -101 ± 88 | loses | -101 | 0 | 244 appeals sponsored, 120 upheld, 61 paid, 61 of them bad fixes; bad fixes paid in the network 159 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection, and solvers never appeal; reward 2,500 | -2,213 ± 85 | loses | -2,213 | 0 | 313 appeals sponsored, 45 upheld, 38 paid, 6 of them bad fixes; bad fixes paid in the network 104 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 2,500 | +0 ± 0 | not significant | 0 | 0 | 0 appeals sponsored, 0 upheld, 0 paid, 0 of them bad fixes; bad fixes paid in the network 98 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running GPT-6.1 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 2,500 | +0 ± 0 | not significant | 0 | 0 | 0 appeals sponsored, 0 upheld, 0 paid, 0 of them bad fixes; bad fixes paid in the network 98 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 2,500 | -1,276 ± 69 | loses | -1,276 | 0 | 227 appeals sponsored, 42 upheld, 36 paid, 4 of them bad fixes; bad fixes paid in the network 103 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running DeepSeek V3.2 sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 2,500 | -726 ± 78 | loses | -726 | 0 | 227 appeals sponsored, 58 upheld, 52 paid, 4 of them bad fixes; bad fixes paid in the network 103 (twin's run: 98); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 1,000 | -1,601 ± 70 | loses | -1,601 | 0 | 402 appeals sponsored, 148 upheld, 139 paid, 2 of them bad fixes; bad fixes paid in the network 64 (twin's run: 61); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 1,000 | -137 ± 68 | loses | -137 | 0 | 389 appeals sponsored, 212 upheld, 201 paid, 2 of them bad fixes; bad fixes paid in the network 65 (twin's run: 61); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 50 %; reward 2,500 | +531 ± 116 | **wins** | 531 | 0 | 402 appeals sponsored, 148 upheld, 139 paid, 2 of them bad fixes; bad fixes paid in the network 64 (twin's run: 61); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted 75 %; reward 2,500 | +2,955 ± 143 | **wins** | 2,955 | 0 | 389 appeals sponsored, 212 upheld, 201 paid, 2 of them bad fixes; bad fixes paid in the network 65 (twin's run: 61); the four weak families seated 0 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection; live scores, six shadows; bad-fix evidence accepted 20 %; reward 1,000 | -2,139 ± 66 | loses | -2,139 | 0 | 269 appeals sponsored, 53 upheld, 27 paid, 27 of them bad fixes; bad fixes paid in the network 106 (twin's run: 80); the four weak families seated 1 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection; live scores, six shadows, known-answer issues at 5 %; bad-fix evidence accepted 20 %; reward 1,000 | -2,075 ± 73 | loses | -2,075 | 0 | 255 appeals sponsored, 50 upheld, 25 paid, 25 of them bad fixes; bad fixes paid in the network 114 (twin's run: 91); the four weak families seated 1 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection; live scores, six shadows; bad-fix evidence accepted 50 %; reward 1,000 | -976 ± 56 | loses | -976 | 0 | 278 appeals sponsored, 137 upheld, 69 paid, 69 of them bad fixes; bad fixes paid in the network 144 (twin's run: 80); the four weak families seated 1 % of the year, added (twin's run: 0 %) |
| bad = pass the tests, wrong: sponsors every rejection; live scores, six shadows, known-answer issues at 5 %; bad-fix evidence accepted 50 %; reward 1,000 | -948 ± 55 | loses | -948 | 0 | 261 appeals sponsored, 129 upheld, 65 paid, 65 of them bad fixes; bad fixes paid in the network 151 (twin's run: 91); the four weak families seated 0 % of the year, added (twin's run: 0 %) |

### Known-answer issues (D26), on live scores

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | the four others, their shares added | No family met the rule, share of the year | Runs in which Opus 5.5 was ever seated | Week it was first seated | Known-answer issues a year | Their checks, $ a year | …per submission |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: scores on every known answer (10.1's upper bound) | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | n/a | n/a | 0 ± 0 | $0 ± 0 | $0.000 ± 0.000 |
| bad = the tests fail them: genesis Opus 5.5; live scores, no known-answer issues | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 0 ± 0 | 0 ± 0 | $0 ± 0 | $0.000 ± 0.000 |
| bad = the tests fail them: genesis Opus 5.5; known-answer issues at 2 % | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 0 ± 0 | 31 ± 2 | $33 ± 2 | $0.021 ± 0.001 |
| bad = the tests fail them: genesis Opus 5.5; **known-answer issues at 5 %** | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 0 % ± 1 | 100 % ± 0 | 0 ± 0 | 76 ± 3 | $81 ± 3 | $0.052 ± 0.002 |
| bad = the tests fail them: genesis Opus 5.5; known-answer issues at 10 % | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 0 ± 0 | 152 ± 4 | $163 ± 5 | $0.105 ± 0.003 |
| bad = the tests fail them: genesis Opus 5.5; known-answer issues at 20 % | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 0 ± 0 | 304 ± 6 | $327 ± 7 | $0.211 ± 0.004 |
| bad = the tests fail them: genesis GPT-6.1; live scores, no known-answer issues | 10.5 ± 0.3 | 31.6 % ± 0.4 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | n/a | 0 ± 0 | $0 ± 0 | $0.000 ± 0.000 |
| bad = the tests fail them: genesis GPT-6.1; known-answer issues at 2 % | 10.5 ± 0.3 | 31.6 % ± 0.4 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | n/a | 31 ± 2 | $33 ± 2 | $0.021 ± 0.001 |
| bad = the tests fail them: genesis GPT-6.1; **known-answer issues at 5 %** | 8.2 ± 0.4 | 24.2 % ± 0.7 | 34 % ± 3 | 66 % ± 3 | 0 % ± 1 | 0 % ± 0 | 0 % ± 1 | 100 % ± 0 | 34 ± 2 | 76 ± 3 | $81 ± 3 | $0.052 ± 0.002 |
| bad = the tests fail them: genesis GPT-6.1; known-answer issues at 10 % | 6.3 ± 0.3 | 16.8 % ± 0.5 | 66 % ± 2 | 34 % ± 2 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 18 ± 1 | 152 ± 4 | $163 ± 5 | $0.105 ± 0.003 |
| bad = the tests fail them: genesis GPT-6.1; known-answer issues at 20 % | 5.4 ± 0.3 | 12.8 % ± 0.3 | 83 % ± 1 | 17 % ± 1 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 9 ± 0 | 304 ± 6 | $328 ± 7 | $0.211 ± 0.004 |
| bad = the tests fail them: genesis GPT-6.1; known-answer issues at 10 %, window 400, at least 100 | 8.2 ± 0.3 | 24.3 % ± 0.6 | 34 % ± 2 | 66 % ± 2 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 100 % ± 0 | 34 ± 1 | 152 ± 4 | $163 ± 5 | $0.105 ± 0.003 |
| bad = the tests fail them: genesis GPT-6.1; known-answer issues at 5 %, with the appeal on evidence | 7.1 ± 0.3 | 13.6 % ± 0.5 | 38 % ± 4 | 62 % ± 4 | 0 % ± 1 | 0 % ± 0 | 2 % ± 1 | 100 % ± 0 | 29 ± 2 | 76 ± 3 | $81 ± 3 | $0.052 ± 0.002 |
| bad = pass the tests, wrong: scores on every known answer (10.1's upper bound) | 8.5 ± 0.2 | 9.0 % ± 0.3 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | n/a | n/a | 0 ± 0 | $0 ± 0 | $0.000 ± 0.000 |
| bad = pass the tests, wrong: genesis Opus 5.5; live scores, no known-answer issues | 9.5 ± 0.3 | 11.3 % ± 1.5 | 87 % ± 7 | 11 % ± 7 | 2 % ± 2 | 0 % ± 0 | 3 % ± 1 | 100 % ± 0 | 0 ± 0 | 0 ± 0 | $0 ± 0 | $0.000 ± 0.000 |
| bad = pass the tests, wrong: genesis Opus 5.5; known-answer issues at 2 % | 9.5 ± 0.3 | 11.3 % ± 1.5 | 87 % ± 7 | 11 % ± 7 | 2 % ± 2 | 0 % ± 0 | 3 % ± 1 | 100 % ± 0 | 0 ± 0 | 31 ± 2 | $33 ± 2 | $0.021 ± 0.001 |
| bad = pass the tests, wrong: genesis Opus 5.5; **known-answer issues at 5 %** | 9.4 ± 0.3 | 11.4 % ± 1.0 | 83 % ± 6 | 23 % ± 6 | 18 % ± 5 | 0 % ± 0 | 4 % ± 3 | 100 % ± 0 | 0 ± 0 | 76 ± 3 | $81 ± 3 | $0.052 ± 0.002 |
| bad = pass the tests, wrong: genesis Opus 5.5; known-answer issues at 10 % | 9.2 ± 0.3 | 12.1 % ± 1.3 | 80 % ± 7 | 44 % ± 7 | 39 % ± 9 | 0 % ± 0 | 2 % ± 1 | 100 % ± 0 | 0 ± 0 | 152 ± 4 | $163 ± 5 | $0.105 ± 0.003 |
| bad = pass the tests, wrong: genesis Opus 5.5; known-answer issues at 20 % | 9.0 ± 0.3 | 12.6 % ± 1.6 | 80 % ± 7 | 64 % ± 7 | 51 % ± 9 | 0 % ± 0 | 2 % ± 3 | 100 % ± 0 | 0 ± 0 | 304 ± 6 | $327 ± 7 | $0.211 ± 0.004 |
| bad = pass the tests, wrong: genesis GPT-6.1; live scores, no known-answer issues | 7.2 ± 0.3 | 31.6 % ± 0.4 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | n/a | 0 ± 0 | $0 ± 0 | $0.000 ± 0.000 |
| bad = pass the tests, wrong: genesis GPT-6.1; known-answer issues at 2 % | 7.2 ± 0.3 | 31.6 % ± 0.4 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | n/a | 31 ± 2 | $33 ± 2 | $0.021 ± 0.001 |
| bad = pass the tests, wrong: genesis GPT-6.1; **known-answer issues at 5 %** | 7.8 ± 0.3 | 26.7 % ± 1.1 | 20 % ± 5 | 87 % ± 5 | 17 % ± 5 | 0 % ± 0 | 2 % ± 3 | 80 % ± 13 | 37 ± 2 | 76 ± 3 | $81 ± 3 | $0.052 ± 0.002 |
| bad = pass the tests, wrong: genesis GPT-6.1; known-answer issues at 10 % | 8.3 ± 0.3 | 20.9 % ± 1.6 | 46 % ± 7 | 78 % ± 7 | 39 % ± 9 | 0 % ± 0 | 1 % ± 1 | 88 % ± 11 | 20 ± 1 | 152 ± 4 | $163 ± 5 | $0.105 ± 0.003 |
| bad = pass the tests, wrong: genesis GPT-6.1; known-answer issues at 20 % | 8.4 ± 0.3 | 18.4 % ± 1.8 | 62 % ± 8 | 82 % ± 6 | 51 % ± 9 | 0 % ± 0 | 2 % ± 3 | 98 % ± 5 | 12 ± 2 | 304 ± 6 | $327 ± 7 | $0.211 ± 0.004 |
| bad = pass the tests, wrong: genesis GPT-6.1; known-answer issues at 10 %, window 400, at least 100 | 7.8 ± 0.3 | 26.4 % ± 0.9 | 25 % ± 4 | 90 % ± 5 | 20 % ± 5 | 0 % ± 0 | 0 % ± 1 | 88 % ± 11 | 35 ± 1 | 152 ± 4 | $163 ± 5 | $0.105 ± 0.003 |
| bad = pass the tests, wrong: genesis GPT-6.1; known-answer issues at 5 %, with the appeal on evidence | 6.9 ± 0.3 | 15.3 % ± 0.6 | 20 % ± 5 | 87 % ± 5 | 17 % ± 5 | 0 % ± 0 | 2 % ± 3 | 80 % ± 13 | 37 ± 3 | 76 ± 3 | $81 ± 3 | $0.052 ± 0.002 |

### The second panel (D27), with second-opinion challenges

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Submissions that waited | Challenges a year | …judged by a second draw | Verdicts never final |
|---|---|---|---|---|---|---|---|
| bad = the tests fail them: v3 as designed; D4: a larger fresh panel, or the challenge waits | 8.8 ± 1.2 | 24.7 % ± 2.3 | $1.31 ± 0.09 | 79.6 % ± 1.5 | 81 ± 10 | 0 ± 0 | 23.6 % ± 2.5 |
| bad = the tests fail them: v3 as designed; **a second draw while fewer than three families can judge** | 10.2 ± 1.3 | 14.7 % ± 2.2 | $1.32 ± 0.10 | 79.4 % ± 1.6 | 79 ± 12 | 78 ± 12 | 0.1 % ± 0.2 |
| bad = the tests fail them: v3 as designed; a second draw whenever the larger panel cannot be drawn | 10.2 ± 1.3 | 14.6 % ± 2.2 | $1.33 ± 0.10 | 79.4 % ± 1.6 | 79 ± 12 | 78 ± 12 | 0.1 % ± 0.2 |
| bad = the tests fail them: seats by rank, `SEAT_MARGIN` 5; D4 | 4.5 ± 0.2 | 10.0 % ± 0.3 | $4.23 ± 0.09 | 0.1 % ± 0.0 | 40 ± 2 | 0 ± 0 | 2.7 % ± 0.2 |
| bad = the tests fail them: seats by rank, `SEAT_MARGIN` 5; **a second draw while fewer than three families can judge** | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 40 ± 2 | 40 ± 2 | 0.0 % ± 0.0 |
| bad = the tests fail them: seats by rank, `SEAT_MARGIN` 5; a second draw whenever the larger panel cannot be drawn | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 40 ± 2 | 40 ± 2 | 0.0 % ± 0.0 |
| bad = the tests fail them: seats by rank, `SEAT_MARGIN` 1; D4 | 4.5 ± 0.2 | 10.0 % ± 0.3 | $4.23 ± 0.09 | 0.1 % ± 0.0 | 40 ± 2 | 0 ± 0 | 2.7 % ± 0.2 |
| bad = the tests fail them: seats by rank, `SEAT_MARGIN` 1; a second draw while fewer than three families can judge | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 40 ± 2 | 40 ± 2 | 0.0 % ± 0.0 |
| bad = pass the tests, wrong: v3 as designed; D4: a larger fresh panel, or the challenge waits | 9.7 ± 0.6 | 26.1 % ± 2.0 | $1.31 ± 0.07 | 76.2 % ± 2.2 | 85 ± 7 | 0 ± 0 | 23.0 % ± 2.4 |
| bad = pass the tests, wrong: v3 as designed; **a second draw while fewer than three families can judge** | 11.3 ± 0.8 | 18.2 % ± 2.0 | $1.30 ± 0.07 | 76.1 % ± 2.2 | 88 ± 8 | 87 ± 8 | 0.0 % ± 0.0 |
| bad = pass the tests, wrong: v3 as designed; a second draw whenever the larger panel cannot be drawn | 11.3 ± 0.8 | 18.1 % ± 2.0 | $1.30 ± 0.07 | 76.4 % ± 2.1 | 88 ± 8 | 87 ± 8 | 0.0 % ± 0.0 |
| bad = pass the tests, wrong: seats by rank, `SEAT_MARGIN` 5; D4 | 8.5 ± 0.2 | 9.1 % ± 0.3 | $3.98 ± 0.09 | 0.0 % ± 0.0 | 34 ± 2 | 0 ± 0 | 0.3 % ± 0.1 |
| bad = pass the tests, wrong: seats by rank, `SEAT_MARGIN` 5; **a second draw while fewer than three families can judge** | 8.5 ± 0.2 | 9.1 % ± 0.3 | $3.98 ± 0.09 | 0.0 % ± 0.0 | 34 ± 2 | 0 ± 0 | 0.3 % ± 0.1 |
| bad = pass the tests, wrong: seats by rank, `SEAT_MARGIN` 5; a second draw whenever the larger panel cannot be drawn | 8.5 ± 0.2 | 8.9 % ± 0.3 | $3.88 ± 0.08 | 0.0 % ± 0.0 | 33 ± 2 | 15 ± 2 | 0.0 % ± 0.0 |
| bad = pass the tests, wrong: seats by rank, `SEAT_MARGIN` 1; D4 | 9.0 ± 0.3 | 17.3 % ± 1.0 | $6.15 ± 0.24 | 0.0 % ± 0.0 | 47 ± 3 | 0 ± 0 | 2.4 % ± 0.3 |
| bad = pass the tests, wrong: seats by rank, `SEAT_MARGIN` 1; a second draw while fewer than three families can judge | 9.2 ± 0.3 | 15.7 % ± 0.9 | $5.68 ± 0.21 | 0.0 % ± 0.0 | 47 ± 3 | 44 ± 3 | 0.0 % ± 0.0 |

### Rival solvers as disputers (D21: anyone may dispute a pass)

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Bad fixes paid a year | Passes reversed by a test, a year | …of which a rival solver's test | Issues reopened by a test, a year |
|---|---|---|---|---|---|---|---|
| bad = the tests fail them: no test disputes at all | 6.0 ± 0.2 | 6.0 % ± 0.2 | $1.64 ± 0.03 | 69 ± 3 | 0 ± 0 | 0 ± 0 | 0 ± 0 |
| bad = the tests fail them: contenders only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $1.64 ± 0.03 | 49 ± 2 | 54 ± 2 | 0 ± 0 | 20 ± 1 |
| bad = the tests fail them: contenders and 1 rival solver, each finding a test 10 % of the time | 4.0 ± 0.2 | 8.9 % ± 0.2 | $1.64 ± 0.03 | 44 ± 2 | 59 ± 2 | 5 ± 1 | 25 ± 1 |
| bad = the tests fail them: contenders and 3 rival solvers, each finding a test 10 % of the time | 3.3 ± 0.2 | 8.9 % ± 0.2 | $1.63 ± 0.03 | 36 ± 2 | 67 ± 3 | 13 ± 1 | 33 ± 2 |
| bad = the tests fail them: contenders and 10 rival solvers, each finding a test 10 % of the time | 1.7 ± 0.1 | 8.9 % ± 0.2 | $1.63 ± 0.03 | 18 ± 1 | 85 ± 3 | 31 ± 2 | 51 ± 2 |
| bad = the tests fail them: contenders and 1 rival solver, each finding a test 25 % of the time | 3.4 ± 0.2 | 8.9 % ± 0.2 | $1.64 ± 0.03 | 37 ± 2 | 66 ± 2 | 12 ± 1 | 32 ± 2 |
| bad = the tests fail them: contenders and 3 rival solvers, each finding a test 25 % of the time | 2.0 ± 0.1 | 8.9 % ± 0.2 | $1.63 ± 0.03 | 21 ± 1 | 82 ± 3 | 28 ± 2 | 48 ± 2 |
| bad = the tests fail them: contenders and 10 rival solvers, each finding a test 25 % of the time | 0.3 ± 0.1 | 8.9 % ± 0.2 | $1.63 ± 0.03 | 3 ± 1 | 100 ± 3 | 46 ± 2 | 66 ± 3 |
| bad = the tests fail them: contenders and 1 rival solver, each finding a test 50 % of the time | 2.3 ± 0.1 | 8.9 % ± 0.2 | $1.64 ± 0.03 | 25 ± 2 | 78 ± 3 | 24 ± 2 | 44 ± 2 |
| bad = the tests fail them: contenders and 3 rival solvers, each finding a test 50 % of the time | 0.6 ± 0.1 | 8.9 % ± 0.2 | $1.63 ± 0.03 | 6 ± 1 | 97 ± 3 | 43 ± 3 | 63 ± 3 |
| bad = the tests fail them: contenders and 10 rival solvers, each finding a test 50 % of the time | 0.0 ± 0.0 | 8.9 % ± 0.2 | $1.63 ± 0.03 | 0 ± 0 | 103 ± 3 | 49 ± 3 | 69 ± 3 |
| bad = the tests fail them: no contenders; 1 rival solver, each finding a test 25 % of the time | 4.6 ± 0.2 | 6.0 % ± 0.2 | $1.64 ± 0.03 | 52 ± 3 | 18 ± 1 | 18 ± 1 | 18 ± 1 |
| bad = the tests fail them: no contenders; 3 rival solvers, each finding a test 25 % of the time | 2.7 ± 0.2 | 6.0 % ± 0.2 | $1.64 ± 0.03 | 30 ± 2 | 40 ± 2 | 40 ± 2 | 40 ± 2 |
| bad = the tests fail them: no contenders; 10 rival solvers, each finding a test 25 % of the time | 0.4 ± 0.1 | 6.0 % ± 0.2 | $1.63 ± 0.03 | 4 ± 1 | 65 ± 3 | 65 ± 3 | 65 ± 3 |
| bad = pass the tests, wrong: no test disputes at all | 11.7 ± 0.3 | 6.1 % ± 0.2 | $1.60 ± 0.00 | 144 ± 4 | 0 ± 0 | 0 ± 0 | 0 ± 0 |
| bad = pass the tests, wrong: contenders only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 98 ± 3 | 80 ± 4 | 0 ± 0 | 46 ± 3 |
| bad = pass the tests, wrong: contenders and 1 rival solver, each finding a test 10 % of the time | 7.7 ± 0.2 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 88 ± 3 | 91 ± 4 | 11 ± 1 | 57 ± 3 |
| bad = pass the tests, wrong: contenders and 3 rival solvers, each finding a test 10 % of the time | 6.2 ± 0.2 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 70 ± 2 | 108 ± 4 | 28 ± 2 | 74 ± 3 |
| bad = pass the tests, wrong: contenders and 10 rival solvers, each finding a test 10 % of the time | 3.1 ± 0.1 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 34 ± 2 | 145 ± 4 | 64 ± 3 | 111 ± 3 |
| bad = pass the tests, wrong: contenders and 1 rival solver, each finding a test 25 % of the time | 6.4 ± 0.2 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 72 ± 2 | 107 ± 4 | 27 ± 2 | 73 ± 3 |
| bad = pass the tests, wrong: contenders and 3 rival solvers, each finding a test 25 % of the time | 3.6 ± 0.2 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 39 ± 2 | 139 ± 4 | 59 ± 3 | 105 ± 4 |
| bad = pass the tests, wrong: contenders and 10 rival solvers, each finding a test 25 % of the time | 0.5 ± 0.1 | 9.1 % ± 0.3 | $1.60 ± 0.00 | 6 ± 1 | 173 ± 5 | 93 ± 3 | 139 ± 4 |
| bad = pass the tests, wrong: contenders and 1 rival solver, each finding a test 50 % of the time | 4.3 ± 0.1 | 9.0 % ± 0.3 | $1.60 ± 0.00 | 47 ± 2 | 131 ± 4 | 51 ± 2 | 97 ± 4 |
| bad = pass the tests, wrong: contenders and 3 rival solvers, each finding a test 50 % of the time | 1.1 ± 0.1 | 9.1 % ± 0.3 | $1.60 ± 0.00 | 11 ± 1 | 167 ± 5 | 87 ± 3 | 133 ± 4 |
| bad = pass the tests, wrong: contenders and 10 rival solvers, each finding a test 50 % of the time | 0.0 ± 0.0 | 9.1 % ± 0.3 | $1.60 ± 0.00 | 0 ± 0 | 179 ± 5 | 98 ± 3 | 145 ± 4 |
| bad = pass the tests, wrong: no contenders; 1 rival solver, each finding a test 25 % of the time | 8.9 ± 0.2 | 6.1 % ± 0.2 | $1.60 ± 0.00 | 107 ± 3 | 38 ± 2 | 38 ± 2 | 38 ± 2 |
| bad = pass the tests, wrong: no contenders; 3 rival solvers, each finding a test 25 % of the time | 5.1 ± 0.2 | 6.1 % ± 0.2 | $1.60 ± 0.00 | 59 ± 3 | 86 ± 3 | 86 ± 3 | 86 ± 3 |
| bad = pass the tests, wrong: no contenders; 10 rival solvers, each finding a test 25 % of the time | 0.8 ± 0.1 | 6.1 % ± 0.2 | $1.60 ± 0.00 | 8 ± 1 | 136 ± 4 | 136 ± 4 | 136 ± 4 |

### No solver's deposit: the solver of bad fixes against rival solvers' disputes

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: no deposit; contenders and 0 rival solvers | +2,741 ± 204 | **wins** | 2,741 | 0 | 32 bad fixes paid of 261 submitted (12 %); $+10.50 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 1 rival solver at 25 % | +1,902 ± 179 | **wins** | 1,902 | 0 | 23 bad fixes paid of 261 submitted (9 %); $+7.29 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 3 rival solvers at 10 % | +1,870 ± 188 | **wins** | 1,870 | 0 | 23 bad fixes paid of 261 submitted (9 %); $+7.16 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 3 rival solvers at 25 % | +891 ± 159 | **wins** | 891 | 0 | 13 bad fixes paid of 261 submitted (5 %); $+3.41 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 3 rival solvers at 50 % | -27 ± 83 | not significant | -27 | 0 | 4 bad fixes paid of 261 submitted (1 %); $-0.11 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 10 rival solvers at 10 % | +707 ± 122 | **wins** | 707 | 0 | 11 bad fixes paid of 261 submitted (4 %); $+2.71 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 10 rival solvers at 25 % | -265 ± 43 | loses | -265 | 0 | 2 bad fixes paid of 261 submitted (1 %); $-1.02 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; contenders and 10 rival solvers at 50 % | -420 ± 15 | loses | -420 | 0 | 0 bad fixes paid of 261 submitted (0 %); $-1.61 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; no test disputes at all | +4,229 ± 238 | **wins** | 4,229 | 0 | 46 bad fixes paid of 261 submitted (18 %); $+16.20 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; GPT-6.1 alone seated; contenders and 0 rival solvers | +5,768 ± 278 | **wins** | 5,768 | 0 | 62 bad fixes paid of 261 submitted (24 %); $+22.09 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; GPT-6.1 alone seated; contenders and 3 rival solvers at 25 % | +2,237 ± 180 | **wins** | 2,237 | 0 | 27 bad fixes paid of 261 submitted (10 %); $+8.57 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; GPT-6.1 alone seated; contenders and 10 rival solvers at 25 % | -62 ± 79 | not significant | -62 | 0 | 4 bad fixes paid of 261 submitted (1 %); $-0.24 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; GPT-6.1 alone seated; contenders and 10 rival solvers at 50 % | -395 ± 13 | loses | -395 | 0 | 0 bad fixes paid of 261 submitted (0 %); $-1.51 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; it tries each issue up to 21 times; contenders and 0 rival solvers | +19,833 ± 700 | **wins** | 19,833 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $+10.93 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; it tries each issue up to 21 times; contenders and 10 rival solvers at 25 % | -4,352 ± 333 | loses | -4,352 | 0 | 32 bad fixes paid of 4547 submitted (1 %); $-0.96 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: no deposit; it tries each issue up to 21 times; contenders and 10 rival solvers at 50 % | -8,032 ± 364 | loses | -8,032 | 0 | 0 bad fixes paid of 4868 submitted (0 %); $-1.65 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: for comparison: deposit 2,500; contenders and 0 rival solvers | -2,976 ± 262 | loses | -2,976 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-11.40 a fix submitted; $5,718 of deposits lost |
| bad = the tests fail them: for comparison: deposit 4,000; contenders and 0 rival solvers | -6,407 ± 337 | loses | -6,407 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-24.54 a fix submitted; $9,148 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 0 rival solvers | +6,126 ± 370 | **wins** | 6,126 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+23.46 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 1 rival solver at 25 % | +4,466 ± 336 | **wins** | 4,466 | 0 | 48 bad fixes paid of 261 submitted (19 %); $+17.11 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 3 rival solvers at 10 % | +4,484 ± 330 | **wins** | 4,484 | 0 | 48 bad fixes paid of 261 submitted (19 %); $+17.17 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 3 rival solvers at 25 % | +2,433 ± 251 | **wins** | 2,433 | 0 | 28 bad fixes paid of 261 submitted (11 %); $+9.32 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 3 rival solvers at 50 % | +418 ± 102 | **wins** | 418 | 0 | 8 bad fixes paid of 261 submitted (3 %); $+1.60 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 10 rival solvers at 10 % | +1,896 ± 213 | **wins** | 1,896 | 0 | 22 bad fixes paid of 261 submitted (9 %); $+7.26 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 10 rival solvers at 25 % | -77 ± 68 | loses | -77 | 0 | 4 bad fixes paid of 261 submitted (1 %); $-0.30 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; contenders and 10 rival solvers at 50 % | -410 ± 11 | loses | -410 | 0 | 0 bad fixes paid of 261 submitted (0 %); $-1.57 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; no test disputes at all | +9,317 ± 403 | **wins** | 9,317 | 0 | 96 bad fixes paid of 261 submitted (37 %); $+35.69 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; GPT-6.1 alone seated; contenders and 0 rival solvers | +3,779 ± 270 | **wins** | 3,779 | 0 | 42 bad fixes paid of 261 submitted (16 %); $+14.47 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; GPT-6.1 alone seated; contenders and 3 rival solvers at 25 % | +1,451 ± 172 | **wins** | 1,451 | 0 | 18 bad fixes paid of 261 submitted (7 %); $+5.56 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; GPT-6.1 alone seated; contenders and 10 rival solvers at 25 % | -195 ± 53 | loses | -195 | 0 | 2 bad fixes paid of 261 submitted (1 %); $-0.75 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; GPT-6.1 alone seated; contenders and 10 rival solvers at 50 % | -395 ± 11 | loses | -395 | 0 | 0 bad fixes paid of 261 submitted (0 %); $-1.51 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; it tries each issue up to 21 times; contenders and 0 rival solvers | +24,082 ± 685 | **wins** | 24,082 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $+23.32 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; it tries each issue up to 21 times; contenders and 10 rival solvers at 25 % | -764 ± 309 | loses | -764 | 0 | 63 bad fixes paid of 4525 submitted (1 %); $-0.17 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: no deposit; it tries each issue up to 21 times; contenders and 10 rival solvers at 50 % | -7,978 ± 182 | loses | -7,978 | 0 | 1 bad fixes paid of 5185 submitted (0 %); $-1.54 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: for comparison: deposit 2,500; contenders and 0 rival solvers | +1,191 ± 369 | **wins** | 1,191 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+4.56 a fix submitted; $4,935 of deposits lost |
| bad = pass the tests, wrong: for comparison: deposit 4,000; contenders and 0 rival solvers | -1,769 ± 394 | loses | -1,769 | 0 | 65 bad fixes paid of 261 submitted (25 %); $-6.78 a fix submitted; $7,895 of deposits lost |

### Task 10.1's network beside the revision

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | …of which appeal stakes lost | Fixes paid a year | Verdicts never final | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | the four others, their shares added | Appeals a year | …sponsored | Bad fixes paid after an appeal, a year | Wrongly rejected good fixes paid in the end | Known-answer checks, $ a year | Service fee, last 13 weeks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: 10.1: seats by rank, disputes, no appeal, deposit 2,500; scores on every known answer | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | $0.00 ± 0.00 | 1097 ± 10 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 | $0 ± 0 | $0.010 ± 0.000 |
| bad = the tests fail them: 10.1: the same on live scores | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | $0.00 ± 0.00 | 1097 ± 10 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 | $0 ± 0 | $0.010 ± 0.000 |
| bad = the tests fail them: 10.1 on live scores, no deposit | 4.5 ± 0.2 | 8.9 % ± 0.2 | $1.64 ± 0.03 | $0.00 ± 0.00 | $0.00 ± 0.00 | 1097 ± 10 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 | $0 ± 0 | $0.010 ± 0.000 |
| bad = the tests fail them: **the revision, no deposit**: appeal on evidence, sponsors, known-answer issues at 5 %, the second draw; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 % | 4.9 ± 0.2 | 6.1 % ± 0.2 | $2.00 ± 0.04 | $0.00 ± 0.00 | $0.29 ± 0.02 | 1136 ± 11 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 359 ± 7 | 291 ± 6 | 6.8 ± 0.9 | 46 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 20 % | 6.7 ± 0.3 | 6.2 % ± 0.3 | $2.00 ± 0.04 | $0.00 ± 0.00 | $0.30 ± 0.03 | 1156 ± 11 | 0.0 % ± 0.0 | 99 % ± 2 | 1 % ± 2 | 0 % ± 1 | 0 % ± 0 | 361 ± 7 | 290 ± 7 | 27.3 ± 2.1 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision, no deposit; good-fix evidence accepted 25 %, bad-fix evidence accepted 5 % | 5.0 ± 0.2 | 7.5 % ± 0.2 | $2.15 ± 0.04 | $0.00 ± 0.00 | $0.45 ± 0.03 | 1121 ± 11 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 359 ± 7 | 291 ± 6 | 6.8 ± 0.9 | 24 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; honest solvers appeal every rejection | 5.0 ± 0.2 | 6.1 % ± 0.2 | $2.00 ± 0.04 | $0.00 ± 0.00 | $0.29 ± 0.02 | 1137 ± 10 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 382 ± 7 | 0 ± 0 | 7.5 ± 1.0 | 46 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; 10 rival solvers, each finding a test 25 % of the time | 0.3 ± 0.0 | 6.1 % ± 0.2 | $1.99 ± 0.04 | $0.00 ± 0.00 | $0.29 ± 0.02 | 1083 ± 10 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 359 ± 7 | 291 ± 6 | 0.5 ± 0.2 | 46 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; with second-opinion challenges | 4.9 ± 0.2 | 6.2 % ± 0.2 | $2.00 ± 0.04 | $0.00 ± 0.00 | $0.29 ± 0.02 | 1135 ± 11 | 0.1 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 359 ± 7 | 290 ± 6 | 6.5 ± 0.9 | 45 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; deposit 2,500 (`D236R2`) | 4.9 ± 0.2 | 6.1 % ± 0.2 | $3.55 ± 0.08 | $1.56 ± 0.06 | $0.29 ± 0.02 | 1136 ± 11 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 359 ± 7 | 291 ± 6 | 6.8 ± 0.9 | 46 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = the tests fail them: the revision; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; deposit 4,000 | 4.9 ± 0.2 | 6.1 % ± 0.2 | $4.49 ± 0.11 | $2.49 ± 0.09 | $0.29 ± 0.02 | 1136 ± 11 | 0.0 % ± 0.0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 1 | 0 % ± 0 | 359 ± 7 | 291 ± 6 | 6.8 ± 0.9 | 46 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: 10.1: seats by rank, disputes, no appeal, deposit 2,500; scores on every known answer | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | $0.00 ± 0.00 | 1155 ± 11 | 0.2 % ± 0.1 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 | $0 ± 0 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: 10.1: the same on live scores | 9.5 ± 0.3 | 11.3 % ± 1.5 | $4.45 ± 0.31 | $2.87 ± 0.35 | $0.00 ± 0.00 | 1128 ± 24 | 0.0 % ± 0.0 | 87 % ± 7 | 11 % ± 7 | 2 % ± 2 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 | $0 ± 0 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: 10.1 on live scores, no deposit | 9.5 ± 0.3 | 11.3 % ± 1.5 | $1.57 ± 0.05 | $0.00 ± 0.00 | $0.00 ± 0.00 | 1128 ± 24 | 0.0 % ± 0.0 | 87 % ± 7 | 11 % ± 7 | 2 % ± 2 | 0 % ± 0 | 0 ± 0 | 0 ± 0 | 0.0 ± 0.0 | 0 % ± 0 | $0 ± 0 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: **the revision, no deposit**: appeal on evidence, sponsors, known-answer issues at 5 %, the second draw; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 % | 9.3 ± 0.3 | 7.6 % ± 0.7 | $2.06 ± 0.06 | $0.00 ± 0.00 | $0.44 ± 0.07 | 1177 ± 16 | 0.0 % ± 0.0 | 81 % ± 6 | 26 % ± 7 | 18 % ± 5 | 0 % ± 0 | 311 ± 23 | 207 ± 8 | 5.0 ± 0.8 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 20 % | 10.5 ± 0.3 | 7.6 % ± 0.7 | $2.04 ± 0.06 | $0.00 ± 0.00 | $0.45 ± 0.07 | 1192 ± 15 | 0.0 % ± 0.0 | 79 % ± 6 | 27 % ± 7 | 19 % ± 5 | 0 % ± 0 | 313 ± 23 | 207 ± 8 | 20.6 ± 1.6 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision, no deposit; good-fix evidence accepted 25 %, bad-fix evidence accepted 5 % | 9.5 ± 0.3 | 9.8 % ± 1.1 | $2.30 ± 0.08 | $0.00 ± 0.00 | $0.68 ± 0.10 | 1151 ± 19 | 0.0 % ± 0.0 | 81 % ± 6 | 26 % ± 7 | 17 % ± 5 | 0 % ± 0 | 314 ± 23 | 207 ± 8 | 5.1 ± 0.8 | 24 % ± 1 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; honest solvers appeal every rejection | 9.4 ± 0.3 | 7.6 % ± 0.7 | $2.06 ± 0.06 | $0.00 ± 0.00 | $0.44 ± 0.07 | 1178 ± 16 | 0.0 % ± 0.0 | 81 % ± 6 | 26 % ± 7 | 18 % ± 5 | 0 % ± 0 | 330 ± 23 | 0 ± 0 | 5.5 ± 0.7 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; 10 rival solvers, each finding a test 25 % of the time | 0.6 ± 0.1 | 8.8 % ± 0.8 | $2.09 ± 0.07 | $0.00 ± 0.00 | $0.56 ± 0.08 | 1055 ± 15 | 0.0 % ± 0.0 | 68 % ± 5 | 36 % ± 7 | 20 % ± 5 | 0 % ± 0 | 346 ± 24 | 216 ± 8 | 0.4 ± 0.2 | 47 % ± 1 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision, no deposit; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; with second-opinion challenges | 9.5 ± 0.3 | 7.7 % ± 0.8 | $2.05 ± 0.05 | $0.00 ± 0.00 | $0.44 ± 0.07 | 1177 ± 16 | 0.0 % ± 0.0 | 81 % ± 6 | 26 % ± 7 | 18 % ± 5 | 0 % ± 0 | 308 ± 22 | 206 ± 8 | 4.9 ± 0.8 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; deposit 2,500 (`D236R2`) | 9.3 ± 0.3 | 7.6 % ± 0.7 | $3.97 ± 0.23 | $1.91 ± 0.18 | $0.44 ± 0.07 | 1177 ± 16 | 0.0 % ± 0.0 | 81 % ± 6 | 26 % ± 7 | 18 % ± 5 | 0 % ± 0 | 311 ± 23 | 207 ± 8 | 5.0 ± 0.8 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: the revision; good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; deposit 4,000 | 9.3 ± 0.3 | 7.6 % ± 0.7 | $5.11 ± 0.34 | $3.06 ± 0.29 | $0.44 ± 0.07 | 1177 ± 16 | 0.0 % ± 0.0 | 81 % ± 6 | 26 % ± 7 | 18 % ± 5 | 0 % ± 0 | 311 ± 23 | 207 ± 8 | 5.0 ± 0.8 | 47 % ± 2 | $81 ± 3 | $0.010 ± 0.000 |

### Code health across the solver's deposit, per 100 funded issues

| Network | The bad-fix solver's return ($ a year) | It stays? | Honest solvers that stay away (assumed) | Correctly fixed and paid, per 100 funded issues | Wrongly marked fixed | Left unfixed | Median days a wrong fix stands before reversal |
|---|---|---|---|---|---|---|---|
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 0 | +2,741 ± 204 | yes | 0 % | 57.8 | 4.5 | 37.8 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +454 ± 213 | yes | 0 % | 57.8 | 4.5 | 37.8 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +454 ± 213 | yes | 2 % | 56.3 | 4.4 | 39.3 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +454 ± 213 | yes | 5 % | 54.9 | 4.3 | 40.8 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +454 ± 213 | yes | 10 % | 52.0 | 4.2 | 43.8 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | -2,976 ± 262 | no (it has left) | 0 % | 57.8 | 2.7 | 39.5 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | -2,976 ± 262 | no (it has left) | 6 % | 54.2 | 2.5 | 43.3 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | -2,976 ± 262 | no (it has left) | 12 % | 50.6 | 2.4 | 47.1 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | -2,976 ± 262 | no (it has left) | 25 % | 43.3 | 2.0 | 54.6 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -6,407 ± 337 | no (it has left) | 0 % | 57.8 | 2.7 | 39.5 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -6,407 ± 337 | no (it has left) | 10 % | 52.0 | 2.4 | 45.5 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -6,407 ± 337 | no (it has left) | 20 % | 46.2 | 2.2 | 51.6 | 0.2 |
| bad = the tests fail them: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -6,407 ± 337 | no (it has left) | 40 % | 34.7 | 1.6 | 63.7 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 0 | +2,741 ± 204 | yes | 0 % | 59.5 | 4.9 | 35.6 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +469 ± 213 | yes | 0 % | 59.5 | 4.9 | 35.6 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +469 ± 213 | yes | 2 % | 58.1 | 4.8 | 37.2 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +469 ± 213 | yes | 5 % | 56.6 | 4.7 | 38.7 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +469 ± 213 | yes | 10 % | 53.6 | 4.6 | 41.9 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | -2,939 ± 262 | no (it has left) | 0 % | 59.6 | 3.1 | 37.3 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | -2,939 ± 262 | no (it has left) | 6 % | 55.9 | 2.9 | 41.2 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | -2,939 ± 262 | no (it has left) | 12 % | 52.1 | 2.7 | 45.1 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | -2,939 ± 262 | no (it has left) | 25 % | 44.7 | 2.3 | 53.0 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -6,347 ± 337 | no (it has left) | 0 % | 59.6 | 3.1 | 37.3 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -6,347 ± 337 | no (it has left) | 10 % | 53.6 | 2.8 | 43.6 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -6,347 ± 337 | no (it has left) | 20 % | 47.7 | 2.5 | 49.8 | 0.2 |
| bad = the tests fail them: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -6,347 ± 337 | no (it has left) | 40 % | 35.7 | 1.9 | 62.4 | 0.2 |
| bad = the tests fail them: no appeal, 3 rival solvers at 25 % (post hoc); `SOLVER_DEPOSIT_BPS` 0 | +891 ± 159 | yes | 0 % | 57.8 | 1.9 | 40.3 | 0.2 |
| bad = the tests fail them: no appeal, 10 rival solvers at 25 % (post hoc); `SOLVER_DEPOSIT_BPS` 0 | -265 ± 43 | no (it has left) | 0 % | 57.8 | 0.2 | 42.0 | 0.2 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 0 | +6,126 ± 370 | yes | 0 % | 58.3 | 9.0 | 32.7 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +4,152 ± 363 | yes | 0 % | 58.3 | 9.0 | 32.7 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +4,152 ± 363 | yes | 2 % | 56.8 | 8.9 | 34.3 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +4,152 ± 363 | yes | 5 % | 55.4 | 8.7 | 35.9 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 1,000 | +4,152 ± 363 | yes | 10 % | 52.5 | 8.4 | 39.1 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | +1,191 ± 369 | yes | 0 % | 58.3 | 9.0 | 32.7 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | +1,191 ± 369 | yes | 6 % | 54.7 | 8.6 | 36.7 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | +1,191 ± 369 | yes | 12 % | 51.0 | 8.3 | 40.7 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 2,500 | +1,191 ± 369 | yes | 25 % | 43.7 | 7.6 | 48.6 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -1,769 ± 394 | no (it has left) | 0 % | 58.3 | 5.4 | 36.3 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -1,769 ± 394 | no (it has left) | 10 % | 52.5 | 4.9 | 42.6 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -1,769 ± 394 | no (it has left) | 20 % | 46.6 | 4.3 | 49.0 | 0.1 |
| bad = pass the tests, wrong: no appeal; `SOLVER_DEPOSIT_BPS` 4,000 | -1,769 ± 394 | no (it has left) | 40 % | 35.0 | 3.3 | 61.8 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 0 | +6,126 ± 370 | yes | 0 % | 60.1 | 9.3 | 30.6 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +4,163 ± 363 | yes | 0 % | 60.1 | 9.3 | 30.6 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +4,163 ± 363 | yes | 2 % | 58.6 | 9.2 | 32.3 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +4,163 ± 363 | yes | 5 % | 57.1 | 9.0 | 33.9 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 1,000 | +4,163 ± 363 | yes | 10 % | 54.1 | 8.7 | 37.2 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | +1,220 ± 368 | yes | 0 % | 60.1 | 9.3 | 30.6 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | +1,220 ± 368 | yes | 6 % | 56.3 | 9.0 | 34.7 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | +1,220 ± 368 | yes | 12 % | 52.6 | 8.6 | 38.8 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 2,500 | +1,220 ± 368 | yes | 25 % | 45.1 | 7.9 | 47.1 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -1,723 ± 392 | no (it has left) | 0 % | 60.1 | 5.8 | 34.2 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -1,723 ± 392 | no (it has left) | 10 % | 54.1 | 5.2 | 40.8 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -1,723 ± 392 | no (it has left) | 20 % | 48.1 | 4.6 | 47.3 | 0.1 |
| bad = pass the tests, wrong: appeal on evidence, good-fix evidence accepted 50 %, bad-fix evidence accepted 5 %; `SOLVER_DEPOSIT_BPS` 4,000 | -1,723 ± 392 | no (it has left) | 40 % | 36.0 | 3.5 | 60.5 | 0.1 |
| bad = pass the tests, wrong: no appeal, 3 rival solvers at 25 % (post hoc); `SOLVER_DEPOSIT_BPS` 0 | +2,433 ± 251 | yes | 0 % | 58.3 | 3.7 | 38.0 | 0.1 |
| bad = pass the tests, wrong: no appeal, 10 rival solvers at 25 % (post hoc); `SOLVER_DEPOSIT_BPS` 0 | -77 ± 68 | no (it has left) | 0 % | 58.3 | 0.3 | 41.4 | 0.1 |

### The pot split by standing fixes, beside per-issue bounties (expected values, no simulation)

| Bad fixes | Seated | Honest solvers | A bad fix stands | Bad-fix solver, bounties, no deposit ($ a year) | …the pot, no deposit | …bounties, deposit 2,500 | …bounties, deposit 4,000 | Honest twin, bounties, no deposit | …the pot | Farmer of trivial fixes − its bounty return | Farmer filing its own issues, the pot | Issues not worth an honest fix (equal units) | …their share of funding | A rival's return per search: bounties | …the pot | Fixed / wrong / unfixed per 100: bounties | …the pot | Income spread: bounties | …the pot |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 | 1 | 10.1 % | +2,364 | +3,115 | -3,540 | -7,083 | +5,756 | +11,169 | +27,074 | +26,949 | 3 % | 11 % | $-0.35 | $+1.44 | 70 / 2.5 / 27 | 68 / 2.4 / 29 | 0.05 | 0.03 |
| the tests fail them | Opus 5.5 | 3 | 5.7 % | +1,200 | +1,622 | -4,995 | -8,713 | +5,465 | +10,796 | +27,074 | +26,949 | 3 % | 11 % | $-0.35 | $+1.44 | 70 / 1.4 / 28 | 68 / 1.4 / 30 | 0.11 | 0.08 |
| the tests fail them | Opus 5.5 | 10 | 0.8 % | -97 | -40 | -6,617 | -10,528 | +5,141 | +10,380 | +27,074 | +26,949 | 3 % | 11 % | $-0.35 | $+1.44 | 70 / 0.2 / 29 | 68 / 0.2 / 32 | 0.23 | 0.18 |
| the tests fail them | GPT-6.1 | 1 | 18.4 % | +4,532 | +6,685 | -830 | -4,048 | +1,568 | +8,256 | +23,776 | +24,507 | 7 % | 18 % | $-0.10 | $+5.35 | 52 / 4.6 / 43 | 49 / 4.3 / 47 | 0.06 | 0.03 |
| the tests fail them | GPT-6.1 | 3 | 10.3 % | +2,420 | +3,631 | -3,471 | -7,005 | +1,040 | +7,493 | +23,776 | +24,507 | 7 % | 18 % | $-0.10 | $+5.35 | 52 / 2.6 / 45 | 49 / 2.4 / 49 | 0.13 | 0.09 |
| the tests fail them | GPT-6.1 | 10 | 1.4 % | +66 | +228 | -6,413 | -10,301 | +451 | +6,642 | +23,776 | +24,507 | 7 % | 18 % | $-0.10 | $+5.35 | 52 / 0.3 / 47 | 49 / 0.3 / 51 | 0.26 | 0.21 |
| pass the tests, wrong | Opus 5.5 | 1 | 21.6 % | +5,389 | +6,078 | +241 | -2,849 | +6,512 | +8,928 | +22,303 | +25,070 | 6 % | 16 % | $-0.15 | $+3.39 | 70 / 5.4 / 24 | 66 / 5.1 / 28 | 0.04 | 0.03 |
| pass the tests, wrong | Opus 5.5 | 3 | 12.2 % | +2,902 | +3,289 | -2,869 | -6,331 | +5,890 | +8,231 | +22,303 | +25,070 | 6 % | 16 % | $-0.15 | $+3.39 | 70 / 3.0 / 26 | 66 / 2.9 / 31 | 0.11 | 0.08 |
| pass the tests, wrong | Opus 5.5 | 10 | 1.6 % | +130 | +182 | -6,333 | -10,211 | +5,198 | +7,455 | +22,303 | +25,070 | 6 % | 16 % | $-0.15 | $+3.39 | 70 / 0.4 / 29 | 66 / 0.4 / 33 | 0.23 | 0.18 |
| pass the tests, wrong | GPT-6.1 | 1 | 12.0 % | +2,862 | +4,923 | -2,918 | -6,386 | +1,150 | +10,668 | +28,340 | +26,374 | 4 % | 13 % | $-0.29 | $+3.00 | 52 / 3.0 / 44 | 50 / 2.9 / 47 | 0.06 | 0.03 |
| pass the tests, wrong | GPT-6.1 | 3 | 6.8 % | +1,480 | +2,640 | -4,645 | -8,321 | +805 | +10,098 | +28,340 | +26,374 | 4 % | 13 % | $-0.29 | $+3.00 | 52 / 1.7 / 46 | 50 / 1.6 / 48 | 0.13 | 0.09 |
| pass the tests, wrong | GPT-6.1 | 10 | 0.9 % | -59 | +96 | -6,570 | -10,476 | +420 | +9,462 | +28,340 | +26,374 | 4 % | 13 % | $-0.29 | $+3.00 | 52 / 0.2 / 47 | 50 / 0.2 / 49 | 0.26 | 0.21 |

### How many rival solvers it takes, with no deposit (expected values, no simulation)

| Bad fixes | Seated | Each rival finds a test | Bounties, no deposit: rivals needed for the bad-fix solver to earn nothing | The pot: rivals needed for it to earn nothing | The pot: rivals needed for it to earn under a tenth of an honest solver |
|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 | 10 % | 24 | 26 | 12 |
| the tests fail them | Opus 5.5 | 25 % | 9 | 10 | 5 |
| the tests fail them | Opus 5.5 | 50 % | 4 | 4 | 2 |
| the tests fail them | GPT-6.1 | 10 % | 30 | 33 | 22 |
| the tests fail them | GPT-6.1 | 25 % | 11 | 12 | 8 |
| the tests fail them | GPT-6.1 | 50 % | 5 | 5 | 4 |
| pass the tests, wrong | Opus 5.5 | 10 % | 31 | 32 | 20 |
| pass the tests, wrong | Opus 5.5 | 25 % | 12 | 12 | 8 |
| pass the tests, wrong | Opus 5.5 | 50 % | 5 | 5 | 4 |
| pass the tests, wrong | GPT-6.1 | 10 % | 26 | 30 | 17 |
| pass the tests, wrong | GPT-6.1 | 25 % | 10 | 11 | 6 |
| pass the tests, wrong | GPT-6.1 | 50 % | 4 | 5 | 3 |

