"""The simulated project: actors acting day by day on the mechanism (ledger, lifecycle, challenges, payouts).

One step per day (design D4), a release every `release_every_days`. Each contribution has a hidden defect drawn
from its author's behaviour (design D6): hunters find real defects and file valid proofs, griefers file false
ones, reviewers (proof-of-fix#10) catch some on duty, validators vote on the truth (with an error rate), colluders
vote for their group. Everything random comes from one `random.Random(seed)`, and everything is iterated in a
fixed order, so a run is reproducible.

Panels that #10 adds outside challenges (approving a maintainer's own work, a decline over the limit, a decline
appeal, an owner's split change) are drawn from the validators and vote on the truth with their error rate; they
move no money (a simplification recorded in the change's design).
"""

from __future__ import annotations

import random

from .. import BPS, credits, share
from ..challenges import ChallengeError, Challenges, Proof, ValidatorSet, commitment
from ..ledger import Ledger
from ..lifecycle import Lifecycle, LifecycleError, NeedsPanel
from ..params import Params
from ..payouts import PanelNeeded, Releases
from .actors import SEVERITY_MIX, STACKING, Actor, Behaviour

LOW_EFFORT = ("spammer", "splitter", "padder", "sybil")
REFERENCE_CATCH = credits(2.5)  # what a catch was worth under the first defaults (design D1)


class World:
    def __init__(self, params: Params, seed: int, actors: list[Actor], size_sampler, maintainer: Actor | None = None,
                 mechanism: bool = True, hunt_elasticity: float = 0.5, review_detect_bps: int = 6_000) -> None:
        self.params, self.seed, self.rng = params, seed, random.Random(seed)
        self.owner_rng = self.rng  # the owner's defection panels (the market world gives them their own stream)
        self.actors, self.maintainer, self.mechanism = actors, maintainer, mechanism
        self.hunt_elasticity, self.review_detect_bps = hunt_elasticity, review_detect_bps
        self.sample_size = size_sampler
        L = self.ledger = Ledger()
        self.infra, self.insurance = L.open("infrastructure"), L.open("insurance")
        for a in actors:
            a.account = L.open("actor")
            if a.behaviour.endowment:
                L.issue(a.account, a.behaviour.endowment, "endowment", "setup", 0)
        self.life = Lifecycle(L, params, self.infra, maintainers={maintainer.account} if maintainer else set())
        self.vset = ValidatorSet(L)
        for a in actors:
            if a.behaviour.validator_stake:
                self.vset.register(a.account, a.behaviour.validator_stake, 0)
                a.staked += a.behaviour.validator_stake
        self.challenges = Challenges(L, params, self.life, self.vset, self.insurance, self.infra)
        owner = next((a for a in actors if a.kind == "owner"), None)
        self.owner = owner
        self.releases = Releases(L, params, self.life, self.insurance, self.infra,
                                 owner.account if owner else L.open("actor"), challenges=self.challenges)
        self.by_account = {a.account: a for a in actors}
        self.author, self.defect, self.pending, self.in_beta = {}, {}, [], []
        self.incomplete: set[int] = set()  # contributions that only partly solve their issue (#43): no regression
        self.mine: dict[str, list] = {}  # account -> its contributions, for pledging (proof-of-fix#19)
        self.pledged: dict[int, int] = {}  # contribution id -> amount pledged into its stake
        self.open_challenges, self.finalized = [], []
        self.stream: list[tuple[int, int]] = []  # (day, changed lines) of every contribution, mechanism on or off
        self.release = None
        self.hunt_factor = 1.0
        self.panels = {"approvals": 0, "declines_over_limit": 0, "decline_appeals": 0, "overturned": 0,
                       "split_changes_refused": 0}

    # ---------- the run ----------

    def run(self, days: int, drain_days: int = 40) -> "World":
        day = 0
        for day in range(days + drain_days):
            if day % self.params.release_every_days == 0 and self.mechanism:
                self._release(day)
            if day < days:
                for a in self.actors:
                    self._act(a, day)
            if self.mechanism:
                self._review(day)
                self._judge(day)
                self._settle(day)
            if day >= days and self._quiet():
                break
        if self.mechanism and self.release is not None:
            self.releases.close_release(self.release, self.finalized, day)
            self.release = None
        return self

    def _quiet(self) -> bool:
        return (not self.in_beta and not self.pending and not self.open_challenges
                and not any(c.in_clawback for c in self.life.contributions.values()))

    # ---------- panels (simulated votes on the truth) ----------

    def _panel(self, truth: bool, exclude: set[str], n: int = 3, rng: random.Random | None = None) -> bool:
        rng = rng or self.rng
        try:
            members = self.vset.select(n, f"panel:{rng.getrandbits(64)}", exclude)
        except ChallengeError:
            return truth
        votes = 0
        for m in members:
            voter = self.by_account[m]
            right = rng.randrange(BPS) >= voter.behaviour.vote_error_bps
            votes += 1 if (truth if right else not truth) else 0
        return votes * 2 > len(members)

    # ---------- releases ----------

    def _release(self, day: int) -> None:
        if self.release is not None:
            self.releases.close_release(self.release, self.finalized, day)
            self.finalized = []
        o = self.owner
        if o and o.behaviour.shift_split_to_validators and not o.stats.get("split_tried"):
            o.bump("split_tried")
            split = dict(self.params.release_split_bps, contributors=4_000, validators=3_000)
            new = self.params.with_(release_split_bps=split)
            try:
                self.releases.publish(new, day, by=o.account)
            except PanelNeeded:
                # honest validators don't approve a split change that raises a share the owner holds
                approved = self._panel(False, {o.account}, rng=self.owner_rng)
                if not self.releases.publish(new, day, by=o.account, panel_majority=approved):
                    self.panels["split_changes_refused"] += 1
        self.release = self.releases.open_release(day)
        ready = []
        for c in self.pending:
            if c.state != "checked":
                continue
            if c.by_maintainer and c.approved_by is None:
                self.panels["approvals"] += 1
                found = self.defect.get(c.id) is not None and self.rng.randrange(BPS) < self.review_detect_bps
                self.life.approve(c, None, day, panel_majority=self._panel(not found, {c.contributor}))
                if c.state != "checked":
                    continue
            ready.append(c)
        self.releases.ship_beta(self.release, ready, day)
        self.in_beta += ready
        self.pending = [c for c in self.pending if c.state == "checked" and c not in ready]
        rewards = [c.reward for c in ready] or [0]
        value = (share(share(self.params.base_stake, self.params.challenger_reward_share_bps), 5_000)
                 + share(sum(rewards) // len(rewards), self.params.challenger_escrow_share_bps))
        ratio = max(value, 1) / REFERENCE_CATCH
        self.hunt_factor = min(4.0, max(0.25, ratio ** self.hunt_elasticity))

    # ---------- actors ----------

    @staticmethod
    def _behaviour(a: Actor, day: int) -> Behaviour:
        """The pledge stacker (proof-of-fix#19) and the index gamer (#23) turn at their day; everyone else acts as
        configured."""
        beh = a.behaviour
        if beh.stack_from_day and day >= beh.stack_from_day:
            return beh.turns_to or STACKING
        return beh

    def _act(self, a: Actor, day: int) -> None:
        b = self.rng
        beh = self._behaviour(a, day)
        if beh.submissions_per_week and b.random() < beh.submissions_per_week / 7:
            lines = self.sample_size(b)
            if beh.max_lines:
                lines = min(lines, beh.max_lines)
            parts = max(1, beh.split_into)
            for _ in range(parts):
                self._submit(a, max(1, lines * (8 if parts > 1 else 1) // parts) * max(1, beh.pad_factor), day, beh)
        if beh.hunt_daily_bps:
            rate = min(BPS, int(beh.hunt_daily_bps * self.hunt_factor))
            targets = self.in_beta + [c for c in self.life.contributions.values() if c.in_clawback]
            for c in targets:
                if self.defect.get(c.id) and b.randrange(BPS) < rate:
                    if not any(ch.contribution is c for ch in self.open_challenges):
                        flaky = b.randrange(BPS) < self.params.replay_inconclusive_bps
                        proof = self._proof("found regression", c, flaky)
                        if proof is not None:
                            self._challenge(a, c, proof, self.defect[c.id], day)
        if beh.false_challenges_per_day and self.in_beta and b.random() < beh.false_challenges_per_day:
            c = b.choice(self.in_beta)
            if c.state == "in_beta" and not self.defect.get(c.id):
                bare = b.random() < 0.5
                proof = Proof("claimed regression", None if bare else c.id, flaky=not bare)
                self._challenge(a, c, proof, "wrong_result", day)

    def _submit(self, a: Actor, lines: int, day: int, beh: Behaviour) -> None:
        b = self.rng
        high = b.randrange(BPS) < beh.high_risk_bps
        defect_bps = beh.high_risk_defect_bps if high else beh.defect_bps
        defect = None
        if b.randrange(BPS) < defect_bps:
            pick = b.randrange(BPS)
            for severity, share_bps in SEVERITY_MIX:
                if pick < share_bps:
                    defect = severity
                    break
                pick -= share_bps
        if defect is None and beh.padding_defect_bps and b.randrange(BPS) < beh.padding_defect_bps:
            defect = "cosmetic"  # padding reported as a cosmetic defect (design: risks)
        self.stream.append((day, lines))
        a.actions += 1
        if not self.mechanism:
            return
        risk = "high" if high else "normal"
        stake = self.life.stake_for(lines, risk)  # indexed to the expected reward once releases publish it (#23)
        sponsor, pledges = None, None
        if self.ledger.balance(a.account) < stake:
            if a.sponsor is not None:
                sponsor = a.sponsor.account
            else:
                pledges = self._pledges(a, stake)
        try:
            c = self.life.submit(a.account, lines, day, risk, sponsor=sponsor, pledges=pledges)
        except LifecycleError:
            a.bump("unaffordable")
            return
        (a.sponsor if sponsor else a).staked += c.stake - c.pledged
        self.mine.setdefault(a.account, []).append(c)
        a.bump("submitted")
        if c.pledged:
            self.pledged[c.id] = c.pledged
            a.bump("pledges")
            a.bump("pledged", c.pledged)
        self.author[c.id], self.defect[c.id] = a, defect
        caught = defect is not None and b.randrange(BPS) < beh.checks_catch_bps
        flaky_ci = defect is None and b.randrange(BPS) < beh.false_check_failure_bps
        self.life.run_checks(c, not (caught or flaky_ci), day)
        if c.state != "checked":
            return
        m = self.maintainer
        if m is not None and m is not a:
            spam = a.kind in LOW_EFFORT and b.randrange(BPS) < 3_000  # maintainers notice some low-effort work
            selfish = b.randrange(BPS) < m.behaviour.decline_others_bps
            if spam or selfish:
                self._decline(m, a, c, day, justified=spam or self.defect.get(c.id) is not None)
                if c.state != "checked":
                    return
        self.pending.append(c)

    def _pledges(self, a: Actor, stake: int) -> list | None:
        """The smallest pledge that covers what the balance can't (design D7): from the actor's backing
        contributions with the most pledgeable reward first. None when even the allowed pledge isn't enough."""
        need = stake - self.ledger.balance(a.account)
        if need > share(stake, self.params.pledge_max_stake_bps):
            return None
        room = sorted(((self.life.pledgeable(c), c.id, c) for c in self.mine.get(a.account, ()) if c.in_clawback),
                      key=lambda t: (-t[0], t[1]))
        out = []
        for amount, _, c in room:
            if need <= 0 or amount <= 0:
                break
            take = min(amount, need)
            out.append((c, take))
            need -= take
        return out if need <= 0 else None

    def _decline(self, m: Actor, a: Actor, c, day: int, justified: bool) -> None:
        reason = "low effort" if justified else "maintainer's choice"
        try:
            self.life.decline(c, day, by=m.account, reason=reason)
        except NeedsPanel:
            self.panels["declines_over_limit"] += 1
            self.life.decline(c, day, by=m.account, reason=reason,
                              panel_majority=self._panel(justified, {m.account, c.contributor}, rng=self.owner_rng))
        if c.state != "declined":
            return
        m.bump("declined_others")
        if not justified and a.behaviour.appeals_wrong_decisions:
            try:
                self.life.appeal_decline(c, day)
            except LifecycleError:
                return
            self.panels["decline_appeals"] += 1
            # truth: the decline wasn't justified
            overturned = self._panel(True, {m.account, c.contributor}, rng=self.owner_rng)
            try:
                self.life.resolve_decline_appeal(c, overturned, day)
            except LifecycleError:
                return
            if overturned:
                self.panels["overturned"] += 1
                a.bump("decline_overturned")

    def _proof(self, description: str, c, flaky: bool) -> Proof | None:
        """What a finder can prove: a regression, or (#43) for a fix that only partly solves its issue, a case of
        the issue that still fails, where the rules allow that challenge. None: nothing provable."""
        if c.id not in self.incomplete:
            return Proof(description, c.id, flaky=flaky)
        if not self.params.not_solved_challenges:
            return None  # it broke nothing, so without the challenge there's nothing to prove
        return Proof(f"{description}: a case of the issue still fails", c.id, flaky=flaky, kind="not_solved")

    def _challenge(self, a: Actor, c, proof: Proof, severity: str, day: int) -> None:
        try:
            ch = self.challenges.file(c, a.account, proof, severity, day, beacon=str(self.rng.getrandbits(64)))
        except ChallengeError:
            a.bump("challenge_unaffordable")
            return
        a.actions += 1
        a.staked += ch.stake
        a.bump("challenges")
        if ch.state != "refused":
            self.open_challenges.append(ch)
        else:
            a.bump("refused")

    # ---------- review duty (proof-of-fix#10) ----------

    def _review(self, day: int) -> None:
        for cid, review in sorted(self.challenges.reviews.items()):
            c = review.contribution
            if review.found is not None or c.state != "in_beta" or day < review.drawn_day + 1:
                continue
            reviewer = self.by_account[review.reviewer]
            if self.rng.randrange(BPS) < reviewer.behaviour.no_reveal_bps:
                continue  # forgot: no report this day
            found = self.defect.get(c.id) is not None and self.rng.randrange(BPS) < self.review_detect_bps
            try:
                self.challenges.report_review(c, review.reviewer, found, day)
            except ChallengeError:
                continue
            reviewer.actions += 1
            reviewer.bump("reviews")
            if found:
                flaky = self.rng.randrange(BPS) < self.params.replay_inconclusive_bps
                proof = self._proof("found in review", c, flaky)
                if proof is not None:
                    self._challenge(reviewer, c, proof, self.defect[c.id], day)

    # ---------- judging ----------

    def _judge(self, day: int) -> None:
        for ch in list(self.open_challenges):
            if ch.state in ("voting", "appeal"):
                self._vote(ch, day)
            if ch.state == "decided":
                truth = self.defect.get(ch.contribution.id) is not None and ch.proof.introduced_by == ch.contribution.id
                loser = ch.contribution.contributor if ch.outcome else ch.challenger
                actor = self.by_account.get(loser)
                if (ch.outcome != truth and actor is not None and actor.behaviour.appeals_wrong_decisions
                        and ch.appealed_by is None):
                    try:
                        self.challenges.appeal(ch, loser, day)
                        actor.staked += ch.appeal_stake
                        actor.bump("appeals")
                        continue
                    except ChallengeError:
                        pass
            if ch.state in ("decided", "final") and not ch.applied:
                self.challenges.finalize(ch, day)
                self.open_challenges.remove(ch)
                self.finalized.append(ch)

    def _vote(self, ch, day: int) -> None:
        panel = ch.panels[-1]
        truth = self.defect.get(ch.contribution.id) is not None and ch.proof.introduced_by == ch.contribution.id
        author = self.author.get(ch.contribution.id)
        secrets = {}
        for m in panel.members:
            voter = self.by_account[m]
            if voter.group is not None and author is not None and author.group == voter.group:
                verdict = False  # protect the group's contribution whatever the evidence
            else:
                verdict = truth if self.rng.randrange(BPS) >= voter.behaviour.vote_error_bps else not truth
            secrets[m] = (verdict, f"{m}:{self.rng.getrandbits(32)}")
            self.challenges.commit(ch, m, commitment(*secrets[m]))
        for m in panel.members:
            voter = self.by_account[m]
            if self.rng.randrange(BPS) >= voter.behaviour.no_reveal_bps:
                if self.challenges.reveal(ch, m, *secrets[m]):
                    voter.actions += 1
                    voter.bump("votes")
        self.challenges.close_voting(ch, day)

    def _settle(self, day: int) -> None:
        for c in list(self.in_beta):
            if c.state == "in_beta":
                self.life.advance(c, day)
            if c.state != "in_beta":
                self.in_beta.remove(c)
                self.author[c.id].bump(c.state)

    # ---------- results ----------

    def escaped_regressions(self) -> int:
        """Defective contributions that kept their reward: accepted and never clawed back."""
        return sum(1 for c in self.life.contributions.values()
                   if c.state == "accepted" and self.defect.get(c.id) and not c.clawed_back)

    def wealth(self, a: Actor) -> int:
        """What an actor holds: its account, its validator stake, and (for the owner) its unvested share."""
        total = self.ledger.balance(a.account)
        if a.account in self.vset.stake_account:
            total += self.ledger.balance(self.vset.stake_account[a.account])
        if a is self.owner:
            total += self.ledger.balance(self.releases.owner_vesting)
        return total

    def net(self, a: Actor) -> int:
        return self.wealth(a) - a.behaviour.endowment
