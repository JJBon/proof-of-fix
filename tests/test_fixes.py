"""proof-of-fix#10 tasks 1-4: the spec deltas' scenarios (sponsored stakes, instalments and clawback, maintainer
guardrails, payment from the escrowed reward, review duty, work units, the owner's split changes)."""

import unittest

from pof import credits, share
from pof.challenges import Challenges, Proof, ValidatorSet
from pof.ledger import Ledger
from pof.lifecycle import Lifecycle, LifecycleError, NeedsPanel
from pof.params import LEGACY, ParamsError
from pof.payouts import PanelNeeded, Releases


class World(unittest.TestCase):
    maintainers = ()

    def setUp(self):
        L = self.ledger = Ledger()
        self.infra, self.insurance = L.open("infrastructure"), L.open("insurance")
        self.dev, self.newcomer, self.challenger, self.owner = (L.open("actor") for _ in range(4))
        self.other_maintainer = L.open("actor")
        for a in (self.dev, self.challenger, self.owner, self.other_maintainer):
            L.issue(a, credits(5_000), "endowment", "setup", 0)
        roles = {"owner": self.owner, "other": self.other_maintainer}
        self.life = Lifecycle(L, LEGACY, self.infra, maintainers={roles[m] for m in self.maintainers})
        self.vset = ValidatorSet(L)
        self.vals = []
        for _ in range(12):
            v = L.open("actor")
            L.issue(v, credits(200), "endowment", "setup", 0)
            self.vset.register(v, credits(50), 0)
            self.vals.append(v)
        self.ch = Challenges(L, LEGACY, self.life, self.vset, self.insurance, self.infra)
        self.rel = Releases(L, LEGACY, self.life, self.insurance, self.infra, self.owner, challenges=self.ch)

    def tearDown(self):
        self.assertTrue(self.ledger.conserved())

    def checked(self, who=None, lines=78, sponsor=None, day=1):
        c = self.life.submit(who or self.dev, lines, day, sponsor=sponsor)
        self.life.run_checks(c, True, day)
        return c

    def accepted(self, who=None, sponsor=None):
        r = self.rel.open_release(0)
        c = self.checked(who, sponsor=sponsor)
        self.rel.ship_beta(r, [c], 1)
        self.ch.report_review(c, self.ch.reviews[c.id].reviewer, False, 2)
        self.life.advance(c, c.window_end)
        return r, c


def later_releases(t, c, n):
    """Close the open release and open n more, the first the day after the contribution was accepted."""
    day = c.settled_day + 1
    out = {}
    for _ in range(n):
        out = t.rel.close_release(t.rel.current, [], day)
        t.rel.open_release(day)
        day += 7
    return day, out


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"reward_instalments": 0}, {"reward_weight_cap_lines": 0}, {"review_bond": 0},
                    {"challenger_escrow_share_bps": 10_001}, {"max_declines_bps": -1}):
            with self.assertRaises(ParamsError, msg=bad):
                LEGACY.with_(**bad)

    def test_one_change_split_into_eight(self):
        for n in (80, 800, 1_200, LEGACY.reward_weight_cap_lines):  # up to the cap (design: risk above it)
            parts = sum(LEGACY.reward_weight_for(n // 8) for _ in range(8))
            self.assertLessEqual(parts, LEGACY.reward_weight_for(n), n)
        self.assertGreater(8 * LEGACY.stake_for(100), LEGACY.stake_for(800))  # each part pays its own stake


class TestSponsoredStakes(World):
    def test_only_proven_contributors_sponsor(self):
        before = self.ledger.entries
        with self.assertRaises(LifecycleError):
            self.life.submit(self.newcomer, 78, 1, sponsor=self.dev)  # dev has no accepted contribution yet
        self.assertEqual(self.ledger.entries, before)

    def test_a_newcomer_is_sponsored(self):
        self.accepted(self.dev)
        before = self.ledger.balance(self.dev)
        c = self.life.submit(self.newcomer, 78, 9, sponsor=self.dev)
        self.assertEqual(self.ledger.balance(self.newcomer), 0)
        self.assertEqual(before - self.ledger.balance(self.dev), c.stake)

    def test_a_sponsored_contribution_is_slashed(self):
        r, _ = self.accepted(self.dev)
        self.rel.close_release(r, [], 7)
        r2 = self.rel.open_release(8)
        c = self.checked(self.newcomer, sponsor=self.dev, day=8)
        self.rel.ship_beta(r2, [c], 8)
        ch = self.ch.file(c, self.challenger, Proof("bug", c.id), "wrong_result", 9, "b")
        self.ch.finalize(ch, 9)
        net = Ledger.net(self.ledger.entries_for(c.ref))
        forfeited = share(c.stake, LEGACY.severity_slash_bps["wrong_result"])
        self.assertEqual(net[self.dev], -c.check_fee - forfeited)  # the sponsor bears it
        self.assertEqual(net.get(self.newcomer, 0), 0)


class TestInstalmentsAndClawback(World):
    def test_paid_in_instalments(self):
        r, c = self.accepted()
        self.assertEqual(self.ledger.balance(c.escrow_account), c.reward)  # nothing paid at acceptance (D9)
        self.assertEqual(self.ledger.balance(c.stake_account), c.stake - c.check_fee)  # stake still locked
        later_releases(self, c, LEGACY.reward_instalments)
        self.assertEqual((c.instalments_left, self.ledger.balance(c.escrow_account)), (0, 0))
        self.assertEqual(self.ledger.balance(c.stake_account), 0)  # returned with the last instalment
        rewards = sum(e.amount for e in self.ledger.entries_for(c.ref) if e.reason == "reward")
        self.assertEqual(rewards, c.reward)

    def test_defect_found_after_acceptance(self):
        r, c = self.accepted()
        later_releases(self, c, 1)  # one instalment paid
        paid = c.reward // LEGACY.reward_instalments
        day = c.settled_day + 9
        ch = self.ch.file(c, self.challenger, Proof("late bug", c.id), "wrong_result", day, "b")
        self.ch.finalize(ch, day)
        unpaid = c.reward - paid
        self.assertEqual(c.clawed_back, unpaid)
        slashed = share(c.stake, LEGACY.severity_slash_bps["wrong_result"])
        net = Ledger.net(self.ledger.entries_for(c.ref))
        self.assertEqual(net[c.contributor], paid - c.check_fee - slashed)  # keeps what was paid; stake slashed (D9)
        self.assertEqual(net[self.challenger], share(unpaid, LEGACY.challenger_escrow_share_bps)
                         + share(slashed, LEGACY.challenger_reward_share_bps))

    def test_after_the_last_instalment(self):
        r, c = self.accepted()
        day, _ = later_releases(self, c, LEGACY.reward_instalments)
        from pof.challenges import ChallengeError
        with self.assertRaises(ChallengeError):
            self.ch.file(c, self.challenger, Proof("too late", c.id), "crash", day, "b")


class TestGuardrails(World):
    maintainers = ("owner", "other")

    def test_approved_by_another_maintainer(self):
        c = self.checked(self.owner)
        r = self.rel.open_release(1)
        with self.assertRaises(NeedsPanel):
            self.rel.ship_beta(r, [c], 1)
        with self.assertRaises(LifecycleError):
            self.life.approve(c, self.owner, 1)  # not by oneself
        self.life.approve(c, self.other_maintainer, 1)
        self.rel.ship_beta(r, [c], 1)
        self.assertEqual(c.state, "in_beta")

    def test_maintainer_declines_with_a_reason(self):
        for _ in range(10):
            self.checked()
        c = self.checked()
        self.life.decline(c, 2, by=self.owner, reason="duplicate of another change")
        self.assertEqual(self.ledger.events[-1].detail, f"by {self.owner}: duplicate of another change")
        self.assertEqual(Ledger.net(self.ledger.entries_for(c.ref)).get(self.dev, 0), 0)

    def test_over_the_limit(self):
        cs = [self.checked() for _ in range(10)]  # 10 % of 10 others' contributions: one decline unaided
        self.life.decline(cs[0], 2, by=self.owner, reason="r")
        with self.assertRaises(NeedsPanel):
            self.life.decline(cs[1], 2, by=self.owner, reason="r")
        self.life.decline(cs[1], 2, by=self.owner, reason="r", panel_majority=False)
        self.assertEqual(cs[1].state, "checked")  # the panel didn't agree: it goes on

    def test_decline_overturned_on_appeal(self):
        for _ in range(10):
            self.checked()
        c = self.checked()
        self.life.decline(c, 2, by=self.owner, reason="r")
        self.life.appeal_decline(c, 3)
        self.life.resolve_decline_appeal(c, overturned=True, day=4)
        self.assertEqual(c.state, "checked")
        self.assertEqual(self.ledger.events[-1].kind, "decline_overturned")
        self.assertIn(self.owner, self.ledger.events[-1].detail)


class TestOnlyMaintainer(World):
    maintainers = ("owner",)

    def test_only_maintainer_needs_a_panel(self):
        c = self.checked(self.owner)
        with self.assertRaises(NeedsPanel):
            self.life.approve(c, None, 1)
        self.life.approve(c, None, 1, panel_majority=True)
        self.assertEqual(c.approved_by, "panel")
        rejected = self.checked(self.owner)
        self.life.approve(rejected, None, 1, panel_majority=False)
        self.assertEqual(rejected.state, "declined")


class TestReviewDuty(World):
    def test_reviewer_drawn(self):
        self.accepted(self.dev)
        for i in range(20):
            r = self.rel.current
            c = self.checked(self.newcomer, sponsor=self.dev, day=1)
            r.shipped = []
            self.rel.ship_beta(r, [c], 1)
            review = self.ch.reviews[c.id]
            self.assertNotIn(review.reviewer, (self.newcomer, self.dev))
            self.assertEqual(self.ledger.balance(review.bond_account), LEGACY.review_bond)

    def test_review_completed(self):
        r, c = self.accepted()
        reviewer = self.ch.reviews[c.id].reviewer
        day, _ = later_releases(self, c, LEGACY.reward_instalments)
        paid = self.rel.close_release(self.rel.current, [], day)
        self.assertEqual(list(paid), [reviewer])  # reviews are paid work: the only work in these releases
        self.assertEqual(Ledger.net(self.ledger.entries_for(f"review:{c.id}")).get(reviewer, 0), 0)  # bond back

    def test_missed_defect(self):
        r, c = self.accepted()
        reviewer = self.ch.reviews[c.id].reviewer
        ch = self.ch.file(c, self.challenger, Proof("late bug", c.id), "wrong_result", 10, "b")
        self.ch.finalize(ch, 10)
        self.ch.settle_due_reviews(10)
        self.assertEqual(Ledger.net(self.ledger.entries_for(f"review:{c.id}"))[reviewer],
                         -share(LEGACY.review_bond, LEGACY.missed_review_penalty_bps))
        settled = self.ch.take_settled_reviews()
        self.assertEqual([x.outcome for x in settled], ["missed"])

    def test_no_report(self):
        r = self.rel.open_release(0)
        c = self.checked()
        self.rel.ship_beta(r, [c], 1)
        reviewer = self.ch.reviews[c.id].reviewer
        from pof.challenges import ChallengeError
        self.life.advance(c, c.window_end)
        with self.assertRaises(ChallengeError):
            self.ch.report_review(c, reviewer, False, c.window_end)
        ch = self.ch.file(c, self.challenger, Proof("bug", c.id), "cosmetic", 10, "b")
        self.ch.finalize(ch, 10)
        self.ch.settle_due_reviews(10)
        net = Ledger.net(self.ledger.entries_for(f"review:{c.id}"))[reviewer]
        self.assertEqual(net, -share(LEGACY.review_bond, LEGACY.missed_review_penalty_bps))


class TestOwnerSplitChange(World):
    def test_a_change_that_would_benefit_the_owner(self):
        self.vset.register(self.owner, credits(50), 0)
        split = dict(LEGACY.release_split_bps, contributors=4_000, validators=3_000)
        new = LEGACY.with_(release_split_bps=split)
        with self.assertRaises(PanelNeeded):
            self.rel.publish(new, 1, by=self.owner)
        self.assertFalse(self.rel.publish(new, 1, by=self.owner, panel_majority=False))
        self.assertEqual(self.rel.params.release_split_bps["validators"], 2_000)
        self.assertTrue(self.rel.publish(new, 2, by=self.owner, panel_majority=True))
        self.assertEqual(self.rel.params.release_split_bps["validators"], 3_000)
        self.assertTrue(self.rel.publish(LEGACY, 3, by=self.challenger))  # anyone else: no panel


if __name__ == "__main__":
    unittest.main()
