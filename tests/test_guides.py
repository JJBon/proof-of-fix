"""The onboarding guides (docs/guides/, #251 task 5.7), without Docker: every command block the devnet test
(tests/integration/guides_radicle.py, `scripts/radicle-spike.sh --guides`) runs is one it knows how to run, and the
guides keep to the launch's rules (a keystore, never a devnet key; the test coin said to have no value)."""

from __future__ import annotations

import json
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



WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
README = ROOT / "README.md"
TAKE_PART = ROOT / "docs" / "take-part.md"
# The live deployment the guides name: v3.1 (2026-11-25, block 12211341), which superseded v3 (`sepolia-v3.json`).
RECORD = ROOT / "contracts" / "deployments" / "sepolia-v3.1.json"
PLAN = ROOT / "contracts" / "deployments" / "sepolia-v3.1.plan.json"


def flat(path: Path) -> str:
    """A doc's text on one line, without emphasis: what a reader reads, not how it wraps."""
    return " ".join(path.read_text(encoding="utf-8").replace("**", "").split())


def constant(source: str, name: str) -> int:
    """A `uint256 ... constant NAME = N;` read from contracts/src/v3 (`50e6` and `1_000` forms too)."""
    m = re.search(rf"constant {name} = ([0-9_e]+);", (ROOT / "contracts" / "src" / "v3" / source).read_text())
    assert m, f"{name} not found in {source}"
    return int(float(m.group(1).replace("_", "")))


def hold_counts() -> dict:
    """What a held k = 1 verdict needs (PanelsVerdict._challengersReady: challengeK(1) + auditsDue - auditsDrawn +
    (auditDecided ? 0 : 1)), outside its panel and auditors, and in all."""
    hold_k, audits = constant("PanelsDraw.sol", "HOLD_K"), constant("PanelsBase.sol", "K1_AUDITS")
    before = hold_k + audits + 1  # the random audit still undecided counts one more
    return {"before": before, "beforeAll": before + 1, "after": hold_k, "afterAll": hold_k + 1 + audits}


class Numbers(unittest.TestCase):
    """The numbers the docs state, against the contracts' source and the deployment record (v3.1 polish VP14, VP21)."""

    def setUp(self):
        self.record = json.loads(RECORD.read_text(encoding="utf-8"))
        self.guides = {name: G.GUIDES / f"{name}.md" for name in G.NEWCOMERS}

    def test_the_holds_count(self):
        """F7: six outside the panel before the audits are drawn (seven in all), three outside the judge and its
        auditors after (six in all); below it everything stays held, at it one pause holds them all."""
        n = hold_counts()
        self.assertEqual(n, {"before": 6, "beforeAll": 7, "after": 3, "afterAll": 6})
        for path in (README, TAKE_PART, G.GUIDES / "run-a-validator.md"):
            text = flat(path).lower()
            with self.subTest(path.name):
                self.assertIn(f"{WORDS[n['before']]} eligible validators outside its panel", text)
                self.assertIn(f"({WORDS[n['beforeAll']]} in all, with the judge)", text)
                self.assertIn(f"{WORDS[n['after']]} outside the judge and its auditors", text)
                self.assertIn(f"({WORDS[n['afterAll']]} in all, with two auditors)", text)
                self.assertIn("one validator pausing", text)
                self.assertIn("holds them all", text)
                self.assertIn("every lone verdict stays held", text)
        self.assertEqual(constant("PanelsBase.sol", "K1_AUDITS"), WORDS.index("two"))

    def test_no_three_validators_outside_the_panel_remains(self):
        for path in [README, *sorted((ROOT / "docs").rglob("*.md"))]:
            with self.subTest(path.relative_to(ROOT).as_posix()):
                self.assertNotRegex(flat(path), r"(?i)\b(3|three) validators outside the panel")
                self.assertNotIn("fewer than 3 validators", flat(path))

    def test_the_newcomers_ceiling(self):
        """F6: REP_BASE at the record's opening share, with the finder's fee on top (capOf = held / (1 + fee))."""
        config = self.record["constructorArgs"]["RaceV3"]["config"]
        config = json.loads(config) if isinstance(config, str) else config
        share, fee = config["startPriceBps"] / 10_000, config["finderFeeBps"] / 10_000
        rep_base = constant("SolverBook.sol", "REP_BASE") / 1e6
        ceiling = rep_base / share * (1 + fee)
        self.assertEqual((rep_base, share, fee), (50, 0.5, 0.1765))
        stated = f"about {int(ceiling * 10) / 10:.1f} coins"
        self.assertEqual(stated, "about 117.6 coins")
        for path in (TAKE_PART, self.guides["submit-a-fix"]):
            text = flat(path)
            with self.subTest(path.name):
                self.assertIn(stated, text)
                self.assertIn(f"up to {rep_base:g} coins (`REP_BASE`", text)
                self.assertIn(f"opening share ({share * 100:g} %) and finder's fee ({fee * 100:g} %)", text)
                self.assertIn("funds less the registration fee", text)
                self.assertIn("Pledges made after you start still raise the claim", text)
                self.assertIn("record the attempt first", text)
                self.assertIn("check `pofctl status`' room", text)

    def test_the_timing(self):
        """VP21: minutes to a verdict on v3.1 once every seat has sealed; at most about 2-3 h when a seat doesn't seal
        (the seal window, then the reveal, and the count); then held until 6-7 validators with room; 7 days of
        challenges at k = 1. The windows are v3.1's record's."""
        w = self.record["windows"]
        seal_h, reveal_h = w["seal"] / 3600, w["reveal"] / 3600
        self.assertEqual((seal_h, reveal_h), (2, 1))
        n = hold_counts()
        hold = f"held until {n['afterAll']}–{n['beforeAll']} validators with room"
        for path in (TAKE_PART, *self.guides.values()):
            text = flat(path)
            with self.subTest(path.name):
                self.assertIn(f"about {seal_h:g}–{seal_h + reveal_h:g} hours", text)
                self.assertIn(f"the {seal_h:g}-hour seal window, then the reveal (up to an hour) and the count", text)
                self.assertIn("as soon as every seat has sealed", text)
                self.assertIn(hold, text)
        k1_days = w["k1Min"] / 86400
        for path in (TAKE_PART, self.guides["submit-a-fix"], self.guides["fund-an-issue"],
                     self.guides["run-a-validator"]):
            with self.subTest(path.name):
                self.assertIn(f"waits {k1_days:g} days for challenges", flat(path))


class Commands(unittest.TestCase):
    """The v3.1 polish's commands in the guides (task 7.3) and the keeper's docs (task 7.4)."""

    def test_the_guides_use_pofctls_own_commands(self):
        fund, solve = flat(G.GUIDES / "fund-an-issue.md"), flat(G.GUIDES / "submit-a-fix.md")
        for name in G.NEWCOMERS:  # `issue register --title` opens the issue: no scraping of `rad issue open`'s box
            for b in G.blocks(G.GUIDES / f"{name}.md"):
                self.assertFalse("rad issue open" in b["code"] and "awk" in b["code"], f"{name}:{b['line']}")
        self.assertIn("issue register --title", fund)
        self.assertIn("issue show --issue", fund)
        for text in (fund, solve):
            self.assertIn("pofctl --v3 draw", text.replace('"$POFCTL"', "pofctl").replace("scripts/pofctl", "pofctl"))
            self.assertIn("if no validator draws it within 10 minutes", text)
            self.assertIn('"address": "%s"', text)  # status reads the address from pofctl.json: no password
            self.assertIn("asks for no password", text)

    def test_the_v31_family_and_v3_as_history(self):
        """Task 11.3: the guides name v3.1's family `anthropic/claude`; the dotted name and v3's
        `ORACLE_LIST_PRICES = "{}"` stay only in the notes on the superseded v3."""
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        self.assertEqual(plan["families"], ["anthropic/claude"])
        guide = G.GUIDES / "run-a-validator.md"
        text = guide.read_text(encoding="utf-8")
        self.assertIn("export FAMILY=anthropic/claude", text)
        self.assertIn('ORACLE_FAMILY      = "anthropic/claude"', text)
        self.assertNotIn("ORACLE_LIST_PRICES", text)
        take = flat(TAKE_PART)
        history = take[take.index("Earlier deployments (history only)."):take.index("## Pick a role")]
        self.assertIn('`ORACLE_LIST_PRICES = "{}"`', history)
        self.assertIn("`anthropic.claude`", history)
        self.assertNotIn("anthropic.claude", take.replace(history, ""))
        for name in G.NEWCOMERS:
            text = flat(G.GUIDES / f"{name}.md")
            with self.subTest(name):
                self.assertEqual(text.count("anthropic.claude"), 1 if name == "run-a-validator" else 0)

    def test_the_guides_name_the_live_deployment(self):
        """The values the guides give are v3.1's record's and plan's: its RID, record, branch, RaceV3, first block and
        the disk image its plan lists; v3 and its repository appear only as history."""
        record = json.loads(RECORD.read_text(encoding="utf-8"))
        plan = json.loads(PLAN.read_text(encoding="utf-8"))
        rel = RECORD.relative_to(ROOT).as_posix()
        race, block = record["addresses"]["race"], record["block"]
        self.assertEqual((plan["rid"], plan["genesisHead"]), (record["rid"], record["genesisHeadCheck"]["commit"]))
        short = f"RaceV3 {race[:6]}…{race[-4:].lower()}, block {block}"
        for name in G.NEWCOMERS:
            text = (G.GUIDES / f"{name}.md").read_text(encoding="utf-8")
            with self.subTest(name):
                self.assertIn(f"export RID={record['rid']}", text)
                self.assertIn(f"export RECORD={rel}", text)
                self.assertIn("git checkout -b sepolia-v3.1 asclepius/sepolia-v3.1", text)
                self.assertIn(short, text)
        validator = (G.GUIDES / "run-a-validator.md").read_text(encoding="utf-8")
        self.assertEqual(plan["images"], [plan["genesisValidator"]["image"]])
        image = plan["images"][0]
        self.assertIn(f"It must print `{image}`", validator)
        self.assertIn(f'ORACLE_IMAGE       = "{image}"', validator)
        self.assertIn(f'ORACLE_RACE        = "{race}"', validator)
        self.assertIn(f'ORACLE_FROM_BLOCK  = "{block}"', validator)
        self.assertIn(f'ORACLE_RADICLE_RID = "{record["rid"]}"', validator)
        self.assertIn(f"the record's `commit` ({record['commit'][:7]}…)", validator.replace("The record's", "the record's"))
        take = TAKE_PART.read_text(encoding="utf-8")
        for s in (f"`{record['rid']}`", f"first block {block}", f"RaceV3 `{race}`",
                  f"registry `{record['addresses']['registry']}`", f"[`{rel}`]", f"image digest `{image}`"):
            self.assertIn(s, take)
        v3 = json.loads((ROOT / "contracts" / "deployments" / "sepolia-v3.json").read_text(encoding="utf-8"))
        v3_plan = json.loads((ROOT / "contracts" / "deployments" / "sepolia-v3.plan.json").read_text(encoding="utf-8"))
        self.assertEqual(v3["supersededBy"], rel)
        self.assertEqual((v3["supersededAt"]["block"], v3["supersededAt"]["race"]), (block, race))
        history = flat(TAKE_PART)
        history = history[history.index("Earlier deployments (history only)."):history.index("## Pick a role")]
        for s in (v3["rid"], v3["addresses"]["race"], str(v3["block"]), "superseded by v3.1", "frozen"):
            self.assertIn(s, history)
        for path in (TAKE_PART, *(G.GUIDES / f"{n}.md" for n in G.NEWCOMERS), README):
            body = flat(path)
            if path == TAKE_PART:
                body = body.replace(history, "")
            with self.subTest(path.name):
                self.assertNotIn(v3["addresses"]["race"], body)
                self.assertNotIn(str(v3["block"]), body)
                self.assertNotIn("sepolia-v3.json", body)
                for image in v3_plan["images"]:
                    self.assertNotIn(image, body)

    def test_the_keeper_and_the_draw_duty(self):
        take = flat(TAKE_PART)
        for s in ("Anyone can keep", "python3 -m oracle.keeper run", "python3 -m oracle.keeper info",
                  "a plain key that pays gas only", "pofctl --v3 draw <check>"):
            self.assertIn(s, take)
        runbook = (ROOT / "validator-kit" / "runbook.md").read_text(encoding="utf-8")
        section = runbook[runbook.index("## Run a keeper"):runbook.index("## The AWS devnet")]
        for s in ("ORACLE_POLL=120", "ORACLE_TX_POLL=3", "ORACLE_KEEPER_MAX_TX_HOUR=60", "ORACLE_KEEPER_ADDRESS=",
                  "ORACLE_RPC_SECRET_ARN=", "ExecStart=/usr/bin/python3 -E -s -B -u -m oracle.keeper run",
                  "About 1.5–2M gas a check", "about 9k RPC calls a day at a 120 s poll",
                  "| `WAKE_ON_DRAW` | `\"true\"`", "| `DRAW_GRACE_BLOCKS` | 25", "| `DRAW_STAGGER_MINUTES` | 10",
                  "| `DRAW_MAX_STARTS` | 1", "| `DRAW_READS_MAX` | 20", "| `MAX_BLOCK_RANGE` |"):
            self.assertIn(s, section)
        self.assertNotRegex(section, r"\d{12}|i-[0-9a-f]{8,}")  # no account id or instance id
        plan = flat(ROOT / "validator-kit" / "SEVSNP-PLAN.md")
        self.assertIn("The draw duty (v3.1 polish VP9).", plan)
        self.assertIn("about 10 minutes of compute per undrawn check", plan)

if __name__ == "__main__":
    unittest.main()
