# Design

## Context

#43 made CI (attested runners) and judging (AI juries) oracles paid by the bounty: a run fee of 0.3 per runner whose result stands, and a verdict fee of 0.5 per counted verdict. A bounty had to hold more than the oracle reserve (2 runs + 10 verdicts = 5.6), and its price cap left room for it.

Bidders posted a fixed evaluation fee of 2, refunded to the winner, forfeited by void bids, and forfeited on a failed delivery.

A split rejection or inconclusive CI returns the bond, so a solver can repeat borderline attempts while the bounty pays their checks.

## Goals / Non-Goals

**Goals:**
- Whoever causes a check pays for it.
- Funders pay only for the price, the market fee and the finder's fee.
- The split farmer loses.

**Non-Goals:**
- Changing the oracle fees' amounts.
- Changing what checks run.
- Changing who decides a delivery.

## Decisions

### D1. The check deposit
- **Size:** every bid posts a check deposit equal to the oracle reserve (`Params.oracle_reserve`, 5.6 at the defaults), with its stake.
- **The forfeitable part:** the fixed evaluation fee (2) stays, as the part forfeited when no checks run: a void or unrevealed bid, or a late delivery.
- **Losing bids** get the whole deposit back.
- **The assigned bid:** its deposit pays each fee as the checks close, and **the unused part returns** once the delivery is decided (the second jury only runs on a split).
- **A runner-up offered the job** posts its stake and deposit again.
- *Alternative:* charge each check as it runs, from the solver's balance. Rejected: a solver might not hold the balance when a split sends the delivery to a second jury. The deposit guarantees the checks are paid.

### D2. The bounty pays no checks
- The price cap returns to the bounty's balance less the market and finder's fees.
- The minimum target goes: a bounty too small to cover a solver's price plus its checks simply gets no bids and closes unsolved. That's the solver's judgement, as the owner put it.
- Planted cases stay paid from insurance. Appeals of failed runs keep their own fee.

### D3. Pricing in the simulation
- **Expected checks:** an honest solver's break-even adds the expected checks of an attempt: 2 runs, plus 3 verdicts, plus 7 more on a split, at the market's published escalation rate (about 0.44).
- **Divided by the chance of being paid:** like its other costs, checks are paid on every attempt but the price only on success.
- **Attackers who deliver junk** price like honest solvers, to win jobs.

### D4. The split farmer
- A solver delivering cheap junk (cost × 0.3) that the AI evaluators misjudge half the time, whatever their family: its fixes are borderline by design.
- It counts on splits, which return its bond, and on the occasional acceptance.
- It's measured against the same solver fixing honestly, on the same seeds. It must lose significantly.

### D5. The comparison
`checks_paid_by` = "solver" (the default) or "bounty" (#43's rule, kept for the comparison). The report gives the change in funders' cost per paid bounty, mean price, bounties paid and honest solvers' returns.

## Risks / Trade-offs

- **Honest solvers pay for wrongly rejected checks.** At the assumed model accuracy, consensus wrongly rejects about a quarter of good fixes, and each one now also costs the solver its checks (about 3.7 expected). Honest solvers' earnings, already the one open criterion in #43, may fall. The accuracy condition (#47) addresses it.
- **Prices rise by the expected checks over the chance of success.** Funders pay about the same in total for paid bounties, but through the price rather than as fees.
- **Small bounties may get no bids,** where the expected checks don't fit under the reserve. They close unsolved, which is the market deciding they're not worth checking.
