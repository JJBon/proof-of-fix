"""The integration suite's panel interface (tests/integration/panel.py; proof-of-fix#140, task 5.0 of #132): v2's fixed
draw and v3's counted panel answer the same questions, and scripts/integration.sh picks the version."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from oracle import v3  # noqa: E402
from oracle.rpc import Wallet  # noqa: E402
from panel import PanelV2, PanelV3  # noqa: E402

A, B, C, D = ("0x" + c * 40 for c in "abcd")


class ChainV2:
    def submission(self, s):
        return {"seed": "0x" + "11" * 32, "bounty": 7}

    def drawn(self, seed, bounty, s):
        assert (seed, bounty, s) == ("0x" + "11" * 32, 7, 5)
        return [A, B, C], [D]  # D was recused on the way


class ChainV3:
    def __init__(self, status=v3.WINDOW, k=3, pid=4, shadow=0):
        self.v = {"status": status, "k": k, "pid": pid, "shadowPid": shadow}
        self.panels = {4: [A, "", C], 9: [D]}  # an empty seat: a reveal missed after the majority revealed

    def verdict(self, s):
        return self.v

    def judges(self, pid):
        return self.panels[pid]


class PanelInterface(unittest.TestCase):
    def test_v2_reads_the_fixed_draw_and_doesnt_replace(self):
        p = PanelV2(ChainV2())
        self.assertEqual((p.drawn(5), p.size(5), p.decides(5)), ([A, B, C], 3, 2))
        self.assertEqual((p.reports(5), p.reports(5, silent=1), p.replaces_silent()), (3, 2, False))

    def test_v3_reads_the_counted_panel_and_replaces(self):
        p = PanelV3(ChainV3(shadow=9))
        self.assertEqual((p.drawn(5), p.size(5), p.decides(5)), ([A, C], 3, 2))
        self.assertEqual((p.reports(5), p.reports(5, silent=1), p.replaces_silent()), (3, 3, True))
        self.assertEqual((p.shadows(5), p.waiting(5)), ([D], False))
        for k, need in ((1, 1), (5, 3), (7, 4)):
            self.assertEqual(PanelV3(ChainV3(k=k)).decides(5), need)

    def test_a_waiting_v3_submission_has_no_panel(self):
        p = PanelV3(ChainV3(status=v3.WAITING, k=0, pid=0))
        self.assertEqual((p.drawn(5), p.shadows(5), p.waiting(5)), ([], [], True))

    def test_both_answer_the_same_questions(self):
        for name in ("drawn", "size", "decides", "reports", "replaces_silent"):
            self.assertTrue(callable(getattr(PanelV2, name)) and callable(getattr(PanelV3, name)), name)


class IntegrationVersion(unittest.TestCase):
    def run_sh(self, *args):
        return subprocess.run(["bash", str(ROOT / "scripts" / "integration.sh"), *args], capture_output=True, text=True,
                              timeout=60)

    def test_an_unknown_version_is_refused(self):
        r = self.run_sh("--version", "4")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown version 4", r.stderr)

    def test_v3_on_aws_is_refused_before_anything_starts(self):
        r = self.run_sh("--target", "aws", "--version", "3")
        self.assertEqual(r.returncode, 2)
        self.assertIn("task 5.2", r.stderr)

    def test_the_wallet_polls_for_a_receipt_every_400_ms_unless_a_test_chain_says_sooner(self):
        self.assertEqual(Wallet.poll_s, 0.4)


if __name__ == "__main__":
    unittest.main()
