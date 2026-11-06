"""#85 task 4.5: check fees (pof/checkgas.py, design S15): usage at unit prices plus one agreed service fee, the
median rule, caps and CI profiles, the deposit's ceiling, refunds, bounded and delayed updates, and the market
simulation with check gas against flat fees."""

import unittest
from dataclasses import replace

from pof import MICRO
from pof import checkgas as G
from pof.sim import market_sim as MS


def _judges(tokens):
    return [(f"j{i}", fam, G.Usage(t, 0, 1_000, 240, 480)) for i, (fam, t) in
            enumerate(zip(("anthropic", "openai", "google"), tokens))]


class TestCharge(unittest.TestCase):
    def test_one_judge_pads_its_usage(self):
        """oracle-network: two judges report 4,000 tokens and the third 40,000: each is paid for 4,000 tokens at its
        own family's prices, plus the service fee."""
        t = G.judge_table(service_fee=0.05)
        c = G.charge(t, _judges((4_000, 4_000, 40_000)))
        honest = G.Usage(4_000, 0, 1_000)
        for (who, fam, _), (paid_who, paid) in zip(_judges((0, 0, 0)), c.judges):
            self.assertEqual(who, paid_who)
            self.assertAlmostEqual(paid, G.tokens_cost(t.family(fam), honest) + 0.05)
        self.assertAlmostEqual(c.total, G.charge(t, _judges((4_000, 4_000, 4_000))).total)

    def test_a_heavier_check_costs_more_at_the_same_prices(self):
        t = G.judge_table()
        light, heavy = G.charge(t, _judges((3_000,) * 3)), G.charge(t, _judges((40_000,) * 3))
        self.assertGreater(heavy.total, light.total)
        self.assertEqual(light.service_fees, heavy.service_fees)  # the fee is per check, not per token

    def test_the_service_fee_is_the_same_for_every_seat(self):
        t = G.judge_table(service_fee=0.07)
        c = G.charge(t, _judges((5_000,) * 3))
        self.assertAlmostEqual(c.service_fees, 0.21)
        ai = [p - 0.07 for _, p in c.judges]
        self.assertEqual(len(set(round(a, 9) for a in ai)), 3)  # each family's own token prices differ

    def test_the_caps_and_the_ci_profile(self):
        """A run that reaches the timeout stops there, and a heavier profile shows a higher maximum check cost."""
        small, heavy = G.CIProfile(vcpu=1, gb=2, timeout_s=60), G.CIProfile(vcpu=2, gb=4, timeout_s=8 * 60)
        self.assertEqual(small.run(10_000).vcpu_seconds, 60)
        t, fams = G.judge_table(), ["anthropic", "openai", "google"]
        self.assertGreater(G.deposit_max(t, 3, fams, heavy), G.deposit_max(t, 3, fams, small))
        over = G.Usage(10_000_000, 0, 10_000_000, 1e9, 1e9, 1e9).capped(G.Caps(), small)
        self.assertEqual((over.input, over.output, over.vcpu_seconds), (140_000, 16_000, 60))

    def test_the_deposit_is_the_ceiling_and_the_rest_is_refunded(self):
        """oracle-network: the deposit is the worst case under the caps plus the fees and a gas allowance; no charge
        exceeds it; what the checks don't use is refunded."""
        t, p = G.judge_table(), G.CIProfile()
        fams = ["anthropic", "openai", "google"]
        deposit = G.deposit_max(t, 3, fams, p, gas_allowance=0.10)
        worst = [(f"j{i}", f, G.Usage(10**9, 0, 10**9, 10**9, 10**9, 10**9)) for i, f in enumerate(fams)]
        top = G.charge(t, worst, p, gas=0.10)
        self.assertLessEqual(top.total, deposit + 1e-9)
        c = G.charge(t, _judges((28_500,) * 3), p, gas=0.03)
        self.assertAlmostEqual(G.refund(deposit, c), deposit - c.total)
        with self.assertRaises(ValueError):
            G.refund(0.01, c)

    def test_a_single_attested_ci_run_is_charged_once(self):
        t = G.judge_table()
        judges = [("j0", "anthropic", G.Usage(4_000, 0, 1_000, 240, 480)),
                  ("j1", "openai", G.Usage(4_000, 0, 1_000)), ("j2", "google", G.Usage(4_000, 0, 1_000))]
        once = G.charge(t, judges, ci_single_run=True)
        self.assertAlmostEqual(once.ci, G.sandbox_cost(t, G.Usage(0, 0, 0, 240, 480)))
        each = G.charge(t, _judges((4_000,) * 3))
        self.assertAlmostEqual(each.ci, 3 * once.ci)


class TestUpdates(unittest.TestCase):
    def setUp(self):
        self.s = G.Schedule(G.judge_table(service_fee=0.05), service_fee_cap=0.25)

    def test_a_price_jump_is_refused(self):
        """oracle-network: 5 seats sign a table raising one entry by 40 %: refused."""
        t = self.s.table
        jumped = replace(t, tokens=((t.tokens[0][0], t.tokens[0][1].scaled(14_000)),) + t.tokens[1:])
        with self.assertRaises(G.UpdateRefused):
            self.s.propose(jumped, 5, day=0)

    def test_a_service_fee_above_the_cap_is_refused(self):
        s = G.Schedule(G.judge_table(service_fee=0.22), service_fee_cap=0.25)
        with self.assertRaises(G.UpdateRefused):
            s.propose(replace(s.table, service_fee=0.27), 5, day=0)  # within 25 %, above the cap

    def test_an_update_needs_five_seats_and_one_at_a_time(self):
        up = self.s.table.scaled(11_000)
        with self.assertRaises(G.UpdateRefused):
            self.s.propose(up, 4, day=0)
        self.s.propose(up, 5, day=0)
        with self.assertRaises(G.UpdateRefused):
            self.s.propose(up.scaled(11_000), 5, day=1)

    def test_an_updates_notice(self):
        """oracle-network: attempts in the next 7 days are still charged at the old prices."""
        old = self.s.table
        self.s.propose(old.scaled(12_000), 5, day=10)
        for day in range(10, 17):
            self.assertIs(self.s.apply(day), old)
        self.assertIsNot(self.s.apply(17), old)

    def test_the_cartels_year(self):
        """incentive-simulation: 5 colluders raise everything by the maximum at every chance for a year. The fee
        stops at its cap; the unit prices have no cap of their own (a finding for #100)."""
        t, n = G.cartel_year(G.judge_table(service_fee=0.05), cap=0.25)
        self.assertEqual(n, 52)
        self.assertAlmostEqual(t.service_fee, 0.25)
        self.assertGreater(t.vcpu_second / G.VCPU_SECOND, 10_000)


class TestEnclave(unittest.TestCase):
    def test_break_even(self):
        e = G.Enclave()
        n = e.break_even_checks(0.05)
        self.assertAlmostEqual(e.net_month(0.05, n), 0.0, places=6)
        self.assertGreater(e.net_month(0.05, 2 * n), 0)
        self.assertEqual(e.break_even_checks(e.per_check), float("inf"))
        self.assertAlmostEqual(e.break_even_fee(n), 0.05)

    def test_a_seat_is_drawn_for_3_of_7(self):
        self.assertAlmostEqual(G.seat_checks_month(70), 70 * 52 / 12 * 3 / 7)


class TestMarket(unittest.TestCase):
    def test_flat_fees_unchanged_and_check_gas_opt_in(self):
        flat = MS.run("market", 3)
        self.assertIsNone(flat.market.check_gas)
        self.assertEqual(flat.market.deposit(), flat.params.oracle_reserve)
        gas = MS.run("market", 3, check_gas=G.judge_table())
        self.assertEqual(gas.market.deposit(), gas.market.gas_reserve())

    def test_check_gas_charges_solvers_less_per_paid_fix_on_one_seed(self):
        from pof.sim import oraclenet as O
        f, g = O.market_row("market", 4, None), O.market_row("market", 4, G.judge_table())
        self.assertLess(g["check_fees_per_paid_fix"], f["check_fees_per_paid_fix"])

    def test_the_sim_verdict_is_usage_plus_the_fee(self):
        t = G.judge_table(service_fee=0.05)
        v = G.sim_verdict(t, "A", 200)
        u = G.review_usage(200)
        self.assertAlmostEqual(v, G.tokens_cost(t.family("anthropic"), u) + u.storage_mb * t.storage_mb + 0.05)
        self.assertGreater(G.sim_verdict(t, "A", 800), v)
        self.assertGreater(G.sim_run(t, 800), G.sim_run(t, 50) * MICRO / MICRO)


if __name__ == "__main__":
    unittest.main()
