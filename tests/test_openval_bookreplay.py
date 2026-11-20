"""#251 contract batch 3 (pof/sim/openval/bookreplay.py): report v5's R(minus)+F rows and the launch's pledge gate,
exported for SolverBook's replay (contracts/test/v3/ReplaySolversV3.t.sol). The files the replay reads are what the
exporter writes on their seeds; the export's integer mirror follows the contract's rules; and a run whose float cap
decision differs from the integer one is refused."""

import json
import os
import unittest

from pof.sim.openval import bookreplay as B

DATA = os.path.join(os.path.dirname(__file__), "..", "contracts", "test", "data")
REPLAYS = (("L", 1), ("YS", 1))  # the files ReplaySolversV3.t.sol reads


class Exports(unittest.TestCase):
    def test_theReplaysFilesAreTheExportersOnTheirSeeds(self):
        for row, seed in REPLAYS:
            with open(os.path.join(DATA, f"v3-book-{row}-{seed}.json")) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk, json.loads(json.dumps(B.export(row, seed))), f"{row} seed {seed}")

    def test_theLongConsReputationRisesAndFalls(self):
        o = B.export("L", 1)
        self.assertFalse(o["gate"])
        k = o["byKind"]
        self.assertGreater(k["pass"], 0)
        self.assertGreater(k["reversed"], 0)  # its bad fixes are reversed: twice their bounty off
        reps = [r for kind, r in zip(o["kinds"], o["reps"]) if kind == B.PASS]
        self.assertGreater(max(reps), B.REP_BASE)  # it may claim more than a new identity after farming

    def test_theSybilsGateIsCounted(self):
        o = B.export("YS", 1)
        self.assertTrue(o["gate"])
        self.assertEqual(o["activeWindow"], 26 * 7 * 24 * 3600)
        counts = [c for kind, c in zip(o["kinds"], o["counts"]) if kind == B.GATE]
        self.assertTrue(counts)
        self.assertTrue(any(c < 3 for c in counts) and any(c >= 3 for c in counts))  # locked, then unlocked
        self.assertEqual(o["gateDiffers"], 0)  # the contract's narrower rule decided every gate as the run did

    def test_timesAreInOrder(self):
        for row, seed in REPLAYS:
            ts = B.export(row, seed)["ts"]
            self.assertEqual(ts, sorted(ts))


class Mirror(unittest.TestCase):
    def test_theIntegerMirrorIsTheContracts(self):
        actor, w, p = B.row("L")
        net = B.TraceNet(1, p, actor.world(), [actor]).run()
        for idt, i in net.who.items():
            self.assertAlmostEqual(net.rep[idt] * 1e6, net.irep.get(i, 0), delta=2)
            self.assertGreaterEqual(net.iopen.get(i, 0), 0)

    def test_aFloatDecisionTheIntegersDontShareIsRefused(self):
        actor, w, p = B.row("L")
        net = B.TraceNet(1, p, actor.world(), [actor])
        orig = net.ident

        def ident(sub):
            idt = orig(sub)
            if idt is not None:
                net.irep[net._id(idt)] = -10 ** 12  # the mirror now refuses what the run admits
            return idt
        net.ident = ident
        with self.assertRaises(B.Unfollowable):
            net.run()

    def test_microAndSeconds(self):
        self.assertEqual(B.micro(40.0), 40_000_000)
        self.assertEqual(B.micro(0.0000004), 0)
        self.assertEqual(B.seconds(1.5), 5400)


if __name__ == "__main__":
    unittest.main()
