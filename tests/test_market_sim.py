"""proof-of-fix#15 task 3: the market simulation (issues and solvers, the actors, the report and the criteria)."""

import unittest

from pof import BPS
from pof.sim import market_sim as M
from pof.sim.market_world import DELIVERY_CATCH_WITH_CHECKS
from pof.sim.baseline import load, weekly_volume


class TestMarketRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = M.run("market", 1)  # the standard 8 weeks: a 3-week run can end with every attempt failed
        cls.report = M.market_report(cls.world, "market", 1)

    def test_a_market_run(self):
        self.assertTrue(self.world.ledger.conserved())
        self.assertTrue(self.report["market"]["pledges_accounted"])
        self.assertIn("paid", self.report["market"]["bounties"])
        self.assertTrue({"pledged", "treasury"} & set(self.report["market"]["issues"]))

    def test_reported_per_bounty(self):
        for key in ("issues", "bounties", "price_to_cost", "mean_price", "treasury_spend", "treasury_junk",
                    "treasury_within_budget", "pledges_accounted"):
            self.assertIn(key, self.report["market"])
        for key in ("effort", "net_of_effort", "bids", "assigned", "delivered"):
            self.assertIn(key, self.report["returns"]["solver"])

    def test_only_solvers_with_a_job_build(self):
        for a in self.world.actors:  # assigned in the auction; attempting in the race, the default since #60
            if a.behaviour.capacity and a.stats.get("effort"):  # checkers' effort is their re-runs and verdicts
                self.assertTrue(a.stats.get("assigned") or a.stats.get("attempts"), a.name)

    def test_costs_are_private_and_positive(self):
        issue = next(i for i in self.world.issues if not i.junk)
        costs = {a.name: self.world.cost(a, issue) for a in self.world.solvers}
        self.assertTrue(all(c > 0 for c in costs.values()))
        self.assertGreater(len(set(costs.values())), 1)  # skills differ

    def test_no_personal_data(self):
        self.assertTrue(all(a.name.split("-")[0] in ("pledger", "reporter", "solver", "validator", "hunter", "owner",
                                                       "evaluator", "runner")
                            for a in self.world.actors))


class TestIssuesAndBids(unittest.TestCase):
    def test_arrival_rate(self):
        w = M.run("market", 2, weeks=8, issues_per_week=20.0)
        real = [i for i in w.issues if not i.junk]
        self.assertAlmostEqual(len(real) / 8, 20.0, delta=6.0)
        self.assertLess(20.0, weekly_volume(load()))  # the base scenario is smaller than GridCraft's rate

    def test_honest_bid_is_the_break_even_price(self):
        w = M.build("market_bluff", 1)
        w.run(14)
        b = next(b for b in w.market.bounties.values() if b.state in ("open", "assigned", "won", "paid"))
        issue = w.issue_of[b.id]
        solver = w.solvers[0]
        self.assertGreater(w.break_even(solver, b, issue), w.cost(solver, issue))  # risks priced in
        bluffer = next(a for a in w.actors if a.kind == "bluffer")
        price = w._price(bluffer, b, issue)
        if price is not None and price < w.market.reserve(b):
            self.assertEqual(price, int(w.break_even(bluffer, b, issue) * 1.5))

    def test_a_solver_that_fails_more(self):  # #40 design D3
        w = M.build("market", 1)
        w.run(14)
        b = next(b for b in w.market.bounties.values() if b.state in ("open", "assigned", "won", "paid"))
        issue = w.issue_of[b.id]
        a = next(s for s in w.solvers if not w.market.reputation.outcomes.get((s.account, "solver")))
        clean_fail, clean_caught = w.rates(a)
        beh = a.behaviour
        d, q, catch = beh.defect_bps / BPS, beh.incomplete_bps / BPS, DELIVERY_CATCH_WITH_CHECKS
        self.assertAlmostEqual(clean_fail, d * catch + q * catch + (1 - d - q) * beh.false_check_failure_bps / BPS)
        # no record: the default, at the checking layer's published detection rate (#43)
        before = w.break_even(a, b, issue)
        for i in range(3):  # recorded with no points, so only its rates change, not its bond
            w.market.reputation.outcomes.setdefault((a.account, "solver"), {})
            w.market.reputation.outcomes[(a.account, "solver")]["delivery failed"] = i + 1
        self.assertGreater(w.rates(a)[0], clean_fail)
        self.assertGreater(w.break_even(a, b, issue), before)
        w.market.reputation.outcomes[(a.account, "solver")] = {"accepted": 20}
        self.assertLess(w.rates(a)[1], clean_caught)  # a long clean record: less risk priced in

    def test_no_show_never_delivers(self):
        w = M.run("market_noshow", 1, weeks=4)
        for a in w.actors:
            if a.kind == "no_show":
                self.assertFalse(a.stats.get("delivered"))
                self.assertFalse(a.stats.get("effort"))

    def test_ring_sends_one_bidder_per_round(self):
        w = M.run("market_ring", 1, weeks=4, ring_size=4)
        ring = {a.account for a in w.actors if a.group == "ring"}
        for b in w.market.bounties.values():
            for rnd in range(1, b.rounds + 1):
                self.assertLessEqual(sum(1 for e in b.entries if e.round == rnd and e.solver in ring), 1)

    def test_flood_stays_within_budget(self):
        w = M.run("market_flood", 1, weeks=4)
        r = M.market_report(w, "market_flood", 1)
        self.assertTrue(r["market"]["treasury_within_budget"])
        self.assertGreater(r["market"]["treasury_junk"], 0)  # some junk gets through the AI treasury

    def test_failed_defection_leaves_the_market_path(self):
        """#47: the owner's panels draw from their own stream, so failed attempts don't shift the comparison."""
        honest = M.run("market_owner", 1, weeks=4)
        selfish = M.run("market_owner", 1, weeks=4, self_interested=True)
        self.assertGreater(selfish.panels["declines_over_limit"] + selfish.panels["split_changes_refused"], 0)
        self.assertEqual(selfish.owner.stats.get("declined_others", 0), 0)
        self.assertEqual(honest.net(honest.owner), selfish.net(selfish.owner))
        self.assertEqual(len(honest.ledger.entries), len(selfish.ledger.entries))


class TestCriteria(unittest.TestCase):
    def test_acceptance_reports_each_criterion(self):
        r = M.acceptance([1, 2], weeks=3, only=("market", "market_bluff", "market_noshow", "market_owner"))
        for key in ("solver", "validator", "bluffer_gain", "lowballer_gain", "no_show", "owner_gain"):
            self.assertIn(key, r["criteria"])
        self.assertEqual(len(r["runs"]["market_bluff"]), 2)  # each seed, bluffing
        self.assertEqual(len(r["runs"]["market_bluff:variant"]), 2)  # and truthful, kept apart (#43)

    def test_a_failure_is_named(self):
        r = M.acceptance([1], weeks=2, only=("market",), cost_per_line=10**9)  # no job is worth anyone's cost
        self.assertIn("honest solvers earn more than their cost", {f["criterion"] for f in r["failures"]})

    def test_summary_has_its_tables(self):
        s = M.summarize(range(1, 3), weeks=2, sweep_seeds=range(1, 2))
        for key in ("criteria", "elasticity_verdicts", "returns", "market", "sweeps"):
            self.assertIn(key, s)
        self.assertEqual(set(s["sweeps"]), {"cost per line", "pledged share", "treasury junk detection",
                                            "bond (stake share)", "delivery days", "market fee", "issue stake",
                                            "finder's fee", "matching share", "trust floor", "bond discount",
                                            "reserve", "trust points per release",
                                            "model correlation within a family", "evaluator cost per verdict",
                                            "planted share", "jury accept threshold", "jury size",
                                            "model accuracy (added to every family)",
                                            "second jury accept threshold", "enclave compromise",
                                            "attested runners per delivery"})
        self.assertIn("caught_share", s["checking"])
        reserve = s["sweeps"]["reserve"]["7500"]
        self.assertIn("bounties_paid", reserve)
        self.assertIn("bounties_unsolved", reserve)
        self.assertIn("rings", reserve)


if __name__ == "__main__":
    unittest.main()
