"""One contribution from stake to its last reward instalment (specs/contribution-lifecycle).

    submitted --checks fail--> failed_checks          (stake back minus the check fee)
        |  \\--maintainer declines / contributor withdraws--> declined / withdrawn
        v
     checked --(a maintainer's own: another approver)--enter_beta--> in_beta --window closes--> accepted | slashed
                                                                                               |
                                              instalments, one per release; clawback until the last

The stake lives in its own account while the contribution is open, and the reward in its own escrow account.
Whoever posted the stake (the contributor, or a sponsor, proof-of-fix#10) gets it back or bears its forfeit. Where
the reward comes from is the caller's (release payouts); who gets a forfeit is the challenges' (`slash` and
`claw_back` take the distribution).

Part of a stake can be pledged from the unpaid rewards of the contributor's own accepted contributions in clawback
(proof-of-fix#19). A pledge is a transfer from the backing escrow into the stake account (D1); forfeits take the
part posted from the balance first (D3); a pledge goes back to its backing escrow while that contribution is in
clawback, to the contributor after, and where the clawback sent the escrow if the backing was clawed back (D4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import BPS, share
from .ledger import Ledger, LedgerError
from .params import Params

OPEN = ("submitted", "checked", "in_beta")
FINAL = ("failed_checks", "declined", "withdrawn", "accepted", "slashed")


class LifecycleError(ValueError):
    """A step the contribution's state doesn't allow, or one the contributor can't pay for; nothing changed."""


class NeedsPanel(LifecycleError):
    """The step needs a validator panel's majority first (a maintainer's own work, or a decline over the limit)."""


@dataclass
class Contribution:
    id: int
    contributor: str
    changed_lines: int
    risk: str
    stake: int  # the stake locked at submission
    stake_account: str
    escrow_account: str
    submitted_day: int
    sponsor: str | None = None
    state: str = "submitted"
    check_fee: int = 0
    reward: int = 0
    reward_source: str | None = None
    beta_day: int | None = None
    window_end: int | None = None
    extended: bool = False
    open_challenges: int = 0
    settled_day: int | None = None
    slashed: int = 0
    instalments_left: int = 0
    clawed_back: int = 0
    by_maintainer: bool = False
    approved_by: str | None = None
    declined_by: str | None = None
    release: int = 0
    pledges: dict[int, int] = field(default_factory=dict)  # backing contribution id -> pledged amount still here
    pledged_out: int = 0  # this contribution's unpaid reward now in other contributions' stakes
    pledge_slashed: dict[int, int] = field(default_factory=dict)  # backing id -> pledge lost to this one's slash
    pledge_clawed: int = 0  # this contribution's pledged reward forfeited by its own clawback (D4)
    history: list[tuple[int, str]] = field(default_factory=list)

    @property
    def ref(self) -> str:
        return f"contribution:{self.id}"

    @property
    def stake_owner(self) -> str:
        return self.sponsor or self.contributor

    @property
    def in_clawback(self) -> bool:
        return self.state == "accepted" and self.instalments_left > 0

    @property
    def pledged(self) -> int:
        return sum(self.pledges.values())


class Lifecycle:
    def __init__(self, ledger: Ledger, params: Params, infrastructure: str, maintainers: set[str] | None = None) -> None:
        self.ledger = ledger
        self.params = params
        self.infrastructure = infrastructure
        self.maintainers = set(maintainers or ())
        self.contributions: dict[int, Contribution] = {}
        self.accepted_count: dict[str, int] = {}
        self.release = 0  # the open release, set by release payouts
        self._others: dict[int, int] = {}  # release -> others' contributions submitted
        self._declines: dict[tuple[str, int], int] = {}  # (maintainer, release) -> declines of others' work
        self._appeals: dict[int, str] = {}  # contribution id -> appeal stake account
        self._clawed_pledges: dict[int, str | None] = {}  # clawed-back backing id -> its challenger (D4)
        self.reward_per_weight: int | None = None  # the stake index, set by release payouts (proof-of-fix#23)

    # ---------- before beta ----------

    def submit(self, contributor: str, changed_lines: int, day: int, risk: str = "normal",
               sponsor: str | None = None, pledges: list[tuple[Contribution, int]] | None = None,
               stake: int | None = None) -> Contribution:
        """Lock the entry stake for this size and risk class, from the contributor or a sponsor with enough
        accepted contributions, and partly from pledges of the contributor's unpaid rewards (#19). Refused, with
        nothing recorded, if whoever posts it can't cover it or a pledge breaks a limit."""
        if changed_lines < 1:
            raise LifecycleError("a contribution changes at least one line")
        if sponsor is not None:
            if sponsor == contributor:
                raise LifecycleError("a contributor can't sponsor themselves")
            if self.accepted_count.get(sponsor, 0) < self.params.sponsor_min_accepted:
                raise LifecycleError(f"{sponsor} has no accepted contribution, so can't sponsor")
        payer = sponsor or contributor
        if stake is None:
            stake = self.stake_for(changed_lines, risk)
        elif stake < 0 or (stake == 0 and self.params.bounty_stake_bps and not self.params.token_emission_per_period):
            # an explicit stake: a market entry's (proof-of-fix#15); 0 only in a race without stakes (#56 D9), or for
            # a bounty of 0 coin, which has no reward to back (#58)
            raise LifecycleError("a stake is positive")
        pledged = self._check_pledges(contributor, stake, sponsor, pledges or [])
        if self.ledger.balance(payer) < stake - sum(pledged.values()):
            raise LifecycleError(f"{payer} can't cover the stake of {stake}")
        cid = len(self.contributions) + 1
        c = Contribution(cid, contributor, changed_lines, risk, stake, self.ledger.open("stake"),
                         self.ledger.open("escrow"), day, sponsor=sponsor,
                         by_maintainer=contributor in self.maintainers, release=self.release)
        for bid, amount in pledged.items():
            b = self.contributions[bid]
            self.ledger.transfer(b.escrow_account, c.stake_account, amount, "stake", c.ref, day)
            self.ledger.record(day, "pledge", c.ref, f"{amount} pledged from {b.ref}")
            b.pledged_out += amount
            c.pledges[bid] = amount
        if stake - c.pledged:
            self.ledger.transfer(payer, c.stake_account, stake - c.pledged, "stake", c.ref, day)
        self.contributions[cid] = c
        if not c.by_maintainer:
            self._others[self.release] = self._others.get(self.release, 0) + 1
        self._log(c, day, "submitted" + (f" (sponsored by {sponsor})" if sponsor else ""))
        return c

    def stake_for(self, changed_lines: int, risk: str = "normal") -> int:
        """The entry stake now: indexed to the expected reward once releases have published an index (#23)."""
        return self.params.stake_for(changed_lines, risk, self.reward_per_weight)

    def pledgeable(self, b: Contribution) -> int:
        """How much more of b's unpaid reward can be pledged now: a share of what's unpaid (in its escrow or already
        pledged), less what's pledged, and nothing under an open challenge."""
        if not b.in_clawback or b.open_challenges:
            return 0
        escrow = self.ledger.balance(b.escrow_account)
        return max(0, min(escrow, share(escrow + b.pledged_out, self.params.pledge_max_escrow_bps) - b.pledged_out))

    def run_checks(self, c: Contribution, passed: bool, day: int) -> None:
        """The deterministic gate (build, format, lint, tests). The check fee goes to infrastructure either way; a
        contribution that fails gets the rest of its stake back and ends there."""
        self._expect(c, "submitted")
        c.check_fee = share(c.stake, self.params.check_fee_bps)
        if c.check_fee:
            self.ledger.transfer(c.stake_account, self.infrastructure, c.check_fee, "fee", c.ref, day)
        if passed:
            c.state = "checked"
            self._log(c, day, "checks passed")
        else:
            self._refund_stake(c, day)
            self._finish(c, day, "failed_checks")

    def approve(self, c: Contribution, approver: str | None, day: int, panel_majority: bool | None = None) -> None:
        """A maintainer's own contribution needs another maintainer's approval or, where there's none, a validator
        panel's majority (the caller runs the panel and passes its result)."""
        self._expect(c, "checked")
        if not c.by_maintainer:
            raise LifecycleError("only a maintainer's own contribution needs approval")
        if approver is not None:
            if approver == c.contributor or approver not in self.maintainers:
                raise LifecycleError("approval must come from another maintainer")
            c.approved_by = approver
        elif panel_majority is None:
            raise NeedsPanel("no other maintainer: a validator panel decides")
        elif panel_majority:
            c.approved_by = "panel"
        else:
            self._refund_stake(c, day)
            self._finish(c, day, "declined")
            self.ledger.record(day, "decline", c.ref, "a validator panel didn't approve a maintainer's contribution")
            return
        self.ledger.record(day, "approval", c.ref, f"approved by {c.approved_by}")

    def decline(self, c: Contribution, day: int, by: str | None = None, reason: str = "",
                panel_majority: bool | None = None) -> None:
        """A maintainer declines before the beta build: the stake comes back in full, check fee included, and the
        decline is recorded with who and why. Over the maintainer's limit for others' work in this release, a
        validator panel's majority is needed; without it the contribution goes on."""
        self._expect(c, "submitted", "checked")
        if by is not None and by != c.contributor and not c.by_maintainer:
            used = self._declines.get((by, c.release), 0)
            allowed = self.params.max_declines_bps * self._others.get(c.release, 0) // BPS
            if used + 1 > allowed:
                if panel_majority is None:
                    raise NeedsPanel(f"{by} is at the decline limit for release {c.release}: a panel decides")
                if not panel_majority:
                    self.ledger.record(day, "decline_refused", c.ref, f"panel refused {by}'s decline over the limit")
                    return
            self._declines[(by, c.release)] = used + 1
        if c.check_fee:
            self.ledger.transfer(self.infrastructure, c.stake_owner, c.check_fee, "refund", c.ref, day)
        self._refund_stake(c, day)
        c.declined_by = by
        self._finish(c, day, "declined")
        self.ledger.record(day, "decline", c.ref, f"by {by or 'a maintainer'}: {reason or 'no reason given'}")

    def appeal_decline(self, c: Contribution, day: int) -> None:
        """The declined contributor appeals with a small stake (decline_appeal_stake_bps of the stake)."""
        self._expect(c, "declined")
        if c.id in self._appeals or c.declined_by is None:
            raise LifecycleError("only a maintainer's decline can be appealed, once")
        amount = max(1, share(c.stake, self.params.decline_appeal_stake_bps))
        if self.ledger.balance(c.contributor) < amount:
            raise LifecycleError(f"{c.contributor} can't cover the appeal stake of {amount}")
        account = self.ledger.open("astake")
        self.ledger.transfer(c.contributor, account, amount, "stake", c.ref, day)
        self._appeals[c.id] = account

    def resolve_decline_appeal(self, c: Contribution, overturned: bool, day: int) -> None:
        """Overturned: the appeal stake returns, the stake is locked again and the contribution goes to the next
        beta build, recorded against the maintainer. Upheld: the appeal stake goes to infrastructure."""
        account = self._appeals.pop(c.id, None)
        if account is None:
            raise LifecycleError("no open appeal")
        if overturned:
            if self.ledger.balance(c.stake_owner) < c.stake - c.check_fee:
                self._appeals[c.id] = account
                raise LifecycleError(f"{c.stake_owner} can't re-post the stake")
            self.ledger.transfer(account, c.contributor, self.ledger.balance(account), "refund", c.ref, day)
            if c.stake - c.check_fee:  # a stake of 0 (a race without stakes, a 0-coin bounty) has none to re-post
                self.ledger.transfer(c.stake_owner, c.stake_account, c.stake - c.check_fee, "stake", c.ref, day)
            self.ledger.record(day, "decline_overturned", c.ref, f"against {c.declined_by}")
            c.state, c.settled_day = "checked", None
            self._log(c, day, "decline overturned")
        else:
            self.ledger.transfer(account, self.infrastructure, self.ledger.balance(account), "fee", c.ref, day)
            self.ledger.record(day, "decline_upheld", c.ref, f"by {c.declined_by}")

    def withdraw(self, c: Contribution, day: int) -> None:
        """The contributor withdraws before the beta build: the stake comes back minus the check fee if the checks
        already ran."""
        self._expect(c, "submitted", "checked")
        self._refund_stake(c, day)
        self._finish(c, day, "withdrawn")

    # ---------- in beta ----------

    def enter_beta(self, c: Contribution, day: int, reward: int, source: str) -> None:
        """Merged into the next beta build: the reward moves from source into this contribution's escrow, and the
        challenge window opens. A maintainer's own contribution must be approved first."""
        self._expect(c, "checked")
        if c.by_maintainer and c.approved_by is None:
            raise NeedsPanel(f"{c.ref} is a maintainer's own work: it needs another approver")
        if reward < 0:
            raise LifecycleError("a reward can't be negative")
        if reward:
            try:
                self.ledger.transfer(source, c.escrow_account, reward, "escrow", c.ref, day)
            except LedgerError as e:
                raise LifecycleError(str(e)) from e
        c.reward, c.reward_source = reward, source
        c.state, c.beta_day = "in_beta", day
        c.window_end = day + self.params.challenge_window_days
        self._log(c, day, "in beta")

    def challenge_opened(self, c: Contribution, day: int) -> None:
        """A challenge can be filed while the window is open, or during the clawback (until the last instalment)."""
        if c.in_clawback:
            c.open_challenges += 1
            return
        self._expect(c, "in_beta")
        if day >= self.window_end(c):
            raise LifecycleError("the challenge window has closed")
        c.open_challenges += 1

    def challenge_closed(self, c: Contribution, day: int) -> None:
        if c.open_challenges < 1:
            raise LifecycleError("no open challenge")
        c.open_challenges -= 1

    def window_end(self, c: Contribution) -> int:
        if c.window_end is None:
            raise LifecycleError("not in a beta build")
        return c.window_end

    def advance(self, c: Contribution, day: int) -> str:
        """What the window means on this day: 'open', 'extended' (it ended with a challenge pending, so it's
        extended once), 'waiting' (still pending after the extension), or 'accepted' (settled now)."""
        self._expect(c, "in_beta")
        if day < self.window_end(c):
            return "open"
        if c.open_challenges:
            if not c.extended:
                c.extended = True
                c.window_end += self.params.extension_days
                self._log(c, day, "window extended")
                return "extended"
            return "waiting"
        self._accept(c, day)
        return "accepted"

    def slash(self, c: Contribution, severity: str, day: int, forfeit_to: list[tuple[str, int]],
              reward_to: str | None = None) -> int:
        """An upheld challenge in the window: challenger_escrow_share of the escrowed reward goes to `reward_to`
        (the challenger) and the rest back to its source; the severity's share of the stake is forfeited (split by
        forfeit_to, (account, bps) pairs summing to the whole; the remainder to the last one), and the rest of the
        stake returns to whoever posted it. Returns the stake forfeited."""
        self._expect(c, "in_beta")
        if severity not in self.params.severity_slash_bps:
            raise LifecycleError(f"unknown severity {severity!r}")
        if not forfeit_to or sum(bps for _, bps in forfeit_to) != BPS:
            raise LifecycleError("the forfeit distribution must sum to the whole")
        forfeited = min(share(c.stake, self.params.severity_slash_bps[severity]), self._stake_left(c))
        self._forfeit_escrow(c, day, reward_to)
        self._take_from_pledges(c, forfeited)
        left = forfeited
        for i, (account, bps) in enumerate(forfeit_to):
            amount = left if i == len(forfeit_to) - 1 else share(forfeited, bps)
            if amount:
                self.ledger.transfer(c.stake_account, account, amount, "slash", c.ref, day)
            left -= amount
        c.slashed, c.open_challenges = forfeited, 0
        self._refund_stake(c, day)
        self._finish(c, day, "slashed")
        return forfeited

    # ---------- after acceptance: instalments and clawback ----------

    def pay_instalment(self, c: Contribution, day: int) -> int:
        """The next instalment of an accepted contribution's reward (the last one pays whatever is left). Paused
        while a clawback challenge is open. Returns the amount paid."""
        if not c.in_clawback or c.open_challenges:
            return 0
        left = self.ledger.balance(c.escrow_account)
        amount = left if c.instalments_left == 1 else min(left, c.reward // self.params.reward_instalments)
        if amount:
            self.ledger.transfer(c.escrow_account, c.contributor, amount, "reward", c.ref, day)
        c.instalments_left -= 1
        if c.instalments_left == 0:
            self._refund_stake(c, day)  # the stake backs the work until the last instalment (proof-of-fix#10, D9)
        self._log(c, day, f"instalment paid, {c.instalments_left} left")
        return amount

    def claw_back(self, c: Contribution, day: int, reward_to: str | None, severity: str | None = None,
                  forfeit_to: list[tuple[str, int]] | None = None) -> int:
        """An upheld challenge during the clawback: every unpaid instalment is forfeited (challenger_escrow_share
        to `reward_to`, the rest back to its source), and, since the stake is still locked (D9), the severity's
        share of it is slashed like in the window; the rest of the stake returns. Returns the escrow taken."""
        if not c.in_clawback:
            raise LifecycleError(f"{c.ref} isn't in its clawback period")
        taken = self.ledger.balance(c.escrow_account)
        self._forfeit_escrow(c, day, reward_to)
        if c.pledged_out:
            self._clawed_pledges[c.id] = reward_to  # its pledges are forfeited when they come back (D4)
        if severity is not None and forfeit_to:
            forfeited = min(share(c.stake, self.params.severity_slash_bps[severity]), self._stake_left(c))
            self._take_from_pledges(c, forfeited)
            left = forfeited
            for i, (account, bps) in enumerate(forfeit_to):
                amount = left if i == len(forfeit_to) - 1 else share(forfeited, bps)
                if amount:
                    self.ledger.transfer(c.stake_account, account, amount, "slash", c.ref, day)
                left -= amount
            c.slashed = forfeited
        self._refund_stake(c, day)
        c.clawed_back, c.instalments_left, c.open_challenges = taken, 0, 0
        self._log(c, day, "clawed back")
        return taken

    # ---------- internals ----------

    def _accept(self, c: Contribution, day: int) -> None:
        """Accepted: the instalments start at the next release, and the stake stays locked until the last one
        (D9: otherwise a defect proven in the clawback would cost only the unpaid part)."""
        self._finish(c, day, "accepted")
        self.accepted_count[c.contributor] = self.accepted_count.get(c.contributor, 0) + 1
        c.instalments_left = self.params.reward_instalments if c.reward or self.params.zero_reward_instalments else 0
        if not c.instalments_left:
            self._refund_stake(c, day)

    def _forfeit_escrow(self, c: Contribution, day: int, reward_to: str | None) -> None:
        self._forfeit(c.escrow_account, self.ledger.balance(c.escrow_account), c, reward_to, c.ref, day)

    def _forfeit(self, account: str, amount: int, c: Contribution, reward_to: str | None, ref: str, day: int) -> None:
        """Forfeit `amount` of c's reward from `account`: challenger_escrow_share to the challenger, the rest back to
        the reward's source."""
        to_challenger = share(amount, self.params.challenger_escrow_share_bps) if reward_to else 0
        if to_challenger:
            self.ledger.transfer(account, reward_to, to_challenger, "slash", ref, day)
        if amount - to_challenger:
            self.ledger.transfer(account, c.reward_source, amount - to_challenger, "refund", ref, day)

    def _take_from_pledges(self, c: Contribution, forfeited: int) -> None:
        """A forfeit takes the part posted from the balance first (D3); whatever it takes beyond that comes off the
        pledges, in the order they were made."""
        over = forfeited - (self._stake_left(c) - c.pledged)
        for bid in list(c.pledges):
            if over <= 0:
                break
            cut = min(over, c.pledges[bid])
            c.pledges[bid] -= cut
            c.pledge_slashed[bid] = c.pledge_slashed.get(bid, 0) + cut
            self.contributions[bid].pledged_out -= cut
            over -= cut

    def _return_pledges(self, c: Contribution, day: int) -> None:
        """Each pledge goes back to its backing escrow while that contribution is in clawback, to the contributor
        after it, and, if it was clawed back, where the clawback sent its escrow (D4). Paying or forfeiting the
        backing's reward is recorded under the backing contribution, whose reward it is."""
        for bid, amount in c.pledges.items():
            b = self.contributions[bid]
            b.pledged_out -= amount
            if not amount:
                continue
            if bid in self._clawed_pledges:
                self._forfeit(c.stake_account, amount, b, self._clawed_pledges[bid], b.ref, day)
                b.pledge_clawed += amount
            elif b.in_clawback:
                self.ledger.transfer(c.stake_account, b.escrow_account, amount, "refund", c.ref, day)
            else:
                self.ledger.transfer(c.stake_account, b.contributor, amount, "reward", b.ref, day)
        c.pledges = {}

    def _stake_left(self, c: Contribution) -> int:
        return self.ledger.balance(c.stake_account)

    def _check_pledges(self, contributor: str, stake: int, sponsor: str | None,
                       pledges: list[tuple[Contribution, int]]) -> dict[int, int]:
        """The pledges merged per backing contribution, or LifecycleError if any limit is broken."""
        merged: dict[int, int] = {}
        for b, amount in pledges:
            if amount < 1:
                raise LifecycleError("a pledge is positive")
            merged[b.id] = merged.get(b.id, 0) + amount
        if not merged:
            return merged
        if sponsor is not None:
            raise LifecycleError("a sponsored stake can't also be pledged")
        if self.accepted_count.get(contributor, 0) < max(1, self.params.sponsor_min_accepted):
            raise LifecycleError(f"{contributor} has no accepted contribution, so can't pledge")
        if sum(merged.values()) > share(stake, self.params.pledge_max_stake_bps):
            raise LifecycleError("the pledges cover more of the stake than allowed")
        for bid, amount in merged.items():
            b = self.contributions.get(bid)
            if b is None or b.contributor != contributor:
                raise LifecycleError("only the contributor's own accepted contributions can back a pledge")
            if b.open_challenges:
                raise LifecycleError(f"{b.ref} has an open challenge, so nothing can be pledged from it")
            if amount > self.pledgeable(b):
                raise LifecycleError(f"{b.ref} can't back a pledge of {amount}")
        return merged

    def _refund_stake(self, c: Contribution, day: int) -> None:
        self._return_pledges(c, day)
        left = self._stake_left(c)
        if left:
            self.ledger.transfer(c.stake_account, c.stake_owner, left, "refund", c.ref, day)

    def _finish(self, c: Contribution, day: int, state: str) -> None:
        c.state, c.settled_day = state, day
        self._log(c, day, state)

    def _expect(self, c: Contribution, *states: str) -> None:
        if c.state not in states:
            raise LifecycleError(f"{c.ref} is {c.state}, expected {' or '.join(states)}")

    @staticmethod
    def _log(c: Contribution, day: int, what: str) -> None:
        c.history.append((day, what))
