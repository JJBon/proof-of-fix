"""#236, the revision of 2026-11-15 (design D24-D28): the appeal on evidence decided by the seated families, a
contender's sponsorship, known-answer issues, the second panel and the deposit held during the appeal period
(pof/sim/openval/net.py, seats.py), and the sweeps of reports/open-validators-measured-v4.md (evidence.py). One test
class per switch."""

import unittest
from dataclasses import replace

from pof.sim.openval import actors as A
from pof.sim.openval import evidence as E
from pof.sim.openval import measured as M
from pof.sim.openval import sizing as Z
from pof.sim.openval.net import WEEK, Net
from pof.sim.openval.params import D236, D236R2, PARAMS

NO_DISPUTES = dict(find=0.0, false=0.0)


def short(pool="hidden", weeks=8, a=1.0, b=0.0, **kw):
    return replace(E.world(pool, a, b, **kw), weeks=weeks)


def run(w, p, seed=5, actor=None):
    return Net(seed, p, w, [actor or Z.OnMarket(w=w)]).run()


def issue(net, honest=True):
    return [s for s in net.subs.values() if s.tier == "issue" and (s.party is None) == honest]


class TestDefaults(unittest.TestCase):
    def test_every_new_rule_is_off_by_default_and_in_10_1s_proposal(self):
        for p in (PARAMS, D236, Z.BASE):
            self.assertEqual((p.APPEAL_STAKE, p.APPEAL_STAKE_BPS, p.SPONSOR, p.SPONSOR_REWARD_BPS, p.KNOWN_RATE,
                              p.SECOND_PANEL), (0.0, 0, False, 0, 0.0, "larger"))
            self.assertNotEqual(p.APPEAL, "evidence")
        st = run(short(weeks=4), Z.BASE).stats
        self.assertEqual((st["known_issues"], st["second_panels"], st["astake_lost"], st["appeals_sponsored"]),
                         (0, 0, 0, 0))

    def test_the_revision_is_the_proposal(self):
        p = D236R2
        self.assertEqual((p.APPEAL, p.APPEAL_STAKE, p.APPEAL_STAKE_BPS, p.APPEAL_STAKE_TO, p.SPONSOR,
                          p.SPONSOR_REWARD_BPS, p.KNOWN_RATE, p.SECOND_PANEL, p.SOLVER_DEPOSIT_BPS),
                         ("evidence", 5.0, 1_000, "pool", True, 1_000, 0.05, "few", D236.SOLVER_DEPOSIT_BPS))  # the deposit: on hold
        self.assertEqual((p.SEAT_RULE, p.SEAT_MARGIN, p.CAP_MIN_FAMILIES, p.SOLVER_DEPOSIT_TO),
                         ("rank", 0.05, 3, "bounty"))  # D20 and D22's destination are unchanged
        self.assertEqual((p.appeal_stake(40.0), p.appeal_stake(400.0)), (5.0, 40.0))


class TestEvidenceAppeal(unittest.TestCase):
    def test_the_seated_families_decide_and_one_family_is_enough(self):
        net = run(short(appeal_bad=1.0, **NO_DISPUTES), E.EV)
        app = [s for s in issue(net) if s.appeal_judges]
        self.assertGreater(len(app), 20)
        fams = {net.reg.validators[vid].family for s in app for vid in s.appeal_judges}
        self.assertEqual(fams, {"anthropic"})  # the one seated family: no contender sits on the appeal
        self.assertLess(net.stats["appeals_no_panel"], 0.1 * net.stats["appeals"])
        # D23's alternative, the seated families' next draw outside the first panel, found no panel (report v3)
        old = run(short(appeal_bad=1.0, **NO_DISPUTES), replace(Z.BASE, APPEAL="seated"))
        self.assertGreater(old.stats["appeals_no_panel"], 0.8 * old.stats["appeals"])
        self.assertEqual(old.stats["appeals_upheld"], 0)

    def test_the_assumed_rates_decide_the_outcome(self):
        net = run(short(a=1.0, b=0.0, appeal_bad=1.0, **NO_DISPUTES), E.EV)
        judged = [s for s in issue(net) if s.appeal in ("upheld", "failed") and s.final is not None]
        good, bad = [s for s in judged if s.good], [s for s in judged if not s.good]
        self.assertTrue(good and bad)
        self.assertTrue(all(s.appeal == "upheld" and s.final for s in good))
        self.assertTrue(all(s.appeal == "failed" and s.final is False for s in bad))
        net = run(short(a=0.0, b=1.0, appeal_bad=1.0, **NO_DISPUTES), E.EV)
        judged = [s for s in issue(net) if s.appeal in ("upheld", "failed") and s.final is not None]
        self.assertTrue(all((s.appeal == "upheld") is (not s.good) for s in judged))
        self.assertGreater(net.stats["appeals_upheld_bad"], 10)

    def test_the_stake_is_lost_when_the_appeal_fails_and_returned_when_it_passes(self):
        net = run(short(a=0.5, b=0.0, appeal_bad=1.0, **NO_DISPUTES), E.EV)
        done = [s for s in issue(net) if s.appeal in ("upheld", "failed") and s.final is not None]
        up, down = [s for s in done if s.appeal == "upheld"], [s for s in done if s.appeal == "failed"]
        self.assertTrue(up and down)
        for s in down:
            self.assertAlmostEqual(s.astake_lost, max(5.0, 0.10 * s.bounty))
            self.assertEqual((s.final, s.sdeposit_to), (False, "bounty"))  # D28: then the deposit goes to the bounty
        for s in up:
            self.assertEqual((s.astake_lost, s.final, s.sdeposit_to), (0.0, True, "returned"))
        self.assertAlmostEqual(net.stats["astake_lost"], sum(s.astake_lost for s in issue(net)))

    def test_an_appeal_that_finds_no_panel_loses_no_stake(self):
        net = run(short(appeal_bad=1.0, **NO_DISPUTES), E.EV)
        none = [s for s in issue(net) if s.appeal == "no panel"]
        self.assertTrue(all(s.astake_lost == 0.0 for s in none))

    def test_one_appeal_a_fix_and_an_upheld_one_is_open_to_test_disputes(self):
        w = short(a=1.0, b=1.0, appeal_bad=1.0, find=1.0, false=0.0)
        net = run(w, E.EV)
        s = next(s for s in issue(net) if s.appeal == "failed" or s.appeal == "upheld")
        before = net.stats["appeals"]
        net._appeal(s)
        self.assertEqual(net.stats["appeals"], before)
        back = [s for s in issue(net) if s.appeal == "upheld" and s.by_evidence]
        self.assertTrue(back and all(not s.good and s.final is False and s.sdeposit_to == "disputer" for s in back))

    def test_a_solver_of_bad_fixes_pays_for_appeals_the_panel_refuses(self):
        w = short(b=0.0, **NO_DISPUTES)
        mk = lambda h: Z.Solver(h, w, appeal=True, twin="no_appeal")  # noqa: E731
        r = A.against_twin(mk, [3], p=E.EV, metrics=Z._party_metrics)
        self.assertGreater(r["appeals"], 10)
        self.assertEqual((r["upheld"], r["bad_paid"]), (0, r["twin_bad_paid"]))
        self.assertLess(r["diff"], -5.0 * 0.8 * r["appeals"])  # at least the flat stake on nearly every appeal

    def test_and_gains_when_the_panel_passes_a_test_that_proves_nothing(self):
        w = short(b=1.0, **NO_DISPUTES)
        mk = lambda h: Z.Solver(h, w, appeal=True, twin="no_appeal")  # noqa: E731
        r = A.against_twin(mk, [3], p=E.EV, metrics=Z._party_metrics)
        self.assertGreater(r["bad_paid"], r["twin_bad_paid"])
        self.assertGreater(r["diff"], 0)

    def test_the_break_even_rate_is_the_stake_over_the_stake_and_the_prize(self):
        self.assertAlmostEqual(E.break_even(0.10, 0.25), 0.10 / 1.35)
        self.assertAlmostEqual(E.break_even(0.10, 0.25, 0.5), 0.10 / 0.725)
        self.assertLess(E.break_even(0.10, 0.40), E.break_even(0.10, 0.25))  # a larger deposit is a larger prize


class TestSponsor(unittest.TestCase):
    P = replace(E.EV, SPONSOR=True, SPONSOR_REWARD_BPS=1_000)

    def test_nobody_sponsors_unless_the_switch_is_on(self):
        w = short(appeal_good=0.0, sponsor_by=E.SEVEN, **NO_DISPUTES)
        self.assertEqual(run(w, E.EV).stats["appeals"], 0)
        self.assertGreater(run(w, self.P).stats["appeals_sponsored"], 10)

    def test_a_contender_sponsors_only_fixes_its_model_passed_and_only_while_unseated(self):
        w = short(appeal_good=0.0, sponsor_by=("openai", "anthropic"), **NO_DISPUTES)
        net = run(w, self.P)
        mine = [s for s in issue(net) if s.sponsor]
        self.assertTrue(mine)
        self.assertEqual({s.sponsor for s in mine}, {"contender:openai"})  # Opus 5.5 is seated: it can't sponsor
        self.assertTrue(all(M.case_of(net, s)["openai"] and s.verdict is False for s in mine))
        self.assertTrue(all(s.astake_lost == 0.0 for s in mine))  # the stake is the sponsor's, not the solver's

    def test_the_solvers_own_appeal_comes_first(self):
        w = short(appeal_good=1.0, sponsor_by=E.SEVEN, **NO_DISPUTES)
        net = run(w, self.P)
        self.assertTrue(all(not s.sponsor for s in issue(net) if s.good and s.appeal))

    def test_a_sponsor_is_paid_its_share_of_the_bounty_and_pays_the_stake_and_the_checks(self):
        w = short(a=1.0, b=0.0, appeal_good=0.0, **NO_DISPUTES)
        a = E.Sponsor(False, w, "every", search_cost=0.0)
        net = run(w, self.P, actor=a)
        pa = net.parties[a.party]
        mine = [s for s in issue(net) if s.sponsor == a.party and s.appeal in ("upheld", "failed")]
        paid = [s for s in mine if s.final]
        lost = [s for s in mine if s.appeal == "failed"]
        self.assertTrue(paid and lost and all(s.good for s in paid))
        self.assertAlmostEqual(pa.gains, sum(0.10 * s.bounty for s in paid))
        self.assertAlmostEqual(pa.costs, sum(max(5.0, 0.10 * s.bounty) for s in lost)
                               + sum(s.sponsor_charges for s in mine), places=6)
        self.assertTrue(all(abs(s.sponsor_fee - 0.10 * s.bounty) < 1e-9 for s in paid))

    def test_the_twin_sponsors_nothing(self):
        w = short(appeal_good=0.0, **NO_DISPUTES)
        r = A.against_twin(lambda h: E.Sponsor(h, w, "every"), [3], p=self.P, metrics=E._party_metrics)
        self.assertEqual((r["twin"], r["twin_sponsored"]), (0.0, 0))
        self.assertGreater(r["sponsored"], 10)

    def test_an_upheld_sponsored_appeal_scores_the_rejecting_judges_as_wrong(self):
        w = short(a=1.0, b=0.0, appeal_good=0.0, sponsor_by=E.SEVEN, **NO_DISPUTES)
        net = run(w, self.P)
        up = [s for s in issue(net) if s.sponsor and s.appeal == "upheld" and s.final]
        self.assertTrue(up)
        wrong = [e for e in net.family_outcomes["anthropic"] if not e[1] and e[2]]
        self.assertGreaterEqual(len(wrong), len(up))


class TestKnownAnswers(unittest.TestCase):
    def gpt_first(self, weeks, **kw):
        w = replace(E.genesis(E.world("hidden", scores="live"), "openai"), weeks=weeks)
        return run(w, replace(Z.BASE, **kw))

    def test_every_family_is_scored_seated_or_not_and_no_solver_pays(self):
        net = self.gpt_first(6, KNOWN_RATE=0.5)
        n = net.stats["known_issues"]
        self.assertGreater(n, 50)
        self.assertEqual({f: len(v) for f, v in net.known_outcomes.items()}, {f: n for f in E.SEVEN})
        self.assertEqual(net.stats["known_checks"], 7 * n)
        self.assertGreater(net.stats["known_pay"], 0)
        self.assertEqual(sum(1 for s in net.subs.values() if s.solver == "known-answer"), 0)  # no submission, no bounty

    def test_the_better_family_takes_the_seat_from_a_strict_genesis_family(self):
        net = self.gpt_first(10, KNOWN_RATE=0.5)
        self.assertEqual(set(net.seats.seated()), {"anthropic"})
        self.assertTrue(net.seats.fam["anthropic"].by_known and net.seats.fam["openai"].by_known)
        self.assertGreater(net.seats.score("anthropic"), net.seats.score("openai") + 0.05)
        self.assertEqual(set(self.gpt_first(10).seats.seated()), {"openai"})  # live scores alone keep the incumbent

    def test_below_the_minimum_number_of_known_verdicts_nothing_changes(self):
        net = self.gpt_first(6, KNOWN_RATE=0.05)
        self.assertLess(net.stats["known_issues"], PARAMS.KNOWN_MIN)
        self.assertEqual(set(net.seats.seated()), {"openai"})
        self.assertFalse(any(st.by_known for st in net.seats.fam.values()))


class TestSecondPanel(unittest.TestCase):
    def nets(self, pool, **kw):
        w = replace(E.world(pool, second_opinions=True), weeks=16)
        return run(w, replace(Z.BASE, **kw))

    def waiting(self, net):
        return [s for s in issue(net) if s.state == "challenged" and s.verdict_t < net.t - 4 * WEEK]

    def test_with_one_family_d4s_larger_panel_never_comes_and_the_second_draw_decides(self):
        d4 = self.nets("hidden")
        self.assertTrue(self.waiting(d4))
        self.assertEqual(d4.stats["second_panels"], 0)
        few = self.nets("hidden", SECOND_PANEL="few")
        self.assertFalse(self.waiting(few))
        self.assertGreater(few.stats["second_panels"], 0)
        self.assertEqual(few.stats["reversed"], d4.stats["reversed"])  # the same family repeats its verdict

    def test_with_three_families_seated_the_rule_does_not_apply(self):
        self.assertEqual(self.nets("pbw", SECOND_PANEL="few").stats["second_panels"], 0)
        self.assertGreater(self.nets("pbw", SECOND_PANEL="always").stats["second_panels"], 0)


class TestDepositHeld(unittest.TestCase):
    def test_a_rejected_fixs_deposit_moves_only_when_its_appeal_period_has_closed(self):
        w = short(weeks=10, appeal_good=0.0, **NO_DISPUTES)
        a = E.Retrier(False, w, retry=3)
        net = run(w, E.EV, actor=a)
        mine = sorted(issue(net, honest=False), key=lambda s: s.sid)
        rej = [s for s in mine if s.final is False]
        self.assertTrue(rej)
        self.assertTrue(all(s.final_t - s.verdict_t >= E.EV.APPEAL_WINDOW_H - 1e-6 and s.sdeposit_to == "bounty"
                            for s in rej))
        again = [s for s in mine if s.pot > 0]
        self.assertTrue(again)
        for s in again:  # a patient solver's next fix arrives after the deposit moved, and stakes a share of it
            first = [x for x in mine if x.issue == s.issue and x.sid < s.sid]
            self.assertTrue(all(x.final_t <= s.t for x in first))
            self.assertAlmostEqual(s.sdeposit, 0.25 * (s.bounty + s.pot))

    def test_a_fix_submitted_while_the_deposit_is_held_stakes_the_bare_bounty(self):
        w = short(weeks=10, appeal_good=0.0, **NO_DISPUTES)
        a = E.Retrier(False, w, retry=3, eager=True)
        net = run(w, E.EV, actor=a)
        mine = sorted(issue(net, honest=False), key=lambda s: s.sid)
        early = [s for s in mine if any(x.issue == s.issue and x.sid < s.sid and x.final_t is not None
                                        and x.final_t > s.t for x in mine)]
        self.assertTrue(early)
        self.assertTrue(any(s.pot == 0.0 and abs(s.sdeposit - 0.25 * s.bounty) < 1e-9 for s in early))
        issues = {}
        for s in mine:
            issues.setdefault(s.issue, []).append(s)
        self.assertTrue(all(sum(1 for s in subs if s.final) <= 1 or len(subs) > 1 for subs in issues.values()))


class TestRows(unittest.TestCase):
    def test_the_rows_are_distinct_and_cover_both_pools(self):
        for name, rows in list(E.TABLES.items()) + list(E.ATTACKS.items()):
            labels = [r[0] for r in rows()]
            self.assertEqual(len(set(labels)), len(labels), name)
            self.assertEqual(sum("the tests fail them" in x for x in labels),
                             sum("pass the tests, wrong" in x for x in labels), name)

    def test_a_row_is_reproducible_and_has_the_reports_numbers(self):
        row = next(r for r in E.final_rows() if "D236R2" in r[0])
        row = (row[0], replace(row[1], weeks=6), row[2], row[3])
        a, b = E.metrics(E.run_row(row, 4)), E.metrics(E.run_row(row, 4))
        self.assertEqual({k: v for k, v in a.items() if v == v}, {k: v for k, v in b.items() if v == v})
        for k in ("bad_per_100", "good_failed_pct", "cost_good", "dep_good", "stake_good", "appeals", "sponsored",
                  "known_pay", "second_panels", "stuck_pct"):
            self.assertIn(k, a)

    def test_measured_mode_stays_on_issue_tier_fixes(self):
        self.assertTrue(all(r[1].measured in ("hidden", "pbw") for rows in E.TABLES.values() for r in rows()))


class TestRivalSolvers(unittest.TestCase):
    def test_rival_solvers_reverse_more_bad_passes_and_touch_no_good_fix(self):
        w0 = replace(E.world("pbw"), weeks=10)
        w10 = replace(E.world("pbw", rival_solvers=10, rival_find=0.5), weeks=10)
        self.assertEqual(E.P0.SOLVER_DEPOSIT_BPS, 0)  # the primary case: no solver's deposit
        a, b = run(w0, E.P0), run(w10, E.P0)
        self.assertEqual((a.stats["rival_tests"], a.stats["rival_searches"]), (0, 0))
        self.assertGreater(b.stats["rival_tests"], 5)
        self.assertLess(b.stats["bad_merged"], 0.2 * a.stats["bad_merged"] + 1)
        self.assertEqual(a.stats["evidence_wrong"], b.stats["evidence_wrong"])  # a rival's test fails on a bad fix only

    def test_code_health_counts_every_funded_issue_once(self):
        net = run(replace(E.world("hidden"), weeks=8), Z.BASE)
        n, fixed, wrong, stood = E.health(net, True)
        self.assertEqual(n, len(issue(net)))
        self.assertEqual(fixed + wrong, sum(1 for s in issue(net) if s.final))
        self.assertGreater(stood, 0)


class TestPotSplit(unittest.TestCase):
    def test_the_pot_pays_out_exactly_the_funding(self):
        from pof.sim.openval import potsplit as PS
        r = PS.compare("anthropic", "hidden", 3)
        pg, pb, _ = PS.judge("anthropic", "hidden")
        # every passed fix yields one unit: to its solver while it stands, to whoever reversed it otherwise
        units = PS.ISSUES * (PS.GOOD * pg + (1 - PS.GOOD) * pb) + PS.BAD_PER_YEAR * pb
        self.assertAlmostEqual(r["unit"] * units, sum(PS.bounties()), places=6)
        self.assertEqual(r["sybil"], 0.0)

    def test_more_rival_solvers_leave_a_bad_fix_standing_less_often(self):
        from pof.sim.openval import potsplit as PS
        s = [PS.stands("openai", "pbw", n) for n in (1, 3, 10)]
        self.assertTrue(s[0] > s[1] > s[2])
        self.assertLess(PS.compare("anthropic", "hidden", 10)["pot_bad"], PS.compare("anthropic", "hidden", 1)["pot_bad"])


if __name__ == "__main__":
    unittest.main()
