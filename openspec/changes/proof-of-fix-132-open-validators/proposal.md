# Proposal

Ticket: proof-of-fix#132. Builds on #85 (self-healing, v2), #100 (validator openness, comment 4988), ADR 0003 (#121), #94 (attestation) and #118 (direct model calls).

**Revised 2026-11-03 (#141).** #134's simulation ([`reports/open-validators-v1.md`](../../../reports/open-validators-v1.md)) met 4 of its 10 acceptance criteria. The lone validator, the seed grinder and the constitution coalition won, the fee never left its ceiling, and honest validators lost money. This revision changes those rules, resolves the report's 23 spec gaps and publishes every acceptance threshold. See design.md, "Revision 2026-11-03 (#141)". The simulation's re-run is task group 6.

**Revised again 2026-11-03 (#141, round 2).** The re-run with round 1's rules ([`reports/open-validators-v2.md`](../../../reports/open-validators-v2.md), PR #147) met 8 of its 13 criteria. The market collapsed in 33 of 40 runs, bribed silence and withholding paid, an early constitution coalition still gained, too few of the lone validator's bad fixes were reversed, and herders of a weak family gained. With the owner's agreement, round 2 counts every wait for the fee, slashes silence and withholding a flat $5, draws ADRs that add from 21 eligible validators (removals from 14) with a $15 deposit a rejected ADR forfeits, audits every k = 1 verdict twice, balances the score and makes recovery wait for a fresh block, starts the TEE-type cap at k = 3 once five TEE types are accepted, and judges attackers by "doesn't gain". See design.md, "Revision 2026-11-03, round 2 (#141)". Its re-run is task group 7.

**Revised a third time 2026-11-03 (#141, round 3).** Round 2's run ([`reports/open-validators-v3.md`](../../../reports/open-validators-v3.md), PR #153) met 9 of its 13 criteria; no attack in the four that failed was shown to pay. With the owner's agreement, round 3 changes no protocol rule. It judges attackers by "not shown to gain", counts `LONE_CATCH_SHARE` on the lone validator's own verdicts and names its accomplice's other fixes as a trust point, sets `WAIT_CROWD_MAX` at 20 % to keep the balanced score, and sweeps a silence slash in proportion to the bounty for the parameters ADR to size. See design.md, "Revision 2026-11-03, round 3 (#141)". Its work is task group 8.

## Why

The owner (2026-11-02): *"can there be a way of a validator running and choosing a random valid odd number: if there is only 1 validator, run the AI check; if there are others, run 3? Everyone can host a validator node as long as there is a way to prove the AI check has been done."*

v2's `Verdicts` is a federation, which ADR 0003 names as a central point:
- 7 seats are fixed at deployment;
- a vacant seat is reserved for a named operator;
- a join needs 5 sitting seats to co-sign;
- every check draws 3.

So the owner has to recruit, run or approve the validator set before anything works, and the set can't grow.

This change makes the validator set **open by rule**:
- anyone who posts a bond and proves their node runs the official checker can judge;
- the number of judges grows with the network and with what's at stake.

That **simplifies deployment:** the project can start with a single genesis validator, so no owner-run validator set is needed, and grow without anyone's permission. With the self-healing loop (#85), the project can sustain itself:
- bounties on proof-of-fix's own issues, paid from the sponsors' pool, fund the work on the contracts;
- open validators judge it;
- fees pay the validators.

## What Changes

**Validators: open registration** (replaces v2's fixed seats and co-signed joins):
- Anyone registers a validator key with:
  - a **bond**;
  - an **attestation** of an accepted TEE type showing the official checker image;
  - its declared model family;
  - the infrastructure host, which is read from the attestation.
- No one co-signs. A new validator first serves a **qualification period** as a **shadow judge**: uncounted verdicts, sealed before the counted ones are revealed. It becomes active automatically if its reveal rate and its agreement with the final outcomes reach published thresholds.
- **Leaving:**
  - a validator leaves with an **unbonding delay** longer than the longest challenge window, and its bond waits for every challenge against it, so a fault can still be slashed;
  - a validator with a bond below the minimum isn't drawn.
- **The genesis validator** must hold a TEE (level A or B, below): a network of ordinary PCs can run once grown, but can't grow from one.
- **Slashing** (#141): a false verdict costs the **whole bond**. A counted judge that never seals, or seals and doesn't reveal, loses a flat $5 whatever its bond (round 2), and is replaced; the reveal-rate floor stops drawing it.

**Judges: an odd number that grows with the network and the bounty** (replaces "3 of 7" and "all 7"):
- At each draw, **k = the largest odd number ≤ min(eligible validators, K_MAX)**. A majority, (k + 1) / 2, decides.
- **Eligible** means active, bonded, not a party, and within the caps.
- **k = 1 is allowed:** with one validator, the check runs. Because one validator could pass its accomplice's fixes (#141):
  - its verdict is **held**, and nothing is paid, until 3 other validators could judge a challenge against it;
  - every k = 1 verdict is audited twice, by two other validators, before it is paid (round 2);
  - one validator may have at most 10 k = 1 verdicts pending;
  - candidates are scored only against outcomes no lone validator set, so it can't stall their qualification.
- **Each k has a published largest bounty and challenge window:**
  - a small panel may only judge small bounties, and its verdict becomes final only after a longer window;
  - a bounty above the current k's limit **waits** for more validators, and the solver may withdraw the deposit.
- **k is fixed at the draw.** A drawn judge that doesn't seal or reveal in time is replaced by the next in the shuffle. Its silence never shrinks k.
- **The constitution tier needs K_MAX judges** (published, 7 at first) with the published threshold (5 of 7), drawn only when at least three times K_MAX validators are eligible, or twice K_MAX for an ADR that only removes something (round 2). ADRs and escalated fixes submitted to a smaller network expire unjudged, so no backlog is drawn the moment a few early validators are most of the network. A rejected ADR forfeits a published deposit (round 2).

**Proof that the AI check ran:** a verdict counts only with all of:
- its key's attestation (the official image, an accepted TEE type);
- a direct provider call from inside the TEE (#118);
- a signed receipt bound to the verdict and posted on-chain (5.6).

Anyone may challenge within the window, with a stake and evidence. A larger, fresh panel re-judges.

**Random audits:** a published share of verdicts (10 % to start, #141) is re-run by a randomly drawn validator, paid from fees, so someone is always watching, even when no volunteer challenges. Every k = 1 verdict is audited twice (round 2), and every split pass by a level C panel once.

**Proof levels: a TEE, or zkTLS on any PC; both accepted, neither required** (owner, 2026-11-02):
- **Level A:** a TEE in a cloud, where the validator has no physical access.
- **Level B:** a TEE elsewhere, such as a home or rented server, where the validator might break its own chip.
- **Level C:** zkTLS on any machine. The model call is proven by a proof from one of several listed notaries, none required; the tests are checked by re-run challenges. Retrying the model for a wanted answer can't be proven per call: it's the named trust point at level C (#141).
- **A panel's level** is its majority's weakest. Each (k, level) has its own largest bounty and challenge window, so weaker proof means smaller bounties and longer waits, never exclusion. A network of ordinary PCs alone can judge.
- **Hidden tests and private repositories** need every judge at level A or B.
- **TEE attestations must meet a minimum firmware level.** A broken type, notary, image or firmware level is **removed by ADR after a short window**; a new one is **added only after the full challenge window**.
- **Nodes run anywhere:** one container and a timer, at home or in any cloud; AWS's Lambda is just one adapter.

**Prices: a market, not a vote** (replaces v2's "5 of 7 seats sign a price update"):
- **Pass-through unit prices** (tokens, sandbox time, gas) become, each period, the **median of the validators' own posted cost tables**, at most ±25 % per period and never above 2× genesis.
- **Every validator posts every unit:** its own sandbox, storage and gas costs, and every model family's public list price, so a few validators of one family can't set its price (#141).
- **The service fee follows the queue,** like Ethereum's base fee (EIP-1559). It starts at its ceiling, rises a step when submissions wait for a panel (every wait counts, round 2), falls a step when many validators sit idle, and stays between a floor and a ceiling.
- **Open entry makes it competitive:** a high fee attracts new validators until it falls back toward their average (break-even) cost, within a published margin. No account, panel or DAO sets a price.

**Model scores** (owner, 2026-11-02): each model family has a public score, its agreement with final outcomes, balanced over passed and failed outcomes so that always voting pass scores 50 % (round 2).
- A family below the minimum isn't drawn, and recovers by its shadow verdicts alone, which never lift its counted score (#141), on a fresh block above the minimum plus a margin (round 2). A new family starts neutral.
- **The service fee is scaled by the score** (0.5× to 2×), normalised so the network's mean factor is 1× (#141), and token costs are always repaid in full. A validator without money can use a frontier model's API, a validator with a GPU an open-weight model, and the market rewards whichever judges better per inference.
- **Votes stay one per judge.** Weighted votes are only simulated, for a possible later version.

**Defences against one party running many nodes:**
- a bond per validator: a validator may judge only bounties whose tier (the next limit in the k table) is at most half its bond;
- the attestation (every node runs the same honest code);
- caps per infrastructure host, TEE type and model family in any panel, read from the attestation and the receipts (the TEE-type cap from panels of 3 once five TEE types are accepted, from panels of 5 before; each attestation scheme its own type; round 2);
- a declared operator account, with at most one validator per declared operator in a panel;
- a draw seed that no single party can choose: fixed at a block after the submission is sealed.

**Sustainability and the owner:**
- **The owner may run at most one validator**, disclosed and under the same rules, and recuses as a party (rule 3).
- **No account controls any parameter:**
  - the k table, windows, bonds, caps and thresholds are fixed per version (entrenched; a new version by migration, D15);
  - the lists the constitution allows (attestation types, image digests) change only by ADR at the constitution tier.
- **A DAO or other legal wrapper (#126)** may fund the sponsors' pool and sponsor bounties on proof-of-fix's own issues. It may run a validator under the same rules, and **holds no key or vote over the contracts.**

**Building the contracts (owner, 2026-11-13):** groups 3–5 build them now. v3 builds its own seals, reveals and receipts on-chain, and its own bonds and slashes, instead of waiting for them in v2 (#122, #85 5.5, 5.6 and 5.8). Attestation is simulated on devnets (design D18).

**Amendment after the judge measurement (2026-11-14, #236; design D20–D23):** on measured judges v3 as designed merges 10–18 bad fixes per 100 paid against the 1.1 assumed, and its score ranks the judges wrongly. The owner agreed the direction on 2026-11-14; the values wait for the simulation (task 10.1) and a new parameters ADR:
- seats go to the best-scoring families, and the family cap applies only among near-equals;
- anyone may reverse a pass with a failing test, and is paid for it;
- a solver posts a deposit, lost on rejection;
- final outcomes come from those disputes and from a rejected fix's one appeal, and a new family starts as a contender.

It affects solvers (a deposit), validators of weaker models (contenders, not judges), and adds three attackers to the simulation: a solver of bad fixes, a solver that appeals everything, and a disputer without evidence.

**Amendment after task 10.1 (2026-11-15, #236; design D24–D28):** the appeal panel of 2026-11-14, drawn from the families that didn't judge, overturned four in five correct rejections in the simulation. **The owner dropped it on 2026-11-15: the seated families decide an appeal, and wrong rejections need a challenge that doesn't hand the decision to weaker judges.** The replacement below is proposed, not decided, part by part (`reports/open-validators-measured-v4.md` has the simulation):
- an appeal needs new evidence, a test that fails on the base code and passes with the fix, and a stake of its own (proposed);
- a contender may sponsor the appeal of a fix its model passed (proposed);
- issues with known answers score every family, seated or not (proposed);
- while fewer than three families can judge, a challenge is decided by a second draw from them (proposed);
- a rejected fix's deposit is held until its appeal period closes (proposed). **The deposit itself is on hold (owner, 2026-11-15):** he is against it, and its share is neither 2,500 nor the 4,000 task 10.1 found until he rules.

It adds two attackers to the simulation: a contender that sponsors every rejection, and a solver that tries an issue again while its deposit is held.

**Out of scope:**
- token rewards (the token is parked); the validators' token slice is #142, related;
- a public deployment (after D1; rule 1);
- verifying TEE quotes or zkTLS proofs on-chain (checked off-chain by the drawn panel, with the hash published, as in #85);
- running a zkTLS notary ourselves as a required service;
- the legal wrapper itself (#126).

## Capabilities

### New Capabilities
- `validator-admission`: how anyone becomes, stays and stops being a validator: registration with a bond under an accepted proof type (a TEE or zkTLS), qualification as a shadow judge, activation, suspension, unbonding, the caps that bound one party's presence, and faster removal than addition of accepted types.
- `judge-scores`: each model family's public score from agreement with final outcomes on counted verdicts, the minimum score to be drawn, recovery by shadow verdicts, the neutral start, and the service fee scaled by a normalised score factor, with votes kept one per judge.
- `check-pricing`: how a check's price moves with no vote: unit prices from the median of validators' posted cost tables, and the service fee from the queue, within fixed bounds.
- `judge-panels`: how each check's judges are chosen and when their verdict is final: the odd k from eligible validators and the bounty, the draw and its seed, replacement of silent judges, the proof a counted verdict must carry, challenge windows by panel size, the hold on a lone judge's verdict, audits, and the constitution tier's fixed size.

### Modified Capabilities
- `bounty-market`: in v3, a solver's deposit, lost on rejection and added to the issue's bounty (#236), held until the appeal period closes (proposed, 2026-11-15).
- `incentive-simulation`: adds open-validator scenarios (one party running many nodes, few validators, k = 1, window and bond sizes), market pricing and its attackers (fake shortage, fake demand, inflated costs), zkTLS validators, #141's two re-runs with their rules beside their alternatives, and the acceptance criteria, each with a published threshold, to meet before any contract code.

## Impact

- **Actors and incentives:**
  - **validators:** anyone can join; each pays a bond and running costs, and earns check fees (#111);
  - **solvers:** fewer judges and a longer wait for finality while the network is small; a k = 1 fix is paid only once 3 other validators could challenge it (a median 19 days in round 1's re-run, accepted by the owner);
  - **funders:** a cap on bounty size while the network is small;
  - **challengers:** paid for upheld challenges;
  - **the owner:** no longer gatekeeps; one disclosed validator at most;
  - **a DAO:** funds, never controls.
- **Attacks covered:**
  - one party running many nodes, to dominate the draw;
  - a lone validator approving its own or a colluder's fix (k = 1), and stalling newcomers' qualification;
  - grinding the draw seed;
  - going silent to change the panel;
  - farming fees with many idle nodes;
  - capturing the constitution tier while the network is small;
  - shadow judges copying the counted judges;
  - judges herding to the majority to lift a weak family's score;
  - a cartel faking a shortage to raise fees, fake demand, inflated cost tables;
  - a level C validator lying about its test results, or retrying the model until it gets the answer it wants;
  - a level B validator breaking its own chip.
- **Code (planned, not in this change):**
  - **contracts:** a new `Validators` registry and `Panels` draw replacing v2's `Verdicts` seats; `RaceV2`'s successor reading k and the window from them; `Fees`' successor with the median and queue pricing (the fee formula unchanged);
  - **the oracle node:** registration, shadow judging, the challenge flow, posting its cost table, and a zkTLS prover for nodes without a TEE;
  - **the validator kit:** register instead of join;
  - **`pof/sim/openval/`** (built in #134): the new scenarios, and #141's two re-runs.
- **Migration:** v2 stays for the devnet demo. v3 is a new version (D15): v2's bounties finish in v2, and new ones open in v3.
