"""proof-of-fix#15 tasks 1-2: the bounty market's spec scenarios (bounties and pledges, treasury bounties, sealed
rounds for the job, assignment and delivery, payment through the lifecycle, the market fee and refunds)."""

import unittest

from pof import BPS, credits, share
from pof.challenges import Challenges, Proof, ValidatorSet
from pof.ledger import Ledger
from pof.lifecycle import Lifecycle, NeedsPanel
from pof.market import Market, MarketError, seal
from pof.params import AUCTION, DEFAULTS, FEE_SHARES, LEGACY, ParamsError
from pof.payouts import Releases

P = AUCTION  # the sealed rounds tested here (the race is the default since #60)


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"reward_source": "auction"}, {"market_fee_split_bps": {"validators": 10_000}},
                    {"market_fee_bps": 10_000}, {"evaluation_fee": 0}, {"round_days": 0}, {"delivery_days": 0},
                    {"treasury_bounty_cap": 0}, {"treasury_budget": -1}, {"reserve_bps": 0},
                    {"reserve_bps": BPS + 1}, {"trust_points_per_release": 0}):
            with self.assertRaises(ParamsError, msg=bad):
                DEFAULTS.with_(**bad)
        self.assertEqual(sum(P.market_fee_split_bps.values()), BPS)
        with self.assertRaises(ParamsError):  # pledges pay only for released fixes: no escrow share for challengers
            LEGACY.with_(reward_source="market")


class MarketWorld(unittest.TestCase):
    def setUp(self):
        L = self.ledger = Ledger()
        self.infra, self.insurance, self.owner = L.open("infrastructure"), L.open("insurance"), L.open("actor")
        self.users = [L.open("actor") for _ in range(3)]
        self.solvers = [L.open("actor") for _ in range(4)]
        self.challenger = L.open("actor")
        for a in self.users + self.solvers + [self.challenger, self.owner]:
            L.issue(a, credits(2_000), "endowment", "setup", 0)
        self.life = Lifecycle(L, P, self.infra)
        self.vset = ValidatorSet(L)
        for _ in range(12):
            v = L.open("actor")
            L.issue(v, credits(200), "endowment", "setup", 0)
            self.vset.register(v, credits(50), 0)
        self.ch = Challenges(L, P, self.life, self.vset, self.insurance, self.infra)
        self.rel = Releases(L, P, self.life, self.insurance, self.infra, self.owner, challenges=self.ch)
        self.m = Market(L, P, self.life, self.rel, self.infra)

    def tearDown(self):
        self.assertTrue(self.ledger.conserved())

    def pledged(self, target=credits(300), day=1):
        b = self.m.open_bounty(target, day)
        for u, amount in zip(self.users, (target // 2, target // 3, target - target // 2 - target // 3)):
            self.m.pledge(b, u, amount, day)
        return b

    def round_with(self, b, bids, day=2):
        """One sealed bid per (solver index, price), revealed at the deadline; the round closes. Returns the bids
        and the assigned one."""
        entries = [(self.m.commit(b, self.solvers[i], seal(price, f"s{i}"), day), price, f"s{i}") for i, price in bids]
        for e, price, salt in entries:
            self.m.reveal(e, price, salt, b.round_deadline)
        return [e for e, _, _ in entries], self.m.close_round(b, b.round_deadline)


class TestBountiesAndPledges(MarketWorld):
    def test_target_reached(self):
        b = self.pledged()
        self.assertEqual((b.state, self.ledger.balance(b.account)), ("open", credits(300)))
        self.assertEqual(b.round_deadline, 1 + P.round_days)

    def test_target_missed(self):
        before = [self.ledger.balance(u) for u in self.users]
        b = self.m.open_bounty(credits(300), 1)
        self.m.pledge(b, self.users[0], credits(100), 1)
        self.m.expire(b.deadline)
        self.assertEqual(b.state, "refunded")
        self.assertEqual([self.ledger.balance(u) for u in self.users], before)


class TestTreasury(MarketWorld):
    def test_within_the_budget(self):
        b = self.m.fund_treasury(credits(250), 1)
        self.assertEqual((b.state, b.treasury, self.ledger.balance(b.account)), ("open", True, credits(250)))

    def test_over_the_budget(self):
        for _ in range((P.treasury_budget - share(P.treasury_budget, P.matching_share_bps)) // credits(250)):
            self.m.fund_treasury(credits(250), 1)
        with self.assertRaises(MarketError):
            self.m.fund_treasury(credits(250), 1)
        self.assertTrue(any(e.kind == "treasury_refused" for e in self.ledger.events))

    def test_a_large_proposal(self):
        with self.assertRaises(NeedsPanel):
            self.m.fund_treasury(credits(400), 1)
        with self.assertRaises(MarketError):
            self.m.fund_treasury(credits(400), 1, panel_majority=False)
        self.assertEqual(self.m.fund_treasury(credits(400), 1, panel_majority=True).state, "open")
        with self.assertRaises(MarketError):
            self.m.fund_treasury(P.treasury_bounty_cap + 1, 1, panel_majority=True)


class TestSealedRounds(MarketWorld):
    def test_bid_accepted(self):
        b = self.pledged()
        before = self.ledger.balance(self.solvers[0])
        e = self.m.commit(b, self.solvers[0], seal(credits(100), "s"), 2)
        self.assertEqual(e.stake, share(self.m.price_cap(b), P.bounty_stake_bps))
        self.assertEqual(self.ledger.balance(self.solvers[0]), before - e.stake - P.evaluation_fee)
        self.assertIsNone(e.price)  # sealed

    def test_nothing_to_copy(self):
        b = self.pledged()
        e = self.m.commit(b, self.solvers[0], seal(credits(100), "s"), 2)
        with self.assertRaises(MarketError):  # reveals open only after bids close
            self.m.reveal(e, credits(100), "s", b.round_deadline - 1)
        self.m.reveal(e, credits(100), "s", b.round_deadline)
        self.assertFalse(hasattr(e, "solution"))  # a bid is a price: there's no solution to see
        with self.assertRaises(MarketError):  # and no one can bid after seeing it
            self.m.commit(b, self.solvers[1], seal(credits(99), "x"), b.round_deadline)

    def test_reveal_doesnt_match(self):
        b = self.pledged()
        before = self.ledger.balance(self.solvers[0])
        e = self.m.commit(b, self.solvers[0], seal(credits(100), "s"), 2)
        self.assertFalse(self.m.reveal(e, credits(90), "s", b.round_deadline))
        self.m.close_round(b, b.round_deadline)
        self.assertEqual(e.state, "void")
        self.assertEqual(self.ledger.balance(self.solvers[0]), before - P.evaluation_fee)

    def test_price_above_the_cap_is_void(self):
        b = self.pledged()  # 300 pledged: the cap leaves room for the fee, 300 / 1.2 = 250
        entries, _ = self.round_with(b, [(0, credits(100)), (1, credits(260))])
        self.assertEqual(self.m.price_cap(b), credits(250))
        self.assertEqual(entries[1].state, "void")


class TestAssignment(MarketWorld):
    def test_second_price(self):
        b = self.pledged()
        before = [self.ledger.balance(s) for s in self.solvers[1:3]]
        entries, assigned = self.round_with(b, [(0, credits(100)), (1, credits(150)), (2, credits(180))])
        self.assertIs(assigned, entries[0])
        self.assertEqual((b.state, b.price), ("assigned", credits(150)))
        self.assertEqual(self.ledger.balance(assigned.account), assigned.stake + P.evaluation_fee)  # the bond
        self.assertEqual([self.ledger.balance(s) for s in self.solvers[1:3]], before)  # stakes and fees back
        self.assertEqual([e.state for e in b.queue], ["queued", "queued"])

    def test_only_one_bid(self):
        b = self.pledged()
        _, assigned = self.round_with(b, [(0, credits(100))])
        self.assertEqual(b.price, self.m.reserve(b))  # the reserve, not the cap (#40)
        self.assertEqual(b.price, share(credits(250), P.reserve_bps))

    def test_above_the_reserve(self):
        b = self.pledged()  # cap 250, reserve 187.5
        before = self.ledger.balance(self.solvers[1])
        entries, assigned = self.round_with(b, [(0, credits(100)), (1, credits(200))])
        self.assertEqual(entries[1].state, "void")
        self.assertEqual(self.ledger.balance(self.solvers[1]), before - P.evaluation_fee)  # the fee is lost
        self.assertIs(assigned, entries[0])
        self.assertEqual(b.price, self.m.reserve(b))  # the only valid bid: the reserve

    def test_no_reserve(self):
        self.m.params = P.with_(reserve_bps=BPS)  # 100 %: the v3 rule, the cap
        b = self.pledged()
        self.round_with(b, [(0, credits(100))])
        self.assertEqual(b.price, self.m.price_cap(b))

    def test_no_bid(self):
        b = self.pledged()
        self.assertIsNone(self.m.close_round(b, b.round_deadline))
        self.assertEqual((b.state, b.rounds, self.ledger.balance(b.account)), ("open", 2, credits(300)))


class TestDelivery(MarketWorld):
    def test_delivered_in_time(self):
        b = self.pledged()
        entries, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        before = self.ledger.balance(self.solvers[0])
        c = self.m.deliver(e, 78, e.deliver_by, passes=True)
        self.assertEqual((b.state, c.contributor, c.stake), ("won", self.solvers[0], e.stake))
        self.assertEqual(c.state, "checked")
        self.assertEqual(self.ledger.balance(self.solvers[0]), before + P.evaluation_fee)  # fee back; bond is the stake

    def test_not_delivered(self):
        b = self.pledged()
        entries, e = self.round_with(b, [(0, credits(100)), (1, credits(150)), (2, credits(180))])
        nxt = self.m.expire_deliveries(e.deliver_by + 1)
        self.assertEqual(e.state, "failed")
        self.assertEqual(self.ledger.balance(b.account), credits(300) + e.stake)  # the bond went to the bounty
        self.assertEqual([x.solver for x in nxt], [self.solvers[1]])
        self.assertEqual(b.price, min(credits(180), self.m.reserve(b)))  # the next queued price
        self.assertEqual(b.rounds, 1)

    def test_failing_the_gate(self):  # #43: a failed attempt is published, and everyone bids again on what's left
        b = self.pledged()
        entries, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        self.assertIsNone(self.m.deliver(e, 78, e.deliver_by, passes=False))
        self.assertEqual((e.state, b.state, b.rounds, b.published, b.hidden_set), ("failed", "open", 2, [e.id], 2))
        self.assertEqual((entries[1].state, b.queue), ("released", []))
        self.assertTrue(any(ev.kind == "attempt_published" for ev in self.ledger.events))

    def test_failing_the_gate_queue_rule(self):  # the rule before #43, kept for the comparison
        self.m.params = P.with_(failed_reopens_round=False)
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        self.assertIsNone(self.m.deliver(e, 78, e.deliver_by, passes=False))
        self.assertEqual((e.state, b.assigned.solver), ("failed", self.solvers[1]))
        self.assertEqual(b.price, self.m.reserve(b))  # the last queued bid: the reserve
        self.assertEqual(b.hidden_set, 2)  # the hidden tests are burned either way

    def test_runner_up_cant_post_its_stake(self):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150)), (2, credits(180))])
        self.ledger.transfer(self.solvers[1], self.infra, self.ledger.balance(self.solvers[1]), "fee", "x", 3)
        self.m.fail(e, 4)
        self.assertEqual(b.assigned.solver, self.solvers[2])  # the broke runner-up was skipped
        self.assertEqual(b.queue, [])


class TestPayment(MarketWorld):
    def delivered(self, bids):
        b = self.pledged()
        _, e = self.round_with(b, bids)
        c = self.m.deliver(e, 78, e.deliver_by - 1, passes=True)
        r = self.rel.open_release(c.submitted_day)
        self.rel.ship_beta(r, [c], c.submitted_day)
        return b, c

    def instalments(self, c):
        day = c.settled_day + 1
        for _ in range(P.reward_instalments):
            self.rel.close_release(self.rel.current, [], day)
            self.rel.open_release(day)
            day += 7
        return day

    def test_paid_on_release_with_fee_and_leftover(self):
        b = self.pledged()
        users_before = [self.ledger.balance(u) for u in self.users]
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        solver_before = self.ledger.balance(self.solvers[0])
        c = self.m.deliver(e, 78, e.deliver_by - 1, passes=True)
        r = self.rel.open_release(c.submitted_day)
        self.rel.ship_beta(r, [c], c.submitted_day)
        self.assertEqual(c.reward, credits(150))
        fee = share(credits(150), P.market_fee_bps)
        self.assertEqual(self.ledger.balance(b.account), credits(300) - credits(150) - fee)
        targets = self.rel.fee_targets()
        paid = {name: sum(x.amount for x in self.ledger.entries_for(b.ref)
                          if x.source == b.account and x.target == targets[name] and x.reason == "payout")
                for name in FEE_SHARES}
        self.assertEqual(sum(paid.values()), fee)
        self.assertEqual(paid["owner"], share(fee, P.market_fee_split_bps["owner"]))
        self.ch.report_review(c, self.ch.reviews[c.id].reviewer, False, c.beta_day + 1)
        self.life.advance(c, c.window_end)
        day = self.instalments(c)
        self.m.settle(day)
        self.assertEqual((b.state, self.ledger.balance(b.account)), ("paid", 0))
        got = self.ledger.balance(self.solvers[0]) - solver_before
        # measured while the bond was locked: the fee back, the price, and the stake back less the check fee
        self.assertEqual(got, P.evaluation_fee + credits(150) + c.stake - c.check_fee)
        refunds = [self.ledger.balance(u) - x for u, x in zip(self.users, users_before)]
        leftover = credits(300) - credits(150) - fee
        self.assertEqual(sum(refunds), leftover)
        self.assertAlmostEqual(refunds[0], leftover // 2, delta=2)  # pro rata: the first pledged half

    def test_winner_slashed(self):
        b, c = self.delivered([(0, credits(100)), (1, credits(150)), (2, credits(180))])
        escrow = c.reward
        ch = self.ch.file(c, self.challenger, Proof("regression", c.id), "crash", c.beta_day + 1, "x")
        self.ch.finalize(ch, c.beta_day + 1)
        self.assertEqual(c.state, "slashed")
        bounty_after_slash = self.ledger.balance(b.account)
        self.assertGreaterEqual(bounty_after_slash, escrow)  # the escrow came back in full (no challenger share)
        nxt = self.m.settle(c.beta_day + 2)
        self.assertEqual(nxt, [])  # #43: it was public in beta; a fresh round opens for what's left
        self.assertEqual((b.state, b.rounds, b.published), ("open", 2, [c.id and self.m._entry_of[c.id].id]))

    def test_the_market_is_the_default(self):
        self.assertEqual((DEFAULTS.reward_source, LEGACY.reward_source), ("market", "pool"))
        self.assertEqual(LEGACY.challenger_escrow_share_bps, 5_000)  # the legacy runs' value


if __name__ == "__main__":
    unittest.main()
