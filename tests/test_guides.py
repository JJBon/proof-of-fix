"""The onboarding guides (docs/guides/, #251 task 5.7), without Docker: every command block the devnet test
(tests/integration/guides_radicle.py, `scripts/radicle-spike.sh --guides`) runs is one it knows how to run, and the
guides keep to the launch's rules (a keystore, never a devnet key; the test coin said to have no value)."""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import guides_radicle as G  # noqa: E402

VALUES = {"POFCTL_RPC", "RID", "RECORD", "BOUNTY", "FAMILY", "ORACLE_VERSION", "ORACLE_RPC",
          "DSTACK_SIMULATOR_ENDPOINT"}


class Guides(unittest.TestCase):
    def guides(self):
        return {name: G.blocks(G.GUIDES / f"{name}.md") for name in G.NEWCOMERS}

    def test_each_guide_has_commands_and_a_newcomer(self):
        self.assertEqual(sorted(p.stem for p in G.GUIDES.glob("*.md")), sorted(G.NEWCOMERS))
        for name, blocks in self.guides().items():
            with self.subTest(name):
                self.assertGreaterEqual(len([b for b in blocks if b["lang"] == "bash"]), 5)

    def test_every_marker_is_one_the_test_runs(self):
        for name, blocks in self.guides().items():
            for b in blocks:
                m = b["marker"]
                if not m or m.startswith("skip (") or m in ("values", "devnet-values"):
                    continue
                with self.subTest(name=name, line=b["line"]):
                    self.assertTrue(hasattr(G.GuideStory, "hook_" + m.replace("-", "_")), m)

    def test_values_blocks_set_only_what_the_test_replaces(self):
        for name, blocks in self.guides().items():
            for b in blocks:
                if b["marker"] in ("values", "devnet-values"):
                    with self.subTest(name=name, line=b["line"]):
                        self.assertEqual(b["lang"], "bash")
                        names = set(re.findall(r"\b([A-Z_]+)=", b["code"]))
                        self.assertTrue(names and names <= VALUES, names - VALUES)
            self.assertEqual(blocks[[b["lang"] for b in blocks].index("bash")]["marker"], "values",
                             f"{name}: its first command block is its values")

    def test_no_devnet_key_and_the_coin_has_no_value(self):
        for name in G.NEWCOMERS:
            text = (G.GUIDES / f"{name}.md").read_text(encoding="utf-8")
            with self.subTest(name):
                self.assertNotRegex(text, r"--as\b|DEVNET_KEYS|POFCTL_KEY_")
                self.assertIn("which has no value", " ".join(text.split()))
                self.assertNotRegex(text.lower(), r"\bearn|\bprofit|\bincome")

    def test_the_parser_reads_markers_only_right_before_a_block(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "guide.md"
        path.write_text("<!-- test: gas -->\nsome words\n```bash\necho a\n```\n\n<!-- test: skip (x) -->\n\n"
                        "```bash\necho b\n```\n```text\nout\n```\n", encoding="utf-8")
        got = [(b["lang"], b["code"], b["marker"]) for b in G.blocks(path)]
        self.assertEqual(got, [("bash", "echo a\n", None), ("bash", "echo b\n", "skip (x)"), ("text", "out\n", None)])


if __name__ == "__main__":
    unittest.main()
