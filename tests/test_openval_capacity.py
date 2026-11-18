"""#253: a validator's capacity a trailing hour, a repository's cap, the queue's order and the spammer
(pof/sim/openval/capacity.py; design D31, D32; reports/open-validators-measured-v6.md, simulation A)."""

import unittest
from collections import defaultdict
from dataclasses import replace

from pof.sim.openval import capacity as K
from pof.sim.openval import nodeposit as N
from pof.sim.openval import sizing as Z
from pof.sim.openval.evidence import P0
from pof.sim.openval.net import ISSUE, Net
from pof.sim.openval.params import D236, HOUR, PARAMS


def short(n=7, weeks=3, seat="anthropic"):
    return K.world(seat, n, weeks=weeks)


def run(p, w, rate=0.0, seed=2, **kw):
    a = K.Spammer(False, w, per_hour=rate, **kw)
    return K.CapNet(seed, p, w, [a]).run(), a


def issues(net):
    return [s for s in net.subs.values() if s.tier == ISSUE]


class TestDefaults(unittest.TestCase):
    def test_every_switch_is_off_by_default(self):
        for p in (PARAMS, D236, P0):
            self.assertEqual((p.MAX_CHECKS_PER_HOUR, p.REPO_CHECKS_PER_HOUR, p.QUEUE_ORDER), (None, None, "fifo"))

    def test_a_plain_net_refuses_the_switches(self):
        w = short()
        for kw in (dict(MAX_CHECKS_PER_HOUR=5), dict(REPO_CHECKS_PER_HOUR=7), dict(QUEUE_ORDER="reputation")):
            with self.assertRaises(ValueError):
                Net(1, replace(P0, **kw), w, [Z.OnMarket(w=w)])

    def test_with_every_switch_off_capnet_is_ndnet(self):
        w = replace(N.world("hidden", "anthropic", 3), weeks=8)
        p = replace(P0, REP_CAP=True)
        a, b = N.BadFix(False, w), N.BadFix(False, w)
        old = N.NDNet(4, p, w, [a]).run()
        new = K.CapNet(4, p, w, [b]).run()
        self.assertAlmostEqual(old.party_net(a.party), new.party_net(b.party), places=6)
        for k in ("paid", "bad_merged", "submitted", "waited", "audits", "rival_tests"):
            self.assertEqual(old.stats[k], new.stats[k], k)


class TestCapacity(unittest.TestCase):
    def test_no_validator_is_drawn_for_more_counted_checks_an_hour_than_its_capacity(self):
        for cap in (1, 3):
            net, _ = run(K._p(cap, "fifo"), short(), rate=10.0)
            times = defaultdict(list)
            for s in issues(net):
                if s.drawn_t is not None:
                    for vid, _, _ in s.judges:
                        times[vid].append(s.drawn_t)
            self.assertTrue(times)
            for ts in times.values():
                ts.sort()
                for i, t in enumerate(ts):
                    inside = sum(1 for x in ts[i:] if x < t + HOUR - 1e-9)
                    self.assertLessEqual(inside, cap)

    def test_capacity_never_lowers_k_and_nothing_fails(self):
        net, _ = run(K._p(1, "fifo"), short(), rate=1.0)
        drawn = [s for s in issues(net) if s.drawn_t is not None]
        self.assertTrue(drawn)
        self.assertTrue(all(s.k == 7 for s in drawn))  # 7 validators: k is always 7, as without capacity
        self.assertGreater(net.stats["drawn_after_wait"], 50)  # waits end in draws
        self.assertFalse(any(s.state in ("refused", "expired") for s in issues(net) if s.party is None))

    def test_without_capacity_the_spam_is_drawn_at_once(self):
        net, _ = run(K._p(None, "fifo"), short(), rate=1.0)
        self.assertEqual(net.stats["waited"], 0)
        self.assertEqual(len(net.inq), 0)

    def test_junk_is_rejected_and_the_spammer_pays_only_charges_in_test_eth(self):
        net, a = run(K._p(5, "fifo"), short(), rate=1.0)
        junk = [s for s in issues(net) if s.sid in net.junk]
        self.assertGreater(len(junk), 300)
        self.assertFalse(any(s.final for s in junk))
        # all of it test ETH on a testnet: the attempt fee (`World.attempt_fee`) and its panels' per-check charges
        self.assertAlmostEqual(net.parties[a.party].costs, sum(0.5 + s.billed for s in junk), places=4)

    def test_with_the_judges_fee_the_spammer_pays_it_on_every_junk_fix(self):
        net, a = run(K._p(5, "fifo", JUDGE_FEE=K.FEE), short(), rate=1.0)
        junk = [s for s in issues(net) if s.sid in net.junk]
        self.assertAlmostEqual(net.parties[a.party].costs, (K.FEE + 0.5) * len(junk), places=4)


class TestQueue(unittest.TestCase):
    def test_fifo_draws_in_arrival_order(self):
        net, _ = run(K._p(1, "fifo"), short(), rate=1.0)
        waited = sorted((net.seq[s.sid], s.drawn_t) for s in issues(net) if s.waited and s.drawn_t is not None)
        self.assertGreater(len(waited), 50)
        self.assertTrue(all(b[1] >= a[1] - 1e-9 for a, b in zip(waited, waited[1:])))

    def test_reputation_order_serves_established_solvers_first(self):
        w = short()
        waits = {}
        for o in ("fifo", "reputation"):
            net = run(K._p(1, o), w, rate=1.0)[0]
            xs = [s.drawn_t - s.t for s in issues(net) if s.party is None and s.drawn_t is not None
                  and s.solver not in {f"solver-{i}" for i in range(10)}]
            waits[o] = sum(xs) / len(xs)
        self.assertLess(waits["reputation"], waits["fifo"] / 10)
        net, _ = run(K._p(1, "reputation"), w, rate=1.0)
        first = sorted((net.seq[s.sid], s.drawn_t) for s in issues(net)
                       if s.waited and s.drawn_t is not None and net.cls[s.sid] == 0)
        self.assertTrue(all(b[1] >= a[1] - 1e-9 for a, b in zip(first, first[1:])))  # FIFO within a class

    def test_junk_and_newcomers_are_in_the_second_class(self):
        net, _ = run(K._p(5, "reputation"), short(), rate=1.0)
        for s in issues(net):
            if s.sid in net.junk:
                self.assertEqual(net.cls[s.sid], 1)
            elif s.solver in {f"solver-{i}" for i in range(10, 50)}:
                self.assertEqual(net.cls[s.sid], 0)

    def test_a_reputable_spammer_is_bounded_by_the_cap(self):
        net, a = run(K._p(5, "reputation"), short(), rate=10.0, reputable=True)
        self.assertGreater(a.count["skipped"], 0)  # no listed issue fits its room: the cap binds
        self.assertLessEqual(net.open[(a.party, "rep")], net.p.REP_BASE + K.REP0 + 1e-6)


class TestRepositoryCap(unittest.TestCase):
    def test_no_repository_draws_more_counted_checks_an_hour_than_its_cap(self):
        net, _ = run(K._p(None, "fifo", 7), short(), rate=10.0)
        by = defaultdict(list)
        for s in issues(net):
            if s.drawn_t is not None:
                by[net.repo_of(s)].append((s.drawn_t, s.k))
        self.assertTrue(any(len(v) > 100 for v in by.values()))
        for xs in by.values():
            xs.sort()
            for i, (t, _) in enumerate(xs):
                self.assertLessEqual(sum(k for x, k in xs[i:] if x < t + HOUR - 1e-9), 7)

    def test_spam_on_one_repository_leaves_the_others_alone(self):
        net, _ = run(K._p(None, "fifo", 7), short(), rate=10.0)
        others = [s for s in issues(net) if s.party is None and net.repo_of(s) != 0 and s.t > 1.0]
        self.assertTrue(others)
        self.assertLess(max(s.drawn_t - s.t for s in others if s.drawn_t is not None), 1.0 + 1e-6)


# ---------- post hoc (after report v6): the newcomer lane and its per-identity rate ----------

def lane_p(cap=5, share=0.25, rcap=None, **kw):
    return K._p(cap, "reputation", rcap, NEWCOMER_LANE=share, **kw)


NEW = {f"solver-{i}" for i in range(10)}


class TestLaneDefaults(unittest.TestCase):
    def test_the_lane_and_the_rate_are_off_by_default(self):
        for p in (PARAMS, D236, P0, K.BASE):
            self.assertEqual((p.NEWCOMER_LANE, p.LANE_PER_ID_DAY), (0.0, None))

    def test_a_plain_net_refuses_them_and_capnet_needs_a_capacity_and_reputation_first(self):
        w = short()
        for kw in (dict(NEWCOMER_LANE=0.25), dict(LANE_PER_ID_DAY=2)):
            with self.assertRaises(ValueError):
                Net(1, replace(P0, **kw), w, [Z.OnMarket(w=w)])
        for p in (K._p(None, "reputation", NEWCOMER_LANE=0.25), K._p(5, "fifo", NEWCOMER_LANE=0.25),
                  K._p(5, "reputation", NEWCOMER_LANE=1.0), K._p(5, "fifo", LANE_PER_ID_DAY=2)):
            with self.assertRaises(ValueError):
                K.CapNet(1, p, w, [])

    def test_the_v6_rows_are_unchanged(self):
        self.assertEqual(len(K.grid_rows()), 150)
        self.assertEqual(len(K.repo_rows()), 40)
        self.assertEqual(len(K.fee_rows()), 22)
        for row in K.grid_rows() + K.repo_rows() + K.fee_rows():
            self.assertEqual(len(K.key_of(row).split("|")), 8)
            self.assertEqual((row[9].NEWCOMER_LANE, row[9].LANE_PER_ID_DAY), (0.0, None))


class TestNewcomerLane(unittest.TestCase):
    def test_no_validator_takes_more_lane_checks_than_its_credit(self):
        w = short()
        for cap, share in ((5, 0.10), (5, 0.50), (10, 0.25)):
            net, _ = run(lane_p(cap, share), w, rate=10.0)
            r = share * cap
            times = defaultdict(list)
            for s in issues(net):
                if s.drawn_t is not None and net.cls[s.sid] == 1:
                    for vid in s.draw.panel:
                        times[vid].append(s.drawn_t)
            self.assertTrue(times)
            for ts in times.values():
                ts.sort()
                for span in (HOUR, 24 * HOUR):
                    for i, t in enumerate(ts):
                        inside = sum(1 for x in ts[i:] if x < t + span - 1e-9)
                        self.assertLessEqual(inside, max(1.0, r) + r * span / HOUR + 1e-6)
            self.assertEqual(net.lane_checks, sum(len(v) for v in times.values()))

    def test_the_lane_never_takes_the_established_solvers_capacity(self):
        net, _ = run(lane_p(5, 0.50), short(), rate=10.0)
        est = [s for s in issues(net) if s.party is None and net.cls[s.sid] == 0 and s.t > HOUR]
        self.assertGreater(len(est), 30)
        self.assertTrue(all(s.drawn_t is not None for s in est))
        self.assertLess(max(s.drawn_t - s.t for s in est), HOUR + 1e-6)

    def test_the_lane_is_first_come_first_served_and_newcomers_share_it_with_the_junk(self):
        net, _ = run(lane_p(5, 0.25), short(), rate=10.0)
        lane = sorted((net.seq[s.sid], s.drawn_t) for s in issues(net)
                      if net.cls[s.sid] == 1 and s.drawn_t is not None and s.waited)
        self.assertGreater(len(lane), 50)
        self.assertTrue(all(b[1] >= a[1] - 1e-9 for a, b in zip(lane, lane[1:])))
        self.assertTrue(all(net.cls[s.sid] == 1 for s in issues(net) if s.sid in net.junk))
        self.assertTrue(any(net.cls[s.sid] == 1 for s in issues(net) if s.party is None and s.solver in NEW))

    def test_the_lane_draws_as_soon_as_its_credit_allows(self):
        w = short(weeks=4)
        net, _ = run(lane_p(5, 0.25), w, rate=10.0)  # always backlogged: the lane runs at its full rate
        days = w.horizon_h / 24
        self.assertAlmostEqual(net.lane_checks / 7 / days, 24 * 0.25 * 5, delta=0.6)

    def test_spend_falls_to_the_lane_under_spam(self):
        w = short()
        none, _ = run(K._p(5, "reputation"), w, rate=10.0)
        lane, _ = run(lane_p(5, 0.10), w, rate=10.0)
        self.assertLess(K.metrics(lane)["checks_day"], K.metrics(none)["checks_day"] / 4)


class TestPerIdentityRate(unittest.TestCase):
    def test_fresh_identities_defeat_it(self):
        w = short(weeks=5)
        a = K.metrics(run(lane_p(5, 0.25), w, rate=10.0)[0])
        b = K.metrics(run(lane_p(5, 0.25, LANE_PER_ID_DAY=K.ID_RATE), w, rate=10.0)[0])
        self.assertEqual(b["refused_junk_day"], 0.0)
        for k in ("over24", "withdrawn", "new_withdrawn", "checks_day", "junk_n", "queue_max"):
            self.assertEqual(a[k], b[k], k)
        self.assertGreater(a["new_withdrawn"], 50)  # and the lane, swamped, loses the newcomers' fixes

    def test_no_identity_in_the_lane_submits_more_than_its_rate_a_day(self):
        net, a = run(lane_p(5, 0.25, LANE_PER_ID_DAY=2), short(), rate=10.0, idents=10)
        self.assertGreater(net.rate_refused["actor"], 0)
        self.assertEqual(net.rate_refused["honest"], 0)  # an honest solver submits far below 2 a day here
        by = defaultdict(list)
        for s in issues(net):
            if s.sid in net.junk:
                by[net.ident(s)].append(s.t)
        self.assertLessEqual(len(by), 10)
        for ts in by.values():
            ts.sort()
            for i, t in enumerate(ts):
                self.assertLessEqual(sum(1 for x in ts[i:] if x < t + 24 * HOUR - 1e-9), 2)

    def test_a_refused_honest_fix_counts_as_never_drawn(self):
        w = short(weeks=4)
        net, _ = run(lane_p(5, 0.25, LANE_PER_ID_DAY=0), w, rate=0.0)
        refused = [s for s in issues(net) if s.party is None and s.state == "refused"]
        self.assertTrue(refused)
        self.assertEqual(len(refused), net.rate_refused["honest"])
        self.assertTrue(all(net.cls[s.sid] == 1 and s.drawn_t is None for s in refused))


# ---------- post hoc (#251 task 3.15): junk pays the judges' fee from faucet USDC ----------

def fee_p(cap=5, order="reputation", **kw):
    return K._p(cap, order, JUDGE_FEE=K.FEE, **kw)


class TestFaucet(unittest.TestCase):
    def test_off_by_default_and_the_earlier_rows_are_unchanged(self):
        self.assertIsNone(K.Spammer(False, short(), per_hour=1.0).usdc_day)
        for row in K.grid_rows() + K.repo_rows() + K.fee_rows() + K.lane_rows() + K.rate_rows():
            self.assertFalse(row[7].startswith("usdc:"))
        self.assertEqual(K.FAUCET_ADDRESS_DAY, 240.0)

    def test_it_needs_the_judges_fee(self):
        with self.assertRaises(ValueError):
            run(K._p(5, "reputation"), short(), rate=1.0, usdc_day=240.0)

    def test_an_income_that_never_binds_changes_nothing(self):
        w = short(weeks=5)
        a = K.metrics(run(fee_p(), w, rate=10.0)[0])
        b = K.metrics(run(fee_p(), w, rate=10.0, usdc_day=1e9)[0])
        for k in ("over24", "withdrawn", "new_withdrawn", "checks_day", "junk_n", "queue_max"):
            self.assertEqual(a[k], b[k], k)

    def test_the_junk_rate_is_the_income_over_the_fee(self):
        w = short(weeks=4)
        days = w.horizon_h / 24
        for usdc in (20.0, 240.0, 480.0):
            net, a = run(fee_p(), w, rate=10.0, usdc_day=usdc)
            junk = [s for s in issues(net) if s.sid in net.junk]
            self.assertAlmostEqual(len(junk) / days, usdc / K.FEE, delta=0.06 * usdc / K.FEE + 0.5)
            self.assertGreater(a.count["unfunded"], 0)
            self.assertLessEqual(a.usdc_paid, a.usdc_in + 1e-6)  # never spends more than the faucet paid in
            self.assertGreaterEqual(a.wallet, -1e-9)
            self.assertAlmostEqual(a.usdc_paid, K.FEE * len(junk), places=4)

    def test_below_the_income_the_intended_rate_is_kept(self):
        w = short(weeks=3)
        a = run(fee_p(), w, rate=1.0)[1]
        b = run(fee_p(), w, rate=1.0, usdc_day=K.FAUCET_ADDRESS_DAY)[1]  # 1 an hour needs 121 USDC a day
        self.assertLessEqual(a.count["submitted"] - b.count["submitted"], 2)  # only the first hours' slots wait

    def test_the_faucet_rows(self):
        rows = K.faucet_rows()
        self.assertEqual(len(rows), 96)
        self.assertEqual(len({K.key_of(r) for r in rows}), 96)
        for r in rows:
            _, seat, n, cap, rate, order, rcap, form, w, p = r
            self.assertEqual((cap, rcap, w.repos, p.JUDGE_FEE, p.REPO_CHECKS_PER_HOUR), (5, None, 1, K.FEE, None))
            self.assertIn(n, (7, 15))
            self.assertTrue(form.startswith("usdc:"))
        self.assertEqual(K.FAUCET_SEEDS, tuple(range(41, 81)))


if __name__ == "__main__":
    unittest.main()
