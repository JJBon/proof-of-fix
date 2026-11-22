"""#141 (task group 6 of #132): the open-validator simulation's re-run rules. Each of #141's rules alone, one test per
new or changed scenario of specs/validator-admission, judge-panels, judge-scores and check-pricing; each switch
changes only what it names; the new actors act as configured beside their honest twins; D17's judging; `Params` with
#134's values (`V1`) reproduces v1's numbers; and `python3 -m pof.sim market validators --v2r1` (round 1's report,
reports/open-validators-v2.md, byte for byte on a quick seed) and --v1. Round 1's rules are `V2` (= `V2R1`) here, now
that round 2's are the defaults (tests/test_openval_r2.py)."""

import contextlib
import io
import re
import subprocess
import sys
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from pof.sim import __main__ as cli
from pof.sim.openval import actors as A
from pof.sim.openval import levels as L
from pof.sim.openval import panels as D
from pof.sim.openval import pricing as PR
from pof.sim.openval import rerun as RR
from pof.sim.openval import scores as S
from pof.sim.openval.net import CONSTITUTION, ISSUE, R_K1_CAP, Act, Honest, Net, Sub
from pof.sim.openval.params import DAY, V1, V2, WORLD, v1_fields
from pof.sim.openval.registry import ACTIVE, CANDIDATE, GONE, LEAVING, ZKTLS, RegistrationError, Registry

ROOT = Path(__file__).resolve().parent.parent
P = V2
TEES = ("nitro", "tdx", "sev-snp")
FAMS = ("anthropic", "openai", "google", "open-weight")
QUIET = replace(WORLD, weeks=3, subs_week=0.0, joins_week=0.0, volunteer_per_day=0.0, reliability=1.0,
                accuracy=1.0)
NO_AUDIT = replace(P, AUDIT_RATE=0.0)


def net(initial=0, p=NO_AUDIT, w=QUIET, actors=(), **kw):
    return Net(1, p, replace(w, initial_active=initial, **kw), actors)


def add(n, i, bond=1250.0, active=True, host=None, family=None, tee=None, behaviour=None):
    v = n.reg.register(n.t, key=f"x{i}", signer=f"x{i}", bond=bond, proof=tee or TEES[i % 3],
                       host=host or f"xh{i}", family=family or FAMS[(i + 1) % 4], operator=f"xop{i}",
                       behaviour=behaviour)
    if active:
        n.reg.seed_active(v, n.t)
    return v


class At(A.Actor):
    party = "test"

    def __init__(self, day, fn):
        super().__init__()
        self.day, self.fn, self.done = day, fn, False

    def on_tick(self, n):
        if not self.done and n.t >= self.day * DAY:
            self.done = True
            self.fn(n)


class Mute(Honest):
    def counted(self, n, sub, v):
        return Act(False, False)


class Withhold(Honest):
    def counted(self, n, sub, v):
        return Act(False, True)


# ---------- validator-admission ----------

class TestAdmission(unittest.TestCase):
    def test_a_genesis_on_an_ordinary_pc_is_refused(self):
        r = Registry(P)
        with self.assertRaises(RegistrationError):
            r.genesis([dict(key="g", signer="g", bond=1250.0, proof=ZKTLS, host="home", family="openai",
                            operator="g")])
        self.assertEqual(r.validators, {})
        Registry(V1).genesis([dict(key="g", signer="g", bond=1250.0, proof=ZKTLS, host="home", family="openai",
                                   operator="g")])  # #134 allowed it
        Registry(P).genesis([dict(key="g", signer="g", bond=1250.0, proof="tdx", host="home", family="openai",
                                  operator="g", cloud_attested=False)])  # level B is fine

    def test_level_c_is_off_at_launch_until_switched_on(self):
        """Owner decision 2026-11-03: only A and B register at launch; C_ACCEPTED switches C on."""
        off = L.LevelNet(1, P, replace(WORLD, weeks=8), ())
        off.run()
        self.assertGreater(off.stats["refused_c"], 0)
        self.assertFalse(any(v.level == "C" for v in off.reg.validators.values()))
        with self.assertRaises(RegistrationError):
            off.register_level("pc", 100.0, "C", "home", "openai", "pc-op")
        on = L.LevelNet(1, RR.C_ON, replace(WORLD, weeks=8), ()).run()
        self.assertEqual(on.stats["refused_c"], 0)
        self.assertTrue(any(v.level == "C" for v in on.reg.validators.values()))

    def test_silence_is_not_slashed_and_the_judge_is_replaced(self):
        n = net(initial=2)
        mute = add(n, 9, behaviour=Mute())
        subs = [n.submit(1.0 + i, 40.0, True, f"s{i}", None) for i in range(12)]
        n.run()
        self.assertEqual(mute.acct.slashed, 0.0)
        self.assertGreater(n.stats["silent"], 0)
        self.assertTrue(all(k == c for k, c in n.k_seen))  # replaced: k never shrinks
        self.assertTrue(all(s.final is not None for s in subs))

    def test_a_sealed_vote_not_revealed_costs_the_flat_amount(self):
        n = net(initial=2)
        w = add(n, 9, behaviour=Withhold())
        for i in range(12):
            n.submit(1.0 + i, 40.0, True, f"s{i}", None)
        n.run()
        self.assertGreater(n.stats["withheld"], 0)
        self.assertAlmostEqual(w.acct.slashed, P.SEALED_NO_REVEAL_SLASH * n.stats["withheld"])
        v1 = net(initial=2, p=replace(V1, AUDIT_RATE=0.0))
        w1 = add(v1, 9, behaviour=Withhold())
        for i in range(12):
            v1.submit(1.0 + i, 40.0, True, f"s{i}", None)
        v1.run()
        self.assertGreater(w1.acct.slashed, P.SEALED_NO_REVEAL_SLASH * v1.stats["withheld"])  # 5 % of $1,250 each

    def test_the_unbonding_delay_is_the_longest_window_plus_a_week(self):
        longest = max(h for lv in P.CHALLENGE_WINDOW_H.values() for h in lv.values())
        self.assertEqual(P.UNBONDING_DELAY_H, longest + 7 * DAY)
        self.assertEqual(P.UNBONDING_DELAY_H, 504.0)

    def test_leave_while_a_challenge_waits(self):
        """Its bond stays locked past the delay until nothing it judged is open, and it stays slashable."""
        n = net(initial=0, w=replace(QUIET, weeks=6))
        v = add(n, 5)
        state = {}

        def leave(n):
            n.open_by[v.vid].add(999)  # a verdict it gave, still open (a frozen challenge)
            n.leave(v)

        def close(n):
            state["before"] = (v.state, n.reg.slashable(v, n.t), n.t >= v.unbond_at)
            n.open_by[v.vid].discard(999)

        n2 = Net(1, NO_AUDIT, replace(QUIET, weeks=6), [At(1, leave), At(30, close)])
        v = add(n2, 5)
        n2.run()
        self.assertEqual(state["before"], (LEAVING, True, True))
        self.assertEqual(v.state, GONE)
        self.assertGreaterEqual(v.gone_at, 30 * DAY)
        self.assertGreater(n2.stats["unbond_waits"], 0)

    def test_a_waiting_submission_scores_its_shadows_by_their_majority(self):
        """Three candidates shadow a waiting submission, two vote fail: each is scored against fail."""
        n = net(initial=0)
        cs = [add(n, i, active=False) for i in range(3)]
        n._score_majority([(cs[0].vid, True, False), (cs[1].vid, True, False), (cs[2].vid, True, True)], [])
        self.assertEqual([(c.shadow_n, c.shadow_agree) for c in cs], [(1, 1), (1, 1), (1, 0)])
        n._score_majority([(cs[0].vid, True, False), (cs[1].vid, False, False)], [])  # 1 revealed: none counts
        self.assertEqual([c.shadow_n for c in cs], [1, 1, 1])

    def test_a_waiting_submission_draws_its_shadows(self):
        n = net(initial=0, w=replace(QUIET, weeks=2))
        cs = [add(n, i, active=False) for i in range(4)]
        sub = n.submit(1.0, 400.0, True, "s", None)  # above k = 1's limit: it waits
        n.run()
        self.assertTrue(sub.waited)
        self.assertEqual(len(sub.wait_shadows), P.SHADOW_PER_WAITING)
        self.assertEqual(sum(c.shadow_n for c in cs), P.SHADOW_PER_WAITING)  # scored by their majority
        none = net(initial=0, p=replace(NO_AUDIT, SHADOW_PER_WAITING=0), w=replace(QUIET, weeks=2))
        sub0 = none.submit(1.0, 400.0, True, "s", None)
        none.run()
        self.assertEqual(sub0.wait_shadows, [])

    def test_a_colluding_genesis_doesnt_set_its_shadows_scores(self):
        """Held verdicts don't score the candidates shadowing them; the sealed majority does, so they qualify."""
        a = A.LoneColluder()
        n = A.run(a, 2, p=P, w=replace(WORLD, weeks=10))
        mine = [s for s in n.subs.values() if s.party == a.party and s.judges]
        self.assertTrue(mine)
        self.assertTrue(all(s.shadows_scored for s in mine if s.was_held))
        self.assertGreater(n.stats["qualified"], 0)

    def test_switching_family_means_registering_again(self):
        m = S.Movers(everyone=True, pace=1.0, margin=0.0)
        n = A.run(m, 1, p=P, w=replace(S.SCORE_WORLD, weeks=10))
        self.assertGreater(n.stats["reregistered"], 0)
        new = [v for v in n.reg.validators.values() if v.vid >= S.MOVER_VID]
        self.assertTrue(new)
        self.assertTrue(all(v.active_at is None or v.active_at > v.registered_at for v in new))  # qualified first
        self.assertTrue(any(v.state == LEAVING or v.state == GONE for v in n.reg.validators.values()))


# ---------- judge-panels ----------

class TestPanels(unittest.TestCase):
    def test_the_genesis_validators_first_verdicts_are_held(self):
        """Only the genesis is active: its k = 1 verdict is held, unpaid, until three others are eligible; then its
        7-day window starts."""
        seen = {}
        n = Net(1, NO_AUDIT, replace(QUIET, weeks=4), [At(5, lambda n: [add(n, i) for i in range(3)]),
                                                         At(4, lambda n: seen.update(state=sub.state))])
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(seen["state"], "held")
        self.assertTrue(sub.was_held)
        self.assertTrue(sub.final)
        self.assertGreaterEqual(sub.final_t, 5 * DAY + P.window_h(1))
        self.assertGreaterEqual(sub.held_h, 4 * DAY)
        self.assertEqual(sub.audit, "agreed")  # audited once a validator outside its panel was eligible

    def test_the_network_already_has_challengers(self):
        """k = 1 (the caps step it down: one host) while three others are eligible: its window starts at once."""
        n = net(initial=0, w=replace(QUIET, weeks=3), genesis_bond=1250.0)
        for i in range(3):
            add(n, i, host="aws", family="anthropic")  # the genesis's host and family: no panel of 3 fits
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.k, 1)
        self.assertFalse(sub.was_held)

    def test_a_lone_validator_at_the_cap_isnt_drawn_at_k1(self):
        n = net(initial=0, w=replace(QUIET, weeks=2))
        cs = [add(n, i, active=False) for i in range(3)]
        subs = [n.submit(1.0 + i, 40.0, True, f"s{i}", None) for i in range(P.K1_PENDING_MAX + 1)]
        n.run()
        self.assertEqual(sum(1 for s in subs if s.draw is not None), P.K1_PENDING_MAX)
        last = subs[-1]
        self.assertEqual(last.wait_reason, R_K1_CAP)
        self.assertEqual(len(last.wait_shadows), 3)  # its waiting shadows are drawn meanwhile
        self.assertTrue(cs)

    def test_the_batch_bond_switch(self):
        p = RR.SW["k1_batch"].p
        n = net(initial=0, p=p)
        v = n.reg.validators[1]  # the genesis, $1,250
        sub = Sub(1, 0.0, 50.0, True, "s", frozenset({"s"}))
        self.assertTrue(n.k1_ok(v, sub))
        n.k1_bounty[v.vid] = 600.0  # 2 x (600 + 50) > 1,250
        self.assertFalse(n.k1_ok(v, sub))
        n.k1_pending[v.vid] = 50  # no count cap under the switch
        n.k1_bounty[v.vid] = 0.0
        self.assertTrue(n.k1_ok(v, sub))

    def test_a_challenge_needs_a_larger_fresh_panel(self):
        r = Registry(P)
        pool = []
        for i in range(7):
            v = r.register(0.0, key=f"k{i}", signer=f"k{i}", bond=1250.0, proof=TEES[i % 3], host=f"h{i}",
                           family=FAMS[i % 4], operator=f"op{i}")
            r.seed_active(v, 0.0)
            pool.append(v)
        self.assertFalse(D.challenge_draw(7, pool[:2], 1, P).filled)  # 2 eligible: no panel larger than 1
        self.assertEqual(D.challenge_draw(7, pool[:3], 1, P).k, 3)
        self.assertFalse(D.challenge_draw(7, pool[:3], 3, P).filled)  # waits for a panel of 5
        self.assertEqual(D.challenge_draw(7, pool[:3], 3, V1).k, 3)  # #134 judged it with 3
        self.assertEqual(D.challenge_draw(7, pool[:7], 7, P).k, 7)  # K_MAX for a panel of K_MAX

    def test_every_k1_verdict_is_audited_once_an_auditor_is_eligible(self):
        n = Net(1, NO_AUDIT, replace(QUIET, weeks=2), [At(3, lambda n: add(n, 0))])
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(n.stats["audits_deferred"], 1)
        self.assertEqual(n.stats["audits"], 1)
        self.assertEqual(sub.audit, "agreed")
        v1 = Net(1, replace(V1, AUDIT_RATE=0.0), replace(QUIET, weeks=2), [At(3, lambda n: add(n, 0))])
        v1.submit(1.0, 40.0, True, "alice", None)
        v1.run()
        self.assertEqual(v1.stats["audits"], 0)

    def test_a_split_level_c_pass_is_audited(self):
        n = L.LevelNet(1, RR.C_ON, replace(QUIET, weeks=0), ())
        split = Sub(1, 0.0, 100.0, False, "s", frozenset({"s"}), k=7, level="C", verdict=True,
                    judges=[(i, i < 4, False) for i in range(7)])
        self.assertTrue(n.always_audit(split))
        self.assertFalse(n.always_audit(replace(split, judges=[(i, True, False) for i in range(7)])))
        self.assertFalse(n.always_audit(replace(split, level="B")))
        self.assertFalse(L.LevelNet(1, V1, replace(QUIET, weeks=0), ()).always_audit(split))

    def test_an_adr_on_a_small_network_expires(self):
        n = net(initial=9)  # 10 eligible
        adr = n.submit(1.0, 0.0, True, "author", None, tier=CONSTITUTION)
        n.run()
        self.assertEqual(adr.state, "expired")
        self.assertIsNone(adr.draw)
        old = net(initial=9, p=replace(V1, AUDIT_RATE=0.0))
        adr1 = old.submit(1.0, 0.0, True, "author", None, tier=CONSTITUTION)
        old.run()
        self.assertEqual(adr1.k, P.K_MAX)  # #134 drew it from 10

    def test_the_network_reaches_the_threshold(self):
        """An ADR from a network of 10 expires; once 14 are eligible, only ADRs submitted then are drawn."""
        n = Net(1, NO_AUDIT, replace(QUIET, initial_active=9, weeks=3),
                [At(3, lambda n: [add(n, 20 + i) for i in range(4)])])
        early = n.submit(1.0, 0.0, True, "a", None, tier=CONSTITUTION)
        late = n.submit(5 * DAY, 0.0, True, "b", None, tier=CONSTITUTION)
        n.run()
        self.assertEqual(early.state, "expired")
        self.assertEqual(late.k, P.K_MAX)
        self.assertGreaterEqual(len(late.draw.pool), P.CONSTITUTION_MIN_ELIGIBLE)

    def test_two_of_one_tee_type_in_a_panel_of_3(self):
        r = Registry(P)
        vs = []
        for i, tee in enumerate(("tdx", "tdx", "nitro", "sev-snp", "tdx")):
            vs.append(r.register(0.0, key=f"k{i}", signer=f"k{i}", bond=1250.0, proof=tee, host=f"h{i}",
                                 family=FAMS[i % 4], operator=f"op{i}"))
        self.assertTrue(D.fits(vs[:1], vs[1], 3, P))  # k = 3: no TEE cap
        self.assertFalse(D.fits(vs[:1], vs[1], 3, V1))  # #134: one of each
        self.assertFalse(D.fits([vs[0], vs[1]], vs[4], 5, P))  # k = 5: at most 2 of a type

    def test_a_bounty_between_two_tiers(self):
        self.assertEqual(P.bond_needed(60.0), 250.0)
        self.assertEqual(P.bond_needed(40.0), 100.0)
        self.assertEqual(P.bond_needed(300.0), 625.0)
        self.assertEqual(V1.bond_needed(60.0), 120.0)


# ---------- judge-scores ----------

def scores(p=P):
    n = Net(1, p, QUIET)
    return n, S.install(n)


def entries(n_ok, n_bad, t=0.0, outcome=True):
    return [(t, True, outcome)] * n_ok + [(t, False, outcome)] * n_bad


class TestScores(unittest.TestCase):
    def test_shadow_verdicts_dont_lift_a_score(self):
        n, sc = scores()
        n.family_outcomes["f"] = entries(40, 20)
        n.family_shadow_outcomes["f"] = entries(200, 0)
        self.assertAlmostEqual(sc.state("f")[0], 40 / 60)
        self.assertFalse(sc.ok("f"))
        n1, sc1 = scores(V1)
        n1.family_outcomes["f"] = entries(40, 20)
        n1.family_shadow_outcomes["f"] = [(1.0, True, True)] * 200
        self.assertTrue(sc1.ok("f"))  # #134 merged them

    def test_a_model_that_gets_better(self):
        n, sc = scores()
        n.family_outcomes["f"] = entries(30, 20)
        self.assertFalse(sc.ok("f"))
        n.family_shadow_outcomes["f"] = entries(40, 10, t=1.0)  # its last 50 shadow verdicts: 80 %
        self.assertTrue(sc.ok("f"))
        self.assertEqual(sc.factor("f"), P.SCORE_FACTOR_MIN)  # paid the minimum until 50 new counted verdicts
        n.family_outcomes["f"] = n.family_outcomes["f"] + entries(45, 5, t=2.0)
        self.assertTrue(sc.ok("f"))
        self.assertGreater(sc.factor("f"), P.SCORE_FACTOR_MIN)
        self.assertAlmostEqual(sc.state("f")[0], 0.9)  # the window restarted

    def test_a_newly_released_open_model(self):
        n, sc = scores()
        self.assertEqual(sc.factor("new"), 1.0)
        self.assertTrue(sc.ok("new"))

    def test_scores_dont_raise_the_price_of_a_check(self):
        """The factors over a period's counted seats average 1 x."""
        n, sc = scores()
        n.family_outcomes.update(a=entries(190, 10), b=entries(170, 30), c=entries(160, 40))
        seats = ["a"] * 5 + ["b"] * 3 + ["c"] * 2
        for f in seats:
            sc.seat(f)
        sc.end_period()
        self.assertAlmostEqual(sum(sc.factor(f) for f in seats) / len(seats), 1.0)
        _, lin = scores(V1)
        lin.net.family_outcomes.update(a=entries(190, 10), b=entries(170, 30), c=entries(160, 40))
        self.assertGreater(sum(lin.factor(f) for f in seats) / len(seats), 1.2)  # #134: neutral at 80 %

    def test_the_balanced_score_of_an_always_pass_judge(self):
        always_pass = [(0.0, True, True)] * 78 + [(0.0, False, False)] * 22
        self.assertAlmostEqual(S.agreement(always_pass, P), 0.78)
        self.assertAlmostEqual(S.agreement(always_pass, RR.SW["balanced"].p), 0.5)

    def test_the_median_neutral_switch(self):
        n, sc = scores(RR.SW["median"].p)
        n.family_outcomes.update(a=entries(190, 10), b=entries(170, 30), c=entries(160, 40))
        n.reg.register(0.0, key="fa", signer="fa", bond=100.0, proof="nitro", host="h", family="a", operator="o1")
        n.reg.register(0.0, key="fb", signer="fb", bond=100.0, proof="nitro", host="h", family="b", operator="o2")
        n.reg.register(0.0, key="fc", signer="fc", bond=100.0, proof="nitro", host="h", family="c", operator="o3")
        self.assertAlmostEqual(sc.factor("b"), 1.0)
        self.assertGreater(sc.factor("a"), 1.0)
        self.assertLess(sc.factor("c"), 1.0)


# ---------- check-pricing ----------

def fake_net(validators, t=24.0):
    reg = SimpleNamespace(validators={v.vid: v for v in validators})
    return SimpleNamespace(reg=reg, stalled=[], subs={}, period_drawn=set(), t=t)


class TestPricing(unittest.TestCase):
    def test_honest_tables_post_every_familys_list_price(self):
        m = PR.Market(P, WORLD, PR.MARKET, 1)
        v = SimpleNamespace(vid=7, family="openai", state=ACTIVE)
        table = m.honest_table(v, 0.0)
        self.assertEqual(set(table), set(m.genesis))
        self.assertEqual(table["anthropic.input"], m.genesis["anthropic.input"])  # the public list price
        old = PR.Market(V1, WORLD, PR.MARKET, 1).honest_table(v, 0.0)
        self.assertNotIn("anthropic.input", old)

    def test_a_table_without_another_familys_price_doesnt_count(self):
        m = PR.Market(P, WORLD, PR.MARKET, 1)
        vs = [SimpleNamespace(vid=i, family="anthropic", state=ACTIVE) for i in range(4)]
        own = PR.family_units("anthropic") + PR.SHARED_UNITS
        m.posters[3] = lambda m, v, t: {u: 100 * x for u, x in m.honest_table(v, t).items() if u in own}
        m.end_period(fake_net(vs), Counter())
        self.assertEqual(m.prices["anthropic.input"], m.genesis["anthropic.input"])

    def test_the_fee_starts_at_its_ceiling(self):
        self.assertEqual(PR.Market(P, WORLD, PR.MARKET, 1).fee_now, P.FEE_CEILING)

    def test_an_even_count_takes_the_lower_middle(self):
        self.assertEqual(PR.step_price(4.0, 4.0, [3.9, 4.0, 4.2, 4.4], P), 4.0)

    def test_only_waits_a_newcomer_could_end_raise_the_fee(self):
        n = net(initial=0, genesis_bond=500.0)
        small = Sub(1, 0.0, 40.0, True, "genesis", frozenset({"genesis"}))  # the genesis is a party: nobody eligible
        self.assertEqual(n.fixable(small), (True, True))
        big = Sub(2, 0.0, 500.0, True, "s", frozenset({"s"}))  # needs $1,250 bonds
        self.assertEqual(n.fixable(big), (False, False))
        add(n, 4, bond=500.0)
        mid = Sub(3, 0.0, 200.0, True, "s", frozenset({"s"}))  # 2 eligible, k = 1: above its $50
        self.assertEqual(n.fixable(mid), (False, True))  # a newcomer of any bond makes k = 3; one at the floor can't

    def test_idle_high_and_the_step_up(self):
        self.assertAlmostEqual(PR.step_fee(0.1, 20, 0, 10, 5, P), 0.095)  # 50 % idle > 40 %
        self.assertAlmostEqual(PR.step_fee(0.1, 20, 0, 10, 7, P), 0.1)  # 30 % idle
        self.assertAlmostEqual(PR.step_fee(0.1, 20, 2, 10, 10, RR.SW["step_up"].p), 0.11)
        self.assertAlmostEqual(PR.step_fee(0.1, 20, 0, 10, 5, RR.SW["step_up"].p), 0.095)

    def test_idling_over_seven_days(self):
        vs = [SimpleNamespace(vid=i, family="anthropic", state=ACTIVE) for i in range(2)]
        fees = {}
        for key, p in (("one", P), ("seven", RR.SW["idle_7d"].p)):
            m = PR.Market(p, WORLD, PR.MARKET, 1)
            nt = fake_net(vs)
            nt.period_drawn = {0, 1}
            m.end_period(nt, Counter(submitted=1))
            nt.period_drawn = set()
            m.end_period(nt, Counter(submitted=1))
            fees[key] = m.fee_now
        self.assertLess(fees["one"], P.FEE_CEILING)  # nobody drawn today: 100 % idle
        self.assertEqual(fees["seven"], P.FEE_CEILING)  # both drawn this week


# ---------- the switches (6.2), the new actors (6.3), D17's judging (6.4) ----------

class TestSwitches(unittest.TestCase):
    def test_each_switch_changes_only_what_it_names(self):
        for s in RR.SWITCHES:
            with self.subTest(s.key):
                changed = RR.switch_fields(s)
                self.assertTrue(changed)
                self.assertLessEqual(set(changed), set(s.names))
                if s.world is not None:
                    self.assertEqual([f for f in WORLD.__dataclass_fields__
                                      if getattr(s.world, f) != getattr(WORLD, f)], ["tees"])

    def test_v1_restores_every_rule_141_changed(self):
        self.assertTrue({"K1_HOLD", "K1_PENDING_MAX", "AUDIT_RATE", "FALSE_VERDICT_SLASH_BPS", "IDLE_HIGH",
                         "CONSTITUTION_MIN_ELIGIBLE", "WAIT_SIGNAL", "SCORE_COUNTED_ONLY", "TEE_CAP_FROM_K",
                         "SHADOW_PER_WAITING", "C_ACCEPTED", "GENESIS_LEVELS"} <= set(v1_fields()))

    def test_the_k1_window_switch_moves_only_k1(self):
        p = RR.SW["k1_window_30"].p
        self.assertEqual(p.window_h(1), 720.0)
        self.assertEqual(p.window_h(3), P.window_h(3))
        self.assertEqual(p.CHALLENGE_WINDOW_H["C"], P.CHALLENGE_WINDOW_H["C"])
        self.assertEqual(p.UNBONDING_DELAY_H, 720.0 + 7 * DAY)


class TestNewActors(unittest.TestCase):
    def test_the_withholder_seals_then_withholds_and_its_twin_doesnt(self):
        w = replace(A.SilentJudge().world(), weeks=12)
        a, t = A.run(A.SilentJudge(sealed=True), 1, p=P, w=w), A.run(A.SilentJudge(True, sealed=True), 1, p=P, w=w)
        me = a.party_validators("silent")[0]
        self.assertGreater(a.stats["withheld"], 0)
        self.assertEqual(t.stats["withheld"], 0)
        self.assertAlmostEqual(me.acct.slashed, P.SEALED_NO_REVEAL_SLASH * a.stats["withheld"])

    def test_the_silent_judge_isnt_slashed_and_k_never_shrinks(self):
        n = A.run(A.SilentJudge(), 1, p=P, w=replace(A.SilentJudge().world(), weeks=12))
        self.assertGreater(n.stats["silences"], 0)
        self.assertEqual(n.party_validators("silent")[0].acct.slashed, 0.0)
        self.assertTrue(all(k == c for k, c in n.k_seen))

    def test_the_colluding_genesis_is_held_and_audited(self):
        a = A.LoneColluder()
        n = A.run(a, 3, p=P, w=replace(WORLD, weeks=20))
        mine = [s for s in n.subs.values() if s.party == a.party and s.verdict]
        self.assertTrue(mine)
        self.assertTrue(all(s.was_held for s in mine))
        self.assertGreater(sum(1 for s in mine if s.reversed), sum(1 for s in mine if s.final))

    def test_a_level_c_attacker_is_refused_while_c_is_off(self):
        r = RR.level_twin(lambda h: L.TestLiar(h, "grown"), [1], P)
        self.assertIn("refused", r)
        self.assertIn("refused", RR.level_twin(lambda h: L.TestLiar(h), [1], RR.C_ON))  # the genesis at C


class TestJudging(unittest.TestCase):
    def test_a_result_that_isnt_significant_fails(self):
        self.assertFalse(RR.loses(-34.0, 23.5))  # -34 ± 47
        self.assertTrue(RR.loses(-137.0, 32.0))
        ok, why = RR._rows_against_twin([("a", -100.0, 10.0), ("b", -34.0, 23.5)])
        self.assertFalse(ok)
        self.assertIn("b (-34 ± 47 $)", why)
        self.assertTrue(RR._rows_against_twin([("a", -100.0, 10.0)])[0])

    def test_at_most_and_at_least(self):
        self.assertTrue(RR.at_most(0.10, 0.02, 0.15))
        self.assertFalse(RR.at_most(0.12, 0.02, 0.15))
        self.assertTrue(RR.at_least(0.95, 0.02, 0.90))
        self.assertFalse(RR.at_least(0.93, 0.02, 0.90))

    def test_a_pooled_share(self):
        r, se = RR.pooled([9, 9, 9], [10, 10, 10])
        self.assertAlmostEqual(r, 0.9)
        self.assertEqual(se, 0.0)
        r, se = RR.pooled([10, 8], [10, 10])
        self.assertAlmostEqual(r, 0.9)
        self.assertGreater(se, 0.0)
        self.assertFalse(RR.at_least(r, se, 0.9) and se > 0 and r - 2 * se >= 0.9)


# ---------- #134's rules reproduce v1's numbers (seed 1, captured before #141's change) ----------

class TestV1Reproduces(unittest.TestCase):
    def test_v1_params_reproduce_v1s_numbers(self):
        n = Net(1, V1, WORLD).run()
        st = {k: n.stats[k] for k in ("submitted", "waited", "drawn", "final", "paid", "bad_merged", "qualified",
                                      "reversed", "challenges", "withdrawn", "stepped_down", "audits")}
        self.assertEqual(st, {"submitted": 1566, "waited": 1021, "drawn": 626, "final": 624, "paid": 447,
                              "bad_merged": 4, "qualified": 19, "reversed": 11, "challenges": 31, "withdrawn": 927,
                              "stepped_down": 451, "audits": 30})
        self.assertAlmostEqual(n.stats["slashed"], 550.0)
        self.assertAlmostEqual(sum(n.validator_net(v) for v in n.reg.validators.values()), -2861.01446, places=4)
        self.assertAlmostEqual(A.against_twin(lambda h: A.LoneColluder(h), [1], p=V1)["diff"], 4201.131785, places=4)
        self.assertAlmostEqual(A.against_twin(lambda h: A.SeedGrinder(h), [1], p=V1)["diff"], 137.734092, places=4)
        st = PR.settle(PR.run_market(1, V1))
        self.assertAlmostEqual(st["fee"], 0.249698, places=5)
        self.assertAlmostEqual(st["break_even"], 0.256715, places=5)
        lv = L.LevelNet(1, V1, WORLD).run()
        self.assertEqual((lv.stats["drawn"], lv.stats["withdrawn"], lv.stats["qualified"]), (563, 990, 13))
        m = S.market_metrics(S.run_mode(1, "pay", S.SCORE_WORLD, V1))
        self.assertAlmostEqual(m["fee_per_check"], 0.509416, places=5)
        self.assertAlmostEqual(m["barred_weak"], 0.747253, places=5)


# ---------- the command (6.5) ----------

def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(list(argv))
    return rc, out.getvalue()


CRITERIA = ("open-validator attacker loses", "pricing attacker loses", "proof-level attacker loses",
            "scoring attacker", "a sybil at or under", "a sybil above the share", "colluding lone validator",
            "constitution waits", "fee settles", "crowds into one model", "network still grows", "answer shopping",
            "every earlier criterion", "adopt the k table")
VERDICT = re.compile(r"\*\*(met|not met)\*\*")


def acceptance_rows(text):
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        for phrase in CRITERIA:
            if phrase in cells[0].lower() and phrase not in rows:
                m = VERDICT.search(cells[1])
                if m:
                    rows[phrase] = m.group(1)
    return rows


class TheCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rc, cls.out = run_cli("market", "validators", "--seeds", "1", "--quick", "--v2r1")

    def test_it_prints_the_v2_report_and_names_each_criterion(self):
        self.assertEqual(self.rc, 0)
        self.assertIn("# Open validators, v2", self.out)
        rows = acceptance_rows(self.out)
        self.assertEqual(set(rows), set(CRITERIA))
        others = [v for k, v in rows.items() if k != "adopt the k table"]
        self.assertEqual(rows["adopt the k table"], "not met" if "not met" in others else "met")
        for heading in ("An honest network grows under the hold", "The colluding genesis under the hold",
                        "A silent judge without a silence slash", "An early coalition", "An honest validator's month",
                        "A rule against its alternative", "Level C at launch", "Acceptance criteria for open"):
            self.assertIn(heading, self.out)

    def test_its_numbers_are_reproducible_on_fixed_seeds(self):
        for name in ("colluder", "growth", "silent"):
            a = RR._section(name, (1,), (1,), True)
            b = RR._section(name, (1,), (1,), True)
            self.assertEqual(repr(a), repr(b))
        self.assertIn(RR.md_colluder(RR._section("colluder", (1,), (1,), True), [1]).splitlines()[4], self.out)

    def test_v2r1_prints_round_1s_report_unchanged(self):
        """Captured from main before round 2 (f6c7641): round 1's rules reproduce round 1's report byte for byte."""
        self.assertEqual(self.out, (ROOT / "tests" / "data" / "openval-v2-quick-seed1.md").read_text(encoding="utf-8"))

    def test_v1_prints_134s_report_unchanged(self):
        out = subprocess.run([sys.executable, "-m", "pof.sim", "market", "validators", "--v1", "--seeds", "1",
                              "--quick"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
        self.assertEqual(out, (ROOT / "tests" / "data" / "openval-v1-quick-seed1.md").read_text(encoding="utf-8"))


class TheReport(unittest.TestCase):
    REPORT = ROOT / "reports" / "open-validators-v2.md"

    def test_the_report_names_each_criterion_met_or_not(self):
        if not self.REPORT.exists():
            self.skipTest("reports/open-validators-v2.md not written yet")
        self.assertEqual(set(acceptance_rows(self.REPORT.read_text(encoding="utf-8"))), set(CRITERIA))

    def test_v1s_numbers_quoted_beside_the_rows_are_v1s(self):
        v1 = (ROOT / "reports" / "open-validators-v1.md").read_text(encoding="utf-8")
        for key, text in RR.V1_PUBLISHED.items():
            with self.subTest(key):
                self.assertIn(text, v1)


if __name__ == "__main__":
    unittest.main()
