"""Tasks 5.1-5.3: specs/release-payouts, one test per scenario, each checking the ledger."""

import unittest

from pof import credits, share
from pof.challenges import Challenges, Proof, ValidatorSet, commitment
from pof.ledger import Ledger
from pof.lifecycle import Lifecycle
from pof.params import LEGACY, SPLIT_SHARES, ParamsError
from pof.payouts import DAYS_PER_MONTH, PayoutError, Releases


class Setup(unittest.TestCase):
    def setUp(self):
        L = self.ledger = Ledger()
        self.infra, self.insurance, self.owner = L.open("infrastructure"), L.open("insurance"), L.open("actor")
        self.devs = [L.open("actor") for _ in range(4)]
        self.challenger = L.open("actor")
        for a in self.devs + [self.challenger]:
            L.issue(a, credits(5_000), "endowment", "setup", 0)
        self.life = Lifecycle(L, LEGACY, self.infra)
        self.vset = ValidatorSet(L)
        self.vals = []
        for i in range(12):  # enough for 3 validators plus 7 jurors
            v = L.open("actor")
            L.issue(v, credits(200), "endowment", "setup", 0)
            self.vset.register(v, credits(50), 0)
            self.vals.append(v)
        self.ch = Challenges(L, LEGACY, self.life, self.vset, self.insurance, self.infra)
        self.rel = Releases(L, LEGACY, self.life, self.insurance, self.infra, self.owner, upstream_keys={"key-A"})

    def tearDown(self):
        self.assertTrue(self.ledger.conserved())

    def submitted(self, lines=(78, 78, 78, 78), day=1):
        out = []
        for dev, n in zip(self.devs, lines):
            c = self.life.submit(dev, n, day)
            self.life.run_checks(c, True, day)
            out.append(c)
        return out


class TestSplit(Setup):
    def test_split_adds_up(self):
        r = self.rel.open_release(1)
        self.assertEqual(sum(r.split.values()), LEGACY.release_funding)
        for name in SPLIT_SHARES:
            expected = share(LEGACY.release_funding, LEGACY.release_split_bps[name])
            if name == "insurance":
                self.assertGreaterEqual(r.split[name], expected)  # plus any rounding remainder
            else:
                self.assertEqual(r.split[name], expected)
        self.assertEqual(self.ledger.balance(self.rel.treasury), 0)

    def test_shares_cannot_change_mid_release(self):
        r = self.rel.open_release(1)
        split = dict(LEGACY.release_split_bps, contributors=4_000, validators=3_000)
        self.rel.publish(LEGACY.with_(release_split_bps=split), 3)
        self.assertEqual(r.params.release_split_bps["contributors"], 5_000)  # the open release keeps its set
        self.rel.close_release(r, [], 7)
        r2 = self.rel.open_release(8)
        self.assertEqual(r2.split["contributors"], share(LEGACY.release_funding, 4_000))
        event = self.ledger.events[-1]
        self.assertEqual((event.kind, event.time, event.ref), ("params", 3, "release:2"))


class TestContributors(Setup):
    def test_divided_among_contributions_entering_the_beta(self):
        self.rel.params = LEGACY.with_(reward_cap_stake_multiple=0)  # the division itself; the cap: test_indexed_stake
        r = self.rel.open_release(1)
        cs = self.submitted((78, 78, 300, 1_098))
        rewards = self.rel.ship_beta(r, cs, 1)
        pool = r.split["contributors"]
        weights = [LEGACY.reward_weight_for(c.changed_lines) for c in cs]  # linear in lines (proof-of-fix#10)
        for c, w in zip(cs, weights):
            self.assertEqual(rewards[c.id], pool * w // sum(weights))
            self.assertEqual(self.ledger.balance(c.escrow_account), rewards[c.id])

    def test_only_accepted_contributions_are_paid(self):
        r = self.rel.open_release(1)
        cs = self.submitted()
        rewards = self.rel.ship_beta(r, cs, 1)
        bad = cs[3]
        ch = self.ch.file(bad, self.challenger, Proof("regression", bad.id), "wrong_result", 2, "b")
        self.ch.finalize(ch, 2)
        for c in cs[:3]:
            self.life.advance(c, c.window_end)
        for c in cs[:3]:  # accepted; paid from the next release on, stake held until then (proof-of-fix#10, D9)
            self.assertEqual(c.state, "accepted")
            self.assertEqual(self.ledger.balance(c.escrow_account), rewards[c.id])
        self.assertNotIn(bad.contributor, [e.target for e in self.ledger.entries_for(bad.ref) if e.reason == "reward"])
        leftover = r.split["contributors"] - sum(rewards.values())
        back = rewards[bad.id] - share(rewards[bad.id], LEGACY.challenger_escrow_share_bps)  # half to the challenger
        self.assertEqual(self.ledger.balance(self.rel.contributors_pool), back + leftover)

    def test_unused_share_rolls_over(self):
        self.rel.params = LEGACY.with_(reward_cap_stake_multiple=0)  # the rollover itself; the cap: test_indexed_stake
        r1 = self.rel.open_release(1)
        self.rel.ship_beta(r1, [], 1)
        self.rel.close_release(r1, [], 7)
        r2 = self.rel.open_release(8)
        cs = self.submitted((78,), day=8)
        rewards = self.rel.ship_beta(r2, cs, 8)
        self.assertEqual(rewards[cs[0].id], r1.split["contributors"] + r2.split["contributors"])


class TestValidators(Setup):
    def test_overturned_verdict_earns_nothing(self):
        r = self.rel.open_release(1)
        cs = self.submitted((78,))
        self.rel.ship_beta(r, cs, 1)
        ch = self.ch.file(cs[0], self.challenger, Proof("flaky", cs[0].id, flaky=True), "wrong_result", 2, "b")
        validators = ch.panels[0].members
        for m in validators:
            self.ch.commit(ch, m, commitment(False, m))
        for m in validators:
            self.ch.reveal(ch, m, False, m)
        self.ch.close_voting(ch, 3)
        self.ch.appeal(ch, self.challenger, 4)
        jurors = ch.panels[1].members
        for m in jurors:
            self.ch.commit(ch, m, commitment(True, m))
        for m in jurors:
            self.ch.reveal(ch, m, True, m)
        self.ch.close_voting(ch, 5)
        self.ch.finalize(ch, 5)
        paid = self.rel.close_release(r, [ch], 7)
        self.assertFalse(set(paid) & set(validators))  # overturned: nothing from the pool
        self.assertEqual(set(paid), set(jurors))
        self.assertEqual(len(set(paid.values())), 1)  # one matching verdict each, equal shares

    def test_nothing_matched_rolls_over(self):
        r = self.rel.open_release(1)
        self.rel.close_release(r, [], 7)
        self.assertEqual(self.ledger.balance(self.rel.validators_pool), r.split["validators"])


class TestAuthorEscrow(Setup):
    def test_unclaimed_share_accrues(self):
        for i in range(3):
            r = self.rel.open_release(1 + 7 * i)
            self.rel.close_release(r, [], 7 + 7 * i)
        self.assertEqual(self.ledger.balance(self.rel.author_escrow), 3 * share(LEGACY.release_funding, 1_000))
        with self.assertRaises(PayoutError):
            self.rel.withdraw_author(30)
        self.assertNotIn("author", {a.split("-")[0] for a in self.ledger.accounts()})  # no address assigned

    def test_verified_claim(self):
        self.rel.open_release(1)
        account = self.rel.claim_author("key-A", "key-A", "key-A", 5)
        paid = self.rel.withdraw_author(5)
        self.assertEqual(self.ledger.balance(account), paid)
        self.assertEqual(paid, share(LEGACY.release_funding, 1_000))
        self.assertEqual(self.ledger.events[-1].kind, "author_claim")

    def test_unverified_claim(self):
        self.rel.open_release(1)
        before = self.ledger.balance(self.rel.author_escrow)
        for statement, commit in (("key-B", "key-B"), ("key-A", None), ("key-A", "key-B")):
            with self.assertRaises(PayoutError):
                self.rel.claim_author(statement, statement, commit, 5)
        self.assertEqual(self.ledger.balance(self.rel.author_escrow), before)
        self.assertIsNone(self.rel.author_account)


class TestOwner(Setup):
    def test_cap_enforced(self):
        split = dict(LEGACY.release_split_bps, owner=1_000, contributors=4_500)
        with self.assertRaises(ParamsError):
            self.rel.publish(LEGACY.with_(release_split_bps=split), 1)

    def test_vesting_and_leaving(self):
        r = self.rel.open_release(0)
        span = LEGACY.owner_vesting_months * DAYS_PER_MONTH
        self.assertEqual(self.rel.withdraw_owner(span // 2), r.split["owner"] // 2)
        forfeited = self.rel.owner_leaves(span // 2)
        self.assertEqual(forfeited, r.split["owner"] - r.split["owner"] // 2)
        self.rel.close_release(r, [], 7)
        r2 = self.rel.open_release(8)
        self.assertEqual(self.ledger.balance(self.rel.owner_vesting), 0)  # later shares go to insurance
        self.assertEqual(r2.split["owner"], share(LEGACY.release_funding, 500))

    def test_owner_cannot_validate_on_the_share(self):
        self.rel.open_release(0)
        self.rel.withdraw_owner(LEGACY.owner_vesting_months * DAYS_PER_MONTH)
        for i in range(50):
            self.assertNotIn(self.owner, self.vset.select(5, f"s{i}", set()))
        self.vset.register(self.owner, credits(50), 1)  # a separate validator stake, like anyone else
        picked = any(self.owner in self.vset.select(5, f"s{i}", set()) for i in range(50))
        self.assertTrue(picked)


class TestInfrastructureAndInsurance(Setup):
    def test_insurance_pays_out(self):
        r = self.rel.open_release(1)
        cs = self.submitted((78,))
        self.rel.ship_beta(r, cs, 1)
        ch = self.ch.file(cs[0], self.challenger, Proof("data loss", cs[0].id), "crash", 2, "b")
        self.ch.finalize(ch, 2)
        harmed = self.ledger.open("actor")
        paid = self.rel.pay_insurance(r, harmed, credits(1_000_000), ch, 3)
        self.assertEqual(paid, r.insurance_limit)
        self.assertEqual(self.rel.pay_insurance(r, harmed, credits(1), ch, 3), 0)  # the limit is spent

    def test_insurance_only_for_upheld_crashes(self):
        r = self.rel.open_release(1)
        cs = self.submitted((78,))
        self.rel.ship_beta(r, cs, 1)
        ch = self.ch.file(cs[0], self.challenger, Proof("typo", cs[0].id), "cosmetic", 2, "b")
        self.ch.finalize(ch, 2)
        with self.assertRaises(PayoutError):
            self.rel.pay_insurance(r, self.challenger, credits(1), ch, 3)

    def test_unspent_infrastructure_funds_roll_over(self):
        r = self.rel.open_release(1)
        self.rel.spend_infrastructure(credits(100), 2, "ci")
        self.rel.close_release(r, [], 7)
        self.rel.open_release(8)
        self.assertEqual(self.ledger.balance(self.infra), 2 * r.split["infrastructure"] - credits(100))


if __name__ == "__main__":
    unittest.main()
