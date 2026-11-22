"""proof-of-fix#27: funding that follows use, defective work judged with clustered standard errors, splitting per
accepted line, three abusers, and sweeps on their own seeds."""

import unittest

from pof import BPS, credits, share
from pof.params import LEGACY, ParamsError
from pof.sim import scenarios as S
from pof.sim.report import ATTACKERS, MIN_DEFECTIVE_SAMPLE, acceptance, judge_defective, pooled

from test_fixes import World


class TestParams(unittest.TestCase):
    def test_buffer_not_negative(self):
        with self.assertRaises(ParamsError):
            LEGACY.with_(pool_buffer_releases=-1)
        LEGACY.with_(pool_buffer_releases=0)


class TestFundingFollowsUse(World):
    def full_share(self, p=LEGACY):
        return share(p.release_funding, p.release_split_bps["contributors"])

    def fill_pool(self, amount):
        self.ledger.issue(self.rel.contributors_pool, amount, "release_funding", "setup", 0)

    def test_pool_within_the_buffer(self):
        self.fill_pool(LEGACY.pool_buffer_releases * self.full_share())
        r = self.rel.open_release(1)
        self.assertEqual(sum(r.split.values()), LEGACY.release_funding)
        self.assertFalse([e for e in self.ledger.events if e.kind == "funding_scaled"])

    def test_pool_over_the_buffer(self):
        surplus = self.full_share() // 4
        self.fill_pool(LEGACY.pool_buffer_releases * self.full_share() + surplus)
        r = self.rel.open_release(1)
        funding = sum(r.split.values())
        self.assertEqual(funding, LEGACY.release_funding - LEGACY.release_funding * surplus // self.full_share())
        for name, bps in LEGACY.release_split_bps.items():  # the published shares, of the reduced funding
            if name != "insurance":  # insurance also takes the rounding remainder
                self.assertEqual(r.split[name], share(funding, bps))
        scaled = [e for e in self.ledger.events if e.kind == "funding_scaled"]
        self.assertEqual(len(scaled), 1)
        self.assertIn(f"factor_bps={funding * BPS // LEGACY.release_funding}", scaled[0].detail)

    def test_far_over_the_buffer_funds_nothing(self):
        self.fill_pool((LEGACY.pool_buffer_releases + 2) * self.full_share())
        r = self.rel.open_release(1)
        self.assertEqual(sum(r.split.values()), 0)

    def test_buffer_switched_off(self):
        self.rel.params = LEGACY.with_(pool_buffer_releases=0)
        self.fill_pool(10 * self.full_share())
        r = self.rel.open_release(1)
        self.assertEqual(sum(r.split.values()), LEGACY.release_funding)


class TestPooledStatistic(unittest.TestCase):
    def test_known_values(self):
        rows = [(-10.0, 2), (-30.0, 3), (-5.0, 1)]  # totals and counts per run
        m, se, n = pooled(rows)
        self.assertEqual(n, 6)
        self.assertAlmostEqual(m, -45 / 6)
        k = 3
        expected = (k / (k - 1) * sum((t - m * c) ** 2 for t, c in rows) / 36) ** 0.5
        self.assertAlmostEqual(se, expected)

    def test_empty_and_single_run(self):
        self.assertEqual(pooled([]), (0.0, 0.0, 0))
        self.assertEqual(pooled([(-4.0, 2)]), (-2.0, 0.0, 2))


def runs(mean, spread, n_runs=20, per_run=5):
    """Hand-made per-run (total, count) rows around a mean, alternating +/- spread per contribution."""
    return [((mean + (spread if i % 2 else -spread)) * per_run, per_run) for i in range(n_runs)]


class TestDefectiveVerdicts(unittest.TestCase):
    def test_attacker_loses(self):
        self.assertEqual(judge_defective("spammer", runs(-10, 2))["verdict"], "loses")

    def test_attacker_not_shown_fails(self):
        self.assertEqual(judge_defective("spammer", runs(-1, 20))["verdict"], "not shown")

    def test_attacker_pays(self):
        self.assertEqual(judge_defective("spammer", runs(10, 2))["verdict"], "pays")

    def test_attacker_inconclusive_under_the_minimum(self):
        few = runs(-50, 1, n_runs=MIN_DEFECTIVE_SAMPLE // 5 - 1)
        v = judge_defective("abuser", few)
        self.assertEqual(v["verdict"], "inconclusive")
        self.assertLess(v["n"], MIN_DEFECTIVE_SAMPLE)

    def test_honest_kinds_only_fail_if_they_gain(self):
        self.assertNotIn("newcomer", ATTACKERS)
        self.assertEqual(judge_defective("newcomer", runs(1, 20))["verdict"], "ok")  # positive but not significant
        self.assertEqual(judge_defective("owner", runs(10, 2))["verdict"], "pays")

    def test_acceptance_names_the_failure(self):
        result = acceptance([1], weeks=2, only=("sponsorship",))  # too few contributions in two weeks: inconclusive
        crits = {f["criterion"] for f in result["failures"]}
        self.assertTrue(any(c.startswith("defective work loses money") for c in crits), result["failures"])


class TestSplittingPerLine(unittest.TestCase):
    def test_reported_per_accepted_line(self):
        c = acceptance([1, 2], weeks=3, only=("spam",))["criteria"]
        self.assertEqual(c["splitting"]["per"], "accepted line")
        self.assertIn("lines_accepted_split", c["splitting"])
        self.assertIn("lines_accepted_unsplit", c["splitting"])
        self.assertIn("splitting_total", c)  # the old total-return comparison stays visible


class TestThreeAbusers(unittest.TestCase):
    def test_each_abuser_has_its_own_fake_accounts(self):
        w = S.build("sponsorship", 1)
        abusers = [a for a in w.actors if a.kind == "abuser"]
        self.assertEqual(len(abusers), 3)
        for a in abusers:
            self.assertEqual(sum(1 for s in w.actors if s.kind == "sybil" and s.sponsor is a), 4)
        self.assertEqual(sum(1 for a in S.build("sponsorship", 1, no_sybils=True).actors if a.kind == "sybil"), 0)


class TestSweepSeeds(unittest.TestCase):
    def test_sweeps_use_their_own_seeds(self):
        from pof.sim.summary import summarize

        s = summarize(range(1, 3), weeks=2, sweep_seeds=range(1, 2))
        self.assertEqual((s["seeds"], s["sweep_seeds"]), (2, 1))
        self.assertEqual(set(s["pool_buffer_sweep"]), {"0", "1", "2", "4"})
        for row in s["ablation"].values():
            self.assertEqual(row["seeds"], 1)
            self.assertIn("verdicts", row)
            self.assertIn("passed_except_inconclusive", row)
        self.assertEqual({k: v["seeds"] for k, v in s["elasticity_verdicts"].items()}, {"0.0": 2, "1.0": 2})


if __name__ == "__main__":
    unittest.main()
