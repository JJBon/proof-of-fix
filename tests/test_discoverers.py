"""proof-of-fix#34 tasks 1-2: issue stakes with a finder's fee, quadratic matching, and refunds in proportion to what
each source put in (spec delta scenarios for bounty-market)."""

import unittest

from pof import BPS, credits, share
from pof.market import MarketError, seal
from pof.params import DEFAULTS, ParamsError

from test_market import MarketWorld, P


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"issue_stake": 0}, {"finder_fee_bps": DEFAULTS.market_fee_bps},
                    {"matching_share_bps": 10_001}, {"match_cap_bps": -1}):
            with self.assertRaises(ParamsError, msg=bad):
                DEFAULTS.with_(**bad)


class Discoverers(MarketWorld):
    def paid_bounty(self, report=None, target=credits(300)):
        """A pledged bounty run to the end: assigned, delivered, shipped, accepted and paid in instalments."""
        b = self.m.open_bounty(target, 1, report=report)
        for u, amount in zip(self.users, (target // 2, target // 3, target - target // 2 - target // 3)):
            self.m.pledge(b, u, amount, 1)
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        c = self.m.deliver(e, 78, e.deliver_by - 1, passes=True)
        r = self.rel.open_release(c.submitted_day)
        self.rel.ship_beta(r, [c], c.submitted_day)
        self.ch.report_review(c, self.ch.reviews[c.id].reviewer, False, c.beta_day + 1)
        self.life.advance(c, c.window_end)
        day = c.settled_day + 1
        for _ in range(P.reward_instalments):
            self.rel.close_release(self.rel.current, [], day)
            self.rel.open_release(day)
            day += 7
        self.m.settle(day)
        self.assertEqual(b.state, "paid")
        return b


class TestIssueStakes(Discoverers):
    def test_real_issue_fixed(self):
        reporter = self.challenger
        before = self.ledger.balance(reporter)
        r = self.m.report_issue(reporter, 1)
        self.assertEqual(self.ledger.balance(reporter), before - P.issue_stake)
        b = self.paid_bounty(report=r)
        self.assertEqual(r.state, "rewarded")
        self.assertEqual(self.ledger.balance(reporter), before + share(b.price, P.finder_fee_bps))

    def test_price_cap_leaves_room_for_the_finders_fee(self):
        r = self.m.report_issue(self.challenger, 1)
        b = self.m.open_bounty(credits(300), 1, report=r)
        for u in self.users:
            self.m.pledge(b, u, credits(100), 1)
        self.assertEqual(self.m.price_cap(b), credits(300) * BPS // (BPS + P.market_fee_bps + P.finder_fee_bps))

    def test_junk_confirmed(self):
        before = self.ledger.balance(self.challenger)
        insurance = self.ledger.balance(self.insurance)
        r = self.m.report_issue(self.challenger, 1)
        b = self.m.open_bounty(credits(300), 1, report=r)
        self.m.pledge(b, self.users[0], credits(100), 1)
        user_after_pledge = self.ledger.balance(self.users[0])
        self.assertTrue(self.m.flag_junk(r, 2, panel_majority=True))
        self.assertEqual((r.state, b.state), ("forfeited", "refunded"))
        self.assertEqual(self.ledger.balance(self.challenger), before - P.issue_stake)
        self.assertEqual(self.ledger.balance(self.insurance), insurance + P.issue_stake)
        self.assertEqual(self.ledger.balance(self.users[0]), user_after_pledge + credits(100))  # pledge back

    def test_flag_not_confirmed(self):
        r = self.m.report_issue(self.challenger, 1)
        self.assertFalse(self.m.flag_junk(r, 2, panel_majority=False))
        self.assertEqual(r.state, "posted")
        self.m.open_bounty(credits(300), 2, report=r)  # it can still be funded

    def test_never_funded(self):
        before = self.ledger.balance(self.challenger)
        r = self.m.report_issue(self.challenger, 1)
        b = self.m.open_bounty(credits(300), 1, report=r)
        self.m.pledge(b, self.users[0], credits(10), 1)
        self.m.expire(b.deadline)
        self.assertEqual((b.state, r.state), ("refunded", "returned"))
        self.assertEqual(self.ledger.balance(self.challenger), before)

    def test_funding_your_own_issue_doesnt_pay(self):
        me = self.challenger
        r = self.m.report_issue(me, 1)
        b = self.m.open_bounty(credits(300), 1, report=r)
        self.m.pledge(b, me, credits(300), 1)
        finder = share(credits(150), P.finder_fee_bps)
        market_fee = share(credits(150), P.market_fee_bps)
        self.assertLess(finder, market_fee)  # whatever the price, the fee it pays itself exceeds what it gets back
        with self.assertRaises(MarketError):  # one issue backs one bounty
            self.m.open_bounty(credits(300), 1, report=r)


class TestMatching(Discoverers):
    def test_many_small_pledgers_attract_more(self):
        crowd = [self.ledger.open("actor") for _ in range(10)]
        for a in crowd:
            self.ledger.issue(a, credits(100), "endowment", "setup", 0)
        many = self.m.open_bounty(credits(400), 1)
        one = self.m.open_bounty(credits(400), 1)
        for a in crowd:
            self.m.pledge(many, a, credits(10), 1)
        self.m.pledge(one, self.users[0], credits(100), 1)
        matches = self.m.match(2)
        self.assertGreater(matches.get(many.id, 0), 0)
        self.assertNotIn(one.id, matches)

    def test_within_the_matching_budget(self):
        bounties = []
        for i in range(6):
            b = self.m.open_bounty(credits(2_000), 1)
            for u in self.users + self.solvers:
                self.m.pledge(b, u, credits(30), 1)
            bounties.append(b)
        matches = self.m.match(2)
        self.assertLessEqual(sum(matches.values()), share(P.treasury_budget, P.matching_share_bps))
        self.assertGreater(len(matches), 1)

    def test_capped(self):
        crowd = [self.ledger.open("actor") for _ in range(30)]
        for a in crowd:
            self.ledger.issue(a, credits(100), "endowment", "setup", 0)
        b = self.m.open_bounty(credits(400), 1)
        for a in crowd:
            self.m.pledge(b, a, credits(5), 1)  # weight (30 * sqrt 5)^2 - 150 = 4,350: far above the cap
        self.m.match(2)
        self.assertEqual(b.matched, share(credits(400), P.match_cap_bps))

    def test_a_match_completes_the_target(self):
        crowd = [self.ledger.open("actor") for _ in range(20)]
        for a in crowd:
            self.ledger.issue(a, credits(100), "endowment", "setup", 0)
        b = self.m.open_bounty(credits(150), 1)
        for a in crowd:
            self.m.pledge(b, a, credits(5), 1)  # 100 pledged of 150
        self.m.match(2)
        self.assertEqual((b.state, self.ledger.balance(b.account)), ("open", credits(150)))


class TestUnsolved(Discoverers):
    def test_no_one_can_do_it(self):
        before = self.ledger.balance(self.challenger)
        r = self.m.report_issue(self.challenger, 1)
        b = self.m.open_bounty(credits(300), 1, report=r)
        users_before = [self.ledger.balance(u) for u in self.users]
        for u in self.users:
            self.m.pledge(b, u, credits(100), 1)
        for _ in range(P.bounty_max_rounds):
            self.assertIsNone(self.m.close_round(b, b.round_deadline))
        self.assertEqual((b.state, r.state), ("unsolved", "returned"))
        self.assertEqual([self.ledger.balance(u) for u in self.users], users_before)  # every pledge back
        self.assertEqual(self.ledger.balance(self.challenger), before)  # the stake back, no fee

    def test_a_bid_in_time(self):
        b = self.m.open_bounty(credits(300), 1)
        for u in self.users:
            self.m.pledge(b, u, credits(100), 1)
        for _ in range(P.bounty_max_rounds - 1):
            self.m.close_round(b, b.round_deadline)
        _, e = self.round_with(b, [(0, credits(100))], day=b.round_deadline - 1)
        self.assertEqual((b.state, b.empty_rounds), ("assigned", 0))


class TestRefunds(Discoverers):
    def test_leftover_refunded_after_the_finders_fee(self):
        r = self.m.report_issue(self.challenger, 1)
        before = [self.ledger.balance(u) for u in self.users]
        b = self.paid_bounty(report=r)
        fee, finder = share(b.price, P.market_fee_bps), share(b.price, P.finder_fee_bps)
        refunds = sum(self.ledger.balance(u) - x for u, x in zip(self.users, before))
        self.assertEqual(refunds, credits(300) - b.price - fee - finder - credits(300))  # pledged 300, got the rest

    def test_matched_leftover(self):
        crowd = [self.ledger.open("actor") for _ in range(8)]
        for a in crowd:
            self.ledger.issue(a, credits(100), "endowment", "setup", 0)
        b = self.m.open_bounty(credits(300), 1)
        for a in crowd:
            self.m.pledge(b, a, credits(25), 1)  # 200 pledged
        self.m.match(2)
        self.assertGreater(b.matched, 0)
        self.ledger.transfer(b.account, self.infra, self.ledger.balance(b.account) - credits(90), "fee", "x", 3)
        insurance, crowd_before = self.ledger.balance(self.insurance), [self.ledger.balance(a) for a in crowd]
        self.m._refund_inputs(b, 3)
        to_treasury = self.ledger.balance(self.insurance) - insurance
        to_pledgers = sum(self.ledger.balance(a) - x for a, x in zip(crowd, crowd_before))
        total_in = credits(200) + b.treasury_in
        self.assertAlmostEqual(to_treasury, credits(90) * b.treasury_in // total_in, delta=10)
        self.assertEqual(to_pledgers + to_treasury, credits(90))  # nothing lost, and no pledger profits from the match


if __name__ == "__main__":
    unittest.main()
