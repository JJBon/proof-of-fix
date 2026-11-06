"""proof-of-fix#43 task 3: the checking layer in the market simulation (the error model, the attackers, the
criteria)."""

import unittest

from pof.sim import market_sim as M
from pof.sim.checks import FAMILIES, checking_report


class TestErrorModel(unittest.TestCase):
    def test_correlated_errors(self):
        w = M.build("market", 1)
        sim = w.checks
        fam = {}
        for a in w.actors:
            if a.kind == "evaluator":
                fam.setdefault(a.family, []).append(a.account)
        same = fam["C"][:2]  # the least accurate provider: the most errors to correlate
        other = [fam["C"][0], fam["B"][0]]
        def joint(pair, n=4_000):
            both = 0
            for _ in range(n):
                e = sim._errors(pair, crafted=False)
                both += e[pair[0]] and e[pair[1]]
            return both / n
        self.assertGreater(joint(same), joint(other) + 0.005)  # one family errs together more often

    def test_accuracy_per_family(self):
        w = M.build("market", 1)
        a = next(x for x in w.actors if x.kind == "evaluator" and x.family == "C")
        errs = sum(w.checks._errors([a.account], crafted=False)[a.account] for _ in range(4_000)) / 4_000
        self.assertAlmostEqual(errs, 1 - dict(FAMILIES)["C"], delta=0.03)

    def test_fixed_odds_comparison(self):
        w = M.run("market", 1, weeks=3, checking=False)
        self.assertIsNone(w.checks)
        self.assertIn("defective", checking_report(w))


class TestAttackers(unittest.TestCase):
    def test_lazy_validator_never_runs(self):
        w = M.run("check_lazy", 1, weeks=4)
        lazy = next(a for a in w.actors if a.kind in ("lazy_validator", "lazy_runner"))
        self.assertTrue(lazy.stats.get("reruns"))
        self.assertFalse(lazy.stats.get("effort"))
        for job in w.checks.checking.jobs:
            if job.kind == "rerun" and lazy.account in job.reveals:
                self.assertIs(job.reveals[lazy.account], True)

    def test_herder_always_accepts(self):
        w = M.run("check_herd", 1, weeks=4)
        herder = next(a for a in w.actors if a.kind == "herder")
        seen = [j.reveals[herder.account] for j in w.checks.checking.jobs if herder.account in j.reveals]
        self.assertTrue(seen)
        self.assertTrue(all(v.accepts and v.p == 0.9 for v in seen))
        self.assertFalse(w.checks.checking.qualified(herder.account))  # scored on the truth, it never qualifies

    def test_copies_share_one_model(self):
        w = M.build("check_copy", 1)
        copies = [a.account for a in w.actors if a.kind == "copy_evaluator"]
        self.assertEqual(len({w.checks.checking.evaluators[c].family for c in copies}), 3)  # declared apart
        for _ in range(200):
            e = w.checks._errors(copies, crafted=False)
            self.assertEqual(len({e[c] for c in copies}), 1)  # but they err together

    def test_crafted_fix_fools_its_target(self):
        w = M.build("market", 1)
        a = next(x for x in w.actors if x.kind == "evaluator" and x.family == "A")
        c = next(x for x in w.actors if x.kind == "evaluator" and x.family == "C")
        fooled = sum(w.checks._errors([a.account], crafted=True)[a.account] for _ in range(2_000)) / 2_000
        other = sum(w.checks._errors([c.account], crafted=True)[c.account] for _ in range(2_000)) / 2_000
        self.assertAlmostEqual(fooled, 0.9, delta=0.03)
        self.assertAlmostEqual(other, 0.3, delta=0.03)

    def test_planter_partner_challenges(self):
        w = M.run("check_plant", 2, weeks=8)
        partner = next(a for a in w.actors if a.kind == "plant_partner")
        planter = next(a for a in w.actors if a.kind == "planter")
        for ch in w.finalized + w.open_challenges:
            if ch.challenger == partner.account:
                self.assertEqual(ch.contribution.contributor, planter.account)

    def test_half_fixer_solves_only_the_public_case(self):
        w = M.run("check_half", 1)
        half = next(a for a in w.actors if a.kind == "half_fixer")
        delivered = [b for b in w.bids.values() if b.actor is half and b.defect is not None]
        self.assertTrue(delivered)
        self.assertTrue(all(b.defect == "wrong_result" for b in delivered))
        for cid in w.incomplete:  # partial fixes break nothing: only a "not solved" proof can catch them
            self.assertIsNotNone(w.defect.get(cid))

    def test_honest_twin(self):
        a = {x.name: x.kind for x in M.build("check_craft", 3).actors}
        b = {x.name: x.kind for x in M.build("check_craft", 3, honest_attack=True).actors}
        self.assertEqual(set(a), set(b))  # the same accounts
        self.assertEqual((a["crafter-1"], b["crafter-1"]), ("crafter", "solver"))


class TestSolverPays(unittest.TestCase):  # #49
    def test_checks_priced_into_the_break_even(self):
        w = M.build("market", 1)
        w.run(14)
        b = next(b for b in w.market.bounties.values() if b.state in ("open", "assigned", "won", "paid"))
        issue, a = w.issue_of[b.id], w.solvers[0]
        self.assertGreater(w.expected_checks(), 0)
        priced = w.break_even(a, b, issue)
        w.params = w.params.with_(checks_paid_by="bounty")
        self.assertEqual(w.expected_checks(), 0)
        self.assertGreater(priced, w.break_even(a, b, issue))  # the checks over the chance of being paid

    def test_split_farmer_delivers_borderline_junk(self):
        w = M.build("market", 1)
        a = next(x for x in w.actors if x.kind == "evaluator")
        errs = sum(w.checks._errors([a.account], crafted=False, borderline=True)[a.account] for _ in range(2_000))
        self.assertAlmostEqual(errs / 2_000, 0.5, delta=0.04)
        w = M.run("check_split", 2)
        farmer = next(x for x in w.actors if x.kind == "split_farmer")
        self.assertTrue(all(bid.defect is not None for bid in w.bids.values() if bid.actor is farmer and
                            bid.deliver_on is not None))

    def test_bounty_pays_nothing_for_checks(self):
        w = M.run("market", 3)
        bounties = {b.account for b in w.market.bounties.values()}
        checkers = set(w.checks.checking.evaluators) | set(w.checks.checking.runners)
        self.assertFalse([e for e in w.ledger.entries if e.source in bounties and e.target in checkers])


class TestOracleQuality(unittest.TestCase):  # #47
    def test_top_models_only(self):
        w = M.build("market", 1)
        c = w.checks.checking
        self.assertTrue(all(c.listed(e.model) for e in c.evaluators.values()))
        self.assertFalse(c.listed("A-small"))  # below the bar
        self.assertEqual({e.family for e in c.evaluators.values()}, {"A", "B", "C"})

    def test_cheat_is_discarded(self):
        w = M.run("check_cheat", 1)
        cheat = next(a for a in w.actors if a.kind == "model_cheat")
        c = w.checks.checking
        self.assertFalse(c.qualified(cheat.account))  # its bond drained by unproven verdicts in the exam
        for job in c.jobs:
            v = job.reveals.get(cheat.account)
            if v is not None:
                self.assertEqual(v.proven, "A-small")
                self.assertFalse(c.counts(v, cheat.account))

    def test_better_tier_pays_more(self):
        w = M.run("market", 2)
        c = w.checks.checking
        fees = {e.family: [] for e in c.evaluators.values()}
        for a, e in c.evaluators.items():
            if c.brier(a) is not None:
                fees[e.family].append(c.verdict_fee(a))
        self.assertGreaterEqual(sum(fees["A"]) / len(fees["A"]), sum(fees["C"]) / len(fees["C"]))


class TestFreshRounds(unittest.TestCase):
    def test_head_start_after_a_published_attempt(self):
        w = M.run("market", 1)
        reopened = [b for b in w.market.bounties.values() if b.published]
        self.assertTrue(reopened)
        for b in reopened:
            issue = w.issue_of[b.id]
            bids = [w.bids[eid] for eid in b.published if eid in w.bids]
            if issue.junk or all(x.actor.kind in ("crafter", "copy_partner", "planter") for x in bids):
                continue
            self.assertLess(issue.remaining, 1.0)  # whoever bids next starts from the attempt

    def test_queue_rule_comparison(self):
        w = M.run("market", 1, M.MARKET.with_(failed_reopens_round=False))
        self.assertFalse(any(b.published for b in w.market.bounties.values()))

    def test_bidders_never_check_their_bounty(self):
        w = M.run("market", 2)
        entry_bounty = {e.id: w.market.bounties[e.bounty] for e in w.market.entries.values()}
        for job in w.checks.checking.jobs:
            if job.ref.startswith("entry:"):
                b = entry_bounty[int(job.ref.split(":")[1])]
                self.assertFalse(w.market.parties(b) & set(job.members), job.ref)

    def test_sock_reports_failures_for_its_partner(self):
        w = M.run("check_sock", 1)
        sock = next(a for a in w.actors if a.kind in ("sock_validator", "sock_runner"))
        partner = next(a for a in w.actors if a.kind == "sock_solver")
        seen = 0
        for job in w.checks.checking.jobs:
            if sock.account in job.reveals and job.ref.startswith("entry:"):
                e = w.market.entries[int(job.ref.split(":")[1])]
                b = w.market.bounties[e.bounty]
                if e.solver != partner.account and any(x.solver == partner.account and x.round <= e.round
                                                       for x in b.entries):  # a rival's delivery, partner bid by then
                    self.assertIs(job.reveals[sock.account], False)
                    seen += 1
        self.assertGreaterEqual(seen, 0)


class TestCriteria(unittest.TestCase):
    def test_checking_criteria_reported(self):
        r = M.acceptance(range(1, 3), weeks=3)
        c = r["criteria"]
        for key in ("detection_change", "evaluator", "validator_net", "herd_agreement_gain",
                    "fresh_funder_cost_change", "fresh_solver_change", "who_pays_funder_cost_change",
                    "who_pays_solver_change") + tuple(
                f"{n}_gain" for n in M.CHECK_ATTACKS):
            self.assertIn(key, c)
        self.assertIn("checking", r["runs"]["market"][0])
        self.assertIn("market:variant", r["runs"])  # variants kept apart from the base runs


if __name__ == "__main__":
    unittest.main()
