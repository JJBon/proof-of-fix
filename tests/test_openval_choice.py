"""#252: validators choose repositories (allow and deny lists respected by every draw), a repository's minimum of
eligible validators across TEE types, its stake cap, and the silence and broken-TEE attackers
(pof/sim/openval/choice.py; design D33, D34; reports/open-validators-measured-v6.md, simulation B)."""

import unittest
from dataclasses import replace

from pof.sim.openval import capacity as K
from pof.sim.openval import choice as B
from pof.sim.openval import nodeposit as N
from pof.sim.openval import sizing as Z
from pof.sim.openval.evidence import P0
from pof.sim.openval.net import ACTOR_VID, ISSUE, Net
from pof.sim.openval.params import PARAMS


def short(weeks=12, pool="hidden"):
    return replace(B.world(pool), weeks=weeks)


def run(p, h, kind="tee", nodes=3, form="one", honest=False, seed=3, w=None):
    w = w or short()
    a = B.RepoAttacker(honest, w, kind, nodes, form)
    return B.ChoiceNet(seed, p, w, [a], target_honest=h).run(), a


class TestDefaults(unittest.TestCase):
    def test_every_switch_is_off_by_default(self):
        self.assertEqual((PARAMS.REPO_LISTS, PARAMS.REPO_MIN_ELIGIBLE, PARAMS.REPO_STAKE_X), (False, 0, 0.0))

    def test_a_plain_net_refuses_the_switches(self):
        w = short()
        for kw in (dict(REPO_LISTS=True), dict(REPO_MIN_ELIGIBLE=3), dict(REPO_STAKE_X=0.1)):
            with self.assertRaises(ValueError):
                Net(1, replace(P0, **kw), w, [Z.OnMarket(w=w)])

    def test_lists_nobody_uses_change_nothing(self):
        w = replace(N.world("hidden", "anthropic", 3), weeks=8)
        a, b = N.BadFix(False, w), N.BadFix(False, w)
        old = N.NDNet(5, P0, w, [a]).run()
        new = B.ChoiceNet(5, replace(P0, REPO_LISTS=True), w, [b]).run()
        self.assertAlmostEqual(old.party_net(a.party), new.party_net(b.party), places=6)
        for k in ("paid", "bad_merged", "submitted", "audits", "challenges"):
            self.assertEqual(old.stats[k], new.stats[k], k)


class TestLists(unittest.TestCase):
    def test_no_validator_checks_a_repository_it_denied_or_did_not_allow(self):
        for kind in ("tee", "silence"):
            for form in ("one", "spread"):
                net, _ = run(B.BASE, 3, kind, 10, form)
                self.assertTrue(net.checked)
                for vid, r in net.checked:  # counted panels, audits, challenge and appeal panels
                    self.assertTrue(net.allowed(net.reg.validators[vid], r), (kind, form, vid, r))
                attackers = {vid for vid in net.reg.validators if vid >= ACTOR_VID}
                self.assertTrue(any(vid in attackers for vid, _ in net.checked) or kind == "silence")

    def test_the_target_is_judged_only_by_those_that_allow_it(self):
        net, _ = run(B.BASE, 3, nodes=0)
        on_target = {vid for vid, r in net.checked if r == B.TARGET}
        self.assertTrue(on_target)
        self.assertLessEqual(len(on_target), 3)

    def test_without_lists_every_validator_judges_everywhere(self):
        net, _ = run(replace(B.BASE, REPO_LISTS=False), 3, nodes=0)
        self.assertGreater(len({vid for vid, r in net.checked if r == B.TARGET}), 3)


class TestMinimum(unittest.TestCase):
    def test_one_tee_type_counts_at_most_its_share(self):
        net, _ = run(replace(B.BASE, REPO_MIN_ELIGIBLE=5), 1, nodes=10)  # 1 honest + 10 of one TEE type
        sub = next(s for s in list(net.subs.values()) + net.unlisted if net.repo.get(s.sid) == B.TARGET)
        self.assertEqual(sorted(v.tee for v in net.eligible(sub)).count("tdx"), 10)
        self.assertLessEqual(net.counted_eligible(sub), 2 + 1)

    def test_a_repository_below_the_minimum_lists_nothing_and_charges_nothing(self):
        net, a = run(replace(B.BASE, REPO_MIN_ELIGIBLE=3), 1, nodes=0)
        target = [s for s in net.unlisted if net.repo.get(s.sid) == B.TARGET]
        self.assertTrue(target)
        self.assertFalse(any(net.repo.get(s.sid) == B.TARGET for s in net.subs.values() if s.tier == ISSUE))
        self.assertTrue(all(net.repo.get(s.sid) == B.TARGET for s in net.unlisted))

    def test_the_stake_cap_bounds_every_listed_bounty(self):
        net, a = run(replace(B.BASE, REPO_STAKE_X=0.1), 1, nodes=10)
        target = [s for s in net.subs.values() if s.tier == ISSUE and net.repo.get(s.sid) == B.TARGET]
        self.assertTrue(target)
        self.assertTrue(all(s.bounty <= 125.0 + 1e-6 for s in target))  # 0.1 x the honest validator's $1,250
        self.assertGreater(net.stats["stake_capped"], 0)


class TestAttackers(unittest.TestCase):
    def test_silent_attackers_never_answer_on_the_target_and_are_suspended(self):
        net, a = run(B.BASE, 3, "silence", 3)
        nodes = net.party_validators(a.party)
        self.assertGreater(net.stats["silences"], 0)
        self.assertTrue(any(v.suspensions for v in nodes))
        self.assertGreater(sum(v.acct.slashed for v in nodes), 0)
        twin, t = run(B.BASE, 3, "silence", 3, honest=True)
        self.assertLess(net.party_net(a.party), twin.party_net(t.party))

    def test_a_broken_tee_passes_its_accomplices_fixes_unslashed_for_false_verdicts(self):
        net, a = run(B.BASE, 1, "tee", 3)
        mine = [s for s in net.subs.values() if s.party == a.party]
        self.assertTrue(mine and all(net.repo[s.sid] == B.TARGET for s in mine))
        self.assertGreater(sum(1 for s in mine if s.final), 0)
        self.assertEqual(net.stats["receipts_upheld"], 0)  # a faked model answer: nothing a re-run can prove

    def test_spread_attackers_submit_where_their_validators_are(self):
        net, a = run(B.BASE, 3, "tee", 3, "spread")
        self.assertEqual(set(a.repos), {0, 1, 2})
        self.assertEqual({net.repo[s.sid] for s in net.subs.values() if s.party == a.party}, {0, 1, 2})


if __name__ == "__main__":
    unittest.main()
