# Paper outline: Who Judges the Judges?

> **Status:** an outline for the owner's review (proof-of-fix#158). This is not the paper, and it must not be published
> from this repository. The paper is published from a scrubbed public copy. Written as research, with no launch, price
> or "get in early" language. The token is described as an optional component of the design.

**Title (owner, 2026-11-03):** ***Who Judges the Judges?*** *Proof of Fix: open AI-judged bounties, and what simulation reveals about keeping them honest*

**Author:** the owner, under their own name (#158).

## 1. The problem (about 1 page)
- **What open source lacks:** money doesn't reach the people who fix issues, and maintainers can't review every fix.
- **The question:** can a bounty pay out on a fix *verified* by independent judges, without a central party deciding?
- **The claim** is limited and honest: a mechanism and the evidence for it. No product and no token sale.

## 2. Background and related work (about 1 page)
- **Bounty platforms,** human-reviewed and centralised.
- **Decentralised oracles,** optimistic verification and the "watcher's dilemma".
- **AI judges for code:** model accuracy and how models can be gamed.
- **Attested compute** (TEEs) and **verifiable model calls** (zkTLS).
- **Sources:** the desk study (#44), with references to add.

## 3. The mechanism (about 4 pages)
Source: `openspec/changes/proof-of-fix-132-open-validators/design.md` and ADR 0004.
1. **The race:** registered issues, funded bounties, attempts, sealed fixes, and instalment payouts (v2: the `Race` contracts).
2. **Judges as a panel:** an odd number k that grows with the network, drawn by seed under caps (per operator, host, TEE type and model family).
3. **Admission:** open registration with a bond and an attestation, shadow-judging qualification, the reveal-rate floor.
4. **Proof levels:** A (a cloud TEE), B (a TEE elsewhere), C (zkTLS on any PC, off at launch) and why.
5. **Keeping judges honest:**
   - sealed votes;
   - random audits (10 %, two on lone verdicts);
   - challenges;
   - slashes (the whole bond for a false verdict, $5 for silence or withholding);
   - the hold on lone verdicts.
6. **Pricing without a vote:** validators post costs, the median sets unit prices, and a queue-driven service fee works like EIP-1559.
7. **Model-family scores:** pay by score, one vote per judge, and why weighted votes were rejected.
8. **Changing the rules:** a constitution of 7 judges drawn from at least 21 eligible validators (14 for removals), a forfeited deposit, keyless contracts and upgrades by migration only (ADR 0003, D15).
9. **The token (optional):**
   - an emission minted only for paid fixes, split by AI-judged weight between solver and reporter;
   - no founder's share (#157).
   - The mechanism works without it.

## 4. Method: the simulation (about 2 pages)
- **The agent-based simulator** (`pof/sim/`): seeds, honest twins, ± 2 SE, and the acceptance criteria (D17), including "not shown to gain".
- **The attackers modelled:**
  - sybil, lone colluder, seed grinder, silent judge, withholder, coalition;
  - fee farmer, cost inflater, spammer, cartel;
  - herder, answer shopper, test liar, chip breaker.
- **Assumptions,** named in `World`, and their limits.

## 5. Results: four rounds (about 4 pages)
Source: reports `open-validators-v1`, `-v2`, `-v3`, `-v3.1`, plus `tokens-v1…v4` and the acceptance reports.

| Round | Criteria met | Lesson |
|---|---|---|
| v1 | 4 of 10 | A lone judge can't be trusted, the outage slash froze the fee, and an early coalition owns the rules. |
| v2 | 8 of 13 | Fixing the lone judge worked. The fee signal collapsed markets (33 of 40). |
| v3 | 9 of 13 | No attack shown to pay. Criteria misread zero-effect attacks. |
| v3.1 | 13 of 13 | Re-judged with a statistically sound test. Five trust points named. |

- Each failure and its fix, with the deciding numbers. This is the paper's main contribution: **what broke, and why**.
- **Growth from one validator:** k ≥ 3 by week 6.
- **The fee settles** at about 1.2 × break-even.

## 6. Experiments with real systems (about 2 pages)
- **Determinism** (`reports/determinism-v1.md`, #125): an open model gave 600 of 600 identical judgements in vLLM's batch-invariant mode on one setup. The measured answer-shopping room was much smaller than assumed. A new knob was found: the check ID.
- **zkTLS** (`reports/zktls-spike-v1.md`, #135): 13 model calls were proven. It's not ready: no independent signing notary, and a 4 KB request cap.

## 7. Trust points and open problems (about 2 pages, written honestly)
1. **One TEE type** can hold the majority of 3-judge panels while only three types exist.
2. **The accomplice gap** in lone verdicts.
3. **A silence bribe above $5.**
4. **A sybil above 12.5 %.**
5. **Answer shopping** once level C is on.
6. **Honest validators net about −$1.43 a month early on** (#141). Candidate fixes: a token slice (#142) or fee tuning.
7. **What simulation can't show:** real model accuracy, real costs, real people.

## 8. Reference implementation and deployment checklist (about 1 page)
- **Contracts** (v2 built; v3 specified, ADR 0004), the validator node and kit, and the simulator. All open source under a permissive licence (MIT or Apache-2.0); forks welcome.
- **A deployment checklist,** so the easy path is the good one:
  1. Audited contracts.
  2. ADR 0004's parameters.
  3. Level C off until its conditions hold.
  4. TEE types confirmed by region.
  5. No founder's allocation.
  6. A randomness source suited to the chain.
- **The author doesn't deploy or operate it** (#158).

## 9. Conclusion (about half a page)
- What the evidence supports, what it doesn't, and an invitation to collaborate on the open problems.

## Before publishing (from #158)
- [ ] The Ridges/storytold decision.
- [ ] A scrubbed, fresh-history public repo: no `example.com` links, no AWS account IDs, no internal ticket, ERP or platform references, no personal emails.
- [ ] The company's note releasing the work under the licence.
- [ ] The owner's review of the full draft.
