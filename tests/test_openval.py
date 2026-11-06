"""#134 phase 1 (pof/sim/openval): the open registry (task 1.1), the panels (1.2), the attackers against their twins
(1.3) and random audits (1.6), one test per phase-1 scenario of #132's specs/validator-admission and
specs/judge-panels, plus the incentive-simulation scenarios phase 1 can already run."""

import unittest
from dataclasses import replace

from pof.sim.openval import actors as A
from pof.sim.openval import panels as D
from pof.sim.openval import report as R
from pof.sim.openval.net import CONSTITUTION, Act, Honest, Net
from pof.sim.openval.params import DAY, WORLD
from pof.sim.openval.params import V1 as PARAMS  # #134's rules: these tests keep them reachable (#141)
from pof.sim.openval.registry import ACTIVE, CANDIDATE, GONE, LEAVING, RegistrationError, Registry

P = PARAMS
TEES = ("nitro", "tdx", "sev-snp")
FAMS = ("anthropic", "openai", "google", "open-weight")
# a world with nothing happening on its own: scenario tests submit and register what they need
QUIET = replace(WORLD, weeks=3, subs_week=0.0, joins_week=0.0, volunteer_per_day=0.0, reliability=1.0,
                accuracy=1.0)
NO_AUDIT = replace(P, AUDIT_RATE=0.0)


def registry(n, hosts=None, bond=1250.0, families=None, operators=None, p=P):
    r = Registry(p)
    for i in range(n):
        v = r.register(0.0, key=f"k{i}", signer=f"k{i}", bond=bond, proof=TEES[i % 3],
                       host=(hosts[i] if hosts else f"h{i}"), family=(families[i] if families else FAMS[i % 4]),
                       operator=(operators[i] if operators else f"op{i}"))
        r.seed_active(v, 0.0)
    return r


def net(initial=0, p=NO_AUDIT, w=QUIET, actors=(), **kw):
    return Net(1, p, replace(w, initial_active=initial, **kw), actors)


class Mute(Honest):
    """Never seals (a silent judge, or a node that is off)."""

    def counted(self, n, sub, v):
        return Act(False, False)

    def shadow(self, n, sub, v):
        return Act(False, False)


class NoReceipt(Honest):
    """Seals and reveals a verdict, but posts no receipt: treated as not having revealed."""

    def counted(self, n, sub, v):
        return Act(False, True)


class At(A.Actor):
    """A test actor: runs `fn(net)` once, at the first tick on or after `day`."""
    party = "test"

    def __init__(self, day, fn):
        super().__init__()
        self.day, self.fn, self.done = day, fn, False

    def on_tick(self, n):
        if not self.done and n.t >= self.day * DAY:
            self.done = True
            self.fn(n)


def activate(n, count, bond=1250.0, start=0):
    for i in range(start, start + count):
        v = n.reg.register(n.t, key=f"late{i}", signer=f"late{i}", bond=bond, proof=TEES[i % 3], host=f"late-h{i}",
                           family=FAMS[(i + 1) % 4], operator=f"late-op{i}")
        n.reg.seed_active(v, n.t)


# ---------- 1.1: the registry (specs/validator-admission) ----------

class TestRegistration(unittest.TestCase):
    def test_a_newcomer_registers_as_a_candidate_with_no_co_signature(self):
        r = Registry()
        v = r.register(0.0, key="new", signer="new", bond=P.BOND_FLOOR, proof="nitro", host="aws", family="openai",
                       operator="stranger")
        self.assertEqual(v.state, CANDIDATE)
        self.assertNotIn("co_signers", v.public())

    def test_an_image_not_on_the_list_is_refused(self):
        with self.assertRaises(RegistrationError):
            Registry().register(0.0, key="x", signer="x", bond=100, proof="tdx", host="h", family="f", operator="o",
                                image="sha256:something-else")

    def test_too_small_a_bond_is_refused(self):
        with self.assertRaises(RegistrationError):
            Registry().register(0.0, key="x", signer="x", bond=P.BOND_FLOOR - 0.01, proof="tdx", host="h",
                                family="f", operator="o")

    def test_someone_elses_key_is_refused(self):
        with self.assertRaises(RegistrationError):
            Registry().register(0.0, key="victim", signer="attacker", bond=100, proof="tdx", host="h", family="f",
                                operator="o")

    def test_anyone_reads_what_the_caps_need(self):
        v = Registry().register(0.0, key="x", signer="x", bond=100, proof="sev-snp", host="ovh", family="google",
                                operator="acct", attestation="0xatt")
        pub = v.public()
        for k, want in (("proof", "sev-snp"), ("tee", "sev-snp"), ("host", "ovh"), ("family", "google"),
                        ("operator", "acct"), ("attestation", "0xatt")):
            self.assertEqual(pub[k], want)

    def test_a_validator_on_ordinary_hardware_and_the_levels(self):
        """zkTLS registers as a candidate at level C (phase 1 records the level and treats every level alike); a
        cloud confidential VM is A, a TEE at home is B."""
        r = Registry()
        c = r.register(0.0, key="pc", signer="pc", bond=100, proof="zktls", host="home", family="open-weight",
                       operator="o1", attestation=None)
        a = r.register(0.0, key="vm", signer="vm", bond=100, proof="tdx", host="gcp", family="google", operator="o2")
        b = r.register(0.0, key="srv", signer="srv", bond=100, proof="sev-snp", host="home", family="openai",
                       operator="o3", cloud_attested=False)
        self.assertEqual((c.state, c.level, c.tee), (CANDIDATE, "C", "none"))
        self.assertEqual((a.level, b.level), ("A", "B"))

    def test_at_most_one_genesis_validator(self):
        spec = dict(key="g", signer="g", bond=1250, proof="nitro", host="aws", family="anthropic", operator="g")
        with self.assertRaises(RegistrationError):
            Registry().genesis([spec, dict(spec, key="g2", signer="g2", operator="g2")])
        r = Registry()
        (g,) = r.genesis([spec])
        self.assertTrue(g.genesis and g.state == ACTIVE)
        with self.assertRaises(RegistrationError):
            r.genesis([dict(spec, key="g3", signer="g3")])

    def test_no_function_admits_removes_or_suspends_by_hand(self):
        """The owner tries to admit a friend: there is no function to do it."""
        public = {m for m in dir(Registry) if not m.startswith("_")}
        for name in ("activate", "admit", "approve", "add", "remove", "suspend", "set_param", "kick"):
            self.assertNotIn(name, public)
        r = Registry()
        friend = r.register(0.0, key="f", signer="f", bond=100, proof="tdx", host="h", family="f", operator="o")
        self.assertEqual(friend.state, CANDIDATE)
        # a DAO's validator: registered like any other, a candidate until it qualifies
        dao = r.register(0.0, key="dao", signer="dao", bond=100, proof="nitro", host="aws", family="g", operator="dao")
        self.assertEqual(dao.state, CANDIDATE)


class TestQualification(unittest.TestCase):
    def setUp(self):
        self.r = Registry()
        self.v = self.r.register(0.0, key="c", signer="c", bond=100, proof="tdx", host="h", family="f", operator="o")

    def test_a_candidate_qualifies_at_exactly_qualify_verdicts(self):
        for i in range(P.QUALIFY_VERDICTS - 1):
            self.assertIsNone(self.r.record_shadow(self.v, True, i % 10 != 0, 1.0 + i))
            self.assertEqual(self.v.state, CANDIDATE)
        self.assertEqual(self.r.record_shadow(self.v, True, True, 50.0), "active")
        self.assertEqual(self.v.state, ACTIVE)

    def test_the_thresholds_are_inclusive(self):
        """19 of 20 revealed (95 %) with 16 of the 19 agreeing (84 %) qualifies; 18 of 20 revealed (90 %) doesn't."""
        n = P.QUALIFY_VERDICTS
        for i in range(n):
            self.r.record_shadow(self.v, i != 0, i not in (1, 2, 3), float(i))
        self.assertEqual(self.v.state, ACTIVE)
        r2 = Registry()
        w = r2.register(0.0, key="d", signer="d", bond=100, proof="tdx", host="h", family="f", operator="o")
        for i in range(n):
            r2.record_shadow(w, i > 1, True, float(i))
        self.assertEqual(w.state, CANDIDATE)

    def test_a_candidate_that_never_answers_stays_a_candidate_with_its_bond(self):
        for i in range(3 * P.QUALIFY_VERDICTS):
            self.r.record_shadow(self.v, False, False, i * 30 * DAY)
        self.assertEqual(self.v.state, CANDIDATE)
        self.assertEqual(self.v.bond, 100)
        self.assertGreaterEqual(self.v.qualify_tries, 2)

    def test_a_failed_candidate_cools_off_then_tries_again(self):
        for i in range(P.QUALIFY_VERDICTS):
            self.r.record_shadow(self.v, True, False, 10.0)
        self.assertEqual(self.v.cooldown_until, 10.0 + P.QUALIFY_COOLDOWN_H)
        self.assertIsNone(self.r.record_shadow(self.v, True, True, 11.0))  # still cooling off: not counted
        self.assertEqual(self.v.shadow_n, 0)
        for i in range(P.QUALIFY_VERDICTS):
            self.r.record_shadow(self.v, True, True, 10.0 + P.QUALIFY_COOLDOWN_H + i)
        self.assertEqual(self.v.state, ACTIVE)

    def test_a_candidate_that_copies_the_counted_judges_misses_its_seal(self):
        """A copier waits for the counted reveals; its seal window has closed by then, so it never reveals and
        never qualifies, though it is drawn as a shadow (net-level)."""
        n = net(initial=8, w=replace(QUIET, weeks=6, subs_week=40.0))
        copier = n.reg.register(0.0, key="cp", signer="cp", bond=100, proof="tdx", host="h", family="f",
                                operator="copier", behaviour=Mute())
        n.run()
        self.assertGreaterEqual(copier.qualify_tries, 1)
        self.assertEqual(copier.state, CANDIDATE)
        self.assertEqual(copier.acct.slashed, 0.0)


class TestStayingAndLeaving(unittest.TestCase):
    def test_a_validator_that_goes_offline_stops_being_drawn_and_must_requalify(self):
        r = registry(1)
        v = r.validators[1]
        allowed = int(round((1 - P.ACTIVE_REVEAL_MIN) * P.ACTIVE_REVEAL_WINDOW))
        for i in range(P.ACTIVE_REVEAL_WINDOW - allowed - 1):
            r.record_counted(v, True, float(i))
        for i in range(allowed):
            self.assertFalse(r.record_counted(v, False, 100.0 + i))
        self.assertEqual(v.state, ACTIVE)
        self.assertTrue(r.record_counted(v, False, 200.0))
        self.assertEqual(v.state, CANDIDATE)
        self.assertEqual(r.eligible(10.0), [])

    def test_a_missed_reveal_costs_the_published_share(self):
        """A counted judge that doesn't reveal is replaced and slashed NO_REVEAL_SLASH_BPS (net-level)."""
        n = net(initial=4)
        silent = n.register_actor(0, "s", 1000.0, "sh", "tdx", "google", "s-op", Mute(), active=True)
        subs = [n.submit(1.0 + i, 40.0, True, f"solver{i}", None) for i in range(12)]
        n.run()
        drawn = sum(1 for s in subs if silent.vid in s.draw.drawn)
        self.assertGreater(drawn, 0)
        self.assertAlmostEqual(silent.acct.slashed, sum(1000.0 * (1 - 0.05) ** i * 0.05 for i in range(drawn)))

    def test_leave_then_a_fault_is_proven(self):
        r = registry(1)
        v = r.validators[1]
        r.leave(v, 100.0)
        self.assertEqual(v.state, LEAVING)
        self.assertEqual(r.eligible(10.0), [])  # a leaving validator isn't drawn
        self.assertEqual(r.withdraw(v, 100.0 + P.UNBONDING_DELAY_H - 1), 0.0)  # not before the delay
        self.assertEqual(r.slash(v, P.EQUIVOCATION_SLASH_BPS // 2, 100.0 + P.UNBONDING_DELAY_H - 1), 625.0)
        self.assertEqual(r.withdraw(v, 100.0 + P.UNBONDING_DELAY_H), 625.0)  # only what remains
        self.assertEqual(v.state, GONE)
        self.assertEqual(r.slash(v, P.EQUIVOCATION_SLASH_BPS, 100.0 + P.UNBONDING_DELAY_H + 1), 0.0)

    def test_the_unbonding_delay_outlasts_every_window(self):
        self.assertGreater(P.UNBONDING_DELAY_H, max(max(w.values()) for w in P.CHALLENGE_WINDOW_H.values()))

    def test_an_honest_mistake_is_not_slashed(self):
        """Verdicts overturned by challenges, with valid receipts: no false-verdict slash in an honest network."""
        n = Net(3, P, replace(WORLD, initial_active=12, joins_week=0.0, weeks=20, volunteer_per_day=2.0,
                              accuracy=0.7)).run()
        self.assertGreater(n.stats["reversed"], 0)
        self.assertEqual(n.stats["receipts_upheld"], 0)
        self.assertEqual(n.stats["slashed_false"], 0)


# ---------- 1.2: the panels (specs/judge-panels, validator-admission's caps) ----------

class TestK(unittest.TestCase):
    def test_k_is_the_largest_odd_number_the_network_allows(self):
        for n, k in ((0, 0), (1, 1), (2, 1), (3, 3), (4, 3), (5, 5), (6, 5), (7, 7), (8, 7), (40, 7)):
            self.assertEqual(P.k_for(n), k, n)

    def test_one_validator_judges_alone_and_decides_after_k1s_window(self):
        n = net(initial=0)
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.k, 1)
        self.assertTrue(sub.final)
        self.assertAlmostEqual(sub.final_t, sub.verdict_t + P.window_h(1))

    def test_two_validators_give_k1_never_2(self):
        n = net(initial=1)
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual((sub.k, len(sub.judges)), (1, 1))

    def test_six_validators_give_k5_and_three_passes_pass(self):
        r = registry(6)
        d = D.draw(12345, r.eligible(100.0), P.k_for(6), P)
        self.assertEqual(d.k, 5)
        n = net(initial=5)
        sub = n.submit(1.0, 100.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.k, 5)
        self.assertEqual((sub.k + 1) // 2, 3)

    def test_forty_validators_give_k7_and_four_passes_pass(self):
        r = registry(40)
        d = D.draw(999, r.eligible(100.0), P.k_for(40), P)
        self.assertEqual((d.k, len(set(d.panel))), (7, 7))
        n = net(initial=39)
        sub = n.submit(1.0, 100.0, True, "alice", None)
        n.run()
        self.assertEqual((sub.k, (sub.k + 1) // 2), (7, 4))

    def test_a_fix_passes_with_a_majority_of_k(self):
        """3 of 5 pass: two judges of an always-wrong family can't fail a good fix."""
        w = replace(QUIET, family_accuracy=(("anthropic", 0.0),), initial_active=4, families=FAMS)
        n = Net(1, NO_AUDIT, w)
        sub = n.submit(1.0, 100.0, True, "alice", None)
        n.run()
        wrong = sum(1 for vid, vote, _ in sub.judges if not vote)
        self.assertEqual(sub.k, 5)
        self.assertEqual(sub.verdict, wrong < 3)


class TestBondsAndLimits(unittest.TestCase):
    def test_a_small_bond_a_small_bounty(self):
        r = registry(1, bond=100.0)
        self.assertEqual(len(r.eligible(40.0)), 1)
        self.assertEqual(len(r.eligible(400.0)), 0)

    def test_the_bond_tiers_of_d2(self):
        """D2's counters (BOND_TIERS, #141's rule) need 2x the bounty's tier, the steps at every level's limits:
        stricter than #134's 2x the bounty."""
        tiers = replace(P, BOND_TIERS=True)
        self.assertEqual(tiers.bond_needed(40.0), 100.0)
        self.assertEqual(tiers.bond_needed(60.0), 250.0)  # the spec's "A bounty between two tiers": $125's tier
        self.assertEqual(P.bond_needed(60.0), 120.0)

    def test_a_big_bounty_on_a_small_network_waits_and_may_be_withdrawn(self):
        n = net(initial=0, w=replace(QUIET, weeks=4))
        sub = n.submit(1.0, 200.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.state, "withdrawn")
        self.assertIsNone(sub.draw)  # no judge was drawn
        self.assertEqual(sub.charges, 0.0)  # the deposit comes back whole
        self.assertEqual(n.stats["withdrawn"], 1)

    def test_the_network_grows_and_the_waiting_submission_is_drawn(self):
        n = net(initial=0, actors=[At(3, lambda n: activate(n, 3))])
        sub = n.submit(1.0, 200.0, True, "alice", None)
        n.run()
        self.assertTrue(sub.waited)
        self.assertGreaterEqual(sub.drawn_t, 3 * DAY)
        self.assertEqual(sub.k, 3)
        self.assertTrue(sub.final)

    def test_the_largest_bounty_follows_k(self):
        n = net(initial=0)
        self.assertEqual(n.largest_bounty(), P.limit(1))
        activate(n, 2)
        self.assertEqual(n.largest_bounty(), P.limit(3))


class TestCaps(unittest.TestCase):
    def test_ten_nodes_on_one_cloud(self):
        """A panel of 5 holds at most 2 of them; the rest from other hosts. (Rejection sampling can step k down
        when DRAW_TRIES x k tries don't fill it: rarely.)"""
        hosts = ["cloud"] * 10 + [f"h{i}" for i in range(10)]
        r = registry(20, hosts=hosts)
        pool = r.eligible(100.0)
        full = 0
        for seed in range(200):
            d = D.draw(seed, pool, 5, P)
            full += d.k == 5
            on_cloud = sum(1 for v in d.panel if r.validators[v].host == "cloud")
            self.assertLessEqual(on_cloud, P.cap(d.k))
        self.assertGreaterEqual(full, 190)

    def test_too_few_distinct_hosts_lower_k(self):
        """k comes from what the caps leave: seven validators on two hosts can only form k = 1 (k = 3 needs three
        hosts); on three hosts (5, 1, 1), k = 3 at most."""
        two = registry(7, hosts=["a"] * 4 + ["b"] * 3)
        three = Registry()
        for i, (host, tee, fam) in enumerate([("a", "nitro", FAMS[i % 2]) for i in range(5)]
                                             + [("b", "tdx", "google"), ("c", "sev-snp", "open-weight")]):
            three.seed_active(three.register(0.0, key=f"k{i}", signer=f"k{i}", bond=1250, proof=tee, host=host,
                                             family=fam, operator=f"o{i}"), 0.0)
        ks = [D.draw(seed, three.eligible(10.0), 7, P).k for seed in range(100)]
        for seed in range(100):
            self.assertEqual(D.draw(seed, two.eligible(10.0), 7, P).k, 1)
        self.assertLessEqual(max(ks), 3)
        self.assertGreaterEqual(ks.count(3), 85)

    def test_one_validator_per_declared_operator(self):
        r = registry(9, operators=["same"] * 5 + [f"o{i}" for i in range(4)])
        for seed in range(50):
            d = D.draw(seed, r.eligible(10.0), 7, P)
            self.assertLessEqual(sum(1 for v in d.panel if r.validators[v].operator == "same"), 1)
            self.assertLessEqual(d.k, 5)  # five distinct operators at most

    def test_the_owners_validator_is_recused_from_the_owners_fix(self):
        r = registry(4, operators=["owner", "o1", "o2", "o3"])
        pool = r.eligible(40.0, parties=frozenset({"owner"}))
        self.assertNotIn(1, [v.vid for v in pool])
        d = D.draw(77, pool, P.k_for(len(pool)), P)
        self.assertEqual(d.k, 3)
        self.assertNotIn(1, d.panel)


class TestSeedAndRecompute(unittest.TestCase):
    def test_recomputing_a_panel_gives_the_same_validators_in_the_same_order(self):
        n = Net(4, P, replace(WORLD, initial_active=15, joins_week=0.0, weeks=2)).run()
        drawn = [s for s in n.subs.values() if s.draw is not None]
        self.assertGreater(len(drawn), 10)
        for s in drawn:
            pool = [n.reg.validators[v] for v in s.draw.pool]
            again = D.draw(s.draw.seed, pool, P.k_for(len(pool)), P)
            self.assertEqual((again.k, again.panel), (s.k, s.draw.panel))

    def test_the_seed_depends_on_a_block_after_the_seal(self):
        """The same sealed submission gets different seeds on different chains (block hashes); without the later
        block, the solver alone fixes it."""
        seeds = {D.draw_seed(P, chain, 1000, 42, 40.0, 7) for chain in range(20)}
        self.assertEqual(len(seeds), 20)
        fixed = replace(P, SEED_FROM_LATER_BLOCK=False)
        self.assertEqual(len({D.draw_seed(fixed, chain, 1000, 42, 40.0, 7) for chain in range(20)}), 1)

    def test_grinding_the_seed(self):
        """Every attempt pays the attempt fee and its checks; a declared validator is recused as a party."""
        g = A.SeedGrinder()
        n = A.run(g, 2, p=P, w=replace(WORLD, weeks=16))
        pa = n.parties["grinder"]
        self.assertGreater(pa.submitted, 0)
        self.assertGreaterEqual(pa.costs, pa.submitted * WORLD.attempt_fee)
        mine = [s for s in n.subs.values() if s.party == "grinder" and s.draw is not None]
        self.assertTrue(all(s.k == 1 for s in mine))
        declared = A.SeedGrinder(declared=True)
        n2 = A.run(declared, 2, p=P, w=replace(WORLD, weeks=16))
        me = n2.party_validators("grinder")[0].vid
        self.assertTrue(all(me not in s.draw.drawn for s in n2.subs.values()
                            if s.party == "grinder" and s.draw is not None))


class TestSilentJudges(unittest.TestCase):
    def test_a_judge_that_goes_silent_is_replaced_and_k_stays(self):
        n = net(initial=2)
        # TEE types and families chosen so that a panel of 3 with it, and one without it, both fit the caps
        silent = n.register_actor(0, "s", 1250.0, "sh", "tdx", "open-weight", "s-op", Mute(), active=True)
        subs = [n.submit(1.0 + i, 100.0, False, f"solver{i}", None) for i in range(10)]
        n.run()
        hit = [s for s in subs if s.draw is not None and silent.vid in s.draw.drawn]
        self.assertTrue(hit)
        for s in hit:
            self.assertEqual(s.k, 3)
            self.assertEqual(len(s.judges), 3)
            self.assertNotIn(silent.vid, [vid for vid, _, _ in s.judges])
            self.assertFalse(s.verdict)  # 2 passes still needed; honest judges fail the bad fix
            self.assertGreaterEqual(s.verdict_t, s.drawn_t + P.SEAL_WINDOW_H + P.judge_hours)  # a fresh window
        self.assertTrue(all(k == m for k, m in n.k_seen))

    def test_a_verdict_with_no_receipt_doesnt_count(self):
        n = net(initial=2)
        nr = n.register_actor(0, "s", 1250.0, "sh", "tdx", "open-weight", "s-op", NoReceipt(), active=True)
        subs = [n.submit(1.0 + i, 100.0, True, f"solver{i}", None) for i in range(10)]
        n.run()
        hit = [s for s in subs if s.draw is not None and nr.vid in s.draw.drawn]
        self.assertTrue(hit)
        self.assertTrue(all(nr.vid not in [vid for vid, _, _ in s.judges] and len(s.judges) == 3 for s in hit))
        self.assertGreater(nr.acct.slashed, 0)

    def test_an_exhausted_shuffle_waits_for_the_next_eligible_validator(self):
        """One validator, silent: nobody can replace it until a newcomer is active; then the check goes on."""
        mute = A.Actor()
        mute.genesis = lambda n: dict(key="g", signer="g", bond=1250, proof="nitro", host="aws", family="openai",
                                      operator="g", behaviour=Mute())
        n = net(initial=0, actors=[mute, At(4, lambda n: activate(n, 1))])
        sub = n.submit(1.0, 40.0, True, "alice", None)
        n.run()
        self.assertEqual(n.stats["stalled"], 1)
        self.assertEqual(sub.k, 1)
        self.assertTrue(sub.final)
        self.assertGreaterEqual(sub.verdict_t, 4 * DAY)


class TestChallenges(unittest.TestCase):
    def colluding_genesis(self, actor_party="c"):
        a = A.Actor()
        a.party = actor_party
        a.genesis = lambda n: dict(key="g", signer="g", bond=1250, proof="nitro", host="aws", family="openai",
                                   operator="g", party=actor_party, behaviour=A.Colluder(actor_party))
        return a

    def test_a_lone_validator_passes_a_bad_fix_and_is_challenged(self):
        """k = 1 passes a bad fix; a volunteer re-runs it; a fresh panel of 3 upholds the challenge: no merge, no
        payment, the false verdict slashed and the challenger paid."""
        w = replace(QUIET, volunteer_per_day=1000.0)
        n = net(initial=0, w=w, actors=[self.colluding_genesis(), At(1, lambda n: activate(n, 3))])
        sub = n.submit(2.0, 40.0, False, "c-solver", "c")
        n.run()
        self.assertEqual((sub.k, sub.verdict), (1, True))
        ch = sub.challenge
        self.assertIsNotNone(ch)
        self.assertEqual(ch.k, P.challenge_k(1))
        self.assertTrue(ch.upheld and sub.reversed)
        self.assertFalse(sub.final)
        self.assertEqual(n.parties["c"].gains, 0.0)
        self.assertEqual(ch.receipts, (1,))
        self.assertGreater(n.reg.validators[1].acct.slashed, 0)

    def test_a_challenge_with_too_few_validators_freezes_the_window(self):
        w = replace(QUIET, volunteer_per_day=1000.0, weeks=3)
        late = At(12, lambda n: activate(n, 1))
        n = net(initial=0, w=w, actors=[self.colluding_genesis(), late])
        sub = n.submit(2.0, 40.0, False, "c-solver", "c")
        n.run()
        ch = sub.challenge
        self.assertTrue(ch.waited)
        self.assertGreater(ch.resolved_t, sub.window_end)  # the window didn't expire while it waited
        self.assertGreaterEqual(ch.resolved_t, 12 * DAY)
        self.assertEqual(ch.k, 1)  # every other eligible validator, as the largest odd number
        self.assertTrue(sub.reversed)
        never = net(initial=0, w=w, actors=[self.colluding_genesis()])
        sub2 = never.submit(2.0, 40.0, False, "c-solver", "c")
        never.run()
        self.assertEqual((sub2.state, sub2.final), ("challenged", None))

    def test_designs_reading_waits_for_the_full_challenge_panel(self):
        w = replace(QUIET, volunteer_per_day=1000.0)
        d4 = replace(NO_AUDIT, CHALLENGE_WAITS_FOR_FULL=True)
        n = Net(1, d4, replace(w, initial_active=0), [self.colluding_genesis(), At(1, lambda n: activate(n, 2)),
                                                      At(8, lambda n: activate(n, 1, start=2))])
        sub = n.submit(2.0, 40.0, False, "c-solver", "c")
        n.run()
        self.assertEqual(sub.challenge.k, 3)
        self.assertGreaterEqual(sub.challenge.resolved_t, 8 * DAY)

    def test_a_large_panels_quick_finality(self):
        n = net(initial=9)
        sub = n.submit(1.0, 100.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.k, 7)
        self.assertAlmostEqual(sub.final_t - sub.verdict_t, P.window_h(7))


class TestAudits(unittest.TestCase):
    def test_nobody_is_watching_but_the_audit(self):
        """No volunteer; every submission audited; a lone colluder's wrong verdicts are re-checked, the mismatch
        opens a challenge before the window ends, and a fresh validator reverses them. Hosts arranged so k = 1."""
        a = A.Actor()
        a.party = "c"
        a.genesis = lambda n: dict(key="g", signer="g", bond=1250, proof="nitro", host="one", family="openai",
                                   operator="g", party="c", behaviour=A.Colluder("c"))

        def two_more(n):
            for i, host in enumerate(("one", "two")):
                v = n.reg.register(n.t, key=f"h{i}", signer=f"h{i}", bond=1250, proof="tdx", host=host,
                                   family="google", operator=f"ho{i}")
                n.reg.seed_active(v, n.t)

        n = net(initial=0, p=replace(P, AUDIT_RATE=1.0), actors=[a, At(0, two_more)])
        subs = [n.submit(DAY + 1.5 + i * 0.2, 40.0, False, "c-solver", "c") for i in range(12)]
        n.run()
        mine = [s for s in subs if s.judges and s.judges[0][0] == 1]
        self.assertTrue(mine)
        for s in mine:
            self.assertEqual(s.k, 1)
            self.assertEqual(s.audit, "mismatch")
            self.assertEqual(s.challenge.by, "audit")
            self.assertLess(s.challenge.filed_t, s.window_end)
            self.assertTrue(s.reversed)
        auditors = [v for v in n.reg.validators.values() if v.acct.rewards > 0]
        self.assertTrue(auditors)  # the auditor shares in the slash its audit led to

    def test_an_audit_that_agrees_changes_nothing_and_is_paid(self):
        n = net(initial=9, p=replace(P, AUDIT_RATE=1.0))
        sub = n.submit(1.0, 100.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.audit, "agreed")
        self.assertIsNone(sub.challenge)
        self.assertTrue(sub.final)
        auditor = [v for v in n.reg.validators.values() if v.acct.audits]
        self.assertEqual(len(auditor), 1)
        self.assertAlmostEqual(auditor[0].acct.fees, WORLD.service_fee)
        self.assertNotIn(auditor[0].vid, sub.draw.drawn)

    def test_the_audit_is_drawn_by_the_seed_at_the_rate(self):
        hits = sum(D.audited(D.h(s, 9), P) for s in range(20_000))
        self.assertAlmostEqual(hits / 20_000, P.AUDIT_RATE, delta=0.006)


class TestConstitution(unittest.TestCase):
    def test_an_adr_on_a_small_network_waits(self):
        n = net(initial=3)
        adr = n.submit(1.0, 0.0, False, "proposer", None, tier=CONSTITUTION)
        n.run()
        self.assertEqual(adr.state, "waiting")
        self.assertIsNone(adr.draw)

    def test_an_adr_on_a_grown_network_needs_the_threshold_of_k_max(self):
        n = net(initial=9, actors=[])
        good = n.submit(1.0, 0.0, True, "proposer", None, tier=CONSTITUTION)
        n.run()
        self.assertEqual(good.k, P.K_MAX)
        self.assertTrue(good.final)
        self.assertAlmostEqual(good.final_t - good.verdict_t, P.ADR_WINDOW_H)
        w = replace(QUIET, family_accuracy=(("anthropic", 0.0), ("openai", 0.0)))
        n2 = Net(1, NO_AUDIT, replace(w, initial_active=9))
        adr = n2.submit(1.0, 0.0, True, "proposer", None, tier=CONSTITUTION)
        n2.run()
        passes = sum(1 for _, vote, _ in adr.judges if vote)
        self.assertEqual(adr.verdict, passes >= P.CONSTITUTION_QUORUM)

    def test_the_issue_tier_never_judges_an_adr(self):
        n = net(initial=5, actors=[At(2, lambda n: activate(n, 3))])
        adr = n.submit(1.0, 0.0, True, "proposer", None, tier=CONSTITUTION)
        n.run()
        self.assertGreaterEqual(adr.drawn_t, 2 * DAY)
        self.assertEqual(adr.k, P.K_MAX)


# ---------- the network over time: growth and determinism ----------

class TestNetwork(unittest.TestCase):
    def test_a_launch_with_one_validator(self):
        """Small bounties are judged at k = 1 under k = 1's window, and the first candidates qualify on the genesis
        validator's panels."""
        n = Net(1, P, replace(WORLD, weeks=14)).run()
        self.assertGreater(n.stats["k1"], 0)
        self.assertGreater(n.stats["qualified"], 0)
        k1 = [s for s in n.subs.values() if s.k == 1 and s.final is not None and s.challenge is None]
        self.assertTrue(all(abs(s.final_t - s.verdict_t - P.window_h(1)) < 1e-6 for s in k1))
        self.assertTrue(all(s.bounty <= P.limit(s.k) for s in n.subs.values() if s.draw is not None))

    def test_growth_from_one_validator_reports_k_the_limit_and_the_waiting(self):
        g = R.growth(range(1, 3), w=replace(WORLD, weeks=16))
        self.assertGreaterEqual(len(g["rows"]), 4)
        for row in g["rows"]:
            for key in ("active", "k_small", "max_bounty", "waiting"):
                self.assertEqual(len(row[key]), 2)
        self.assertEqual(g["rows"][0]["k_small"], [1, 1])

    def test_k_is_odd_at_most_k_max_and_fixed_at_the_draw(self):
        """Over a year with frequent outages (so many replacements): every panel's k is odd, at most K_MAX, and the
        number of counted judges equals the k drawn."""
        n = Net(2, P, replace(WORLD, reliability=0.9, initial_active=4, weeks=26)).run()
        self.assertGreater(n.stats["replaced"], 10)
        for k, counted in n.k_seen:
            self.assertEqual((k % 2, k <= P.K_MAX, counted), (1, True, k))

    def test_runs_are_deterministic(self):
        a = Net(5, P, replace(WORLD, weeks=10)).run()
        b = Net(5, P, replace(WORLD, weeks=10)).run()
        self.assertEqual(a.stats, b.stats)
        self.assertEqual(a.series, b.series)
        self.assertNotEqual(a.stats, Net(6, P, replace(WORLD, weeks=10)).run().stats)

    def test_the_reports_numbers_are_reproducible(self):
        w = replace(WORLD, weeks=8)
        self.assertEqual(R.growth_table(range(1, 3), w=w), R.growth_table(range(1, 3), w=w))

    def test_phase_2s_hooks(self):
        """The fee, the panel's level and the families' eligibility are pluggable; every counted verdict's
        agreement with the final outcome is recorded per family."""

        class Double:
            periods = 0

            def fee(self, n, sub, v):
                return 0.10

            def end_period(self, n, period):
                Double.periods += 1

        n = Net(1, NO_AUDIT, replace(QUIET, initial_active=5, weeks=1), fee=Double(),
                level_rule=lambda levels: "C", family_ok=lambda f: f != "openai")
        sub = n.submit(1.0, 10.0, True, "alice", None)
        n.run()
        self.assertEqual(sub.level, "C")
        self.assertAlmostEqual(sub.final_t - sub.verdict_t, P.window_h(sub.k, "C"))
        self.assertTrue(all(n.reg.validators[vid].family != "openai" for vid, _, _ in sub.judges))
        self.assertAlmostEqual(sum(v.acct.fees for v in n.reg.validators.values()), 0.10 * sub.k)
        self.assertGreater(Double.periods, 0)
        self.assertEqual(sum(len(x) for x in n.family_outcomes.values()), sub.k)


# ---------- 1.3 and 1.6: the attackers, each alone and against its twin ----------

SHORT = replace(WORLD, weeks=20)
TWIN_SEEDS = range(1, 4)


class TestAttackersAct(unittest.TestCase):
    def test_the_sybil_passes_its_own_fixes_when_it_holds_a_majority(self):
        a = A.Sybil()
        n = A.run(a, 1, p=P, w=replace(a.world(), weeks=20))
        nodes = n.party_validators("sybil")
        self.assertEqual(len({v.operator for v in nodes}), 10)
        mine = [s for s in n.subs.values() if s.party == "sybil" and s.judges]
        self.assertTrue(mine)
        for s in mine:
            own = [vote for vid, vote, _ in s.judges if n.reg.validators[vid].party == "sybil"]
            self.assertTrue(all(own))
            if len(own) >= (s.k + 1) // 2:
                self.assertTrue(s.verdict)

    def test_the_lone_colluder_passes_every_fix_of_its_solver(self):
        a = A.LoneColluder()
        n = A.run(a, 2, p=P, w=SHORT)
        mine = [s for s in n.subs.values() if s.party == "colluder" and s.judges]
        self.assertTrue(mine)
        self.assertTrue(all(s.k == 1 and s.bounty <= P.limit(1) for s in mine))
        self.assertTrue(all(s.verdict for s in mine if s.judges[0][0] == 1))

    def test_the_grinder_with_a_fixed_seed_always_draws_itself(self):
        g = A.SeedGrinder()
        n = A.run(g, 2, p=replace(P, SEED_FROM_LATER_BLOCK=False), w=SHORT)
        me = n.party_validators("grinder")[0].vid
        mine = [s for s in n.subs.values() if s.party == "grinder" and s.draw is not None]
        self.assertTrue(mine)
        self.assertTrue(all(s.draw.panel == [me] for s in mine))
        later = A.run(A.SeedGrinder(), 2, p=P, w=SHORT)
        theirs = [s for s in later.subs.values() if s.party == "grinder" and s.draw is not None]
        self.assertTrue(any(s.draw.panel != [me] for s in theirs))

    def test_the_silent_judge_stays_silent_when_bribed(self):
        n = A.run(A.SilentJudge(), 1, p=P, w=replace(A.SilentJudge().world(), weeks=12))
        self.assertGreater(n.stats["silences"], 0)
        self.assertTrue(all(k == m for k, m in n.k_seen))

    def test_the_fee_farmer_registers_its_nodes_and_its_twin_one(self):
        self.assertEqual(len(A.run(A.FeeFarmer(), 1, p=P, w=replace(A.FeeFarmer().world(), weeks=2))
                             .party_validators("farmer")), 10)
        self.assertEqual(len(A.run(A.FeeFarmer(True), 1, p=P, w=replace(A.FeeFarmer().world(), weeks=2))
                             .party_validators("farmer")), 1)

    def test_the_constitution_waits_for_the_network(self):
        """No ADR passes in any run while fewer than K_MAX validators are eligible."""
        for seed in (1, 2, 3):
            a = A.ConstitutionCoalition()
            n = A.run(a, seed, p=P, w=replace(WORLD, weeks=30))
            adrs = [s for s in n.subs.values() if s.tier == CONSTITUTION]
            self.assertTrue(adrs)
            for s in adrs:
                if s.draw is not None:
                    self.assertGreaterEqual(len(s.draw.pool), P.K_MAX)
                    self.assertEqual(s.k, P.K_MAX)
                else:
                    self.assertNotEqual(s.final, True)

    def test_the_cheater_cheats_at_its_rate(self):
        a = A.WatchedCheater()
        n = A.run(a, 1, p=P, w=replace(a.world(), weeks=26))
        me = n.party_validators("cheater")[0]
        self.assertAlmostEqual(n.stats["cheats"] / (me.acct.checks + n.stats["missed_reveals"]), 0.1, delta=0.05)


class TestAgainstTwins(unittest.TestCase):
    def test_the_sybil_loses(self):
        r = A.against_twin(lambda h: A.Sybil(h), TWIN_SEEDS, p=P, w=replace(A.Sybil().world(), weeks=26))
        self.assertTrue(r["loses"], r["diff"])

    def test_the_silent_judge_loses(self):
        r = A.against_twin(lambda h: A.SilentJudge(h), TWIN_SEEDS, p=P, w=replace(A.SilentJudge().world(), weeks=20))
        self.assertTrue(r["loses"], r["diff"])

    def test_the_fee_farmer_loses(self):
        r = A.against_twin(lambda h: A.FeeFarmer(h), TWIN_SEEDS, p=P, w=replace(A.FeeFarmer().world(), weeks=20))
        self.assertTrue(r["loses"], r["diff"])

    def test_the_cheater_loses_to_audits_and_gains_with_nobody_watching(self):
        w = replace(A.WatchedCheater(volunteers=False).world(), weeks=26)
        audited = A.against_twin(lambda h: A.WatchedCheater(h, volunteers=False), TWIN_SEEDS, p=P, w=w)
        self.assertTrue(audited["loses"], audited["diff"])
        unwatched = A.against_twin(lambda h: A.WatchedCheater(h, volunteers=False), TWIN_SEEDS,
                                   p=replace(P, AUDIT_RATE=0.0), w=w)
        self.assertGreater(unwatched["diff"], 0)

    def test_the_lone_colluder_gains_on_the_specs_defaults(self):
        """A finding, not a wish: with a $100 bond, 20 % slashes and challenges waiting for fresh validators, the
        colluding genesis gains (reports/open-validators-v1.md); its twin is the same genesis judging honestly."""
        r = A.against_twin(lambda h: A.LoneColluder(h), TWIN_SEEDS, p=P, w=SHORT)
        self.assertGreater(r["diff"], 0)
        self.assertGreater(r["attacker"], r["twin"])

    def test_the_seed_grinder_gains_more_with_a_seed_fixed_at_the_seal(self):
        later = A.against_twin(lambda h: A.SeedGrinder(h), TWIN_SEEDS, p=P, w=SHORT)
        fixed = A.against_twin(lambda h: A.SeedGrinder(h), TWIN_SEEDS, p=replace(P, SEED_FROM_LATER_BLOCK=False), w=SHORT)
        self.assertGreater(fixed["diff"], later["diff"])

    def test_the_twins_see_the_same_world(self):
        """The same honest submissions and newcomers for an attacker and its twin."""
        a, t = A.run(A.Sybil(), 3, p=P, w=replace(A.Sybil().world(), weeks=6)), \
            A.run(A.Sybil(True), 3, p=P, w=replace(A.Sybil().world(), weeks=6))
        honest = lambda n: [(s.sid, s.t, s.bounty, s.good) for s in n.subs.values() if s.party is None]
        self.assertEqual(honest(a), honest(t))
        self.assertEqual(a.stats["joined"], t.stats["joined"])


if __name__ == "__main__":
    unittest.main()
