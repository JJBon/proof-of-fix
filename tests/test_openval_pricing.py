"""#134 task 1.4 (pof/sim/openval/pricing.py): market pricing (#132 design D9). One test per scenario of
specs/check-pricing, each pricing attacker alone against its twin, and the fee settling from the ceiling toward the
validators' cost on a fixed seed."""

import unittest
from collections import Counter
from dataclasses import FrozenInstanceError, replace

from pof.sim.openval import pricing as M
from pof.sim.openval.net import Net
from pof.sim.openval.params import DAY, WORLD
from pof.sim.openval.params import V1 as PARAMS  # #134's rules: these tests keep them reachable (#141)
from pof.sim.openval.registry import ACTIVE, CANDIDATE

P = PARAMS
MOVING = replace(P, NO_REVEAL_SLASH_BPS=0, IDLE_HIGH=0.5)  # v1's "moving" market
TEES = ("nitro", "tdx", "sev-snp")
FAMS = ("anthropic", "openai", "google", "open-weight")
UNIT = "anthropic.input"  # $4 per million at deployment
# a world with nothing happening on its own, and a market with no validators of its own and no entry or exit
QUIET = replace(WORLD, weeks=3, subs_week=0.0, joins_week=0.0, volunteer_per_day=0.0, reliability=1.0,
                accuracy=1.0, initial_active=0)
STILL = replace(M.MARKET, initial=0, entry=False)


def market_net(n=0, w=QUIET, p=P, mw=STILL, family=None, bond=1250.0):
    """A network with the market installed and `n` active validators (one family, or the four in turn)."""
    b = M.Baseline(mw=mw, w=w)
    net = Net(1, p, w, [b])
    vs = [activate(net, i, family or FAMS[i % 4], bond) for i in range(n)]
    m = M.market_of(net)
    m.posters[1] = lambda _m, _v, _t: {}  # the genesis posts nothing unless a test says so
    return net, m, vs


def activate(net, i, family="anthropic", bond=1250.0):
    v = net.reg.register(net.t, key=f"t{i}", signer=f"t{i}", bond=bond, proof=TEES[i % 3], host=f"h{i}",
                         family=family, operator=f"op{i}")
    net.reg.seed_active(v, net.t)
    return v


def posts(m, v, **units):
    """`v` posts the same table every period (`units` with "_" for ".")."""
    table = {k.replace("__", "."): x for k, x in units.items()}
    m.posters[v.vid] = lambda _m, _v, _t: table


def close(net, m, n=1, **counts):
    """End `n` pricing periods with the given counts (submitted, waited, ...)."""
    for _ in range(n):
        net.t += DAY
        m.end_period(net, Counter(counts))


class TestPostedTables(unittest.TestCase):
    def test_a_provider_cuts_its_prices(self):
        """The validators using it post new tables: the latest replaces the earlier, with no proposal or vote."""
        net, m, vs = market_net(5, family="anthropic")
        for v in vs:
            posts(m, v, anthropic__input=4.0)
        close(net, m)
        for v in vs:
            posts(m, v, anthropic__input=2.0)
        close(net, m)
        self.assertTrue(all(m.tables[v.vid][UNIT] == 2.0 for v in vs))
        self.assertAlmostEqual(m.prices[UNIT], 3.0)  # one 25 % step toward the new median
        self.assertEqual([n for n in dir(m) if n.lower().startswith(("set", "vote", "propose", "admin"))], [])

    def test_honest_validators_post_their_own_costs(self):
        net, m, vs = market_net(4)
        close(net, m)
        for v in vs:
            self.assertEqual(set(m.tables[v.vid]), set(M.family_units(v.family)) | set(M.SHARED_UNITS))
            self.assertAlmostEqual(m.tables[v.vid]["vcpu_second"] / m.genesis["vcpu_second"], m.factors(v.vid)[1])

    def test_candidates_suspended_and_leaving_validators_tables_dont_count(self):
        net, m, vs = market_net(3, family="anthropic")
        for v in vs:
            posts(m, v, anthropic__input=4.0)
        cand = net.reg.register(0.0, key="c", signer="c", bond=1250, proof="tdx", host="hc", family="anthropic",
                                operator="opc")
        m.post(cand, {UNIT: 400.0})
        leaver = activate(net, 10)
        m.post(leaver, {UNIT: 400.0})  # posted while active, then leaves
        net.leave(leaver)
        suspended = activate(net, 11)
        m.post(suspended, {UNIT: 400.0})
        suspended.state = CANDIDATE  # what the reveal-rate floor does
        close(net, m, 3)
        self.assertEqual(m.prices[UNIT], 4.0)

    def test_a_table_holds_units_only(self):
        net, m, vs = market_net(1)
        with self.assertRaises(ValueError):
            m.post(vs[0], {"service_fee": 1.0})
        with self.assertRaises(ValueError):
            m.post(vs[0], {UNIT: -1.0})


class TestMedian(unittest.TestCase):
    def test_one_validator_posts_an_absurd_price(self):
        """One of 15 posts a token price 100 times the others': the median doesn't change, nor the price."""
        net, m, vs = market_net(15, family="anthropic")
        for v in vs[1:]:
            posts(m, v, anthropic__input=4.0)
        posts(m, vs[0], anthropic__input=400.0)
        close(net, m, 5)
        self.assertEqual(m.prices[UNIT], 4.0)

    def test_a_real_price_drop(self):
        """Every posted price halves: the price falls by the step each period until it reaches the new median."""
        net, m, vs = market_net(5, family="anthropic")
        for v in vs:
            posts(m, v, anthropic__input=2.0)
        seen = []
        for _ in range(4):
            close(net, m)
            seen.append(m.prices[UNIT])
        self.assertEqual([round(x, 4) for x in seen], [3.0, 2.25, 2.0, 2.0])

    def test_too_few_tables(self):
        net, m, vs = market_net(3, family="anthropic")
        for v in vs[:2]:
            posts(m, v, anthropic__input=2.0)
        posts(m, vs[2], openai__input=1.0)
        close(net, m, 3)
        self.assertEqual(m.prices[UNIT], 4.0)
        self.assertEqual(m.prices["openai.input"], 2.0)  # one poster: unchanged too
        posts(m, vs[2], anthropic__input=2.0)
        close(net, m)
        self.assertAlmostEqual(m.prices[UNIT], 3.0)  # the third poster: it moves

    def test_never_above_twice_its_value_at_deployment(self):
        net, m, vs = market_net(3, family="anthropic")
        for v in vs:
            posts(m, v, anthropic__input=40.0)
        close(net, m, 10)
        self.assertEqual(m.prices[UNIT], 2 * 4.0)

    def test_an_even_count_and_the_lower_median(self):
        vals = [4.0, 4.0, 400.0, 400.0]
        self.assertEqual(M.step_price(4.0, 4.0, vals, P), 5.0)  # the mean of the middle two pulls it up a step
        self.assertEqual(M.step_price(4.0, 4.0, vals, replace(P, MEDIAN_LOW_EVEN=True)), 4.0)


class TestServiceFee(unittest.TestCase):
    def test_the_rule(self):
        self.assertAlmostEqual(M.step_fee(0.1, 20, 2, 10, 10, p=P), 0.105)  # 10 % waited: up a step
        self.assertAlmostEqual(M.step_fee(0.1, 20, 1, 10, 10, p=P), 0.1)  # exactly 5 % isn't more than WAIT_HIGH
        self.assertAlmostEqual(M.step_fee(0.1, 20, 0, 10, 1, p=P), 0.095)  # 90 % idle: down a step
        self.assertAlmostEqual(M.step_fee(0.1, 20, 0, 10, 2, p=P), 0.1)  # exactly 80 % idle: unchanged
        self.assertAlmostEqual(M.step_fee(0.1, 20, 2, 10, 0, p=P), 0.105)  # waiting outranks idling
        self.assertEqual(M.step_fee(0.25, 20, 5, 10, 10, p=P), 0.25)  # the ceiling
        self.assertEqual(M.step_fee(0.01, 0, 0, 10, 0, p=P), 0.01)  # the floor

    def test_not_enough_validators(self):
        """More than WAIT_HIGH of a period's submissions waited: the fee rises one step."""
        net, m, _ = market_net(mw=replace(STILL, fee_start=0.10))
        net.submit(1.0, 300.0, True, "s", None)  # the genesis alone: k = 1 judges up to $50, so it waits
        net.run()
        self.assertTrue(net.subs[2_000_000].waited)
        self.assertAlmostEqual(m.series[0]["fee"], 0.105)
        self.assertEqual(m.series[0]["waited"], 1.0)

    def test_too_many_idle_validators(self):
        """No submission waited and most active validators weren't drawn: the fee falls one step, to the floor at
        most."""
        net, m, _ = market_net(10, mw=replace(STILL, fee_start=0.0102))
        close(net, m, submitted=0)
        self.assertAlmostEqual(m.fee_now, 0.01)  # 0.0102 x 0.95 = 0.00969, held at the floor
        net2, m2, _ = market_net(10, mw=replace(STILL, fee_start=0.10))
        close(net2, m2)
        self.assertAlmostEqual(m2.fee_now, 0.095)


class TestNoVote(unittest.TestCase):
    def test_no_account_sets_a_price(self):
        """No setter; the bounds are the version's frozen parameters; a table can't carry a fee."""
        with self.assertRaises(FrozenInstanceError):
            P.FEE_CEILING = 1.0  # type: ignore[misc]
        net, m, vs = market_net(3)
        self.assertFalse(any(callable(getattr(m, n)) for n in dir(m) if "set" in n.lower() and n[:2] != "__"))

    def test_a_cartel_proposes_higher_fees(self):
        """There's nothing to vote on: refusing work gets its members replaced in the draw and their reveal rate
        lowered, and the fee doesn't rise."""
        a = M.in_market(M.Cartel(nodes=3, rate=1.0), replace(STILL, fee_start=0.10))
        w = replace(QUIET, weeks=3, subs_week=40.0)
        net = Net(1, P, w, [a])
        for i in range(10):
            activate(net, i, FAMS[i % 4])
        net.run()
        m = M.market_of(net)
        self.assertGreater(net.stats["refusals"], 6)
        self.assertEqual(net.stats["replaced"], net.stats["refusals"])  # every refusal replaced from the sample
        self.assertEqual(net.stats["waited"] + net.stats["stalled"], 0)
        self.assertTrue(all(len(s.judges) == s.k for s in net.subs.values() if s.verdict is not None))
        self.assertTrue(all(v.suspensions >= 1 for v in net.party_validators("cartel")))
        self.assertEqual(max(r["fee"] for r in m.series), 0.10)


class TestQuotes(unittest.TestCase):
    def test_prices_change_during_a_check(self):
        """The fee moves at the end of a period while a submission waits for its panel (it rises a step on the
        wait, then falls on the idle day the panel is drawn): it's charged the fee and the unit prices it was quoted
        when it started."""
        net, m, _ = market_net(mw=replace(STILL, fee_start=0.10), w=replace(QUIET, weeks=1))
        sub = net.submit(1.0, 200.0, True, "s", "solver")  # waits: the genesis alone judges up to $50
        late = []
        net._at(30.0, lambda: late.extend(activate(net, i, FAMS[i % 4]) for i in (1, 2, 3, 4)))
        net.run()
        self.assertIsNotNone(sub.draw)
        self.assertGreater(sub.drawn_t, DAY)
        self.assertAlmostEqual(m.quote(DAY)[0], 0.105)
        self.assertNotAlmostEqual(m.quote(sub.drawn_t)[0], 0.10)  # the fee had moved by the draw
        quoted, prices = m.quote(sub.t)
        self.assertEqual(quoted, 0.10)
        want = sum(quoted + M.usage_cost(prices, net.reg.validators[vid].family) for vid, _, _ in sub.judges)
        self.assertAlmostEqual(sub.charges, want)


class TestPricingAttackers(unittest.TestCase):
    """Each pricing attacker alone, as configured, against its twin on one seed (short runs)."""
    W = replace(WORLD, initial_active=0, joins_week=0.0, weeks=6)

    def twin_runs(self, make):
        a, t = make(False), make(True)
        return Net(1, P, self.W, [a]).run(), a, Net(1, P, self.W, [t]).run(), t

    def test_the_cartel_refuses_and_loses(self):
        na, a, nt, t = self.twin_runs(lambda h: M.Cartel(h))
        self.assertGreater(na.stats["refusals"], 0)
        self.assertEqual(nt.stats["refusals"], 0)
        self.assertGreater(sum(v.suspensions for v in na.party_validators("cartel")), 0)
        self.assertLess(na.party_net(a.party), nt.party_net(t.party))

    def test_the_spammer_fakes_waiting_and_raises_the_fee(self):
        mw = replace(M.MARKET, fee_start=0.05)
        na, a, nt, t = self.twin_runs(lambda h: M.in_market(M.Spammer(h), mw))
        spam = [s for s in na.subs.values() if s.party == "spammer"]
        self.assertTrue(spam and all(s.waited for s in spam))
        fa = [r["fee"] for r in M.market_of(na).series]
        ft = [r["fee"] for r in M.market_of(nt).series]
        self.assertGreater(sum(fa), sum(ft))
        self.assertLess(na.party_net(a.party), nt.party_net(t.party))

    def test_the_spammer_fakes_demand_with_judged_fixes(self):
        na, a, nt, t = self.twin_runs(lambda h: M.Spammer(h, kind="judged"))
        spam = [s for s in na.subs.values() if s.party == "spammer" and s.final is not None]
        self.assertTrue(spam and not any(s.final for s in spam))  # bad fixes, judged, failed
        self.assertGreater(na.stats["drawn"], nt.stats["drawn"])
        self.assertLess(na.party_net(a.party), nt.party_net(t.party))

    def test_inflaters_on_a_small_network_set_their_familys_price(self):
        na, a, nt, t = self.twin_runs(lambda h: M.Inflater(h, small=True))
        ma, mt = M.market_of(na), M.market_of(nt)
        self.assertEqual(ma.prices[UNIT], 2 * ma.genesis[UNIT])  # the cap
        self.assertLess(mt.prices[UNIT], 1.2 * mt.genesis[UNIT])
        self.assertGreater(sum(ma.led(v.vid).margin for v in na.party_validators("inflater")),
                           sum(mt.led(v.vid).margin for v in nt.party_validators("inflater")))

    def test_inflaters_are_a_minority_when_everyone_posts_every_family(self):
        mw = replace(M.MARKET, post_all_families=True)
        na, a, nt, t = self.twin_runs(lambda h: M.in_market(M.Inflater(h, small=True), mw))
        self.assertLess(M.market_of(na).prices[UNIT], 1.2 * M.market_of(na).genesis[UNIT])

    def test_the_fee_farmer_runs_idle_nodes(self):
        na, a, nt, t = self.twin_runs(lambda h: M.PricedFeeFarmer(h))
        self.assertEqual((len(na.party_validators("farmer")), len(nt.party_validators("farmer"))), (10, 1))
        self.assertLess(na.party_net(a.party), nt.party_net(t.party))


class TestTheFeeFindsCost(unittest.TestCase):
    def test_the_fee_settles_from_the_ceiling_toward_the_validators_cost(self):
        """Seed 1, no slash for an honest outage and IDLE_HIGH 50 % (the report's "moving" pricing): from the
        ceiling, the fee falls, validators leave and enter, and over the last 13 weeks it is within $0.05 of the
        break-even fee, above the marginal cost."""
        net = M.run_market(1, MOVING)
        m, st = M.market_of(net), M.settle(net)
        self.assertEqual(m.quotes[0][0], P.FEE_CEILING)
        self.assertLess(min(r["fee"] for r in m.series), 0.8 * P.FEE_CEILING)
        self.assertGreater(m.stats["left"], 0)
        self.assertGreater(m.stats["entered"], 0)
        self.assertLess(abs(st["fee"] - st["break_even"]), 0.05)
        self.assertGreater(st["fee"], st["marginal"])

    def test_at_the_design_values_it_stays_at_the_ceiling(self):
        """The report's finding, pinned: at the design's values the wait share stays above WAIT_HIGH (bounties whose
        bonds or k the network lacks), so the fee never leaves the ceiling for long."""
        net = M.run_market(1, P)
        st = M.settle(net)
        self.assertGreater(st["fee"], 0.24)
        self.assertGreater(st["waited"], P.WAIT_HIGH)

    def test_reproducible_on_a_fixed_seed(self):
        a, b = M.run_market(2, MOVING), M.run_market(2, MOVING)
        self.assertEqual(M.market_of(a).series, M.market_of(b).series)


if __name__ == "__main__":
    unittest.main()
