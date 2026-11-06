"""#141 round 2 (task group 7 of #132): the open-validator simulation's round-2 rules. Each rule alone, one test per
new or changed scenario of specs/validator-admission, judge-panels, judge-scores and check-pricing; D6's real TEE
types and the cap's start following their number; each switch changes only what it names; the new actors act as
configured beside their honest twins; D17's round-2 judging ("doesn't gain"); `V2R1` reproduces round 1's numbers;
and `python3 -m pof.sim market validators` (round 2's report, reports/open-validators-v3.md)."""

import contextlib
import copy
import io
import random
import re
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pof.sim import __main__ as cli
from pof.sim.openval import actors as A
from pof.sim.openval import levels as L
from pof.sim.openval import pricing as PR
from pof.sim.openval import round2 as RM
from pof.sim.openval import scores as S
from pof.sim.openval.net import CONSTITUTION, COUNTED, Act, FlatFee, Honest, Net
from pof.sim.openval.params import DAY, V1, V2, V2R1, V2R2, WORLD, r2_fields
from pof.sim.openval.registry import ACTIVE

ROOT = Path(__file__).resolve().parent.parent
P = V2R2
NO_AUDIT = replace(P, AUDIT_RATE=0.0)
TEES = ("nitro", "tdx", "sev-snp")
FAMS = ("anthropic", "openai", "google", "open-weight")
QUIET = replace(WORLD, weeks=3, subs_week=0.0, joins_week=0.0, volunteer_per_day=0.0, reliability=1.0,
                accuracy=1.0)


def net(initial=0, p=NO_AUDIT, w=QUIET, actors=(), **kw):
    return Net(1, p, replace(w, initial_active=initial, **kw), actors)


def add(n, i, bond=1250.0, active=True, behaviour=None, tee=None):
    v = n.reg.register(n.t, key=f"x{i}", signer=f"x{i}", bond=bond, proof=tee or TEES[i % 3], host=f"xh{i}",
                       family=FAMS[(i + 1) % 4], operator=f"xop{i}", behaviour=behaviour)
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


class ShadowWithhold(Honest):
    def shadow(self, n, sub, v):
        return Act(False, True)


class Contrary(Honest):
    def audit(self, n, sub, v):
        return Act(True, True, not sub.verdict)


class Periods(FlatFee):
    """The flat fee, recording each period's counts."""

    def __init__(self):
        super().__init__(0.05)
        self.periods = []

    def end_period(self, net, period):
        self.periods.append(dict(period))


def fake_net(validators, stalled=(), t=24.0):
    reg = SimpleNamespace(validators={v.vid: v for v in validators})
    return SimpleNamespace(reg=reg, stalled=list(stalled), subs={}, period_drawn=set(), t=t)


def entries(n_ok, n_bad, t=0.0, outcome=True):
    return [(t, True, outcome)] * n_ok + [(t, False, outcome)] * n_bad


def scores(p=P):
    n = Net(1, p, QUIET)
    return n, S.install(n)


# ---------- check-pricing: every wait counts, once ----------

class TestPricing(unittest.TestCase):
    def test_every_wait_raises_the_fee_whatever_its_bounty(self):
        vs = [SimpleNamespace(vid=i, family="anthropic", state=ACTIVE) for i in range(4)]
        for p, rises in ((P, True), (RM.SW["wait_floor"].p, False)):
            m = PR.Market(p, WORLD, PR.MARKET, 1)
            m.fee_now = 0.10
            nt = fake_net(vs)
            nt.period_drawn = {0, 1, 2, 3}
            m.end_period(nt, Counter(submitted=20, waited=2, waited_floor=0, waited_any=2))  # two $500 bounties
            self.assertEqual(m.fee_now > 0.10, rises, p.WAIT_SIGNAL)

    def test_a_submission_counts_once_in_the_period_it_starts_waiting(self):
        fee = Periods()
        n = Net(1, NO_AUDIT, replace(QUIET, weeks=1, initial_active=0), fee=fee)
        sub = n.submit(1.0, 400.0, True, "s", None)  # nobody bonded for it: it waits all week
        n.run()
        self.assertTrue(sub.waited)
        self.assertEqual([x.get("waited", 0) for x in fee.periods][:6], [1, 0, 0, 0, 0, 0])

    def test_a_stalled_counted_panel_counts_once(self):
        vs = [SimpleNamespace(vid=i, family="anthropic", state=ACTIVE) for i in range(4)]
        panel = SimpleNamespace(role=COUNTED, sub=SimpleNamespace(sid=5, bounty=400.0))
        m = PR.Market(P, WORLD, PR.MARKET, 1)
        m.end_period(fake_net(vs, [panel]), Counter(submitted=10))
        m.end_period(fake_net(vs, [panel]), Counter(submitted=10))
        self.assertEqual([round(x["waited"], 3) for x in m.series], [0.1, 0.0])


# ---------- validator-admission and judge-panels: slashes, the constitution, two audits, held shadows ----------

class TestSlashes(unittest.TestCase):
    def test_silence_and_withholding_cost_5_flat_whatever_the_bond(self):
        for beh, key in ((Mute(), "silent"), (Withhold(), "withheld")):
            for bond in (250.0, 1250.0):
                with self.subTest(key=key, bond=bond):
                    n = net(initial=2)
                    v = add(n, 9, bond=bond, behaviour=beh)
                    for i in range(12):
                        n.submit(1.0 + i, 40.0, True, f"s{i}", None)
                    n.run()
                    self.assertGreater(n.stats[key], 0)
                    self.assertAlmostEqual(v.acct.slashed, 5.0 * n.stats[key])
                    self.assertTrue(all(k == c for k, c in n.k_seen))  # replaced: k never shrinks

    def test_round_1_slashed_withholding_1_and_silence_nothing(self):
        for beh, cost in ((Mute(), 0.0), (Withhold(), 1.0)):
            n = net(initial=2, p=replace(V2R1, AUDIT_RATE=0.0))
            v = add(n, 9, behaviour=beh)
            for i in range(12):
                n.submit(1.0 + i, 40.0, True, f"s{i}", None)
            n.run()
            self.assertAlmostEqual(v.acct.slashed, cost * (n.stats["silent"] + n.stats["withheld"]))

    def test_a_shadow_isnt_slashed(self):
        n = net(initial=0, w=replace(QUIET, weeks=2))
        cs = [add(n, i, active=False, behaviour=ShadowWithhold()) for i in range(4)]
        n.submit(1.0, 400.0, True, "s", None)  # it waits; candidates shadow it and withhold
        n.run()
        self.assertEqual(sum(c.acct.slashed for c in cs), 0.0)


class TestConstitution(unittest.TestCase):
    def test_adding_adrs_need_21_eligible_and_removals_14(self):
        n = net(initial=15)  # 16 eligible
        adding = n.submit(1.0, 0.0, False, "a", None, tier=CONSTITUTION)
        escalated = n.submit(1.0, 0.0, False, "e", None, tier=CONSTITUTION)
        escalated.escalated = True
        removal = n.submit(1.0, 0.0, False, "r", None, tier=CONSTITUTION)
        removal.removal = "sev-snp"
        n.run()
        self.assertEqual((adding.state, escalated.state), ("expired", "expired"))
        self.assertEqual(removal.k, P.K_MAX)
        self.assertGreaterEqual(len(removal.draw.pool), P.REMOVAL_MIN_ELIGIBLE)
        small = net(initial=12)  # 13 eligible: the removal expires too
        rem = small.submit(1.0, 0.0, False, "r", None, tier=CONSTITUTION)
        rem.removal = "sev-snp"
        small.run()
        self.assertEqual(rem.state, "expired")
        big = net(initial=20)  # 21 eligible: the adding ADR is drawn
        adr = big.submit(1.0, 0.0, False, "a", None, tier=CONSTITUTION)
        big.run()
        self.assertEqual(adr.k, P.K_MAX)
        self.assertEqual(P.constitution_min(False), 21)
        self.assertEqual(V2R1.constitution_min(False), V2R1.constitution_min(True))  # round 1: 14 for every ADR

    def test_the_deposit_is_forfeited_to_the_pool_when_rejected_and_refunded_otherwise(self):
        n = net(initial=21)
        bad = n.submit(1.0, 0.0, False, "coal", "coal", tier=CONSTITUTION)  # rejected (judges are right)
        good = n.submit(1.0, 0.0, True, "auth", "auth", tier=CONSTITUTION)  # passes
        n.run()
        self.assertEqual((bad.final, good.final), (False, True))
        pc, pa = n.parties["coal"], n.parties["auth"]
        self.assertEqual((pc.deposits, pc.forfeited, pa.deposits, pa.forfeited), (15.0, 15.0, 15.0, 0.0))
        self.assertAlmostEqual(pc.costs, n.w.attempt_fee + bad.charges + 15.0)
        self.assertAlmostEqual(pa.costs, n.w.attempt_fee + good.charges)  # refunded when it takes effect
        self.assertEqual(n.stats["deposits_forfeited"], 15.0)  # the sponsors' pool
        small = net(initial=5)
        exp = small.submit(1.0, 0.0, False, "coal", "coal", tier=CONSTITUTION)
        small.run()
        self.assertEqual(exp.state, "expired")
        self.assertAlmostEqual(small.parties["coal"].costs, small.w.attempt_fee)  # refunded when it expires

    def test_an_escalated_fixs_forfeit_never_goes_to_its_funder(self):
        for p, back in ((NO_AUDIT, 0.0), (replace(RM.SW["forfeit_funder"].p, AUDIT_RATE=0.0), 15.0)):
            n = net(initial=21, p=p)
            fix = n.submit(1.0, 0.0, False, "coal", "coal", tier=CONSTITUTION)
            fix.escalated, fix.funder_party = True, "coal"
            n.run()
            self.assertFalse(fix.final)
            self.assertEqual(n.parties["coal"].gains, back)
            self.assertEqual(n.stats["deposits_forfeited"], 15.0 - back)


class TestAudits(unittest.TestCase):
    def test_every_k1_verdict_is_audited_twice_by_different_validators(self):
        n = Net(1, NO_AUDIT, replace(QUIET, weeks=2), [At(3, lambda n: add(n, 0)), At(6, lambda n: add(n, 1))])
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.k, 1)
        self.assertEqual(len(set(sub.auditors)), 2)
        self.assertFalse(set(sub.auditors) & sub.draw.drawn)
        self.assertEqual(n.stats["audits"], 2)
        one = Net(1, replace(RM.SW["k1_audits_1"].p, AUDIT_RATE=0.0), replace(QUIET, weeks=2),
                  [At(3, lambda n: add(n, 0)), At(6, lambda n: add(n, 1))])
        s1 = one.submit(1.0, 40.0, True, "alice", None)
        one.run()
        self.assertEqual(len(s1.auditors), 1)

    def test_a_mismatch_from_the_second_auditor_opens_a_challenge(self):
        n = Net(1, NO_AUDIT, replace(QUIET, weeks=2),
                [At(3, lambda n: add(n, 0)), At(6, lambda n: add(n, 1, behaviour=Contrary()))])
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(len(sub.auditors), 2)
        self.assertEqual(n.stats["challenges_audit"], 1)


class MissOnce(Honest):
    """An auditor whose re-run wrongly agrees, once per submission (it still finds a fabricated receipt)."""

    def __init__(self):
        self.done = set()

    def audit(self, n, sub, v):
        if sub.sid not in self.done:
            self.done.add(sub.sid)
            return Act(True, True, bool(sub.verdict), found=n.rerun_found(sub, v.vid))
        return super().audit(n, sub, v)


class TestOneAuditorMisses(unittest.TestCase):
    def run_it(self, p):
        miss = MissOnce()
        w = replace(QUIET, weeks=4, rerun_detect=1.0)
        n = Net(1, replace(p, AUDIT_RATE=0.0), w, [At(3, lambda n: [add(n, i, behaviour=miss) for i in range(5)])])
        n.reg.validators[1].behaviour = A.Colluder("p")  # the genesis passes its accomplice's bad fix
        sub = n.submit(1.0, 40.0, False, "accomplice", "p")
        n.run()
        return n, sub

    def test_the_second_auditors_mismatch_opens_a_challenge_before_payment(self):
        n, sub = self.run_it(P)
        self.assertEqual((sub.k, len(sub.auditors)), (1, 2))
        self.assertGreater(n.stats["challenges_queued"], 0)  # filed while the first auditor's was judged
        self.assertTrue(sub.reversed)
        self.assertEqual(n.parties["p"].paid, 0)
        n1, sub1 = self.run_it(RM.SW["k1_audits_1"].p)  # one audit: the miss stands, and the bad fix is paid
        self.assertFalse(sub1.reversed)
        self.assertEqual(n1.parties["p"].bad_paid, 1)


class TestShadows(unittest.TestCase):
    def test_a_held_k1_verdicts_shadows_are_scored_once_by_the_sealed_majority(self):
        n = Net(1, NO_AUDIT, replace(QUIET, weeks=4), [At(5, lambda n: [add(n, i) for i in range(3)])])
        cs = [add(n, 10 + i, active=False) for i in range(3)]
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertTrue(sub.was_held and sub.shadows_scored and sub.final)
        self.assertEqual(sum(c.shadow_n for c in cs), len(sub.shadows))  # once, at the reveal; not again at finality


# ---------- judge-scores: the balanced score, recovery on fresh blocks ----------

class TestScores(unittest.TestCase):
    def test_an_always_pass_judge_scores_50(self):
        always_pass = entries(78, 0, outcome=True) + entries(0, 22, outcome=False)
        self.assertAlmostEqual(S.agreement(always_pass, P), 0.5)
        self.assertAlmostEqual(S.agreement(always_pass, RM.SW["plain"].p), 0.78)

    def test_recovery_on_fresh_blocks_each_judged_once(self):
        n, sc = scores()
        n.family_outcomes["f"] = entries(30, 20)
        self.assertFalse(sc.ok("f"))  # 60 % over 50 counted verdicts: barred
        n.family_shadow_outcomes["f"] = entries(79, 21, t=1.0)  # a block at 79 %: under 80 %
        self.assertFalse(sc.ok("f"))
        n.family_shadow_outcomes["f"] = n.family_shadow_outcomes["f"] + entries(50, 0, t=2.0)  # half a block
        self.assertFalse(sc.ok("f"))  # the first block isn't judged again; the second isn't complete
        self.assertEqual(sc.fam["f"].blocks, 1)
        n.family_shadow_outcomes["f"] = n.family_shadow_outcomes["f"] + entries(30, 20, t=3.0)  # block 2: 80 %
        self.assertTrue(sc.ok("f"))
        self.assertEqual((sc.fam["f"].blocks, sc.fam["f"].recoveries), (2, 1))
        r1, sc1 = scores(V2R1)  # round 1: the last 50 at 70 %, at each check
        r1.family_outcomes["f"] = entries(30, 20)
        self.assertFalse(sc1.ok("f"))
        r1.family_shadow_outcomes["f"] = entries(79, 21, t=1.0) + entries(50, 0, t=2.0)
        self.assertTrue(sc1.ok("f"))

    def test_only_one_kind_of_outcome(self):
        self.assertAlmostEqual(S.agreement(entries(9, 1, outcome=True), P), 0.9)

    def test_a_weak_models_lucky_streak(self):
        """50 shadow verdicts at 74 % inside a block of 100 at 71 %: it stays barred."""
        n, sc = scores()
        n.family_outcomes["f"] = entries(30, 20)
        self.assertFalse(sc.ok("f"))
        n.family_shadow_outcomes["f"] = entries(34, 16, t=1.0) + entries(37, 13, t=2.0)
        self.assertFalse(sc.ok("f"))
        self.assertEqual(sc.fam["f"].blocks, 1)

    def test_a_model_that_gets_better(self):
        """A block at 85 %: drawn again, paid the minimum factor until 50 new counted verdicts."""
        n, sc = scores()
        n.family_outcomes["f"] = entries(30, 20)
        self.assertFalse(sc.ok("f"))
        n.family_shadow_outcomes["f"] = entries(85, 15, t=1.0)
        self.assertTrue(sc.ok("f"))
        self.assertEqual(sc.factor("f"), P.SCORE_FACTOR_MIN)
        n.family_outcomes["f"] = n.family_outcomes["f"] + entries(45, 5, t=2.0)
        self.assertGreater(sc.factor("f"), P.SCORE_FACTOR_MIN)

    def test_a_block_of_200_at_75(self):
        n, sc = scores(RM.SW["block_200"].p)
        n.family_outcomes["f"] = entries(30, 20)
        self.assertFalse(sc.ok("f"))
        n.family_shadow_outcomes["f"] = entries(150, 50, t=1.0)  # 75 %
        self.assertTrue(sc.ok("f"))


# ---------- D6's TEE types (task 7.2) ----------

class TestTeeTypes(unittest.TestCase):
    def test_the_caps_start_follows_the_number_of_accepted_types(self):
        n3 = Net(1, P, replace(QUIET, weeks=0))
        self.assertEqual((len(n3.tee_list), n3.dp.tee_cap(3)), (3, 3))  # three: no TEE cap at k = 3
        n5 = Net(1, P, replace(RM.W5, weeks=0, subs_week=0.0, joins_week=0.0))
        self.assertEqual((len(n5.tee_list), n5.dp.tee_cap(3), n5.dp.tee_cap(5)), (5, 1, 2))
        self.assertTrue(n5.remove_tee("ibm-se"))  # four left: from k = 5 again
        self.assertEqual(n5.dp.tee_cap(3), 3)
        self.assertEqual(Net(1, V2R1, replace(RM.W5, weeks=0)).dp.tee_cap(3), 3)  # round 1: from k = 5 always
        one = Net(1, P, replace(QUIET, weeks=0, tees=("tdx",)))
        self.assertFalse(one.remove_tee("tdx"))  # never the last accepted type
        self.assertEqual(one.tee_list, ["tdx"])

    def test_five_types_one_vendors_two_types_and_a_panel_of_3(self):
        from pof.sim.openval import panels as D
        n = Net(1, P, replace(RM.W5, weeks=0, subs_week=0.0, joins_week=0.0))
        vs = [add(n, 20 + i, tee=t) for i, t in enumerate(("tdx", "tdx", "sgx"))]
        self.assertFalse(D.fits(vs[:1], vs[1], 3, n.dp))  # five types: no two of one type in a panel of 3
        self.assertTrue(D.fits(vs[:1], vs[2], 3, n.dp))  # SGX and TDX: two types, though one vendor
        self.assertTrue(D.fits(vs[:1], vs[1], 3, Net(1, P, replace(QUIET, weeks=0)).dp))  # three types: allowed

    def test_a_removal_adr_takes_effect_after_its_window(self):
        w = replace(QUIET, tees=RM.TEES5, initial_active=14, weeks=3)
        n = Net(1, NO_AUDIT, w)
        adr = n.submit(1.0, 0.0, True, "author", None, tier=CONSTITUTION)  # a justified removal: it passes
        adr.removal = "ibm-se"
        n.run()
        self.assertTrue(adr.final)
        self.assertAlmostEqual(adr.final_t - adr.verdict_t, P.REMOVAL_WINDOW_H)
        self.assertNotIn("ibm-se", n.tee_list)
        self.assertEqual(n.dp.tee_cap(3), 3)
        self.assertGreater(n.stats["stopped_drawn"], 0)
        probe = n.submit(n.t, 40.0, True, "z", None)
        self.assertTrue(n.eligible(probe))
        self.assertFalse([v for v in n.eligible(probe) if v.tee == "ibm-se"])

    def test_a_levelnets_removal_moves_the_cap_too(self):
        n = L.LevelNet(1, P, replace(RM.W5, weeks=1, subs_week=0.0, joins_week=0.0), ())
        self.assertEqual(n.dp.tee_cap(3), 1)
        n.adr("remove_tee", "sgx")
        n.run()
        self.assertEqual(n.dp.tee_cap(3), 3)

    def test_newcomers_spread_evenly_or_skewed(self):
        rng = random.Random(1)
        picks = Counter(RM.W3_SKEW.pick_tee(rng) for _ in range(4000))
        self.assertAlmostEqual(picks["tdx"] / 4000, 0.4, delta=0.03)
        self.assertAlmostEqual(picks["nitro"] / 4000, 0.2, delta=0.03)
        a, b = random.Random(5), random.Random(5)
        self.assertEqual([WORLD.pick_tee(a) for _ in range(20)], [b.choice(WORLD.tees) for _ in range(20)])
        self.assertEqual(set(RM.TEES5), {"nitro", "tdx", "sev-snp", "sgx", "ibm-se"})


# ---------- the switches (7.3) ----------

class TestSwitches(unittest.TestCase):
    def test_each_switch_changes_only_what_it_names(self):
        for s in RM.SWITCHES + RM.R1_SWITCHES:
            with self.subTest(s.key):
                changed, wf = RM.switch_fields(s), RM.world_fields(s)
                self.assertTrue(changed or wf)
                self.assertLessEqual(set(changed), set(s.names))
                self.assertLessEqual(set(wf), {"tees", "tee_weights"})

    def test_v2r1_is_round_1_as_a_whole(self):
        self.assertEqual(set(RM.switch_fields(RM.SW["v2r1"])), set(r2_fields()))
        self.assertEqual(set(r2_fields()), {
            "WAIT_SIGNAL", "SEALED_NO_REVEAL_SLASH", "SILENCE_SLASH", "CONSTITUTION_MIN_ELIGIBLE", "ADR_DEPOSIT",
            "K1_AUDITS", "SCORE_BALANCED", "SCORE_RECOVERY", "SCORE_RECOVER_VERDICTS", "SCORE_RECOVER_MARGIN",
            "TEE_CAP_K3_TYPES"})  # REMOVAL_MIN_ELIGIBLE: 14 in both rounds (round 1 drew every ADR from 14)
        self.assertIs(V2, V2R1)
        self.assertEqual(P, V2R2)

    def test_the_measured_room_for_answer_shopping(self):
        q = RM.Q125
        self.assertAlmostEqual(1 - (1 - q) ** 5 - q, 0.035, places=6)
        self.assertAlmostEqual(1 - 0.9 ** 5 - 0.1, 0.31, places=2)  # the 1-in-10 assumption: +31 points


# ---------- the new actors beside their twins (7.3) ----------

class TestNewActors(unittest.TestCase):
    def test_the_silent_judge_and_the_withholder_pay_5_a_bribed_miss(self):
        for sealed in (False, True):
            w = replace(A.SilentJudge().world(), weeks=12, reliability=1.0)
            a = A.run(A.SilentJudge(sealed=sealed), 1, p=P, w=w)
            t = A.run(A.SilentJudge(True, sealed=sealed), 1, p=P, w=w)
            me, twin = a.party_validators("silent")[0], t.party_validators("silent")[0]
            self.assertGreater(a.stats["silences"], 0)
            self.assertAlmostEqual(me.acct.slashed, 5.0 * a.stats["silences"])
            self.assertEqual((t.stats["silences"], twin.acct.slashed), (0, 0.0))
            self.assertTrue(all(k == c for k, c in a.k_seen))

    def test_the_coalition_of_removals_acts_and_its_twin_doesnt(self):
        w = replace(WORLD, initial_active=14, joins_week=0.0, weeks=6)
        a, t = A.RemovalCoalition(), A.RemovalCoalition(True)
        na, nt = A.run(a, 1, p=P, w=w), A.run(t, 1, p=P, w=w)
        mine = [s for s in na.subs.values() if s.party == a.party]
        self.assertTrue(mine)
        self.assertTrue(all(s.tier == CONSTITUTION and s.removal == a.tgt for s in mine))
        self.assertEqual(a.tgt, WORLD.tees[0])
        self.assertTrue(all(v.tee != a.tgt for v in na.party_validators(a.party)))
        self.assertFalse([s for s in nt.subs.values() if s.party == t.party])
        rejected = sum(1 for s in mine if s.final is False)
        self.assertEqual(na.parties[a.party].forfeited, 15.0 * rejected)
        self.assertEqual(A.RemovalCoalition().pick_target(RM.W3_SKEW), "tdx")

    def test_an_escalated_fix_posts_the_deposit(self):
        w = replace(WORLD, initial_active=21, joins_week=0.0, weeks=4)
        a = A.ConstitutionCoalition(kind="escalated")
        n = A.run(a, 1, p=P, w=w)
        mine = [s for s in n.subs.values() if s.party == a.party]
        self.assertTrue(mine and all(s.escalated and s.funder_party == a.party and s.deposit == 15.0 for s in mine))


# ---------- D17, round 2 (7.4) ----------

class TestJudging(unittest.TestCase):
    def test_doesnt_gain_follows_its_numbers(self):
        self.assertTrue(RM.doesnt_gain(-1.0, 3.5))  # −$1 ± 7: upper bound +$6, within $10
        self.assertFalse(RM.doesnt_gain(-34.0, 23.5))  # −$34 ± 47: upper bound +$13
        self.assertFalse(RM.doesnt_gain(3.0, 1.0))  # +$3 ± 2: a positive mean
        self.assertFalse(RM.loses(-1.0, 3.5))  # round 1's "loses" can't pass it
        self.assertTrue(RM.doesnt_gain(-137.0, 32.0) and RM.loses(-137.0, 32.0))  # losing is not gaining
        self.assertFalse(RM.doesnt_gain(float("nan"), 0.0))
        ok, why, note = RM.rows_dont_gain([("a", -1.0, 3.5), ("b", -100.0, 10.0)])
        self.assertTrue(ok)
        self.assertEqual(note, "1 of 2 lose")
        ok, why, _ = RM.rows_dont_gain([("a", -1.0, 3.5), ("c", 3.0, 1.0)])
        self.assertFalse(ok)
        self.assertIn("c (+3.0 ± 2.0 $)", why)


# ---------- V2R1 reproduces round 1's numbers (seed 1, captured on main before round 2) ----------

class TestV2R1Reproduces(unittest.TestCase):
    def test_round_1s_rules_reproduce_round_1s_numbers(self):
        n = Net(1, V2R1, WORLD).run()
        st = {k: n.stats[k] for k in ("submitted", "waited", "drawn", "final", "paid", "bad_merged", "qualified",
                                      "reversed", "challenges", "withdrawn", "stepped_down", "audits", "held")}
        self.assertEqual(st, {"submitted": 1566, "waited": 286, "drawn": 1358, "final": 1357, "paid": 1007,
                              "bad_merged": 6, "qualified": 57, "reversed": 4, "challenges": 29, "withdrawn": 208,
                              "stepped_down": 376, "audits": 163, "held": 11})
        self.assertAlmostEqual(sum(n.validator_net(v) for v in n.reg.validators.values()), -2065.177086, places=4)
        self.assertAlmostEqual(A.against_twin(lambda h: A.LoneColluder(h), [1], p=V2R1)["diff"], -327.684604,
                               places=4)
        self.assertAlmostEqual(A.against_twin(lambda h: A.SilentJudge(h), [1], p=V2R1)["diff"], 313.7636, places=4)
        self.assertAlmostEqual(A.against_twin(lambda h: A.ConstitutionCoalition(h), [1], p=V2R1)["diff"], 1924.1574,
                               places=4)


# ---------- the command and the report (7.5, 7.6) ----------

CRITERIA = ("open-validator attacker doesn't gain", "pricing attacker doesn't gain", "proof-level attacker doesn't gain",
            "scoring attacker", "a sybil at or under", "a sybil above the share", "colluding lone validator",
            "constitution waits", "fee settles", "crowds into one model", "network still grows", "answer shopping",
            "every earlier criterion", "adopt the k table")
VERDICT = re.compile(r"\*\*(met|not met)\*\*")


def acceptance_rows(text):
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        for phrase in CRITERIA:
            if phrase in cells[0].lower() and phrase not in rows:
                m = VERDICT.search(cells[1])
                if m:
                    rows[phrase] = (m.group(1), cells[3])
    return rows


class TheCommand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = RM.quick_collect()  # shared with tests/test_openval_r3.py; copied before any change
        cls.out = RM.render(cls.d)

    def test_the_command_prints_round_2s_report(self):
        out = io.StringIO()
        with mock.patch.object(RM, "full_report", lambda *a, **k: "ROUND-2 REPORT"), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["market", "validators", "--seeds", "1", "--quick"]), 0)
        self.assertEqual(out.getvalue(), "ROUND-2 REPORT\n")

    def test_it_names_each_criterion_met_or_not(self):
        self.assertIn("# Open validators, v3", self.out)
        rows = acceptance_rows(self.out)
        self.assertEqual(set(rows), set(CRITERIA))
        others = [v for k, (v, _) in rows.items() if k != "adopt the k table"]
        self.assertEqual(rows["adopt the k table"][0], "not met" if "not met" in others else "met")
        for heading in ("An honest network grows under the hold", "The TEE cap and the number of TEE types",
                        "with two audits", "A bribed silent judge and a bribed withholder", "An early coalition",
                        "A coalition of removals", "An honest validator's month", "Herding", "Acceptance criteria"):
            self.assertIn(heading, self.out)

    def test_the_tables_verdicts_follow_the_criteria_numbers(self):
        crit = RM.acceptance(self.d)
        rows = RM.counted_rows(self.d)
        for c, key in zip(crit[:4], ("open", "pricing", "levels", "scores")):
            self.assertEqual(c.met, bool(rows[key]) and all(RM.doesnt_gain(m, se) for _, m, se in rows[key]))
        d = copy.deepcopy(self.d)
        r = d["silent"][0][2]
        r["diff"], r["se"] = 3.0, 1.0  # +$3 ± 2: it gains
        self.assertFalse(RM.acceptance(d)[0].met)
        r["diff"], r["se"] = -1.0, 3.5  # −$1 ± 7: it doesn't
        self.assertEqual(RM.acceptance(d)[0].met, crit[0].met)
        d = copy.deepcopy(self.d)
        d["constitution"][0][2]["below_need"] = 1.0  # an adding ADR passed below 21
        self.assertFalse(next(c for c in RM.acceptance(d) if "constitution waits" in c.name).met)
        d = copy.deepcopy(self.d)
        d["pricing"]["settle"][0][1]["collapsed"][0] = 1  # a run collapsed
        self.assertFalse(next(c for c in RM.acceptance(d) if "fee settles" in c.name).met)
        d = copy.deepcopy(self.d)
        m = d["colluder"][0][2]
        m["reversed"], m["resolved"] = [8], [10]  # 80 % reversed
        self.assertFalse(next(c for c in RM.acceptance(d) if "colluding lone" in c.name).met)

    def test_its_numbers_are_reproducible_on_fixed_seeds(self):
        a = RM._section("silent", (1,), (1,), True)
        self.assertEqual(repr(a), repr(RM._section("silent", (1,), (1,), True)))
        self.assertIn(RM.md_silent(a, [1]).splitlines()[4], self.out)


class TheReport(unittest.TestCase):
    REPORT = ROOT / "reports" / "open-validators-v3.md"

    def test_the_report_names_each_criterion_met_or_not(self):
        if not self.REPORT.exists():
            self.skipTest("reports/open-validators-v3.md not written yet")
        rows = acceptance_rows(self.REPORT.read_text(encoding="utf-8"))
        self.assertEqual(set(rows), set(CRITERIA))
        for phrase in CRITERIA[:4]:  # "doesn't gain": the verdict follows the rows named
            verdict, decides = rows[phrase]
            self.assertEqual(verdict, "met" if decides.startswith("none of") else "not met", phrase)

    def test_round_1s_numbers_quoted_beside_the_rows_are_round_1s(self):
        v2 = (ROOT / "reports" / "open-validators-v2.md").read_text(encoding="utf-8")
        for key, text in RM.R1_PUBLISHED.items():
            with self.subTest(key):
                self.assertIn(text, v2)


if __name__ == "__main__":
    unittest.main()
