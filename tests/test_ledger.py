"""Task 2.1: specs/ledger, one test per scenario."""

import random
import unittest

from pof import credits
from pof.ledger import Ledger, LedgerError


def funded(*kinds):
    ledger = Ledger()
    accounts = [ledger.open(k) for k in kinds]
    ledger.issue(accounts[0], credits(100), "endowment", "setup", 0)
    return ledger, accounts


class TestSimulatedCreditsOnly(unittest.TestCase):
    def test_accounts_are_pseudonymous(self):
        ledger = Ledger()
        a, b = ledger.open("actor"), ledger.open("actor")
        self.assertEqual((a, b), ("actor-00001", "actor-00002"))
        for bad in ("Alice", "juan@example.com", "0xAbC123", "actor 1", ""):
            with self.assertRaises(LedgerError):
                ledger.open(bad)

    def test_credits_only_issued_as_funding_or_endowment(self):
        ledger = Ledger()
        a = ledger.open("actor")
        with self.assertRaises(LedgerError):
            ledger.issue(a, credits(1), "gift", "x", 0)
        ledger.issue(a, credits(1), "release_funding", "release:1", 0)
        self.assertEqual(ledger.total_issued, credits(1))


class TestAppendOnly(unittest.TestCase):
    def test_entries_carry_time_reason_and_ref(self):
        ledger, (a, b) = funded("actor", "stake")
        e = ledger.transfer(a, b, credits(10), "stake", "contribution:1", 3)
        self.assertEqual((e.time, e.reason, e.ref, e.source, e.target), (3, "stake", "contribution:1", a, b))

    def test_correction_is_a_new_entry(self):
        ledger, (a, b) = funded("actor", "escrow")
        wrong = ledger.transfer(a, b, credits(30), "escrow", "contribution:1", 1)
        reversal = ledger.reverse(wrong.seq, 2)
        ledger.transfer(a, b, credits(3), "escrow", "contribution:1", 2)
        self.assertEqual(reversal.reverses, wrong.seq)
        self.assertIn(wrong, ledger.entries)  # the original stays visible
        self.assertEqual(ledger.balance(b), credits(3))
        with self.assertRaises(LedgerError):
            ledger.reverse(wrong.seq, 3)  # once only

    def test_entries_cannot_be_edited(self):
        ledger, (a, b) = funded("actor", "stake")
        e = ledger.transfer(a, b, credits(1), "stake", "c", 0)
        with self.assertRaises(AttributeError):
            e.amount = credits(1000)
        self.assertIsInstance(ledger.entries, tuple)


class TestConservation(unittest.TestCase):
    def test_balances_add_up_after_any_sequence(self):
        rng = random.Random(14)
        ledger = Ledger()
        accounts = [ledger.open(k) for k in ("actor",) * 6 + ("escrow", "stake", "insurance", "treasury")]
        moved = []
        for step in range(3_000):
            op = rng.random()
            if op < 0.1:
                ledger.issue(rng.choice(accounts), rng.randint(1, credits(50)), "endowment", "x", step)
            elif op < 0.85:
                src, dst = rng.sample(accounts, 2)
                try:
                    moved.append(ledger.transfer(src, dst, rng.randint(1, credits(20)), "payout", "x", step))
                except LedgerError:
                    pass  # refused: nothing recorded
            elif moved:
                try:
                    ledger.reverse(rng.choice(moved).seq, step)
                except LedgerError:
                    pass
            self.assertTrue(ledger.conserved(), f"step {step}")
        self.assertTrue(all(ledger.balance(a) >= 0 for a in accounts))

    def test_no_negative_balances(self):
        ledger, (a, b) = funded("actor", "actor")
        before = ledger.entries
        with self.assertRaises(LedgerError):
            ledger.transfer(a, b, credits(100) + 1, "payout", "x", 1)
        self.assertEqual(ledger.entries, before)
        self.assertEqual(ledger.balance(a), credits(100))

    def test_bad_amounts_refused(self):
        ledger, (a, b) = funded("actor", "actor")
        for amount in (0, -1, 1.5, True):
            with self.assertRaises(LedgerError):
                ledger.transfer(a, b, amount, "payout", "x", 1)


class TestAuditableSettlements(unittest.TestCase):
    def test_recompute_a_settlement_from_its_entries(self):
        ledger = Ledger()
        contributor, stake, escrow, treasury, challenger, insurance = (
            ledger.open(k) for k in ("actor", "stake", "escrow", "treasury", "actor", "insurance")
        )
        ledger.issue(contributor, credits(50), "endowment", "setup", 0)
        ledger.issue(treasury, credits(100), "release_funding", "release:1", 0)
        ref = "contribution:7"
        ledger.transfer(contributor, stake, credits(20), "stake", ref, 1)
        ledger.transfer(treasury, escrow, credits(8), "escrow", ref, 2)
        # slashed at 50 %: half the stake forfeited (half of it to the challenger, half to insurance)
        ledger.transfer(stake, challenger, credits(5), "slash", ref, 9)
        ledger.transfer(stake, insurance, credits(5), "slash", ref, 9)
        ledger.transfer(stake, contributor, credits(10), "refund", ref, 9)
        ledger.transfer(escrow, treasury, credits(8), "refund", ref, 9)
        ledger.transfer(treasury, contributor, credits(1), "payout", "release:1", 9)  # another ref, left out

        net = Ledger.net(ledger.entries_for(ref))
        self.assertEqual(net, {contributor: -credits(10), stake: 0, escrow: 0, treasury: 0,
                               challenger: credits(5), insurance: credits(5)})
        self.assertEqual(ledger.balance(challenger), credits(5))
        self.assertTrue(all(e.ref == ref for e in ledger.entries_for(ref)))


if __name__ == "__main__":
    unittest.main()
