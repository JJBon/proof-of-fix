"""proof-of-fix#58 tasks 1.1-2.4: the token emission (specs/token-emission) and its simulation (specs/incentive-
simulation, "Token emission: scenarios and criteria")."""

import unittest
from unittest import mock

from pof import BPS, MICRO, credits, share
from pof.challenges import Proof
from pof.params import DEFAULTS, TOKENS, ParamsError
from pof.sim import market_sim as MS
from pof.sim.__main__ import main
from pof.tokens import TokenBook, TokenError

from tests.test_award_modes import ModeWorld


class TestParams(unittest.TestCase):  # 1.1
    def test_off_by_default(self):
        self.assertEqual(DEFAULTS.token_emission_per_period, 0)
        self.assertEqual((TOKENS.token_emission_per_period, TOKENS.founder_share_bps, TOKENS.founder_periods,
                          TOKENS.token_reporter_bps), (credits(10_000), 100, 208, 1_500))

    def test_founder_share_above_the_cap_is_refused(self):
        TOKENS.with_(founder_share_bps=TOKENS.owner_share_cap_bps)
        with self.assertRaises(ParamsError):
            TOKENS.with_(founder_share_bps=TOKENS.owner_share_cap_bps + 1)

    def test_validation(self):
        for bad in ({"token_emission_per_period": -1}, {"founder_genesis": -1}, {"founder_periods": -1},
                    {"weight_inflation_pct": 99},
                    {"token_emission_decay_bps": BPS + 1}, {"token_reporter_bps": -1}):
            with self.assertRaises(ParamsError, msg=bad):
                TOKENS.with_(**bad)


def book(**changes) -> TokenBook:
    return TokenBook(TOKENS.with_(**{"token_emission_per_period": 1_000, "founder_share_bps": 0,
                                     "token_emission_decay_bps": 0, **changes}), owner="owner")


class TestEmission(unittest.TestCase):  # 1.2, the token-emission delta's scenarios
    def test_two_bounties_close_in_a_period(self):
        t = book()
        t.record("bounty:1", 3, "a")
        t.record("bounty:2", 1, "b")
        self.assertEqual(t.release(), 1_000)
        self.assertEqual((t.balance("a"), t.balance("b"), t.supply), (750, 250, 1_000))

    def test_nothing_closes(self):
        t = book(founder_share_bps=500, token_emission_decay_bps=100)
        self.assertEqual(t.release(), 0)
        self.assertEqual((t.supply, t.balance("owner")), (0, 0))  # not even the founder's share
        t.record("bounty:1", 1, "a")
        self.assertEqual(t.release(), t.emission(1))  # the next period's own emission: nothing rolled over
        self.assertEqual(t.emission(1), 990)
        self.assertTrue(t.conserved())

    def test_activity_cant_inflate_the_supply(self):
        few, many = book(), book()
        for i in range(2):
            few.record(f"bounty:{i}", 5, f"s{i}")
        for i in range(20):
            many.record(f"bounty:{i}", 5, f"s{i}")
        self.assertEqual((few.release(), many.release()), (1_000, 1_000))
        self.assertEqual(few.supply, many.supply)

    def test_rounding_mints_exactly_the_emission(self):
        t = book()
        for i in range(3):
            t.record(f"bounty:{i}", 1, f"s{i}")
        t.release()
        self.assertEqual(sorted(t.balances.values()), [333, 333, 334])  # the remainder to the first largest weight
        self.assertTrue(t.conserved())

    def test_founder_share_ends(self):
        t = book(founder_share_bps=500, founder_periods=2)
        for period in range(3):
            t.record(f"bounty:{period}", 1, "a")
            t.release()
        self.assertEqual(t.balance("owner"), 2 * 50)
        self.assertEqual(t.balance("a"), 950 + 950 + 1_000)  # the whole emission to fixes once it ends

    def test_genesis_only_as_published(self):
        t = book(founder_genesis=2_000)
        self.assertEqual((t.balance("owner"), t.supply), (2_000, 2_000))
        self.assertTrue(t.conserved())
        self.assertEqual(book().supply, 0)

    def test_the_split(self):
        t = book()
        t.record("bounty:1", 7, "solver", ["reporter"])
        t.release()
        self.assertEqual((t.balance("reporter"), t.balance("solver")), (150, 850))
        t.record("bounty:2", 7, "solver", ["r1", "r2"])  # a bundle's reporters share the reporter's part
        t.release()
        self.assertEqual((t.balance("r1"), t.balance("r2")), (75, 75))

    def test_a_bounty_closes_once_a_period(self):
        t = book()
        t.record("bounty:1", 1, "a")
        with self.assertRaises(TokenError):
            t.record("bounty:1", 1, "a")
        with self.assertRaises(TokenError):
            t.record("bounty:2", -1, "a")

    def test_the_published_rate_is_pooled(self):
        t = book()
        self.assertIsNone(t.rate)
        t.record("bounty:1", 1, "a")  # a thin period: its rate alone would be 1,000 a unit of weight
        t.release()
        t.record("bounty:2", 99, "b")
        t.release()
        self.assertEqual(t.rate, 2_000 / 100)
        for period in range(TokenBook.RATE_PERIODS):
            t.record(f"bounty:{3 + period}", 100, "c")
            t.release()
        self.assertEqual(t.rate, 10)  # the thin period has left the window


class TokenWorld(ModeWorld):
    base = TOKENS

    def paid(self, b, solver, fix, day=3):
        """A submission wins the bounty, is merged at the next release, accepted, and paid in instalments."""
        c = self.m.deliver(self.m.race_submit(b, solver, day, fix=fix), 50, day, passes=True)
        if self.rel.current is not None:
            self.rel.close_release(self.rel.current, [], day)
        self.rel.ship_beta(self.rel.open_release(day), [c], day)
        self.ch.report_review(c, self.ch.reviews[c.id].reviewer, False, c.beta_day + 1)
        self.life.advance(c, c.window_end)
        return c, self.instalments(c.settled_day + 1)

    def instalments(self, day):
        for _ in range(self.P.reward_instalments):
            self.rel.close_release(self.rel.current, [], day)
            self.rel.open_release(day)
            day += 7
        return day

    def mint(self, day):
        """The period ends at the next release."""
        self.rel.close_release(self.rel.current, [], day)
        self.rel.open_release(day)


class TestMintOnClose(TokenWorld):  # 1.3
    def test_zero_coin(self):
        reporter = self.users[0]
        r = self.m.report_issue(reporter, 1)
        b = self.m.open_bounty(0, 1, report=r, weight=credits(80))
        self.assertEqual(self.m.price_cap(b), 0)
        coin = self.ledger.balance(self.solvers[0])
        c, day = self.paid(b, self.solvers[0], "fix-a")
        self.m.settle(day)
        self.assertEqual((b.state, c.reward), ("paid", 0))
        self.assertEqual(self.m.tokens.balance(self.solvers[0]), 0)  # minted at the next release
        self.mint(day)
        t, emission = self.m.tokens, self.m.tokens.emission(self.m.tokens.period - 1)
        pool = emission - share(emission, self.P.founder_share_bps)
        self.assertEqual(t.balance(reporter), share(pool, self.P.token_reporter_bps))
        self.assertEqual(t.balance(self.solvers[0]), pool - t.balance(reporter))
        self.assertEqual(t.balance(self.owner), share(emission, self.P.founder_share_bps))
        self.assertLessEqual(self.ledger.balance(self.solvers[0]), coin)  # no coin paid: only its check costs

    def test_zero_coin_decline_overturned(self):
        b = self.m.open_bounty(0, 1, weight=credits(80))
        c = self.m.deliver(self.m.race_submit(b, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=True)
        self.assertEqual(c.stake, 0)
        self.life.decline(c, 3, by=self.owner, reason="x", panel_majority=True)
        self.life.appeal_decline(c, 3)
        self.life.resolve_decline_appeal(c, True, 4)  # nothing to re-post: it goes on to the next beta build
        self.assertEqual(c.state, "checked")

    def test_refunded_or_unsolved_mints_nothing(self):
        b = self.funded()
        self.m.close_idle(1 + self.P.bounty_max_rounds * self.P.round_days)
        self.assertEqual(b.state, "unsolved")
        self.assertEqual((self.m.tokens.closes, self.m.tokens.supply), ([], 0))

    def test_inflated_estimate(self):
        b = self.funded()
        b.weight = credits(200)  # the registration check overestimated it
        self.m.weigh_at_merge = lambda b: credits(90)
        _, day = self.paid(b, self.solvers[0], "fix-a")
        self.assertEqual((b.merge_weight, self.m.token_weight(b)), (credits(90), credits(90)))
        self.m.settle(day)
        self.assertEqual(self.m.tokens.closes[0].weight, credits(90))  # the smaller estimate counts

    def reported(self, registered, merged):
        reporter = self.users[0]
        b = self.m.open_bounty(0, 1, report=self.m.report_issue(reporter, 1), weight=registered)
        self.m.pledge(b, self.users[1], credits(300), 1)
        self.m.weigh_at_merge = lambda b: merged
        coin = self.ledger.balance(reporter)
        _, day = self.paid(b, self.solvers[0], "fix-a")
        self.m.settle(day)
        self.mint(day)
        return b, reporter, self.ledger.balance(reporter) - coin

    def test_inflation_forfeits_the_reporters_share(self):
        b, reporter, coin = self.reported(credits(400), credits(100))  # registered at 4x the merge estimate
        t = self.m.tokens
        self.assertTrue(b.inflated)
        self.assertEqual((t.balance(reporter), t.history[0][1].reporters), (0, []))
        self.assertEqual(coin, self.P.issue_stake)  # its stake back, no finder's fee: that returned to the funders
        self.assertTrue(t.conserved())

    def test_within_the_tolerance_the_reporter_is_paid(self):
        b, reporter, coin = self.reported(credits(290), credits(100))  # within the tolerance
        self.assertFalse(b.inflated)
        self.assertGreater(self.m.tokens.balance(reporter), 0)
        self.assertGreater(coin, self.P.issue_stake)  # its stake back and the finder's fee

    def test_treasury_tops_up_an_open_bounty(self):
        b = self.m.open_bounty(0, 1, weight=credits(50))
        self.rel.open_release(1)
        self.m.top_up_treasury(b, credits(100), 1)
        self.assertEqual((b.treasury_in, self.ledger.balance(b.account), self.m._treasury_spent[1]),
                         (credits(100), credits(100), credits(100)))
        with self.assertRaises(Exception):  # the cap per bounty
            self.m.top_up_treasury(b, self.P.treasury_bounty_cap, 1)


class TestClawedBack(TokenWorld):
    base = TOKENS.with_(challenge_appeals=False)  # final challenges, so the clawback is one step

    def test_clawed_back(self):
        b = self.m.open_bounty(0, 1, weight=credits(80))
        e = self.m.race_submit(b, self.solvers[0], 3, fix="fix-a")
        c = self.m.deliver(e, 50, 3, passes=True)
        self.rel.ship_beta(self.rel.open_release(3), [c], 3)
        ch = self.ch.file(c, self.users[0], Proof("regression", c.id), "crash", c.beta_day + 1, "x")
        self.ch.finalize(ch, c.beta_day + 1)
        self.m.settle(c.beta_day + 2)
        self.assertEqual(b.state, "open")  # reopened: the clawed-back fix earns nothing
        self.assertEqual(self.m.tokens.closes, [])
        day = c.beta_day + 3
        self.rel.close_release(self.rel.current, [], day)
        _, day = self.paid(b, self.solvers[1], "fix-b", day)
        self.m.settle(day)
        self.mint(day)
        self.assertEqual(self.m.tokens.balance(self.solvers[0]), 0)
        self.assertGreater(self.m.tokens.balance(self.solvers[1]), 0)  # the eventual paid fix earns them


class TestTokenWorld(unittest.TestCase):  # 2.1 and 2.2
    @classmethod
    def setUpClass(cls):
        cls.on = MS.run("market", 1, TOKENS, weeks=3, token_price=0.05)
        cls.off = MS.run("market", 1, weeks=3)

    def test_unpledged_issues_open_as_zero_coin_bounties(self):
        w = self.on
        self.assertTrue(any(i.route == "zero_coin" for i in w.issues))
        self.assertFalse(any(i.route == "treasury" for i in w.issues))  # the treasury tops up instead
        topped = [b for b in w.market.bounties.values() if b.treasury]
        self.assertTrue(topped and all(b.key for b in topped))  # each tracks its issue: one open per issue
        self.assertTrue(all(b.weight > 0 for b in w.market.bounties.values()))
        self.assertTrue(w.ledger.conserved() and w.market.tokens.conserved())

    def test_emission_off_unchanged(self):
        w = self.off
        self.assertIsNone(w.market.tokens)
        self.assertFalse(any(i.route == "zero_coin" for i in w.issues))
        self.assertTrue(all(b.weight == 0 for b in w.market.bounties.values()))
        self.assertNotIn("tokens", MS.market_report(w, "market", 1))

    def test_solvers_price_tokens(self):
        w = self.on
        b = next(b for b in w.market.bounties.values() if b.weight)
        expected = w.market.expected_tokens(b, 21)
        self.assertGreater(expected, 0)
        self.assertEqual(w.token_value(b, 21), int(expected * 0.05))
        w.token_price = 0
        self.assertEqual(w.token_value(b, 21), 0)
        w.token_price = 0.05

    def test_earnings_include_tokens(self):
        w = self.on
        a = next(a for a in w.actors if a.kind == "solver" and w.tokens(a))
        self.assertEqual(w.net(a) - int(w.tokens(a) * 0.05), super(type(w), w).net(a))


class TestScenarios(unittest.TestCase):  # 2.3
    def test_actors(self):
        kinds = lambda name, **k: {a.kind for a in MS.build(name, 1, TOKENS, **k).actors}
        self.assertIn("self_coder", kinds("token_self"))
        self.assertNotIn("self_coder", kinds("token_self", honest_attack=True))
        self.assertIn("importance_inflater", kinds("token_inflate"))
        self.assertIn("self_coder", kinds("token_inflate", honest_attack=True))
        launch = MS.build("token_launch", 1, TOKENS, solvers=MS.LAUNCH_SOLVERS)
        self.assertEqual(sum(1 for a in launch.actors if a.behaviour.capacity and a.kind in ("solver", "owner")), 3)
        self.assertTrue(launch.owner.behaviour.codes_own)

    def test_inflated_registrations(self):
        w = MS.run("token_inflate", 1, TOKENS, weeks=3, token_price=0.05)
        own = [i for i in w.issues if i.owner is not None and i.bounty is not None]
        self.assertTrue(own and all(i.bias == 2.0 for i in own))
        ratio = sum(i.bounty.weight / i.value for i in own) / len(own)
        self.assertGreater(ratio, 1.5)  # twice the truth, with the estimate's error

    def test_token_report(self):
        r = MS.market_report(MS.run("market", 2, TOKENS, weeks=3, token_price=0.05), "market", 2)
        t = r["tokens"]
        self.assertTrue(t["conserved"] and t["by_weight"])
        shares = t["kinds"]
        self.assertAlmostEqual(sum(v["tokens_share"] for v in shares.values()), 1, places=3)
        self.assertAlmostEqual(shares["reporter"]["weight_share"], TOKENS.token_reporter_bps / BPS, places=1)
        self.assertGreaterEqual(t["owner_supply_share"], TOKENS.founder_share_bps / BPS - 0.001)
        self.assertIn("tokens", r["returns"]["solver"])

    def test_concentration_criterion(self):
        with mock.patch.object(MS, "OWNER_SUPPLY_CAP_BPS", 50):  # below the founder's 1 %: it must fail
            result = MS.token_acceptance([1], 0.05, weeks=2)
        failed = {(f["criterion"], f["scenario"]) for f in result["failures"]}
        self.assertIn(("the owner's supply share stays below its cap", "market"), failed)
        self.assertIn(("the owner's supply share stays below its cap", "market_owner"), failed)
        self.assertNotIn("tokens follow weighted work, and only closes mint them", {c for c, _ in failed})
        for size in MS.RING_SIZES:  # a ring is judged by what it costs others; its own gain is reported
            self.assertEqual(set(result["criteria"][f"ring_cost@{size}"]),
                             {"outsiders", "outsiders_se", "funders", "funders_se"})
            self.assertIn(f"ring@{size}", result["criteria"])

    def test_a_ring_fails_only_if_it_gains_at_others_cost(self):  # owner, 2026-10-30
        no_cost, costs_funders, costs_outsiders = (2.9, 7.1), (5.9, 2.8), (-9.0, 3.0)
        self.assertEqual(MS.judge_ring(6, (19.4, 47.5), no_cost, costs_funders), [])  # costs others, gains nothing
        self.assertEqual(MS.judge_ring(6, (577.0, 166.0), no_cost, (3.1, 3.4)), [])  # gains, costs no one
        self.assertEqual(len(MS.judge_ring(6, (577.0, 166.0), no_cost, costs_funders)), 1)  # gains at funders' cost
        self.assertEqual(len(MS.judge_ring(6, (577.0, 166.0), costs_outsiders, costs_funders)), 2)

    def test_founder_options(self):
        options = MS._founder_options(TOKENS)
        self.assertEqual(options["genesis"].founder_genesis, 2 * TOKENS.token_emission_per_period)
        self.assertEqual(options["genesis"].founder_share_bps, 0)
        self.assertEqual(options["share"].founder_share_bps, 100)
        self.assertEqual(options["share_5pct (tokens-v1)"].founder_share_bps, 500)


class TestCommand(unittest.TestCase):  # 2.4
    def test_smoke(self):
        with mock.patch.object(MS, "TOKEN_PRICES", (0.05,)), mock.patch("sys.stdout") as out:
            with mock.patch.object(MS, "tokens_summary", wraps=MS.tokens_summary) as summary:
                main(["market", "tokens", "--seeds", "1", "--weeks", "1"])
        summary.assert_called_once()
        self.assertTrue(out.write.called)


if __name__ == "__main__":
    unittest.main()
