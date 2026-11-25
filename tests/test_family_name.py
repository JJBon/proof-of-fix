"""One family name, `provider/line` (proof-of-fix#251, v3.1 polish VP12, F10 in the node): `register` refuses an
ORACLE_FAMILY in another form unless that exact name is already priced on the deployment (live v3's
`anthropic.claude`), and says then that v3.1 renames it. On test_oracle_v3's fake chain; nothing is sent when refused."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # test_oracle_v3's fakes

from oracle import node_v3, v3  # noqa: E402
from oracle.node_v3 import SetupError  # noqa: E402
from test_oracle_v3 import IMAGE, FakeChain, FakeWallet, SimKeys  # noqa: E402


class FamilyName(unittest.TestCase):
    def register(self, chain, family, logs):
        keys = SimKeys(0)
        with tempfile.TemporaryDirectory() as tmp:
            return node_v3.register(chain, keys, FakeWallet(chain, keys.address()), 100 * 10**6, Path(tmp),
                                    log=logs.append, proof="simulated", family=family, host="home", image=IMAGE)

    def test_the_provider_line_form_is_accepted(self):
        chain, logs = FakeChain(), []
        r = self.register(chain, "anthropic/claude", logs)  # not priced here: the form is enough
        self.assertEqual(r.family, v3.name_id("anthropic/claude"))
        self.assertIn("register", chain.names())
        self.assertFalse(any("renames" in x for x in logs))
        for good in ("openai/gpt", "google/gemini-2.5", "meta-llama/llama3.1", "x/y"):
            node_v3.check_family(chain, good, logs.append)

    def test_the_dotted_name_on_a_deployment_that_prices_it(self):
        chain, logs = FakeChain(), []
        chain.priced = [v3.name_id("fake"), v3.name_id("anthropic.claude")]  # live v3's
        r = self.register(chain, "anthropic.claude", logs)
        self.assertEqual(r.family, v3.name_id("anthropic.claude"))
        self.assertIn("register", chain.names())
        self.assertIn("family 'anthropic.claude' is accepted because this deployment prices it; v3.1 renames it "
                      "'anthropic/claude' (one form: provider/line)", logs)

    def test_the_dotted_name_on_a_deployment_that_doesnt_price_it(self):
        chain, logs = FakeChain(), []
        with self.assertRaises(SetupError) as caught:
            self.register(chain, "anthropic.claude", logs)
        self.assertIn("isn't in the provider/line form", str(caught.exception))
        self.assertIn("anthropic/claude", str(caught.exception))
        self.assertIn(node_v3.FAMILY_FORM.pattern, str(caught.exception))
        self.assertEqual(chain.txs, [])  # refused before anything is sent
        for bad in ("Anthropic/Claude", "anthropic", "/claude", "anthropic/", "anthropic/claude/x", "a b/c", ""):
            with self.assertRaises(SetupError, msg=bad):
                node_v3.check_family(chain, bad, logs.append)

    def test_a_devnets_priced_name_is_accepted_quietly(self):
        chain, logs = FakeChain(), []  # prices "fake", as a devnet's LOCAL_FAMILIES do
        self.register(chain, "fake", logs)
        self.assertIn("register", chain.names())
        self.assertFalse(any("renames" in x for x in logs))


if __name__ == "__main__":
    unittest.main()
