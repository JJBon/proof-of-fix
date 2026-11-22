"""#134 task 1.5 (pof/sim/openval/levels.py): proof levels. One test per proof-level scenario of #132's
specs/validator-admission, specs/judge-panels and specs/incentive-simulation, and each level attacker alone and
against its twin."""

import contextlib
import io
import unittest
from dataclasses import replace
from unittest import mock

from pof.sim.openval import levels as L
from pof.sim.openval import report as R
from pof.sim.openval.net import Net, Sub
from pof.sim.openval.params import DAY, WORLD
from pof.sim.openval.params import V1 as PARAMS  # #134's rules: these tests keep them reachable (#141)
from pof.sim.openval.registry import ACTIVE, CANDIDATE, RegistrationError, Registry

P = PARAMS
NO_AUDIT = replace(P, AUDIT_RATE=0.0)
QUIET = replace(WORLD, weeks=3, subs_week=0.0, joins_week=0.0, volunteer_per_day=0.0, reliability=1.0,
                accuracy=1.0)
FAMS = ("openai", "google", "open-weight", "anthropic")
A_TEES = ("tdx", "sev-snp", "nitro")  # confidential VMs in a cloud (with the platform's attestation) are level A


class At(L.LevelActor):
    """A test actor: runs `fn(net)` once, at the first tick on or after `day`."""
    party = "test"

    def __init__(self, day, fn):
        super().__init__()
        self.day, self.fn, self.done = day, fn, False

    def genesis(self, n):
        return None

    def on_tick(self, n):
        if not self.done and n.t >= self.day * DAY:
            self.done = True
            self.fn(n)


def lnet(genesis="A", p=NO_AUDIT, w=QUIET, actors=(), **lw):
    return L.LevelNet(1, p, w, actors, lw=replace(L.LEVEL_WORLD, genesis_level=genesis, **lw))


def add(n, levels, start=1, active=True, bond=1250.0):
    """Validators at `levels`, on distinct hosts and spread over families and TEE types."""
    out = []
    for j, lv in enumerate(levels, start):
        tee = A_TEES[j % 3] if lv == "A" else L.HOME_TEES[j % 2]
        out.append(n.register_level(f"v{j}", bond, lv, f"h{j}", FAMS[j % 4], f"op{j}", tee=tee, active=active))
    return out


def sub(n, bounty=10.0):
    return Sub(99, n.t, bounty, True, "s", frozenset({"s"}))


# ---------- specs/validator-admission ----------

class TestLevelsAtRegistration(unittest.TestCase):
    def test_a_confidential_vm_in_a_cloud_is_level_a(self):
        v = Registry().register(0.0, key="vm", signer="vm", bond=100, proof="tdx", host="gcp", family="google",
                                operator="o", cloud_attested=True)
        self.assertEqual((v.level, v.public()["level"]), ("A", "A"))
        n = lnet()
        self.assertEqual(n.register_level("x", 100, "A", "aws", "openai", "ox", tee="nitro").level, "A")

    def test_a_tee_server_at_home_is_level_b(self):
        v = Registry().register(0.0, key="srv", signer="srv", bond=100, proof="sev-snp", host="home",
                                family="openai", operator="o", cloud_attested=False)
        self.assertEqual((v.level, v.tee), ("B", "sev-snp"))
        n = lnet()
        self.assertEqual(n.register_level("x", 100, "B", "home", "openai", "ox", tee="tdx").level, "B")

    def test_an_ordinary_pc_is_level_c(self):
        n = lnet()
        v = n.register_level("pc", 100, "C", "home", "open-weight", "o")
        self.assertEqual((v.level, v.proof, v.tee, v.attestation), ("C", "zktls", "none", None))

    def test_a_validator_on_ordinary_hardware_qualifies_by_the_same_rules(self):
        """A zkTLS candidate shadow-judges the genesis validator's panels and becomes active at QUALIFY_VERDICTS."""
        n = lnet()
        pc = n.register_level("pc", 100, "C", "home", "open-weight", "o")
        for i in range(P.QUALIFY_VERDICTS + 2):
            n.submit(1.0 + i, 10.0, i % 4 != 0, f"s{i}", None)
        n.run()
        self.assertEqual((pc.state, pc.level), (ACTIVE, "C"))
        self.assertEqual(pc.activations, 1)

    def test_a_notary_that_isnt_listed(self):
        """Registering with an unlisted notary is refused; a verdict proven by one doesn't count: the judge is
        treated as not having revealed and the next validator replaces it."""
        n = lnet(genesis="C")
        with self.assertRaises(RegistrationError):
            n.register_level("pc", 100, "C", "home", "google", "o", notary="rogue")
        g = n.reg.validators[1]
        n.attest(g).notary = "rogue"  # its proofs now come from a notary that isn't on the list
        late = []
        n.actors.append(At(1, lambda net: late.extend(add(net, ["C"]))))
        s = n.submit(1.0, 5.0, True, "alice", None)
        n.run()
        self.assertEqual([vid for vid, _, _ in s.judges], [late[0].vid])
        self.assertEqual(s.replaced, 1)
        self.assertGreater(g.acct.slashed, 0)  # "treated as not having revealed"
        self.assertEqual(s.final, True)

    def test_a_listed_notary_removed_by_adr_stops_counting_after_the_short_window(self):
        n = lnet()
        eff = n.adr("remove_notary", "notary-1")
        self.assertEqual(eff, n.lp.REMOVAL_WINDOW_H)
        self.assertTrue(n.const.notary_ok("notary-1", eff - 1))
        self.assertFalse(n.const.notary_ok("notary-1", eff))
        self.assertTrue(n.const.notary_ok("notary-2", eff))


class TestFirmwareAndRemoval(unittest.TestCase):
    def test_a_flaw_is_patched(self):
        """An ADR raises tdx's minimum firmware: tdx validators on the old firmware are still drawn during the
        removal window, then stop being drawn, keep their bonds, and return after updating and attesting again."""
        n = lnet()
        vs = add(n, ["B", "B", "A"])  # tdx at home, sev-snp at home, a tdx confidential VM (A)
        tdx = [v for v in vs if v.proof == "tdx"]
        self.assertEqual(len(tdx), 2)
        eff = n.adr("raise_tcb", "tdx", 2)
        n.t = eff - 1
        self.assertTrue(all(v in n.eligible(sub(n)) for v in tdx))
        n.t = eff
        el = n.eligible(sub(n))
        self.assertTrue(all(v not in el for v in tdx))
        self.assertTrue(all(v.bond == 1250.0 and v.state == ACTIVE for v in tdx))
        self.assertIn(next(v for v in vs if v.proof == "sev-snp"), el)
        n.reattest(tdx[0], 2)
        self.assertIn(tdx[0], n.eligible(sub(n)))
        self.assertNotIn(tdx[1], n.eligible(sub(n)))

    def test_old_firmware_and_a_revoked_platform_are_refused_at_registration(self):
        n = lnet()
        with self.assertRaises(RegistrationError):
            n.register_level("x", 100, "B", "home", "google", "o", tee="tdx", tcb=0)
        n.const.revoked.add("chip-stolen")
        with self.assertRaises(RegistrationError):
            n.register_level("y", 100, "B", "home", "google", "o", tee="tdx", platform="chip-stolen")
        self.assertEqual(n.register_level("z", 100, "B", "home", "google", "o", tee="tdx", tcb=1).level, "B")

    def test_an_exploit_is_published_for_a_tee_type(self):
        """An ADR removes sev-snp: its validators stop being drawn after the short window, without losing their
        bonds, and may register again with an accepted type."""
        n = lnet()
        vs = add(n, ["B", "B", "A"])
        sev = [v for v in vs if v.proof == "sev-snp"]
        eff = n.adr("remove_tee", "sev-snp")
        self.assertEqual(eff, 48.0)
        n.t = eff - 1
        self.assertTrue(all(v in n.eligible(sub(n)) for v in sev))
        n.t = eff
        self.assertTrue(all(v not in n.eligible(sub(n)) and v.bond == 1250.0 for v in sev))
        with self.assertRaises(RegistrationError):
            n.register_level("again", 100, "B", "home", "google", "o2", tee="sev-snp")
        again = n.register_level("again", 100, "B", "home", "google", "o2", tee="tdx")
        self.assertEqual((again.state, again.level), (CANDIDATE, "B"))

    def test_a_new_tee_type_takes_the_full_challenge_window(self):
        n = lnet()
        eff = n.adr("add_tee", "cca")
        self.assertEqual(eff, 14 * DAY)
        n.t = eff - 1
        with self.assertRaises(RegistrationError):
            n.register_level("arm", 100, "B", "home", "google", "o", tee="cca")
        n.t = eff
        v = n.register_level("arm", 100, "B", "home", "google", "o", tee="cca")
        self.assertEqual((v.proof, v.level), ("cca", "B"))


# ---------- specs/judge-panels ----------

class TestPanelLevel(unittest.TestCase):
    def test_the_majoritys_weakest(self):
        for levels, want in ((["A"], "A"), (["C"], "C"), (["A", "B", "C"], "B"), (["C", "A", "A"], "A"),
                             (["C", "C", "A"], "C"), (["A", "A", "A", "A", "C", "C", "C"], "A"),
                             (["A", "A", "A", "B", "C", "C", "C"], "B"), (["B", "B", "C", "C", "A"], "B")):
            self.assertEqual(L.majority_weakest(levels), want, levels)

    def test_a_mixed_panel_of_3(self):
        n = lnet()
        add(n, ["B", "C"])
        s = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(sorted(n.reg.validators[v].level for v, _, _ in s.judges), ["A", "B", "C"])
        self.assertEqual((s.k, s.level), (3, "B"))
        self.assertAlmostEqual(s.final_t - s.verdict_t, P.window_h(3, "B"))

    def test_a_network_of_ordinary_pcs(self):
        """Every eligible validator at C: panels still form, at C, with C's limits and windows."""
        n = lnet(genesis="C")
        add(n, ["C"] * 6)
        ok = n.submit(1.0, 240.0, True, "alice", None)
        over = n.submit(2.0, 260.0, True, "bob", None)
        n.run()
        self.assertEqual((ok.k, ok.level, ok.final), (7, "C", True))
        self.assertAlmostEqual(ok.final_t - ok.verdict_t, P.window_h(7, "C"))
        self.assertIsNone(over.draw)
        self.assertIn(over.state, ("waiting", "withdrawn"))
        self.assertIn("the panel's proof level", n.reasons[over.sid])

    def test_a_level_c_panel_waits_longer(self):
        n = lnet(genesis="C")
        add(n, ["C", "C"])
        s = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual((s.k, s.level, s.final), (3, "C", True))
        self.assertAlmostEqual(s.final_t - s.verdict_t, 72.0)
        self.assertGreater(P.window_h(3, "C"), P.window_h(3, "A"))

    def test_a_large_level_a_panels_quick_finality(self):
        n = lnet()
        add(n, ["A"] * 6)
        s = n.submit(1.0, 600.0, True, "alice", None)
        n.run()
        self.assertEqual((s.k, s.level), (7, "A"))
        self.assertAlmostEqual(s.final_t - s.verdict_t, 6.0)

    def test_each_k_and_level_has_its_limit_and_window(self):
        """The design's table: B half of A's bounties and twice its windows; C its own; windows longer for smaller
        panels and weaker levels, limits rising (not falling) with k and with the level."""
        a, b, c = (P.BOUNTY_LIMIT[x] for x in "ABC")
        self.assertEqual(a, {1: 50, 3: 250, 5: 625, 7: 625})
        self.assertEqual(c, {1: 10, 3: 50, 5: 125, 7: 250})
        self.assertEqual(P.CHALLENGE_WINDOW_H["A"], {1: 72, 3: 24, 5: 12, 7: 6})
        self.assertEqual(P.CHALLENGE_WINDOW_H["C"], {1: 168, 3: 72, 5: 48, 7: 24})
        for k in (1, 3, 5, 7):
            self.assertEqual(b[k], a[k] / 2)
            self.assertEqual(P.window_h(k, "B"), 2 * P.window_h(k, "A"))
            self.assertTrue(P.limit(k, "A") >= P.limit(k, "B") >= P.limit(k, "C"))
            self.assertTrue(P.window_h(k, "A") < P.window_h(k, "B") < P.window_h(k, "C"))
        for lv in "ABC":
            self.assertEqual(sorted(P.BOUNTY_LIMIT[lv].values()), [P.limit(k, lv) for k in (1, 3, 5, 7)])
            self.assertEqual(sorted(P.CHALLENGE_WINDOW_H[lv].values(), reverse=True),
                             [P.window_h(k, lv) for k in (1, 3, 5, 7)])

    def test_a_panel_too_weak_for_the_bounty_waits_and_is_drawn_when_the_network_grows(self):
        """$200 at k = 3: A's limit is $250 but a panel of A, B and C is level B ($125), so it waits; with two more
        level A validators, k = 5 at level A takes it, without the solver doing anything."""
        late = []
        n = lnet(actors=[At(1, lambda net: late.extend(add(net, ["A", "A"], start=3)))])
        add(n, ["B", "C"])
        s = n.submit(1.0, 200.0, True, "alice", None)
        n.run()
        self.assertIn("the panel's proof level", n.reasons[s.sid])
        self.assertEqual((s.k, s.level, s.final), (5, "A", True))
        self.assertGreaterEqual(s.drawn_t, DAY)


class TestHiddenTests(unittest.TestCase):
    def test_a_bounty_with_hidden_tests_on_a_small_network(self):
        """Only level C validators are eligible: it waits for TEE validators, and no level C validator sees it
        (counted, shadow, auditor or challenge judge). When TEE validators qualify, it is judged by them alone."""
        tee = []

        def grow(net):
            tee.extend(add(net, ["A", "B", "A", "B"], start=10))
            tee.append(net.register_level("cand-b", 1250.0, "B", "h-cb", "google", "op-cb", tee="tdx"))

        n = lnet(genesis="C", p=replace(P, AUDIT_RATE=1.0), actors=[At(1, grow)])
        cs = add(n, ["C", "C"]) + [n.register_level("cand-c", 1250.0, "C", "h-cc", "openai", "op-cc")]
        s = n.submit(1.0, 20.0, True, "alice", None, hidden=True)
        plain = n.submit(1.5, 20.0, True, "bob", None)
        n.run()
        self.assertIn("hidden tests: no TEE validator", n.reasons[s.sid])
        self.assertIsNotNone(plain.draw)
        self.assertLess(plain.drawn_t, DAY)
        self.assertGreaterEqual(s.drawn_t, DAY)
        seen = set(s.draw.drawn) | {vid for vid, _, _ in s.shadows}
        self.assertTrue(seen)
        self.assertTrue(all(n.reg.validators[v].level in "AB" for v in seen))
        self.assertTrue(s.shadows)  # the level B candidate shadowed it; the level C one didn't
        self.assertEqual(s.audit, "agreed")
        self.assertTrue(all(v.acct.audits == 0 for v in cs + [n.reg.validators[1]]))
        self.assertEqual(s.final, True)

    def test_volunteers_cant_rerun_hidden_tests(self):
        n = lnet()
        h = n.submit(1.0, 10.0, False, "alice", None, hidden=True)
        h.verdict = True
        self.assertTrue(n.honest_vote(h, None, 5))
        self.assertEqual(n.rerun_found(h, 0), ())


# ---------- specs/incentive-simulation: the attackers ----------

class TestAttackersAct(unittest.TestCase):
    def test_a_zktls_validator_lies_about_the_tests(self):
        """judge-panels: a level C judge's receipt reports passing tests a fresh panel's re-runs don't reproduce; the
        receipt challenge is upheld, the judge slashed, and the fix reversed before payment."""
        n = lnet(genesis="C", w=replace(QUIET, volunteer_per_day=24.0, rerun_detect=1.0),
                 actors=[At(1, lambda net: add(net, ["C", "C", "C"]))])
        liar = n.reg.validators[1]
        liar.behaviour = L.Colluder("liar")
        s = n.submit(1.0, 8.0, False, "liar-solver", "liar")
        n.run()
        self.assertEqual(s.judges, [(liar.vid, True, True)])
        self.assertIsNotNone(s.challenge)
        self.assertEqual(s.challenge.receipts, (liar.vid,))
        self.assertTrue(s.reversed)
        self.assertEqual(s.final, False)
        self.assertAlmostEqual(liar.acct.slashed, WORLD.genesis_bond * P.FALSE_VERDICT_SLASH_BPS / 10_000)

    def test_the_test_liar_passes_its_solvers_fixes_with_lies_and_reruns_catch_some(self):
        a = L.TestLiar(where="grown")
        n = L.run(a, 1, p=P)
        me = a.me(n)
        self.assertEqual(me.level, "C")
        mine = [s for s in n.subs.values() if s.party == "liar" and any(v == me.vid for v, _, _ in s.judges)]
        self.assertTrue(mine)
        self.assertTrue(all(vote for s in mine for v, vote, _ in s.judges if v == me.vid))
        self.assertGreater(n.stats["receipts_upheld"], 0)
        self.assertTrue(all(s.bounty <= P.limit(s.k, "C") for s in n.subs.values() if s.draw is not None))

    def test_the_answer_shopper_flips_verdicts_with_valid_receipts(self):
        a = L.AnswerShopper(where="grown")
        n = L.run(a, 1, p=P, w=replace(a.world(), weeks=26, reliability=1.0))
        sh, me = a.shopper, a.me(n)
        self.assertGreater(len(sh.flipped), 0)
        self.assertEqual(n.stats["receipts_upheld"], 0)  # nothing for a re-run to disprove
        self.assertEqual(me.acct.slashed, 0.0)
        flipped = [n.subs[i] for i in sh.flipped]
        self.assertTrue(any(s.verdict is False for s in flipped))  # outweighed by the other judges
        self.assertTrue(all(s.sid in n.borderline and not s.good for s in flipped))
        self.assertGreaterEqual(me.acct.overhead, sh.extra_calls * n.w.usage_per_check)
        self.assertTrue(all(sum(v for _, v, _ in s.judges) >= (s.k + 1) // 2 for s in flipped if s.verdict))

    def test_the_twin_of_the_shopper_calls_once(self):
        twin = L.AnswerShopper(True, "grown", twin_submits=True)
        n = L.run(twin, 1, p=P, w=replace(twin.world(), weeks=12))
        self.assertEqual(len(twin.shopper.flipped), 0)
        self.assertTrue(any(s.party == "shopper" for s in n.subs.values()))
        self.assertIsNone(twin.me(n).behaviour)

    def test_the_chip_breaker_forges_at_its_rate_within_level_bs_limits(self):
        a = L.ChipBreaker(where="grown", break_cost=50.0)
        n = L.run(a, 2, p=P)
        me, b = a.me(n), a.breaker
        self.assertEqual((me.level, me.tee), ("B", "tdx"))
        self.assertGreater(b.forged, 0)
        others = [s for s in n.subs.values() if s.party != "breaker" and not s.good
                  and any(v == me.vid for v, _, _ in s.judges)]
        forged = sum(1 for s in others for v, _, f in s.judges if v == me.vid and f)
        self.assertAlmostEqual(forged / len(others), a.rate * n.w.accuracy, delta=0.15)
        self.assertTrue(all(s.bounty <= P.limit(s.k, s.level) for s in n.subs.values() if s.draw is not None))
        self.assertTrue(all(s.bounty <= P.limit(s.k, "B") for s in n.subs.values() if s.party == "breaker"))
        self.assertGreater(me.acct.overhead, 50.0)

    def test_the_genesis_breaker_stays_within_bs_k1_limit(self):
        a = L.ChipBreaker()
        n = L.run(a, 1, p=P, w=replace(a.world(), weeks=16))
        mine = [s for s in n.subs.values() if s.party == "breaker"]
        self.assertTrue(mine)
        self.assertTrue(all(s.bounty <= P.limit(1, "B") for s in mine))
        self.assertTrue(all(s.level == "B" for s in mine if s.draw is not None))

    def test_the_twins_see_the_same_levels_and_world(self):
        a, t = L.run(L.ChipBreaker(where="grown"), 3, p=P, w=replace(L.ChipBreaker(where="grown").world(), weeks=8)), \
            L.run(L.ChipBreaker(True, "grown"), 3, p=P, w=replace(L.ChipBreaker(where="grown").world(), weeks=8))
        honest = lambda n: [(s.sid, s.t, s.bounty, s.good) for s in n.subs.values() if s.party is None]
        lv = lambda n: [(v.key, v.level) for v in n.reg.validators.values() if v.party != "breaker"]
        self.assertEqual(honest(a), honest(t))
        self.assertEqual(lv(a), lv(t))
        self.assertEqual({x for _, x in lv(a)}, {"A", "B", "C"})


class TestAgainstTwins(unittest.TestCase):
    SEEDS = range(1, 4)

    def test_the_test_liar_loses_in_a_grown_network(self):
        r = L.against_twin(lambda h: L.TestLiar(h, "grown"), self.SEEDS, p=P)
        self.assertTrue(r["loses"], r["diff"])

    def test_the_chip_breaker_loses_in_a_grown_network(self):
        r = L.against_twin(lambda h: L.ChipBreaker(h, "grown", break_cost=50.0), self.SEEDS, p=P)
        self.assertTrue(r["loses"], r["diff"])

    def test_the_genesis_liar_gains_less_with_levels(self):
        """A finding, not a wish: as the genesis at C it still gains (like phase 1's lone colluder), but less than
        with level A's limits and windows."""
        w = replace(WORLD, weeks=26)
        lv = L.against_twin(lambda h: L.TestLiar(h), self.SEEDS, p=P, w=w)
        no = L.against_twin(lambda h: L.TestLiar(h), self.SEEDS, p=P, w=w, rule=L.ALL_A)
        self.assertGreater(lv["diff"], 0)
        self.assertGreater(no["diff"], lv["diff"])


# ---------- the network, the report and the CLI ----------

class TestNetwork(unittest.TestCase):
    def test_all_level_a_is_phase_1(self):
        """With every validator at A, the levels change nothing: the same run as phase 1's network."""
        w = replace(WORLD, weeks=12)
        a = L.LevelNet(3, P, w, lw=replace(L.LEVEL_WORLD, mix=(1.0, 0.0, 0.0))).run()
        b = Net(3, P, w).run()
        self.assertEqual(a.stats, b.stats)
        self.assertEqual(a.series, b.series)

    def test_a_mixed_network_draws_panels_at_every_level_within_their_limits(self):
        n = L.LevelNet(2, P, replace(L.MATURE, weeks=10)).run()
        drawn = [s for s in n.subs.values() if s.draw is not None]
        self.assertEqual({s.level for s in drawn}, {"A", "B", "C"})
        for s in drawn:
            self.assertEqual(s.level, L.majority_weakest([n.reg.validators[v].level for v in s.draw.panel]))
            self.assertLessEqual(s.bounty, P.limit(s.k, s.level))
            if s.final is not None and s.challenge is None:
                self.assertAlmostEqual(s.final_t - s.verdict_t, P.window_h(s.k, s.level))

    def test_the_tables_are_reproducible(self):
        w = replace(WORLD, weeks=6)
        rows = [("mixed", w, L.LEVEL_WORLD), ("hidden", w, replace(L.LEVEL_WORLD, hidden_share=0.2))]
        a = L.networks(range(1, 3), rows, p=P)
        self.assertEqual(a, L.networks(range(1, 3), rows, p=P))
        self.assertEqual(sum(a[1][1]["hidden_c_seen"]), 0)
        row = [("liar", lambda h: L.TestLiar(h, "grown"), P, L.majority_weakest, "liar")]
        x = L.attackers(range(1, 2), row)
        self.assertEqual(x[0][1]["diff"], L.attackers(range(1, 2), row)[0][1]["diff"])

    def test_the_cli_has_levels(self):
        out = io.StringIO()
        with mock.patch.object(L, "levels_report", lambda seeds: f"levels on {len(seeds)} seeds"), \
                contextlib.redirect_stdout(out):
            R.main(["levels", "--seeds", "3"])
        self.assertEqual(out.getvalue().strip(), "levels on 3 seeds")


if __name__ == "__main__":
    unittest.main()
