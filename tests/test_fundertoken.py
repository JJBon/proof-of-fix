"""One general token earned by funders, investor pools and an adapting emission (proof-of-fix#193,
pof.sim.fundertoken)."""

import json
import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from statistics import mean

from pof.sim import fundertoken as FT

P = FT.Params()


def cycle(p=P, seed=1, cycles=3):
    """A few cycles run by hand, returning the simulation and the last cycle's fixes."""
    sim = FT.Sim(seed, replace(p, cycles=cycles))
    fixes = []
    for t in range(cycles):
        sim.inflows(t)
        fixes = sim.make_fixes(t)
        sim.judge(fixes)
        claims = sim.split(t, fixes)
        sim.emit(t, fixes, claims)
        sim.burn(t, fixes, claims)
        sim.account(t, fixes, claims)
        sim.review(t)
        sim.record(t)
    return sim, fixes


class FunderTokenTest(unittest.TestCase):
    def test_deterministic(self):
        a, b = FT.run(3, P), FT.run(3, P)
        self.assertEqual(a.mint, b.mint)
        self.assertEqual(a.stall_investor_share, b.stall_investor_share)

    def test_the_thin_cycle_fix_pays_at_most_the_merit(self):
        _, fixes = cycle()
        self.assertTrue(fixes)
        for f in fixes:
            self.assertLessEqual(f.pool, max(0.0, f.merit - f.bounty) + 1e-9)

    def test_pay_per_merit_dollar_never_exceeds_the_ceiling(self):
        _, fixes = cycle(replace(P, adapt_pay=True))
        for f in fixes:
            self.assertLessEqual(f.pool, max(0.0, P.pay_max * f.merit - f.bounty) + 1e-9)

    def test_tokens_are_capped_by_the_coin_that_paid(self):
        r = FT.run(1, P)
        for cyc in r.items:
            for tokens, coin in cyc:
                self.assertLessEqual(tokens, P.tpc * coin + 1e-9)

    def test_emission_stays_under_the_cap(self):
        r = FT.run(1, P)
        self.assertLessEqual(max(r.mint), P.cap + 1e-6)

    def test_every_minted_token_goes_to_a_funder(self):
        sim = FT.Sim(2, P)
        r = sim.run()
        held = sum(f.tokens for f in r.funders) + sim.forfeit.tokens
        self.assertAlmostEqual(held, sum(r.mint), delta=1e-6 * sum(r.mint))

    def test_short_pools_give_funders_more_tokens_per_coin(self):
        """A pool paying 1x has funders' tokens per coin near E/M; paying up to 1.5x (b) lowers it."""
        a, b = FT.run(1, P), FT.run(1, replace(P, adapt_pay=True))
        pool = lambda r: FT.tpc_spent([f for f in r.funders if f.kind in ("repo", "index")])  # noqa: E731
        self.assertGreater(pool(a), pool(b))
        self.assertGreater(b.paid["healthy"] / b.merit["healthy"], a.paid["healthy"] / a.merit["healthy"])

    def test_carrying_the_shortfall_leaves_less_merit_unpaid(self):
        a, c = FT.run(1, P), FT.run(1, replace(P, carry=True))
        self.assertLess(c.underpaid, a.underpaid)

    def test_investors_leave_stalling_repositories(self):
        rs = [FT.run(s, P) for s in range(1, 4)]
        at_stall = mean(r.stall_investor_share[P.stall_at - 1] for r in rs)
        end = mean(r.stall_investor_share[-1] for r in rs)
        self.assertLess(end, at_stall / 2)

    def test_at_the_flow_price_burns_absorb_the_mint(self):
        r = FT.run(1, P)
        ps = FT.flow_price(r, P)
        self.assertAlmostEqual(FT.burned_at(r, P, ps) / sum(r.mint), 1.0, places=3)
        self.assertLess(FT.burned_at(r, P, ps * 1.1), sum(r.mint))

    def test_funders_get_back_the_fee_cap_plus_other_burns_at_the_flow_price(self):
        """At p*, funders' tokens are worth about the payout fee's cap plus the other burns over the coin funded,
        whatever the emission's settings."""
        for kw in ({}, {"cap": 4_000.0}, {"rate": 0.5}):
            p = replace(P, **kw)
            r = FT.run(1, p)
            ps = FT.flow_price(r, p)
            coin = sum(c for cyc in r.items for _, c in cyc)
            other = P.margin * sum(r.checks) + sum(r.stakes)
            value = ps * sum(r.mint) / coin
            self.assertAlmostEqual(value, P.fee_cap + other / coin, delta=0.02)

    def test_outside_checks_needed_match_the_flow_price(self):
        r = FT.run(1, P)
        need = FT.outside_needed(r, P, 0.05, 0.5)
        self.assertAlmostEqual(FT.flow_price(r, P, 0.05, need), 0.5, delta=0.005)
        self.assertEqual(FT.outside_needed(r, P, 0.05, 0.01), 0.0)

    def test_the_cap_following_burns_adds_its_base_once_it_binds(self):
        p = replace(P, adapt_cap=True, base=2_000.0, price=1.0)
        r = FT.run(1, p)
        added = mean(r.mint[-13:]) - mean(r.burned[-13:])
        self.assertAlmostEqual(added, 2_000.0, delta=150.0)

    def test_self_dealing_pays_only_when_funding_pays(self):
        twin = replace(P, attack="overclaim")
        play = replace(twin, own_coin=5.0)
        base, att = FT.run(1, twin), FT.run(1, play)
        honest = FT.tpc_spent([f for f in att.funders if f.kind in ("repo", "index")])
        self.assertLess(FT.attack_profit(att, play, 0.5 / honest), FT.attack_profit(base, twin, 0.5 / honest))
        self.assertGreater(FT.pays_from(base, att, play, twin) * honest, 0.9)

    def test_the_stake_makes_overclaiming_lose(self):
        twin = replace(P, attack="overclaim", colluders=5)
        play = replace(twin, claim=200.0, own_coin=200.0)
        base, att = FT.run(1, twin), FT.run(1, play)
        self.assertLess(FT.attack_profit(att, play, 0.2), FT.attack_profit(base, twin, 0.2))

    def test_one_cent_pledges_need_the_per_fix_cap(self):
        cent = replace(P, unfunded=2, attack="cent")
        for tpc, gains in ((P.tpc, False), (1e12, True)):
            q = replace(cent, tpc=tpc)
            att, twin = FT.run(1, q), FT.run(1, replace(q, attack=""))
            gain = FT.attack_profit(att, q, 0.2) - FT.attack_profit(twin, replace(q, attack=""), 0.2)
            self.assertEqual(gain > 0, gains, tpc)

    def test_redistributing_the_cut_stops_one_cent_dilution(self):
        """The cut not minted lets 1-cent pledges dilute everyone while the cap binds; giving it to uncapped fixes
        (#186 D3) doesn't."""
        cent = replace(P, unfunded=2, attack="cent")
        pool = lambda r: FT.tpc_spent([f for f in r.funders if f.kind in ("repo", "index")])  # noqa: E731
        for redistribute, hurt in ((False, True), (True, False)):
            q = replace(cent, redistribute=redistribute)
            ratio = pool(FT.run(1, q)) / pool(FT.run(1, replace(q, attack="")))
            self.assertEqual(ratio < 0.95, hurt, redistribute)

    # ----- v2: outside use in check domains (#195) -----

    def test_no_outside_use_reproduces_v1_exactly(self):
        """v1's report (reports/fundertoken-v1.json) is reproduced with no domains: bit for bit on the Python that wrote
        it (3.12 and later sum floats with compensation), to the last digits on earlier ones."""
        path = Path(__file__).resolve().parent.parent / "reports" / "fundertoken-v1.json"
        v1 = json.loads(path.read_text(encoding="utf-8"))
        same = self.assertEqual if sys.version_info >= (3, 12) else \
            (lambda a, b: self.assertAlmostEqual(a, b, delta=1e-12 * abs(b)))
        for s in (1, 2, 3):
            r = FT.run(s, P)
            same(FT.flow_price(r, P), v1["investors_none"]["p_star"][s - 1])
        cell = next(c for c in v1["sustainability"]["cells"]
                    if c.get("margin") == 0.1 and c.get("external") == 100_000.0 and c["fee"].startswith("burned"))
        same(FT.flow_price(FT.run(1, P), P, 0.1, 100_000.0), cell["p_star"][0])
        self.assertNotIn("domains", FT._params_v1(P))

    def test_a_domain_with_no_requests_changes_nothing(self):
        a = FT.run(2, P)
        b = FT.run(2, replace(P, domains=(FT.generic(0.0, 0.25),)))
        self.assertEqual(a.mint, b.mint)
        self.assertEqual(a.burned, b.burned)

    def test_a_flat_domain_burns_like_outside_checks(self):
        a = FT.run(1, replace(P, external_checks=20_000.0))
        b = FT.run(1, replace(P, domains=(FT.generic(20_000.0, P.margin),)))
        self.assertEqual(a.mint, b.mint)
        for x, y in zip(a.burned, b.burned):
            self.assertAlmostEqual(x, y, delta=1e-9 * x)

    def test_judges_cost_is_passed_through_not_burned(self):
        cheap = FT.priced("t", "checkable", 9.0, 1.0, requests=900.0)
        dear = replace(cheap, judge_cost=3.0)
        self.assertAlmostEqual(cheap.margin, 8.0)
        a, b = FT.run(1, replace(P, domains=(cheap,))), FT.run(1, replace(P, domains=(dear,)))
        self.assertEqual(a.burned, b.burned)
        self.assertAlmostEqual(sum(a.judges_paid), 52 * 900 * 3 * cheap.judge_cost)
        self.assertGreater(sum(b.judges_paid), sum(a.judges_paid))

    def test_a_growing_domain_grows_to_its_ceiling(self):
        d = FT.generic(100.0, 1.0, growth=0.1, ceiling=200.0)
        self.assertEqual(d.at(0), 100.0)
        self.assertAlmostEqual(d.at(1), 110.0)
        self.assertEqual(d.at(51), 200.0)

    def test_outside_dollars_needed_meet_the_target(self):
        r = FT.run(1, P)
        g = FT.pool_tpc(r)
        d = FT.outside_dollars_needed(r, P, 1.2 / g)
        self.assertAlmostEqual(g * FT.flow_price(r, P, outside=FT.flat(d, P)), 1.2, delta=0.005)
        p = replace(P, domains=(FT.generic(d, 1.0),))
        self.assertAlmostEqual(g * FT.flow_price(FT.run(1, p), p), 1.2, delta=0.005)

    def test_outside_use_moves_only_the_price_without_a(self):
        """Without (a), outside burns don't touch pools or tokens, so an attack's gain at a given price is v1's."""
        twin = replace(P, attack="overclaim", colluders=5)
        play = replace(twin, claim=15.0, own_coin=5.0)
        dom = (FT.generic(50_000.0, 1.0),)
        for q in (twin, play):
            a, b = FT.run(1, q), FT.run(1, replace(q, domains=dom))
            self.assertEqual(FT.attack_profit(a, q, 3.0), FT.attack_profit(b, replace(q, domains=dom), 3.0))
        self.assertGreater(FT.flow_price(FT.run(1, replace(P, domains=dom)), replace(P, domains=dom)), 2.84)

    def test_overclaiming_never_beats_the_honest_use_of_its_coin(self):
        twin = replace(P, attack="overclaim", colluders=5)
        play = replace(twin, claim=15.0, own_coin=5.0)
        b, a = FT.run(1, twin), FT.run(1, play)
        self.assertGreater(FT.attack_profit(a, play, 5.0), FT.attack_profit(b, twin, 5.0))  # v1's measure: it pays
        for x in (1.0, 3.0, 10.0, 50.0):
            self.assertLess(FT.invested_gain(b, a, play, twin, x), 0.0)

    def test_the_rebate_ceiling_bounds_what_funders_get_back(self):
        dom = (FT.generic(200_000.0, 1.0),)
        free = replace(P, domains=dom)
        capped = replace(free, rebate_max=1.2)
        rf, rc = FT.run(1, free), FT.run(1, capped)
        self.assertGreater(FT.pool_tpc(rf) * FT.flow_price(rf, free), 5.0)
        value = FT.pool_tpc(rc) * FT.flow_price(rc, capped)
        self.assertLess(value, 1.4)
        self.assertGreater(value, 1.1)
        self.assertGreater(sum(rc.outside_waived), sum(rc.outside))
        self.assertLess(FT.flow_price(rc, capped), 2.84)

    def test_validators_count_answers_and_bonds(self):
        d = replace(FT.DOMAINS["disputes"], requests=70.0)
        v = FT.validators((d,))
        self.assertEqual(v["answers"], 490.0)
        self.assertEqual(v["seat_answers"], 70.0)
        self.assertEqual(v["bond"], 2 * d.at_stake)
        self.assertEqual(v["nodes_per_seat"], 1)
        self.assertEqual(v["v3_validators"], FT.SEATS)

    def test_report_v2_runs(self):
        md, data = FT.report_v2(range(1, 2), replace(P, cycles=26))
        self.assertIn("### 8. The rebate ceiling", md)
        self.assertEqual(data["v1_p_star"][0], FT.flow_price(FT.run(1, replace(P, cycles=26)), replace(P, cycles=26)))

    def test_report_runs(self):
        md, data = FT.report(range(1, 2), replace(P, cycles=20), colluders=(0,))
        self.assertIn("### 4. Sustainability", md)
        self.assertIn("farming", data)
        self.assertTrue(all(math.isfinite(x) for x in data["investors_none"]["p_star"]))


if __name__ == "__main__":
    unittest.main()
