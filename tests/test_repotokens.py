"""Per-repository tokens and the self-farmer (proof-of-fix#177, pof.sim.repotokens)."""

import math
import unittest

from pof.sim import repotokens as RT


class RepoTokensTest(unittest.TestCase):
    def test_fixed_emission_is_cheap_to_farm(self):
        r = RT.run(1, RT.Rule("fixed"))
        year = sum(1_000 * (1 - RT.DECAY) ** k for k in range(RT.WEEKS))
        self.assertAlmostEqual(r.farmer_tokens, year, places=3)  # one trivial fix a week takes it all
        self.assertAlmostEqual(r.break_even, RT.WEEKS * RT.Costs().per_fix(5.0) / year, places=9)

    def test_coin_rule_needs_outside_coin(self):
        sim = RT.Sim(1, RT.Rule("coin"))
        tokens, _ = sim.farmer(RT.Strategy(fixes=5, coin=50.0, socks=0, rep=False))
        self.assertEqual(tokens, 0.0)  # funding its own fix as the solver counts for nothing

    def test_coin_rule_is_bounded_by_the_ai_weight(self):
        a, _ = RT.Sim(1, RT.Rule("coin")).farmer(RT.Strategy(1, 50.0, 3, False))  # above any $5 weight
        b, _ = RT.Sim(1, RT.Rule("coin")).farmer(RT.Strategy(1, 500.0, 3, False))
        self.assertAlmostEqual(b, a, places=6)  # past the weight, more circled coin mints nothing more

    def test_reputation_without_history_mints_nothing(self):
        tokens, _ = RT.Sim(1, RT.Rule("reputation")).farmer(RT.Strategy(5, 50.0, 3, False))
        self.assertEqual(tokens, 0.0)

    def test_burn_raises_the_break_even_by_the_floor(self):
        a = RT.run(2, RT.Rule("coin"))
        b = RT.run(2, RT.Rule("coin", burn=0.05))
        self.assertAlmostEqual(b.break_even - a.break_even, 0.05, places=6)

    def test_activation_waits_for_reputable_funders(self):
        r = RT.run(1, RT.Rule("reputation", activate=5))
        self.assertGreater(r.honest_weeks_to_activate, 0)
        self.assertEqual(r.strategy.socks, 10)  # 3 socks can't turn it on

    def test_contract_fees_are_lower(self):
        self.assertLess(RT.CONTRACT_COSTS.per_fix(100.0), RT.Costs().per_fix(100.0))

    def test_single_token_shares_a_pool(self):
        be, tokens, tpd = RT.single_token(1)
        self.assertTrue(math.isfinite(be) and tokens > 0 and tpd > 0)

    def test_judges_seeing_through_everything_is_the_trivial_case(self):
        a = RT.run(1, RT.Rule("coin"), RT.World())
        b = RT.run(1, RT.Rule("coin"), RT.World(manufactured=200.0, detect=1.0))
        self.assertAlmostEqual(a.break_even / b.break_even, 1.0, delta=0.01)  # the same, but for noise draws

    def test_manufactured_importance_lowers_the_break_even(self):
        a = RT.run(1, RT.Rule("coin"), RT.World(), RT.CONTRACT_COSTS)
        b = RT.run(1, RT.Rule("coin"), RT.World(manufactured=200.0), RT.CONTRACT_COSTS)
        self.assertLess(b.break_even, a.break_even / 10)

    def test_cycle_vesting_costs_honest_projects_when_reach_dips(self):
        a = RT.cycle_run(1, RT.Cycle(need=5))
        b = RT.cycle_run(1, RT.Cycle(need=5, vest_weeks=13))
        self.assertLessEqual(b[1], a[1] + 1e-9)  # tokens per dollar funded


    def test_hybrid_cap_needs_coin_behind_manufactured_importance(self):
        """With the split capped by outside coin, a fee on that coin makes faked importance cost money: farming must
        wait for a much higher token price than without the cap, at the same detection."""
        w, costs = RT.World(manufactured=200.0, detect=0.8), RT.replace(RT.Costs(), market_fee=0.2)
        plain = RT.cycle_run(1, RT.Cycle(need=5), w, costs)
        hybrid = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True), w, costs)
        self.assertGreater(hybrid[0] * hybrid[1], 2 * plain[0] * plain[1])

    def test_hybrid_without_a_fee_is_no_better(self):
        """The cap alone does nothing: the farmer's coin comes back to it as the solver."""
        w = RT.World(manufactured=200.0, detect=0.8)
        plain = RT.cycle_run(1, RT.Cycle(need=5), w, RT.CONTRACT_COSTS)
        hybrid = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True), w, RT.CONTRACT_COSTS)
        self.assertLessEqual(hybrid[0] * hybrid[1], plain[0] * plain[1] * 1.05)


    def test_capped_break_even(self):
        # profit = 10p - 5 - min(1, 2p): the cap binds from p = 0.5, so 10p - 6 = 0 at p = 0.6
        self.assertAlmostEqual(RT._capped_break_even(10.0, 5.0, [(2.0, 1.0)]), 0.6, places=6)
        self.assertEqual(RT._capped_break_even(1.0, 5.0, [(2.0, 1e12)]), float("inf"))  # fee outgrows tokens

    def test_a_pot_fee_costs_honest_funders_beta_of_their_token_value(self):
        r = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True, pot_fee=0.3), RT.World(), RT.replace(RT.Costs(), market_fee=0))
        self.assertAlmostEqual(r[5] / r[1], 0.3, delta=0.03)

    def test_an_uncapped_pot_fee_protects_less_than_a_flat_fee(self):
        """#182: a fee that shrinks with the token's price costs the farmer little where its break-even lies."""
        w = RT.World(manufactured=200.0, detect=0.8)
        flat = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True), w, RT.replace(RT.Costs(), market_fee=0.2))
        pot = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True, pot_fee=0.3), w, RT.replace(RT.Costs(), market_fee=0))
        self.assertLess(pot[0] * pot[1], flat[0] * flat[1] / 2)

    def test_the_capped_pot_fee_protects_like_the_flat_fee(self):
        w = RT.World(manufactured=200.0, detect=0.8)
        flat = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True), w, RT.replace(RT.Costs(), market_fee=0.2))
        capped = RT.cycle_run(1, RT.Cycle(need=5, cap_coin=True, pot_fee=1.0, pot_cap=0.2), w,
                              RT.replace(RT.Costs(), market_fee=0))
        self.assertGreater(capped[0] * capped[1], 0.9 * flat[0] * flat[1])


if __name__ == "__main__":
    unittest.main()
