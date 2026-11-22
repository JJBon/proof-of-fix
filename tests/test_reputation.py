"""proof-of-fix#37 tasks 1-2: non-transferable reputation (scores from outcomes, recomputable, trust) and its uses in
the market (the bond discount, trust-weighted matching, the treasury's ranking)."""

import unittest

from pof import BPS, credits, share
from pof.challenges import Proof
from pof.params import DEFAULTS, ParamsError
from pof.reputation import Reputation

from test_discoverers import Discoverers
from test_market import P


def earn(case, account, role, n):
    """n positive points, one per release (the cap is per release, #40); the open release is restored."""
    keep = case.life.release
    for i in range(n):
        case.life.release = keep + 1 + i
        case.m.reputation.record(account, role, 1, "test", i, "earned")
    case.life.release = keep


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"points_paid": 0}, {"points_failed": 1}, {"points_forfeited": 0}, {"trust_floor_bps": BPS},
                    {"trust_step_bps": 0}, {"reputation_min_pledge": 0}, {"bond_discount_bps": BPS + 1}):
            with self.assertRaises(ParamsError, msg=bad):
                DEFAULTS.with_(**bad)


class TestScores(Discoverers):
    def test_an_accepted_job(self):
        b = self.paid_bounty()
        solver = self.life.contributions[b.contribution].contributor
        self.assertEqual(self.m.reputation.score(solver, "solver"), P.points_paid)
        self.assertTrue(any(e.kind == "reputation" and e.ref == b.ref and solver in e.detail
                            for e in self.ledger.events))
        for u in self.users:  # each pledged at least the minimum
            self.assertEqual(self.m.reputation.score(u, "funder"), P.points_paid)

    def test_a_failure(self):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        self.m.fail(e, 5)
        self.assertEqual(self.m.reputation.score(self.solvers[0], "solver"), P.points_failed)

    def test_a_slash(self):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        c = self.m.deliver(e, 78, e.deliver_by - 1, passes=True)
        r = self.rel.open_release(c.submitted_day)
        self.rel.ship_beta(r, [c], c.submitted_day)
        ch = self.ch.file(c, self.challenger, Proof("bug", c.id), "crash", c.beta_day + 1, "x")
        self.ch.finalize(ch, c.beta_day + 1)
        self.m.settle(c.beta_day + 2)
        self.assertEqual(self.m.reputation.score(self.solvers[0], "solver"), P.points_slashed)

    def test_a_small_pledge(self):
        tiny = self.ledger.open("actor")
        self.ledger.issue(tiny, credits(50), "endowment", "setup", 0)
        b = self.m.open_bounty(credits(300), 1)
        self.m.pledge(b, tiny, P.reputation_min_pledge - 1, 1)
        self.m.pledge(b, self.users[0], credits(300), 1)
        _, e = self.round_with(b, [(0, credits(100))])
        c = self.m.deliver(e, 78, e.deliver_by - 1, passes=True)
        self.rel.ship_beta(self.rel.open_release(c.submitted_day), [c], c.submitted_day)
        self.ch.report_review(c, self.ch.reviews[c.id].reviewer, False, c.beta_day + 1)
        self.life.advance(c, c.window_end)
        self.m.settle(c.window_end)  # accepted: the points are earned now
        self.assertEqual(self.m.reputation.score(tiny, "funder"), 0)
        self.assertEqual(self.m.reputation.score(self.users[0], "funder"), P.points_paid)

    def test_reporter_scores(self):
        r = self.m.report_issue(self.challenger, 1)
        self.paid_bounty(report=r)
        self.assertEqual(self.m.reputation.score(self.challenger, "reporter"), P.points_rewarded)
        junk = self.m.report_issue(self.challenger, 2)
        self.m.flag_junk(junk, 3, panel_majority=True)
        self.assertEqual(self.m.reputation.score(self.challenger, "reporter"), P.points_rewarded + P.points_forfeited)

    def test_recomputed_from_the_records(self):
        r = self.m.report_issue(self.challenger, 1)
        self.paid_bounty(report=r)
        self.assertEqual(Reputation.recompute(self.ledger), self.m.reputation.scores())

    def test_no_transfer(self):
        public = [name for name in dir(Reputation) if not name.startswith("_")]
        self.assertEqual(sorted(public), ["recompute", "record", "score", "scores", "trust_bps"])  # nothing moves a score


class TestTrust(Discoverers):
    def test_a_newcomer(self):
        self.assertEqual(self.m.reputation.trust_bps(self.ledger.open("actor"), "solver"), P.trust_floor_bps)

    def test_proven(self):
        rep, who = self.m.reputation, self.solvers[0]
        steps = (BPS - P.trust_floor_bps + P.trust_step_bps - 1) // P.trust_step_bps
        earn(self, who, "solver", steps + 2)
        self.assertEqual(rep.trust_bps(who, "solver"), BPS)
        rep.record(who, "solver", P.points_slashed, "test", 9, "slashed")  # a failure takes trust back down
        self.assertLess(rep.trust_bps(who, "solver"), BPS)

    def test_capped_per_release(self):  # #40 design D2
        rep, who = self.m.reputation, self.solvers[0]
        for i in range(3):
            rep.record(who, "solver", 1, "test", i, "accepted")
        self.assertEqual(rep.score(who, "solver"), P.trust_points_per_release)
        self.assertEqual(rep.outcomes[(who, "solver")]["accepted"], 3)  # every outcome is recorded
        self.assertEqual(sum(1 for e in self.ledger.events if e.kind == "reputation" and "+0 accepted" in e.detail), 2)
        rep.record(who, "reporter", 1, "test", 4, "rewarded")  # another role has its own cap
        self.assertEqual(rep.score(who, "reporter"), 1)
        self.life.release += 1  # a new release: it earns again
        rep.record(who, "solver", 1, "test", 8, "accepted")
        self.assertEqual(rep.score(who, "solver"), 2)
        self.assertEqual(Reputation.recompute(self.ledger), rep.scores())

    def test_failures_uncapped(self):
        rep, who = self.m.reputation, self.solvers[0]
        rep.record(who, "solver", 1, "test", 1, "accepted")
        rep.record(who, "solver", P.points_failed, "test", 2, "delivery failed")
        rep.record(who, "solver", P.points_slashed, "test", 3, "slashed")
        self.assertEqual(rep.score(who, "solver"), 1 + P.points_failed + P.points_slashed)

    def test_a_proven_offender(self):
        rep, who = self.m.reputation, self.solvers[2]
        rep.record(who, "reporter", P.points_forfeited, "test", 1, "forfeited")
        self.assertLess(rep.trust_bps(who, "reporter"), P.trust_floor_bps)
        rep.record(who, "reporter", P.points_forfeited, "test", 2, "forfeited")
        self.assertEqual(rep.trust_bps(who, "reporter"), 0)


class TestUses(Discoverers):
    def test_a_proven_solvers_bond(self):
        b = self.pledged()
        full = self.m.stake_for(b)
        self.assertEqual(self.m.stake_for(b, solver=self.solvers[0]), full)  # a newcomer pays the full bond
        earn(self, self.solvers[1], "solver", 4)
        self.assertEqual(self.m.stake_for(b, solver=self.solvers[1]), full - share(full, P.bond_discount_bps))
        e = self.m.commit(b, self.solvers[1], "c", 2)
        self.assertEqual(e.stake, full - share(full, P.bond_discount_bps))

    def test_new_accounts_draw_little(self):
        proven = [self.ledger.open("actor") for _ in range(4)]
        fresh = [self.ledger.open("actor") for _ in range(4)]
        for a in proven + fresh:
            self.ledger.issue(a, credits(100), "endowment", "setup", 0)
        for a in proven:
            earn(self, a, "funder", 4)
        b1, b2 = self.m.open_bounty(credits(400), 1), self.m.open_bounty(credits(400), 1)
        for a in proven:
            self.m.pledge(b1, a, credits(10), 1)
        for a in fresh:
            self.m.pledge(b2, a, credits(10), 1)
        matches = self.m.match(2)
        floor = P.trust_floor_bps / BPS
        self.assertAlmostEqual(matches[b2.id] / matches[b1.id], floor ** 2, delta=0.01)

    def test_ranked_by_trust(self):
        proven, stranger = self.solvers[0], self.solvers[1]
        earn(self, proven, "reporter", 4)
        self.assertGreater(self.m.priority(credits(100), proven), self.m.priority(credits(100), stranger))
        self.assertEqual(self.m.priority(credits(100), proven), credits(100))


if __name__ == "__main__":
    unittest.main()
