"""#236, task 10.1 (design D20-D23): seats by rank, the solver's deposit, test disputes, the appeal and a new family's
start (pof/sim/openval/seats.py, net.py), and the sweeps that size them (sizing.py). One test class per switch."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from pof.sim.openval import actors as A
from pof.sim.openval import measured as M
from pof.sim.openval import seats as ST
from pof.sim.openval import sizing as Z
from pof.sim.openval.net import Net
from pof.sim.openval.params import D236, PARAMS, WORLD

RANK = replace(PARAMS, SEAT_RULE="rank")


def short(pool="hidden", weeks=8, **kw):
    return replace(Z.world(pool, **kw), weeks=weeks)


def run(w, p, seed=5, actor=None):
    return Net(seed, p, w, [actor or Z.OnMarket(w=w)]).run()


def issue(net, honest=True):
    return [s for s in net.subs.values() if s.tier == "issue" and (s.party is None) == honest]


class TestDefaults(unittest.TestCase):
    def test_every_rule_is_off_by_default(self):
        p = PARAMS
        self.assertEqual((p.SEAT_RULE, p.NEW_FAMILY_START, p.SOLVER_DEPOSIT_BPS, p.EVIDENCE_REWARD_BPS, p.APPEAL,
                          p.IDLE_COUNTS, p.CONTENDER_SHADOWS), ("min", "neutral", 0, 0, "off", "active", 0))
        self.assertEqual(p.evidence_stake(500.0), 0.0)
        net = run(short(weeks=4), PARAMS)
        self.assertIsNone(net.seats)
        st = net.stats
        self.assertEqual((st["sdep_posted"], st["appeals"], st["stakes_lost"], st["evidence_reward"]), (0, 0, 0, 0))

    def test_the_proposal_is_the_designs(self):
        self.assertEqual((D236.SEAT_RULE, D236.SEAT_MARGIN, D236.CAP_MIN_FAMILIES, D236.SOLVER_DEPOSIT_BPS,
                          D236.SOLVER_DEPOSIT_TO, D236.EVIDENCE_REWARD_BPS, D236.APPEAL, D236.NEW_FAMILY_START),
                         ("rank", 0.05, 3, 2_500, "bounty", 1_000, "others", "contender"))
        self.assertEqual(D236.SCORE_MIN, 0.70)


class TestSeatRule(unittest.TestCase):
    def test_one_family_far_ahead(self):  # specs/judge-scores, "One family far ahead"
        self.assertEqual(ST.rule({"a": 0.88, "b": 0.65, "c": 0.55}, RANK), {"a"})

    def test_three_families_level(self):  # "Three families level"
        self.assertEqual(ST.rule({"a": 0.75, "b": 0.75, "c": 0.74, "d": 0.59}, RANK), {"a", "b", "c"})

    def test_the_margin_and_the_minimum_each_bind(self):
        s = {"a": 0.90, "b": 0.86, "c": 0.72, "d": None}
        self.assertEqual(ST.rule(s, RANK), {"a", "b"})
        self.assertEqual(ST.rule(s, replace(RANK, SEAT_MARGIN=0.0)), {"a"})
        self.assertEqual(ST.rule(s, replace(RANK, SEAT_MARGIN=0.25)), {"a", "b", "c"})
        self.assertEqual(ST.rule({"a": 0.90, "b": 0.69}, replace(RANK, SEAT_MARGIN=0.25)), {"a"})
        self.assertEqual(ST.rule({"a": 0.90, "b": 0.69}, replace(RANK, SEAT_MARGIN=0.25, SCORE_MIN=0.5)), {"a", "b"})

    def test_on_known_answers_the_seats_are_the_judge_runs(self):
        seated = lambda pool, **kw: set(run(short(pool, weeks=1), replace(RANK, **kw)).seats.seated())  # noqa: E731
        self.assertEqual(seated("hidden"), {"anthropic"})
        self.assertEqual(seated("pbw"), {"anthropic", "openai", "google"})
        self.assertEqual(seated("pbw", SEAT_MARGIN=0.01), {"anthropic", "openai"})
        self.assertEqual(seated("pbw", SEAT_MARGIN=0.0), {"openai"})

    def test_only_seated_families_are_drawn_and_the_rest_shadow(self):
        net = run(short(), RANK)
        fam = lambda vid: net.reg.validators[vid].family  # noqa: E731
        subs = [s for s in issue(net) if s.judges]
        self.assertTrue(subs)
        self.assertEqual({fam(vid) for s in subs for vid, _, _ in s.judges}, {"anthropic"})
        shadows = {fam(vid) for s in subs for vid, _, _ in s.family_shadows}
        self.assertTrue(shadows and "anthropic" not in shadows)

    def test_with_the_v3_rule_every_family_is_drawn(self):
        net = run(short(), PARAMS)
        fams = {net.reg.validators[vid].family for s in issue(net) for vid, _, _ in s.judges}
        self.assertGreater(len(fams), 3)


class TestFamilyCap(unittest.TestCase):
    def most(self, net):
        out = []
        for s in issue(net):
            if s.k >= 3 and s.judges:
                fams = [net.reg.validators[vid].family for vid, _, _ in s.judges]
                out.append((max(fams.count(f) for f in fams), s.k))
        return out

    def test_one_seated_family_holds_every_seat(self):  # validator-admission, "One family holds every seat"
        net = run(short(), RANK)
        self.assertFalse(net.draw_p().FAMILY_CAP)
        panels = self.most(net)
        self.assertTrue(panels and all(n == k for n, k in panels))
        hosts = [len({net.reg.validators[vid].host for vid, _, _ in s.judges}) for s in issue(net)
                 if s.k >= 3 and s.judges]
        self.assertTrue(hosts and all(h >= 3 for h in hosts))  # the host cap still applies

    def test_three_seated_families_are_capped(self):  # "Three families seated"
        net = run(short("pbw"), RANK)
        self.assertTrue(net.draw_p().FAMILY_CAP)
        panels = self.most(net)
        self.assertTrue(panels and all(n <= (k - 1) // 2 for n, k in panels))

    def test_cap_min_families_moves_the_switch(self):
        self.assertTrue(run(short(weeks=1), replace(RANK, CAP_MIN_FAMILIES=1)).draw_p().FAMILY_CAP)
        self.assertFalse(run(short("pbw", weeks=1), replace(RANK, CAP_MIN_FAMILIES=4)).draw_p().FAMILY_CAP)
        two = replace(RANK, SEAT_MARGIN=0.01)
        self.assertFalse(run(short("pbw", weeks=1), two).draw_p().FAMILY_CAP)
        self.assertTrue(run(short("pbw", weeks=1), replace(two, CAP_MIN_FAMILIES=2)).draw_p().FAMILY_CAP)

    def test_the_cap_with_one_family_leaves_most_fixes_waiting(self):
        capped = run(short(), replace(RANK, CAP_MIN_FAMILIES=1))
        free = run(short(), RANK)
        self.assertGreater(capped.stats["waited"], 5 * max(1, free.stats["waited"]))


class TestLiveSeats(unittest.TestCase):
    def fake(self, p):
        vs = {i: SimpleNamespace(family=f, genesis=f == "a") for i, f in enumerate("abc")}
        return SimpleNamespace(p=p, t=0.0, n_final=0, reg=SimpleNamespace(validators=vs), family_outcomes={},
                               family_shadow_outcomes={})

    def feed(self, net, book, family, n, agree):
        """n verdicts, `agree` of them right, alternating passed and failed outcomes."""
        rec = getattr(net, book).setdefault(family, [])
        rec += [(net.t, i < agree, i % 2 == 0) for i in range(n)]
        net.n_final += 1

    def test_the_genesis_family_is_seated_and_a_new_one_is_a_contender(self):
        net = self.fake(replace(RANK, NEW_FAMILY_START="contender"))
        self.assertEqual(ST.LiveSeats(net).seated(), {"a"})
        self.assertEqual(ST.LiveSeats(self.fake(RANK)).seated(), {"a", "b", "c"})  # D14's neutral start

    def test_a_contender_is_seated_by_a_complete_block_only(self):
        net = self.fake(replace(RANK, NEW_FAMILY_START="contender"))
        seats = ST.LiveSeats(net)
        self.assertEqual(seats.seated(), {"a"})
        self.feed(net, "family_outcomes", "a", 60, 54)  # the seated family: 90 %
        self.feed(net, "family_shadow_outcomes", "b", 99, 99)
        self.assertEqual(seats.seated(), {"a"})  # 99 perfect verdicts are not a block
        self.assertAlmostEqual(seats.score("a"), 0.9)
        self.feed(net, "family_shadow_outcomes", "b", 1, 1)
        self.assertEqual(seats.seated(), {"b"})  # b's block at 100 % seats it, and puts a's 90 % outside the margin
        self.assertFalse(seats.fam["a"].seated)

    def test_a_block_inside_the_margin_shares_the_seats_and_a_weak_one_does_not(self):
        net = self.fake(replace(RANK, NEW_FAMILY_START="contender"))
        seats = ST.LiveSeats(net)
        seats.seated()
        self.feed(net, "family_outcomes", "a", 60, 54)
        self.feed(net, "family_shadow_outcomes", "b", 100, 88)
        self.feed(net, "family_shadow_outcomes", "c", 100, 80)
        self.assertEqual(seats.seated(), {"a", "b"})
        self.assertEqual(seats.fam["c"].blocks, 1)
        self.feed(net, "family_shadow_outcomes", "c", 50, 50)  # half a block: judged only when complete
        self.assertEqual(seats.seated(), {"a", "b"})

    def test_a_seated_family_that_falls_becomes_a_contender_unless_nobody_else_can_judge(self):
        net = self.fake(replace(RANK, NEW_FAMILY_START="contender"))
        seats = ST.LiveSeats(net)
        seats.seated()
        self.feed(net, "family_outcomes", "a", 60, 30)  # 50 %: below SCORE_MIN, and nobody else has a score
        self.assertEqual(seats.seated(), {"a"})
        self.assertTrue(seats.fallback)
        self.feed(net, "family_shadow_outcomes", "b", 100, 85)
        self.assertEqual(seats.seated(), {"b"})
        self.assertFalse(seats.fallback)
        self.assertEqual((seats.fam["a"].unseatings, seats.fam["b"].seatings), (1, 1))

    def test_live_and_known_agree_when_one_family_is_far_ahead(self):
        w = short(weeks=10, scores="live")
        live, known = run(w, Z.BASE), run(replace(w, seat_scores="known"), Z.BASE)
        self.assertEqual(live.seats.seated(), known.seats.seated())
        self.assertEqual(live.stats["paid"], known.stats["paid"])


class TestNewFamily(unittest.TestCase):
    def counted(self, start, appeal="off"):
        w = replace(Z.late("hidden", "mistral"), weeks=10)
        p = replace(Z.BASE, NEW_FAMILY_START=start, APPEAL=appeal)
        net = run(w, p, actor=Z.NewFamily(w=w, family="mistral", week=2))
        self.assertEqual(sum(v.family == "mistral" for v in net.reg.validators.values()), 4)
        return net, sum(1 for s in issue(net) for vid, _, _ in s.judges
                        if net.reg.validators[vid].family == "mistral")

    def test_a_new_family_starting_as_a_contender_is_not_drawn(self):
        net, n = self.counted("contender")
        self.assertEqual(n, 0)
        self.assertNotIn("mistral", net.seats.seated())
        self.assertTrue(any(net.reg.validators[vid].family == "mistral"
                            for s in issue(net) for vid, _, _ in s.family_shadows))  # it shadow-judges

    def test_with_the_neutral_start_it_is_drawn_at_once(self):
        _, n = self.counted("neutral")
        self.assertGreater(n, 20)


class TestDeposit(unittest.TestCase):
    def test_the_three_destinations(self):
        net = run(short(weeks=10, find=1.0), Z.BASE)
        subs = [s for s in issue(net) if s.final is not None]
        self.assertTrue(all(abs(s.sdeposit - 0.25 * s.bounty) < 1e-9 for s in subs))
        for s in subs:
            want = "returned" if s.final else "disputer" if s.by_evidence else "bounty"
            self.assertEqual(s.sdeposit_to, want)
        st = net.stats
        self.assertTrue(st["sdep_returned"] > 0 and st["sdep_bounty"] > 0 and st["sdep_disputer"] > 0)
        locked = sum(s.sdeposit for s in issue(net) if not s.sdeposit_to)
        self.assertAlmostEqual(st["sdep_posted"], st["sdep_returned"] + st["sdep_bounty"] + st["sdep_disputer"]
                               + locked, places=6)

    def test_the_pool_is_the_alternative(self):
        net = run(short(weeks=6), replace(Z.BASE, SOLVER_DEPOSIT_TO="pool"))
        self.assertGreater(net.stats["sdep_pool"], 0)
        self.assertEqual(net.stats["sdep_bounty"], 0)

    def test_judges_do_not_earn_by_rejecting(self):  # bounty-market, "Judges don't earn by rejecting"
        w = short(weeks=6)
        fees = lambda net: sorted((v.vid, round(v.acct.fees + v.acct.rewards + v.acct.gains, 9))  # noqa: E731
                                  for v in net.reg.validators.values())
        self.assertEqual(fees(run(w, Z.BASE)), fees(run(w, replace(Z.BASE, SOLVER_DEPOSIT_BPS=0))))

    def test_a_rejected_fix_raises_the_bounty_for_the_next_solver(self):  # "A bad fix rejected"
        w = short(weeks=10, find=0.0, false=0.0)
        a = Z.Solver(w=w, retry=3)
        net = run(w, Z.BASE, actor=a)
        mine = sorted(issue(net, honest=False), key=lambda s: s.sid)
        again = [s for s in mine if s.pot > 0]
        self.assertTrue(again)
        s = again[0]
        first = next(x for x in mine if x.issue == s.issue)
        self.assertEqual((first.final, first.sdeposit_to), (False, "bounty"))
        self.assertAlmostEqual(first.sdeposit, 0.25 * first.bounty)
        self.assertAlmostEqual(s.pot, first.sdeposit)
        self.assertAlmostEqual(s.sdeposit, 0.25 * (s.bounty + s.pot))  # $20 on $80, then $25 on $100
        pa = net.parties[a.party]
        self.assertAlmostEqual(pa.sdeposits_lost, sum(x.sdeposit for x in mine if x.sdeposit_to == "bounty"))
        paid_pots = sum(x.pot for x in mine if x.final)
        self.assertAlmostEqual(net.stats["pots_paid"], paid_pots)

    def test_a_solver_loses_its_deposit_only_when_its_fix_is_not_paid(self):
        w = short(weeks=8, find=0.0, false=0.0)
        r0 = A.against_twin(lambda h: Z.Solver(h, w), [3], p=replace(Z.BASE, SOLVER_DEPOSIT_BPS=0),
                            metrics=Z._party_metrics)
        r = A.against_twin(lambda h: Z.Solver(h, w), [3], p=Z.BASE, metrics=Z._party_metrics)
        self.assertEqual((r["twin"], r["twin_submitted"]), (0.0, 0))
        self.assertEqual((r["submitted"], r["bad_paid"]), (r0["submitted"], r0["bad_paid"]))
        self.assertGreater(r["lost"], 0)
        self.assertAlmostEqual(r0["attacker"] - r["attacker"], r["lost"], places=6)


class TestTests(unittest.TestCase):
    def test_a_disputer_without_evidence_loses_its_stakes_to_the_solvers(self):  # judge-panels' scenario
        w = short(weeks=6, find=0.0, false=0.0)
        net = run(w, Z.BASE, actor=Z.Disputer(False, w, "passing"))
        st, pa = net.stats, net.parties["disputer"]
        self.assertGreater(pa.tests, 50)
        self.assertEqual((pa.tests_upheld, st["evidence_reversed"], st["test_panels"]), (0, 0, 0))
        self.assertAlmostEqual(pa.costs, 5.0 * pa.tests)
        self.assertAlmostEqual(sum(s.stakes_won for s in issue(net)), pa.costs)
        self.assertEqual(net.party_net("disputer"), -pa.costs)

    def test_an_accepted_test_pays_the_deposit_and_the_reward(self):
        w = short(weeks=6, find=0.0, false=1.0)  # every wrong test is accepted
        net = run(w, Z.BASE, actor=Z.Disputer(False, w, "wrong"))
        pa = net.parties["disputer"]
        rev = [s for s in issue(net) if s.by_evidence]
        self.assertTrue(rev and all(s.disputer == "disputer" and s.final is False and s.sdeposit_to == "disputer"
                                    for s in rev))
        self.assertEqual(pa.tests_upheld, len(rev))
        self.assertAlmostEqual(pa.gains, sum(0.25 * s.bounty + 0.10 * s.bounty for s in rev))
        self.assertEqual(net.stats["paid"], 0)

    def test_the_stake_follows_the_bounty_when_the_share_is_set(self):
        p = replace(Z.BASE, EVIDENCE_STAKE_BPS=500)
        self.assertEqual((p.evidence_stake(40.0), p.evidence_stake(400.0)), (5.0, 20.0))
        w = short(weeks=4, find=0.0, false=0.0)
        net = run(w, p, actor=Z.Disputer(False, w, "passing"))
        self.assertAlmostEqual(net.parties["disputer"].costs,
                               sum(max(5.0, 0.05 * s.bounty) for s in issue(net) if s.stakes_won))

    def test_a_selective_disputer_posts_only_where_it_expects_to_gain(self):
        w = short(weeks=6)
        net = run(w, Z.BASE, actor=Z.Disputer(False, w, "wrong", select=True))
        hit = [s for s in issue(net) if s.stakes_won or s.disputer == "disputer"]
        self.assertTrue(hit)
        self.assertTrue(all(0.05 * 0.35 * s.bounty > 0.95 * 5.0 for s in hit))

    def test_the_twin_posts_nothing_and_an_honest_contender_searches(self):
        w = short(weeks=6)
        r = A.against_twin(lambda h: Z.Disputer(h, w, "contender", seat="openai"), [3], p=Z.BASE,
                           metrics=Z._party_metrics)
        self.assertEqual((r["twin"], r["twin_tests"], r["twin_searches"]), (0.0, 0, 0))
        self.assertGreater(r["searches"], r["tests_upheld"])


class TestAppeal(unittest.TestCase):
    def nets(self, **kw):
        w = short(weeks=10, find=0.0, false=0.0, appeal_bad=1.0)
        return run(w, replace(D236, **kw))

    def test_no_appeal_by_default_and_one_per_rejected_fix(self):
        net = self.nets()
        rej = [s for s in issue(net) if s.verdict is False and s.final is not None]
        self.assertTrue(rej and all(s.appeal in ("upheld", "failed") for s in rej))
        self.assertEqual(net.stats["appeals"], sum(1 for s in issue(net) if s.appeal))
        self.assertTrue(all(not s.appeal for s in issue(net) if s.verdict))
        s = rej[0]
        before = net.stats["appeals"]
        net._appeal(s)  # a second appeal is refused
        self.assertEqual(net.stats["appeals"], before)

    def test_the_panel_is_drawn_from_the_families_that_did_not_judge_contenders_included(self):
        net = self.nets()
        fam = lambda vid: net.reg.validators[vid].family  # noqa: E731
        app = [s for s in issue(net) if s.appeal_judges]
        self.assertTrue(app)
        for s in app:
            judged = {fam(vid) for vid, _, _ in s.judges}
            on = [fam(vid) for vid in s.appeal_judges]
            self.assertFalse(judged & set(on))
            self.assertFalse(set(s.appeal_judges) & s.draw.drawn)
            self.assertEqual(len(on), net.p.challenge_k(s.k))
            self.assertLessEqual(max(on.count(f) for f in on), (len(on) - 1) // 2)  # six families: the cap applies
        self.assertTrue(any(not net.seats.ok(fam(vid)) for s in app for vid in s.appeal_judges))

    def test_without_contenders_one_seated_family_leaves_no_panel(self):
        net = self.nets(APPEAL="others_seated")
        app = [s for s in issue(net) if s.appeal]
        self.assertTrue(app and all(s.appeal == "no panel" and not s.appeal_judges for s in app))
        self.assertTrue(all(s.final is False for s in app if s.final is not None))

    def test_the_seated_families_own_draw_repeats_the_verdict(self):
        net = self.nets(APPEAL="seated")
        app = [s for s in issue(net) if s.appeal_judges]
        self.assertTrue(all(net.seats.ok(net.reg.validators[vid].family) for s in app for vid in s.appeal_judges))
        self.assertEqual(net.stats["appeals_upheld"], 0)

    def test_every_judge_must_pass_upholds_fewer(self):
        self.assertLess(self.nets(APPEAL_PASS_RULE="unanimous").stats["appeals_upheld"],
                        self.nets().stats["appeals_upheld"])

    def test_an_upheld_appeal_is_paid_and_scored_against_the_rejecting_judges(self):
        net = self.nets()
        up = [s for s in issue(net) if s.appeal == "upheld" and s.final is not None]
        self.assertTrue(up and all(s.final and s.sdeposit_to == "returned" and s.verdict is False for s in up))
        down = [s for s in issue(net) if s.appeal == "failed" and s.final is not None]
        self.assertTrue(down and all(s.final is False and s.sdeposit_to == "bounty" for s in down))
        wrong = [e for e in net.family_outcomes["anthropic"] if not e[1] and e[2]]
        self.assertGreaterEqual(len(wrong), len(up))  # each rejecting judge is scored as wrong

    def test_an_upheld_appeal_is_open_to_disputes(self):
        w = short(weeks=10, find=1.0, false=0.0, appeal_bad=1.0)
        net = run(w, D236)
        up = [s for s in issue(net) if s.appeal == "upheld" and s.final is not None]
        back = [s for s in up if s.by_evidence]
        self.assertTrue(back and all(s.final is False and s.sdeposit_to == "disputer" for s in back))
        self.assertTrue(all(not s.good for s in back))

    def test_the_appellant_pays_the_appeal_panel(self):
        w = short(weeks=8, find=0.0, false=0.0)
        a = Z.Solver(w=w, appeal=True)
        net = run(w, replace(D236, APPEAL_PASS_RULE="unanimous"), actor=a)
        mine = issue(net, honest=False)
        pa = net.parties[a.party]
        self.assertGreater(pa.appeals, 10)
        self.assertAlmostEqual(pa.costs, net.w.attempt_fee * len(mine) + sum(s.billed for s in mine)
                               + pa.sdeposits_lost, places=6)
        per_judge = lambda subs: sum(s.charges for s in subs) / sum(s.k for s in subs)  # noqa: E731
        self.assertGreater(per_judge([s for s in mine if s.appeal_judges]),
                           1.5 * per_judge([s for s in mine if s.verdict]))

    def test_appealing_to_the_seated_families_gains_a_solver_of_bad_fixes_nothing(self):
        w = short(weeks=8, find=0.0, false=0.0)
        mk = lambda h: Z.Solver(h, w, appeal=True, twin="no_appeal")  # noqa: E731
        r = A.against_twin(mk, [3], p=replace(D236, APPEAL="seated"), metrics=Z._party_metrics)
        self.assertEqual((r["twin_appeals"], r["twin_submitted"]), (0, r["submitted"]))
        self.assertGreater(r["appeals"], 10)
        self.assertEqual(r["bad_paid"], r["twin_bad_paid"])  # the same family repeats itself
        self.assertLessEqual(r["diff"], 0)

    def test_a_solver_of_bad_fixes_gains_by_appealing_to_contenders(self):
        w = short(weeks=8, find=0.0, false=0.0)
        mk = lambda h: Z.Solver(h, w, appeal=True, twin="no_appeal")  # noqa: E731
        r = A.against_twin(mk, [3], p=D236, metrics=Z._party_metrics)
        self.assertGreater(r["upheld"], 0.5 * r["appeals"])
        self.assertGreater(r["bad_paid"], r["twin_bad_paid"])
        self.assertGreater(r["diff"], 0)


class TestSizing(unittest.TestCase):
    def test_the_rows_are_distinct_and_cover_both_pools(self):
        for name, rows in list(Z.TABLES.items()) + list(Z.ATTACKS.items()):
            labels = [r[0] for r in rows()]
            self.assertEqual(len(set(labels)), len(labels), name)
            self.assertEqual(sum("the tests fail them" in x for x in labels),
                             sum("pass the tests, wrong" in x for x in labels), name)

    def test_a_row_is_reproducible_and_has_the_reports_numbers(self):
        row = next(r for r in Z.final_rows() if "D236" in r[0])
        row = (row[0], replace(row[1], weeks=6), row[2], row[3])
        a, b = Z.metrics(Z.run_row(row, 4)), Z.metrics(Z.run_row(row, 4))
        self.assertEqual({k: v for k, v in a.items() if v == v}, {k: v for k, v in b.items() if v == v})
        for k in ("bad_per_100", "good_failed_pct", "cost_good", "dep_good", "appeals", "fee", "seated_anthropic"):
            self.assertIn(k, a)

    def test_the_fee_is_the_markets_and_contenders_pull_it_to_the_floor(self):
        w = short(weeks=12)
        last = lambda net: net.fee.series[-1]["fee"]  # noqa: E731
        self.assertAlmostEqual(last(run(w, Z.BASE)), PARAMS.FEE_FLOOR, places=3)
        self.assertGreater(last(run(w, replace(Z.BASE, IDLE_COUNTS="seated"))), 10 * PARAMS.FEE_FLOOR)

    def test_no_second_opinion_challenges_unless_asked(self):
        self.assertEqual(Z.world("hidden").volunteer_per_day, 0.0)
        self.assertEqual(Z.world("hidden", second_opinions=True).volunteer_per_day, WORLD.volunteer_per_day)
        self.assertEqual(run(short(weeks=6), Z.BASE).stats["challenges_volunteer"], 0)

    def test_the_exact_appeal_counts(self):
        seven = [s for _, s in M.SEVEN]
        x = Z.appeal_exact("hidden", ("anthropic",), [s for s in seven if s != "anthropic"])
        self.assertEqual((x["bad_rejected"], x["good_rejected"]), (82, 3))
        self.assertGreater(x["bad_overturned"], 0.5)
        one = Z.appeal_exact("hidden", ("anthropic",), ["anthropic"], cap=5)
        self.assertEqual((one["bad_overturned"], one["good_restored"]), (0.0, 0.0))  # a model repeats itself

    def test_measured_judges_stay_on_issue_tier_fixes(self):
        net = run(short(weeks=2), D236)
        net.w = replace(net.w, accuracy=1.0)
        adr = SimpleNamespace(sid=7, good=False, tier="constitution")
        self.assertIs(net.honest_vote(adr, SimpleNamespace(vid=3, family="anthropic"), 0), False)


if __name__ == "__main__":
    unittest.main()
