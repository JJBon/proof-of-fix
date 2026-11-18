"""#138 task 3.5 (pof/sim/openval/contract.py): group 7's market in FeesV3's integers, exported for RaceV3's replay
(contracts/test/v3/ReplayV3.t.sol). The integer rules are FeesV3's; the files the replay reads are what the exporter
writes on their seeds; and the runs the replay can't follow exactly are refused by name."""

import json
import os
import unittest

from pof.sim.openval import contract as K
from pof.sim.openval.params import V2R2

DATA = os.path.join(os.path.dirname(__file__), "..", "contracts", "test", "data")
REPLAYS = ((1, 4), (2, 8), (3, 8), (4, 8))  # (seed, weeks) of each file ReplayV3.t.sol reads


class Rules(unittest.TestCase):
    def test_stepPriceIsFeesV3s(self):
        # at most 25 % of itself, the lower bound rounded up; never above twice the first price
        self.assertEqual(K.step_price(1_000, 1_000, 10), 750)
        self.assertEqual(K.step_price(1_001, 1_000, 0), 751)  # 750.75 rounds up
        self.assertEqual(K.step_price(1_000, 1_000, 5_000), 1_250)
        self.assertEqual(K.step_price(1_900, 1_000, 5_000), 2_000)  # the cap
        self.assertEqual(K.step_price(1_000, 1_000, 1_100), 1_100)

    def test_stepFeeIsFeesV3s(self):
        self.assertEqual(K.step_fee(250_000, 100, 6, 10, 10), 250_000)  # rises, capped at the ceiling
        self.assertEqual(K.step_fee(200_001, 100, 6, 10, 10), 210_001)  # 210,001.05 rounds down
        self.assertEqual(K.step_fee(200_001, 100, 5, 10, 5), 190_000)  # 190,000.95 rounds down; 5 % isn't more
        self.assertEqual(K.step_fee(10_000, 0, 0, 10, 0), 10_000)  # the floor
        self.assertEqual(K.step_fee(100_000, 0, 0, 10, 60), 100_000)  # seated capped at the active count

    def test_aTableIsPostedInIntegers(self):
        self.assertEqual(K.micro_of("anthropic.input", 4.0), 4_000_000)  # $4 per million tokens
        self.assertEqual(K.micro_of("vcpu_second", 1.1244444444444444e-05), 11_244_444)
        self.assertEqual(K.micro_of("storage_mb", 0.00026953125), 269_531_250)

    def test_theMarketMustHaveFeesV3sRules(self):
        from dataclasses import replace
        with self.assertRaises(K.ExportError):
            K.run(1, 1, replace(V2R2, IDLE_HIGH=0.5))


class Exports(unittest.TestCase):
    def test_theReplaysFilesAreTheExportersOnTheirSeeds(self):
        for seed, weeks in REPLAYS:
            with open(os.path.join(DATA, f"v3-replay-{seed}.json")) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk, json.loads(json.dumps(K.export(seed, weeks))), f"seed {seed}")

    def test_anExportIsReproducible(self):
        self.assertEqual(K.export(2, 2), K.export(2, 2))

    def test_thePaysAreFeesV3sAtTheQuote(self):
        net, rec = K.run(3, 2)
        m = net.fee
        counted = [e for e in rec.events if e["kind"] == "counted"]
        self.assertTrue(counted)
        for e in counted:
            sub = net.subs[e["sid"]]
            for vid, micro in zip(e["vids"], e["micro"]):
                usage, fee = m.pay_micro(net.reg.validators[vid].family, m.epoch_of(sub.t))
                self.assertEqual(micro, usage + fee)

    def test_theFeeMovesBothWays(self):
        _, rec = K.run(2, 8)
        fees = [e["fee"] for e in rec.events if e["kind"] == "close"]
        self.assertTrue(any(b > a for a, b in zip(fees, fees[1:])))
        self.assertTrue(any(b < a for a, b in zip(fees, fees[1:])))

    def test_runsTheReplayCantFollowAreRefused(self):
        with self.assertRaisesRegex(K.ExportError, "waits in the first period"):
            K.export(5, 2)
        with self.assertRaisesRegex(K.ExportError, "not active at its close"):
            K.export(1, 8)


if __name__ == "__main__":
    unittest.main()
