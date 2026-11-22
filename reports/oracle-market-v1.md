# The judges as an outside oracle: who pays for verdicts today, v1 (proof-of-fix#195; 2026-11-09)

**What this is:** a desk study, for item 1 of #195. It uses public web pages only: no contact with any project, no sign-ups and no accounts. Every figure carries its date and its source, listed at the end.
- **P** marks a primary source: the project's own docs, blog, forum or dashboard, or a paper.
- **S** marks a secondary source: news, an aggregator, or a mirror of a project's post.
- **Estimate** marks arithmetic of ours, and the arithmetic is shown.
- Where a number isn't public, the study says so. Nothing here is a forecast.

**The question.** Could the judges' network answer other contracts' questions and earn enough margin to pay funders? The network has attested TEE judges, sealed-then-revealed verdicts, 2-of-3 and 5-of-7 signatures, receipts and staked challenges (Article 3; ADR 0003; ADR 0004).
- [fundertoken v1](https://git.example.com/example-org/proof-of-fix/pulls/194) (#193) found that funders break even only with about **139,000 / 69,000 / 27,000 outside requests a weekly cycle at a $0.05 / $0.10 / $0.25 margin**.
- Those three targets are one target in dollars. Break-even comes when margin × outside requests reaches about 70 % of what funders spend. That's about **$6,800-7,000 of margin a week** in #193's world, where funders spend about $9,700 a cycle.
- So the question is really this: **where can the network earn about $7,000 of margin a week, at a price buyers already pay?** A count of requests matters only together with what each request can carry.

## The answer

1. **No domain reaches 27,000-139,000 outside requests a week at a price we can serve, today.** The on-chain market for paid verdicts is about **5,000-30,000 requests a week in total** (estimate, below).
   - It's dominated by two things: prediction-market assertions on UMA, and bug-bounty and audit-contest submissions.
   - A new network could realistically win **a few hundred to a few thousand a week** within its first year. That's an estimate, with no public basis for a share.
2. **Most of the volume is priced below our cost.**
   - **Routine prediction-market resolution** pays the proposer about $2-5. UMA's own AI proposer drafts a proposal for about half a cent.
   - **Price feeds** are free per update (Pyth Core), or sold by subscription.
   - **One of our checks costs $0.05-0.37 before any margin** ([costs v1](costs-v1.md)). A quorum of three attested judges can't compete on price for questions that one model answers well enough.
3. **The dollar target is within reach only where verdicts are expensive and adversarial.**
   - **Bug-bounty and audit-contest triage is the clearest case.** Contest judging pays about $8-10 an issue (Sherlock's own example). AI audit scans sell for $49-149 a run (Nethermind). Immunefi says AI has pushed report volume up, and that most reports are invalid.
   - **The target in that market:** about 700-900 triage verdicts a week at a $8-10 margin would meet it. Web3 bounty platforms alone may see about 3,000 submissions a week (a rough estimate from one customer's ratios).
   - **Prediction-market disputes** are expensive too ($750 bonds, a token vote), but there are only about 50 a week.
4. **Open code checks first, maths second (for credibility, not money), and prediction-market disputes third.**
   - Code checks with tests and proof-of-concept exploits are checkable, and they're the network's home ground: the one checker image, attested test runs.
   - Lean proofs are checkable, but nobody pays per check today.
   - Prediction-market disputes need verifiably fetched sources (#139's zkTLS, not ready).
   - Insurance claims, disputes and grants are judgment questions with tiny volumes (about 1, 1-10 and 10-30 a week). Leave them for v3's larger panels.
5. **For the paper:** outside revenue can't be counted on to pay funders at today's market sizes.
   - The case that holds is narrower: a **high-price, checkable niche** (security triage) could carry the margin #193 needs, on hundreds of verdicts a week rather than a hundred thousand.
   - It depends on buyers valuing an attested, sealed quorum over one cheap model.
   - #195's item 2 should model margin per domain in dollars, not one flat margin a check.

## Domains

The verifiability tiers follow #195:
- **checkable:** a machine can confirm the answer;
- **partly checkable:** facts from verifiably fetched sources;
- **judgment:** merit, framing, disputes.

"Fit" means how well v2's network (7 judges, 3-judge and 7-judge tiers, a bond of at least 2× the largest bounty, one checker image) can serve the domain without v3.

| Domain | Who pays today | Volume a week (date) | Price per request | Tier | Fit | Main competitor |
|---|---|---|---|---|---|---|
| 1. Prediction-market resolution | Polymarket, Predict.fun and others, via UMA's optimistic oracle | Assertions: about 1,600-23,000 (2025-26; sources conflict, see 1). Escalated to a vote: about 50 (Apr 2026) | Proposer reward about $2-5; AI draft about $0.005; a $750 bond, returned unless disputed | partly checkable | **Low for routine questions** (price); **medium for disputes**, once sources can be proven (#139) | UMA (incumbent); Chainlink CRE's AI consensus; GenLayer (testnet) |
| 2. Dispute resolution | Kleros users (Curate, Reality.eth, escrow, Lemon); AAA-ICDR's AI arbitrator, off-chain | Kleros: about 1-10 cases (estimate). AAA: not public | Kleros: about 30 xDAI a juror vote, about $90 a 3-juror first round (estimate) | judgment | **Low**: judgment, small volume, needs v3's larger panels and longer windows | Kleros; GenLayer; AAA-ICDR |
| 3. Compute and data oracles | DeFi protocols (price feeds, randomness, automation) | Pyth: about 6.2 M price updates (Q4 2025 average). Chainlink Functions: not public, and the product is retired | Pyth Core: free per update. Chainlink VRF / Automation: gas + 20-84 % premium. CRE: not public | checkable (data), not a verdict | **None**: commodity data, priced far below a judged check | Chainlink, Pyth, RedStone, API3 |
| 4. Verifiable AI inference | dApps wanting a model's output on-chain | Paid on-chain volume not public. ORA: 180,000 calls cumulative (undated). OpenGradient: 2 M inferences cumulative (Apr 2026) | ORA: per model, an example of 0.0148 ETH; EigenAI: on request | varies | **Competitors, not customers**: they sell attested inference, we'd sell attested verdicts | ORA, Ritual, EigenAI, OpenGradient, Gensyn Judge, Phala |
| 5. Insurance claims | Nexus Mutual members; InsurAce; Sherlock coverage | Nexus Mutual: about 0.7 claims (estimate, from 104 accepted since 2020). Parametric covers: 0 verdicts | Nexus: a 0.05 ETH claim deposit; assessor rewards removed (Sep 2025). Sherlock: about $22k to escalate to UMA | judgment / partly checkable | **Low**: about one claim a week, and a $6.1 M claim would need a bond far beyond v2's caps | Nexus Mutual's 3-member Claims Committee; UMA |
| 6. Grants and retro funding | Optimism, Gitcoin, Arbitrum, Ethereum Foundation, Deep Funding | About 10-30 applications on average, in bursts of hundreds (2025-26 rounds) | Optimism Grants Council: about 950 OP an application (estimate). Badgeholders and Deep Funding jurors: unpaid | judgment | **Low**: moving to metrics and in-house AI scoring | Optimism's algorithmic Retro Funding (OpenSource Observer); Gitcoin Checker |
| 7. Code checks, audits, bug-bounty triage | Bounty programs (Immunefi), audit contests (Sherlock, Code4rena, Cantina), teams buying AI review | Immunefi: about 85 paid reports (Q1 2026), about 3,100 submissions (rough estimate). HackerOne: about 1,770 valid reports (Jul 2025-Jun 2026, S). Contests: a few hundred issues each | Contest judging about $8-10 an issue (Sherlock). AI scan $49-149 (Nethermind). AI PR review about $1 (Greptile) | **checkable** (with tests and PoCs) to partly | **High**: the checker image, attested test runs and quorum already do this | Immunefi's AI + human triage; Sherlock AI; Zellic V12 (free); CodeRabbit, Greptile |
| 8. Maths and formal proofs | Grant funders (AI for Math Fund), prize sponsors | Mathlib: about 266 PRs opened, about 62 merged (Oct 2026). Erdős problems: a few claims a month | No per-check market. Grants $100k-1 M | **checkable** (Lean's kernel) | **High technically, no money**: the kernel checks the proof; a judge would check that the formal statement says what the informal one means | Lean's kernel itself; Mathlib's reviewers |

### 1. Prediction-market resolution
- **How it works:**
  - On Polymarket, a whitelisted proposer posts a $750 bond with an answer, and anyone may dispute within 2 hours with a matching bond (Polymarket docs, P).
  - A disputed question goes to UMA's token vote. The winner gets its bond back plus half the loser's.
  - Only whitelisted addresses may propose under MOOV2. It started with 37 (S; the launch date is reported as August 2025 by The Block and November 2025 by crypto.news).
- **Volume: the sources don't agree.**
  - UMA passed **100,000 assertions in September 2025** (UMA blog, 2025-10-07, P).
  - In March 2026, UMA wrote of "hundreds of thousands" (UMA blog, 2026-03-10, P).
  - A post relayed from UMA's account says **400,000 assertions, 0.69 % disputed**, and about 100,000 in one month (S, undated).
  - crypto.news says "upward of 7,000 proposals per month" (2026-07-03, S).
  - **Estimate:** 300,000 assertions added between September 2025 and some date in 2026 means 25,000-50,000 a month if that date was 6-12 months later. That's **about 6,000-12,000 a week**. The full range across sources is 1,600-23,000.
- **Disputes:**
  - About 1 % of assertions are disputed (UMA, 2026-03-10, P), and about 0.4 % are substantive disputes rather than early proposals (UMA blog, undated, P).
  - About **230 Polymarket contracts went to a UMA vote in April 2026**, against 79 six months earlier (Bloomberg, 2026-05-26, via KuCoin, S).
  - More than 1,150 Polymarket markets were disputed in January-May 2026, more than in all of 2025 (crypto.news, 2026-07-03, S).
  - An academic snapshot to 2025-10-27 counted 140,582 Polymarket events, 558 of them disputed by users (arXiv 2604.15674, P).
  - The same Bloomberg report says 9 large holders controlled over half of the dispute votes. That's the weakness a sealed, attested quorum addresses.
- **Price:**
  - The proposer's reward is about $2-5 (guides, S).
  - **UMA's AI proposer** ("Optimistic Truth Bot", 90-95 % accuracy, not yet proposing on-chain in March 2026, S) drafts a proposal for about **$0.005** (crypto.news, S).
  - UMA's revenue from final fees and burned bonds isn't public.
- **Other resolvers:**
  - Myriad uses Chainlink CRE (S, 2026).
  - Reality.eth escalates to Kleros; its question counts aren't public.
  - Polymarket's fast crypto price markets settle on Chainlink (S, 2025).
  - Talk of Polymarket bringing resolution in-house is reported but unconfirmed (S).
  - A May 2026 paper's multi-agent LLM oracle was 97.9 % accurate on the 47 % of questions where its agents agreed unanimously (arXiv 2605.30802, P). No production AI resolver publishes paid volume.
- **For us:**
  - **Routine resolution is a price race we lose:** $0.005 against our $0.05-0.37 cost.
  - **The disputes are a real fit:** about 50 a week, each worth a $750 bond or more, where the current vote is criticised as concentrated.
  - **It needs proven sources** (#139: TLSNotary isn't ready, [zktls spike v1](zktls-spike-v1.md)), and a challenge window that suits a 2-hour market. That's a v3 question (ADR 0004's windows are 6-336 hours).

### 2. Dispute resolution
- **Kleros:**
  - **Volume:** Kleros 2.0's beta on Arbitrum passed 100 cases on 2025-09-02 (Kleros blog, P). All-time totals are quoted from "900+" to "2,000+" (S, forum).
    - Estimate: on the order of **1-10 cases a week**.
    - No monthly figure is public. Kleros's subgraph has the counters, but we didn't query it.
  - **Price:** proposed xDAI courts pay 30 xDAI per coherent vote (governance proposals, P). A 3-juror first round is about $90 (estimate).
  - **Status:** v2 is in beta, audited by Certora (2026-03-03, P).
- **Aragon Court** is effectively closed (front end ended 2024-12-01, P).
- **AAA-ICDR's AI arbitrator:**
  - Live since 2025-11-03 for documents-only construction cases up to $25,000 (P).
  - It claims about 35 % lower cost. It publishes no price or case count.
- **GenLayer's "Internet Court":**
  - The project claims about **$0.50 a case** and 20,000-25,000 testnet decisions a day, with mainnet targeted for Q4 2026 (cryptobriefing, 2026-09-07, S).
  - The same article gives a peak of 4,097 a day, so the testnet figures are inconsistent, and testnet decisions aren't paid demand.
  - It's the closest competitor in kind: AI validators reaching consensus on judgment questions.
- **For us:**
  - Judgment, with tiny paid volume.
  - #195 puts disputes in the last tier: larger panels, longer windows, staked challenges.
  - Under v2, only the 3-of-7 and 7-of-7 tiers exist (Article 3).

### 3. Compute and data oracles
- **Chainlink Functions:**
  - Deprecated, with a sunset on 2026-09-01. Subscriptions move to the Chainlink Runtime Environment (CRE) (functions.chain.link, seen 2026-11-09, P).
  - Its pricing was callback gas plus a fixed USD premium per request, paid in LINK. The docs' example was 0.2 LINK.
  - No request counts were ever published.
- **CRE:**
  - Early access. Usage is metered in credits, with no public dollar rate (Chainlink docs, 2026, P).
  - Expanded to 9 new mainnets in Q2 2026, with no execution counts (Chainlink Q2 2026 review, P).
  - Its prediction-market page offers "AI-powered consensus" (P).
  - The multi-LLM corporate-actions pilot with Swift, DTCC and Euroclear reported near-100 % agreement in September 2025. It published no volume or price (S).
- **VRF and Automation** charge gas plus a premium of 20-84 % by chain and payment coin (Chainlink docs, current, P). No 2026 request counts.
- **Pyth:**
  - Core updates are free on EVM, Solana and Sui; Pro charges 1 wei or 1 lamport per verified update (Pyth docs, current, P).
  - About 886,700 updates a day in Q4 2025 (Messari, via coincub, S). That's about **6.2 M a week**.
- **For us: data feeds aren't verdicts, and they're priced near zero.**
  - The only overlap is "ask several LLMs and agree on an answer", which Chainlink now offers inside CRE.
  - That is a competitor with distribution, and no public volume.

### 4. Verifiable AI inference
- **What these projects sell:** they sell a model's output with a proof (opML, TEE, consensus or sampling), mostly by request or subscription. None publishes a current weekly count of paid on-chain requests.
- **ORA (OAO, opML):**
  - Per-model fees in wei. Its docs' Stable Diffusion example is 0.0148 ETH (undated, P).
  - "180,000+ AI inference calls, 500 nodes, 20+ projects" (undated, likely 2024, S).
  - Its docs domain didn't resolve on 2026-11-09.
- **Ritual:**
  - Infernet, then its own chain, with mainnet about 2026-10-26 (S).
  - "8,000+ Infernet nodes" (undated, P).
  - No price, and no request counts.
- **EigenAI (EigenCloud):**
  - Deterministic, verifiable LLM inference (arXiv 2602.00182, January 2026, P).
  - 1 M tokens free, then priced on request.
- **OpenGradient:** 2 M+ inferences and 500,000+ proofs cumulative at its April 2026 mainnet (self-reported, via MEXC, S).
- **Allora:**
  - 692 M inferences cumulative (February 2026, S).
  - These are paid mostly by token emissions, so they're not demand.
- **Gensyn Judge:** verifiable model evaluation, launched in late April 2026 (Gensyn blog, P). No price or usage.
- **Phala / RedPill:**
  - Tens of billions of tokens a day of TEE inference through OpenRouter (September 2026, S).
  - That's off-chain chat traffic, not on-chain verdicts.
- **Bittensor:** about $70 M a year of revenue across its subnets (2026-11-04, S, unaudited). No subnet sells verdicts to contracts.
- **Estimate:** **paid on-chain AI requests are probably in the low thousands a week at most.** The only per-request count, ORA's 180,000, has no stated period.
- **For us: these are the competitors.**
  - Their pitch is "a model's answer, proven". Ours would be "a quorum of different model families, from different operators, sealed then revealed, with a staked challenge".
  - That's worth paying for only where someone gains by bending one model's answer: where money moves on the verdict.

### 5. Insurance claims
- **Nexus Mutual:**
  - Since November 2025, a **3-member Claims Committee** decides each claim, 2 of 3 within 72 hours. Claimants pay a 0.05 ETH deposit (Nexus docs, reviewed August 2026, P).
  - Members' voting rewards were removed by NMPIP-261 (passed 2025-09-15, P).
  - It has paid more than $18.5 M (docs, August 2026, P). Another tally gives $24.7 M across 104 accepted claims since 2020 (AltStreet, 2026-11-01, S).
  - Its largest recent claim: **$6.1 M**, approved by all three members in about 3 hours (October 2026, S).
  - **Estimate:** about 17 accepted a year. If about half are denied, as in the visible 2020-21 records, that's about **0.7 claims a week**.
- **InsurAce:** its one published batch is 155 approved and 18 rejected in the 2022 UST depeg (S).
- **Sherlock coverage:** escalation goes to UMA with a bond of about $22,000 (Sherlock docs, undated, P). No claim counts.
- **Parametric covers** (Etherisc and the Lemonade coalition, about 7,000 Kenyan farmers in 2022-23, P) pay automatically from index data. They involve no claim and no verdict.
- More than 90 % of all-time DeFi insurance payout value was in 2022 (OpenCover, via The Block, S).
- **For us:**
  - About one judgment a week, in bursts around hacks.
  - A claim of millions needs a bond of at least twice the claim under Article 3's rule, far beyond v2's caps.
  - Not a volume market.

### 6. Grants and retroactive funding
- **Optimism Retro Funding:**
  - Rounds 3-5 had about 130 to over 600 projects (Optimism forum, 2024-11-05, P).
  - From Season 7 (2025), badgeholders vote on **evaluation algorithms** run by OpenSource Observer, not on projects (P).
  - Season 8 caps Retro Funding at 20 M OP (P).
- **Optimism Grants Council, Season 7 (first half of 2025):**
  - About 10 M OP granted, about 220 applications (S), 3-4 reviewers each (P).
  - It built its own AI scoring form on OpenAI (2025-06-09, P).
  - One member was paid 30,000 OP for five months.
  - **Estimate:** about 8.5 applications a week, and about 950 OP of council pay per application.
- **Gitcoin:**
  - GG24 (October 2025): a privacy round of 121 applications, 93 accepted (P), and Solutions Development with 22 full applications, 19 funded (P).
  - Its AI reviewer, Checker, has been in use since December 2023 (P). No cost per application is published.
- **Deep Funding:** about 650 juror comparisons by 45 jurors over about 9 months (Gitcoin forum, P). That's about 17 a week, by volunteers.
- **Ethereum Foundation ESP:** application counts aren't public; open grants were paused in 2025 over volume (S).
- **For us:**
  - About 10-30 judgment calls a week, in bursts, and the large programmes already moved to metrics and in-house AI.
  - The pay per application is high, but the volume and the trend are against it.

### 7. Code checks, audits and bug-bounty triage
- **Immunefi:**
  - **Payouts:** Q1 2026 paid $7.87 M across **1,104 paid reports** (about 85 a week), over 230 programmes (KuCoin summary of Immunefi data, S). Total submissions aren't public.
  - **One customer's ratios:** Alchemix's case study, for the 12 months to 2026-10-17 (P):
    - Immunefi's triage closed 89 % of reports before the team saw them;
    - one in four of the rest was valid;
    - "AI has pushed report volume up."
  - **Estimate:** 85 ÷ (0.11 × 0.25) ≈ **3,100 submissions a week**. That rests on one customer's ratios and is highly uncertain.
  - Immunefi filters with "AI triage agents and expert human triagers" (P). Its managed triage has no public price.
- **Audit contests:**
  - **Sherlock** pays judging about 8 % of the pot: $4,000 on a $50,000 contest. A judge is expected to assess about 100 issues a day, and contests run to about 500 issues (Sherlock docs, undated, P).
    - Estimate: **about $8-10 an issue**.
  - **Code4rena** pays judges a share of the pool that isn't public, and retired its validator role in April 2025 (P).
  - **CodeHawks** already runs an AI judge for its unpaid practice contests (P).
  - Contests per month across platforms aren't public.
- **HackerOne (off-chain):**
  - $81 M paid and about 1,950 programmes, July 2024-June 2025 (S).
  - A later report gives 92,194 valid reports for July 2025-June 2026 (S, unverified). That's about 1,770 a week.
    - Estimate: at 5-25 % valid, about 7,000-35,000 submissions a week.
  - HackerOne paused the Internet Bug Bounty in March 2026, because AI-found bugs outpaced maintainers (S).
  - curl ended its bounty on 2026-01-31, after its confirmed rate fell below 5 % (Daniel Stenberg's blog, P).
  - **Triage demand is growing because of AI-written reports.**
- **AI review sold per check:**
  - Greptile: $1 a review beyond a seat's 50 (S, since March 2026).
  - CodeRabbit: $1 per credit of 4 files (S).
  - Nethermind AuditAgent: **$49 or $149 a scan** (P).
  - Zellic V12: reported free (S).
- **Ceiling:**
  - GitHub merged 518.7 M pull requests in 2025, about 10 M a week (Octoverse 2025, S).
  - A reading of Octoverse 2026's chart gives about 220 M a month (S, unverified).
  - Almost none of these needs an attested quorum.
- **For us: the best fit by far.**
  - Submissions with a proof-of-concept or tests are checkable inside the one checker image, and the network already seals, reveals and signs exactly these checks.
  - Prices are high enough to carry a margin, and the buyers are already on-chain.
  - **Where our model's checks would face the same problem:** an AI-written submission flood. A paid check per submission is also an anti-spam fee, as Immunefi's pay-to-submit pricing shows.

### 8. Maths and formal proofs
- **Mathlib:** Lean's community library had **about 266 pull requests opened a week in October 2026** (1,155 in the month), and about 62 a week merged.
  - These are counts from GitHub's public API, made for this study. The merge count may undercount.
  - A May 2026 paper calls review Mathlib's bottleneck (arXiv 2605.07147, P).
- **Erdős problems:**
  - About 1,217 problems are listed (S). 15 moved from open to solved in January-May 2026, 11 credited to AI (S).
  - Epoch's set of 68 open problems has 17 solved since (P).
- **Funding:**
  - The AI for Math Fund gave $17.1 M in 22 awards from 470+ applications in 2026, $100,000-1 M each (Renaissance Philanthropy, P).
  - The Equational Theories Project settled 22 M implications in Lean, 99.995 % automatically (arXiv 2512.07087, P).
- **No live market** pays per Lean proof check or per proof bounty, and we found none. =nil;'s Proof Market sells ZK proof generation, with no public volume (S).
- **For us:**
  - A Lean proof is checked by Lean's kernel, at almost no cost. A judge adds value only on **whether the formal statement says what the informal question means**.
  - That's a small, credible showcase for the paper (#5), not revenue.

## Total against the target

| | Requests a week (estimate) | What one carries |
|---|---|---|
| Whole on-chain paid-verdict market today (domains 1-8) | **about 5,000-30,000**: UMA assertions 1,600-23,000; web3 bounty submissions about 3,000; the rest under 1,000 together | from $0.005 (AI proposal) to $8-10 (contest judging) to $49-149 (AI audit scan) |
| What the network could serve at a margin, without competing on price with one model | **about 1,000-4,000**: web3 triage and contest issues, plus about 50 prediction-market disputes | $1-10 of margin each, if buyers pay incumbents' prices |
| What a new network might win in its first year | **a few hundred to a few thousand** (no public basis for a share) | as above |
| **#193's break-even** | **27,000-139,000** at $0.25-0.05 | about **$7,000 of margin a week** in all |

- **By count, the target is 1-30× the whole market,** and about 7-500× what we could plausibly win.
- **By dollars, it isn't hopeless.** About 700-900 security-triage verdicts a week at a $8-10 margin, or about 5,000 at $1.40, meet #193's $7,000.
  - But the margin is what's left above our cost: a triage check with a PoC run and 3 judge-grade reviews costs more than a medium check's $0.37.
  - And the target grows with the bounty market: funders' spend sets it.
- **Off-chain code review is the only pool far above the target** (millions of pull requests a week). But it pays about $1 a review, and its buyers don't need sealed quorums.
- **Capacity isn't the limit.** 139,000 requests a week at 3 judges each is about 6 model calls a minute per judge seat. The limit is buyers.

## Which domains to open first

1. **Security triage and code checks (checkable, open first).**
   - Bug-bounty submissions with a PoC, audit-contest issues and dedup, and attested CI checks on repositories where money moves on the result.
   - **Why:** the highest prices per verdict, growing demand from AI-written reports, the one checker image already fits, and v2's 3-of-7 tier is enough.
   - **Shadow mode first,** scored against the platforms' published final judgments (contest results are public), as #195's template asks.
2. **Lean statement checks (checkable, for credibility).**
   - Small and unpaid, but the cleanest accuracy record the network can show, and a natural fit with #5.
3. **Prediction-market disputes (partly checkable, after #139).**
   - Only the escalated ones (about 50 a week), not routine proposals.
   - Waits on proven sources and on v3's windows.
4. **Later, after v3 (#132):** insurance claims, disputes, grants. Judgment, a few to tens a week, and they need larger panels and bonds than v2 allows.
5. **Don't enter:** price feeds and generic inference (commodity prices; well-funded incumbents).

## For #195's next steps
- **Item 2 (the simulation):** model outside revenue per domain as **verdicts × (price − cost)**, using this table's prices, rather than one flat margin per check.
  - Start with security triage at 500-4,000 verdicts a week and $1-10 of margin.
  - Add the cost of a triage check, which [costs v1](costs-v1.md) doesn't have yet.
- **Item 3 (ADR 0005):**
  - security triage fits v2's tiers;
  - prediction-market disputes need #139 and shorter windows;
  - insurance, disputes and grants need v3's panels and bonds.

## What's uncertain
- **UMA's weekly volume:** 1,600 or 23,000. Sources a year apart disagree, and the primary figures are cumulative. Dune or UMA's explorer would settle it; we read neither.
- **Bounty submissions:**
  - Total submissions aren't public on Immunefi or HackerOne. The 3,100-a-week estimate rests on one customer's triage ratios.
  - The quarterly payout figures come through a secondary summary.
- **Our cost for a triage verdict** isn't measured. A PoC run on a forked chain may cost more than a medium check.
- **Whether buyers pay for a quorum:** every price here is what buyers pay incumbents (one model, one committee or a token vote). Nothing shows they'd pay more for an attested, sealed, multi-family quorum. Concentrated UMA votes and AI report floods are the arguments that they might.
- **Secondary sources:** many figures are from news or aggregators, some likely AI-written. Each is marked S. None of the S figures is load-bearing alone except UMA's later totals and Immunefi's quarterly counts.
- **Trends:** the market moves fast. Polymarket's resolution may move in-house, Chainlink's CRE adds AI consensus, and GenLayer targets mainnet this quarter. This study is a snapshot as of 2026-11-09.

## Sources (read 2026-11-09)
**1. Prediction markets**
- UMA blog, "100,000 Assertions and Counting" (2025-10-07, P): https://blog.uma.xyz/articles/100k-assertions
- UMA blog, Predict.fun on BNB Chain (2026-03-10, P): https://blog.uma.xyz/articles/uma-powers-market-resolution-for-predict-fun-on-bnb-chain
- UMA blog, recent improvements to the optimistic oracle (undated, P): https://blog.uma.xyz/articles/recent-improvements-to-umas-optimistic-oracle
- crypto.news, how prediction markets resolve (2026-07-03, S): https://crypto.news/how-prediction-markets-resolve-uma-optimistic-oracle/
- Polymarket docs, UMA resolution (P, seen in search snippets; the page didn't load): https://docs.polymarket.com/developers/resolution/UMA
- Bloomberg via KuCoin, dispute votes (2026-05-26, S): https://www.kucoin.com/news/flash/bloomberg-9-whale-wallets-control-over-half-of-polymarket-s-dispute-resolutions
- The Block, MOOV2 (S): https://www.theblock.co/post/366507/polymarket-uma-oracle-update
- arXiv 2604.15674, Polymarket disputes (P): https://arxiv.org/html/2604.15674
- arXiv 2605.30802, multi-agent LLM oracle (May 2026, P): https://arxiv.org/abs/2605.30802
- Polymarket guide, proposer reward (S): https://polymarketguide.gitbook.io/polymarketguide/basics/how-do-markets-resolve

**2. Disputes**
- Kleros development update (2025-09, P): https://blog.kleros.io/kleros-development-update-september-2025
- Certora, Kleros v2 audit (2026-03-03, P): https://www.certora.com/reports/kleros-v2
- Aragon legacy products (P): https://blog.aragon.org/legacy-product-update/
- AAA-ICDR AI arbitrator (P): https://www.adr.org/press-releases/aaa-icdr-ai-arbitrator-now-available/
- cryptobriefing, GenLayer (2026-09-07, S): https://cryptobriefing.com/genlayer-ai-court-validators/

**3-4. Compute oracles and verifiable AI**
- Chainlink Functions, deprecation notice (P): https://functions.chain.link/mainnet
- Chainlink CRE service quotas (P): https://docs.chain.link/cre/service-quotas
- Chainlink Q2 2026 review (P): https://chain.link/blog/quarterly-review-q2-2026
- Chainlink CRE for prediction markets (P): https://chain.link/use-cases/cre-prediction-markets
- Chainlink VRF v2.5 networks (P): https://docs.chain.link/vrf/v2-5/supported-networks
- The Block, Chainlink corporate-actions pilot (S): https://www.theblock.co/post/372820
- Pyth fees (P): https://docs.pyth.network/price-feeds/current-fees
- ORA web3.js plugin (P): https://github.com/ora-io/web3.js-plugin-ora
- Gensyn, Judge (P): https://blog.gensyn.ai/introducing-judge
- EigenAI (arXiv 2602.00182, P): https://arxiv.org/abs/2602.00182

**5. Insurance**
- Nexus Mutual claims history (P): https://docs.nexusmutual.io/overview/claims-history/
- Nexus Mutual claims assessment (P): https://docs.nexusmutual.io/protocol/claims-assessment
- NMPIP-261 (2025-09-15, P): https://forum.nexusmutual.io/t/nmpip-261-reform-the-claims-mechanism-to-build-trust-upgrade-governance-to-formally-use-an-optimistic-model/1790
- AltStreet, Neutrl claims (2026-10-15, S): https://altstreet.investments/news/nexus-mutual-pays-6-1-million-neutrl-claims-acquires-6-7-million-recovery-position-2026-10-15
- Sherlock exploit flow (P): https://docs.sherlock.xyz/coverage/protocols/exploit-flow
- Etherisc, Kenyan farmers (P): https://blog.etherisc.com/etherisc-protects-another-7-000-kenyan-farmers-as-part-of-the-lemonade-crypto-climate-coalition-e169eca3d6bc
- The Block, OpenCover on 2022 payouts (S): https://www.theblock.co/post/221423/more-than-90-of-all-time-defi-insurance-payout-value-was-in-2022-opencover

**6. Grants**
- Optimism, two years of Retro Funding (2024-11-05, P): https://gov.optimism.io/t/lessons-learned-from-two-years-of-retroactive-public-goods-funding/9239
- Optimism, Season 7 missions (P): https://gov.optimism.io/t/season-7-retro-funding-missions/9295
- Optimism, Season 8 budget (P): https://gov.optimism.io/t/budget-board-proposal-for-retro-funding-for-season-8/10097
- Optimism Grants Council, Season 7 retrospective (2025-06-09, P): https://gov.optimism.io/t/grants-council-season-7-retrospective-report/9992
- Gitcoin, GG24 privacy round (2025-11-14, P): https://gitcoin.co/case-studies/gg24-privacy-round-retrospective
- Gitcoin, GG24 solutions development (P): https://gitcoin.co/case-studies/gg24-solutions-development-grants-retrospective
- Gitcoin, Checker (P): https://gov.gitcoin.co/t/introducing-checker/17292
- Gitcoin forum, Deep Funding jurors (P): https://gov.gitcoin.co/t/lessons-from-building-verdict-improving-deep-funding-juror-data-collection/25199

**7. Code checks**
- Immunefi, Alchemix case study (to 2026-10-17, P): https://immunefi.com/case-studies/alchemix/
- Immunefi, bug bounty programme (P): https://immunefi.com/bug-bounty-program/
- KuCoin, Immunefi Q1 2026 (S): https://www.kucoin.com/blog/fr-immunefi-ecosystem-2026-q1-update
- Sherlock, community judging (P): https://docs.sherlock.xyz/audits/judging/community-judging
- Code4rena, judges (P): https://docs.code4rena.com/roles/judges
- Cyfrin, AI First Flights (P): https://docs.cyfrin.io/codehawks/ai-first-flights
- BleepingComputer, HackerOne payouts (S): https://www.bleepingcomputer.com/news/security/hackerone-paid-81-million-in-bug-bounties-over-the-past-year/
- Stingrai, bug bounty statistics 2026 (S, unverified): https://www.stingrai.io/blog/bug-bounty-statistics-2026
- Privacy Guides, Internet Bug Bounty paused (2026-04-17, S): https://www.privacyguides.org/news/2026/04/17/hackerone-pauses-internet-bug-bounty/
- Daniel Stenberg, the end of the curl bug bounty (2026-01-26, P): https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/
- Nethermind AuditAgent pricing (P): https://docs.auditagent.nethermind.io/pricing/pay-per-scan
- Greptile pricing (S): https://aicodereview.cc/blog/greptile-pricing
- GitHub Octoverse 2025, via It's FOSS (S): https://news.itsfoss.com/github-octoverse-2025

**8. Maths**
- arXiv 2605.07147, Mathlib review (May 2026, P): https://arxiv.org/abs/2605.07147
- Mathlib pull requests (P; counted through GitHub's public API, 2026-11-09): https://github.com/leanprover-community/mathlib4/pulls
- Epoch AI, FrontierMath Erdős (P): https://epoch.ai/benchmarks/frontiermath-erdos
- Renaissance Philanthropy, AI for Math Fund 2026 (P): https://www.renaissancephilanthropy.org/ai-for-math-fund-2026-projects
- arXiv 2512.07087, Equational Theories Project (December 2025, P): https://arxiv.org/abs/2512.07087
- Terence Tao's wiki, AI contributions to Erdős problems (P): https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems
