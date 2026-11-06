"""proof-of-fix#60 tasks 2.1-2.3: solvers racing and claiming, fix quality and the gates, the award-mode attacks, and
the comparison across modes."""

import unittest

from pof import BPS
from pof.params import AUCTION
from pof.sim import market_sim as M
from pof.sim.market_world import Issue

RACE = M.MARKET.with_(award_mode="race")
CLAIM = M.MARKET.with_(award_mode="claim")


class TestRacing(unittest.TestCase):
    def test_race_run(self):
        w = M.run("market", 1, RACE, weeks=4)
        r = M.market_report(w, "market", 1)
        self.assertTrue(r["conserved"])
        self.assertTrue(r["market"]["pledges_accounted"])
        self.assertGreater(r["market"]["attempts"], 0)
        self.assertEqual(r["market"]["claims"], 0)
        honest = [a for a in w.actors if a.kind == "solver"]
        for a in honest:  # waste is part of the effort, never more
            self.assertLessEqual(a.stats.get("wasted", 0), a.stats.get("effort", 0))
        self.assertGreater(r["market"]["wasted_share"], 0)
        self.assertFalse(w.attempts and w._quiet())

    def test_claim_run(self):
        w = M.run("market", 1, CLAIM, weeks=4)
        r = M.market_report(w, "market", 1)
        self.assertTrue(r["conserved"])
        self.assertGreater(r["market"]["claims"], 0)
        self.assertEqual(r["market"]["attempts"], 0)

    def test_auction_has_no_gates(self):
        r = M.market_report(M.run("market", 1, AUCTION, weeks=4), "market", 1)
        self.assertEqual((r["market"]["attempts"], r["market"]["claims"], r["market"]["gates_failed"],
                          r["market"]["bundles"]), (0, 0, 0, 0))

    def test_ring_doesnt_race_itself(self):
        w = M.build("market_ring", 1, RACE, ring_size=3)
        w.run(28, drain_days=M.MARKET_DRAIN)
        ring = {a.account for a in w.actors if a.group == "ring"}
        for b in w.market.bounties.values():  # never two of the ring's entries submitted on the same day
            days = [e.day for e in b.entries if e.solver in ring]
            self.assertEqual(len(days), len(set(days)))


class TestRegistrationInTheWorld(unittest.TestCase):
    def world(self, **knobs):
        return M.build("market", 1, RACE, **knobs)

    def test_bundle_pool(self):
        w = self.world()
        floor = w.params.size_floor_lines
        small = [Issue(900 + i, 1, 10 ** 7, 5, estimate=floor // 3 + 1) for i in range(3)]  # two under, three over
        self.assertTrue(w._below_floor(small[0], 1) and w._below_floor(small[1], 1))
        self.assertEqual(w.candidates, [])  # still waiting
        self.assertTrue(w._below_floor(small[2], 1))
        merged = w.candidates[-1]
        self.assertEqual((merged.lines, merged.estimate, w.bundle), (15, 3 * (floor // 3 + 1), []))
        self.assertFalse(w._below_floor(Issue(999, 1, 10 ** 7, 50, estimate=floor), 1))

    def test_inflated_estimates(self):
        w = M.build("mode_inflate", 1, RACE, estimate_error=0.0)
        inflater = next(a for a in w.actors if a.kind == "inflater")
        reporter = next(a for a in w.actors if a.kind == "reporter")
        mine, theirs = Issue(901, 1, 10 ** 7, 12), Issue(902, 1, 10 ** 7, 12)
        self.assertTrue(w._report(mine, inflater, 1) and w._report(theirs, reporter, 1))
        self.assertEqual((mine.estimate, theirs.estimate), (24, 12))  # its own issue slips over the floor of 20

    def test_registration_paid(self):
        w = self.world()
        reporter = next(a for a in w.actors if a.kind == "reporter")
        before = w.ledger.balance(reporter.account)
        w._report(Issue(903, 1, 10 ** 7, 50), reporter, 1)
        self.assertEqual(before - w.ledger.balance(reporter.account), w.params.registration_fee + w.params.issue_stake)


class TestGates(unittest.TestCase):
    def test_padded_tests(self):
        w = M.build("mode_pad", 1, RACE.with_(mutation_catch_bps=BPS))
        padder = next(a for a in w.actors if a.kind == "test_padder")
        b = type("B", (), {"gate_bar_bps": 7_000})()
        self.assertFalse(any(w._gates(padder, b)[1] for _ in range(20)))  # always caught
        w2 = M.build("mode_pad", 1, RACE.with_(mutation_catch_bps=0, gate_accuracy_bps=0))
        padder2 = next(a for a in w2.actors if a.kind == "test_padder")
        quality, passes = w2._gates(padder2, b)
        self.assertTrue(passes)  # uncaught, it looks like 0.9
        self.assertLess(quality, 0.7)  # what it really is

    def test_auction_never_gates(self):
        w = M.build("mode_pad", 1, AUCTION.with_(mutation_catch_bps=BPS))
        padder = next(a for a in w.actors if a.kind == "test_padder")
        b = type("B", (), {"gate_bar_bps": 7_000})()
        self.assertTrue(w._gates(padder, b)[1])


class TestModeAttacks(unittest.TestCase):
    def test_twins(self):
        for name in M.MODE_ATTACKS:
            atk = [a for a in M.build(name, 1, RACE).actors if a.cohort == "attack"]
            fair = [a for a in M.build(name, 1, RACE, honest_attack=True).actors if a.cohort == "attack"]
            self.assertEqual([a.name for a in atk], [a.name for a in fair])  # the same accounts
            self.assertEqual([a.behaviour.skill for a in atk], [a.behaviour.skill for a in fair])

    def test_variant_partner(self):
        w = M.build("mode_variant", 1, RACE)
        racer = next(a for a in w.actors if a.kind == "variant_racer")
        partner = next(a for a in w.actors if a.kind == "second_account")
        self.assertEqual(racer.cohort, partner.cohort)
        self.assertTrue(racer.behaviour.variants)


class TestComparison(unittest.TestCase):
    def test_mode_metrics(self):
        base = [{"returns": {"solver": {"net_of_effort": 10.0}}, "market": {"wasted_share": 0.5, "bounties": {}},
                 "checking": {}},
                {"returns": {"solver": {"net_of_effort": 20.0}}, "market": {"wasted_share": 0.3,
                                                                            "bounties": {"paid": 4}}, "checking": {}}]
        m = M.mode_metrics(base)
        self.assertEqual(m["solver_net_of_effort"]["mean"], 15.0)
        self.assertEqual(m["wasted_share"]["mean"], 0.4)
        self.assertEqual(m["bounties_paid"]["mean"], 2.0)  # a missing state counts as none
        self.assertNotIn("days_to_fix", m)

    def test_attack_criterion(self):
        r = M.acceptance([1], RACE, weeks=2, only=("mode_inflate",))
        self.assertIn("mode_inflate_gain", r["criteria"])

    def test_summarize_modes(self):
        s = M.summarize_modes([1], weeks=2, sweep_seeds=[1])
        self.assertEqual(set(s["modes"]), {"auction", "race", "claim"})
        self.assertIn("wasted_share", s["modes"]["race"]["compare"])
        self.assertEqual(set(s["sweeps"]), {"race", "claim"})
        self.assertEqual(set(s["sweeps"]["race"]["attempt cost (cost per line)"]),
                         {str(v) for v in (100_000, 500_000, 1_000_000, 2_000_000)})


if __name__ == "__main__":
    unittest.main()


class TestNothingIsFree(unittest.TestCase):  # #64 tasks 2.1-2.2
    def test_false_duplicates_appealed(self):
        w = M.run("market", 1, RACE, weeks=6, duplicate_false_bps=BPS)  # every honest fix on a failed bounty flagged
        r = M.market_report(w, "market", 1)
        self.assertTrue(r["conserved"])
        self.assertGreater(r["market"]["false_duplicates"], 0)
        self.assertGreater(r["market"]["duplicate_appeals_won"], 0)  # accurate juries mostly clear them
        self.assertLessEqual(r["market"]["duplicate_appeals_won"], r["market"]["duplicate_appeals"])

    def test_appeal_jury_one_per_provider_first(self):
        for n in (3, 5):
            w = M.build("market", 1, RACE.with_(duplicate_appeal_jury=n))
            w.checks.exam()
            b = type("B", (), {"entries": [], "attempting": set()})()
            votes = w._appeal_votes(b, independent=True)
            fams = [w.checks.checking.evaluators[x].family for x, _, _ in votes]
            self.assertEqual(len(votes), n)
            self.assertEqual(len(set(fams[:3])), 3)  # three providers before any repeats

    def test_fake_attempts(self):
        w = M.run("mode_fake", 5, RACE, weeks=4)  # seed 5: a cheap attacker that attempts often
        socks = [a for a in w.actors if a.kind == "sock_account"]
        self.assertTrue(w.ledger.conserved())
        self.assertGreater(sum(a.stats.get("fake_attempts", 0) for a in socks), 0)
        sock_accounts = {a.account for a in socks}
        self.assertFalse(any(e.solver in sock_accounts for b in w.market.bounties.values() for e in b.entries))
        self.assertTrue(all(b.state in ("open", "assigned") for b in (w.market.bounties[i] for i in w.fake_attempts)))
        twin = M.build("mode_fake", 1, RACE, honest_attack=True)
        self.assertEqual([a.kind for a in twin.actors if a.cohort == "attack"][0], "solver")
