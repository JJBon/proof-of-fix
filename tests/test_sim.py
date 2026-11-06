"""Tasks 7.1-7.3: actors behave as configured, runs are reproducible, the replay matches the baseline, and the
report and acceptance check flag an unsound parameter set."""

import unittest
from dataclasses import replace

from pof import credits

from pof.params import LEGACY
from pof.sim import actors as A
from pof.sim import scenarios as S
from pof.sim.actors import Actor
from pof.sim.baseline import load, size_sampler, weekly_volume
from pof.sim.report import acceptance, report
from pof.sim.world import World

BASELINE = load()


def world(people, seed=1, maintainer=None, params=LEGACY):
    return World(params, seed, people, size_sampler(BASELINE), maintainer=maintainer)


def crew(*extra):
    """Enough validators and a hunter for anything to be judged, plus the actors under test."""
    return [Actor(f"v{i}", "validator", A.VALIDATOR) for i in range(12)] + list(extra)


class TestActors(unittest.TestCase):
    def test_honest_contributor_submits_at_its_rate(self):
        # enough capital for 3.5 PRs a week with 75-credit stakes held ~5 weeks (proof-of-fix#10: capital is a limit)
        dev = Actor("dev", "honest", replace(A.HONEST, submissions_per_week=3.5, endowment=credits(5_000)))
        w = world(crew(dev)).run(28)
        self.assertTrue(8 <= dev.stats["submitted"] <= 22, dev.stats)  # about 14 over four weeks

    def test_spammer_stays_small(self):
        spam = Actor("s", "spammer", A.SPAMMER)
        w = world(crew(spam)).run(14)
        self.assertTrue(all(lines <= A.SPAMMER.max_lines for _, lines in w.stream))
        self.assertGreater(spam.stats["submitted"], 3)

    def test_splitter_splits(self):
        split = Actor("x", "splitter", replace(A.SPLITTER, submissions_per_week=7))
        w = world(crew(split)).run(3)
        self.assertEqual(len(w.stream) % A.SPLITTER.split_into, 0)
        self.assertGreaterEqual(len(w.stream), A.SPLITTER.split_into)

    def test_griefer_files_false_challenges_and_loses(self):
        dev = Actor("dev", "honest", replace(A.HONEST, submissions_per_week=7, defect_bps=0))
        grief = Actor("g", "griefer", replace(A.GRIEFER, false_challenges_per_day=1.0))
        w = world(crew(dev, grief)).run(21)
        self.assertGreater(grief.stats.get("challenges", 0), 3)
        self.assertEqual(sum(bool(ch.outcome) for ch in w.challenges.challenges.values()), 0)
        self.assertLess(w.net(grief), 0)

    def test_colluders_protect_their_group(self):
        ally = Actor("ally", "spammer", replace(A.SPAMMER, defect_bps=10_000, checks_catch_bps=0), group="ring")
        ring = [Actor(f"c{i}", "colluder", replace(A.COLLUDER, validator_stake=10**12, endowment=10**12 + 10**8),
                      group="ring") for i in range(3)]
        hunter = Actor("h", "hunter", replace(A.HUNTER, hunt_daily_bps=10_000))
        w = world(crew(ally, hunter, *ring), params=LEGACY.with_(replay_inconclusive_bps=10_000)).run(21)
        votes = [v for ch in w.challenges.challenges.values() for p in ch.panels for m, v in p.verdicts.items()
                 if w.by_account[m].group == "ring"]
        self.assertTrue(votes)
        self.assertFalse(any(votes))  # every colluder vote rejects challenges against the ally

    def test_self_interested_owner_declines_others(self):
        owner = Actor("owner", "owner", replace(A.OWNER_SELF_INTERESTED, decline_others_bps=10_000))
        dev = Actor("dev", "honest", replace(A.HONEST, submissions_per_week=7, defect_bps=0, false_check_failure_bps=0))
        w = world(crew(dev, owner), maintainer=owner).run(14)
        self.assertGreater(owner.stats.get("declined_others", 0), 0)
        # proof-of-fix#10: declines over the limit need a panel, and unjustified ones can be overturned on appeal
        declined = sum(c.state == "declined" for c in w.life.contributions.values())
        self.assertEqual(owner.stats["declined_others"], declined + dev.stats.get("decline_overturned", 0))
        self.assertGreater(w.panels["declines_over_limit"] + w.panels["decline_appeals"], 0)
        # the split-shift move now goes to a panel without the owner, which refuses it (proof-of-fix#10)
        self.assertTrue(any(e.kind == "params_panel" and "rejected" in e.detail for e in w.ledger.events))
        self.assertEqual(w.panels["split_changes_refused"], 1)


class TestFixesActors(unittest.TestCase):
    """proof-of-fix#10 task 5.1: the new actors, each alone, acting as configured."""

    def test_padder_pads(self):
        pad = Actor("p", "padder", replace(A.PADDER, submissions_per_week=7, max_lines=10))
        w = world(crew(pad)).run(7)
        self.assertTrue(w.stream and all(lines % A.PADDER.pad_factor == 0 for _, lines in w.stream))

    def test_newcomer_is_sponsored(self):
        sponsor = Actor("s", "honest", replace(A.HONEST, submissions_per_week=7, defect_bps=0, false_check_failure_bps=0))
        newcomer = Actor("n", "newcomer", replace(A.NEWCOMER, submissions_per_week=7, defect_bps=0), sponsor=sponsor)
        w = world(crew(sponsor, newcomer)).run(35)
        sponsored = [c for c in w.life.contributions.values() if c.sponsor == sponsor.account]
        self.assertTrue(sponsored)
        self.assertTrue(all(c.contributor == newcomer.account for c in sponsored))

    def test_abuser_sponsors_sybils(self):
        abuser = Actor("a", "abuser", replace(A.ABUSER, submissions_per_week=7, defect_bps=0), cohort="abuse")
        sybils = [Actor(f"s{i}", "sybil", A.SYBIL, sponsor=abuser, cohort="abuse") for i in range(2)]
        w = world(crew(abuser, *sybils)).run(35)
        self.assertTrue(any(c.sponsor == abuser.account for c in w.life.contributions.values()))
        self.assertTrue(any(s.stats.get("unaffordable") for s in sybils))  # refused until the abuser is proven

    def test_hunting_responds_to_pay(self):
        def factor(e):
            w = S.build("spam", 3, hunt_elasticity=e)
            w.run(21)
            return w.hunt_factor
        self.assertEqual(factor(0.0), 1.0)
        self.assertGreater(factor(0.5), 1.0)

    def test_reviewers_report_and_file(self):
        w = S.run("spam", 4, weeks=3, review_detect_bps=10_000)
        reviews = sum(a.stats.get("reviews", 0) for a in w.actors)
        self.assertGreater(reviews, 0)
        filed_by_reviewers = sum(a.stats.get("challenges", 0) for a in w.actors if a.kind == "validator")
        self.assertGreater(filed_by_reviewers, 0)


class TestPledgeActors(unittest.TestCase):
    """proof-of-fix#19 task 3.1: contributors pledge when short; the stacker turns and stacks on its pledges."""

    def test_a_short_contributor_pledges(self):
        dev = Actor("d", "honest", replace(A.HONEST, endowment=credits(300), submissions_per_week=7, defect_bps=0,
                                           false_check_failure_bps=0))
        w = world(crew(dev), params=LEGACY.with_(release_funding=credits(500))).run(56)  # modest rewards
        pledged = [c for c in w.life.contributions.values() if w.pledged.get(c.id)]
        self.assertTrue(dev.stats.get("pledges") and pledged)
        for c in pledged:
            self.assertLessEqual(w.pledged[c.id], c.stake * LEGACY.pledge_max_stake_bps // 10_000)

    def test_no_pledges_without_the_cap(self):
        dev = Actor("d", "honest", replace(A.HONEST, endowment=credits(300), submissions_per_week=7, defect_bps=0))
        w = world(crew(dev), params=LEGACY.with_(pledge_max_stake_bps=0)).run(56)
        self.assertFalse(w.pledged)

    def test_stacker_turns_and_stacks(self):
        stacker = Actor("s", "stacker", replace(A.STACKER, submissions_per_week=7, defect_bps=0, endowment=credits(300)))
        hunters = [Actor(f"h{i}", "hunter", A.HUNTER) for i in range(3)]
        w = world(crew(stacker, *hunters)).run(56)
        mine = [c for c in w.life.contributions.values() if c.contributor == stacker.account]
        before = [c for c in mine if c.submitted_day < A.STACKER.stack_from_day]
        after = [c for c in mine if c.submitted_day >= A.STACKER.stack_from_day]
        self.assertTrue(before and after)
        self.assertFalse(any(w.defect.get(c.id) for c in before))  # honest while it builds accepted work
        self.assertGreater(sum(1 for c in after if w.defect.get(c.id)) / len(after), 0.3)
        self.assertTrue(stacker.stats.get("slashed"))  # its stacked defects are caught (pledging: test_pledges)
        self.assertTrue(w.ledger.conserved())


class TestIndexGamer(unittest.TestCase):
    """proof-of-fix#23 task 3.1: the index gamer floods, which lowers the index, then turns."""

    def test_gamer_floods_then_turns(self):
        others = [Actor(f"d{i}", "honest", replace(A.HONEST, submissions_per_week=3)) for i in range(4)]
        gamer = Actor("g", "gamer", A.INDEX_GAMER)
        hunters = [Actor(f"h{i}", "hunter", A.HUNTER) for i in range(3)]
        w = world(crew(gamer, *others, *hunters)).run(56)
        quiet = world(crew(*[Actor(f"d{i}", "honest", replace(A.HONEST, submissions_per_week=3)) for i in range(4)],
                           *[Actor(f"h{i}", "hunter", A.HUNTER) for i in range(3)])).run(21, drain_days=0)
        flooded = world(crew(Actor("g", "gamer", A.INDEX_GAMER),
                             *[Actor(f"d{i}", "honest", replace(A.HONEST, submissions_per_week=3)) for i in range(4)],
                             *[Actor(f"h{i}", "hunter", A.HUNTER) for i in range(3)])).run(21, drain_days=0)
        self.assertLess(flooded.life.reward_per_weight, quiet.life.reward_per_weight)  # the flood lowers the index
        mine = [c for c in w.life.contributions.values() if c.contributor == gamer.account]
        before = [c for c in mine if c.submitted_day < A.INDEX_GAMER.stack_from_day]
        after = [c for c in mine if c.submitted_day >= A.INDEX_GAMER.stack_from_day]
        self.assertTrue(before and after)
        self.assertTrue(all(c.changed_lines <= 20 and not w.defect.get(c.id) for c in before))  # small and sound
        self.assertGreater(sum(1 for c in after if w.defect.get(c.id)) / len(after), 0.3)
        r = report(w, "test", 1)
        self.assertIn("g", r["turning_actors"])
        self.assertIn("contributors_pool_end", r)
        self.assertTrue(w.ledger.conserved())


class TestScenarios(unittest.TestCase):
    def test_same_seed_same_result(self):
        a, b = S.run("spam", 7, weeks=3), S.run("spam", 7, weeks=3)
        self.assertEqual(a.ledger.entries, b.ledger.entries)
        self.assertEqual(report(a, "spam", 7), report(b, "spam", 7))
        self.assertNotEqual(S.run("spam", 8, weeks=3).ledger.entries, a.ledger.entries)

    def test_collusion_counterfactual_differs_only_in_the_ring(self):
        ring = S.build("collusion", 1, share=0.4)
        honest = S.build("collusion", 1, share=0.4, honest_ring=True)
        self.assertEqual([(a.name, a.kind, a.cohort, a.behaviour) for a in ring.actors],
                         [(a.name, a.kind, a.cohort, a.behaviour) for a in honest.actors])
        self.assertEqual({a.group for a in ring.actors if a.cohort == "ring"}, {"ring"})
        self.assertEqual({a.group for a in honest.actors}, {None})

    def test_replay_matches_the_baseline(self):
        w = S.run("replay", 3, weeks=4, mechanism=False)
        sizes = sorted(lines for _, lines in w.stream)
        median = sizes[len(sizes) // 2]
        self.assertLessEqual(abs(median - BASELINE["merged"]["changed_lines"]["p50"]) / 76, 0.25, median)
        weekly = len(w.stream) / 4
        self.assertLessEqual(abs(weekly - weekly_volume(BASELINE)) / weekly_volume(BASELINE), 0.15, weekly)

    def test_every_scenario_runs_and_conserves(self):
        for name, knobs in (("honest", {}), ("griefing", {}), ("collusion", {"share": 0.4}),
                            ("owner", {"self_interested": True}), ("risk", {"multiplier": 3}), ("replay", {})):
            w = S.run(name, 1, weeks=2, **knobs)
            self.assertTrue(w.ledger.conserved(), name)


class TestReport(unittest.TestCase):
    def test_report_has_every_metric(self):
        r = report(S.run("griefing", 1, weeks=2), "griefing", 1)
        for key in ("returns", "contributions", "escaped_regressions", "mean_days_to_settle", "validator_workload",
                    "releases", "author_escrow", "owner_payout", "params", "seed"):
            self.assertIn(key, r)
        for kind in r["returns"].values():
            self.assertEqual(set(kind), {"actors", "mean_return", "return_per_action", "return_per_stake",
                                         "unaffordable_submissions", "pledges", "lines_accepted"})
        self.assertEqual(set(r["pledges"]), {"made", "amount", "lost_to_slashes", "lost_to_clawbacks"})

    def test_capital_criterion_reports_both_runs(self):
        result = acceptance([1], weeks=2, only=("capital",))
        replays = result["runs"]["replay"]
        self.assertEqual(len(replays), 2)
        differ = {k for k in replays[0]["params"] if replays[0]["params"][k] != replays[1]["params"][k]}
        self.assertEqual(differ, {"stake_per_reward_bps", "reward_cap_stake_multiple"})  # the fixed-stake rules only
        capital = result["criteria"]["capital"]
        self.assertIn("unaffordable_proposed", capital)
        self.assertIn("unaffordable_fixed_stake", capital)

    def test_unsound_parameters_are_flagged(self):
        # no cost for a false challenge: griefing stops losing money, and the check must say so
        free = LEGACY.with_(challenger_stake_bps=0, rejected_challenge_loss_bps=0, filing_fee_bps=0)
        result = acceptance([1], free, weeks=2, only=("griefing",))
        flagged = [f for f in result["failures"] if f["criterion"] == "griefing loses money" and f["scenario"] == "griefing"]
        self.assertTrue(flagged, result["failures"])
        self.assertEqual(flagged[0]["seed"], 1)


class TestSummary(unittest.TestCase):
    def test_summary_has_every_table(self):
        from pof.sim.summary import summarize

        s = summarize(range(1, 3), weeks=2)
        for key in ("returns", "criteria", "collusion", "owner", "hunt_elasticity_sweep", "review_detection_sweep",
                    "ablation", "risk", "replay", "unaffordable_submissions", "passed"):
            self.assertIn(key, s)
        self.assertEqual(set(s["hunt_elasticity_sweep"]), {"0.0", "0.5", "1.0"})
        self.assertIn("no review duty", s["ablation"])
        for key in ("pledge_stake_cap_sweep", "pledge_escrow_cap_sweep", "pledges", "stake_index_sweep",
                    "reward_cap_sweep", "reward_to_stake", "turning_actors", "contributors_pool_end"):
            self.assertIn(key, s)
        for row in ("no pledges", "no index (fixed stake)", "no reward cap"):
            self.assertIn(row, s["ablation"])
        self.assertEqual(set(s["reward_cap_sweep"]), {"0", "4", "6", "8", "16"})
        self.assertEqual(set(s["pledge_stake_cap_sweep"]), {"0", "2500", "5000", "7500"})
        self.assertEqual(len(s["collusion"]), len(S.COLLUSION_SHARES))


if __name__ == "__main__":
    unittest.main()
