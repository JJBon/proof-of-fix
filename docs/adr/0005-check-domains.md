# ADR 0005: Check domains: the judges answer other contracts' questions, one domain at a time, each by its own ADR

- **Status:** proposed (#195). The owner accepts it by merging it. No constitution tier exists yet to pass it, and nothing in it is deployed.
- **Date:** 2026-11-09
- **Author:** Claude, an AI model, drafting for the owner (example-owner; proof-of-fix#195). Interest disclosed: the owner may fund bounties or pools in a version that has the general token, and would then gain from the burns this ADR sends to it. This ADR also amends Article 11.3 so that the owner earns tokens only as an ordinary funder, under the same rules as anyone (owner's decision, 2026-11-10). The owner takes no share of bounties and has no founder's share. The owner may run one judge, under the same rules as any other (ADR 0003).
- **Constitution articles changed:** 1 (Purpose), 5 (one line in clause 11: outside requests pay their own checks), 7 (the domain list becomes a protected path), 10 (outside requesters), 11 (clause 3: the owner earns tokens only as an ordinary funder) and a **new Article 12** (Check domains). None of them is entrenched. The parts that would need Article 3 changed (panels other than 3 and 7, a domain's own list of model families, its own bonds, and scores that steer the draw) are not decided here: they wait for v3 (#132, ADR 0004).
- **Protected paths touched:**
  - `CONSTITUTION.md` (Articles 1, 5, 7, 10 and 11, and the new Article 12, exactly as in section 8)
  - `docs/adr/0005-check-domains.md`

## Problem
**Funders can't be paid back by the protocol's own activity.** #193's simulation ([`reports/fundertoken-v1.md`](../../reports/fundertoken-v1.md), PR #194) prices the one general token at what use alone supports: about **$0.27 a token** (p\*). At that price, investors get back **about 23 cents per dollar** they put in, whichever product they pick: one repository's pool, the index pool, or bounties they choose. Almost all of those 23 cents come from the payout fee, which solvers pay. Investors break even only when about **$6,900 a week** of outside margin is burned: 71 % of what funders spend.

**The network already has what an outside buyer of verdicts needs:** attested judges in TEEs, sealed-then-revealed verdicts, 2-of-3 and 5-of-7 signatures, receipts and staked challenges (Article 3; ADR 0003; ADR 0004). The owner's direction (#195): make the judges' network pay through that infrastructure. The validated judges answer other contracts' questions too, not only proof-of-fix's code checks, and every margin is burned in the one general token, so funders gain from all use.

**What the evidence says about that market:**
- **The desk study** ([`reports/oracle-market-v1.md`](../../reports/oracle-market-v1.md), PR #196, public sources only):
  - the whole on-chain market for paid verdicts is about **5,000-30,000 requests a week**, and a new network might win **a few hundred to a few thousand** in its first year;
  - **most of it is priced below our cost:** routine prediction-market resolution pays about $2-5, and UMA's AI drafts a proposal for about half a cent, against our $0.05-0.37 a check;
  - **security triage is the clearest fit:** bug-bounty and audit-contest reports with a proof of concept (PoC) are checkable inside the one checker image, and contest judging pays about **$8-10 an issue**;
  - prediction-market disputes are expensive (a $750 bond) but few (about 50 a week), and need proven sources (#139); insurance claims, disputes and grants are judgment questions with tiny volumes.
- **The simulation with outside revenue** ([`reports/fundertoken-v2.md`](../../reports/fundertoken-v2.md), PR #194):
  - break even needs about **870 security-triage verdicts a week at an $8 margin** (a $9 price, a $1 cost), or 11,000 code checks at $0.63, or 139,000 routine answers at $0.05;
  - in #196's "realistic first year" (triage 900, code 2,000, 10 disputes, 200 maths checks a week), investors get back **120 %**, and more than 80 % of the margin comes from triage;
  - **our cost per triage verdict isn't measured.** At a $10 price, 900 verdicts a week give back 113 % at a $1 cost, but 93 % at $3;
  - **paying judges only their costs doesn't keep them:** each judge's node and the opportunity cost of its bond go unpaid, **$84-161 a week**, or $0.035-0.23 an answer at #196's volumes;
  - **growth doesn't pay the first year's funders:** triage growing from a tenth of break even gives them 58 % over the year.

**What's missing is the rule.** Nothing says which questions the judges may answer for outsiders, how a kind of question is admitted, what it must prove first, how its money flows, or how a failing kind of question is stopped without harming the others. Article 3 is entrenched, and it fixes 7 judges, a 3-judge tier, a 7-judge tier and one checker image, so any rule written now has to work inside those limits.

## Options
1. **Keep things as they are: code checks for proof-of-fix's own bounties only.**
   - **Costs:** nothing to build.
   - **Risks:** funders get back about 23 cents per dollar at the price use supports (v1). Funding stays a purchase of fixes with a partial rebate, and the paper's claim stays that narrow. The judges' infrastructure sits idle most of the week: one judge node is enough for #196's whole realistic volume (v2, table 5).
2. **A general oracle with one flat policy for every question:** one rubric style, one margin, one panel, one bond and one challenge window, for code, facts, disputes and anything else.
   - **Costs:** one rule set, quickest to write.
   - **Risks:**
     - **one margin can't fit prices from half a cent to $149** (#196). At $0.05 a request, break even needs 139,000 requests a week, more than the whole market; at $8, routine questions find no buyer;
     - **one bond must fit the largest question.** A $50,000 dispute needs a $100,000 bond from each of the 7 judges, $673 a week of opportunity cost, which 10 disputes a week don't cover (v2: disputes pay for their own bonds only from about 24 a week). Otherwise the cap is set so low that no dispute fits;
     - **one failure taints everything:** a bad run of judgment answers lowers the same scores and the same reputation that checkable answers rely on, and there's no way to stop one kind of question alone;
     - **no ordering:** judgment questions open on the same day as checkable ones, before anyone has measured accuracy on either.
3. **Chosen: check domains, each opened, changed and closed by its own ADR.**
   - **Costs:** an ADR per domain (7 verdict fees and a 14-day window, Article 9), and a shadow phase before any money moves on a domain's answers.
   - **Risks:** slower to reach volume; each domain ADR is a chance to loosen something, so the shared core has to be fixed in the constitution where no domain ADR reaches it.
4. **A separate network and token for each domain:** its own judges, bonds, token and burns.
   - **Costs:** a full set of operators per domain. v2's sim shows 7 judges with one node each serve every domain at #196's volumes; splitting multiplies the $84-161 a week each judge's node and bond already leave uncovered.
   - **Risks:** it splits the token, against the owner's one-token decision (#177, #186: per-repository tokens rejected; one protocol token). Each funder would be exposed to one domain's demand, and a small domain's token would have no use to support its price. It also splits the validators, so each network is smaller and easier to capture. **Rejected.**

Option 3 is better than 2 because the evidence says domains differ by two orders of magnitude in price, by ten in volume, and in whether an answer can be checked at all; one policy fits none of them. It's better than 4 because one token and one set of judges are what make outside use pay funders at all, and the simulation shows one set of judges has room for all of it.

## Decision
Option 3. The judges' network answers outside contracts' questions in **check domains**. Each domain is one kind of question, opened, changed and closed by its own ADR, and improved by anyone through later ADRs. Every domain's margin (its price less the judges' real costs and service fee) is burned in the one general token; the judges' real costs are passed through in stablecoins; and the judges earn a service fee on top.

### 1. The shared core, which no domain ADR changes
- **Everything in the entrenched articles** (2, 3 and 9) applies to every domain: no human control, the judges as Article 3 fixes them, and amendment only by ADR.
- **One token.** In a version that has a token, all domains burn their margins in the same one. **Burns are paid to nobody:** no owner's, operator's or fee address's share. A version without a token, like v2 (Article 5.12), charges no margin: a domain's price there is its costs plus its service fee.
- **Costs passed through, one service fee.** The judges' real costs are charged at the shared price table's unit prices (Article 5.11). Each domain sets one service fee per counted answer, the same for every judge, never above Article 5.11's cap ($0.25).
- **No slash for a wrong answer given in good faith** (Article 3.7), in any domain.
- **Answers never govern.** A request never moves the canonical head, a bounty or a rule (Article 10, clause 3, below).

### 2. The domain template
Every domain ADR fills in every field. An empty field means the domain isn't opened.

| Field | What the domain ADR must state |
|---|---|
| **Question and answer format** | A structured answer: yes/no, a score on a stated scale, or one choice from a stated list, always with the judge's reasons. Free text alone is never an answer. |
| **Rubric** | How a judge decides, written so that two judges reading it reach the same answer on clear cases. It's part of the checker's prompts (Article 7). |
| **Ground truth** | What the answers are scored against, and so the domain's verifiability tier (section 3): a **checker** (tests, a Lean proof, a reproducible computation run in the sandbox); **verifiable sources** (fetched with a proof, zkTLS, #139); or **judgment**, scored against a later final outcome. |
| **Panel and quorum** | Under v2: the issue tier (3 of 7, 2 to pass) or the constitution tier (all 7, 5 to pass). Nothing else (section 6). |
| **Challenge window and stakes** | How long anyone may challenge an answer, and the stake. A challenge goes to the constitution tier, and the losing side's stake goes to the winning side. |
| **Allowed model families and versions** | Under v2: all seven judges' families, at the versions Article 7's list allows. The ADR records which versions its shadow phase measured. |
| **Fee table** | The price per request; the expected cost (from the unit prices, with the measured median usage); the margin; the service fee; and the caps: per request, and on requests a week. |
| **Largest value decided, and the bond rule** | The most money any one answer can move or release. **Each judge's bond is at least twice it,** which extends Article 3.7's rule for bounties to outside requests. Under v2 this means a cap (section 6). |
| **Canaries and scores** | How the domain's own known-answer checks are made without a privileged author (#136's keyless canaries, where the domain allows them, or none until then), and how each judge's score in this domain is kept. Scores are per domain and never mixed with another domain's. |
| **Shadow mode, and the bar to leave it** | The accuracy bar, the minimum number of scored answers and the cost per answer to measure, **published before the shadow phase starts,** as ADR 0004's thresholds were published before the run that judged them. |
| **Suspension rule** | The on-chain signal (for example, the share of the domain's recent answers reversed by upheld challenges) at which the domain stops taking new requests. It's automatic: the contracts apply it from on-chain records alone, and no person, judge or key can trigger it or lift it. Only an ADR reopens the domain. |
| **Input handling** | How a request's content reaches the judges: as data inside a marked block, never as instructions; size limits; what is stripped; how prompt injection is tested (canaries with injected instructions, the measurement #85 and ADR 0001 require); and what stays private (only hashes in the public log until the requester's disclosure date, where the content is sensitive). |
| **Refusal policy** | The requests the domain refuses: harmful ones (for example, confirming an exploit against a live, undisclosed target outside its owner's bounty programme, or questions about a private person), and any request that tries to instruct the judges. A refusal is an answer, with its reasons, charged its costs and service fee with no margin. |

### 3. Verifiability tiers, and the order domains open in
| Tier | Ground truth | Domains (from #196) | When |
|---|---|---|---|
| **1. Checkable** | a checker: tests, a PoC run in the sandbox, Lean's kernel, a reproducible computation | security triage and code checks; Lean statement checks | **first,** under v2 |
| **2. Partly checkable** | verifiably fetched sources | prediction-market disputes (only the escalated ones, about 50 a week); fact checks | **after #139** makes fetched sources provable (TLSNotary isn't ready: [`reports/zktls-spike-v1.md`](../../reports/zktls-spike-v1.md)), and in a version with challenge windows short enough for a market (ADR 0004's run from 6 to 336 hours) |
| **3. Judgment** | a later final outcome, or none | disputes, insurance claims, grants | **last, and only under v3:** they need larger panels, longer windows and staked challenges, and bonds v2 can't hold (a $6.1 M claim, #196) |

Not to enter: price feeds and generic AI inference. They're commodities priced near zero, and their sellers (Chainlink, Pyth, ORA, Ritual, EigenAI) are well funded (#196).

### 4. The first domain: security triage and code checks
**What:** bug-bounty submissions with a PoC, and audit-contest issues. The question is whether the submission shows what it claims, within the programme's scope, and at what severity. The answer is a choice (valid, invalid or out of scope), a severity from the programme's own scale, and reasons. Duplicate detection comes later.

**Why first:** it's checkable (the PoC runs in the one checker image's sandbox, on a forked chain at a pinned block); it carries the highest price per verdict in #196's market; demand is growing because AI-written reports are flooding programmes (curl ended its bounty; HackerOne paused the Internet Bug Bounty); and **v2's 3-judge tier is enough.**

**How it starts: in shadow mode, scored against the platforms' published final judgments.** Contest results and disclosed bounty reports are public, so the shadow phase needs no buyer, no contact and no undisclosed report. No money moves on a shadow answer.

**What the shadow phase must measure:**
- **our cost per triage verdict,** which nobody has measured. costs v1's medium code check is $0.37, and a PoC on a forked chain costs more. The money case depends on it: at a $1 cost, 900 verdicts a week at $10 give back 113 %; at $3, 93 % (v2);
- **accuracy** against the final judgments, balanced over valid and invalid outcomes as ADR 0004's scores are, so that a judge who always says "invalid" (most reports are) scores 50 %;
- **prompt injection** in submitted reports, which are written by the party that gains from a "valid".

**The numbers its opening ADR will be judged against (v2, simulated):** break even at about **870 verdicts a week at an $8 margin**, +20 % at about 1,100; at #196's low end (300 a week), investors get back 41-56 %.

**This ADR doesn't open it.** Its own ADR fills in the template, publishes the shadow bar first, and opens it in shadow mode. Lean statement checks follow, sold at cost, for the record they give and for the paper (#5), not for money.

### 5. Isolation, and closing a failing domain
- **A domain's scores, canaries, fee table, stakes and challenges are its own.** An upheld challenge in one domain moves stakes only in that domain and lowers scores only there.
- **Bonds under v2 are shared, but wrong answers can't reach them.** Each judge has one Article 3.7 bond, slashed only for provable faults (conflicting signatures, a missed reveal, a bad receipt), which are the same in every domain. A domain giving wrong answers in good faith can't drain any judge's bond. Separate bonds per domain wait for v3.
- **A failing domain stops itself, automatically.** When its suspension rule's signal is crossed, the domain takes no new requests. The contracts apply the rule from on-chain records alone: **no person, judge or key can trigger it or lift it,** and no vote is taken. So it isn't a pause function, which Article 2.3 forbids: nobody holds it. It's the same kind of rule as Article 5.2's withdraw-only coin. Requests already taken finish under the rules they were taken under. Only an ADR reopens the domain.
- **Then an ADR closes it,** and no other domain changes.
  - **Under v2,** that's an ordinary ADR: 5 of 7 and the 14-day window, since Article 9 is entrenched. The suspension rule is what makes the 14 days safe.
  - **Under v3,** an ADR that only closes a domain or tightens its limits should count as a **removal:** judged from `REMOVAL_MIN_ELIGIBLE` (14) eligible validators, after `REMOVAL_WINDOW` (48 hours) (ADR 0004; design D7, D11). Opening a domain, loosening one or leaving shadow mode is an **adding** ADR, judged from 21 eligible. v3's constitution is written at its deployment (#138), so this is a recommendation to it, not a rule this ADR can set.

### 6. What v2 allows, and what waits for v3
| | Under v2's constitution (Article 3, entrenched) | Waits for v3 (#132, ADR 0004) |
|---|---|---|
| **Panels** | the issue tier (3 of 7, 2 to pass) and the constitution tier (all 7, 5 to pass) | a variable k per domain, and challenge panels sized per domain |
| **Judges** | all 7, each with its fixed family and operator | the open registry; a domain's own list of families |
| **The checker** | the one official checker image. **A domain is a mode of that image,** added through Article 7's allowed list of image digests | the same, with v3's reproducible image (#124) |
| **Value decided** | **no request may decide more than the largest bounty the version accepts,** so Article 3.7's bonds (at least twice it) cover every answer | per-domain bond tiers, at twice the domain's largest value |
| **Scores** | kept per domain and per judge, and published; they change neither the draw nor pay (Article 3.1: weighting by quality only in a later version) | per-domain, per-family scores in the draw and in pay (D14), with keyless canaries (#136) |
| **Tiers of question** | checkable only; partly checkable once #139's sources are accepted | judgment domains |
| **Money** | **no margin** (no token, Article 5.12): costs plus the service fee | the margin burned in the one general token, in the version that carries it |

The value cap is the binding limit for security triage. Bounty payouts are often in the thousands of dollars, so under v2's bonds a live triage answer could decide only small reports. Shadow mode moves no money, so it has no such limit. Live triage on large reports needs larger bonds, which means v3's tiers or a version that sets a larger largest bounty.

### 7. Two findings from the simulation, for #186 and the token
- **#186's attack criteria should compare each attack with the honest use of the attacker's coin, not with doing nothing.** Once funding pays, any funding beats a twin that funds nothing, so plain investing would look like an attack (v2, summary 3). Measured against the honest use of the same coin (putting it in the pools):
  - **overclaimed merit loses $2,900-4,700 a year at every token price up to $100,** with 0, 3 or 5 of 15 judges colluding;
  - **self-dealing** beats honest investing only from $1.16-1.54 a token, and only by **$11-43 a year:** its own coin is paid in full when a pool is short, the edge any bounty has;
  - **1-cent pledges** beat it only from about $16 a token, by $4-18 a year.
  - So no new attack pays, and what stops overclaiming is still the 3× issue stake and the challenges, not a low price. The spec change goes into `openspec/changes/proof-of-fix-186-cycle-pools` (its incentive-simulation delta) in its own PR.
- **The rebate ceiling: considered, not recommended for now.** v2 proposed burning a cycle's outside margins only up to `rebate_max` × the coin paid to fixes that cycle, and charging buyers less above that. At 1.2 it holds investors at 126-127 % and p\* at $1.49-1.64, however large outside use grows. Its purpose was to keep the price below v1's attack prices ($1.12 and $2.84). With the corrected criterion above, those prices are no longer the test, so the ceiling isn't needed. It would also cap funders' returns, and whether self-dealt coin can raise its room (by $1-1.3 a dollar) to profit wasn't simulated. It stays an option if a later run shows an attack that pays at high prices.

### 8. The constitution's new text
**Article 1. Purpose** (new text; the first paragraph is unchanged):

> proof-of-fix is self-healing, decentralized code. Its code is repaired and improved by whoever fixes it best, judged by AI judges under this constitution, and paid by whoever funds the fix. Funding open-source work is the means; code that keeps itself healthy with no one in control is the goal.
>
> The same judges also answer questions that other contracts send them, one check domain at a time (Article 12). Those who ask pay for that work, and it never moves the code or a rule.

**Article 5, clause 11** (one line added to the list of what pays the judges, after "the winner's checks are refunded from the bounty at merge", whose full stop becomes a semicolon):

> - an outside requester's fee pays its request's checks (Article 12).

**Article 7. Protected paths** (one item added at the end of the list; the item before it now ends with a semicolon):

> - `domains/`: the list of open check domains and each domain's definition (Article 12), once they exist in this repository.

**Article 10** (retitled, with a clause added):

> ## Article 10. Outside projects and outside requesters
> *(clauses 1 and 2 unchanged)*
>
> 3. **Outside requesters are never governed by this constitution, and govern nothing in it.**
>    - A contract or person that asks a question in a check domain (Article 12) gets an answer under that domain's rules. What it does with the answer is its own affair.
>    - A request never moves the canonical head, a bounty or a rule.

**Article 11, clause 3** (new text):

> 3. **The owner takes no share of bounties and receives no founder's share;** the owner earns tokens only as an ordinary funder, under the same rules as anyone.

Why: the owner's decision (2026-11-10). The owner keeps no founder's claim of any kind, but isn't barred from funding like anyone else. The old text ("receives no founder's share or token") would have kept the owner from earning the token by funding, which every other funder may do. Funding earns tokens only by the per-fix cap and the shared rules (#186, #193), so the owner gains nothing anyone else couldn't.

**Article 12. Check domains** (new):

> ## Article 12. Check domains
> 1. **A check domain is one kind of question the judges answer for outside requesters.** Each is opened, changed and closed only by its own ADR, which fills in every field of the domain template (ADR 0005) and is recorded under `domains/` (Article 7). Nothing is answered outside an open domain.
> 2. **The shared core, which no domain changes:**
>    - every article of this constitution applies to every domain;
>    - **one token:** in a version that has a token, every domain's margin (its price less the judges' costs and service fee) is burned in that one token, and paid to no one. A version without a token charges no margin;
>    - the judges' costs are charged at the price table's unit prices (Article 5.11), plus one service fee per counted answer, the same for every judge, never above Article 5.11's cap;
>    - **each judge's bond is at least twice the largest value any one answer decides.**
> 3. **In this version (Article 3):**
>    - a domain uses only the issue tier and the constitution tier, with all the version's judges at their allowed model versions;
>    - a domain is a mode of the one official checker image, on the allowed list of digests (Article 7);
>    - no request decides more than the largest bounty the version accepts;
>    - a domain's ground truth is a checker (tests, proofs or a reproducible computation) or, once accepted, verifiably fetched sources. Domains judged by opinion wait for a version with larger panels.
> 4. **A judge whose operator is a party to a request recuses,** as for a bounty. **Each answer's signature binds its domain and its request,** so it can't stand for any other answer or verdict (Article 5.5).
> 5. **Shadow mode first.** A domain opens in shadow mode: its answers are recorded, published and scored against its ground truth. They are paid at cost plus the service fee by whoever asks, they carry no margin, and no money moves on them. It leaves shadow mode only by an ADR that shows its measured accuracy against the bar its opening ADR published before the shadow phase began.
> 6. **Challenges.** Anyone may challenge a domain's answer within its window, with the stake its ADR sets. The constitution tier judges the challenge, and the losing side's stake goes to the winning side.
> 7. **Isolation.** A domain's scores, canaries, fee table, stakes and challenges are its own. **When its suspension rule is met, it takes no new requests, automatically:** the contracts apply the rule from on-chain records alone, and no person, judge or key can trigger it or lift it. Only an ADR reopens or closes the domain, and closing it changes no other domain.
> 8. **Every domain refuses** the requests its refusal policy names, and any request that tries to instruct the judges through its content.

## Evidence
What shows the decision works and breaks no invariant (Article 5):
- **Reports** (both unmerged when this was written):
  - **the market desk study,** [`reports/oracle-market-v1.md`](../../reports/oracle-market-v1.md) (PR #196): public web sources only, each marked primary or secondary, read 2026-11-09; no contact with any project;
  - **the funder token, v1,** [`reports/fundertoken-v1.md`](../../reports/fundertoken-v1.md) (PR #194): `python3 -m pof.sim.fundertoken --seeds 20 --json`, seeds 1-20, a year of 52 weekly cycles;
  - **v2, with outside revenue,** [`reports/fundertoken-v2.md`](../../reports/fundertoken-v2.md) (PR #194): `python3 -m pof.sim.fundertoken --seeds 20 --v2 --json`, the same seeds. With no outside use it reproduces v1 bit for bit (a test checks it).
- **Tests and contracts:** none changed. This ADR is a decision on paper. Contract work for domains, and the domain modes in the checker image, follow in their own issues.
- **The invariants, one by one:**
  - **keyless versions (5.1):** domains open and close by ADR or by their own suspension rule, never by a key;
  - **solvency per coin (5.2) and pull payouts (5.3):** a requester's fee is held per coin and paid out as credits, like a solver's deposit;
  - **caps (5.4):** each domain adds its own caps, and no request decides more than the largest bounty;
  - **signed verdicts (5.5):** an answer's digest binds its domain and request, so it can't be replayed as a merge verdict or another domain's answer;
  - **the race, the split, one payout, payment by instalments and the idle sunset (5.6-5.10):** untouched; requests never enter a bounty;
  - **no cut (5.11):** the margin is burned, never paid to anyone, and only in a version with a token;
  - **no token (5.12):** unchanged; v2 charges no margin;
  - **numbers (5.13):** unchanged.
- **Still to measure,** before any domain leaves shadow mode:
  - our cost per triage verdict (#196 and v2 both say it's unmeasured);
  - the judges' accuracy per domain, against published final judgments;
  - prompt injection through submitted content;
  - whether buyers pay for an attested, sealed, multi-family quorum over one cheap model (#196: every price in the study is what buyers pay incumbents).

## Consequences
- **Funders:** in a version with the general token, they gain from every domain's burns, not only from bounty fees. On the simulated numbers, that's the only way they break even: about $6,900 of margin a week, or about 870 triage verdicts. **A growing market pays later funders more than the first year's** (58 % over the first year on v2's growth path).
- **Solvers:** nothing changes for bounties. The payout fee still burns part of their pay (v1: about 19 % at p\*), and outside burns don't touch pools, tokens or solvers' pay (v2, summary 7).
- **Judges:** more work for the same seven nodes, paid at cost plus each domain's service fee. v2 suggests about **$0.25 an answer** at low volume, falling with volume, which is Article 5.11's cap; for triage, 3 × $0.25 = $0.75 of an $8 margin. Each domain adds a rubric, a mode of the checker image and a shadow phase to run, and scores they can lose in one domain without touching another.
- **Outside requesters:** a structured answer with reasons, signed by a sealed quorum of different model families and operators, with a receipt and a challenge window. They are never governed, and their answers never move the code or a rule. Under v2 they can ask only checkable questions, and only for values up to the largest bounty.
- **Watchers and challengers:** a new kind of thing to challenge, with stakes per domain, judged by the constitution tier. Per-domain scores and suspension signals are public.
- **What becomes harder:**
  - **reputation:** a judgment domain that answers badly hurts the network's name for all domains, even if its scores and stakes are isolated. That's why judgment comes last, and only under v3;
  - **bonds for high-value questions:** a $50,000 dispute needs $100,000 from each judge; v2 can't hold that, and even v3 needs about 24 disputes a week to cover the bonds' cost;
  - **competition:** UMA's optimistic oracle and its AI proposer, Kleros, Chainlink's CRE with AI consensus (Chainlink Functions closed on 2026-09-01), GenLayer, and AI inference oracles (ORA, Ritual, EigenAI, OpenGradient, Gensyn Judge). For triage: Immunefi's AI triage, Sherlock AI, Zellic V12 (reported free) and CodeHawks' AI judge. Each sells a cheaper answer; we'd sell a harder-to-bend one, which pays only where someone gains by bending it;
  - **one ADR per domain** is slow: the 7 verdict fees and 14 days of Article 9 each time.
- **For v3 (#132, #138):** carry per-domain panels, bond tiers, family lists and scores in the draw; count closing a domain as a removal.
- **Money stays simulated (rule 1).** No real token, chain, coin or buyer exists. The project stays private: no public network and no contact with any platform. The first domain's shadow phase uses only already-published reports and judgments.
- **Open bounties keep their version:** domains don't touch bounties, and every bounty keeps the constitution it was registered under (Article 9.5). A request keeps the domain rules in force when it was submitted.

## Challenge window
None yet: no constitution tier exists to pass it, and the owner accepts it by merging. From genesis on, an ADR like this passes the constitution tier (5 of 7) and then a 14-day public challenge window, in which anyone may challenge it with a stake and evidence (Article 9). Each domain ADR that follows takes the same path.
