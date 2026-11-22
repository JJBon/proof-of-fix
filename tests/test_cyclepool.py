"""Cycle pools per repository, paid by merit, and inflated merit healed (proof-of-fix#184, pof.sim.cyclepool)."""

import unittest
from dataclasses import replace

from pof.sim import cyclepool as CP

FULL = dict(challenge=0.5, penalty=0.5, audit=0.10, later=0.10, stake=50.0)


def year(p, seeds=range(1, 6)):
    rs = [CP.run(s, p) for s in seeds]
    return rs, sum(sum(r.team_profit) for r in rs) / len(rs)


class CyclePoolTest(unittest.TestCase):
    def test_deterministic(self):
        a, b = CP.run(3, CP.Params()), CP.run(3, CP.Params())
        self.assertEqual(a.team_profit, b.team_profit)

    def test_with_no_defence_overclaiming_pays(self):
        rs, profit = year(CP.Params())
        self.assertGreater(profit, 0)
        self.assertGreater(min(r.investors_loss for r in rs), 0)

    def test_the_stake_makes_the_overclaim_lose(self):
        """With challenges, scores, audits and a stake forfeited by the 3x rule, a $200 claim on a $5 fix loses money,
        and so does the team's retreat to a claim within the rule."""
        for claim in (200.0, 15.0):
            _, profit = year(replace(CP.Params(), claim=claim, **FULL))
            self.assertLess(profit, 0, claim)

    def test_consensus_scores_backfire_under_a_colluding_majority_and_challenges_fix_it(self):
        def share(**kw):
            rs, _ = year(replace(CP.Params(), colluders=8, **kw))
            return sum(sum(r.colluders_draw_share[-13:]) / 13 for r in rs) / len(rs)
        none = share()
        self.assertGreater(share(penalty=0.5, audit=0.1), none)  # honest judges look like the outliers
        self.assertLess(share(penalty=0.5, audit=0.1, challenge=0.5), none)  # the challenge anchors the truth

    def test_honest_claims_rarely_forfeit(self):
        rs, _ = year(replace(CP.Params(), fakes=0, **FULL))
        for r in rs:
            self.assertLess(r.honest_fixers_loss, 0.02 * r.pool_total)

    def test_a_colluder_brought_back_costs_a_bond(self):
        cheap, _ = year(replace(CP.Params(), colluders=5, bond=0.0, **FULL))
        dear, _ = year(replace(CP.Params(), colluders=5, bond=1_000.0, **FULL))
        self.assertGreater(sum(sum(r.team_profit) for r in cheap), sum(sum(r.team_profit) for r in dear))


if __name__ == "__main__":
    unittest.main()
