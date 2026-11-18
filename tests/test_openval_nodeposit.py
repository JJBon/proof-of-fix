"""#236, the owner's three deposit-free mechanisms (2026-11-15): reputation before large claims, the shared pot
weighted by impact, and a fee that covers the judges' cost (pof/sim/openval/nodeposit.py), and the rows of
reports/open-validators-measured-v5.md. One test class per switch."""

import math
import unittest
from dataclasses import replace
from statistics import mean

from pof.sim.openval import nodeposit as N
from pof.sim.openval import sizing as Z
from pof.sim.openval.evidence import P0
from pof.sim.openval.net import ISSUE, WEEK, Net
from pof.sim.openval.params import D236, D236R2, PARAMS


def short(pool="hidden", seat="anthropic", n=0, weeks=10, **kw):
    return replace(N.world(pool, seat, n, **kw), weeks=weeks)


def run(actor, p, seed=3):
    return N.NDNet(seed, p, actor.world(), [actor]).run()


def mine(net, party):
    return [s for s in net.subs.values() if s.tier == ISSUE and s.party == party]


class TestDefaults(unittest.TestCase):
    def test_every_switch_is_off_by_default(self):
        for p in (PARAMS, D236, D236R2, P0, Z.BASE):
            self.assertEqual((p.REP_CAP, p.POT, p.JUDGE_FEE), (False, "off", 0.0))
        self.assertEqual((PARAMS.REP_BASE, PARAMS.REP_MULT, PARAMS.REP_ON_REVERSAL, PARAMS.POT_WINDOW_WEEKS),
                         (50.0, 1.0, "zero", 13.0))  # the proposal, fixed before the 40-seed runs

    def test_a_plain_net_refuses_the_switches(self):
        w = short()
        for kw in (dict(REP_CAP=True), dict(POT="equal"), dict(JUDGE_FEE=1.0)):
            with self.assertRaises(ValueError):
                Net(1, replace(P0, **kw), w, [Z.OnMarket(w=w)])

    def test_with_every_switch_off_ndnet_is_v4s_network(self):
        w = short(n=3, find=0.25)
        a, b = Z.Solver(False, w), Z.Solver(False, w)
        old = Net(4, P0, w, [a]).run()
        new = N.NDNet(4, P0, w, [b]).run()
        self.assertAlmostEqual(old.party_net(a.party), new.party_net(b.party), places=6)
        for k in ("paid", "bad_merged", "submitted", "evidence_reversed", "rival_tests"):
            self.assertEqual(old.stats[k], new.stats[k], k)


class TestReputation(unittest.TestCase):
    P = replace(P0, REP_CAP=True)

    def test_a_new_identity_claims_at_most_the_base_and_a_refused_claim_costs_nothing(self):
        w = short()
        net = run(N.BadFix(False, w, fresh=True), self.P)
        subs = mine(net, "bad-fix solver")
        self.assertGreater(len(subs), 20)
        self.assertTrue(all(s.bounty <= self.P.REP_BASE for s in subs))
        net = N.NDNet(3, self.P, w, [Z.OnMarket(w=w)])
        s = net.submit(1.0, 80.0, False, "x", "x", ident="new")
        net.run()
        self.assertEqual(s.state, "refused")
        self.assertEqual(net.parties["x"].costs, 0.0)
        self.assertEqual(net.stats["rep_refused"], 1)

    def test_reputation_is_the_bounties_paid_and_a_reversal_resets_it(self):
        w = short(weeks=20)
        net = run(N.BadFix(False, w), self.P)
        idt = ("bad-fix solver", "id")
        subs = mine(net, idt[0])
        last = max((s.final_t for s in subs if s.reversed and s.final is False), default=None)
        self.assertIsNotNone(last)
        self.assertGreater(net.resets[idt], 0)
        after = sum(s.bounty for s in subs if s.final and s.final_t > last)
        self.assertAlmostEqual(net.rep[idt], after, places=6)
        self.assertLessEqual(max(net.open.values()), self.P.REP_BASE + self.P.REP_MULT * 10_000)

    def test_minus_takes_twice_the_bounty_off(self):
        w = short(weeks=20)
        p = replace(self.P, REP_ON_REVERSAL="minus")
        net = N.NDNet(3, p, w, [Z.OnMarket(w=w)])
        idt = ("x", "id")
        net.rep[idt] = 500.0
        s = net.submit(1.0, 40.0, False, "x", "x", ident="id")
        net.run()
        if s.reversed and s.final is False:
            self.assertAlmostEqual(net.rep[idt], 420.0)
        else:  # rejected or paid: nothing taken off
            self.assertGreaterEqual(net.rep[idt], 500.0)

    def test_the_newcomer_is_turned_away_at_first_and_its_twin_never(self):
        w = short(weeks=26)
        a, t = N.Newcomer(False, w), N.Newcomer(True, w)
        na, nt = run(a, self.P), run(t, self.P)
        self.assertGreater(a.count["turned"], 0)
        self.assertEqual(t.count["turned"], 0)
        self.assertLess(na.party_net(a.party), nt.party_net(t.party))
        self.assertIn(w.bounty_median, a.first)  # it may claim a median bounty within half a year

    def test_the_long_con_cashes_in_only_once_it_may_claim_the_largest_bounty(self):
        w = short(weeks=52)
        a = N.LongCon(False, w)
        net = run(a, self.P)
        bad = [s for s in mine(net, a.party) if not s.good]
        good = [s for s in mine(net, a.party) if s.good]
        self.assertTrue(good)
        if bad:
            first_bad = min(s.t for s in bad)
            paid_before = sum(s.bounty for s in good if s.final and s.final_t <= first_bad)
            self.assertGreaterEqual(self.P.REP_BASE + paid_before, N.TRIGGER - 1e-6)
        twin = N.LongCon(True, w)
        self.assertFalse([s for s in mine(run(twin, self.P), twin.party) if not s.good])

    def test_the_reputation_sale_starts_from_the_bought_reputation(self):
        w = short()
        a = N.RepSale(False, w)
        net = run(a, self.P)
        bought = [s for s in mine(net, a.party) if net.meta[s.sid]["ident"] == "bought"]
        self.assertTrue(bought and all(not s.good for s in bought))
        self.assertGreater(max(s.bounty for s in bought), self.P.REP_BASE)  # it claims above a newcomer's cap


class TestPot(unittest.TestCase):
    def test_the_pot_pays_out_exactly_the_funding_and_no_bounty(self):
        w = short(n=3, find=0.25, weeks=26)
        for pot in ("equal", "impact"):
            p = replace(P0, POT=pot, POT_WINDOW_WEEKS=13.0)
            a = N.BadFix(False, w)
            net = run(a, p)
            self.assertAlmostEqual(sum(net.pot_paid.values()) + net.carry, net.funding, places=4)
            self.assertAlmostEqual(net.parties[a.party].gains, net.pot_paid.get(a.party, 0.0), places=6)
            self.assertGreater(net.pot_paid.get("disputers", 0.0), 0.0)  # a reversed fix's weight goes to its disputer

    def test_equal_units_weigh_one_and_the_signal_tracks_impact_at_the_assumed_correlation(self):
        w = short()
        net = N.NDNet(3, replace(P0, POT="equal"), w, [Z.OnMarket(w=w)])
        s = net.submit(1.0, 80.0, True, "x", None)
        self.assertEqual(net.weight(s), 1.0)
        for rho in (0.3, 0.9):
            net = N.NDNet(3, replace(P0, POT="impact"), replace(w, impact_corr=rho), [Z.OnMarket(w=w)])
            xs, ys = [], []
            for i in range(3000):
                b = math.exp(math.log(86) + 0.59 * N._normal(99, i))
                s = net.submit(1.0, b, True, "x", None)
                xs.append(math.log(b))
                ys.append(math.log(net.weight(s)))
            mx, my = mean(xs), mean(ys)
            r = (sum((x - mx) * (y - my) for x, y in zip(xs, ys))
                 / math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)))
            self.assertAlmostEqual(r, rho, delta=0.05)

    def test_inflating_multiplies_the_weight_and_costs_its_price(self):
        w = short(inflate_cost=20.0)
        p = replace(P0, POT="impact")
        net = N.NDNet(3, p, w, [Z.OnMarket(w=w)])
        a = net.submit(1.0, 80.0, True, "x", "x", key=7)
        b = net.submit(1.0, 80.0, True, "y", "y", key=7, inflate=True)
        mu, sig = N._mu_sigma(w)
        self.assertAlmostEqual(net.weight(b) / net.weight(a), math.exp(sig * w.inflate_sd))
        net.run()
        self.assertAlmostEqual(net.parties["y"].costs - net.parties["x"].costs, 20.0, places=6)

    def test_honest_solvers_leave_issues_not_worth_their_effort_only_in_the_pot(self):
        w = short(weeks=26)
        eq = N.NDNet(3, replace(P0, POT="equal"), w, [Z.OnMarket(w=w)]).run()
        self.assertGreater(len(eq.neglected), 0)
        self.assertGreater(mean(s.bounty for s in eq.neglected), w.bounty_p90)  # the hard issues
        self.assertEqual(len(N.NDNet(3, P0, w, [Z.OnMarket(w=w)]).run().neglected), 0)

    def test_the_farmers_twin_spends_the_same_expected_effort(self):
        w = short()
        f, t = N.Farmer(False, w), N.Farmer(True, w)
        lim = N.cheap_limit(w)
        self.assertAlmostEqual(f.per_week * N.mean_bounty(w, lim), t.per_week * N.mean_bounty(w), places=6)
        self.assertLess(lim, w.bounty_median)


class TestJudgeFee(unittest.TestCase):
    def test_every_submission_pays_the_fee_and_no_check_charge(self):
        w = short()
        p = replace(P0, JUDGE_FEE=5.0)
        a = N.BadFix(False, w)
        net = run(a, p)
        pa = net.parties[a.party]
        self.assertAlmostEqual(pa.costs, pa.submitted * (5.0 + w.attempt_fee), places=6)
        base = run(N.BadFix(False, w), P0)
        self.assertGreater(base.parties[a.party].costs, base.parties[a.party].submitted * w.attempt_fee)

    def test_the_fee_is_the_measured_cost_of_the_panels(self):
        fee, rows = N.judge_cost(seeds=(1,))
        self.assertAlmostEqual(fee, N.JUDGE_FEE, delta=0.15 * N.JUDGE_FEE)
        for _, _, r in rows:
            self.assertGreater(r["break_even"], r["fee"])  # the market's fee sits at its floor, below cost
            self.assertGreater(r["cost"], r["charged"])


class TestRows(unittest.TestCase):
    def test_the_grid_covers_every_combination_seat_solver_count_and_kind(self):
        rows = N.grid_rows()
        keys = [N.key_of(r) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual({r[0] for r in rows}, {c for c, _ in N.COMBOS})
        self.assertEqual(len(N.COMBOS), 8)
        self.assertEqual({(r[1], r[2], r[3]) for r in rows},
                         {(s, p, n) for s, _ in N.SEATS for p, _ in N.POOLS for n in N.SOLVERS})
        for combo, _ in N.COMBOS:
            got = {r[4] for r in rows if r[0] == combo}
            self.assertTrue({"B", "S", "T"} <= got)
            self.assertEqual("L" in got, "R" in combo.split("+"))
            self.assertEqual("I" in got, "P" in combo.split("+"))
        for r in rows:
            p = r[7]
            self.assertEqual(p.SOLVER_DEPOSIT_BPS, 0)  # no deposit anywhere: the owner's base case
            self.assertEqual(p.REP_CAP, "R" in r[0].split("+"))
            self.assertEqual(p.POT, "impact" if "P" in r[0].split("+") else "off")
            self.assertEqual(p.JUDGE_FEE, N.JUDGE_FEE if "F" in r[0].split("+") else 0.0)

    def test_the_post_hoc_rows_are_the_recommended_rule(self):
        for r in N.minus_rows() + N.deposit_rows():
            p = r[7]
            self.assertEqual((p.REP_CAP, p.REP_ON_REVERSAL, p.POT, p.JUDGE_FEE), (True, "minus", "off", N.JUDGE_FEE))
        self.assertEqual({r[7].SOLVER_DEPOSIT_BPS for r in N.deposit_rows()}, set(N.HOLE_DEPOSITS))
        self.assertEqual({r[7].SOLVER_DEPOSIT_BPS for r in N.minus_rows()}, {0})

    def test_a_row_is_reproducible(self):
        w = short()
        a = N.against_twin(lambda h: N.Retrier(h, w), [2], replace(P0, REP_CAP=True))
        b = N.against_twin(lambda h: N.Retrier(h, w), [2], replace(P0, REP_CAP=True))
        self.assertEqual(a["diffs"], b["diffs"])


if __name__ == "__main__":
    unittest.main()
