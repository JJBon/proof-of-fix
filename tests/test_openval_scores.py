"""#134 task 1.7 (pof/sim/openval/scores.py): per-family model scores (#132 design D14). One test per scenario of
specs/judge-scores, the rule's pieces (the window, SCORE_MIN, the neutral start, the factor's bounds), the weighted
votes the design rejects, and each new behaviour alone and against its honest twin (movers, herders)."""

import unittest
from dataclasses import replace

from pof.sim.openval import actors as A
from pof.sim.openval import scores as S
from pof.sim.openval.net import Act, Honest, Net
from pof.sim.openval.params import DAY, WORLD
from pof.sim.openval.params import V1 as PARAMS  # #134's rules: these tests keep them reachable (#141)

P = replace(PARAMS, AUDIT_RATE=0.0)
TEES = ("nitro", "tdx", "sev-snp")
# nothing happens on its own; every judge is right (accuracy 1) and online
QUIET = replace(WORLD, weeks=3, subs_week=0.0, joins_week=0.0, volunteer_per_day=0.0, reliability=1.0, accuracy=1.0,
                initial_active=0)
SMALL = replace(P, SCORE_WINDOW=40, SCORE_MIN_VERDICTS=10)  # a short window, so a test sees a family barred and back


class AlwaysPass(Honest):
    """Votes pass on every counted panel: an honest mistake (its receipt is genuine), judging honestly elsewhere."""

    def counted(self, n, sub, v):
        return Act(True, True, True)


class At(A.Actor):
    """Runs `fn(net)` once, at the first tick on or after `day`."""
    party = "test"

    def __init__(self, day, fn):
        super().__init__()
        self.day, self.fn, self.done = day, fn, False

    def on_tick(self, n):
        if not self.done and n.t >= self.day * DAY:
            self.done = True
            self.fn(n)


def add(n, i, family, behaviour=None):
    """An already-qualified validator of `family` on its own host and operator."""
    v = n.reg.register(n.t, key=f"v{i}", signer=f"v{i}", bond=1250.0, proof=TEES[i % 3], host=f"h{i}", family=family,
                       operator=f"op{i}", behaviour=behaviour)
    n.reg.seed_active(v, n.t)
    return v


def quiet(p=P, w=QUIET, actors=()):
    """A network whose genesis validator has already left, so only the validators a test adds are drawn."""
    n = Net(1, p, w, actors)
    n.leave(n.reg.validators[1])
    return n


def seeded(n, family, agree, total):
    """Record `total` past counted verdicts of `family`, `agree` of them agreeing with the outcome."""
    n.family_outcomes[family] = [(0.0, i < agree) for i in range(total)]


class TestTheRule(unittest.TestCase):
    def test_the_score_is_the_share_that_agreed_over_the_window(self):
        rec = [(float(t), t >= 100) for t in range(300)]  # 100 disagreements, then 200 agreements
        self.assertEqual(S.recompute(rec, p=P), (1.0, 200))  # only the last SCORE_WINDOW count
        self.assertEqual(S.recompute(rec[:150], p=P), (50 / 150, 150))
        self.assertEqual(S.recompute([], p=P), (None, 0))
        # shadow verdicts merge in time order
        self.assertEqual(S.recompute([(1.0, True)], [(0.5, False), (2.0, False)], p=P), (1 / 3, 3))

    def test_the_factor_is_linear_and_bounded(self):
        f = lambda s: S.factor(s, 200)
        self.assertAlmostEqual(f(0.70), 0.5)
        self.assertAlmostEqual(f(1.00), 2.0)
        self.assertAlmostEqual(f(0.80), 1.0)
        self.assertAlmostEqual(S.neutral(), 0.80)
        self.assertAlmostEqual(f(0.50), 0.5)  # bounded below (such a family isn't drawn anyway)
        self.assertEqual(S.factor(0.99, 49), 1.0)  # neutral below SCORE_MIN_VERDICTS

    def test_the_parameters_are_the_designs(self):
        self.assertEqual((P.SCORE_WINDOW, P.SCORE_MIN, P.SCORE_MIN_VERDICTS, P.SCORE_FACTOR_MIN, P.SCORE_FACTOR_MAX),
                         (200, 0.70, 50, 0.5, 2.0))


# ---------- specs/judge-scores ----------

class TestPublicScore(unittest.TestCase):
    def test_a_reversal_counts_as_the_truth(self):
        """Two judges pass a bad fix, one votes fail; a volunteer's re-run challenges it, a fresh panel reverses it:
        the fail voter's family is scored as agreeing, the pass voters' families as disagreeing."""
        def more(n):
            for i in range(10, 16):
                add(n, i, ("x", "y", "z")[i % 3])

        n = quiet(w=replace(QUIET, volunteer_per_day=50.0), actors=[At(1, more)])
        sc = S.install(n)
        add(n, 2, "honest-fam")
        add(n, 3, "pass-a", AlwaysPass())
        add(n, 4, "pass-b", AlwaysPass())
        sub = n.submit(1.0, 20.0, False, "alice", None)
        n.run()
        self.assertEqual((sub.k, sub.verdict, sub.reversed, sub.final), (3, True, True, False))
        self.assertEqual([e[1] for e in n.family_outcomes["honest-fam"]], [True])
        self.assertEqual([e[1] for e in n.family_outcomes["pass-a"]], [False])
        self.assertEqual([e[1] for e in n.family_outcomes["pass-b"]], [False])
        self.assertEqual(sc.state("honest-fam"), (1.0, 1))
        self.assertEqual(sc.state("pass-a"), (0.0, 1))

    def test_recomputing_a_score(self):
        """Anyone rebuilding each family's verdicts from the submissions' records (judges, shadows of barred
        families, final outcomes) gets the score the network holds, a barred family's included."""
        w = replace(S.SCORE_WORLD, weeks=20, initial_active=8, joins_week=0.0)
        n = Net(3, SMALL, w)
        sc = S.install(n)
        n.run()
        self.assertGreater(n.stats["barred_shadows"], 0)
        rec = {}
        for sub in sorted((s for s in n.subs.values() if s.final is not None), key=lambda s: s.final_t):
            for vid, vote, _ in sub.judges:
                rec.setdefault(n.reg.validators[vid].family, []).append(vote == sub.final)
            for vid, revealed, vote in sub.family_shadows:
                if revealed:
                    rec.setdefault(n.reg.validators[vid].family, []).append(vote == sub.final)
        for f, xs in rec.items():
            last = xs[-SMALL.SCORE_WINDOW:]
            self.assertEqual(sc.state(f), (sum(last) / len(last), len(last)), f)


class TestMinimumScore(unittest.TestCase):
    def test_a_weak_model(self):
        """A family that is wrong 60 % of the time falls below SCORE_MIN after SCORE_MIN_VERDICTS: its validators
        are drawn only as shadows. When its model improves, its shadow verdicts lift the score back, and it is drawn
        again."""
        acc = dict(top=1.0, mid=1.0, low=1.0, weak=0.4)
        w = replace(S.SCORE_WORLD, weeks=16, initial_active=8, joins_week=0.0, reliability=1.0, volunteer_per_day=0.0,
                    family_blind=(), family_accuracy=tuple(acc.items()))
        seen = []

        def better(n):
            n.w = replace(n.w, family_accuracy=tuple(dict(acc, weak=1.0).items()))

        class Watch(A.Actor):
            party = "watch"

            def on_tick(self, n):
                seen.append((n.t, n.scores.ok("weak")))

        n = Net(1, SMALL, w, [At(42, better), Watch()])
        S.install(n)
        n.run()
        barred = [t for t, ok in seen if not ok]
        self.assertTrue(barred)
        self.assertTrue(all(ok for t, ok in seen if t < barred[0]))
        self.assertTrue(n.scores.ok("weak"))  # back
        back = max(barred)
        weak = lambda s: [vid for vid, _, _ in s.judges if n.reg.validators[vid].family == "weak"]
        while_barred = [s for s in n.subs.values() if s.family_shadows]
        self.assertTrue(while_barred)
        for s in while_barred:  # drawn only as shadows
            self.assertEqual(weak(s), [])
            self.assertTrue(all(n.reg.validators[vid].family == "weak" for vid, _, _ in s.family_shadows))
        self.assertTrue(any(weak(s) for s in n.subs.values() if s.drawn_t is not None and s.drawn_t > back + DAY))
        self.assertGreater(len(n.family_shadow_outcomes["weak"]), 0)


class TestNeutralStart(unittest.TestCase):
    def test_a_newly_released_open_model(self):
        """A family with no verdicts is drawn and paid as at the neutral score until it has SCORE_MIN_VERDICTS;
        then its own score sets the factor."""
        n = quiet()
        sc = S.install(n)
        self.assertEqual((sc.ok("new-open"), sc.factor("new-open"), sc.score("new-open")), (True, 1.0, S.neutral()))
        seeded(n, "new-open", 0, 49)  # 49 disagreements: still neutral
        self.assertEqual((sc.ok("new-open"), sc.factor("new-open")), (True, 1.0))
        seeded(n, "new-open", 0, 50)
        self.assertFalse(sc.ok("new-open"))
        seeded(n, "new-open", 50, 50)
        self.assertEqual((sc.ok("new-open"), sc.factor("new-open")), (True, 2.0))
        # drawn and paid the unscaled fee
        n = quiet()
        S.install(n)
        vs = [add(n, i, f) for i, f in enumerate(("new-open", "b", "c"), start=2)]
        sub = n.submit(1.0, 20.0, True, "alice", None)
        n.run()
        self.assertEqual(sorted(vid for vid, _, _ in sub.judges), [v.vid for v in vs])
        self.assertTrue(all(abs(v.acct.fees - QUIET.service_fee) < 1e-12 for v in vs))


class TestPayByScore(unittest.TestCase):
    def test_a_better_model_earns_more(self):
        """Families with factors 1.5x and 0.8x on one panel: each judge gets its usage back in full and 1.5x and
        0.8x the market fee."""
        n = quiet()
        S.install(n)
        seeded(n, "a", 90, 100)  # score 0.90 -> factor 1.5
        seeded(n, "b", 76, 100)  # score 0.76 -> factor 0.8
        a, b, c = add(n, 2, "a"), add(n, 3, "b"), add(n, 4, "fresh")
        self.assertAlmostEqual(n.scores.factor("a"), 1.5)
        self.assertAlmostEqual(n.scores.factor("b"), 0.8)
        sub = n.submit(1.0, 20.0, True, "alice", None)
        n.run()
        fee = QUIET.service_fee
        self.assertAlmostEqual(a.acct.fees, 1.5 * fee)
        self.assertAlmostEqual(b.acct.fees, 0.8 * fee)
        self.assertAlmostEqual(c.acct.fees, 1.0 * fee)
        self.assertAlmostEqual(sub.charges - (a.acct.fees + b.acct.fees + c.acct.fees), 3 * QUIET.usage_per_check)

    def test_the_factor_composes_with_any_market_fee(self):
        class Market:
            def __init__(self):
                self.periods, self.price = 0, 0.08

            def fee(self, n, sub, v):
                return self.price

            def end_period(self, n, period):
                self.periods += 1

        m = Market()
        n = Net(1, P, QUIET, fee=m)
        n.leave(n.reg.validators[1])
        S.install(n)
        seeded(n, "a", 100, 100)
        v = add(n, 2, "a")
        n.submit(1.0, 20.0, True, "alice", None)
        n.run()
        self.assertAlmostEqual(v.acct.fees, 2.0 * 0.08)
        self.assertGreater(m.periods, 0)
        self.assertEqual(n.fee.price, 0.08)  # the market's own state stays readable through the wrapper


class TestOneVote(unittest.TestCase):
    def _panel(self, weighted):
        n = quiet()
        S.install(n, weighted)
        seeded(n, "top", 100, 100)  # factor 2
        seeded(n, "b1", 70, 100)  # factor 0.5
        seeded(n, "b2", 70, 100)
        add(n, 2, "top", AlwaysPass())
        add(n, 3, "b1")
        add(n, 4, "b2")
        sub = n.submit(1.0, 20.0, False, "alice", None)
        n.run()
        self.assertEqual(sorted(vote for _, vote, _ in sub.judges), [False, False, True])
        return sub

    def test_a_high_score_family_in_the_minority(self):
        """v3: the top family's pass against two fails is 1 of 3, and the fix fails."""
        self.assertFalse(self._panel(None).verdict)

    def test_the_rejected_alternative_lets_one_family_override(self):
        """Weighted by the factor (2 against 0.5 + 0.5), the same panel passes the bad fix."""
        self.assertTrue(self._panel("factor").verdict)
        self.assertFalse(self._panel("score").verdict)  # 1.0 against 0.7 + 0.7

    def test_the_comparison_runs_every_rule_on_the_same_seeds(self):
        w = replace(S.SCORE_WORLD, weeks=12)
        rows = dict(S.compare(range(1, 3), w))
        self.assertEqual(len(rows), len(S.MODES))
        for name, mode in S.MODES:
            self.assertEqual(len(rows[name]["bad_per_100"]), 2)
            if mode in (None, "pay"):
                self.assertEqual(rows[name]["flipped"], [0.0, 0.0])  # one vote: nothing to flip
        self.assertEqual(S.compare_table(range(1, 2), w), S.compare_table(range(1, 2), w))


# ---------- the new behaviours, alone and against their twins ----------

SHORT = replace(S.SCORE_WORLD, weeks=20)


class TestMovers(unittest.TestCase):
    def test_movers_switch_to_the_family_that_pays_most(self):
        a = S.Movers(w=SHORT)
        n = A.run(a, 1, p=PARAMS)
        mine = n.party_validators("movers")
        self.assertEqual(len(mine), 4)
        self.assertGreater(n.stats["moves"], 0)
        self.assertTrue(any(v.family != "low" for v in mine))
        twin = A.run(S.Movers(True, w=SHORT), 1, p=PARAMS)
        self.assertEqual(twin.stats["moves"], 0)
        self.assertTrue(all(v.family == "low" for v in twin.party_validators("movers")))

    def test_everyone_moving_the_caps_hold_and_several_families_stay(self):
        a = S.Movers(everyone=True)
        n = A.run(a, 2, p=PARAMS)
        m = S._mover_metrics(n, a)
        self.assertGreater(m["moves"], 0)
        self.assertEqual(m["over_cap"], 0)
        self.assertGreaterEqual(m["families_10"], 2)
        self.assertLess(m["largest_share"], 0.9)

    def test_moving_against_the_twin(self):
        r = S.movers_party(range(1, 3))
        self.assertEqual(len(r["diffs"]), 2)
        self.assertGreater(r["moves"], 0)
        self.assertEqual(r["twin_moves"], 0)


class TestHerders(unittest.TestCase):
    def test_a_herder_votes_the_expected_majority(self):
        a = S.Herders(w=SHORT)
        n = A.run(a, 1, p=PARAMS)
        mine = [(vote, faked) for s in n.subs.values() for vid, vote, faked in s.judges
                if n.reg.validators[vid].party == "herders"]
        self.assertTrue(mine)
        self.assertTrue(all(vote for vote, _ in mine))  # the base rate's majority is pass
        self.assertGreater(n.stats["herded"], 0)
        self.assertEqual(sum(f for _, f in mine), n.stats["herded"])  # each herded vote's receipt is false

    def test_an_undetectable_herder_signs_genuine_receipts(self):
        a = S.Herders(w=SHORT, detectable=False)
        n = A.run(a, 1, p=PARAMS)
        self.assertFalse(any(f for s in n.subs.values() for _, _, f in s.judges))

    def test_herders_with_detectable_receipts_lose_against_their_twins(self):
        r = A.against_twin(lambda h: S.Herders(h, w=SHORT), range(1, 4), p=PARAMS, metrics=S._herd_metrics)
        self.assertTrue(r["loses"], r["diff"])
        self.assertLess(r["agree"], r["twin_agree"])  # herding by the base rate lowers a 90 % family's agreement


if __name__ == "__main__":
    unittest.main()
