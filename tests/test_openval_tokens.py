"""The validators' token slice (proof-of-fix#142, pof.sim.openval.tokens): simulation only."""

import unittest
from dataclasses import replace

from pof.sim.openval import pricing as PR, rerun as RR, tokens as TK
from pof.sim.openval.params import V2R3, WEEK


def run(bps=1000, price=0.05, mode="work", basis="paid", seed=3):
    p = replace(V2R3, VAL_SLICE_BPS=bps, VAL_SLICE_MODE=mode, VAL_SLICE_BASIS=basis)
    return PR.run_market(seed, p, replace(RR.MARKET_W, token_price=price))


class TokenSliceTest(unittest.TestCase):
    def test_off_changes_nothing(self):
        a = PR.run_market(3, V2R3, RR.MARKET_W)
        b = PR.run_market(3, V2R3, replace(RR.MARKET_W, token_price=0.2))  # a price alone mints nothing
        self.assertIsNone(a.slice)
        self.assertEqual(RR.honest_breakdown(a), RR.honest_breakdown(b))
        self.assertTrue(all(v.acct.tokens == 0 for v in a.reg.validators.values()))

    def test_conserved(self):
        for mode in ("work", "work_rank", "rank"):
            n = run(mode=mode)
            sl = n.slice
            slices = sum(wk["slice"] for wk in sl.weeks)
            self.assertAlmostEqual(sl.minted + sl.unminted, slices, places=6)
            self.assertAlmostEqual(sum(v.acct.tokens for v in n.reg.validators.values()), sl.minted, places=6)
            self.assertEqual(len(sl.weeks), int(n.t // WEEK))

    def test_emission_decays(self):
        sl = run().slice
        self.assertAlmostEqual(sl.emission(0), 10_000.0)
        self.assertAlmostEqual(sl.emission(69) / sl.emission(0), 0.99 ** 69)

    def test_only_standing_verdicts_earn(self):
        n = run(basis="verdicts")
        sl = n.slice
        sl.work, sl.slots = [], 0
        sub = next(s for s in n.subs.values() if s.judges and s.tier == "issue")
        judges = [(sub.judges[0][0], True, False), (sub.judges[-1][0], False, False)]
        sub = replace(sub, judges=judges, audit="")
        sl.on_final(sub, False)  # the second judge's vote stood; the first one's was reversed
        self.assertEqual([vid for vid, _ in sl.work], [judges[1][0]])

    def test_paid_basis_skips_failed_bounties(self):
        n = run(basis="paid")
        sl = n.slice
        sl.work, sl.slots = [], 0
        sub = next(s for s in n.subs.values() if s.judges and s.tier == "issue")
        sl.on_final(replace(sub, judges=[(sub.judges[0][0], False, False)]), False)
        self.assertEqual(sl.work, [])

    def test_rank_pays_at_most_the_top_share(self):
        n = run(mode="rank")
        for wk in n.slice.weeks:
            active = sum(1 for v in n.reg.validators.values())
            self.assertLessEqual(wk["ranked"], active)

    def test_tokens_are_in_the_net(self):
        n = run(price=0.2)
        v = max(n.reg.validators.values(), key=lambda v: v.acct.tokens)
        before = n.validator_net(v)
        n.w = replace(n.w, token_price=0.0)
        self.assertAlmostEqual(before - n.validator_net(v), v.acct.tokens * 0.2, places=6)
        self.assertIn("tokens", TK.honest_month(n))


if __name__ == "__main__":
    unittest.main()
