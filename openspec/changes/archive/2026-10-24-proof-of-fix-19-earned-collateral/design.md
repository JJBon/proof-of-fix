# Design

## Context

After #10, a stake stays locked until the last of 4 instalments (archived design D9). That rule is load-bearing: the ablation shows one instalment, or a stake of 10, lets defective work pay.

In the replay, that leaves an honest contributor at day 35 with:
- 573 credits of stake locked (428 of it on accepted work);
- 334 credits of unpaid rewards in escrow;
- 38 credits free.

At GridCraft's pace, the median reward is about 0.4 of the stake (mean stake about 97, mean reward about 80), so one accepted contribution's unpaid reward backs less than one new stake.

Today the code moves money only by ledger transfers between accounts:
- a contribution has a stake account and an escrow account;
- `claw_back` forfeits the escrow and slashes the stake.

## Goals / Non-Goals

**Goals:**
- Let unpaid rewards back new stakes without making any defect cheaper than it is today.
- Keep conservation and the append-only ledger with no new kind of entry.
- Measure the capital gain against the same seeds without pledges.

**Non-Goals:**
- Lowering stakes for reputation.
- Paying instalments faster.
- Lending between contributors (sponsorship already covers newcomers).
- The bounty market (#15).

## Decisions

### D1. A pledge is a transfer, not a lien
A pledge moves money from the backing contribution's escrow account into the new contribution's stake account. The new contribution records each pledge as (backing contribution, amount).

Nothing new is needed in the ledger, and every step is an ordinary entry, so conservation holds by construction.
- *Alternative:* a lien that leaves the money in the escrow. Rejected for two reasons. The backing contribution's instalments would keep paying out money that is backing another stake. And the ledger would need a notion of encumbered balance.

### D2. Parameters (defaults)
| Parameter | Default | Rationale |
|---|---|---|
| `pledge_max_stake_bps` | 5,000 | At most half of a stake is pledged. With the slash table (cosmetic 25 %, wrong result 50 %, crash 100 %) and the cash-first order (D3), only a crash ever reaches the pledge. |
| `pledge_max_escrow_bps` | 5,000 | At most half of a backing contribution's unpaid reward is pledged. The other half stays in its escrow, reachable by its own clawback at once. |
| who may pledge | `sponsor_min_accepted` (1) | One definition of a proven contributor for sponsoring and pledging. |

**Sweeps (in the summary):**
- `pledge_max_stake_bps`: 0 (no pledges, the counterfactual), 2,500, 5,000 and 7,500;
- `pledge_max_escrow_bps`: 5,000 and 10,000.

The defaults stand only if every criterion passes at them, at hunting elasticity 0 as well.

### D3. Forfeit order: the balance part first, then the pledge
A slash takes the severity's share of the stake from the part posted from the balance before touching the pledge. The check fee also comes from the balance part, so with D2's caps a cosmetic slash never reaches the pledge.

A wrong-result slash reaches it only by the check fee (2 % of the stake), because that fee has already come out of the balance part. That residue is measured with the rest.

The pledge is the money that is also another contribution's clawback cover, so this order limits double-counting to crashes.
- *Alternative:* take from the pledge first, keeping the contributor's cash. Rejected: it spends the shared collateral first.
- *Alternative:* take pro rata. Rejected: it's double-counting in every slash.

### D4. A clawback reaches a pledge when it comes back (deferred)
When a backing contribution is clawed back while part of its reward is pledged:
- its remaining escrow is forfeited as today;
- its outstanding pledges are marked as forfeited to the same distribution: the challenger's escrow share and the reward's source.

When the other contribution settles, whatever of each marked pledge is left goes there, not to the contributor. The challenger's pay for the pledged part is therefore delayed until then. The report counts it when it is paid.
- *Alternative:* pull the pledge out of the other contribution at once and require a top-up. Rejected for two reasons. It leaves that contribution under-staked during its window. And withdrawing a contribution that couldn't top up would let its own defect escape.

### D5. Instalments while pledged
Instalments are paid from what remains in the escrow, at most `reward / reward_instalments` each, and the last one pays whatever is left (unchanged code).

A pledge that comes back while the clawback is still open returns to the escrow and is paid with later instalments. One that comes back after the clawback has ended goes to the contributor, because it is their earned reward.

The clawback period doesn't get longer or shorter with pledges. Nothing is paid twice, because the pledged money is in exactly one account at a time.

### D6. Chains
Only an accepted contribution's escrow can be pledged, never a stake. A contribution backed by a pledge can, once accepted, pledge its own reward. Its stake, which still holds the earlier pledge, stays locked until its last instalment.

Each link in a chain therefore needs real accepted work with a reward, and both caps apply at every link. The pledge stacker (D7) tests chains as well as stacking.

### D7. Simulation
- **Pledging contributor:** this is the default behaviour for every contributor with accepted work, attackers included. When the balance is short of a stake, it pledges the smallest amount that covers it within the caps. It pledges from its backing contributions with the largest unpaid reward first, which needs the fewest pledges.
- **Pledge stacker:** it contributes honestly for the first 3 weeks to build accepted work. After that, it submits defective contributions (defect rate 60 %, like a spammer) as fast as its balance and pledges allow. It's added to the spam scenario.
- **Capital criterion:** the replay runs on the same seeds with `pledge_max_stake_bps` at 0. The report gives unaffordable submissions for both runs, as a mean over seeds with standard errors. Pledges pass if they cut unaffordable submissions by at least a third.
- **Report:** pledges made, the amount pledged, pledges lost to slashes and to clawbacks, and the stacker's return.
- **Ablation:** a new row, "no pledges".

### D8. Sponsored stakes aren't pledged
A sponsor posts the whole stake from its own balance (unchanged). A contributor can't mix a sponsor's stake with its own pledges, so one person never stands behind another's pledge.

### D9. What the implementation and the acceptance run changed (task 4.2)
The implementation added these changes beyond the approved artifacts, in the open:
1. **The balance part must cover the check fee:** `pledge_max_stake_bps + check_fee_bps` can't exceed the whole. A sweep at a pledge cap of 100 % let the check fee eat into the pledge, so the full pledge couldn't be returned. The defaults were never affected.
2. **Paying or forfeiting a backing contribution's reward out of another contribution's stake is recorded under the backing contribution.** It's that contribution's reward, so per-contribution returns credit the right work.
3. **The report moves a pledge lost to a slash onto the slashed contribution,** unless the backing contribution was clawed back, since its own clawback would have taken the money.

**Acceptance run v3** (`reports/acceptance-v3.md`):
- **Pledges are safe at the defaults.** Every safety criterion passes at hunting elasticity 0.5 and 1, and the stacker loses money on its defective work.
- **The capital criterion fails:** a 3 % cut against the third required.
- **The cause** is the stake's size relative to the reward at GridCraft's volume (a reward is about 0.8 of the stake in the replay, against 3–6 times in the small scenarios), not the pledge caps. The capital probe shows a lower stake frees capital: −32 % at 40 credits, −59 % at 25.
- **At elasticity 0, two criteria fail:**
  - The abuser's defective work pays. It's driven by one escaped defect that earned about 30 times its stake in a sparse release, which exposes an uncapped reward per contribution.
  - Splitting gains. That comes from adding the stacker to the spam scenario, and also happens with pledges off.
- **Proposed next step (a new ticket, the owner's decision):** a stake indexed to the expected reward, with a cap on a contribution's reward relative to its stake.
- **Defaults are unchanged.** Whether to keep pledges on is the owner's call.

## Risks / Trade-offs

- **Double-counted collateral on crashes.** A crash slash can reach a pledge that is also a backing contribution's clawback cover. It is bounded by the two caps and measured by the stacker. If the stacker gains, the caps tighten or crash slashes come only from the balance part. The simulation decides, and that would be reported as a forced change (as D9 was in #10).
- **The target may not be reached.** At the replay's reward-to-stake ratio of about 0.4, pledges can't cover much. If unaffordable submissions don't fall by a third at the defaults, the report says so with the sweep. The next lever goes to a follow-up: a reputation-based stake, or shorter instalments for small contributions.
- **The challenger is paid later** for the pledged part of a clawback (D4). The incentive still holds, because the amount is fixed when the challenge is upheld.
- **More states for the proofs:** #5 needs a theorem that pledges conserve value, and one for the cash-first bound.
- **More code in the lifecycle.** It's kept to submission, forfeit order and return. Challenges and payouts don't change.
