"""proof-of-fix#43 tasks 1-2: the checking layer (signed re-runs, planted cases, the AI jury, scoring on the truth)
and delivery through it."""

import unittest

from pof import BPS, credits, share
from pof.challenges import ChallengeError, Proof
from pof.checking import Checking, CheckingError, seal
from pof.params import DEFAULTS, ParamsError

from test_market import MarketWorld
from test_market import P as DEFAULT_P

P = DEFAULT_P.with_(ci_mode="validators", checks_paid_by="bounty")  # these classes test CI by validators with
# #43's bounty-paid checks; TestAttested and TestSolverPays the defaults (#49)


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"rerun_quorum": 4}, {"rerun_quorum": 0}, {"jury_accept": 4}, {"jury_pool": 2},
                    {"planted_share_bps": BPS}, {"evaluator_bond": 0}, {"shadow_verdicts": 0},
                    {"planted_penalty_bps": BPS + 1}):
            with self.assertRaises(ParamsError, msg=bad):
                DEFAULTS.with_(**bad)


class Checks(MarketWorld):
    def setUp(self):
        super().setUp()
        self.m.params = P
        self.c = self.m.checking = self.rel.checking = Checking(self.ledger, P, self.vset, self.insurance)
        self.evaluators = []
        for i, fam in enumerate("ABCDE" * 3):  # 15, enough for a first jury of 3 and a second of 7
            a = self.ledger.open("actor")
            self.ledger.issue(a, credits(50), "endowment", "setup", 0)
            self.c.register_evaluator(a, f"op-{i}", fam, 0)
            self.evaluators.append(a)
        for a in self.evaluators:  # founding evaluators, calibrated
            self.c.evaluators[a].briers = [0.0] * P.shadow_verdicts

    def reruns(self, results, ref="entry:1", planted=None, exclude=frozenset()):
        """Re-runs with these results (None: committed, never revealed)."""
        job = self.c.start_reruns(ref, "seed", set(exclude), 3, planted)
        for m, r in zip(job.members, results):
            self.c.commit(job, m, seal(bool(r), f"s{m}"))
        for m, r in zip(job.members, results):
            if r is not None:
                self.assertTrue(self.c.reveal_rerun(job, m, r, f"s{m}"))
        return job

    def verdicts(self, job, rows):
        """(accepts, p, evidence) per member, in order; None: no reveal."""
        for m, row in zip(job.members, rows):
            row = row or (True, 0.5, "x")
            self.c.commit(job, m, seal(*row, f"v{m}"))
        for m, row in zip(job.members, rows):
            if row is not None:
                self.assertTrue(self.c.reveal_verdict(job, m, *row, f"v{m}"))

    def delivery(self, jury_rows, rerun_results=(True, True, True)):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        ref = f"entry:{e.id}"
        reruns = self.reruns(list(rerun_results), ref=ref, exclude=self.m.parties(b))
        self.c.close_reruns(reruns, 3)
        jury = self.c.draw_jury(ref, "s", self.m.parties(b))
        self.verdicts(jury, jury_rows)
        return b, e, reruns, jury

    def fees(self, reruns, *juries):
        """The oracle fees a delivery's checks cost: matching re-runs, the hidden tests' runner, and each counted
        verdict at its evaluator's own tier fee (#47)."""
        runs = sum(1 for m in reruns.members if reruns.reveals.get(m) == reruns.outcome) + 1
        verdicts = sum(self.c.verdict_fee(m) for j in juries for m in self.c.verdicts_due(j))
        return runs * P.run_fee + verdicts

    def second(self, b, e, jury, accepts):
        second = self.c.draw_jury(f"entry:{e.id}", "s2", self.m.parties(b) | set(jury.members), tier=2)
        self.assertEqual(len(second.members), P.second_jury_size)
        self.assertFalse(set(second.members) & set(jury.members))
        self.verdicts(second, [(True, 0.8, "x")] * accepts + [(False, 0.2, "x")] * (P.second_jury_size - accepts))
        self.c.close_jury(second, 3)
        return second


class TestReruns(Checks):
    def test_all_agree(self):
        job = self.reruns([True, True, True])
        before = {m: self.ledger.balance(m) for m in job.members}
        self.assertIs(self.c.close_reruns(job, 3), True)
        for m in job.members:  # every bond back
            self.assertEqual(self.ledger.balance(m), before[m] + P.review_bond)
        self.assertEqual(self.c.take_work(), {})  # a real delivery's re-runs are paid by its bounty, not the share

    def test_one_disagrees(self):
        job = self.reruns([False, False, True])
        dissenter = job.members[2]
        before = self.ledger.balance(dissenter)
        self.assertIs(self.c.close_reruns(job, 3), False)
        self.assertEqual(self.ledger.balance(dissenter),
                         before + P.review_bond - share(P.review_bond, P.rerun_dissent_penalty_bps))
        self.assertNotIn(dissenter, self.c.take_work())

    def test_no_quorum(self):
        job = self.reruns([True, False, None])
        silent = job.members[2]
        before = self.ledger.balance(silent)
        self.assertIsNone(self.c.close_reruns(job, 3))
        self.assertLess(self.ledger.balance(silent), before + P.review_bond)  # no reveal costs the dissent share
        fresh = self.c.start_reruns("entry:1", "seed-2", set(job.members), 3)
        self.assertFalse(set(fresh.members) & set(job.members))

    def test_results_cant_be_copied(self):
        job = self.c.start_reruns("entry:1", "seed", set(), 3)
        self.c.commit(job, job.members[0], seal(True, "a"))
        with self.assertRaises(CheckingError):  # nothing is revealed until everyone has committed
            self.c.reveal_rerun(job, job.members[0], True, "a")
        for m in job.members[1:]:
            self.c.commit(job, m, seal(True, m))
        self.assertTrue(self.c.reveal_rerun(job, job.members[0], True, "a"))


class TestPlanted(Checks):
    def test_a_lazy_validator(self):
        job = self.reruns([False, False, True], ref="planted:1", planted=False)
        lazy = job.members[2]
        before = self.ledger.balance(lazy)
        self.assertIs(self.c.close_reruns(job, 3), False)
        self.assertEqual(self.ledger.balance(lazy), before + P.review_bond - share(P.review_bond, P.planted_penalty_bps))

    def test_revealed_after_settling(self):
        job = self.reruns([False, False, False], ref="planted:1", planted=False)
        self.c.close_reruns(job, 3)
        self.assertTrue(any(e.kind == "reruns" and "planted=False" in e.detail for e in self.ledger.events))

    def test_confidently_wrong_planted_verdict(self):
        job = self.c.draw_jury("planted:2", "s", set(), planted=False)
        self.verdicts(job, [(True, 0.995, "x"), (False, 0.2, "x"), (False, 0.2, "x")])
        herder = job.members[0]
        bond = self.c.evaluators[herder].bond_account
        self.c.close_jury(job, 3)
        self.assertEqual(self.ledger.balance(bond), P.evaluator_bond - share(P.evaluator_bond, P.planted_penalty_bps))


class TestJury(Checks):
    def test_one_seat_per_family(self):
        twin = self.ledger.open("actor")
        self.ledger.issue(twin, credits(50), "endowment", "setup", 0)
        self.c.register_evaluator(twin, "op-9", "A", 0)  # a second family-A model
        self.c.evaluators[twin].briers = [0.0] * P.shadow_verdicts
        for i in range(30):
            job = self.c.draw_jury(f"entry:{i}", f"seed{i}", set())
            fams = [self.c.evaluators[m].family for m in job.members]
            self.assertEqual(len(fams), len(set(fams)))
            ops = [self.c.evaluators[m].operator for m in job.members]
            self.assertEqual(len(ops), len(set(ops)))
            self.assertEqual(len(job.members), P.jury_size)

    def test_top_of_the_leaderboard_first(self):  # #47: the best-measured models seat first, top to bottom
        self.c.model_accuracy = {"A": 0.95, "B": 0.93, "C": 0.91, "D": 0.89, "E": 0.86}
        for i in range(10):
            job = self.c.draw_jury(f"entry:{i}", f"s{i}", set())
            self.assertEqual(sorted(self.c.evaluators[m].model for m in job.members), ["A", "B", "C"])

    def test_a_fair_tie_break_between_copies(self):
        self.c.model_accuracy = {"A": 0.95, "B": 0.93, "C": 0.91, "D": 0.89, "E": 0.86}
        seats = {tuple(self.c.draw_jury("entry:1", f"seed{i}", set()).members) for i in range(20)}
        self.assertGreater(len(seats), 1)  # the same models, different operators' copies

    def test_selection_reproducible(self):
        a = self.c.draw_jury("entry:1", "same", set())
        b = self.c.draw_jury("entry:1", "same", set())
        self.assertEqual(a.members, b.members)

    def test_shadow_mode(self):
        new = self.ledger.open("actor")
        self.ledger.issue(new, credits(50), "endowment", "setup", 0)
        self.c.register_evaluator(new, "op-new", "F", 0)
        job = self.c.draw_jury("entry:1", "s", set())
        self.assertEqual(job.shadow, [new])
        self.assertNotIn(new, job.members)
        self.verdicts(job, [(True, 0.8, "x")] * 3)
        self.c.commit(job, new, seal(False, 0.1, "x", "n"))
        self.c.reveal_verdict(job, new, False, 0.1, "x", "n")
        self.assertEqual(self.c.close_jury(job, 3), "accept")  # the shadow's rejection doesn't count
        self.c.resolve("entry:1", True, 4)
        self.assertEqual(len(self.c.evaluators[new].briers), 1)  # but it is scored
        self.assertFalse(self.c.qualified(new))

    def test_parties_excluded(self):
        job = self.c.draw_jury("entry:1", "s", {self.evaluators[0]})
        self.assertNotIn(self.evaluators[0], job.members)

    def test_scored_on_the_outcome(self):
        job = self.c.draw_jury("entry:7", "s", set())
        self.verdicts(job, [(True, 0.9, "x"), (True, 0.9, "x"), (True, 0.9, "x")])
        self.c.close_jury(job, 3)
        m = job.members[0]
        n = len(self.c.evaluators[m].briers)
        self.c.resolve("entry:7", False, 30)  # slashed later
        self.assertAlmostEqual(self.c.evaluators[m].briers[-1], 0.81)
        self.assertEqual(len(self.c.evaluators[m].briers), n + 1)
        self.assertEqual(self.c.take_work(), {})  # a verdict that didn't hold up earns nothing

    def test_agreement_scoring_comparison(self):
        c = Checking(self.ledger, P, self.vset, self.insurance, score_on_agreement=True)
        a = self.ledger.open("actor")
        self.ledger.issue(a, credits(50), "endowment", "setup", 0)
        c.register_evaluator(a, "op", "A", 0)
        job = c.shadow_case([a], "exam:1", False)
        c.commit(job, a, seal(True, 0.9, "x", "s"))
        c.reveal_verdict(job, a, True, 0.9, "x", "s")
        c.close_jury(job, 0)
        self.assertAlmostEqual(c.evaluators[a].briers[-1], 0.01)  # it agreed with the majority (itself)
        self.assertEqual(self.ledger.balance(c.evaluators[a].bond_account), P.evaluator_bond)  # no truth, no penalty


class TestDelivery(Checks):
    def test_accepted(self):  # AI consensus: all three accept
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3)
        self.assertEqual(self.c.close_jury(jury, 3), "accept")
        c = self.m.deliver_checked(e, 78, 3, reruns, jury)
        self.assertEqual((c.contributor, b.state), (self.solvers[0], "won"))

    def test_rejected_by_the_jury(self):
        b, e, reruns, jury = self.delivery([(False, 0.2, "x")] * 3)
        self.assertEqual(self.c.close_jury(jury, 3), "reject")
        bounty = self.ledger.balance(b.account)
        self.assertIsNone(self.m.deliver_checked(e, 78, 3, reruns, jury))
        self.assertEqual(e.state, "failed")
        self.assertEqual(self.ledger.balance(b.account), bounty + e.stake - self.fees(reruns, jury))  # the bond in
        self.assertEqual((b.state, b.published), ("open", [e.id]))  # published, and a fresh round
        self.assertTrue(all(len(self.c.evaluators[m].briers) == P.shadow_verdicts for m in jury.members))  # unscored

    def test_split_goes_to_the_second_jury(self):  # no person decides a delivery
        b, e, reruns, jury = self.delivery([(True, 0.8, "x"), (False, 0.2, "x"), (True, 0.8, "")])
        self.assertEqual(self.c.close_jury(jury, 3), "escalate")  # one verdict discarded: no evidence
        second = self.second(b, e, jury, P.second_jury_accept)
        self.assertEqual(second.outcome, "accept")
        self.assertIsNotNone(self.m.deliver_checked(e, 78, 3, reruns, jury, second))

    def test_one_seat_per_operator_on_the_second_jury(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x"), (False, 0.2, "x"), (True, 0.8, "x")])
        self.c.close_jury(jury, 3)
        second = self.c.draw_jury(f"entry:{e.id}", "s2", set(jury.members), tier=2)
        ops = [self.c.evaluators[m].operator for m in second.members]
        fams = [self.c.evaluators[m].family for m in second.members]
        self.assertEqual(len(ops), len(set(ops)))
        self.assertTrue(all(fams.count(f) <= P.second_jury_per_family for f in fams))

    def test_split_rejected_returns_the_bond(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x"), (False, 0.2, "x"), (True, 0.8, "x")])
        self.c.close_jury(jury, 3)
        second = self.second(b, e, jury, P.second_jury_accept - 1)
        self.assertEqual(second.outcome, "reject")
        before, bounty = self.ledger.balance(e.solver), self.ledger.balance(b.account)
        self.assertIsNone(self.m.deliver_checked(e, 78, 3, reruns, jury, second))
        self.assertEqual(self.ledger.balance(e.solver), before + e.stake)  # the bond back; the fee pays the checks
        self.assertEqual(self.ledger.balance(b.account), bounty - self.fees(reruns, jury, second))
        self.assertEqual((e.state, b.state, b.published), ("failed", "open", [e.id]))

    def test_split_rejected_bond_lost_when_off(self):
        self.m.params = P.with_(split_rejection_keeps_bond=False)
        b, e, reruns, jury = self.delivery([(True, 0.8, "x"), (False, 0.2, "x"), (True, 0.8, "x")])
        self.c.close_jury(jury, 3)
        second = self.second(b, e, jury, 0)
        bounty = self.ledger.balance(b.account)
        self.m.deliver_checked(e, 78, 3, reruns, jury, second)
        self.assertEqual(self.ledger.balance(b.account), bounty + e.stake - self.fees(reruns, jury, second))

    def test_failed_reruns(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3, rerun_results=(False, False, True))
        self.c.close_jury(jury, 3)
        self.assertIsNone(self.m.deliver_checked(e, 78, 3, reruns, jury))

    def test_bidders_cant_check(self):
        b = self.pledged()
        entries, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        self.vset.register(self.solvers[1], credits(50), 2)  # the runner-up is also a validator
        job = self.c.start_reruns(f"entry:{e.id}", "s", self.m.parties(b), 3)
        self.assertNotIn(self.solvers[1], job.members)

    def test_hidden_tests_fail(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3)
        self.c.close_jury(jury, 3)
        self.assertIsNone(self.m.deliver_checked(e, 78, 3, reruns, jury, hidden_passes=False))
        self.assertEqual(b.hidden_set, 2)  # burned

    def test_appeal_overturns(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3, rerun_results=(False, False, True))
        self.assertIs(reruns.outcome, False)
        liars = [m for m in reruns.members if reruns.reveals[m] is False]
        stakes = {m: self.ledger.balance(self.vset.stake_account[m]) for m in liars}
        before = self.ledger.balance(e.solver)
        fresh = self.c.appeal_reruns(reruns, e.solver, "appeal", self.m.parties(b), 3)
        self.assertFalse(set(fresh.members) & set(reruns.members))
        for m in fresh.members:
            self.c.commit(fresh, m, seal(True, m))
        for m in fresh.members:
            self.c.reveal_rerun(fresh, m, True, m)
        self.c.close_reruns(fresh, 3)
        self.assertIs(self.c.settle_appeal(reruns, e.solver, 3), True)
        self.assertEqual(self.ledger.balance(e.solver), before)  # the fee came back
        for m in liars:
            self.assertEqual(self.ledger.balance(self.vset.stake_account[m]),
                             stakes[m] - share(P.review_bond, P.rerun_dissent_penalty_bps))
        self.c.close_jury(jury, 3)
        self.assertIsNotNone(self.m.deliver_checked(e, 78, 3, fresh, jury))

    def test_appeal_upheld(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3, rerun_results=(False, False, False))
        before = self.ledger.balance(e.solver)
        fresh = self.c.appeal_reruns(reruns, e.solver, "appeal", self.m.parties(b), 3)
        for m in fresh.members:
            self.c.commit(fresh, m, seal(False, m))
        for m in fresh.members:
            self.c.reveal_rerun(fresh, m, False, m)
        self.c.close_reruns(fresh, 3)
        self.assertIs(self.c.settle_appeal(reruns, e.solver, 3), False)
        self.assertEqual(self.ledger.balance(e.solver), before - P.rerun_appeal_fee)

    def test_evidence_sealed_until_paid(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "runs 1-9 pass")] * 3)
        self.c.close_jury(jury, 3)
        self.m.deliver_checked(e, 78, 3, reruns, jury)
        self.assertFalse(any(ev.kind == "jury_evidence" for ev in self.ledger.events))
        self.m._publish_evidence(b, 60)
        self.assertTrue(any(ev.kind == "jury_evidence" and "runs 1-9 pass" in ev.detail for ev in self.ledger.events))

    def test_checks_must_be_this_bids(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3)
        from pof.market import MarketError
        with self.assertRaises(MarketError):  # the jury is still open
            self.m.deliver_checked(e, 78, 3, reruns, jury)

    def test_oracle_fees(self):  # the bounty pays for every check run on its delivery (owner, 2026-10-25)
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3)
        self.c.close_jury(jury, 3)
        before = {m: self.ledger.balance(m) for m in reruns.members + jury.members + [self.infra]}
        bounty = self.ledger.balance(b.account)
        self.m.deliver_checked(e, 78, 3, reruns, jury)
        for m in reruns.members:
            self.assertEqual(self.ledger.balance(m), before[m] + P.run_fee)
        for m in jury.members:
            self.assertEqual(self.ledger.balance(m), before[m] + self.c.verdict_fee(m))
        hidden = [x for x in self.ledger.entries if x.source == b.account and x.target == self.infra and x.reason == "payout"]
        self.assertEqual([x.amount for x in hidden], [P.run_fee])  # the hidden tests' runner, paid by the bounty
        self.assertEqual(bounty - self.ledger.balance(b.account) - self.life.contributions[b.contribution].reward,
                         self.fees(reruns, jury))  # what left the bounty: the escrowed price and the oracle fees

    def test_oracle_reserve(self):
        with self.assertRaises(Exception):
            self.m.open_bounty(self.m.params.oracle_reserve, 1)  # more than one full attempt's checks
        b = self.pledged()
        self.assertEqual(self.m.price_cap(b), (credits(300) - self.m.params.oracle_reserve) * BPS // (BPS + P.market_fee_bps))


class TestAttested(Checks):  # CI by attested runners, MCP test runners in TEEs: the default (owner, 2026-10-25)
    def setUp(self):
        super().setUp()
        self.m.params = self.c.params = DEFAULT_P
        self.runners = []
        for i in range(6):
            a = self.ledger.open("actor")
            self.ledger.issue(a, credits(50), "endowment", "setup", 0)
            self.c.register_runner(a, f"run-op-{i}", ("tdx", "sev", "cca")[i % 3], 0)
            self.runners.append(a)

    def run_ci(self, results, ref="entry:1", planted=None, exclude=frozenset()):
        job = self.c.start_reruns(ref, "seed", set(exclude), 3, planted)
        for m, r in zip(job.members, results):
            self.c.commit(job, m, seal(r, f"s{m}"))
        for m, r in zip(job.members, results):
            self.c.reveal_rerun(job, m, r, f"s{m}")
        return job

    def test_runners_from_different_operators_and_vendors(self):
        job = self.run_ci([True, True])
        self.assertEqual(len(job.members), DEFAULT_P.ci_runners)
        self.assertTrue(set(job.members) <= set(self.runners))
        vendors = {self.c.runners[m].vendor for m in job.members}
        ops = {self.c.runners[m].operator for m in job.members}
        self.assertEqual((len(vendors), len(ops)), (2, 2))

    def test_all_must_agree(self):
        job = self.run_ci([True, False])
        self.assertIsNone(self.c.close_reruns(job, 3))  # a split: fresh runners settle it
        fresh = self.c.start_reruns("entry:1", "seed-2", set(job.members), 3)
        for m in fresh.members:
            self.c.commit(fresh, m, seal(True, m))
        for m in fresh.members:
            self.c.reveal_rerun(fresh, m, True, m)
        self.assertIs(self.c.close_reruns(fresh, 3), True)
        wrong = job.members[1]
        self.c.settle_split(job, fresh, 3)
        self.assertEqual(self.ledger.balance(self.c.runners[wrong].bond_account),
                         DEFAULT_P.runner_bond - share(DEFAULT_P.review_bond, DEFAULT_P.rerun_dissent_penalty_bps))

    def test_a_lie_on_a_planted_case(self):
        job = self.run_ci([True, False], ref="planted:1", planted=False)
        liar = job.members[0]
        self.c.close_reruns(job, 3)
        self.assertEqual(self.ledger.balance(self.c.runners[liar].bond_account),
                         DEFAULT_P.runner_bond - share(DEFAULT_P.runner_bond, DEFAULT_P.planted_penalty_bps))

    def test_oracle_fees_without_a_system_runner(self):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        ci = self.run_ci([True, True], ref=f"entry:{e.id}", exclude=self.m.parties(b))
        jury = self.c.draw_jury(f"entry:{e.id}", "s", self.m.parties(b))
        self.verdicts(jury, [(True, 0.8, "x")] * 3)
        self.c.close_reruns(ci, 3)
        self.c.close_jury(jury, 3)
        before = {m: self.ledger.balance(m) for m in ci.members}
        self.m.deliver_checked(e, 78, 3, ci, jury)
        for m in ci.members:
            self.assertEqual(self.ledger.balance(m), before[m] + DEFAULT_P.run_fee)
        self.assertFalse([x for x in self.ledger.entries if x.source == b.account and x.target == self.infra
                          and x.reason == "payout"])  # the hidden tests ran inside the runners' enclaves
        self.assertEqual(DEFAULT_P.oracle_reserve, DEFAULT_P.run_fee * 2 + DEFAULT_P.top_verdict_fee * 10)


class TestSolverPays(Checks):  # #49 (owner): the contributor pays its checks from a deposit
    def setUp(self):
        super().setUp()
        self.m.params = self.c.params = P.with_(checks_paid_by="solver")

    @property
    def deposit(self):
        return self.m.params.oracle_reserve

    def test_bid_posts_the_deposit(self):
        b = self.pledged()
        before = self.ledger.balance(self.solvers[0])
        e = self.m.commit(b, self.solvers[0], seal(credits(100), "s0"), 2)
        self.assertEqual(self.m.deposit(), self.deposit)
        self.assertEqual(self.ledger.balance(self.solvers[0]), before - e.stake - self.deposit)

    def test_losers_get_it_back(self):
        b = self.pledged()
        before = self.ledger.balance(self.solvers[1])
        self.round_with(b, [(0, credits(100)), (1, credits(150))])
        self.assertEqual(self.ledger.balance(self.solvers[1]), before)

    def test_void_bid_forfeits_the_evaluation_fee_only(self):
        b = self.pledged()
        before = self.ledger.balance(self.solvers[1])
        self.round_with(b, [(0, credits(100)), (1, credits(240))])  # above the reserve: void
        self.assertEqual(self.ledger.balance(self.solvers[1]), before - self.m.params.evaluation_fee)

    def test_accepted_pays_its_checks_from_the_deposit(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x")] * 3)
        self.c.close_jury(jury, 3)
        bounty, solver = self.ledger.balance(b.account), self.ledger.balance(e.solver)
        c = self.m.deliver_checked(e, 78, 3, reruns, jury)
        fees = self.fees(reruns, jury)
        self.assertEqual(bounty - self.ledger.balance(b.account), c.reward)  # the bounty paid the price only
        self.assertEqual(self.ledger.balance(e.solver), solver + self.deposit - fees)  # the deposit's rest back

    def test_split_rejection_costs_the_splitter(self):
        b, e, reruns, jury = self.delivery([(True, 0.8, "x"), (False, 0.2, "x"), (True, 0.8, "x")])
        self.c.close_jury(jury, 3)
        second = self.second(b, e, jury, self.m.params.second_jury_accept - 1)
        bounty, solver = self.ledger.balance(b.account), self.ledger.balance(e.solver)
        self.assertIsNone(self.m.deliver_checked(e, 78, 3, reruns, jury, second))
        fees = self.fees(reruns, jury, second)
        self.assertLessEqual(fees, self.deposit)
        self.assertEqual(self.ledger.balance(b.account), bounty)  # the bounty paid nothing
        self.assertEqual(self.ledger.balance(e.solver), solver + e.stake + self.deposit - fees)  # bond back, checks paid

    def test_clear_failure_forfeits_the_bond_and_pays_the_checks(self):
        b, e, reruns, jury = self.delivery([(False, 0.2, "x")] * 3)
        self.c.close_jury(jury, 3)
        bounty, solver = self.ledger.balance(b.account), self.ledger.balance(e.solver)
        self.m.deliver_checked(e, 78, 3, reruns, jury)
        self.assertEqual(self.ledger.balance(b.account), bounty + e.stake)  # the bond, and no fees out
        self.assertEqual(self.ledger.balance(e.solver), solver + self.deposit - self.fees(reruns, jury))

    def test_late_forfeits_the_evaluation_fee(self):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        solver = self.ledger.balance(e.solver)
        self.m.expire_deliveries(e.deliver_by + 1)
        self.assertEqual(self.ledger.balance(e.solver), solver + self.deposit - self.m.params.evaluation_fee)

    def test_no_room_kept_in_the_price(self):
        b = self.pledged()
        self.assertEqual(self.m.price_cap(b), credits(300) * BPS // (BPS + P.market_fee_bps))
        self.m.open_bounty(self.m.params.oracle_reserve, 1)  # small bounties are allowed: the solvers decide


class TestNotSolved(MarketWorld):
    def won(self):
        b = self.pledged()
        _, e = self.round_with(b, [(0, credits(100)), (1, credits(150))])
        c = self.m.deliver(e, 78, e.deliver_by - 1, passes=True)
        self.rel.ship_beta(self.rel.open_release(c.submitted_day), [c], c.submitted_day)
        return b, c

    def test_upheld_case_joins_the_definition(self):
        b, c = self.won()
        proof = Proof("SUMIF over an empty range still returns 0", c.id, kind="not_solved")
        ch = self.ch.file(c, self.challenger, proof, "wrong_result", c.beta_day + 1, "x")
        self.ch.finalize(ch, c.beta_day + 1)
        self.assertEqual(c.state, "slashed")
        self.m.settle(c.beta_day + 2)
        self.assertEqual(b.cases, ["SUMIF over an empty range still returns 0"])
        self.assertEqual(b.state, "open")  # reopened, with the case in its public definition
        self.assertTrue(any(ev.kind == "case_added" for ev in self.ledger.events))

    def test_needs_a_bounty(self):
        c = self.life.submit(self.solvers[2], 40, 1)
        with self.assertRaises(ChallengeError):
            self.ch.file(c, self.challenger, Proof("still fails", c.id, kind="not_solved"), "wrong_result", 2, "x")

    def test_off_by_parameter(self):
        b, c = self.won()
        self.ch.params = P.with_(not_solved_challenges=False)
        with self.assertRaises(ChallengeError):
            self.ch.file(c, self.challenger, Proof("still fails", c.id, kind="not_solved"), "wrong_result",
                         c.beta_day + 1, "x")


if __name__ == "__main__":
    unittest.main()
